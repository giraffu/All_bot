from __future__ import annotations

from pathlib import Path

import pytest

from ops.gpu_pool_controller.cli import build_parser
from ops.gpu_pool_controller.providers.runpod import RunPodProvider, RunPodSettings
from ops.gpu_pool_controller.runpod_canary import RunPodCanaryOptions
from ops.gpu_pool_controller.runpod_split_video_canary import (
    DEFAULT_SPLIT_VIDEO_PROMPT,
    RunPodSplitVideoCanaryRunner,
    write_video_canary_png,
)


WAN22_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
    "20260613-wan22aio-yanwkclean-108c7ea"
)


class FakeSplitRunPodProvider:
    def __init__(self) -> None:
        self.settings = RunPodSettings(
            worker_central_url_cloud_test="https://worker-central-test.aivison.it.com",
            use_template_image_to_video=True,
            use_template_wan22_video_v2=True,
            template_id_image_to_video="77gi0wqo8x",
            template_id_wan22_video_v2="77gi0wqo8x",
            image_name_image_to_video=WAN22_IMAGE,
            image_name_wan22_video_v2=WAN22_IMAGE,
            model_sync_enabled=True,
            model_bucket="allbot-model-cache",
            comfy_custom_nodes_enabled=False,
            comfy_kjnodes_enabled=False,
        )
        self.create_calls = 0
        self.delete_calls = 0

    def validate_key(self):
        return {"ok": True}

    def list_pods(self, *, managed_only=True, desired_status=None):
        return {"ok": True, "count": 0, "pods": []}

    def reconcile_managed_pods(self, pods=None):
        return {"ok": True, "managed_count": 0, "orphans": []}

    def render_create_pod_request(self, *, task_type, environment, redact=True):
        return RunPodProvider(self.settings).render_create_pod_request(
            task_type=task_type,
            environment=environment,
            redact=redact,
        )

    def create_pod(self, *, task_type, environment, execute):
        self.create_calls += 1
        return {"ok": True, "pod": {"id": f"pod-{task_type}"}}

    def delete_pod(self, *, pod_id, task_type, execute):
        self.delete_calls += 1
        return {"ok": True}

    def pod_readiness(self, *, pod_id):
        return {"ok": True, "readiness": {"infrastructure_ready": False}}


class FailingSecondCreateProvider(FakeSplitRunPodProvider):
    def create_pod(self, *, task_type, environment, execute):
        self.create_calls += 1
        if self.create_calls == 2:
            return {"ok": False, "error": "runpod_http_500: resources unavailable"}
        return {"ok": True, "pod": {"id": f"pod-{task_type}"}}


