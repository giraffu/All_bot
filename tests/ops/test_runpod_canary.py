from __future__ import annotations

from pathlib import Path

from ops.gpu_pool_controller.cli import build_parser
from ops.gpu_pool_controller.providers.runpod import RunPodSettings
from ops.gpu_pool_controller.runpod_canary import (
    EXPECTED_MODEL_BUCKET,
    EXPECTED_MODEL_MANIFEST_KEY,
    EXPECTED_MODEL_PREFIX,
    EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL,
    EXPECTED_TEST_BUCKET,
    RunPodCanaryOptions,
    RunPodCanaryRunner,
    result_url_path,
    write_canary_png,
)


PUBLIC_GHCR_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-img2img:"
    "20260612-img2img-lora-kjnodes7967a946"
)


class FakeRunPodProvider:
    def __init__(self, settings: RunPodSettings | None = None) -> None:
        self.settings = settings or RunPodSettings()
        self.create_calls = 0
        self.delete_calls = 0

    def validate_key(self):
        return {"ok": True}

    def list_pods(self, *, managed_only=True, desired_status=None):
        return {"ok": True, "count": 0, "pods": []}

    def reconcile_managed_pods(self, pods=None):
        return {"ok": True, "managed_count": 0, "orphans": []}

    def render_create_pod_request(self, *, task_type, environment, redact=True):
        return {
            "ok": True,
            "json": {
                "imageName": PUBLIC_GHCR_IMAGE,
                "env": {
                    "CENTRAL_API_URL": EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL,
                    "SUPPORTED_TASK_TYPES": "img2img,img2img_lora",
                    "MINIO_INPUT_BUCKET": EXPECTED_TEST_BUCKET,
                    "MINIO_RESULT_BUCKET": EXPECTED_TEST_BUCKET,
                    "MINIO_TEMPLATE_BUCKET": EXPECTED_TEST_BUCKET,
                    "AGENT_SECRET_TOKEN": "{{ RUNPOD_SECRET_agent }}",
                    "MINIO_ACCESS_KEY": "{{ RUNPOD_SECRET_r2_access }}",
                    "MINIO_SECRET_KEY": "{{ RUNPOD_SECRET_r2_secret }}",
                    "RUNPOD_MODEL_SYNC_ENABLED": "true",
                    "RUNPOD_MODEL_BUCKET": EXPECTED_MODEL_BUCKET,
                    "RUNPOD_MODEL_PREFIX": EXPECTED_MODEL_PREFIX,
                    "RUNPOD_MODEL_MANIFEST_KEY": EXPECTED_MODEL_MANIFEST_KEY,
                    "RUNPOD_MODEL_ACCESS_KEY": "{{ RUNPOD_SECRET_model_access }}",
                    "RUNPOD_MODEL_SECRET_KEY": "{{ RUNPOD_SECRET_model_secret }}",
                    "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": "false",
                    "RUNPOD_COMFY_KJNODES_ENABLED": "false",
                },
            },
        }

    def create_pod(self, *, task_type, environment, execute):
        self.create_calls += 1
        return {"ok": True, "pod": {"id": "pod-1"}}

    def delete_pod(self, *, pod_id, task_type, execute):
        self.delete_calls += 1
        return {"ok": True}


def test_runpod_canary_dry_run_preflights_without_mutations():
    provider = FakeRunPodProvider()
    options = RunPodCanaryOptions(execute=False, quiet=True)

    payload = RunPodCanaryRunner(
        provider,
        options,
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is True
    assert payload["execute"] is False
    assert payload["render"]["imageName"] == PUBLIC_GHCR_IMAGE
    assert provider.create_calls == 0
    assert provider.delete_calls == 0
    assert "create one RunPod cloud-test pod" in payload["would_execute"]


def test_runpod_canary_execute_requires_explicit_runpod_gates():
    provider = FakeRunPodProvider(settings=RunPodSettings(dry_run=True))
    options = RunPodCanaryOptions(execute=True, quiet=True)

    payload = RunPodCanaryRunner(
        provider,
        options,
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is False
    assert "RUNPOD_DRY_RUN=false" in payload["error"]
    assert provider.create_calls == 0


def test_canary_png_and_result_url_helpers(tmp_path: Path):
    image_path = tmp_path / "canary.png"

    write_canary_png(image_path)

    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result_url_path("https://r2-test.aivison.it.com/history/a/original.png?sig=secret") == (
        "/history/a/original.png"
    )
    assert result_url_path("/history/a/original.png?sig=secret") == "/history/a/original.png"


def test_cli_parses_runpod_canary_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "canary",
            "--env-file",
            ".env.cloud.test",
            "--no-disable-workers",
            "--prompt",
            "图片中出现一个黑人女性",
            "--input-object-key",
            "user-data-test/web_uploads/3/example.png",
            "--download-results-dir",
            "/tmp/allbot_runpod_canary/results",
            "--quiet",
        ]
    )

    assert args.runpod_command == "canary"
    assert args.env_file == Path(".env.cloud.test")
    assert args.execute is False
    assert args.disable_workers is False
    assert args.prompt == "图片中出现一个黑人女性"
    assert args.input_object_key == "user-data-test/web_uploads/3/example.png"
    assert args.download_results_dir == Path("/tmp/allbot_runpod_canary/results")
