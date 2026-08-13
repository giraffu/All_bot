from standalone_group_manage_bot.config import GroupManageBotSettings
from standalone_group_manage_bot.main import build_application
import inspect
import standalone_group_manage_bot.main as main_module


def test_group_manage_bot_registers_only_message_handler(monkeypatch):
    handlers = []

    class App:
        def add_handler(self, handler):
            handlers.append(handler)

    class Builder:
        def __getattr__(self, _name):
            return lambda *_args, **_kwargs: self

        def build(self):
            return App()

    monkeypatch.setattr("standalone_group_manage_bot.main.ApplicationBuilder", Builder)
    monkeypatch.setattr("standalone_group_manage_bot.main.HTTPXRequest", lambda **_: object())
    monkeypatch.setattr(
        "standalone_group_manage_bot.main.build_message_moderation_handler",
        lambda _settings, **_kwargs: "message-handler",
    )
    settings = GroupManageBotSettings(token="secret", target_chat_id=-1001)

    build_application(settings)

    assert handlers == ["message-handler"]


def test_group_manage_entrypoint_does_not_import_database_backed_logger():
    source = inspect.getsource(main_module)
    assert "src.logger" not in source
    assert "src.database" not in source


def test_run_polling_allows_messages_only(monkeypatch):
    from standalone_group_manage_bot import main as module

    observed = {}

    class App:
        def run_polling(self, **kwargs):
            observed.update(kwargs)

    monkeypatch.setattr(
        module.GroupManageBotSettings,
        "from_env",
        lambda: GroupManageBotSettings(token="secret", target_chat_id=-1001),
    )
    monkeypatch.setattr(module, "setup_logging", lambda _path: None)
    monkeypatch.setattr(module, "build_application", lambda _settings: App())

    module.main()

    assert observed["allowed_updates"] == ["message"]
