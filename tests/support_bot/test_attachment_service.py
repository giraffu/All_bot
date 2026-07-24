from types import SimpleNamespace

import pytest

from support_bot import attachment_service


@pytest.mark.asyncio
async def test_download_attachment_bytes_uses_local_file_server_path(monkeypatch):
    monkeypatch.setenv("TELEGRAM_FILE_BASE_URL", "http://local-file:8082/")
    requested_urls = []

    class FakeResponse:
        content = b"image-bytes"

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, timeout):
            requested_urls.append((url, timeout))
            return FakeResponse()

    monkeypatch.setattr(
        attachment_service.httpx,
        "AsyncClient",
        lambda **_kwargs: FakeClient(),
    )
    telegram_file = SimpleNamespace(
        file_path="/var/lib/telegram-bot-api/support/photo.jpg",
        get_bot=lambda: SimpleNamespace(base_file_url="http://local-file:8082"),
        download_as_bytearray=lambda: pytest.fail("PTB default download must not run"),
    )

    payload = await attachment_service.download_attachment_bytes(telegram_file)

    assert payload == b"image-bytes"
    assert requested_urls == [
        ("http://local-file:8082/var/lib/telegram-bot-api/support/photo.jpg", 120.0)
    ]


@pytest.mark.asyncio
async def test_download_attachment_bytes_keeps_ptb_fallback(monkeypatch):
    monkeypatch.setenv("TELEGRAM_FILE_BASE_URL", "http://local-file:8082")

    async def download_default():
        return bytearray(b"telegram-cloud")

    telegram_file = SimpleNamespace(
        file_path="photos/cloud.jpg",
        get_bot=lambda: SimpleNamespace(base_file_url="https://api.telegram.org/file/bot"),
        download_as_bytearray=download_default,
    )

    assert (
        await attachment_service.download_attachment_bytes(telegram_file)
        == b"telegram-cloud"
    )
