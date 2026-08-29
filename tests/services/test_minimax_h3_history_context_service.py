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
        "version": 2,
        "mode": "flf2v",
        "requested_duration": 10,
        "resolution_preset": "standard",
        "aspect_ratio": "source",
        "lora_items": [
            {"name": "sex_pose", "strength": 0.5},
            {"name": "naughty_times", "strength": 1.2},
        ],
    }


def test_minimax_h3_context_supports_ref2v_fixed_aspect_templates():
    context = build_minimax_h3_history_context(
        task_type="minimax_h3_ref2v",
        metadata={
            "minimax_h3_mode": "ref2v",
            "requested_duration": 5,
            "minimax_h3_resolution_preset": "preview",
            "minimax_h3_aspect_ratio": "16:9",
            "reference_audio": "task-inputs/task-ref2v/1.m4a",
            "lora_items": [],
        },
    )

    assert context == {
        "version": 2,
        "mode": "ref2v",
        "requested_duration": 5,
        "resolution_preset": "preview",
        "aspect_ratio": "16:9",
        "reference_audio": "task-inputs/task-ref2v/1.m4a",
        "lora_items": [],
    }


def test_minimax_h3_context_rejects_local_reference_audio_paths():
    assert (
        build_minimax_h3_history_context(
            task_type="minimax_h3_ref2v",
            metadata={
                "minimax_h3_mode": "ref2v",
                "requested_duration": 5,
                "minimax_h3_resolution_preset": "preview",
                "minimax_h3_aspect_ratio": "16:9",
                "reference_audio": "/tmp/telegram-voice.ogg",
                "lora_items": [],
            },
        )
        == {}
    )


def test_minimax_h3_context_rejects_non_gallery_t2v():
    metadata = {
        "minimax_h3_mode": "t2v",
        "requested_duration": 5,
        "minimax_h3_resolution_preset": "preview",
        "minimax_h3_aspect_ratio": "16:9",
    }
    assert (
        build_minimax_h3_history_context(task_type="minimax_h3_t2v", metadata=metadata)
        == {}
    )
    assert merge_minimax_h3_history_context_into_extra_outputs(
        task_type="minimax_h3_t2v", extra_outputs={"last_frame": {}}, metadata=metadata
    ) == {"last_frame": {}}


def test_extract_minimax_h3_context_accepts_v1_and_rejects_unknown_versions():
    assert extract_minimax_h3_history_context({}) == {}
    assert extract_minimax_h3_history_context(
        {MINIMAX_H3_HISTORY_CONTEXT_KEY: {"version": 1, "mode": "i2v"}}
    ) == {"version": 1, "mode": "i2v"}
    assert (
        extract_minimax_h3_history_context(
            {MINIMAX_H3_HISTORY_CONTEXT_KEY: {"version": 3, "mode": "i2v"}}
        )
        == {}
    )


def test_build_minimax_h3_v2_context_keeps_verified_parent_chain():
    context = build_minimax_h3_history_context(
        task_type="minimax_h3_i2v",
        metadata={
            "minimax_h3_mode": "i2v",
            "requested_duration": 5,
            "minimax_h3_resolution_preset": "preview",
            "minimax_h3_aspect_ratio": "source",
            "lora_items": [],
            "minimax_h3_prev_task_id": "segment-2",
            "minimax_h3_chain_task_ids": ["segment-1", "segment-2"],
        },
    )

    assert context["version"] == 2
    assert context["prev_task_id"] == "segment-2"
    assert context["chain_task_ids"] == ["segment-1", "segment-2"]
