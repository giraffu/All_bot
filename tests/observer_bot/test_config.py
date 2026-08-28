from observer_bot.config import ObserverSettings


def test_settings_parse_isolated_bot_admins_and_authorized_groups():
    settings = ObserverSettings.from_mapping(
        {
            "OBSERVER_BOT_TOKEN": "observer-token",
            "OBSERVER_DATABASE_URL": "postgresql://observer@db/observer_prod",
            "OBSERVER_ADMIN_CHAT_IDS": "123, 456",
            "OBSERVER_AUTHORIZED_GROUP_IDS": "-1001,-1002",
            "OBSERVER_LM_STUDIO_BASE_URL": "http://lmstudio:1234/",
        }
    )

    assert settings.admin_chat_ids == frozenset({123, 456})
    assert settings.authorized_group_ids == frozenset({-1001, -1002})
    assert settings.lm_studio_base_url == "http://lmstudio:1234"
    assert settings.central_api_url == "http://central-api:8003"


def test_settings_allow_database_managed_admins():
    settings = ObserverSettings.from_mapping(
        {
            "OBSERVER_BOT_TOKEN": "observer-token",
            "OBSERVER_DATABASE_URL": "postgresql://observer@db/observer_prod",
            "OBSERVER_LM_STUDIO_BASE_URL": "http://lmstudio:1234",
        }
    )

    assert settings.admin_chat_ids == frozenset()
