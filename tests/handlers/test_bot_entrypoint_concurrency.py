import inspect
from pathlib import Path

import paid_group_guard_bot.main as paid_group_main
import qqcc_bot.main as qqcc_main
from src import bot_main


def test_main_bot_uses_per_user_update_processor_and_qqcc_stays_serial():
    source = inspect.getsource(bot_main)

    assert ".concurrent_updates(build_main_bot_update_processor())" in source
    assert ".concurrent_updates(True)" not in source
    assert ".concurrent_updates(True)" not in inspect.getsource(qqcc_main)


def test_paid_group_guard_bot_keeps_concurrent_updates_enabled():
    assert ".concurrent_updates(True)" in inspect.getsource(paid_group_main)


def test_main_bot_uses_scail2_as_video_faceswap_entrypoint():
    source = inspect.getsource(bot_main)

    assert "face_video_fsm" not in source
    assert "get_face_video_fsm_handler" not in source
    assert "get_scail2_video_fsm_handler" in source
    assert not Path("src/handlers/fsm/face_video_fsm.py").exists()
