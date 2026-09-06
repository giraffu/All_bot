import warnings

from telegram import Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, TypeHandler
from telegram.warnings import PTBUserWarning

from src.handlers.main_bot_handler_registry import register_main_bot_handlers


class RecordingApplication:
    def __init__(self):
        self.handlers = []
        self.error_handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((handler, group))

    def add_error_handler(self, handler):
        self.error_handlers.append(handler)


def test_main_bot_registry_preserves_middleware_fsm_and_fallback_order():
    application = RecordingApplication()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=PTBUserWarning)
        register_main_bot_handlers(
            application,
            middleware=lambda _update, _context: None,
            advanced_video_entry_handler=ConversationHandler(
                entry_points=[], states={}, fallbacks=[], name="advanced-entry"
            ),
            advanced_video_compatibility_handlers=(
                ConversationHandler(
                    entry_points=[], states={}, fallbacks=[], name="advanced-compat"
                ),
            ),
        )

    handlers = [handler for handler, _group in application.handlers]
    assert isinstance(handlers[0], TypeHandler)
    assert handlers[0].type is Update
    assert application.handlers[0][1] == -1

    callback_fallback_index = next(
        index
        for index, handler in enumerate(handlers)
        if isinstance(handler, CallbackQueryHandler)
        and not isinstance(handler, ConversationHandler)
    )
    conversation_indexes = [
        index
        for index, handler in enumerate(handlers)
        if isinstance(handler, ConversationHandler)
    ]
    assert conversation_indexes
    assert max(conversation_indexes) < callback_fallback_index
    assert [
        handler.name for handler in handlers if isinstance(handler, ConversationHandler)
    ][6:8] == ["advanced-entry", "advanced-compat"]
    assert len(application.error_handlers) == 1
