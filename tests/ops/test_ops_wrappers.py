import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WHOLE_REPO_RSYNC_SCRIPTS = (
    "scripts/update_cloud_prod_with_maintenance.sh",
    "scripts/update_cloud_prod_qqcc_bot.sh",
    "scripts/update_cloud_test_with_maintenance.sh",
)
RETIRED_CLOUD_TEST_BUILD_SCRIPTS = (
    "scripts/migrate_local_test_to_cloud_containers.sh",
    "scripts/cleanup_cloud_test_for_prod.sh",
    "scripts/safe_deploy_cloud_prod.sh",
)


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


def test_cloud_prod_qqcc_update_shell_syntax():
    result = run_script("bash", "-n", "scripts/update_cloud_prod_qqcc_bot.sh")

    assert result.returncode == 0, result.stderr


def test_retired_full_stack_cloud_compose_is_not_an_active_entrypoint():
    assert not (ROOT / "deploy/docker-compose-cloud-prod.yml").exists()
    assert not (ROOT / "scripts/safe_deploy_cloud_test.sh").exists()


def test_root_docker_context_excludes_runtime_backups():
    patterns = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {"backups/", "runtime/"} <= patterns


def test_quota_module_parses_on_the_production_python_version():
    image = "python:3.10-slim"
    if run_script("docker", "image", "inspect", image).returncode != 0:
        pytest.skip("the production Python image is unavailable")

    result = run_script(
        "docker",
        "run",
        "--rm",
        "-v",
        f"{ROOT}:/workspace:ro",
        image,
        "python",
        "-c",
        (
            "path='/workspace/src/quota.py';"
            "compile(open(path,encoding='utf-8').read(),path,'exec')"
        ),
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", WHOLE_REPO_RSYNC_SCRIPTS)
def test_legacy_sync_entrypoints_are_fail_closed(script: str):
    script_text = (ROOT / script).read_text()
    result = run_script("bash", script)

    assert result.returncode == 2
    assert "scripts/release.py" in result.stderr
    assert "rsync " not in script_text


@pytest.mark.parametrize("script", RETIRED_CLOUD_TEST_BUILD_SCRIPTS)
def test_legacy_cloud_test_build_entrypoints_are_fail_closed(script: str):
    result = run_script("bash", script)

    assert result.returncode == 2
    assert "RETIRED" in result.stderr
    assert "scripts/release.py" in result.stderr


def test_lan_aio_enable_dry_run_shows_safe_order():
    result = run_script(
        "bash", "scripts/lan_aio_prod_ops.sh", "enable-aio", "--dry-run"
    )

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


def test_runpod_artifact_rollout_requires_single_slot_and_artifact():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "rollout-artifact",
        "--profile",
        "i2i_pro",
        "--dry-run",
    )

    assert result.returncode == 2
    assert "--slot and --artifact" in result.stderr


def test_runpod_artifact_rollout_rejects_mutable_artifact():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "rollout-artifact",
        "--profile",
        "image_to_video",
        "--slot",
        "01",
        "--artifact",
        "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:legacy-tag",
        "--dry-run",
    )

    assert result.returncode == 2
    assert "--artifact must be an exact digest-pinned image" in result.stderr


def test_runpod_release_rollout_help_documents_legacy_digest_migration():
    result = run_script("bash", "scripts/runpod_prod_ops.sh", "--help")

    assert result.returncode == 0, result.stderr
    assert "--rollback-ref <repo@sha256:...>" in result.stdout
    assert "live legacy" in result.stdout


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


def test_runpod_add_requires_count():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "add",
        "--profile",
        "img2img",
        "--dry-run",
    )

    assert result.returncode == 2
    assert "--count is required for add" in result.stderr


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


def test_runpod_restart_dry_run_delegates_to_prod_worker():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "restart",
        "--profile",
        "wan22_video_v2",
        "--slot",
        "03",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "Would restart the selected cloud-prod manual RunPod Pod in place" in output
    assert "runpod prod-worker restart" in output
    assert "--profile wan22_video_v2" in output
    assert "--slot 03" in output
    assert "--execute" in output


def test_runpod_scail2_canary_dry_run_delegates_to_prod_worker():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "canary",
        "--profile",
        "scail2",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "runpod prod-worker canary" in output
    assert "--profile scail2" in output
    assert "--execute" in output


def test_runpod_bf16_canary_dry_run_uses_isolated_profile():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "canary",
        "--profile",
        "pornmaster_flux2_edit_bf16",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "runpod prod-worker canary" in output
    assert "--profile pornmaster_flux2_edit_bf16" in output
    assert "--execute" in output


def test_runpod_minimax_h3_canary_dry_run_uses_manual_profile():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "canary",
        "--profile",
        "minimax_h3",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "runpod prod-worker canary" in output
    assert "--profile minimax_h3" in output
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


def test_runpod_down_dry_run_forwards_explicit_drain_timeout():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "down",
        "--profile",
        "minimax_h3",
        "--slot",
        "03",
        "--drain-timeout",
        "7200",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "--drain-timeout 7200" in result.stdout


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
    assert (
        "retry RunPod inventory/resource-unavailable responses up to 3 attempts every 1s"
        in output
    )
    assert "runpod prod-worker scale" in output
    assert "--desired 2" in output


def test_runpod_add_retry_unavailable_dry_run_is_additive():
    result = run_script(
        "bash",
        "scripts/runpod_prod_ops.sh",
        "add",
        "--profile",
        "img2img",
        "--count",
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
    assert "Would add 2 cloud-prod manual RunPod worker" in output
    assert (
        "Would not enable, disable, drain, delete, or recreate any existing RunPod slot"
        in output
    )
    assert (
        "retry RunPod inventory/resource-unavailable responses up to 3 attempts every 1s"
        in output
    )
    assert "runpod prod-worker add" in output
    assert "--count 2" in output


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
    assert "RunPod inventory/resource unavailable; retry 1/2" in result.stderr


@pytest.mark.parametrize(
    "error_output",
    [
        (
            "runpod create-pod failed for slot 02: runpod_http_500: "
            '{"error":"create pod: This machine does not have the resources '
            'to deploy your pod. Please try a different machine","status":500}'
        ),
        (
            "runpod create-pod failed for slot 03: runpod_http_500: "
            '{"error":"create pod: Something went wrong. Please try again later '
            'or contact support.","status":500}'
        ),
    ],
)
def test_runpod_add_retry_unavailable_retries_runpod_create_pod_resource_errors(
    tmp_path,
    error_output,
):
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
    print(os.environ["RUNPOD_FAKE_ERROR"])
    raise SystemExit(2)
print("ok")
raise SystemExit(0)
""".lstrip()
    )

    env = os.environ.copy()
    env["RUNPOD_PROD_OPS_CONTROLLER"] = str(fake_controller)
    env["RUNPOD_FAKE_COUNTER"] = str(counter_file)
    env["RUNPOD_FAKE_ERROR"] = error_output
    result = subprocess.run(
        [
            "bash",
            "scripts/runpod_prod_ops.sh",
            "add",
            "--profile",
            "wan22_video_v2",
            "--count",
            "1",
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
    assert error_output in result.stdout
    assert "RunPod inventory/resource unavailable; retry 1/2" in result.stderr
