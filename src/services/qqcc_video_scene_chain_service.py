from __future__ import annotations

from typing import Any


QQCC_VIDEO_SCENE_SECTIONS = {
    "video": "video_scenes",
    "ai_video": "ai_video_scenes",
}


class QqccVideoSceneChainError(ValueError):
    """Raised before submission when a QQCC video-scene chain is invalid."""


def _scene_id(scene: Any) -> str:
    if not isinstance(scene, dict):
        return ""
    value = scene.get("id")
    return value.strip() if isinstance(value, str) else ""


def _next_scene_id(scene: Any) -> str:
    if not isinstance(scene, dict):
        return ""
    value = scene.get("next_scene_id")
    return value.strip() if isinstance(value, str) else ""


def _scenes_for_kind(config: dict[str, Any], scene_kind: str) -> list[dict[str, Any]]:
    section = QQCC_VIDEO_SCENE_SECTIONS.get(str(scene_kind or ""))
    if section is None:
        raise QqccVideoSceneChainError(f"unsupported QQCC video scene kind: {scene_kind}")
    raw_scenes = config.get(section)
    return [scene for scene in raw_scenes or [] if isinstance(scene, dict)]


def _cycle_path(next_by_id: dict[str, str]) -> list[str] | None:
    globally_done: set[str] = set()
    for start in next_by_id:
        if start in globally_done:
            continue
        path: list[str] = []
        seen_at: dict[str, int] = {}
        current = start
        while current:
            if current in seen_at:
                return [*path[seen_at[current] :], current]
            if current in globally_done:
                break
            seen_at[current] = len(path)
            path.append(current)
            current = next_by_id.get(current, "")
        globally_done.update(path)
    return None


def validate_qqcc_video_scene_chain_config(raw_config: Any) -> None:
    """Validate persisted links without normalizing invalid intent away."""

    if not isinstance(raw_config, dict):
        return
    for scene_kind, section in QQCC_VIDEO_SCENE_SECTIONS.items():
        raw_scenes = raw_config.get(section)
        if not isinstance(raw_scenes, list):
            continue
        scenes = [scene for scene in raw_scenes if isinstance(scene, dict)]
        ids = {_scene_id(scene) for scene in scenes if _scene_id(scene)}
        next_by_id: dict[str, str] = {}
        for scene in scenes:
            scene_id = _scene_id(scene)
            target = _next_scene_id(scene)
            if not scene_id or not target:
                continue
            if target not in ids:
                raise QqccVideoSceneChainError(
                    f"{scene_kind} scene {scene_id} references missing scene {target}"
                )
            next_by_id[scene_id] = target
        cycle = _cycle_path(next_by_id)
        if cycle:
            raise QqccVideoSceneChainError(
                f"{scene_kind} video scene chain contains a cycle: {' -> '.join(cycle)}"
            )


def normalize_qqcc_video_scene_links(scenes: list[dict[str, Any]]) -> None:
    """Best-effort compatibility normalization for legacy/corrupt saved config."""

    scenes_by_id = {_scene_id(scene): scene for scene in scenes if _scene_id(scene)}
    for scene_id, scene in scenes_by_id.items():
        target = _next_scene_id(scene)
        scene["next_scene_id"] = target if target in scenes_by_id else None

    next_by_id = {
        scene_id: str(scene.get("next_scene_id") or "")
        for scene_id, scene in scenes_by_id.items()
        if scene.get("next_scene_id")
    }
    while cycle := _cycle_path(next_by_id):
        for scene_id in cycle[:-1]:
            scenes_by_id[scene_id]["next_scene_id"] = None
            next_by_id.pop(scene_id, None)


def resolve_qqcc_video_scene_chain(
    config: dict[str, Any],
    *,
    scene_kind: str,
    root_scene_id: str,
) -> tuple[dict[str, Any], ...]:
    scenes = _scenes_for_kind(config, scene_kind)
    scenes_by_id = {_scene_id(scene): scene for scene in scenes if _scene_id(scene)}
    current = str(root_scene_id or "").strip()
    if current not in scenes_by_id:
        raise QqccVideoSceneChainError(
            f"{scene_kind} root video scene does not exist: {current}"
        )

    result: list[dict[str, Any]] = []
    seen_at: dict[str, int] = {}
    while current:
        if current in seen_at:
            cycle = [
                *(_scene_id(scene) for scene in result[seen_at[current] :]),
                current,
            ]
            raise QqccVideoSceneChainError(
                f"{scene_kind} video scene chain contains a cycle: {' -> '.join(cycle)}"
            )
        scene = scenes_by_id.get(current)
        if scene is None:
            raise QqccVideoSceneChainError(
                f"{scene_kind} video scene chain references missing scene: {current}"
            )
        seen_at[current] = len(result)
        result.append(dict(scene))
        current = _next_scene_id(scene)
    return tuple(result)
