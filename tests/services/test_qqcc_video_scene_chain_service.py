from __future__ import annotations

import pytest

from src.services.qqcc_video_scene_chain_service import (
    QqccVideoSceneChainError,
    resolve_qqcc_video_scene_chain,
    validate_qqcc_video_scene_chain_config,
)


def _scene(scene_id: str, next_scene_id: str | None = None) -> dict:
    return {
        "id": scene_id,
        "name": scene_id,
        "prompt": f"prompt-{scene_id}",
        "duration": "5s",
        "engine": "image_to_video",
        "next_scene_id": next_scene_id,
    }


def test_video_scene_chain_resolves_long_chain_iteratively():
    scenes = [
        _scene(str(index), str(index + 1) if index < 249 else None)
        for index in range(250)
    ]

    chain = resolve_qqcc_video_scene_chain(
        {"video_scenes": scenes}, scene_kind="video", root_scene_id="0"
    )

    assert [scene["id"] for scene in chain] == [str(index) for index in range(250)]


@pytest.mark.parametrize(
    "scenes, expected_path",
    [
        ([_scene("a", "a")], "a -> a"),
        ([_scene("a", "b"), _scene("b", "a")], "a -> b -> a"),
        (
            [_scene("a", "b"), _scene("b", "c"), _scene("c", "b")],
            "b -> c -> b",
        ),
    ],
)
def test_video_scene_chain_validation_rejects_cycles_with_path(scenes, expected_path):
    with pytest.raises(QqccVideoSceneChainError, match=expected_path):
        validate_qqcc_video_scene_chain_config({"video_scenes": scenes})


def test_video_scene_chain_validation_rejects_missing_target():
    with pytest.raises(QqccVideoSceneChainError, match="missing"):
        validate_qqcc_video_scene_chain_config(
            {"ai_video_scenes": [_scene("a", "missing")]}
        )


def test_runtime_resolver_fails_closed_for_corrupt_cycle():
    with pytest.raises(QqccVideoSceneChainError, match="a -> b -> a"):
        resolve_qqcc_video_scene_chain(
            {"video_scenes": [_scene("a", "b"), _scene("b", "a")]},
            scene_kind="video",
            root_scene_id="a",
        )
