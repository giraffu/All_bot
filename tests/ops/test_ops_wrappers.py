import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_lan_aio_prod_ops_shell_syntax():
    result = run_script("bash", "-n", "scripts/lan_aio_prod_ops.sh")

    assert result.returncode == 0, result.stderr


def test_runpod_prod_ops_shell_syntax():
    result = run_script("bash", "-n", "scripts/runpod_prod_ops.sh")

    assert result.returncode == 0, result.stderr


def test_lan_aio_enable_dry_run_shows_safe_order():
    result = run_script("bash", "scripts/lan_aio_prod_ops.sh", "enable-aio", "--dry-run")

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "Would verify AIO 8190/8191 health" in output
    assert "Would set cloud_prod_worker_06/07 to draining" in output
    assert "Would wait until legacy workers" in output
    assert "enable both LAN AIO agents" in output


def test_lan_aio_rollback_dry_run_shows_restore_order():
    result = run_script("bash", "scripts/lan_aio_prod_ops.sh", "rollback", "--dry-run")

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "Would set both LAN AIO agents to draining" in output
    assert "Would start old gpu-002 comfy0/comfy1" in output
    assert "Would start cloud-prod-comfy-agent-6/7" in output
    assert "Would restore legacy worker controls and disable AIO controls" in output


def test_runpod_enable_requires_profile():
    result = run_script("bash", "scripts/runpod_prod_ops.sh", "enable", "--dry-run")

    assert result.returncode == 2
    assert "--profile is required for enable" in result.stderr


def test_runpod_scale_requires_desired():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "scale",
        "--profile",
        "img2img",
        "--dry-run",
    )

    assert result.returncode == 2
    assert "--desired is required for scale" in result.stderr


def test_runpod_enable_dry_run_delegates_to_prod_worker_without_execute_mode():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "enable",
        "--profile",
        "img2img",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "Would enable the selected cloud-prod manual RunPod worker" in output
    assert "runpod prod-worker enable" in output
    assert "--profile img2img" in output
    assert "--execute" in output


def test_runpod_rollback_delete_profile_dry_run_scales_to_zero():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "rollback",
        "--profile",
        "img2img",
        "--delete-pod",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "scaling the selected profile to desired=0" in output
    assert "runpod prod-worker scale" in output
    assert "--desired 0" in output


def test_runpod_rollback_delete_slot_dry_run_uses_down():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "rollback",
        "--profile",
        "img2img",
        "--slot",
        "01",
        "--delete-pod",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "deleting selected slot 01" in output
    assert "runpod prod-worker down" in output


def test_runpod_scale_retry_unavailable_dry_run_is_bounded():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "scale",
        "--profile",
        "img2img",
        "--desired",
        "2",
        "--retry-unavailable",
        "--max-attempts",
        "3",
        "--retry-interval",
        "1",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "retry RunPod no-inventory responses up to 3 attempts every 1s" in output
    assert "runpod prod-worker scale" in output
    assert "--desired 2" in output


def test_runpod_scale_retry_unavailable_retries_transient_no_inventory(tmp_path):
    fake_controller = tmp_path / "fake_controller.py"
    counter_file = tmp_path / "attempts.txt"
    fake_controller.write_text(
        """
import os
import pathlib
import sys

counter = pathlib.Path(os.environ["RUNPOD_FAKE_COUNTER"])
attempt = int(counter.read_text() or "0") if counter.exists() else 0
attempt += 1
counter.write_text(str(attempt))
if attempt == 1:
    print("There are no instances currently available")
    raise SystemExit(2)
print("ok")
raise SystemExit(0)
""".lstrip()
    )

    env = os.environ.copy()
    env["RUNPOD_PROD_OPS_CONTROLLER"] = str(fake_controller)
    env["RUNPOD_FAKE_COUNTER"] = str(counter_file)
    result = subprocess.run(
        [
            "bash",
            "scripts/runpod_prod_ops.sh",
            "scale",
            "--profile",
            "img2img",
            "--desired",
            "2",
            "--retry-unavailable",
            "--max-attempts",
            "2",
            "--retry-interval",
            "0",
            "--execute",
        ],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert counter_file.read_text() == "2"
    assert "There are no instances currently available" in result.stdout
    assert "RunPod inventory unavailable; retry 1/2" in result.stderr
