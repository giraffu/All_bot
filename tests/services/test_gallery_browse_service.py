from types import SimpleNamespace

import pytest

from src.services.gallery_browse_service import (
    GalleryBrowseMediaSource,
    resolve_gallery_media_source,
    send_gallery_media_message,
)


@pytest.mark.asyncio
async def test_resolve_gallery_media_source_uses_cached_file_id_without_downloading(monkeypatch):
    monkeypatch.setenv("BOT_TYPE", "PROD")
    post = SimpleNamespace(
        id=1,
        task_id="task-1",
        media_type="image",
        telegram_file_id="tg-file-id",
    )
    history = SimpleNamespace(output_file="history/task-1/original.png")

    async def fail_resolver(**_kwargs):
        raise AssertionError("resolver should not be called when file_id is cached")

    source = await resolve_gallery_media_source(
        post=post,
        history=history,
        resolve_gallery_media_urls_func=fail_resolver,
    )

    assert source.cached_file_id == "tg-file-id"
    assert source.media_bytes is None


@pytest.mark.asyncio
async def test_resolve_gallery_media_source_downloads_current_gallery_url_when_cache_missing(monkeypatch):
    monkeypatch.setenv("BOT_TYPE", "PROD")
    post = SimpleNamespace(
        id=1,
        task_id="task-1",
        media_type="image",
        telegram_file_id=None,
    )
    history = SimpleNamespace(output_file="history/task-1/original.png")
    resolver_calls = []

    async def resolver(**kwargs):
        resolver_calls.append(kwargs)
        return "https://r2.example/original.png", ""

    async def downloader(url):
        return f"bytes:{url}".encode()

    source = await resolve_gallery_media_source(
        post=post,
        history=history,
        resolve_gallery_media_urls_func=resolver,
        download_media_bytes_func=downloader,
    )

    assert resolver_calls == [
        {
            "task_id": "task-1",
            "output_file": "history/task-1/original.png",
            "media_type": "image",
        }
    ]
    assert source.cached_file_id is None
    assert source.media_bytes == b"bytes:https://r2.example/original.png"
    assert source.media_url == "https://r2.example/original.png"


@pytest.mark.asyncio
async def test_send_gallery_media_message_refreshes_invalid_cached_file_id(monkeypatch):
    monkeypatch.setenv("BOT_TYPE", "PROD")
    post = SimpleNamespace(id=7, task_id="task-7", media_type="image")
    source = GalleryBrowseMediaSource(
        cached_file_id="bad-file-id",
        media_bytes=None,
        output_file="history/task-7/original.png",
    )

    class FakeBot:
        def __init__(self):
            self.photos = []

        async def send_photo(self, *, chat_id, photo, **_kwargs):
            self.photos.append((chat_id, photo))
            if photo == "bad-file-id":
                raise Exception("Bad Request: wrong file identifier")
            return SimpleNamespace(
                photo=[SimpleNamespace(file_id="new-file-id")],
            )

    class FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(telegram_file_id=None)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, _stmt):
            return FakeResult()

        async def commit(self):
            return None

    async def resolver(**_kwargs):
        return "https://r2.example/original.png", ""

    async def downloader(url):
        return f"bytes:{url}".encode()

    bot = FakeBot()
    await send_gallery_media_message(
        context=SimpleNamespace(bot=bot),
        chat_id=123,
        post=post,
        caption="caption",
        reply_markup=None,
        media_source=source,
        resolve_gallery_media_urls_func=resolver,
        download_media_bytes_func=downloader,
        session_factory=lambda: FakeSession(),
    )

    assert bot.photos == [
        (123, "bad-file-id"),
        (123, b"bytes:https://r2.example/original.png"),
    ]
