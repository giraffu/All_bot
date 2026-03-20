import pytest
import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

def test_import_bot_test():
    try:
        from src import bot_test
        assert bot_test is not None
    except ImportError as e:
        pytest.fail(f"Failed to import src.bot_test: {e}")

def test_import_handlers():
    try:
        from src.handlers import message_handler
        from src.handlers import command_handler
        from src.handlers import callback_handler
        assert message_handler and command_handler and callback_handler
    except ImportError as e:
        pytest.fail(f"Failed to import handlers: {e}")
