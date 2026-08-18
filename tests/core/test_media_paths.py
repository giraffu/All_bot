import pytest

from src import media_paths


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
    ("reference", "expected"),
    [
        ("task-results/backend-1/primary.png", "task-results/backend-1/primary.png"),
        ("user-data-prod/task-results/backend-1/primary.png", "task-results/backend-1/primary.png"),
        ("/user-data-prod/task-results/backend-1/primary.png", "task-results/backend-1/primary.png"),
        (
            "https://objects.example/user-data-prod/task-results/backend-1/primary.png?signature=redacted",
            "task-results/backend-1/primary.png",
        ),
        (
            "https://user-data-prod.objects.example/task-results/backend-1/primary.png",
            "task-results/backend-1/primary.png",
        ),
    ],
)
def test_normalize_storage_object_key_accepts_plain_bucket_prefixed_and_url_references(
    monkeypatch, reference, expected
):
    monkeypatch.setattr(media_paths, "MINIO_BUCKET", "user-data-prod")
    monkeypatch.setattr(media_paths, "MINIO_RESULT_BUCKET", "worker-results-prod")

    assert media_paths.normalize_storage_object_key(reference) == expected


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("staging/user-uploads/7/start.png", "staging/user-uploads/7/start.png"),
        ("user-data-prod/staging/user-uploads/7/start.png", "staging/user-uploads/7/start.png"),
        ("web_uploads/7/start.png", "web_uploads/7/start.png"),
    ],
)
def test_normalize_owned_user_upload_key_accepts_staged_and_legacy_owned_uploads(
    monkeypatch, reference, expected
):
    monkeypatch.setattr(media_paths, "MINIO_BUCKET", "user-data-prod")
    monkeypatch.setattr(media_paths, "MINIO_RESULT_BUCKET", "worker-results-prod")

    assert (
        media_paths.normalize_owned_user_upload_key(
            reference,
            user_id=7,
            allowed_extensions={"png"},
        )
        == expected
    )


def test_normalize_owned_user_upload_key_rejects_foreign_or_bad_suffix_uploads(
    monkeypatch,
):
    monkeypatch.setattr(media_paths, "MINIO_BUCKET", "user-data-prod")
    monkeypatch.setattr(media_paths, "MINIO_RESULT_BUCKET", "worker-results-prod")

    with pytest.raises(ValueError, match="current user"):
        media_paths.normalize_owned_user_upload_key(
            "staging/user-uploads/8/start.png",
            user_id=7,
            allowed_extensions={"png"},
        )
    with pytest.raises(ValueError, match="allowed"):
        media_paths.normalize_owned_user_upload_key(
            "staging/user-uploads/7/start.mp4",
            user_id=7,
            allowed_extensions={"png"},
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
