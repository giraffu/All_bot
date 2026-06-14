from __future__ import annotations

from pathlib import Path

import pytest

from ops.gpu_pool_controller.cli import build_parser
from ops.gpu_pool_controller.providers.runpod import RunPodSettings
from ops.gpu_pool_controller.runpod_canary import (
    EXPECTED_I2I_PRO_GPU_TYPE_IDS,
    EXPECTED_I2I_PRO_IMAGE_REF_PREFIX,
    EXPECTED_I2I_PRO_MODEL_MANIFEST_KEY,
    EXPECTED_I2I_PRO_MODEL_PREFIX,
    EXPECTED_MODEL_BUCKET,
    EXPECTED_MODEL_MANIFEST_KEY,
    EXPECTED_MODEL_PREFIX,
    EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL,
    EXPECTED_TEST_BUCKET,
    EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
    EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX,
    EXPECTED_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
    EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX,
    RunPodCanaryOptions,
    RunPodCanaryError,
    RunPodCanaryRunner,
    result_url_path,
    write_canary_png,
)


PUBLIC_GHCR_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946"
)
PUBLIC_WAN22_GHCR_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260612-wan22aio-test"
)
PUBLIC_I2I_PRO_GHCR_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:20260614-i2ipro-test"
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
        if task_type == "wan22_aio_video":
            image_name = PUBLIC_WAN22_GHCR_IMAGE
            supported_task_types = "image_to_video,wan22_video_v2"
            model_prefix = EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX
            model_manifest_key = EXPECTED_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY
            gpu_type_ids = list(EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS)
            template_id = (
                self.settings.template_id_wan22_aio_video
                if self.settings.use_template_wan22_aio_video
                else ""
            )
        elif task_type == "i2i_pro":
            image_name = PUBLIC_I2I_PRO_GHCR_IMAGE
            supported_task_types = "i2i_pro"
            model_prefix = EXPECTED_I2I_PRO_MODEL_PREFIX
            model_manifest_key = EXPECTED_I2I_PRO_MODEL_MANIFEST_KEY
            gpu_type_ids = list(EXPECTED_I2I_PRO_GPU_TYPE_IDS)
            template_id = (
                self.settings.template_id_i2i_pro
                if self.settings.use_template_i2i_pro
                else ""
            )
        else:
            image_name = PUBLIC_GHCR_IMAGE
            supported_task_types = "img2img,img2img_lora"
            model_prefix = EXPECTED_MODEL_PREFIX
            model_manifest_key = EXPECTED_MODEL_MANIFEST_KEY
            gpu_type_ids = ["NVIDIA GeForce RTX 4090"]
            template_id = ""
        body = {
            "gpuTypeIds": gpu_type_ids,
            "env": {
                "CENTRAL_API_URL": EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL,
                "SUPPORTED_TASK_TYPES": supported_task_types,
                "MINIO_INPUT_BUCKET": EXPECTED_TEST_BUCKET,
                "MINIO_RESULT_BUCKET": EXPECTED_TEST_BUCKET,
                "MINIO_TEMPLATE_BUCKET": EXPECTED_TEST_BUCKET,
                "AGENT_SECRET_TOKEN": "{{ RUNPOD_SECRET_agent }}",
                "MINIO_ACCESS_KEY": "{{ RUNPOD_SECRET_r2_access }}",
                "MINIO_SECRET_KEY": "{{ RUNPOD_SECRET_r2_secret }}",
                "RUNPOD_MODEL_SYNC_ENABLED": "true",
                "RUNPOD_MODEL_BUCKET": EXPECTED_MODEL_BUCKET,
                "RUNPOD_MODEL_PREFIX": model_prefix,
                "RUNPOD_MODEL_MANIFEST_KEY": model_manifest_key,
                "RUNPOD_MODEL_ACCESS_KEY": "{{ RUNPOD_SECRET_model_access }}",
                "RUNPOD_MODEL_SECRET_KEY": "{{ RUNPOD_SECRET_model_secret }}",
                "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": "false",
                "RUNPOD_COMFY_KJNODES_ENABLED": "false",
            },
        }
        if template_id:
            body["templateId"] = template_id
        else:
            body["imageName"] = image_name
        return {
            "ok": True,
            "json": body,
        }

    def create_pod(self, *, task_type, environment, execute):
        self.create_calls += 1
        return {"ok": True, "pod": {"id": "pod-1"}}

    def delete_pod(self, *, pod_id, task_type, execute):
        self.delete_calls += 1
        return {"ok": True}

    def pod_readiness(self, *, pod_id):
        return {"ok": True, "readiness": {"infrastructure_ready": False}}


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


