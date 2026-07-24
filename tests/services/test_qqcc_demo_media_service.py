import hashlib
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import InputMediaPhoto, InputMediaVideo

from src.services.qqcc_demo_media_service import (
    clone_qqcc_config_demo_media_for_private_bot,
    delete_qqcc_private_bot_demo_media,
    send_qqcc_scene_demo_media,
    upload_qqcc_demo_media,
)


class _Upload:
    def __init__(self, *, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self, _size: int) -> bytes:
        return self._content


@pytest.mark.asyncio
async def test_upload_demo_media_uses_deterministic_r2_key_and_expected_media_type():
    put_object = SimpleNamespace(calls=[])

    def _put_object(**kwargs):
        put_object.calls.append(kwargs)

    storage_service = SimpleNamespace(
        r2_client=SimpleNamespace(
            put_object=_put_object,
            list_objects_v2=lambda **_kwargs: {
                "Contents": [],
                "IsTruncated": False,
            },
        ),
        r2_bucket="user-data",
        mark_r2_object_exists=lambda key: None,
    )

    result = await upload_qqcc_demo_media(
        scene_kind="video",
        scene_id="kiss",
        slot="output",
        upload=_Upload(
            filename="result.mp4",
            content_type="video/mp4",
            content=b"\x00\x00\x00\x18ftypmp42demo",
        ),
        storage_service=storage_service,
    )

    assert result == {
        "object_key": "qqcc/demo/video/kiss/output",
        "media_type": "video",
        "mime_type": "video/mp4",
        "file_name": "result.mp4",
        "content_sha256": hashlib.sha256(b"\x00\x00\x00\x18ftypmp42demo").hexdigest(),
        "telegram_file_ids": {},
    }
    assert put_object.calls == [
        {
            "Bucket": "user-data",
            "Key": "qqcc/demo/video/kiss/output",
            "Body": b"\x00\x00\x00\x18ftypmp42demo",
            "ContentType": "video/mp4",
        }
    ]


@pytest.mark.asyncio
async def test_private_bot_demo_media_is_namespaced_by_tenant():
    put_object = SimpleNamespace(calls=[])

    def _put_object(**kwargs):
        put_object.calls.append(kwargs)

    storage_service = SimpleNamespace(
        r2_client=SimpleNamespace(
            put_object=_put_object,
            list_objects_v2=lambda **_kwargs: {
                "Contents": [],
                "IsTruncated": False,
            },
        ),
        r2_bucket="user-data",
        mark_r2_object_exists=lambda key: None,
    )

    result = await upload_qqcc_demo_media(
        scene_kind="draw",
        scene_id="portrait",
        slot="input",
        upload=_Upload(
            filename="input.png",
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\ndemo",
        ),
        object_prefix="qqcc/private/7/demo",
        storage_service=storage_service,
    )

    assert result["object_key"] == "qqcc/private/7/demo/draw/portrait/input"
    assert put_object.calls[0]["Key"] == result["object_key"]


@pytest.mark.asyncio
async def test_generated_demo_uses_unique_draft_key_until_config_is_saved():
    put_object = SimpleNamespace(calls=[])
    storage_service = SimpleNamespace(
        r2_client=SimpleNamespace(
            put_object=lambda **kwargs: put_object.calls.append(kwargs),
            list_objects_v2=lambda **_kwargs: {"Contents": [], "IsTruncated": False},
        ),
        r2_bucket="user-data",
        mark_r2_object_exists=lambda _key: None,
    )

    result = await upload_qqcc_demo_media(
        scene_kind="draw",
        scene_id="portrait",
        slot="output",
        generated_object_id="qqcc-demo-task-1",
        upload=_Upload(
            filename="generated.png",
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\ndemo",
        ),
        storage_service=storage_service,
    )

    assert result["object_key"] == (
        "qqcc/demo/draw/portrait/generated/qqcc-demo-task-1/output"
    )
    assert put_object.calls[0]["Key"] == result["object_key"]


