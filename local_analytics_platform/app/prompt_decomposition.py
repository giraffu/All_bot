from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable


PROMPT_DECOMPOSITION_DEFAULT_TASK = "edit"
PROMPT_DECOMPOSITION_ALLOWED_TASKS = {"edit", "edit_v2"}
PROMPT_DECOMPOSITION_DEFAULT_LIMIT = 20
PROMPT_DECOMPOSITION_MAX_LIMIT = 100
PROMPT_DECOMPOSITION_MIN_TOKEN_PROMPT_COUNT = 20
PROMPT_DECOMPOSITION_MAX_SELECTED_TOKENS = 24
PROMPT_DECOMPOSITION_SAVED_LIST_LIMIT = 20

PROMPT_DECOMPOSITION_GROUP_DEFINITIONS: dict[str, dict[str, Any]] = {
    "preserve": {
        "label": "保持口径",
        "order": 10,
        "note": "保留原图一致性和不变要求",
    },
    "scene": {
        "label": "场景",
        "order": 20,
        "note": "地点、背景和空间环境",
    },
    "items": {
        "label": "物品",
        "order": 30,
        "note": "道具、家具和场景内物件",
    },
    "expression": {
        "label": "表情",
        "order": 40,
        "note": "表情、情绪和面部状态",
    },
    "adult_theme": {
        "label": "成人主题",
        "order": 50,
        "note": "体液、角色、羞辱、裸露和成人概念",
    },
    "pose_action": {
        "label": "动作姿势",
        "order": 60,
        "note": "姿势、动作和肢体朝向",
    },
    "visual": {
        "label": "画面风格构图",
        "order": 70,
        "note": "镜头、构图、角度、风格和质感",
    },
    "body_detail": {
        "label": "身体细节",
        "order": 80,
        "note": "身体部位及局部细节表现",
    },
    "appearance": {
        "label": "外观特征",
        "order": 90,
        "note": "体型、皮肤、妆容和外观状态",
    },
    "clothing": {
        "label": "服饰配件",
        "order": 100,
        "note": "衣物、鞋袜、配件和服饰变化",
    },
    "subject": {
        "label": "人物主体",
        "order": 110,
        "note": "人数、年龄、族裔和身份关系",
    },
}

PROMPT_DECOMPOSITION_CATEGORY_TO_GROUP = {
    "保持口径": "preserve",
    "人物主体": "subject",
    "动作姿势": "pose_action",
    "姿势动作": "pose_action",
    "成人动作": "pose_action",
    "成人主题": "adult_theme",
    "成人角色": "adult_theme",
    "表情情绪": "expression",
    "表情状态": "expression",
    "镜头构图": "visual",
    "风格质量": "visual",
    "身体部分": "body_detail",
    "身体部位": "body_detail",
    "成人解剖": "body_detail",
    "身体/镜头": "body_detail",
    "外观特征": "appearance",
    "服饰配件": "clothing",
    "场景": "scene",
    "场景环境": "scene",
    "场景物体": "scene",
    "场景场景": "scene",
}

PROMPT_DECOMPOSITION_ITEM_SUBCATEGORIES = {
    "家具",
    "器具道具",
    "器具",
    "道具",
    "活动道具",
    "场景道具",
}

PROMPT_DECOMPOSITION_SUBGROUP_LABEL_OVERRIDES: dict[tuple[str, str], str] = {
    ("items", "器具道具"): "成人道具",
    ("items", "家具"): "场景物件",
    ("scene", "背景"): "背景环境",
    ("visual", "质量/风格"): "质量与风格",
    ("visual", "质量/清晰度"): "质量与清晰度",
    ("body_detail", "身体区域"): "身体区域",
    ("body_detail", "部位/镜头"): "局部特写",
    ("subject", "角色/关系"): "角色关系",
    ("subject", "主体/关系"): "主体关系",
    ("adult_theme", "成人行为"): "成人行为",
    ("adult_theme", "器具道具"): "成人道具",
}

PROMPT_DECOMPOSITION_SAVED_SCHEMA_SQL = (
    """
    create table if not exists analytics_prompt_decomposition_saved_templates (
        id bigserial primary key,
        scope_key text not null,
        task_type text not null,
        title text not null default '',
        prompt_hash text not null,
        prompt text not null default '',
        selected_tokens text[] not null default '{}',
        tokens text[] not null default '{}',
        grouped_tokens jsonb not null default '[]'::jsonb,
        uses bigint not null default 0,
        users bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        last_seen timestamptz,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        unique (scope_key, prompt_hash)
    )
    """,
    (
        "create index if not exists idx_prompt_decomposition_saved_scope_updated "
        "on analytics_prompt_decomposition_saved_templates(scope_key, updated_at desc)"
    ),
)


