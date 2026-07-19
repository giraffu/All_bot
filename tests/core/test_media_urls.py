from src.core.media_urls import (
    build_r2_media_key_candidates,
    build_r2_thumbnail_info,
    build_storage_presigned_url,
)
from src.core.media_paths import MINIO_BUCKET


def test_build_r2_media_key_candidates_include_mirrored_full_object_path():
    candidates = build_r2_media_key_candidates(
        output_file="123/output_images/task-1.mp4",
        task_id="task-1",
    )

    assert candidates == [
        "history/task-1/original.mp4",
        "123/output_images/task-1.mp4",
        "task-1.mp4",
    ]


def test_build_r2_media_key_candidates_include_raw_bucket_prefixed_path():
    candidates = build_r2_media_key_candidates(
        output_file="bot-data/history/task-1/output.mp4",
        task_id="task-1",
    )

    assert candidates == [
        "history/task-1/original.mp4",
        "history/task-1/output.mp4",
        "bot-data/history/task-1/output.mp4",
        "output.mp4",
    ]


def test_build_r2_thumbnail_info_includes_mirrored_full_thumbnail_path():
    thumb_file, candidates = build_r2_thumbnail_info(
        output_file="123/output_images/task-1.mp4",
        media_type="video",
        task_id="task-1",
    )

    assert thumb_file == "123/output_images/task-1_thumb.jpg"
    assert candidates == [
        "history/task-1/thumb.jpg",
        "123/output_images/task-1_thumb.jpg",
        "task-1_thumb.jpg",
    ]


def test_build_r2_thumbnail_info_includes_raw_bucket_prefixed_path():
    thumb_file, candidates = build_r2_thumbnail_info(
        output_file="bot-data/history/task-1/output.mp4",
        media_type="video",
        task_id="task-1",
    )

    assert thumb_file == "bot-data/history/task-1/output_thumb.jpg"
    assert candidates == [
        "history/task-1/thumb.jpg",
        "history/task-1/output_thumb.jpg",
        "bot-data/history/task-1/output_thumb.jpg",
        "output_thumb.jpg",
    ]


def test_build_storage_presigned_url_uses_resolved_bucket_and_object(monkeypatch):
    captured = {}

    def fake_builder(object_name: str, bucket_name: str) -> str:
        captured["object_name"] = object_name
        captured["bucket_name"] = bucket_name
        return f"https://cdn.example/{bucket_name}/{object_name}"

    url = build_storage_presigned_url("bot-data/history/task-1/input.png", fake_builder)

    assert url == f"https://cdn.example/{MINIO_BUCKET}/history/task-1/input.png"
    assert captured == {
        "object_name": "history/task-1/input.png",
        "bucket_name": MINIO_BUCKET,
    }


def test_build_storage_presigned_url_returns_none_for_empty_path():
    assert build_storage_presigned_url(None, lambda *_args: "unused") is None
