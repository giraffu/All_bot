import pytest

from src.core import media_paths


@pytest.mark.parametrize(
    ("output_file", "expected"),
    [
        ("bot-data/user/output.png", ("bot-data-test", "user/output.png")),
        ("comfyui-temp/result.mp4", ("comfyui-temp-test", "result.mp4")),
        ("bot-data-test/user/output.png", ("bot-data-test", "user/output.png")),
        ("comfyui-temp-test/result.mp4", ("comfyui-temp-test", "result.mp4")),
        ("44/output_images/task.mp4", ("bot-data-test", "44/output_images/task.mp4")),
        ("just-a-result-file.mp4", ("comfyui-temp-test", "just-a-result-file.mp4")),
    ],
)
def test_resolve_storage_object_preserves_legacy_and_current_bucket_compatibility(
    monkeypatch,
    output_file,
    expected,
):
    monkeypatch.setattr(media_paths, "MINIO_BUCKET", "bot-data-test")
    monkeypatch.setattr(media_paths, "MINIO_RESULT_BUCKET", "comfyui-temp-test")

    assert media_paths.resolve_storage_object(output_file) == expected


def test_resolve_storage_object_keeps_directory_history_paths_on_primary_bucket(
    monkeypatch,
):
    monkeypatch.setattr(media_paths, "MINIO_BUCKET", "bot-data")
    monkeypatch.setattr(media_paths, "MINIO_RESULT_BUCKET", "comfyui-temp")

    assert media_paths.resolve_storage_object("123/output_images/task.mp4") == (
        "bot-data",
        "123/output_images/task.mp4",
    )


@pytest.mark.parametrize(
    ("history_type", "expected"),
    [
        ("custom_video", "video"),
        ("doggy_style", "video"),
        ("txt2img", "image"),
        (None, "image"),
    ],
)
def test_get_media_type_from_history_supports_legacy_video_task_types(
    history_type,
    expected,
):
    assert media_paths.get_media_type_from_history(history_type) == expected
