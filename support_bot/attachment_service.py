from __future__ import annotations

from urllib.parse import urlparse

import httpx
from telegram import File

from src.services.telegram_runtime_bootstrap import resolve_telegram_file_base_url


async def download_attachment_bytes(file: File) -> bytes:
    """Download one support attachment without exposing a public object URL."""

    file_base_url = resolve_telegram_file_base_url()
    bot_base_file_url = str(file.get_bot().base_file_url or "").rstrip("/")
    if bot_base_file_url.startswith(file_base_url):
        raw_path = str(file.file_path or "")
        if not raw_path:
            raise RuntimeError("Telegram file_path is missing")
        if raw_path.startswith("http"):
            raw_path = urlparse(raw_path).path
        if not raw_path.startswith("/"):
            raw_path = "/" + raw_path
        async with httpx.AsyncClient(proxy=None) as client:
            response = await client.get(
                f"{file_base_url}{raw_path}",
                timeout=120.0,
            )
            response.raise_for_status()
            return response.content

    return bytes(await file.download_as_bytearray())
