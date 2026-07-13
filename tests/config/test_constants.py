from src.constants import (
    DYNAMIC_PRIORITY_RULES,
    MODE_IMAGE_TO_VIDEO,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
    VIDEO_TASK_TYPES,
)
from src.database.models import History


def test_video_task_types_constant():
    expected_modes = [
        "doggy_style",
        "perfect_video_insert",
        "blowjob",
        "undress_tongue",
        "closeup_blowjob",
        "custom_video",
        "face_video",
        "face_video_step1",
        "face_video_step2",
        "video_lora",
        "ltx_video",
        MODE_SCAIL2_ACTION_TRANSFER,
        MODE_SCAIL2_ACTION_TRANSFER_LONG,
        MODE_SCAIL2_VIDEO_REPLACEMENT,
        MODE_SCAIL2_FACE_SWAP_V2,
    ]
    for mode in expected_modes:
        assert mode in VIDEO_TASK_TYPES


def test_history_type_column_can_store_all_video_task_types():
    max_task_type_length = max(len(task_type) for task_type in VIDEO_TASK_TYPES)

    assert History.__table__.c.type.type.length >= max_task_type_length


def test_mode_image_to_video_alias_keeps_legacy_value():
    assert MODE_IMAGE_TO_VIDEO == "video_lora"
    assert MODE_IMAGE_TO_VIDEO in VIDEO_TASK_TYPES


def test_dynamic_priority_rules_structure():
    assert "真传弟子" in DYNAMIC_PRIORITY_RULES
    assert "凡人" in DYNAMIC_PRIORITY_RULES
    assert isinstance(DYNAMIC_PRIORITY_RULES["真传弟子"], list)

    # Check Mortal group has no rules
    assert len(DYNAMIC_PRIORITY_RULES["凡人"]) == 0

    # Verify tuple structures
    for limit, priority in DYNAMIC_PRIORITY_RULES["真传弟子"]:
        assert isinstance(limit, (int, float))
        assert isinstance(priority, int)
