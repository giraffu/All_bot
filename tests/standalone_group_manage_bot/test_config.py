from standalone_group_manage_bot.config import GroupManageBotSettings
from standalone_group_manage_bot.moderation import load_group_manage_config


def test_settings_use_isolated_environment_and_paths(monkeypatch):
    values = {
        "GROUP_MANAGE_BOT_TOKEN": "secret",
        "GROUP_MANAGE_CHAT_ID": "-100123",
        "TELEGRAM_API_BASE_URL": "http://telegram:8081",
        "TELEGRAM_FILE_BASE_URL": "http://telegram:8081/file/bot",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    settings = GroupManageBotSettings.from_env()

    assert settings.target_chat_id == -100123
    assert settings.base_url == "http://telegram:8081/bot"
    assert settings.moderation_config_file == "/app/runtime/group-manage/config.json"
    assert settings.moderation_log_file == "/app/logs/group_manage_moderation.jsonl"


def test_missing_group_config_does_not_inherit_paid_guard_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PAID_GROUP_MODERATION_ENABLED", "false")
    monkeypatch.setenv("PAID_GROUP_BLOCK_LINKS", "false")

    config = load_group_manage_config(tmp_path / "missing.json")

    assert config.enabled is True
    assert config.block_links is True
