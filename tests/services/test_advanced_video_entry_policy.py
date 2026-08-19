from src.services.advanced_video_entry_policy import (
    active_advanced_video_menu_key,
    minimax_h3_advanced_video_entry_enabled,
)
from src import bot_main


def test_prod_uses_ltx_advanced_video_entry(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.delenv("MINIMAX_H3_BACKEND_ENABLED", raising=False)

    assert minimax_h3_advanced_video_entry_enabled() is False
    assert active_advanced_video_menu_key() == "menu.ltx_video"


def test_test_environment_keeps_h3_pro_entry(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "test")
    monkeypatch.delenv("MINIMAX_H3_BACKEND_ENABLED", raising=False)

    assert minimax_h3_advanced_video_entry_enabled() is True
    assert active_advanced_video_menu_key() == "menu.advanced_video_pro"


def test_explicit_backend_gate_overrides_environment_default(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")

    assert minimax_h3_advanced_video_entry_enabled() is True


def test_main_bot_builds_ltx_handler_for_prod(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "false")

    assert bot_main.build_advanced_video_entry_handler().name == "ltx_video_fsm"


def test_main_bot_builds_h3_handler_for_test(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "test")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")

    assert (
        bot_main.build_advanced_video_entry_handler().name
        == "advanced_video_pro_fsm"
    )
