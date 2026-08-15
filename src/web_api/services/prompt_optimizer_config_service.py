from __future__ import annotations

from sqlalchemy import select

from src.database.models import PromptOptimizerSceneConfig
from src.prompt_optimizer.config_snapshot import (
    config_content_hash,
    referenced_variables,
    snapshot_content_hash,
    validate_config_templates,
)
from src.prompt_optimizer.registry import get_template_by_ref

SCENE_TEMPLATE_REFS = {
    "ltx_video_v2": "ltx_scene_script_cinematic@3",
    "ltx_t2v": "ltx_scene_script_cinematic@4",
    "ltx_t2v_ic": "ltx_scene_script_cinematic@4",
    "minimax_h3": "minimax_h3_10eros_naughtytimes@1",
}
SCENE_LABELS = {
    "ltx_video_v2": ("高级图生视频 v2", "首帧与首尾帧共用配置"),
    "ltx_t2v": ("纯文生视频", "不包含视觉参考素材"),
    "ltx_t2v_ic": ("双角色与环境文生视频", "两张人物面板与一张环境参考"),
    "minimax_h3": ("高级图生视频pro", "MiniMax H3 文生、首帧与首尾帧共用配置"),
}


def _default(scene_key: str) -> dict:
    if scene_key not in SCENE_TEMPLATE_REFS:
        raise ValueError("unknown scene_key")
    template = get_template_by_ref(SCENE_TEMPLATE_REFS[scene_key])
    user_template = template.user_template
    if scene_key == "ltx_t2v_ic":
        user_template += (
            "\n\nServer-trusted character descriptions:\n{character_descriptions}"
            "\nServer-trusted environment description:\n{environment_description}"
        )
    label, description = SCENE_LABELS[scene_key]
    content_hash = config_content_hash(
        scene_key=scene_key,
        display_name=label,
        description=description,
        system_template=template.system_template,
        user_template=user_template,
    )
    return {
        "scene_key": scene_key,
        "display_name": label,
        "description": description,
        "system_template": template.system_template,
        "user_template": user_template,
        "revision": 0,
        "content_hash": content_hash,
        "updated_by": "built-in",
    }


def get_default_config(scene_key: str) -> dict:
    return _default(scene_key)


def serialize_config(row: PromptOptimizerSceneConfig | None, scene_key: str) -> dict:
    if row is None:
        return _default(scene_key)
    return {
        "scene_key": row.scene_key,
        "display_name": row.display_name,
        "description": row.description or "",
        "system_template": row.system_template,
        "user_template": row.user_template,
        "revision": row.revision,
        "content_hash": row.content_hash,
        "updated_by": row.updated_by,
    }


async def list_configs(db) -> list[dict]:
    rows = {
        row.scene_key: row
        for row in (
            await db.execute(
                select(PromptOptimizerSceneConfig).where(
                    PromptOptimizerSceneConfig.scene_key.in_(SCENE_TEMPLATE_REFS)
                )
            )
        )
        .scalars()
        .all()
    }
    return [serialize_config(rows.get(key), key) for key in SCENE_TEMPLATE_REFS]


async def get_config(db, scene_key: str) -> dict:
    if scene_key not in SCENE_TEMPLATE_REFS:
        raise ValueError("unknown scene_key")
    row = await db.get(PromptOptimizerSceneConfig, scene_key)
    return serialize_config(row, scene_key)


async def save_config(db, *, scene_key: str, payload, updated_by: str) -> dict:
    if scene_key not in SCENE_TEMPLATE_REFS:
        raise ValueError("unknown scene_key")
    system_template = payload.system_template.strip()
    user_template = payload.user_template.strip()
    validate_config_templates(system_template, user_template)
    variables = referenced_variables(system_template) | referenced_variables(
        user_template
    )
    required_by_scene = {
        "ltx_video_v2": {"media_frame_instructions"},
        "ltx_t2v": {"media_frame_instructions"},
        "ltx_t2v_ic": {
            "media_frame_instructions",
            "character_descriptions",
            "environment_description",
        },
            "minimax_h3": {
                "media_frame_instructions",
            },
    }
    missing = required_by_scene[scene_key] - variables
    if missing:
        raise ValueError(
            f"missing required prompt variables: {', '.join(sorted(missing))}"
        )
    row = await db.get(PromptOptimizerSceneConfig, scene_key)
    revision = (row.revision if row else 0) + 1
    values = dict(
        display_name=payload.display_name.strip(),
        description=payload.description.strip(),
        system_template=system_template,
        user_template=user_template,
    )
    digest = config_content_hash(scene_key=scene_key, **values)
    if row is None:
        row = PromptOptimizerSceneConfig(
            scene_key=scene_key,
            revision=revision,
            content_hash=digest,
            updated_by=updated_by,
            **values,
        )
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.revision, row.content_hash, row.updated_by = revision, digest, updated_by
    await db.commit()
    return serialize_config(row, scene_key)


def render_config_snapshot(*, config: dict, profile_ref: str, variables: dict) -> dict:
    render_variables = {key: str(value) for key, value in variables.items()}
    render_variables["profile_ref"] = profile_ref
    system_message = config["system_template"].format_map(render_variables)
    user_message = config["user_template"].format_map(render_variables)
    snapshot = {
        "scene_key": config["scene_key"],
        "revision": config["revision"],
        "config_content_hash": config["content_hash"],
        "profile_ref": profile_ref,
        "system_message": system_message,
        "user_message": user_message,
    }
    snapshot["snapshot_hash"] = snapshot_content_hash(snapshot)
    return snapshot
