from datetime import datetime
from types import SimpleNamespace

import pytest

from src.web_api.services import history_response_builder
from src.web_api.presenters.media_presenter import extract_history_result_meta
from src.services.wan22_video_v2_extension_service import build_wan22_chain_prompt_summary
from src.web_api.services.history_response_builder import (
    build_favorite_gallery_payload,
    extract_history_tags,
)


@pytest.mark.asyncio
async def test_build_favorite_gallery_payload_uses_history_media_type_when_gallery_post_missing(
    monkeypatch,
):
    history = SimpleNamespace(
        task_id="task-legacy-video",
        output_file="123/output_images/task-legacy-video.mp4",
        type="doggy_style",
        billing_resolution=None,
        width=720,
        height=1280,
        duration=8,
        prompt=None,
        created_at=datetime(2026, 5, 27),
    )

    async def fake_resolve_history_media_urls_func(**_kwargs):
        return "https://example.com/task-legacy-video.mp4", ""

    monkeypatch.setattr(
        history_response_builder,
        "resolve_history_media_urls",
        fake_resolve_history_media_urls_func,
    )

    items = await build_favorite_gallery_payload(
        histories=[history],
        gallery_post_map={},
    )

    assert len(items) == 1
    assert items[0].media_type == "video"
    assert items[0].task_type == "doggy_style"


@pytest.mark.asyncio
async def test_build_favorite_gallery_payload_exposes_original_input_files(monkeypatch):
    history = SimpleNamespace(
        task_id="task-scail2",
        output_file="123/output_images/task-scail2.mp4",
        type="scail2_action_transfer",
        input_file="uploads/reference.png|uploads/motion.mp4",
        billing_resolution=None,
        width=512,
        height=896,
        duration=5,
        prompt="natural motion",
        created_at=datetime(2026, 6, 19),
        extra_outputs={},
    )

    async def fake_resolve_history_media_urls_func(**_kwargs):
        return "https://example.com/task-scail2.mp4", "https://example.com/thumb.png"

    monkeypatch.setattr(
        history_response_builder,
        "resolve_history_media_urls",
        fake_resolve_history_media_urls_func,
    )
    monkeypatch.setattr(
        history_response_builder,
        "build_storage_input_file_url",
        lambda key: f"https://storage.test/{key}",
    )

    items = await build_favorite_gallery_payload(
        histories=[history],
        gallery_post_map={},
    )

    assert len(items) == 1
    assert items[0].input_file == "uploads/reference.png"
    assert items[0].input_file_url == "https://storage.test/uploads/reference.png"
    assert items[0].input_files == ["uploads/reference.png", "uploads/motion.mp4"]
    assert items[0].input_file_urls == [
        "https://storage.test/uploads/reference.png",
        "https://storage.test/uploads/motion.mp4",
    ]


def test_extract_history_tags_adds_wan22_mode_tag_for_single_start_frame():
    tags = extract_history_tags(
        "prompt",
        task_type="wan22_video_v2",
        extra_outputs={"_wan22_context": {"wan22_use_end_frame": False}},
    )

    assert tags == ["task.wan22_start_frame", "task.wan22_segment:1"]


def test_extract_history_tags_adds_wan22_mode_tag_for_start_end_frame():
    tags = extract_history_tags(
        "prompt",
        task_type="wan22_video_v2",
        extra_outputs={"_wan22_context": {"wan22_use_end_frame": True}},
    )

    assert tags == ["task.wan22_start_end_frame", "task.wan22_segment:1"]


def test_extract_history_tags_adds_wan22_segment_tag_for_non_first_segment():
    tags = extract_history_tags(
        "prompt",
        task_type="wan22_video_v2",
        extra_outputs={
            "_wan22_context": {
                "wan22_use_end_frame": False,
                "wan22_prev_task_id": "task-prev",
                "wan22_chain_task_ids": ["task-1", "task-2"],
            }
        },
    )

    assert tags == ["task.wan22_start_frame", "task.wan22_segment:3"]


def test_extract_history_tags_skips_mode_tag_for_stitched_wan22_record():
    tags = extract_history_tags(
        "prompt",
        task_type="wan22_video_v2",
        extra_outputs={
            "wan22_chain_stitch": {
                "segment_count": 3,
                "wan22_chain_task_ids": ["task-1", "task-2", "task-3"],
            }
        },
    )

    assert tags == ["task.wan22_stitched_video:3"]


def test_extract_history_tags_adds_ltx_mode_tag_for_single_start_frame():
    tags = extract_history_tags(
        "prompt",
        task_type="ltx_video",
        extra_outputs={"_ltx_context": {"ltx_mode": "i2v"}},
    )

    assert tags == ["task.ltx_start_frame", "task.ltx_segment:1"]


