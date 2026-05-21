from src.core.media_urls import build_storage_presigned_url


def test_build_storage_presigned_url_uses_resolved_bucket_and_object(monkeypatch):
    captured = {}

    def fake_builder(object_name: str, bucket_name: str) -> str:
        captured["object_name"] = object_name
        captured["bucket_name"] = bucket_name
        return f"https://cdn.example/{bucket_name}/{object_name}"

    url = build_storage_presigned_url("bot-data/history/task-1/input.png", fake_builder)

    assert url == "https://cdn.example/bot-data/history/task-1/input.png"
    assert captured == {
        "object_name": "history/task-1/input.png",
        "bucket_name": "bot-data",
    }


def test_build_storage_presigned_url_returns_none_for_empty_path():
    assert build_storage_presigned_url(None, lambda *_args: "unused") is None
