from __future__ import annotations

import hashlib
import json
import string
from copy import deepcopy

from sqlalchemy import select

from src.database.models import CharacterViewPromptConfig


TAG_GROUP_LABELS = {
    "breast_size": "乳房",
    "pubic_hair": "阴毛",
    "skin_tone": "肤色",
}

DEFAULT_TAG_OPTIONS = {
    "breast_size": {
        "large": "巨乳",
        "natural": "正常自然乳房",
        "flat": "平乳",
    },
    "pubic_hair": {
        "full": "浓密自然阴毛",
        "natural": "正常自然阴毛",
        "none": "无阴毛、阴部光滑",
    },
    "skin_tone": {
        "fair": "白皙肤色",
        "asian_yellow": "亚洲自然黄色肤色",
        "asian_tan": "亚洲晒黑肤色",
    },
}

_ENDING = "仅一个人物，纯白背景，不要文字、标签、边框或拼贴。"
_COMMON = (
    "严格保持身份、五官、发型、肤色、身材比例和身体特征一致。人物完全裸体，"
    "不穿任何衣物，不佩戴任何配饰"
)
_FEMALE_DETAIL = "明确保持成年女性解剖特征"
_MALE_DETAIL = (
    "明确保持成年男性解剖特征：自然勃起阴茎和阴囊完整、清晰、无遮挡，"
    "双手自然垂于身体两侧，不遮挡下体；不要女性乳房或女性生殖器"
)
_MALE_BACK_DETAIL = (
    "明确保持成年男性背部、腰臀和腿部解剖特征，双手自然垂于身体两侧；"
    "阴茎保持自然勃起并位于身体正面，不要在背面错误生成生殖器，"
    "不要女性乳房或女性生殖器"
)


def _neutral_prompts() -> dict[str, str]:
    return {
        "face_front": (
            "生成与源图为同一位成年人的正面脸部近景，严格保持身份、五官、发型、"
            "肤色和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何配饰，"
            f"直视镜头，画面包括完整头部、裸露肩部和上胸。{_ENDING}"
        ),
        "body_front": (
            "生成与源图为同一位成年人的全身正面站立图，严格保持身份、五官、发型、"
            "肤色、身材比例和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何"
            f"配饰，正对镜头自然站立，从头顶到双脚完整可见。{_ENDING}"
        ),
        "body_side": (
            "生成与源图为同一位成年人的全身侧面站立图，严格保持身份、五官、发型、"
            "肤色、身材比例和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何"
            "配饰，身体与头部均向左旋转九十度，呈严格侧面，从头顶到双脚完整可见。"
            f"{_ENDING}"
        ),
        "body_back": (
            "生成与源图为同一位成年人的全身背面站立图，严格保持身份、发型、肤色、"
            "身材比例和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何配饰，"
            f"背对镜头自然站立，不回头，从头顶到双脚完整可见。{_ENDING}"
        ),
        "genitals_front": (
            "生成与源图为同一位成年人的生殖器正面特写，保持肤色和身体特征一致。"
            "人物完全裸体，只展示一个成年人的人体参考细节，无互动、无道具、无体液，"
            f"纯白背景，不要文字、标签、边框或拼贴。"
        ),
    }


