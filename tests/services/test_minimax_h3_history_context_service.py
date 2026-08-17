from src.services.minimax_h3_history_context_service import (
    MINIMAX_H3_HISTORY_CONTEXT_KEY,
    build_minimax_h3_history_context,
    extract_minimax_h3_history_context,
    merge_minimax_h3_history_context_into_extra_outputs,
)


def test_build_minimax_h3_history_context_preserves_locked_ordered_parameters():
    context = build_minimax_h3_history_context(
        task_type="minimax_h3_flf2v",
        metadata={
            "minimax_h3_mode": "flf2v",
            "requested_duration": 10,
            "minimax_h3_resolution_preset": "standard",
            "minimax_h3_aspect_ratio": "source",
            "lora_items": [
                {"name": "sex_pose", "strength": 0.5},
                {"name": "naughty_times", "strength": 1.2},
            ],
        },
    )

    assert context == {
        "version": 1,
        "mode": "flf2v",
        "requested_duration": 10,
        "resolution_preset": "standard",
        "aspect_ratio": "source",
        "lora_items": [
            {"name": "sex_pose", "strength": 0.5},
            {"name": "naughty_times", "strength": 1.2},
        ],
    }


def test_minimax_h3_context_is_only_valid_for_i2v_and_flf2v():
    metadata = {
        "minimax_h3_mode": "t2v",
        "requested_duration": 5,
        "minimax_h3_resolution_preset": "preview",
        "minimax_h3_aspect_ratio": "16:9",
    }
    assert build_minimax_h3_history_context(
        task_type="minimax_h3_t2v", metadata=metadata
    ) == {}
    assert merge_minimax_h3_history_context_into_extra_outputs(
        task_type="minimax_h3_t2v", extra_outputs={"last_frame": {}}, metadata=metadata
    ) == {"last_frame": {}}


def test_extract_minimax_h3_context_rejects_missing_or_unknown_versions():
    assert extract_minimax_h3_history_context({}) == {}
    assert extract_minimax_h3_history_context(
        {MINIMAX_H3_HISTORY_CONTEXT_KEY: {"version": 2, "mode": "i2v"}}
    ) == {}
