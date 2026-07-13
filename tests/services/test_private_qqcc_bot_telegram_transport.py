import pytest

from src.services.private_qqcc_bot_telegram_transport import (
    PrivateBotTelegramTransportError,
    build_private_telegram_bot_base_url,
    resolve_private_telegram_file_base_url,
)


def test_private_bot_telegram_transport_defaults_to_official_https(monkeypatch):
    monkeypatch.delenv("PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL", raising=False)
    monkeypatch.delenv("PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL", raising=False)

    assert build_private_telegram_bot_base_url() == "https://api.telegram.org/bot"
    assert (
        resolve_private_telegram_file_base_url()
        == "https://api.telegram.org/file/bot"
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL", "http://69.63.220.115:8081"),
        ("PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL", "https://evil.example"),
        ("PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL", "http://69.63.220.115:8082"),
    ],
)
def test_private_bot_telegram_transport_rejects_insecure_or_untrusted_endpoints(
    monkeypatch,
    name,
    value,
):
    monkeypatch.setenv(name, value)

    with pytest.raises(PrivateBotTelegramTransportError):
        if name.endswith("FILE_BASE_URL"):
            resolve_private_telegram_file_base_url()
        else:
            build_private_telegram_bot_base_url()


def test_private_bot_telegram_transport_accepts_explicit_trusted_tls_host(monkeypatch):
    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS",
        "telegram.internal.example",
    )
    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL",
        "https://telegram.internal.example/api",
    )
    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL",
        "https://telegram.internal.example/file/bot",
    )

    assert (
        build_private_telegram_bot_base_url()
        == "https://telegram.internal.example/api/bot"
    )
    assert (
        resolve_private_telegram_file_base_url()
        == "https://telegram.internal.example/file/bot"
    )