@pytest.mark.asyncio
async def test_private_bot_demo_media_enforces_tenant_object_quota(monkeypatch):
    from src.services import qqcc_demo_media_service

    monkeypatch.setattr(
        qqcc_demo_media_service,
        "PRIVATE_QQCC_DEMO_MAX_OBJECTS",
        1,
    )
    storage_service = SimpleNamespace(
        r2_client=SimpleNamespace(
            list_objects_v2=lambda **_kwargs: {
                "Contents": [
                    {
                        "Key": "qqcc/private/7/demo/draw/old/input",
                        "Size": 10,
                    }
                ],
                "IsTruncated": False,
            },
            put_object=lambda **_kwargs: pytest.fail("quota must reject upload"),
        ),
        r2_bucket="user-data",
        mark_r2_object_exists=lambda _key: None,
    )

    with pytest.raises(
        qqcc_demo_media_service.QqccDemoMediaValidationError,
        match="object quota",
    ):
        await upload_qqcc_demo_media(
            scene_kind="draw",
            scene_id="new",
            slot="input",
            upload=_Upload(
                filename="input.png",
                content_type="image/png",
                content=b"\x89PNG\r\n\x1a\ndemo",
            ),
            object_prefix="qqcc/private/7/demo",
            storage_service=storage_service,
        )


@pytest.mark.asyncio
async def test_private_bot_config_clone_copies_demo_objects_and_clears_file_ids():
    copied = []
    marked = []

    def _copy_object(**kwargs):
        copied.append(kwargs)

    storage_service = SimpleNamespace(
        r2_client=SimpleNamespace(copy_object=_copy_object),
        r2_bucket="user-data",
        mark_r2_object_exists=marked.append,
    )
    source = {
        "draw_scenes": [
            {
                "id": "portrait",
                "demo_input_media": {
                    "object_key": "qqcc/demo/draw/portrait/input",
                    "media_type": "image",
                    "telegram_file_ids": {"123": "official-file-id"},
                },
            }
        ]
    }

    cloned = await clone_qqcc_config_demo_media_for_private_bot(
        source,
        private_bot_id=7,
        storage_service=storage_service,
    )

    media = cloned["draw_scenes"][0]["demo_input_media"]
    assert media["object_key"] == "qqcc/private/7/demo/draw/portrait/input"
    assert media["telegram_file_ids"] == {}
    assert copied == [
        {
            "Bucket": "user-data",
            "Key": "qqcc/private/7/demo/draw/portrait/input",
            "CopySource": {
                "Bucket": "user-data",
                "Key": "qqcc/demo/draw/portrait/input",
            },
        }
    ]
    assert marked == ["qqcc/private/7/demo/draw/portrait/input"]
    assert source["draw_scenes"][0]["demo_input_media"]["object_key"].startswith(
        "qqcc/demo/"
    )


@pytest.mark.asyncio
async def test_private_bot_demo_cleanup_is_limited_to_tenant_prefix():
    deletes = []

    def _list_objects_v2(**_kwargs):
        return {
            "Contents": [
                {"Key": "qqcc/private/7/demo/draw/a/input"},
                {"Key": "qqcc/private/8/demo/draw/b/input"},
            ],
            "IsTruncated": False,
        }

    def _delete_objects(**kwargs):
        deletes.append(kwargs)

    storage_service = SimpleNamespace(
        r2_client=SimpleNamespace(
            list_objects_v2=_list_objects_v2,
            delete_objects=_delete_objects,
        ),
        r2_bucket="user-data",
    )

    deleted = await delete_qqcc_private_bot_demo_media(
        7,
        storage_service=storage_service,
    )

    assert deleted == 1
    assert deletes[0]["Delete"]["Objects"] == [
        {"Key": "qqcc/private/7/demo/draw/a/input"}
    ]


