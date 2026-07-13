import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "watch_cloud_worker_recovery.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _make_fakebin(tmp_path: Path) -> tuple[Path, Path]:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    docker_log = tmp_path / "docker.log"

    _write_executable(
        fakebin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$FAKE_DOCKER_LOG"
if [ "${1:-}" = "compose" ] && [ "${2:-}" = "version" ]; then
  exit 0
fi
if [ "${1:-}" = "inspect" ]; then
  echo "true"
  exit 0
fi
exit 0
""",
    )
    _write_executable(
        fakebin / "curl",
        """#!/usr/bin/env bash
set -euo pipefail
url="${@: -1}"
want_status=0
for arg in "$@"; do
  if [ "$arg" = "%{http_code}" ]; then want_status=1; fi
done
respond() {
  local status="$1"
  local body="${2:-}"
  if [ "$want_status" = "1" ]; then
    printf '%s' "$status"
  else
    printf '%s' "$body"
  fi
}
if [ "${FAKE_GLOBAL_NETWORK_FAIL:-0}" = "1" ]; then
  if [ "$want_status" = "1" ]; then printf '000'; fi
  exit 28
fi
case "$url" in
  */system_stats)
    exit 0
    ;;
  */ready)
    if [ "${FAKE_RELAY_READY_FAIL:-0}" = "1" ]; then
      respond "${FAKE_RELAY_READY_STATUS:-503}" '{"status":"error"}'
      exit 0
    fi
    respond 200 '{"status":"ok"}'
    exit 0
    ;;
  */health)
    if [ "${FAKE_CENTRAL_FAIL:-0}" = "1" ]; then exit 22; fi
    respond 200 '{"status":"ok"}'
    exit 0
    ;;
  */system/workers)
    respond 200 "$FAKE_WORKERS_JSON"
    exit 0
    ;;
esac
if [ "$want_status" = "1" ]; then printf '404'; fi
exit 22
""",
    )
    return fakebin, docker_log


def _workers_payload(*, worker_4_status: str = "running") -> str:
    workers = []
    for idx in range(1, 8):
        status = worker_4_status if idx == 4 else "running"
        workers.append({"agent_id": f"cloud_worker_test_{idx:02d}", "status": status})
    return json.dumps({"workers": workers})


def _run_watchdog(
    tmp_path: Path,
    *,
    mode: str,
    workers_json: str | None = None,
    extra_env: dict[str, str] | None = None,
    state_dir: Path | None = None,
):
    fakebin, docker_log = _make_fakebin(tmp_path)
    env_file = tmp_path / ".env.cloud.test"
    compose_file = tmp_path / "docker-compose-cloud-worker-test.yml"
    env_file.write_text(
        "CLOUD_TEST_CONTROL_HOST=central.test\nCLOUD_TEST_LOCAL_RELAY_PORT=8014\n",
        encoding="utf-8",
    )
    compose_file.write_text("services: {}\n", encoding="utf-8")

    env = {
        **os.environ,
        "PATH": f"{fakebin}:{os.environ['PATH']}",
        "FAKE_DOCKER_LOG": str(docker_log),
        "FAKE_WORKERS_JSON": workers_json or _workers_payload(),
        "CLOUD_WORKER_RECOVERY_ENV_FILE": str(env_file),
        "CLOUD_WORKER_RECOVERY_COMPOSE_FILE": str(compose_file),
    }
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [
            str(SCRIPT),
            "--env",
            "cloud-test",
            "--mode",
            mode,
            "--state-dir",
            str(state_dir or tmp_path / "state"),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, docker_log


def test_watchdog_dry_run_plans_single_worker_recovery(tmp_path):
    result, docker_log = _run_watchdog(
        tmp_path,
        mode="dry-run",
        workers_json=_workers_payload(worker_4_status="error"),
    )

    assert result.returncode == 0
    assert "[dry-run] would recover service=cloud-comfy-agent-test-4" in result.stdout
    assert "restart cloud-comfy-agent-test-4" not in docker_log.read_text(
        encoding="utf-8"
    )


def test_watchdog_execute_restarts_only_target_worker(tmp_path):
    result, docker_log = _run_watchdog(
        tmp_path,
        mode="execute",
        workers_json=_workers_payload(worker_4_status="quarantined"),
    )

    assert result.returncode == 0
    docker_calls = docker_log.read_text(encoding="utf-8")
    assert "restart cloud-comfy-agent-test-4" in docker_calls
    assert "restart cloud-comfy-agent-test-3" not in docker_calls


def test_watchdog_execute_restarts_relay_when_ready_unhealthy(tmp_path):
    result, docker_log = _run_watchdog(
        tmp_path,
        mode="execute",
        extra_env={"FAKE_RELAY_READY_FAIL": "1", "FAKE_RELAY_READY_STATUS": "503"},
    )

    assert result.returncode == 0
    docker_calls = docker_log.read_text(encoding="utf-8")
    assert "restart cloud-worker-relay-test" in docker_calls
    assert "relay_ready_failed_status_503" in result.stdout


def test_watchdog_ready_404_does_not_restart_relay(tmp_path):
    result, docker_log = _run_watchdog(
        tmp_path,
        mode="execute",
        extra_env={"FAKE_RELAY_READY_FAIL": "1", "FAKE_RELAY_READY_STATUS": "404"},
    )

    assert result.returncode == 0
    assert "relay_ready_endpoint_missing" in result.stdout
    assert "restart cloud-worker-relay-test" not in docker_log.read_text(
        encoding="utf-8"
    )


def test_watchdog_global_network_outage_does_not_restart(tmp_path):
    result, docker_log = _run_watchdog(
        tmp_path,
        mode="execute",
        extra_env={"FAKE_GLOBAL_NETWORK_FAIL": "1"},
    )

    assert result.returncode == 0
    assert "network_outage" in result.stdout
    assert "restart " not in docker_log.read_text(encoding="utf-8")


def test_watchdog_cooldown_blocks_repeated_restart(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "cloud-test_cloud-comfy-agent-test-4.last").write_text(
        str(int(time.time())),
        encoding="utf-8",
    )

    result, docker_log = _run_watchdog(
        tmp_path,
        mode="execute",
        workers_json=_workers_payload(worker_4_status="missing"),
        state_dir=state_dir,
    )

    assert result.returncode == 0
    assert "cooldown service=cloud-comfy-agent-test-4" in result.stdout
    assert "restart cloud-comfy-agent-test-4" not in docker_log.read_text(
        encoding="utf-8"
    )