@dataclass(frozen=True)
class PromptDecompositionTokenMetadata:
    token: str
    group_key: str
    group_label: str
    subgroup_key: str
    subgroup_label: str
    category_label: str
    subcategory_label: str


def ensure_prompt_decomposition_task(task_type: str | None) -> str:
    normalized = str(task_type or PROMPT_DECOMPOSITION_DEFAULT_TASK).strip() or PROMPT_DECOMPOSITION_DEFAULT_TASK
    if normalized not in PROMPT_DECOMPOSITION_ALLOWED_TASKS:
        raise ValueError(f"unsupported prompt decomposition task: {normalized}")
    return normalized


async def ensure_prompt_decomposition_schema(conn: Any) -> None:
    for statement in PROMPT_DECOMPOSITION_SAVED_SCHEMA_SQL:
        await conn.execute(statement)


def prompt_decomposition_group_key(category_label: str | None, subcategory_label: str | None) -> str | None:
    category = str(category_label or "").strip()
    subcategory = str(subcategory_label or "").strip()
    group_key = PROMPT_DECOMPOSITION_CATEGORY_TO_GROUP.get(category)
    if not group_key:
        return None
    if group_key == "scene" and subcategory in PROMPT_DECOMPOSITION_ITEM_SUBCATEGORIES:
        return "items"
    if group_key == "adult_theme" and subcategory in PROMPT_DECOMPOSITION_ITEM_SUBCATEGORIES:
        return "items"
    return group_key


def prompt_decomposition_subgroup_label(
    group_key: str,
    category_label: str | None,
    subcategory_label: str | None,
) -> str:
    raw_subcategory = str(subcategory_label or "").strip()
    if raw_subcategory:
        return PROMPT_DECOMPOSITION_SUBGROUP_LABEL_OVERRIDES.get((group_key, raw_subcategory), raw_subcategory)
    category = str(category_label or "").strip()
    if category:
        return PROMPT_DECOMPOSITION_GROUP_DEFINITIONS[group_key]["label"]
    return "未细分"


def build_prompt_decomposition_token_metadata(
    custom_terms: Iterable[Any],
    alias_rules: Iterable[Any],
) -> dict[str, PromptDecompositionTokenMetadata]:
    metadata: dict[str, PromptDecompositionTokenMetadata] = {}

    def register(token_value: str, category_label: str | None, subcategory_label: str | None) -> None:
        token = str(token_value or "").strip()
        if not token:
            return
        group_key = prompt_decomposition_group_key(category_label, subcategory_label)
        if not group_key:
            return
        if token in metadata:
            return
        group_label = str(PROMPT_DECOMPOSITION_GROUP_DEFINITIONS[group_key]["label"])
        subgroup_label = prompt_decomposition_subgroup_label(group_key, category_label, subcategory_label)
        subgroup_key = subgroup_label.casefold()
        metadata[token] = PromptDecompositionTokenMetadata(
            token=token,
            group_key=group_key,
            group_label=group_label,
            subgroup_key=subgroup_key,
            subgroup_label=subgroup_label,
            category_label=str(category_label or "").strip(),
            subcategory_label=str(subcategory_label or "").strip(),
        )

    for row in alias_rules:
        register(
            str(_record_get(row, "representative_token", "") or ""),
            str(_record_get(row, "category_label", "") or ""),
            str(_record_get(row, "subcategory_label", "") or ""),
        )
    for row in custom_terms:
        register(
            str(_record_get(row, "term", "") or ""),
            str(_record_get(row, "category_label", "") or ""),
            str(_record_get(row, "subcategory_label", "") or ""),
        )
    return metadata