def test_runpod_canary_wan22_dry_run_preflights_with_profile_specific_render():
    provider = FakeRunPodProvider()
    options = RunPodCanaryOptions(
        task_type="wan22_aio_video",
        execute=False,
        quiet=True,
    )

    payload = RunPodCanaryRunner(
        provider,
        options,
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is True
    assert payload["render"]["imageName"].startswith(
        EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX
    )
    assert payload["render"]["gpu_type_ids"] == list(
        EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS
    )
    assert payload["render"]["supported_task_types"] == "image_to_video,wan22_video_v2"
    assert payload["render"]["model_prefix"] == EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX
    assert (
        payload["render"]["model_manifest_key"]
        == EXPECTED_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY
    )
    assert (
        "submit image_to_video and wan22_video_v2 preview/5s Web tasks serially"
        in (payload["would_execute"])
    )
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_runpod_canary_wan22_dry_run_accepts_template_render():
    provider = FakeRunPodProvider(
        RunPodSettings(
            use_template_wan22_aio_video=True,
            template_id_wan22_aio_video="77gi0wqo8x",
        )
    )
    options = RunPodCanaryOptions(
        task_type="wan22_aio_video",
        execute=False,
        quiet=True,
    )

    payload = RunPodCanaryRunner(
        provider,
        options,
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is True
    assert payload["render"]["imageName"] is None
    assert payload["render"]["templateId"] == "77gi0wqo8x"
    assert payload["render"]["uses_template"] is True
    assert payload["render"]["gpu_type_ids"] == list(
        EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS
    )
    assert payload["render"]["model_prefix"] == EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_runpod_canary_i2i_pro_dry_run_preflights_with_profile_specific_render():
    provider = FakeRunPodProvider()
    options = RunPodCanaryOptions(
        task_type="i2i_pro",
        execute=False,
        quiet=True,
    )

    payload = RunPodCanaryRunner(
        provider,
        options,
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is True
    assert payload["render"]["imageName"].startswith(EXPECTED_I2I_PRO_IMAGE_REF_PREFIX)
    assert payload["render"]["gpu_type_ids"] == list(EXPECTED_I2I_PRO_GPU_TYPE_IDS)
    assert payload["render"]["supported_task_types"] == "i2i_pro"
    assert payload["render"]["model_prefix"] == EXPECTED_I2I_PRO_MODEL_PREFIX
    assert payload["render"]["model_manifest_key"] == EXPECTED_I2I_PRO_MODEL_MANIFEST_KEY
    assert "submit one i2i_pro Web task" in payload["would_execute"]
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_runpod_canary_execute_requires_explicit_runpod_gates():
    provider = FakeRunPodProvider(settings=RunPodSettings(dry_run=True))
    options = RunPodCanaryOptions(execute=True, quiet=True, disable_workers=False)

    payload = RunPodCanaryRunner(
        provider,
        options,
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is False
    assert "RUNPOD_DRY_RUN=false" in payload["error"]
    assert provider.create_calls == 0


def test_runpod_canary_keyboard_interrupt_returns_cleanup_summary():
    provider = FakeRunPodProvider(
        settings=RunPodSettings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=1,
            max_pods_per_type=1,
        )
    )
    options = RunPodCanaryOptions(execute=True, quiet=True, disable_workers=False)

    def raise_keyboard_interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    runner = RunPodCanaryRunner(
        provider,
        options,
        sleep_func=raise_keyboard_interrupt,
    )
    runner._run_web_preflight = lambda summary: None  # type: ignore[method-assign]

    payload = runner.run()

    assert payload["ok"] is False
    assert payload["error"] == "interrupted"
    assert payload["cleanup"]["pod_delete"] == {"pod_id": "pod-1", "ok": True}
    assert provider.delete_calls == 1


def test_canary_png_and_result_url_helpers(tmp_path: Path):
    image_path = tmp_path / "canary.png"

    write_canary_png(image_path)

    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result_url_path(
        "https://r2-test.aivison.it.com/history/a/original.png?sig=secret"
    ) == ("/history/a/original.png")
    assert (
        result_url_path("/history/a/original.png?sig=secret")
        == "/history/a/original.png"
    )


def test_wan22_canary_task_cases_are_preview_5s_single_frame():
    runner = RunPodCanaryRunner(
        FakeRunPodProvider(),
        RunPodCanaryOptions(task_type="wan22_aio_video", quiet=True),
    )

    cases = runner._task_cases("user-data-test/web_uploads/3/example.png")

    assert [case["label"] for case in cases] == [
        "image_to_video_preview_5s",
        "wan22_video_v2_preview_5s",
    ]
    assert [case["payload"]["task_type"] for case in cases] == [
        "image_to_video",
        "wan22_video_v2",
    ]
    for case in cases:
        inputs = case["payload"]["inputs"]
        assert inputs["image"] == "user-data-test/web_uploads/3/example.png"
        assert inputs["resolution_preset"] == "preview"
        assert inputs["duration_seconds"] == 5
        assert inputs["extract_last_frame"] is True
        assert "end_image" not in inputs
        assert "lora_name" not in inputs
    assert (
        cases[0]["payload"]["inputs"]["wan22_model_profile"] == "legacy_image_to_video"
    )
    assert cases[1]["payload"]["inputs"]["wan22_model_profile"] == "wan22_video_v2"


def test_i2i_pro_canary_task_case_submits_existing_task_type():
    runner = RunPodCanaryRunner(
        FakeRunPodProvider(),
        RunPodCanaryOptions(task_type="i2i_pro", quiet=True),
    )

    cases = runner._task_cases("user-data-test/web_uploads/3/example.png")

    assert [case["label"] for case in cases] == ["i2i_pro_single_image"]
    payload = cases[0]["payload"]
    assert payload["task_type"] == "i2i_pro"
    assert payload["inputs"]["image"] == "user-data-test/web_uploads/3/example.png"
    assert payload["inputs"]["images"] == ["user-data-test/web_uploads/3/example.png"]
    assert payload["inputs"]["seed"] == 20260614
    assert "lora_name" not in payload["inputs"]
    assert "wan22_model_profile" not in payload["inputs"]


def test_wan22_canary_validates_last_frame_extra_output():
    runner = RunPodCanaryRunner(
        FakeRunPodProvider(),
        RunPodCanaryOptions(task_type="wan22_aio_video", quiet=True),
    )
    runner._http_request = lambda *args, **kwargs: {"raw": b"png-bytes"}  # type: ignore[method-assign]

    result = runner._validate_wan22_last_frame_if_required(
        label="wan22_video_v2_preview_5s",
        task_id="task-1",
        result_payload={
            "extra_outputs": {
                "last_frame": {
                    "path": "123/output_images/task-1_last_frame.png",
                    "url": "https://cdn.example/task-1_last_frame.png",
                    "media_type": "image",
                }
            }
        },
    )

    assert result["last_frame_bytes"] == len(b"png-bytes")
    assert result["last_frame_path"] == "/task-1_last_frame.png"
    assert result["last_frame_download_method"] == "public_url"


def test_wan22_canary_requires_last_frame_extra_output():
    runner = RunPodCanaryRunner(
        FakeRunPodProvider(),
        RunPodCanaryOptions(task_type="wan22_aio_video", quiet=True),
    )

    with pytest.raises(RunPodCanaryError, match="missing extra_outputs.last_frame"):
        runner._validate_wan22_last_frame_if_required(
            label="wan22_video_v2_preview_5s",
            task_id="task-1",
            result_payload={"extra_outputs": {}},
        )


def test_wan22_canary_waits_for_profile_specific_runpod_worker():
    runner = RunPodCanaryRunner(
        FakeRunPodProvider(),
        RunPodCanaryOptions(task_type="wan22_aio_video", quiet=True),
        sleep_func=lambda _seconds: None,
    )
    runner._fetch_workers = lambda: [  # type: ignore[method-assign]
        {
            "agent_id": "runpod_test_img2img_lora_pod-1",
            "types": "img2img,img2img_lora",
            "status": "idle",
        },
        {
            "agent_id": "runpod_test_wan22_aio_video_pod-1",
            "types": "image_to_video,wan22_video_v2",
            "status": "idle",
            "provider": "runpod",
        },
    ]
    summary = {}

    worker = runner._wait_runpod_worker("pod-1", summary)

    assert worker["agent_id"] == "runpod_test_wan22_aio_video_pod-1"
    assert summary["runpod_worker"]["runtime_profile"] is None


def test_wan22_canary_disables_only_matching_cloud_test_non_runpod_workers():
    runner = RunPodCanaryRunner(
        FakeRunPodProvider(),
        RunPodCanaryOptions(
            task_type="wan22_aio_video",
            quiet=True,
            worker_ids=("cloud_worker_test_01", "cloud_worker_test_02"),
            worker_ids_explicit=False,
        ),
    )
    runner._fetch_workers = lambda: [  # type: ignore[method-assign]
        {"agent_id": "cloud_worker_test_01", "types": "img2img,img2img_lora"},
        {"agent_id": "cloud_worker_test_05", "types": "wan22_video_v2"},
        {"agent_id": "cloud_worker_test_07", "types": "video_insert,image_to_video"},
        {
            "agent_id": "runpod_test_wan22_aio_video_pod-1",
            "types": "image_to_video,wan22_video_v2",
            "provider": "runpod",
        },
        {"agent_id": "cloud_prod_worker_05", "types": "wan22_video_v2"},
    ]
    runner._get_agent_control = lambda agent_id: {"state": "enabled", "reason": ""}  # type: ignore[method-assign]
    disabled = []
    runner._set_agent_control = (  # type: ignore[method-assign]
        lambda agent_id, state, **_kwargs: disabled.append((agent_id, state))
    )

    controls = runner._disable_test_workers({})

    assert [item["agent_id"] for item in controls] == [
        "cloud_worker_test_05",
        "cloud_worker_test_07",
    ]
    assert disabled == [
        ("cloud_worker_test_05", "disabled"),
        ("cloud_worker_test_07", "disabled"),
    ]


def test_i2i_pro_canary_disables_only_matching_cloud_test_non_runpod_workers():
    runner = RunPodCanaryRunner(
        FakeRunPodProvider(),
        RunPodCanaryOptions(
            task_type="i2i_pro",
            quiet=True,
            worker_ids=("cloud_worker_test_01", "cloud_worker_test_02"),
            worker_ids_explicit=False,
        ),
    )
    runner._fetch_workers = lambda: [  # type: ignore[method-assign]
        {"agent_id": "cloud_worker_test_01", "types": "img2img,img2img_lora"},
        {"agent_id": "cloud_worker_test_03", "types": "face_swap,i2i_pro"},
        {
            "agent_id": "runpod_test_i2i_pro_pod-1",
            "types": "i2i_pro",
            "provider": "runpod",
        },
        {"agent_id": "cloud_prod_worker_01", "types": "i2i_pro"},
    ]
    runner._get_agent_control = lambda agent_id: {"state": "enabled", "reason": ""}  # type: ignore[method-assign]
    disabled = []
    runner._set_agent_control = (  # type: ignore[method-assign]
        lambda agent_id, state, **_kwargs: disabled.append((agent_id, state))
    )

    controls = runner._disable_test_workers({})

    assert [item["agent_id"] for item in controls] == ["cloud_worker_test_03"]
    assert disabled == [("cloud_worker_test_03", "disabled")]


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


def test_cli_parses_wan22_render_and_canary_commands():
    render_args = build_parser().parse_args(
        [
            "runpod",
            "render-create",
            "--task-type",
            "wan22_aio_video",
            "--env",
            "cloud-test",
        ]
    )
    canary_args = build_parser().parse_args(
        [
            "runpod",
            "canary",
            "--task-type",
            "wan22_aio_video",
            "--env",
            "cloud-test",
            "--quiet",
        ]
    )

    assert render_args.runpod_command == "render-create"
    assert render_args.task_type == "wan22_aio_video"
    assert render_args.env == "cloud-test"
    assert canary_args.runpod_command == "canary"
    assert canary_args.task_type == "wan22_aio_video"
    assert canary_args.quiet is True


def test_cli_parses_i2i_pro_render_and_canary_commands():
    render_args = build_parser().parse_args(
        [
            "runpod",
            "render-create",
            "--task-type",
            "i2i_pro",
            "--env",
            "cloud-test",
        ]
    )
    canary_args = build_parser().parse_args(
        [
            "runpod",
            "canary",
            "--task-type",
            "i2i_pro",
            "--env",
            "cloud-test",
            "--quiet",
        ]
    )

    assert render_args.runpod_command == "render-create"
    assert render_args.task_type == "i2i_pro"
    assert render_args.env == "cloud-test"
    assert canary_args.runpod_command == "canary"
    assert canary_args.task_type == "i2i_pro"
    assert canary_args.quiet is True


def test_cli_parses_split_video_workers_render_scale_commands():
    image_to_video_args = build_parser().parse_args(
        [
            "runpod",
            "workers",
            "render-scale",
            "--profile",
            "image_to_video",
            "--desired",
            "1",
            "--env",
            "cloud-test",
        ]
    )
    wan22_v2_args = build_parser().parse_args(
        [
            "runpod",
            "workers",
            "render-scale",
            "--profile",
            "wan22_video_v2",
            "--desired",
            "1",
            "--env",
            "cloud-test",
        ]
    )
    i2i_pro_args = build_parser().parse_args(
        [
            "runpod",
            "workers",
            "render-scale",
            "--profile",
            "i2i_pro",
            "--desired",
            "1",
            "--env",
            "cloud-test",
        ]
    )

    assert image_to_video_args.runpod_command == "workers"
    assert image_to_video_args.workers_command == "render-scale"
    assert image_to_video_args.profile == "image_to_video"
    assert image_to_video_args.desired == 1
    assert wan22_v2_args.profile == "wan22_video_v2"
    assert i2i_pro_args.profile == "i2i_pro"


def test_cli_parses_split_video_manifests_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "split-video-manifests",
            "--env-file",
            ".env.cloud.test",
            "--bucket",
            "allbot-model-cache",
            "--execute",
        ]
    )

    assert args.runpod_command == "split-video-manifests"
    assert args.env_file == Path(".env.cloud.test")
    assert args.bucket == "allbot-model-cache"
    assert args.execute is True