@pytest.mark.asyncio
async def test_send_demo_media_reuses_bot_specific_telegram_file_ids():
    sent_media = []

    async def _reply_media_group(*, media):
        sent_media.extend(media)
        return []

    message = SimpleNamespace(reply_media_group=_reply_media_group)
    scene = {
        "id": "portrait",
        "demo_input_media": {
            "object_key": "qqcc/demo/draw/portrait/input",
            "media_type": "image",
            "telegram_file_ids": {"123": "cached-input-photo"},
        },
        "demo_output_media": {
            "object_key": "qqcc/demo/draw/portrait/output",
            "media_type": "image",
            "telegram_file_ids": {"123": "cached-output-photo"},
        },
    }

    sent = await send_qqcc_scene_demo_media(
        message=message,
        bot=SimpleNamespace(id=123),
        scene_kind="draw",
        scene=scene,
        preview_url_builder=lambda _media: pytest.fail("R2 should not be used"),
    )

    assert sent is True
    assert [item.media for item in sent_media] == [
        "cached-input-photo",
        "cached-output-photo",
    ]


@pytest.mark.asyncio
async def test_video_scene_demo_album_contains_one_photo_and_one_video():
    sent_media = []

    async def _reply_media_group(*, media):
        sent_media.extend(media)
        return []

    scene = {
        "id": "kiss",
        "demo_input_media": {
            "object_key": "qqcc/demo/video/kiss/input",
            "media_type": "image",
            "telegram_file_ids": {"123": "cached-photo"},
        },
        "demo_output_media": {
            "object_key": "qqcc/demo/video/kiss/output",
            "media_type": "video",
            "telegram_file_ids": {"123": "cached-video"},
        },
    }

    sent = await send_qqcc_scene_demo_media(
        message=SimpleNamespace(reply_media_group=_reply_media_group),
        bot=SimpleNamespace(id=123),
        scene_kind="video",
        scene=scene,
    )

    assert sent is True
    assert isinstance(sent_media[0], InputMediaPhoto)
    assert isinstance(sent_media[1], InputMediaVideo)


@pytest.mark.asyncio
async def test_demo_media_falls_back_to_bot_upload_when_telegram_cannot_fetch_r2_url():
    attempts = []
    cache = AsyncMock()

    async def _reply_media_group(*, media):
        attempts.append(media)
        if isinstance(media[0].media, str):
            raise RuntimeError("Telegram cannot fetch the signed URL")
        assert isinstance(media[0], InputMediaPhoto)
        assert isinstance(media[1], InputMediaVideo)
        assert not isinstance(media[0].media, str)
        assert not isinstance(media[1].media, str)
        return [
            SimpleNamespace(photo=[SimpleNamespace(file_id="uploaded-photo")]),
            SimpleNamespace(video=SimpleNamespace(file_id="uploaded-video")),
        ]

    storage_service = SimpleNamespace(
        r2_client=SimpleNamespace(
            get_object=lambda **_kwargs: {
                "Body": BytesIO(
                    b"\x00\x00\x00\x18ftypmp42demo"
                    if _kwargs["Key"].endswith("/output")
                    else b"\x89PNG\r\n\x1a\ndemo"
                )
            }
        ),
        r2_bucket="user-data",
    )
    scene = {
        "id": "kiss",
        "demo_input_media": {
            "object_key": "qqcc/demo/video/kiss/input",
            "media_type": "image",
            "mime_type": "image/png",
            "file_name": "input.png",
            "content_sha256": hashlib.sha256(b"\x89PNG\r\n\x1a\ndemo").hexdigest(),
        },
        "demo_output_media": {
            "object_key": "qqcc/demo/video/kiss/output",
            "media_type": "video",
            "mime_type": "video/mp4",
            "file_name": "output.mp4",
            "content_sha256": hashlib.sha256(b"\x00\x00\x00\x18ftypmp42demo").hexdigest(),
        },
    }

    sent = await send_qqcc_scene_demo_media(
        message=SimpleNamespace(reply_media_group=_reply_media_group),
        bot=SimpleNamespace(id=123),
        scene_kind="video",
        scene=scene,
        preview_url_builder=lambda _media: "https://r2.example/demo.png",
        cache_file_ids_func=cache,
        storage_service=storage_service,
    )

    assert sent is True
    assert [item.media for item in attempts[0]] == [
        "https://r2.example/demo.png",
        "https://r2.example/demo.png",
    ]
    cache.assert_awaited_once()
    assert cache.await_args.kwargs["updates"] == [
        {
            "slot": "input",
            "object_key": "qqcc/demo/video/kiss/input",
            "content_sha256": hashlib.sha256(b"\x89PNG\r\n\x1a\ndemo").hexdigest(),
            "file_id": "uploaded-photo",
        },
        {
            "slot": "output",
            "object_key": "qqcc/demo/video/kiss/output",
            "content_sha256": hashlib.sha256(b"\x00\x00\x00\x18ftypmp42demo").hexdigest(),
            "file_id": "uploaded-video",
        },
    ]