def _gender_templates(view_type: str) -> tuple[str, str]:
    if view_type == "face_front":
        base = (
            "生成与源图为同一位成年{gender}的正面脸部近景，严格保持身份、五官、发型、"
            "肤色和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何配饰，"
            f"直视镜头，画面包括完整头部、裸露肩部和上胸。{{tags}}{_ENDING}"
        )
        return base.format(gender="女性", tags="{tags}"), base.format(gender="男性", tags="{tags}")
    if view_type == "body_front":
        female = (
            f"生成与源图为同一位成年女性的全身正面站立图，{_COMMON}，"
            f"{_FEMALE_DETAIL}。{{tags}}正对镜头自然站立，从头顶到双脚完整可见。{_ENDING}"
        )
        male = (
            f"生成与源图为同一位成年男性的全身正面站立图，{_COMMON}，"
            f"{_MALE_DETAIL}。{{tags}}正对镜头自然站立，从头顶到双脚完整可见。{_ENDING}"
        )
        return female, male
    if view_type == "body_side":
        female = (
            f"生成与源图为同一位成年女性的全身侧面站立图，{_COMMON}，"
            f"{_FEMALE_DETAIL}。{{tags}}身体与头部均向左旋转九十度，呈严格侧面，"
            f"生殖器轮廓完整可见，从头顶到双脚完整可见。{_ENDING}"
        )
        male = (
            f"生成与源图为同一位成年男性的全身侧面站立图，{_COMMON}，"
            f"{_MALE_DETAIL}。{{tags}}身体与头部均向左旋转九十度，呈严格侧面，"
            f"生殖器轮廓完整可见，从头顶到双脚完整可见。{_ENDING}"
        )
        return female, male
    if view_type == "body_back":
        female = (
            f"生成与源图为同一位成年女性的全身背面站立图，{_COMMON}，"
            f"{_FEMALE_DETAIL}。{{tags}}背对镜头自然站立，不回头，从头顶到双脚完整可见。{_ENDING}"
        )
        male = (
            f"生成与源图为同一位成年男性的全身背面站立图，{_COMMON}，"
            f"{_MALE_BACK_DETAIL}。{{tags}}背对镜头自然站立，不回头，从头顶到双脚完整可见。{_ENDING}"
        )
        return female, male
    female = (
        f"生成与全身正面源图为同一位成年女性的外阴正面特写，{_COMMON}，"
        f"{_FEMALE_DETAIL}。{{tags}}外阴和周围皮肤清晰完整，保持中立人体参考姿势，"
        f"无互动、无道具、无体液，不展示第二个人。{_ENDING}"
    )
    male = (
        f"生成与全身正面源图为同一位成年男性的阴茎与阴囊正面特写，{_COMMON}，"
        f"{_MALE_DETAIL}。{{tags}}阴茎自然勃起，阴茎与阴囊清晰完整，"
        f"保持中立人体参考姿势，无互动、无道具、无体液，不展示第二个人。{_ENDING}"
    )
    return female, male


_VIEW_META = (
    ("face_front", "正脸图", 1, True, ["skin_tone"]),
    ("body_front", "全身正面图", 4, True, ["breast_size", "pubic_hair", "skin_tone"]),
    ("body_side", "全身侧面图", 5, True, ["breast_size", "pubic_hair", "skin_tone"]),
    ("body_back", "全身背面图", 6, True, ["breast_size", "pubic_hair", "skin_tone"]),
    ("genitals_front", "生殖器正面特写", 7, False, ["pubic_hair", "skin_tone"]),
)


def _build_defaults() -> dict[str, dict]:
    neutral = _neutral_prompts()
    result = {}
    for view_type, display_name, index, required, tag_groups in _VIEW_META:
        female, male = _gender_templates(view_type)
        result[view_type] = {
            "view_type": view_type,
            "display_name": display_name,
            "index": index,
            "required": required,
            "prompt_templates": {"neutral": neutral[view_type], "female": female, "male": male},
            "tag_groups": tag_groups,
            "tag_options": deepcopy(DEFAULT_TAG_OPTIONS),
        }
    return result


BUILTIN_CHARACTER_VIEW_CONFIGS = _build_defaults()
ALLOWED_TEMPLATE_VARIABLES = {"tags"}


