import pytest

from paid_group_guard_bot.config import PaidGroupBotSettings


def _set_required_environment(monkeypatch):
    values = {
        "PAID_GROUP_BOT_TOKEN": "bot-token",
        "PAID_GROUP_CHAT_ID": "-1001",
        "TELEGRAM_API_BASE_URL": "https://telegram.example/api",
        "TELEGRAM_FILE_BASE_URL": "https://telegram.example/file",
        "PAID_GROUP_DECLINE_UNQUALIFIED": "false",
        "PAID_GROUP_DRY_RUN": "false",
        "PAID_GROUP_BOT_CONNECT_TIMEOUT": "60",
        "PAID_GROUP_BOT_READ_TIMEOUT": "60",
        "PAID_GROUP_BOT_WRITE_TIMEOUT": "60",
        "PAID_GROUP_BOT_POOL_SIZE": "20",
        "PAID_GROUP_BOT_POLL_INTERVAL": "2",
        "PAID_GROUP_BOT_POLL_TIMEOUT": "30",
        "PAID_GROUP_BOT_LOG_FILE": "/logs/bot.log",
        "PAID_GROUP_MODERATION_CONFIG_FILE": "/runtime/config.json",
        "PAID_GROUP_MODERATION_LOG_FILE": "/logs/moderation.jsonl",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_settings_use_only_explicit_runtime_environment(monkeypatch):
    _set_required_environment(monkeypatch)

    settings = PaidGroupBotSettings.from_env()

    assert settings.base_url == "https://telegram.example/api/bot"
    assert settings.base_file_url == "https://telegram.example/file"


def test_settings_fail_closed_without_runtime_endpoint(monkeypatch):
    _set_required_environment(monkeypatch)
    monkeypatch.delenv("TELEGRAM_FILE_BASE_URL")
    monkeypatch.delenv("PAID_GROUP_BOT_BASE_FILE_URL", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_FILE_BASE_URL is required"):
        PaidGroupBotSettings.from_env()
