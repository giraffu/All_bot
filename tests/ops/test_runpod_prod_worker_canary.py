from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ops.gpu_pool_controller.runpod_prod_worker_canary import (
    RunPodProdWorkerCanaryAssets,
    RunPodProdWorkerCanaryCaseBuilder,
    RunPodProdWorkerCanaryConfig,
    RunPodProdWorkerCanaryError,
    RunPodProdWorkerCanaryExecutor,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"png"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


def _config(
    tmp_path: Path,
    *,
    profile: str = "img2img",
    task_type: str = "img2img",
    input_object_key: str = "",
    scail2_reference_object_key: str = "",
    scail2_motion_video_object_key: str = "",
) -> RunPodProdWorkerCanaryConfig:
    return RunPodProdWorkerCanaryConfig(
        profile=profile,
        task_type=task_type,
        agent_id=f"runpod_prod_{profile}_manual_01",
        web_api_url="https://web.example",
        central_url="https://central.example",
        input_object_key=input_object_key,
        scail2_reference_object_key=scail2_reference_object_key,
        scail2_motion_video_object_key=scail2_motion_video_object_key,
        output_dir=tmp_path / "out",
        download_results_dir=tmp_path / "downloads",
        task_timeout_seconds=1.0,
        task_poll_interval_seconds=0.0,
        prompt="prod prompt",
        negative_prompt="prod negative",
    )


def test_case_builder_preserves_profile_payloads(tmp_path):
    builder = RunPodProdWorkerCanaryCaseBuilder(_config(tmp_path))

    assert builder.dry_run_steps() == [
        "verify runpod_prod_img2img_manual_01 heartbeat in prod Central",
        "temporarily set runpod_prod_img2img_manual_01 control to enabled",
        "upload or reuse one non-sensitive PNG in user-data-prod",
        "submit one prod Web img2img task as internal user_id=3",
        "download the result to runpod_canary_results/prod/<date>/",
        "restore runpod_prod_img2img_manual_01 control to disabled",
    ]
    assert builder.img2img_task_case("ref.png")["payload"]["inputs"] == {
        "images": ["ref.png"],
        "image": "ref.png",
        "num_inference_steps": 6,
        "guidance_scale": 1.0,
        "seed": 20260612,
    }
    assert (
        builder.image_to_video_task_case("ref.png")["payload"]["inputs"][
            "wan22_model_profile"
        ]
        == "legacy_image_to_video"
    )
    assert (
        builder.wan22_video_v2_task_case("ref.png")["payload"]["inputs"][
            "wan22_model_profile"
        ]
        == "wan22_video_v2"
    )
    ltx_case = builder.ltx_video_task_case("ref.png")
    assert ltx_case["expected_central_task_type"] == "ltx_video"
    assert ltx_case["result_kind"] == "video_last_frame"
    assert ltx_case["payload"]["inputs"] == {
        "images": ["ref.png"],
        "image": "ref.png",
        "resolution": "1280x704",
        "duration": 5,
        "duration_seconds": 5,
        "extract_last_frame": True,
        "ltx_mode": "i2v",
        "seed": 20260622,
    }

    i2i_cases = builder.i2i_pro_task_cases("ref.png")
    assert [case["payload"]["task_type"] for case in i2i_cases] == [
        "i2i_pro",
        "txt2img",
        "face_swap",
    ]
    scail2_cases = builder.scail2_task_cases(
        {"reference_image_key": "reference.jpg", "motion_video_key": "motion.mp4"}
    )
    assert [case["expected_central_task_type"] for case in scail2_cases] == [
        "scail2_action_transfer",
        "scail2_video_replacement",
    ]
    assert scail2_cases[0]["payload"]["inputs"]["images"] == [
        "reference.jpg",
        "motion.mp4",
    ]

    pornmaster_cases = RunPodProdWorkerCanaryCaseBuilder(
        _config(
            tmp_path,
            profile="pornmaster_flux2_edit",
            task_type="pornmaster_flux2_edit",
        )
    ).pornmaster_flux2_edit_task_cases("ref.png")
    assert [case["payload"]["task_type"] for case in pornmaster_cases] == [
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    ]
    assert [case["expected_central_task_type"] for case in pornmaster_cases] == [
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    ]
    assert pornmaster_cases[0]["payload"]["inputs"]["images"] == ["ref.png"]
    assert pornmaster_cases[1]["payload"]["inputs"]["images"] == [
        "ref.png",
        "ref.png",
    ]
    assert pornmaster_cases[1]["payload"]["inputs"]["image2"] == "ref.png"


def test_assets_upload_bytes_uses_presigned_put(tmp_path):
    calls: list[tuple[str, str, dict[str, object]]] = []

    def http_json(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {
            "object_key": "user-data-prod/web_uploads/3/canary.png",
            "upload_url": "https://upload.example/presigned?token=secret",
        }

    def http_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"status": 204, "text": "", "raw": b""}

    assets = RunPodProdWorkerCanaryAssets(
        _config(tmp_path),
        http_json_func=http_json,
        http_request_func=http_request,
        web_auth_headers_func=lambda: {"Authorization": "Bearer web"},
        phase_func=lambda *args: None,
    )

    object_key = assets.upload_bytes_to_user_data(
        filename="canary.png",
        content_type="image/png",
        body=PNG_BYTES,
    )

    assert object_key == "user-data-prod/web_uploads/3/canary.png"
    assert calls[0] == (
        "GET",
        "https://web.example/storage/presigned-url",
        {
            "params": {"filename": "canary.png", "content_type": "image/png"},
            "headers": {"Authorization": "Bearer web"},
        },
    )
    assert calls[1] == (
        "PUT",
        "https://upload.example/presigned?token=secret",
        {
            "body": PNG_BYTES,
            "headers": {"Content-Type": "image/png"},
            "expected_statuses": (200, 201, 204),
        },
    )


def test_executor_success_downloads_image_and_pop_evidence(tmp_path):
    config = _config(tmp_path)
    phases: list[tuple[str, str | None]] = []

    def http_json(method, url, **kwargs):
        if url == "https://web.example/tasks/generate":
            assert kwargs["json_body"]["task_type"] == "img2img"
            assert kwargs["headers"] == {"Authorization": "Bearer web"}
            return {"task_id": "task-1"}
        if url == "https://central.example/status/task-1":
            return {"status": "done", "task_type": "img2img"}
        if url == "https://web.example/tasks/task-1/result":
            return {
                "status": "success",
                "result_url": "https://cdn.example/results/task-1.png?token=secret",
            }
        raise AssertionError(f"unexpected request: {method} {url}")

    def http_request(method, url, **kwargs):
        assert method == "GET"
        assert kwargs["expected_statuses"] == (200,)
        return {"status": 200, "text": "", "raw": b"image-bytes"}

    executor = RunPodProdWorkerCanaryExecutor(
        config,
        http_json_func=http_json,
        http_request_func=http_request,
        web_auth_headers_func=lambda: {"Authorization": "Bearer web"},
        fetch_workers_func=lambda: [
            {
                "agent_id": config.agent_id,
                "current_task_id": "task-1",
                "current_task_type": "img2img",
                "status": "running",
            }
        ],
        sleep_func=lambda seconds: None,
        phase_func=lambda summary, name, status, details: phases.append(
            (name, status)
        ),
    )

    result = executor.run_task_case(
        RunPodProdWorkerCanaryCaseBuilder(config).img2img_task_case("ref.png"),
        {},
    )

    assert result["registry_task_id"] == "task-1"
    assert result["pop_evidence"]["agent_id"] == config.agent_id
    assert result["download_method"] == "public_url"
    assert Path(result["downloaded_file"]).read_bytes() == b"image-bytes"
    assert phases == [
        ("task_prod_img2img_canary", "running"),
        ("task_prod_img2img_canary", "ok"),
    ]


def test_executor_rejects_central_task_type_mismatch(tmp_path):
    config = _config(tmp_path, profile="image_to_video", task_type="image_to_video")

    def http_json(method, url, **kwargs):
        if url == "https://web.example/tasks/generate":
            return {"task_id": "task-1"}
        if url == "https://central.example/status/task-1":
            return {"status": "done", "task_type": "img2img"}
        raise AssertionError(f"unexpected request: {method} {url}")

    executor = RunPodProdWorkerCanaryExecutor(
        config,
        http_json_func=http_json,
        http_request_func=lambda *args, **kwargs: {"status": 200, "raw": b""},
        web_auth_headers_func=lambda: {"Authorization": "Bearer web"},
        fetch_workers_func=lambda: [],
        sleep_func=lambda seconds: None,
        phase_func=lambda *args: None,
    )

    with pytest.raises(
        RunPodProdWorkerCanaryError,
        match="expected image_to_video",
    ):
        executor.run_task_case(
            RunPodProdWorkerCanaryCaseBuilder(config).image_to_video_task_case(
                "ref.png"
            ),
            {},
        )


def test_executor_downloads_video_and_last_frame(tmp_path):
    config = _config(tmp_path, profile="wan22_video_v2", task_type="wan22_video_v2")

    def http_json(method, url, **kwargs):
        if url == "https://web.example/tasks/generate":
            return {"task_id": "task-video"}
        if url == "https://central.example/status/task-video":
            return {"status": "done", "task_type": "wan22_video_v2"}
        if url == "https://web.example/tasks/task-video/result":
            return {
                "status": "success",
                "result_url": "https://cdn.example/results/task-video.mp4",
                "extra_outputs": {
                    "last_frame": {
                        "url": "https://cdn.example/results/task-video-last.png"
                    }
                },
            }
        raise AssertionError(f"unexpected request: {method} {url}")

    def http_request(method, url, **kwargs):
        if url.endswith(".mp4"):
            return {"status": 200, "text": "", "raw": MP4_BYTES}
        if url.endswith(".png"):
            return {"status": 200, "text": "", "raw": PNG_BYTES}
        raise AssertionError(f"unexpected download: {url}")

    executor = RunPodProdWorkerCanaryExecutor(
        config,
        http_json_func=http_json,
        http_request_func=http_request,
        web_auth_headers_func=lambda: {"Authorization": "Bearer web"},
        fetch_workers_func=lambda: [],
        sleep_func=lambda seconds: None,
        phase_func=lambda *args: None,
    )

    result = executor.run_task_case(
        RunPodProdWorkerCanaryCaseBuilder(config).wan22_video_v2_task_case("ref.png"),
        {},
    )

    assert Path(result["downloaded_file"]).read_bytes() == MP4_BYTES
    assert Path(result["last_frame_downloaded_file"]).read_bytes() == PNG_BYTES
    assert result["last_frame_path"] == "/results/task-video-last.png"


def test_executor_falls_back_to_r2_s3_when_public_download_fails(
    tmp_path,
    monkeypatch,
):
    captured: dict[str, object] = {}

    class FakeBody:
        def read(self) -> bytes:
            return b"r2-bytes"

    class FakeS3Client:
        def get_object(self, *, Bucket, Key):
            captured["bucket"] = Bucket
            captured["key"] = Key
            return {"Body": FakeBody()}

    class FakeBoto3:
        def client(self, service, **kwargs):
            captured["service"] = service
            captured["client_kwargs"] = kwargs
            return FakeS3Client()

    monkeypatch.setenv("MINIO_ENDPOINT", "r2.example")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    monkeypatch.setenv("MINIO_RESULT_BUCKET", "user-data-prod")
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())

    executor = RunPodProdWorkerCanaryExecutor(
        _config(tmp_path),
        http_json_func=lambda *args, **kwargs: {},
        http_request_func=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("public URL failed")
        ),
        web_auth_headers_func=lambda: {},
        fetch_workers_func=lambda: [],
        sleep_func=lambda seconds: None,
        phase_func=lambda *args: None,
    )

    raw, method = executor.fetch_result_bytes(
        "https://cdn.example/results/task.png?token=secret"
    )

    assert raw == b"r2-bytes"
    assert method == "r2_s3"
    assert captured["bucket"] == "user-data-prod"
    assert captured["key"] == "results/task.png"
    assert captured["client_kwargs"]["endpoint_url"] == "https://r2.example"
