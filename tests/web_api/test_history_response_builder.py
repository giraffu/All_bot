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


def test_extract_history_tags_adds_wan22_mode_tag_for_single_start_frame():
    tags = extract_history_tags(
        "prompt",
        task_type="wan22_video_v2",
        extra_outputs={"_wan22_context": {"wan22_use_end_frame": False}},
    )

    assert tags == ["task.wan22_start_frame"]


def test_extract_history_tags_adds_wan22_mode_tag_for_start_end_frame():
    tags = extract_history_tags(
        "prompt",
        task_type="wan22_video_v2",
        extra_outputs={"_wan22_context": {"wan22_use_end_frame": True}},
    )

    assert tags == ["task.wan22_start_end_frame"]


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
