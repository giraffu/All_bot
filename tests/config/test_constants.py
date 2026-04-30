from src.constants import VIDEO_TASK_TYPES, get_video_settings_keyboard, DYNAMIC_PRIORITY_RULES

def test_video_task_types_constant():
    expected_modes = [
        "doggy_style", "perfect_video_insert", "blowjob", 
        "undress_tongue", "closeup_blowjob", "custom_video", 
        "face_video", "face_video_step1", "face_video_step2", 
        "video_lora", "ltx_video"
    ]
    for mode in expected_modes:
        assert mode in VIDEO_TASK_TYPES

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
