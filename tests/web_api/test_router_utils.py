import pytest

from src.web_api.common.utils import (
    build_storage_input_file_url,
    call_with_optional_db,
    probe_apply_context_media_metadata,
    resolve_apply_context_media_metadata,
    run_with_optional_db,
)


def test_resolve_apply_context_media_metadata_prefers_primary_values():
    media_type, width, height, duration = resolve_apply_context_media_metadata(
        task_type="custom_video",
        primary_media_type="video",
        primary_width=720,
        primary_height=1280,
        primary_duration=8,
        fallback_width=512,
        fallback_height=768,
        fallback_duration=5,
    )

    assert media_type == "video"
    assert width == 720
    assert height == 1280
    assert duration == 8


def test_resolve_apply_context_media_metadata_falls_back_to_history_type_and_secondary_values():
    media_type, width, height, duration = resolve_apply_context_media_metadata(
        task_type="image",
        primary_width=None,
        primary_height=None,
        primary_duration=None,
        fallback_width=1024,
        fallback_height=1024,
        fallback_duration=None,
    )

    assert media_type == "image"
    assert width == 1024
    assert height == 1024
    assert duration is None


@pytest.mark.asyncio
async def test_probe_apply_context_media_metadata_backfills_missing_values():
    async def _probe(_output_file: str, _media_type: str):
        return 1024, 1024, 8

    width, height, duration, billing_resolution = (
        await probe_apply_context_media_metadata(
            output_file="bot-data/history/task-1/output.mp4",
            media_type="video",
            width=None,
            height=None,
            duration=None,
            billing_resolution=None,
            task_type="custom_video",
            task_id="task-1",
            probe_media_metadata=_probe,
        )
    )

    assert width == 1024
    assert height == 1024
    assert duration == 8
    assert billing_resolution == "hd"


@pytest.mark.asyncio
async def test_probe_apply_context_media_metadata_keeps_existing_values_on_probe_failure():
    async def _probe(_output_file: str, _media_type: str):
        raise RuntimeError("boom")

    width, height, duration, billing_resolution = (
        await probe_apply_context_media_metadata(
            output_file="bot-data/history/task-2/output.mp4",
            media_type="video",
            width=512,
            height=768,
            duration=5,
            billing_resolution="768",
            task_type="custom_video",
            task_id="task-2",
            probe_media_metadata=_probe,
        )
    )

    assert width == 512
    assert height == 768
    assert duration == 5
    assert billing_resolution == "768"


def test_build_storage_input_file_url_uses_shared_storage_builder(monkeypatch):
    presigned_calls = []

    def fake_get_presigned_url(object_name: str, *, bucket: str):
        presigned_calls.append((object_name, bucket))
        return f"https://storage.example/{bucket}/{object_name}"

    monkeypatch.setattr(
        "src.web_api.common.utils.storage.get_presigned_url",
        fake_get_presigned_url,
    )

    url = build_storage_input_file_url("bot-data/history/task-1/input.png")

    assert url == "https://storage.example/bot-data/history/task-1/input.png"
    assert presigned_calls == [("history/task-1/input.png", "bot-data")]


@pytest.mark.asyncio
async def test_run_with_optional_db_uses_fallback_session_factory_when_db_missing():
    used_sessions = []

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _action(session):
        used_sessions.append(session)
        return "ok"

    result = await run_with_optional_db(
        db=None,
        action=_action,
        session_factory=lambda: _FakeSession(),
    )

    assert result == "ok"
    assert len(used_sessions) == 1


@pytest.mark.asyncio
async def test_call_with_optional_db_passes_fallback_session_to_service():
    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    captured = {}

    async def _service(*, db, payload):
        captured["db"] = db
        captured["payload"] = payload
        return {"status": "success"}

    result = await call_with_optional_db(
        db=None,
        service_fn=_service,
        session_factory=lambda: _FakeSession(),
        payload="value",
    )

    assert result == {"status": "success"}
    assert captured["payload"] == "value"
    assert captured["db"].__class__.__name__ == "_FakeSession"
