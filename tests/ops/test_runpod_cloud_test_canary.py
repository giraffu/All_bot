from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ops.gpu_pool_controller.runpod_cloud_test_canary import (
    RunPodCloudTestCanaryCaseBuilder,
    RunPodCloudTestCanaryConfig,
    RunPodCloudTestCanaryError,
    RunPodCloudTestCanaryExecutor,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"png"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


def _config(
    tmp_path: Path,
    *,
    task_type: str = "img2img_lora",
    download_results: bool = True,
    timeout: float = 1.0,
) -> RunPodCloudTestCanaryConfig:
    return RunPodCloudTestCanaryConfig(
        task_type=task_type,
        web_api_url="https://web.example",
        central_url="https://central.example",
        input_object_key="",
        scail2_reference_object_key="",
        scail2_motion_video_object_key="",
        output_dir=tmp_path / "out",
        download_results_dir=(tmp_path / "downloads") if download_results else None,
        task_timeout_seconds=timeout,
        task_poll_interval_seconds=0.0,
        prompt="cloud prompt",
        negative_prompt="cloud negative",
    )


def test_case_builder_preserves_cloud_test_payloads(tmp_path):
    image_key = "user-data-test/web_uploads/3/canary.png"

    img_cases = RunPodCloudTestCanaryCaseBuilder(
        _config(tmp_path, task_type="img2img_lora")
    ).task_cases(image_key)
    assert [case["label"] for case in img_cases] == [
        "img2img_plain",
        "img2img_lora_yarn",
        "img2img_lora_realistic_texture",
    ]
    assert img_cases[1]["payload"]["inputs"]["lora_strength"] == 0.65

    wan_cases = RunPodCloudTestCanaryCaseBuilder(
        _config(tmp_path, task_type="wan22_aio_video")
    ).task_cases(image_key)
    assert [case["payload"]["task_type"] for case in wan_cases] == [
        "image_to_video",
        "wan22_video_v2",
    ]
    assert wan_cases[1]["payload"]["inputs"]["wan22_model_profile"] == (
        "wan22_video_v2"
    )

    i2i_cases = RunPodCloudTestCanaryCaseBuilder(
        _config(tmp_path, task_type="i2i_pro")
    ).task_cases(image_key)
    assert [case["expected_central_task_type"] for case in i2i_cases] == [
        "i2i_pro",
        "t2i-pornmaster-turbo",
        "face_swap_v2",
        "face_swap",
    ]

    scail2_cases = RunPodCloudTestCanaryCaseBuilder(
        _config(tmp_path, task_type="scail2")
    ).task_cases(
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


def test_split_video_case_builder_preserves_fixed_order(tmp_path):
    cases = RunPodCloudTestCanaryCaseBuilder(_config(tmp_path)).split_video_task_cases(
        "user-data-test/web_uploads/3/canary.png",
        active_profiles=("image_to_video", "wan22_video_v2"),
    )

    assert [case["label"] for case in cases] == [
        "image_to_video_no_lora",
        "image_to_video_insertion_lora",
        "wan22_video_v2",
    ]
    assert cases[1]["payload"]["inputs"]["lora_name"] == "Insertion"
    assert cases[2]["payload"]["inputs"]["wan22_model_profile"] == "wan22_video_v2"


def test_executor_success_downloads_result_and_pop_evidence(tmp_path):
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

    executor = RunPodCloudTestCanaryExecutor(
        config,
        http_json_func=http_json,
        http_request_func=lambda *args, **kwargs: {
            "status": 200,
            "text": "",
            "raw": b"image-bytes",
        },
        web_auth_headers_func=lambda: {"Authorization": "Bearer web"},
        fetch_workers_func=lambda: [
            {
                "agent_id": "runpod-cloud-test",
                "current_task_id": "task-1",
                "current_task_type": "img2img",
                "status": "running",
            }
        ],
        sleep_func=lambda seconds: None,
        phase_func=lambda summary, name, status, details: phases.append((name, status)),
    )

    result = executor.run_task_case(
        RunPodCloudTestCanaryCaseBuilder(config).img2img_task_cases("ref.png")[0],
        {"agent_id": "runpod-cloud-test"},
        {},
    )

    assert result["registry_task_id"] == "task-1"
    assert result["pop_evidence"]["agent_id"] == "runpod-cloud-test"
    assert result["download_method"] == "public_url"
    assert Path(result["downloaded_file"]).read_bytes() == b"image-bytes"
    assert phases == [
        ("task_img2img_plain", "running"),
        ("task_img2img_plain", "ok"),
    ]


def test_executor_rejects_central_task_type_mismatch(tmp_path):
    config = _config(tmp_path, task_type="wan22_aio_video")

    def http_json(method, url, **kwargs):
        if url == "https://web.example/tasks/generate":
            return {"task_id": "task-1"}
        if url == "https://central.example/status/task-1":
            return {"status": "done", "task_type": "img2img"}
        raise AssertionError(f"unexpected request: {method} {url}")

    executor = RunPodCloudTestCanaryExecutor(
        config,
        http_json_func=http_json,
        http_request_func=lambda *args, **kwargs: {"status": 200, "raw": b""},
        web_auth_headers_func=lambda: {},
        fetch_workers_func=lambda: [],
        sleep_func=lambda seconds: None,
        phase_func=lambda *args: None,
    )

    with pytest.raises(RunPodCloudTestCanaryError, match="expected wan22_video_v2"):
        executor.run_task_case(
            RunPodCloudTestCanaryCaseBuilder(config).wan22_aio_video_task_cases(
                "ref.png"
            )[1],
            {"agent_id": "runpod-cloud-test"},
            {},
        )


def test_executor_times_out_waiting_for_web_result(tmp_path):
    config = _config(tmp_path, timeout=0.001)

    executor = RunPodCloudTestCanaryExecutor(
        config,
        http_json_func=lambda *args, **kwargs: {"status": "pending"},
        http_request_func=lambda *args, **kwargs: {"status": 200, "raw": b""},
        web_auth_headers_func=lambda: {},
        fetch_workers_func=lambda: [],
        sleep_func=lambda seconds: None,
        phase_func=lambda *args: None,
    )

    with pytest.raises(RunPodCloudTestCanaryError, match="web result timeout"):
        executor.wait_web_result("task-1")


def test_executor_skips_optional_download_when_disabled(tmp_path):
    executor = RunPodCloudTestCanaryExecutor(
        _config(tmp_path, download_results=False),
        http_json_func=lambda *args, **kwargs: {},
        http_request_func=lambda *args, **kwargs: {"status": 200, "raw": b""},
        web_auth_headers_func=lambda: {},
        fetch_workers_func=lambda: [],
        sleep_func=lambda seconds: None,
        phase_func=lambda *args: None,
    )

    assert (
        executor.download_result_if_requested(
            label="img",
            task_id="task-1",
            result_url="https://cdn.example/result.png",
        )
        == {}
    )


def test_split_download_validates_mp4_and_last_frame_png(tmp_path):
    executor = RunPodCloudTestCanaryExecutor(
        _config(tmp_path),
        http_json_func=lambda *args, **kwargs: {},
        http_request_func=lambda *args, **kwargs: {"status": 200, "raw": b""},
        web_auth_headers_func=lambda: {},
        fetch_workers_func=lambda: [],
        fetch_result_bytes_func=lambda url: (
            (PNG_BYTES, "public_url")
            if url.endswith(".png")
            else (MP4_BYTES, "public_url")
        ),
        sleep_func=lambda seconds: None,
        phase_func=lambda *args: None,
    )

    video = executor.download_named_result(
        label="image_to_video_no_lora",
        result_url="https://cdn.example/result.mp4",
        default_download_dir=Path("runpod_video_test_results"),
    )
    frame = executor.download_last_frame(
        label="image_to_video_no_lora",
        result_payload={
            "extra_outputs": {"last_frame": {"url": "https://cdn.example/frame.png"}}
        },
        default_download_dir=Path("runpod_video_test_results"),
    )

    assert Path(video["downloaded_file"]).read_bytes() == MP4_BYTES
    assert Path(frame["last_frame_downloaded_file"]).read_bytes() == PNG_BYTES


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
    monkeypatch.setenv("MINIO_RESULT_BUCKET", "user-data-test")
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())

    executor = RunPodCloudTestCanaryExecutor(
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
    assert captured["bucket"] == "user-data-test"
    assert captured["key"] == "results/task.png"
    assert captured["client_kwargs"]["endpoint_url"] == "https://r2.example"
