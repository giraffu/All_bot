from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from string import Formatter

ALLOWED_CONFIG_VARIABLES = frozenset(
    {
        "profile_ref",
        "duration_seconds",
        "end_frame_clause",
        "media_frame_instructions",
        "original_prompt",
        "character_descriptions",
        "environment_description",
        "addon_summary",
        "addon_rules",
        "breasts_vocabulary_rule",
        "dialogue_language_instructions",
    }
)


def referenced_variables(template: str) -> frozenset[str]:
    return frozenset(
        field_name.split(".", 1)[0].split("[", 1)[0]
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    )


def validate_config_templates(system_template: str, user_template: str) -> None:
    variables = referenced_variables(system_template) | referenced_variables(
        user_template
    )
    unknown = variables - ALLOWED_CONFIG_VARIABLES
    if unknown:
        raise ValueError(f"unknown prompt variables: {', '.join(sorted(unknown))}")
    if "original_prompt" not in variables or "duration_seconds" not in variables:
        raise ValueError(
            "user prompt must reference original_prompt and duration_seconds"
        )


def config_content_hash(
    *,
    scene_key: str,
    display_name: str,
    description: str,
    system_template: str,
    user_template: str,
) -> str:
    payload = {
        "scene_key": scene_key,
        "display_name": display_name,
        "description": description,
        "system_template": system_template,
        "user_template": user_template,
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def snapshot_content_hash(snapshot: Mapping) -> str:
    payload = {
        key: snapshot[key]
        for key in (
            "scene_key",
            "revision",
            "config_content_hash",
            "profile_ref",
            "system_message",
            "user_message",
        )
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