def _digest(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_character_view_config(
    *,
    view_type: str,
    display_name: str,
    prompt_templates: dict,
    tag_groups: list,
    tag_options: dict,
) -> None:
    if view_type not in BUILTIN_CHARACTER_VIEW_CONFIGS:
        raise ValueError("unknown view_type")
    if not str(display_name).strip():
        raise ValueError("display_name is required")
    if set(prompt_templates) != {"neutral", "female", "male"}:
        raise ValueError("prompt_templates must contain neutral, female and male")
    for template in prompt_templates.values():
        if not str(template).strip():
            raise ValueError("prompt template is required")
        variables = {name for _, name, _, _ in string.Formatter().parse(str(template)) if name}
        unknown = variables - ALLOWED_TEMPLATE_VARIABLES
        if unknown:
            raise ValueError(f"unknown prompt variables: {', '.join(sorted(unknown))}")
    unknown_groups = set(tag_groups) - set(TAG_GROUP_LABELS)
    if unknown_groups:
        raise ValueError(f"unknown tag groups: {', '.join(sorted(unknown_groups))}")
    for group in TAG_GROUP_LABELS:
        expected = set(DEFAULT_TAG_OPTIONS[group])
        actual = set((tag_options or {}).get(group, {}))
        missing_value = any(
            not str(value).strip() for value in tag_options.get(group, {}).values()
        )
        if expected != actual or missing_value:
            raise ValueError(f"tag_options for {group} must define every supported option")


def get_builtin_character_view_config(view_type: str) -> dict:
    try:
        config = deepcopy(BUILTIN_CHARACTER_VIEW_CONFIGS[view_type])
    except KeyError as exc:
        raise ValueError("unknown view_type") from exc
    config.update(
        revision=0,
        content_hash=_digest(config),
        updated_by="built-in",
        config_source="built-in",
    )
    return config


def serialize_character_view_config(row: CharacterViewPromptConfig | None, view_type: str) -> dict:
    if row is None:
        return get_builtin_character_view_config(view_type)
    builtin = BUILTIN_CHARACTER_VIEW_CONFIGS[view_type]
    return {
        "view_type": view_type,
        "display_name": row.display_name,
        "index": builtin["index"],
        "required": builtin["required"],
        "prompt_templates": deepcopy(row.prompt_templates),
        "tag_groups": list(row.tag_groups or []),
        "tag_options": deepcopy(row.tag_options or {}),
        "revision": row.revision,
        "content_hash": row.content_hash,
        "updated_by": row.updated_by,
        "config_source": "database",
    }


async def list_character_view_configs(db) -> list[dict]:
    rows = {
        row.view_type: row
        for row in (await db.execute(select(CharacterViewPromptConfig))).scalars().all()
        if row.view_type in BUILTIN_CHARACTER_VIEW_CONFIGS
    }
    return [
        serialize_character_view_config(rows.get(view_type), view_type)
        for view_type in BUILTIN_CHARACTER_VIEW_CONFIGS
    ]


async def save_character_view_config(db, *, view_type: str, payload, updated_by: str) -> dict:
    templates = {key: str(value).strip() for key, value in dict(payload.prompt_templates).items()}
    groups = list(payload.tag_groups)
    options = deepcopy(dict(payload.tag_options))
    display_name = payload.display_name.strip()
    validate_character_view_config(
        view_type=view_type,
        display_name=display_name,
        prompt_templates=templates,
        tag_groups=groups,
        tag_options=options,
    )
    content = {
        "view_type": view_type,
        "display_name": display_name,
        "prompt_templates": templates,
        "tag_groups": groups,
        "tag_options": options,
    }
    row = await db.get(CharacterViewPromptConfig, view_type)
    revision = (row.revision if row else 0) + 1
    if row is None:
        row = CharacterViewPromptConfig(
            **content,
            revision=revision,
            content_hash=_digest(content),
            updated_by=updated_by,
        )
        db.add(row)
    else:
        for key, value in content.items():
            setattr(row, key, value)
        row.revision = revision
        row.content_hash = _digest(content)
        row.updated_by = updated_by
    await db.commit()
    return serialize_character_view_config(row, view_type)


def render_character_view_prompts(
    profile: dict | None,
    configs: list[dict] | None = None,
) -> dict[str, str]:
    resolved = configs or [
        get_builtin_character_view_config(key)
        for key in BUILTIN_CHARACTER_VIEW_CONFIGS
    ]
    gender = str((profile or {}).get("gender") or "neutral")
    if gender not in {"female", "male"}:
        gender = "neutral"
    prompts = {}
    for config in resolved:
        fragments = []
        for group in config["tag_groups"]:
            selected = (profile or {}).get(group)
            fragment = config["tag_options"].get(group, {}).get(selected)
            if fragment:
                fragments.append(fragment)
        tags = "、".join(fragments)
        tags_text = f"身体特征标签：{tags}。" if tags else ""
        prompts[config["view_type"]] = config["prompt_templates"][gender].format(tags=tags_text)
    return prompts
