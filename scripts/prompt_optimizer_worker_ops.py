#!/usr/bin/env python3
"""Managed 115 GPU0 handoff between the production image worker and Prompt Optimizer."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/docker-compose-prompt-optimizer-test.yml"
STATE = (
    Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state"))
    / "allbot/prompt-optimizer-test.json"
)
CONTAINER = "allbot-prompt-optimizer-test"
DEFAULT_SLOT = "gpu-115-gpu0-img2img_lora_rocm_gfx1151"
DEFAULT_PHYSICAL_SLOT = "gpu-115-gpu0"
MODEL_ALIAS = "ltx-prompt-optimizer"
LANE_IDS = tuple(f"prompt_optimizer_test_{index:02d}" for index in range(1, 5))
TEST_CENTRAL_URL = "https://worker-central-test.aivison.it.com"


def _exact_image(value: str) -> str:
    if "@sha256:" not in value or len(value.rsplit("@sha256:", 1)[-1]) != 64:
        raise ValueError("image must be pinned by an exact sha256 digest")
    return value


def _run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        check=check,
        text=True,
        capture_output=capture,
    )


def _compose(image: str, env_file: str, *args: str) -> None:
    env = {
        **os.environ,
        "ALLBOT_PROMPT_OPTIMIZER_IMAGE": _exact_image(image),
        "ALLBOT_PROMPT_OPTIMIZER_ENV_FILE": env_file,
    }
    _run(["docker", "compose", "-f", str(COMPOSE), *args], env=env)


def _read_state() -> dict[str, Any]:
    return json.loads(STATE.read_text()) if STATE.is_file() else {}


def _write_state(payload: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(STATE)


def _json_url(url: str, *, method: str = "GET") -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def _container_state() -> dict[str, Any]:
    result = _run(
        ["docker", "inspect", CONTAINER, "--format", "{{json .State}}"],
        check=False,
        capture=True,
    )
    if result.returncode:
        return {"Status": "missing", "Running": False}
    return json.loads(result.stdout)


def _container_image() -> str | None:
    result = _run(
        ["docker", "inspect", CONTAINER, "--format", "{{.Config.Image}}"],
        check=False,
        capture=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _server_running() -> bool:
    result = _run(["lms", "server", "status"], check=False, capture=True)
    return "running" in (result.stdout + result.stderr).lower()


def _model_available(model_key: str) -> bool:
    result = _run(["lms", "ls", "--json"], capture=True)
    models = json.loads(result.stdout)
    return any(
        model_key
        in {
            str(item.get("modelKey") or ""),
            str(item.get("indexedModelIdentifier") or ""),
            str(item.get("path") or ""),
        }
        for item in models
        if isinstance(item, dict) and item.get("vision") is True
    )


def _model_alias_loaded(alias: str) -> bool:
    result = _run(["lms", "ps", "--json"], check=False, capture=True)
    if result.returncode:
        return False
    try:
        models = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return any(
        alias
        in {
            str(item.get("identifier") or ""),
            str(item.get("id") or ""),
            str(item.get("modelKey") or ""),
        }
        for item in models
        if isinstance(item, dict)
    )


def _fleet(
    action: str,
    *,
    slot: str,
    operation_id: str | None = None,
    execute: bool = False,
    physical_slot: str | None = None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts/lan_aio_fleet_prod_ops.py"),
        action,
        "--slot",
        slot,
        "--include-disabled",
    ]
    if physical_slot:
        command.extend(["--physical-slot", physical_slot, "--prefer", "old"])
    if operation_id:
        command.extend(["--operation-id", operation_id])
    if execute:
        command.append("--execute")
    result = _run(command, capture=True)
    return json.loads(result.stdout)


def _wait_ready(*, deadline_seconds: int = 600) -> dict[str, Any]:
    deadline = time.time() + deadline_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            last = _json_url("http://127.0.0.1:8097/ready")
            if (
                last.get("ready") is True
                and last.get("ready_lanes") == 4
                and last.get("active_lanes") == 0
            ):
                return last
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError(f"prompt optimizer did not become ready: {last}")


def _wait_lanes(*, deadline_seconds: int = 180) -> list[dict[str, Any]]:
    deadline = time.time() + deadline_seconds
    last: list[dict[str, Any]] = []
    while time.time() < deadline:
        payload = _json_url(f"{TEST_CENTRAL_URL}/system/workers")
        by_id = {
            str(item.get("agent_id")): item
            for item in payload.get("workers", [])
            if isinstance(item, dict)
        }
        last = [by_id[agent_id] for agent_id in LANE_IDS if agent_id in by_id]
        if len(last) == 4 and all(
            str(item.get("status") or "").lower() == "idle"
            and not item.get("current_task_id")
            and item.get("provider") == "lmstudio"
            for item in last
        ):
            return last
        time.sleep(5)
    observed = sorted(str(item.get("agent_id")) for item in last)
    raise TimeoutError(f"four idle Central lane heartbeats not observed: {observed}")


def _wait_drained(*, deadline_seconds: int = 7200) -> dict[str, Any]:
    _json_url("http://127.0.0.1:8097/drain", method="POST")
    deadline = time.time() + deadline_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _json_url("http://127.0.0.1:8097/health")
        if last.get("draining") is True and last.get("active_lanes") == 0:
            return last
        time.sleep(5)
    raise TimeoutError(f"prompt optimizer lanes did not drain: {last}")


def _stop_optimizer(image: str, env_file: str, *, stop_server: bool) -> None:
    errors: list[str] = []
    try:
        _compose(image, env_file, "down", "--remove-orphans")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        errors.append(f"worker:{type(exc).__name__}")
    _run(["lms", "unload", MODEL_ALIAS], check=False, capture=True)
    if _model_alias_loaded(MODEL_ALIAS):
        errors.append("model:unload_failed")
    if stop_server:
        stopped = _run(["lms", "server", "stop"], check=False, capture=True)
        if stopped.returncode:
            errors.append("server:stop_failed")
    if errors:
        raise RuntimeError("prompt optimizer cleanup failed: " + ",".join(errors))


def _status(*, slot: str) -> dict[str, Any]:
    try:
        health = _json_url("http://127.0.0.1:8097/health")
    except Exception:
        health = {"ready": False, "reason": "unreachable"}
    return {
        "ok": True,
        "state_file": str(STATE),
        "state": _read_state(),
        "container": _container_state(),
        "container_image": _container_image(),
        "lm_studio_server_running": _server_running(),
        "worker_health": health,
        "fleet": _fleet("status", slot=slot),
    }


def _preflight(args: argparse.Namespace) -> dict[str, Any]:
    if not args.env_file:
        raise ValueError("preflight requires --env-file")
    env_file = Path(args.env_file).expanduser().resolve()
    if not env_file.is_file():
        raise FileNotFoundError(f"prompt optimizer env file does not exist: {env_file}")
    image = _exact_image(args.image or _container_image() or "")
    if not _model_available(args.model):
        raise RuntimeError(f"vision model is not available in LM Studio: {args.model}")
    fleet = _fleet("status", slot=args.slot)
    if not fleet.get("ok"):
        raise RuntimeError("LAN AIO fleet status is not healthy")
    return {
        "ok": True,
        "action": "preflight",
        "slot": args.slot,
        "physical_slot": args.physical_slot,
        "image": image,
        "env_file": str(env_file),
        "model": args.model,
        "model_alias": MODEL_ALIAS,
        "container_before": _container_state(),
        "fleet": fleet,
    }


def _takeover(args: argparse.Namespace) -> dict[str, Any]:
    preflight = _preflight(args)
    image = preflight["image"]
    env_file = preflight["env_file"]
    operation_id = args.operation_id or f"prompt-optimizer-takeover-{uuid.uuid4()}"
    server_was_running = _server_running()
    steps: list[dict[str, Any]] = [{"action": "preflight", "payload": preflight}]
    fleet_stopped = False
    try:
        stopped = _fleet(
            "canary-stop-disabled",
            slot=args.slot,
            operation_id=operation_id,
            execute=True,
        )
        fleet_stopped = True
        steps.append({"action": "stop-image-worker", "payload": stopped})
        if not server_was_running:
            _run(["lms", "server", "start", "--port", "1234", "--bind", "127.0.0.1"])
        _run(
            [
                "lms",
                "load",
                args.model,
                "--identifier",
                MODEL_ALIAS,
                "--context-length",
                "16384",
                "--parallel",
                "4",
                "--gpu",
                "max",
                "--yes",
            ]
        )
        steps.append({"action": "load-lm-studio", "model_alias": MODEL_ALIAS})
        _compose(image, env_file, "pull", "prompt-optimizer-worker")
        _compose(
            image, env_file, "up", "-d", "--force-recreate", "prompt-optimizer-worker"
        )
        ready = _wait_ready()
        lanes = _wait_lanes()
        steps.append(
            {
                "action": "verify-worker",
                "health": ready,
                "lane_ids": [item["agent_id"] for item in lanes],
            }
        )
        state = {
            "status": "optimizer_active",
            "operation_id": operation_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "slot": args.slot,
            "physical_slot": args.physical_slot,
            "image": image,
            "env_file": env_file,
            "model": args.model,
            "model_alias": MODEL_ALIAS,
            "server_was_running": server_was_running,
        }
        _write_state(state)
        return {"ok": True, "action": "takeover", "state": state, "steps": steps}
    except Exception as exc:
        recovery: dict[str, Any] | None = None
        cleanup_error: Exception | None = None
        try:
            _stop_optimizer(image, env_file, stop_server=not server_was_running)
        except Exception as stop_exc:
            cleanup_error = stop_exc
        if fleet_stopped and cleanup_error is None:
            recovery = _fleet(
                "recover",
                slot=args.slot,
                physical_slot=args.physical_slot,
                operation_id=f"{operation_id}-rollback",
                execute=True,
            )
        _write_state(
            {
                "status": (
                    "takeover_failed_recovered"
                    if recovery
                    else "takeover_failed_cleanup_blocked"
                    if cleanup_error
                    else "preflight_failed"
                ),
                "operation_id": operation_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "error": type(exc).__name__,
                "cleanup_error": type(cleanup_error).__name__
                if cleanup_error
                else None,
            }
        )
        raise RuntimeError(
            "prompt optimizer takeover failed; "
            f"cleanup={'failed' if cleanup_error else 'succeeded'}; "
            f"recovery={'succeeded' if recovery else 'not-needed'}: {exc}"
        ) from exc


def _recover(args: argparse.Namespace) -> dict[str, Any]:
    state = _read_state()
    if state.get("status") != "optimizer_active":
        raise RuntimeError("no active prompt optimizer takeover is recorded")
    image = _exact_image(str(state["image"]))
    env_file = str(state["env_file"])
    drained = _wait_drained()
    _stop_optimizer(
        image, env_file, stop_server=not bool(state.get("server_was_running"))
    )
    operation_id = args.operation_id or f"prompt-optimizer-recover-{uuid.uuid4()}"
    fleet = _fleet(
        "recover",
        slot=str(state["slot"]),
        physical_slot=str(state["physical_slot"]),
        operation_id=operation_id,
        execute=True,
    )
    recovered = {
        **state,
        "status": "image_worker_restored",
        "recovery_operation_id": operation_id,
        "recovered_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_state(recovered)
    return {
        "ok": True,
        "action": "recover",
        "optimizer_drain": drained,
        "fleet": fleet,
        "state": recovered,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("preflight", "takeover", "recover", "status")
    )
    parser.add_argument("--image")
    parser.add_argument("--env-file")
    parser.add_argument(
        "--model", default="qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive"
    )
    parser.add_argument("--slot", default=DEFAULT_SLOT)
    parser.add_argument("--physical-slot", default=DEFAULT_PHYSICAL_SLOT)
    parser.add_argument("--operation-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "status":
        payload = _status(slot=args.slot)
    elif args.action == "preflight":
        payload = _preflight(args)
    elif args.action == "takeover":
        payload = _takeover(args)
    else:
        payload = _recover(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