def prompt_decomposition_grouped_tokens(
    tokens: Iterable[str],
    metadata: dict[str, PromptDecompositionTokenMetadata],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    subgroup_tokens: dict[tuple[str, str], list[str]] = {}
    for raw_token in tokens:
        token = str(raw_token or "").strip()
        token_meta = metadata.get(token)
        if token_meta is None:
            continue
        group = grouped.setdefault(
            token_meta.group_key,
            {
                "group_key": token_meta.group_key,
                "label": token_meta.group_label,
                "order": PROMPT_DECOMPOSITION_GROUP_DEFINITIONS[token_meta.group_key]["order"],
                "subgroups": [],
            },
        )
        subgroup_id = (token_meta.group_key, token_meta.subgroup_key)
        values = subgroup_tokens.setdefault(subgroup_id, [])
        if token_meta.token not in values:
            values.append(token_meta.token)
        if not any(item["key"] == token_meta.subgroup_key for item in group["subgroups"]):
            group["subgroups"].append(
                {
                    "key": token_meta.subgroup_key,
                    "label": token_meta.subgroup_label,
                    "tokens": [],
                }
            )

    ordered_groups = sorted(grouped.values(), key=lambda item: (item["order"], item["label"]))
    for group in ordered_groups:
        for subgroup in group["subgroups"]:
            subgroup_id = (group["group_key"], subgroup["key"])
            subgroup["tokens"] = subgroup_tokens.get(subgroup_id, [])
        group["subgroups"].sort(key=lambda item: item["label"])
        group["tokens"] = [token for subgroup in group["subgroups"] for token in subgroup["tokens"]]
        group.pop("order", None)
    return ordered_groups


def prompt_decomposition_filter_groups(
    token_rows: Iterable[Any],
    metadata: dict[str, PromptDecompositionTokenMetadata],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in token_rows:
        token = str(_record_get(row, "token", "") or "").strip()
        token_meta = metadata.get(token)
        if token_meta is None:
            continue
        group = groups.setdefault(
            token_meta.group_key,
            {
                "key": token_meta.group_key,
                "label": token_meta.group_label,
                "note": PROMPT_DECOMPOSITION_GROUP_DEFINITIONS[token_meta.group_key]["note"],
                "order": PROMPT_DECOMPOSITION_GROUP_DEFINITIONS[token_meta.group_key]["order"],
                "subgroups": {},
                "token_count": 0,
                "prompt_sum": 0,
            },
        )
        subgroup = group["subgroups"].setdefault(
            token_meta.subgroup_key,
            {
                "key": token_meta.subgroup_key,
                "label": token_meta.subgroup_label,
                "tokens": [],
                "token_count": 0,
                "prompt_sum": 0,
            },
        )
        token_payload = {
            "token": token,
            "prompt_count": int(_record_get(row, "prompt_count", 0) or 0),
            "use_count": int(_record_get(row, "use_count", 0) or 0),
            "user_count": int(_record_get(row, "user_count", 0) or 0),
        }
        subgroup["tokens"].append(token_payload)
        subgroup["token_count"] += 1
        subgroup["prompt_sum"] += token_payload["prompt_count"]
        group["token_count"] += 1
        group["prompt_sum"] += token_payload["prompt_count"]

    result: list[dict[str, Any]] = []
    for group in sorted(groups.values(), key=lambda item: (item["order"], item["label"])):
        subgroups = list(group["subgroups"].values())
        for subgroup in subgroups:
            subgroup["tokens"].sort(key=lambda item: (-item["prompt_count"], item["token"]))
        subgroups.sort(key=lambda item: (-item["prompt_sum"], item["label"]))
        result.append(
            {
                "key": group["key"],
                "label": group["label"],
                "note": group["note"],
                "token_count": group["token_count"],
                "prompt_sum": group["prompt_sum"],
                "subgroups": subgroups,
            }
        )
    return result


def normalize_prompt_decomposition_selected_tokens(
    value: str | Iterable[str] | None,
    *,
    max_items: int = PROMPT_DECOMPOSITION_MAX_SELECTED_TOKENS,
) -> list[str]:
    if value is None:
        return []
    raw_items: list[str]
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = []
        for item in value:
            raw_items.extend(str(item or "").split(","))
    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
        if len(normalized) >= max_items:
            break
    return normalized


def dump_grouped_tokens_json(grouped_tokens: list[dict[str, Any]]) -> str:
    return json.dumps(grouped_tokens, ensure_ascii=False)


def _record_get(record: Any, key: str, default: Any = None) -> Any:
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(key, default)
    getter = getattr(record, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            try:
                return getter(key)
            except Exception:
                return default
    try:
        return record[key]
    except Exception:
        return default
