from src.handlers.fsm import quick_video_fsm


def test_qqcc_h3_extension_scenes_only_include_enabled_i2v_entries():
    config = {
        "ai_video_scenes": [
            {"id": "continue", "name": "续写", "prompt": "continue", "duration": 5, "engine": "minimax_h3", "mode": "i2v"},
            {"id": "reference", "name": "参考", "prompt": "reference", "duration": 5, "engine": "minimax_h3", "mode": "ref2v", "reference_images": ["qqcc/config/ref2v/ai_video/reference.png"]},
        ]
    }

    scenes = quick_video_fsm._enabled_h3_extension_scenes(config)

    assert [scene["id"] for scene in scenes] == ["continue"]


def test_qqcc_h3_extension_uses_compact_callback_and_is_registered():
    handler = quick_video_fsm.get_quick_video_fsm_handler()
    entry_patterns = [
        getattr(getattr(item, "pattern", None), "pattern", "")
        for item in handler.entry_points
    ]

    assert any("h3_extend" in pattern for pattern in entry_patterns)
    callback_data = f"{quick_video_fsm.H3_EXTENSION_SCENE_CALLBACK_PREFIX}19"
    assert len(callback_data.encode("utf-8")) <= 64
