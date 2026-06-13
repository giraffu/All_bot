from __future__ import annotations

from ops.gpu_pool_controller.providers.runpod import RunPodProvider, RunPodSettings
from ops.gpu_pool_controller.runpod_workers import (
    RunPodWorkersScaleOptions,
    RunPodWorkersScaler,
)


class FakeRunPodApi:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, method, path, *, params=None, json_body=None, headers=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params or {},
                "json_body": json_body,
            }
        )
        return self.response


def _provider(response=None) -> RunPodProvider:
    settings = RunPodSettings(
        api_key="rp_test",
        worker_central_url_cloud_test="https://worker-central-test.aivison.it.com",
        use_template_image_to_video=True,
        use_template_wan22_video_v2=True,
        template_id_image_to_video="77gi0wqo8x",
        template_id_wan22_video_v2="77gi0wqo8x",
        image_name_image_to_video=(
            "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:test"
        ),
        image_name_wan22_video_v2=(
            "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:test"
        ),
    )
    return RunPodProvider(
        settings,
        request_func=FakeRunPodApi(response or {"pods": []}),
    )


def test_workers_render_scale_renders_target_profile_requests_without_mutation():
    scaler = RunPodWorkersScaler(
        _provider(),
        RunPodWorkersScaleOptions(profile="image_to_video", desired=1),
    )

    payload = scaler.render_scale()
    request = payload["create_requests"][0]["json"]

    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["profile"] == "image_to_video"
    assert payload["would_create_count"] == 1
    assert request["templateId"] == "77gi0wqo8x"
    assert request["env"]["RUNPOD_TASK_TYPE"] == "image_to_video"
    assert request["env"]["SUPPORTED_TASK_TYPES"] == "image_to_video"


def test_workers_scale_only_targets_requested_profile():
    pods = [
        {
            "id": "pod-image",
            "name": "allbot-runpod-test-image-to-video",
            "desiredStatus": "RUNNING",
            "env": {
                "RUNPOD_ENVIRONMENT": "cloud-test",
                "RUNPOD_TASK_TYPE": "image_to_video",
            },
        },
        {
            "id": "pod-v2",
            "name": "allbot-runpod-test-wan22-video-v2",
            "desiredStatus": "RUNNING",
            "env": {
                "RUNPOD_ENVIRONMENT": "cloud-test",
                "RUNPOD_TASK_TYPE": "wan22_video_v2",
            },
        },
    ]
    scaler = RunPodWorkersScaler(
        _provider({"pods": pods}),
        RunPodWorkersScaleOptions(profile="image_to_video", desired=0),
    )

    payload = scaler.scale()

    assert payload["ok"] is True
    assert payload["current"] == 1
    assert payload["delta"] == -1
    assert len(payload["deletes"]) == 1
    assert payload["deletes"][0]["request"]["url"].endswith("/pods/pod-image")