@pytest.mark.asyncio
async def test_send_demo_media_refreshes_invalid_telegram_cache_from_r2():
    attempts = []
    cache = AsyncMock()

    async def _reply_media_group(*, media):
        attempts.append([item.media for item in media])
        if len(attempts) == 1:
            raise RuntimeError("wrong file identifier")
        return [
            SimpleNamespace(photo=[SimpleNamespace(file_id="fresh-input")]),
            SimpleNamespace(photo=[SimpleNamespace(file_id="fresh-output")]),
        ]

    scene = {
        "id": "portrait",
        "demo_input_media": {
            "object_key": "qqcc/demo/draw/portrait/input",
            "media_type": "image",
            "telegram_file_ids": {"123": "stale-input"},
        },
        "demo_output_media": {
            "object_key": "qqcc/demo/draw/portrait/output",
            "media_type": "image",
            "telegram_file_ids": {"123": "stale-output"},
        },
    }

    sent = await send_qqcc_scene_demo_media(
        message=SimpleNamespace(reply_media_group=_reply_media_group),
        bot=SimpleNamespace(id=123),
        scene_kind="draw",
        scene=scene,
        preview_url_builder=lambda media: f"https://r2.example/{media['object_key']}",
        cache_file_ids_func=cache,
    )

    assert sent is True
    assert attempts[0] == ["stale-input", "stale-output"]
    assert attempts[1] == [
        "https://r2.example/qqcc/demo/draw/portrait/input",
        "https://r2.example/qqcc/demo/draw/portrait/output",
    ]
    cache.assert_awaited_once()
    assert cache.await_args.kwargs["updates"] == [
        {
            "slot": "input",
            "object_key": "qqcc/demo/draw/portrait/input",
            "content_sha256": "",
            "file_id": "fresh-input",
        },
        {
            "slot": "output",
            "object_key": "qqcc/demo/draw/portrait/output",
            "content_sha256": "",
            "file_id": "fresh-output",
        },
    ]


@pytest.mark.asyncio
async def test_private_demo_media_forwards_trusted_tenant_id_to_cache_writer():
    cache = AsyncMock()

    async def _reply_photo(*, photo):
        assert photo == "https://r2.example/private-input"
        return SimpleNamespace(photo=[SimpleNamespace(file_id="private-file-id")])

    sent = await send_qqcc_scene_demo_media(
        message=SimpleNamespace(reply_photo=_reply_photo),
        bot=SimpleNamespace(id=456),
        scene_kind="draw",
        scene={
            "id": "portrait",
            "demo_input_media": {
                "object_key": "qqcc/private/7/demo/draw/portrait/input",
                "media_type": "image",
                "content_sha256": "a" * 64,
            },
        },
        private_bot_id=7,
        preview_url_builder=lambda _media: "https://r2.example/private-input",
        cache_file_ids_func=cache,
    )

    assert sent is True
    assert cache.await_args.kwargs["private_bot_id"] == 7
    assert cache.await_args.kwargs["updates"][0]["object_key"].startswith(
        "qqcc/private/7/demo/"
    )
