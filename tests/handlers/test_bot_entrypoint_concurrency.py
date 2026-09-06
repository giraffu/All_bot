import inspect
from pathlib import Path

import paid_group_guard_bot.main as paid_group_main
import qqcc_bot.main as qqcc_main
from src import bot_main
from src.handlers import main_bot_handler_registry


def test_main_and_qqcc_bots_use_keyed_update_processors():
    source = inspect.getsource(bot_main)
    qqcc_source = inspect.getsource(qqcc_main)

    assert ".concurrent_updates(build_main_bot_update_processor())" in source
    assert ".concurrent_updates(True)" not in source
    assert ".concurrent_updates(build_qqcc_bot_update_processor())" in qqcc_source
    assert ".concurrent_updates(True)" not in qqcc_source


def test_paid_group_guard_bot_keeps_concurrent_updates_enabled():
    assert ".concurrent_updates(True)" in inspect.getsource(paid_group_main)


def test_main_bot_uses_scail2_as_video_faceswap_entrypoint():
    source = inspect.getsource(main_bot_handler_registry)

    assert "face_video_fsm" not in source
    assert "get_face_video_fsm_handler" not in source
    assert "get_scail2_video_fsm_handler" in source
    assert not Path("src/handlers/fsm/face_video_fsm.py").exists()