def test_extract_history_tags_adds_ltx_mode_tag_for_start_end_frame():
    tags = extract_history_tags(
        "prompt",
        task_type="ltx_video",
        extra_outputs={
            "_ltx_context": {
                "ltx_mode": "flf2v",
                "ltx_use_end_frame": True,
            }
        },
    )

    assert tags == ["task.ltx_start_end_frame", "task.ltx_segment:1"]


def test_extract_history_tags_adds_ltx_segment_tag_for_non_first_segment():
    tags = extract_history_tags(
        "prompt",
        task_type="ltx_video",
        extra_outputs={
            "_ltx_context": {
                "ltx_mode": "i2v",
                "ltx_prev_task_id": "ltx-task-1",
                "ltx_chain_task_ids": ["ltx-task-1", "ltx-task-2"],
            }
        },
    )

    assert tags == ["task.ltx_start_frame", "task.ltx_segment:3"]


def test_extract_history_tags_adds_ltx_stitched_video_tag():
    tags = extract_history_tags(
        "prompt",
        task_type="ltx_video",
        extra_outputs={
            "ltx_chain_stitch": {
                "segment_count": 2,
                "ltx_chain_task_ids": ["ltx-task-1", "ltx-task-2"],
            }
        },
    )

    assert tags == ["task.ltx_stitched_video:2"]


def test_extract_history_result_meta_marks_stitched_wan22_record():
    result_meta = extract_history_result_meta(
        task_type="wan22_video_v2",
        extra_outputs={
            "wan22_chain_stitch": {
                "segment_count": 2,
                "wan22_chain_task_ids": ["task-1", "task-2"],
            }
        },
    )

    assert result_meta == {"wan22_is_stitched": True}


def test_extract_history_result_meta_adds_segment_index_for_wan22_segment():
    result_meta = extract_history_result_meta(
        task_type="wan22_video_v2",
        extra_outputs={
            "_wan22_context": {
                "wan22_use_end_frame": False,
                "wan22_chain_task_ids": ["task-1"],
            }
        },
    )

    assert result_meta == {
        "wan22_use_end_frame": False,
        "wan22_chain_task_ids": ["task-1"],
        "wan22_segment_index": 2,
    }


def test_extract_history_result_meta_adds_ltx_chain_context():
    result_meta = extract_history_result_meta(
        task_type="ltx_video",
        extra_outputs={
            "_ltx_context": {
                "ltx_mode": "i2v",
                "ltx_prev_task_id": "ltx-task-1",
                "ltx_chain_task_ids": ["ltx-task-1"],
            }
        },
    )

    assert result_meta == {
        "ltx_mode": "i2v",
        "ltx_prev_task_id": "ltx-task-1",
        "ltx_chain_task_ids": ["ltx-task-1"],
        "ltx_segment_index": 2,
    }


def test_extract_history_result_meta_marks_stitched_ltx_record():
    result_meta = extract_history_result_meta(
        task_type="ltx_video",
        extra_outputs={
            "ltx_chain_stitch": {
                "segment_count": 2,
                "ltx_chain_task_ids": ["ltx-task-1", "ltx-task-2"],
            }
        },
    )

    assert result_meta == {"ltx_is_stitched": True}


def test_extract_history_result_meta_exposes_public_h3_chain_fields_only():
    result_meta = extract_history_result_meta(
        task_type="minimax_h3_i2v",
        extra_outputs={
            "_minimax_h3_context": {
                "version": 2,
                "mode": "i2v",
                "requested_duration": 5,
                "resolution_preset": "preview",
                "aspect_ratio": "source",
                "lora_items": [],
                "prev_task_id": "h3-1",
                "chain_task_ids": ["h3-1"],
            }
        },
    )

    assert result_meta == {
        "minimax_h3_prev_task_id": "h3-1",
        "minimax_h3_chain_task_ids": ["h3-1"],
        "minimax_h3_segment_index": 2,
    }


def test_extract_history_result_meta_marks_h3_stitched_record():
    result_meta = extract_history_result_meta(
        task_type="minimax_h3_i2v",
        extra_outputs={
            "_minimax_h3_chain_stitch": {
                "version": 1,
                "segment_count": 2,
                "chain_task_ids": ["h3-1", "h3-2"],
                "source_task_id": "h3-2",
            }
        },
    )

    assert result_meta == {
        "minimax_h3_chain_task_ids": ["h3-1", "h3-2"],
        "minimax_h3_is_stitched": True,
    }


def test_build_wan22_chain_prompt_summary_splits_segments_cleanly():
    summary = build_wan22_chain_prompt_summary(
        [
            SimpleNamespace(prompt="第一段提示词"),
            SimpleNamespace(prompt=""),
            SimpleNamespace(prompt="第三段提示词"),
        ]
    )

    assert summary == (
        "【第 1 段】\n第一段提示词\n\n"
        "【第 2 段】\n（未填写提示词）\n\n"
        "【第 3 段】\n第三段提示词"
    )