def test_split_video_canary_dry_run_renders_both_profiles_without_mutation():
    provider = FakeSplitRunPodProvider()
    options = RunPodCanaryOptions(execute=False, quiet=True)

    payload = RunPodSplitVideoCanaryRunner(
        provider,
        options,
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is True
    assert payload["render"]["image_to_video"]["templateId"] == "77gi0wqo8x"
    assert payload["render"]["wan22_video_v2"]["templateId"] == "77gi0wqo8x"
    assert (
        payload["render"]["image_to_video"]["supported_task_types"] == "image_to_video"
    )
    assert (
        payload["render"]["wan22_video_v2"]["supported_task_types"] == "wan22_video_v2"
    )
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_split_video_canary_dry_run_can_target_wan22_video_v2_only():
    provider = FakeSplitRunPodProvider()
    options = RunPodCanaryOptions(execute=False, quiet=True)

    payload = RunPodSplitVideoCanaryRunner(
        provider,
        options,
        profiles=("wan22_video_v2",),
        sleep_func=lambda _seconds: None,
    ).run()

    assert payload["ok"] is True
    assert payload["profiles"] == ["wan22_video_v2"]
    assert list(payload["render"]) == ["wan22_video_v2"]
    assert "image_to_video" not in payload["render"]
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_split_video_canary_cleans_partial_pod_when_second_create_fails():
    provider = FailingSecondCreateProvider()
    runner = RunPodSplitVideoCanaryRunner(
        provider,
        RunPodCanaryOptions(execute=True, cleanup=True, disable_workers=False),
        sleep_func=lambda _seconds: None,
    )
    summary: dict[str, object] = {
        "render": {
            "image_to_video": {"imageName": WAN22_IMAGE},
            "wan22_video_v2": {"imageName": WAN22_IMAGE},
        },
        "cleanup": {"pod_delete": []},
    }

    with pytest.raises(ValueError, match="runpod create-pod failed"):
        runner._create_pods(summary)

    assert provider.create_calls == 2
    assert provider.delete_calls == 1
    pod_delete = summary["cleanup"]["pod_delete"]  # type: ignore[index]
    assert pod_delete[0]["profile"] == "image_to_video"
    assert pod_delete[0]["pod_id"] == "pod-image_to_video"
    assert pod_delete[0]["partial_create_cleanup"] is True


def test_split_video_canary_task_cases_match_web_generate_plan():
    runner = RunPodSplitVideoCanaryRunner(
        FakeSplitRunPodProvider(),
        RunPodCanaryOptions(prompt=DEFAULT_SPLIT_VIDEO_PROMPT, quiet=True),
    )

    cases = runner._task_cases("user-data-test/web_uploads/3/example.png")

    assert [case["label"] for case in cases] == [
        "image_to_video_no_lora",
        "image_to_video_insertion_lora",
        "wan22_video_v2",
    ]
    assert [case["worker_profile"] for case in cases] == [
        "image_to_video",
        "image_to_video",
        "wan22_video_v2",
    ]
    assert cases[0]["payload"]["task_type"] == "image_to_video"
    assert cases[1]["payload"]["inputs"]["lora_name"] == "Insertion"
    assert cases[1]["payload"]["inputs"]["lora_strength"] == 1.0
    assert cases[2]["payload"]["task_type"] == "wan22_video_v2"
    for case in cases:
        assert case["payload"]["prompt"] == DEFAULT_SPLIT_VIDEO_PROMPT
        inputs = case["payload"]["inputs"]
        assert inputs["image"] == "user-data-test/web_uploads/3/example.png"
        assert inputs["resolution_preset"] == "preview"
        assert inputs["duration_seconds"] == 5
        assert inputs["extract_last_frame"] is True


def test_split_video_canary_task_cases_can_target_wan22_video_v2_only():
    runner = RunPodSplitVideoCanaryRunner(
        FakeSplitRunPodProvider(),
        RunPodCanaryOptions(prompt=DEFAULT_SPLIT_VIDEO_PROMPT, quiet=True),
        profiles=("wan22_video_v2",),
    )

    cases = runner._task_cases("user-data-test/web_uploads/3/example.png")

    assert [case["label"] for case in cases] == ["wan22_video_v2"]
    assert cases[0]["worker_profile"] == "wan22_video_v2"
    assert cases[0]["payload"]["task_type"] == "wan22_video_v2"


def test_split_video_canary_downloads_fixed_result_names(tmp_path: Path):
    runner = RunPodSplitVideoCanaryRunner(
        FakeSplitRunPodProvider(),
        RunPodCanaryOptions(download_results_dir=tmp_path, quiet=True),
    )
    png = b"\x89PNG\r\n\x1a\npng"
    mp4 = b"\x00\x00\x00\x18ftypmp42video"

    runner._fetch_result_bytes = (  # type: ignore[method-assign]
        lambda url: (png, "public_url") if "frame" in url else (mp4, "public_url")
    )

    video = runner._download_named_result(
        label="image_to_video_no_lora",
        result_url="https://cdn.example/result.mp4",
    )
    last_frame = runner._download_last_frame(
        label="image_to_video_no_lora",
        result_payload={
            "extra_outputs": {"last_frame": {"url": "https://cdn.example/frame.png"}}
        },
    )

    assert Path(video["downloaded_file"]).name == "image_to_video_no_lora.mp4"
    assert Path(last_frame["last_frame_downloaded_file"]).name == (
        "image_to_video_no_lora_last_frame.png"
    )
    assert (tmp_path / "image_to_video_no_lora.mp4").read_bytes() == mp4
    assert (tmp_path / "image_to_video_no_lora_last_frame.png").read_bytes() == png


def test_split_video_canary_png_helper_writes_png(tmp_path: Path):
    path = tmp_path / "person.png"

    write_video_canary_png(path)

    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_cli_parses_split_video_canary_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "split-video-canary",
            "--env-file",
            ".env.cloud.test",
            "--execute",
            "--profile",
            "wan22_video_v2",
            "--quiet",
        ]
    )

    assert args.runpod_command == "split-video-canary"
    assert args.env_file == Path(".env.cloud.test")
    assert args.execute is True
    assert args.profile == ["wan22_video_v2"]
    assert args.prompt == DEFAULT_SPLIT_VIDEO_PROMPT
    assert args.download_results_dir == Path("runpod_video_test_results")
