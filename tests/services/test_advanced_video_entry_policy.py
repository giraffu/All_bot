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

    assert minimax_h3_advanced_video_entry_enabled() is False
    assert active_advanced_video_menu_key() == "menu.ltx_video"


def test_explicit_backend_gate_overrides_environment_default(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")

    monkeypatch.setenv("MINIMAX_H3_ENTRY_ENABLED", "true")
    assert minimax_h3_advanced_video_entry_enabled() is True


def test_main_bot_builds_ltx_handler_for_prod(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "false")

    assert bot_main.build_advanced_video_entry_handler().name == "ltx_video_fsm"


def test_main_bot_keeps_ltx_primary_handler_when_h3_is_available(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "test")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_H3_ENTRY_ENABLED", "true")

    assert bot_main.build_advanced_video_entry_handler().name == "ltx_video_fsm"
    assert [
        handler.name
        for handler in bot_main.build_advanced_video_compatibility_handlers()
    ] == ["advanced_video_pro_fsm"]


def test_main_bot_builds_ltx_handler_when_h3_backend_stays_enabled_but_entry_is_hidden(
    monkeypatch,
):
    monkeypatch.setenv("ALLBOT_ENV", "test")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_H3_ENTRY_ENABLED", "false")

    assert bot_main.build_advanced_video_entry_handler().name == "ltx_video_fsm"


def test_hidden_h3_entry_keeps_command_compatibility_without_claiming_ltx_routes(
    monkeypatch,
):
    monkeypatch.setenv("ALLBOT_ENV", "test")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_H3_ENTRY_ENABLED", "false")

    handlers = bot_main.build_advanced_video_compatibility_handlers()

    assert [handler.name for handler in handlers] == ["advanced_video_pro_fsm"]
    entrypoint_commands = {
        command
        for entrypoint in handlers[0].entry_points
        for command in getattr(entrypoint, "commands", frozenset())
    }
    assert "advanced_video_pro" in entrypoint_commands
    assert "ltx_video" not in entrypoint_commands


def test_visible_h3_entry_uses_its_own_routes_without_claiming_ltx(monkeypatch):
    monkeypatch.setenv("ALLBOT_ENV", "test")
    monkeypatch.setenv("MINIMAX_H3_BACKEND_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_H3_ENTRY_ENABLED", "true")

    handlers = bot_main.build_advanced_video_compatibility_handlers()

    assert [handler.name for handler in handlers] == ["advanced_video_pro_fsm"]
    entrypoint_commands = {
        command
        for entrypoint in handlers[0].entry_points
        for command in getattr(entrypoint, "commands", frozenset())
    }
    assert "advanced_video_pro" in entrypoint_commands
    assert "ltx_video" not in entrypoint_commands
