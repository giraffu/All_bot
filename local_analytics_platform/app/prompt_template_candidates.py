from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from .prompt_mart import PROMPT_NORMALIZATION_VERSION
from .prompt_vectors import (
    PROMPT_TOKEN_ALL_TASK,
    PROMPT_TOKEN_MODEL_SCOPE_PREFIX,
    PROMPT_TOKEN_VERSION,
    prompt_token_stat_scope_metadata,
)


PROMPT_TEMPLATE_VERSION = "template-v1-token-slots"
PROMPT_TEMPLATE_BATCH_SIZE = 5000
PROMPT_TEMPLATE_MIN_TOKEN_PROMPT_COUNT = 20
PROMPT_TEMPLATE_MIN_MATERIALIZED_PROMPTS = 5
PROMPT_TEMPLATE_DETAIL_TOKEN_LIMIT = 24
PROMPT_TEMPLATE_KEY_TOKEN_LIMIT = 18
PROMPT_TEMPLATE_EDIT_DEFAULT_SLOT = "task_intent"
PROMPT_TEMPLATE_SIMILARITY_MAX_PAIRS = 12_000
PROMPT_TEMPLATE_SIMILARITY_BUCKETS = ("高度相似", "较相似", "中等相似", "差异较大")
PROMPT_TEMPLATE_SIMILARITY_PUNCT_RE = re.compile(
    r"[\s\u3000\t\r\n`~!@#$%^&*()_+\-=\[\]{};:'\",.<>/?\\|，。！？、；：‘’“”（）【】《》]+"
)

PROMPT_TEMPLATE_SLOT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "task_intent": {"label": "任务意图", "order": 0},
    "preserve": {"label": "保持口径", "order": 10},
    "subject": {"label": "主体人物", "order": 20},
    "body_part": {"label": "身体部分", "order": 30},
    "pose_action": {"label": "动作姿势", "order": 40},
    "adult_theme": {"label": "成人主题", "order": 50},
    "clothing": {"label": "服饰配件", "order": 70},
    "scene": {"label": "场景", "order": 80},
    "composition": {"label": "镜头构图", "order": 90},
    "style_quality": {"label": "风格质量", "order": 100},
    "expression": {"label": "表情情绪", "order": 110},
}

PROMPT_TEMPLATE_CATEGORY_TO_SLOT = {
    "保持口径": "preserve",
    "人物主体": "subject",
    "姿势动作": "pose_action",
    "动作姿势": "pose_action",
    "成人动作": "pose_action",
    "成人解剖": "body_part",
    "身体部位": "body_part",
    "身体部分": "body_part",
    "身体/镜头": "body_part",
    "服饰配件": "clothing",
    "场景": "scene",
    "场景环境": "scene",
    "场景物体": "scene",
    "镜头构图": "composition",
    "风格质量": "style_quality",
    "表情情绪": "expression",
    "表情状态": "expression",
    "成人主题": "adult_theme",
    "成人角色": "adult_theme",
}

PROMPT_TEMPLATE_SLOT_TOKEN_LIMITS = {
    "task_intent": 3,
    "preserve": 2,
    "subject": 2,
    "body_part": 5,
    "pose_action": 3,
    "adult_theme": 4,
    "clothing": 3,
    "scene": 3,
    "composition": 3,
    "style_quality": 3,
    "expression": 2,
}

PROMPT_TEMPLATE_EDIT_TASKS = {"edit", "edit_v2"}
PROMPT_TEMPLATE_EDIT_DEFAULT_TOKENS = ("P图", "主体人物", "人物一致")

PROMPT_TEMPLATE_SCHEMA_SQL = (
    """
    create table if not exists analytics_prompt_template_candidates (
        template_version text not null,
        template_key text not null,
        normalization_version text not null,
        token_version text not null,
        scope_key text not null,
        scope_kind text not null,
        scope_label text not null default '',
        parent_task_type text,
        model_key text,
        model_label text,
        template_title text not null default '',
        token_slots jsonb not null default '{}'::jsonb,
        slot_signature text not null default '',
        tokens text[] not null default '{}',
        prompt_count bigint not null default 0,
        use_count bigint not null default 0,
        user_count bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        similarity_bucket text not null default '',
        similarity_score numeric(20, 4) not null default 0,
        similarity_metrics jsonb not null default '{}'::jsonb,
        latest_prompt_at timestamptz,
        refreshed_at timestamptz not null default now(),
        primary key (template_version, template_key)
    )
    """,
    "alter table analytics_prompt_template_candidates add column if not exists similarity_bucket text not null default ''",
    "alter table analytics_prompt_template_candidates add column if not exists similarity_score numeric(20, 4) not null default 0",
    "alter table analytics_prompt_template_candidates add column if not exists similarity_metrics jsonb not null default '{}'::jsonb",
    """
    create table if not exists analytics_prompt_template_candidate_prompts (
        template_version text not null,
        template_key text not null,
        prompt_hash text not null,
        normalization_version text not null,
        token_version text not null,
        scope_key text not null,
        prompt text not null default '',
        tokens text[] not null default '{}',
        token_slots jsonb not null default '{}'::jsonb,
        task_types text[] not null default '{}',
        scopes text[] not null default '{}',
        uses bigint not null default 0,
        users bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        last_seen timestamptz,
        rank integer not null default 0,
        refreshed_at timestamptz not null default now(),
        primary key (template_version, template_key, prompt_hash)
    )
    """,
    """
    create table if not exists analytics_prompt_template_candidate_review_marks (
        template_version text not null,
        template_key text not null,
        prompt_hash text not null,
        scope_key text not null default '',
        prompt text not null default '',
        tokens text[] not null default '{}',
        token_slots jsonb not null default '{}'::jsonb,
        task_types text[] not null default '{}',
        scopes text[] not null default '{}',
        uses bigint not null default 0,
        users bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        last_seen timestamptz,
        review_processed boolean not null default false,
        review_processed_at timestamptz,
        marked_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        primary key (template_version, template_key, prompt_hash)
    )
    """,
    "alter table analytics_prompt_template_candidate_review_marks add column if not exists review_processed boolean not null default false",
    "alter table analytics_prompt_template_candidate_review_marks add column if not exists review_processed_at timestamptz",
    """
    create table if not exists analytics_prompt_template_candidate_template_review_marks (
        template_version text not null,
        template_key text not null,
        low_quality boolean not null default false,
        low_quality_marked_at timestamptz,
        updated_at timestamptz not null default now(),
        primary key (template_version, template_key)
    )
    """,
    "alter table analytics_prompt_template_candidate_template_review_marks add column if not exists low_quality boolean not null default false",
    "alter table analytics_prompt_template_candidate_template_review_marks add column if not exists low_quality_marked_at timestamptz",
    "alter table analytics_prompt_template_candidate_template_review_marks add column if not exists updated_at timestamptz not null default now()",
    """
    create table if not exists analytics_prompt_template_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    (
        "create index if not exists idx_prompt_template_candidates_scope_score "
        "on analytics_prompt_template_candidates(template_version, scope_key, prompt_count desc, quality_score desc)"
    ),
    (
        "create index if not exists idx_prompt_template_candidates_similarity "
        "on analytics_prompt_template_candidates(template_version, scope_key, similarity_bucket, prompt_count desc)"
    ),
    (
        "create index if not exists idx_prompt_template_candidates_model "
        "on analytics_prompt_template_candidates(template_version, parent_task_type, model_key, prompt_count desc)"
    ),
    (
        "create index if not exists idx_prompt_template_prompts_rank "
        "on analytics_prompt_template_candidate_prompts(template_version, template_key, rank)"
    ),
    (
        "create index if not exists idx_prompt_template_review_marks_template "
        "on analytics_prompt_template_candidate_review_marks(template_version, template_key, updated_at desc)"
    ),
    (
        "create index if not exists idx_prompt_template_review_marks_processed "
        "on analytics_prompt_template_candidate_review_marks(template_version, review_processed, marked_at desc)"
    ),
    (
        "create index if not exists idx_prompt_template_template_review_low_quality "
        "on analytics_prompt_template_candidate_template_review_marks(template_version, low_quality, updated_at desc)"
    ),
)


@dataclass(frozen=True)
class PromptTemplateTokenMetadata:
    token: str
    slot_key: str
    slot_label: str


@dataclass
class PromptTemplateAggregate:
    template_key: str
    scope_key: str
    scope_kind: str
    scope_label: str
    parent_task_type: str | None
    model_key: str | None
    model_label: str | None
    token_slots: dict[str, list[str]]
    slot_signature: str
    tokens: list[str]
    prompt_count: int = 0
    use_count: int = 0
    user_count: int = 0
    quality_total: float = 0.0
    latest_prompt_at: Any | None = None
    prompt_texts: list[str] = field(default_factory=list)
    prompt_token_sets: list[set[str]] = field(default_factory=list)
    similarity_bucket: str = ""
    similarity_score: float = 0.0
    similarity_metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def quality_score(self) -> float:
        if self.prompt_count <= 0:
            return 0.0
        signal = math.log1p(self.use_count) * 1.5 + math.log1p(self.user_count)
        return round((self.quality_total / self.prompt_count) + signal, 2)


def prompt_template_state_key(key: str) -> str:
    return f"{PROMPT_TEMPLATE_VERSION}:{PROMPT_NORMALIZATION_VERSION}:{PROMPT_TOKEN_VERSION}:{key}"


async def ensure_prompt_template_candidate_schema(conn: Any) -> None:
    for statement in PROMPT_TEMPLATE_SCHEMA_SQL:
        await conn.execute(statement)


def prompt_template_slot_key(category_label: str | None) -> str | None:
    return PROMPT_TEMPLATE_CATEGORY_TO_SLOT.get((category_label or "").strip())


def build_prompt_template_token_metadata(
    custom_terms: Iterable[Any],
    alias_rules: Iterable[Any],
) -> dict[str, PromptTemplateTokenMetadata]:
    metadata: dict[str, PromptTemplateTokenMetadata] = {}
    for row in custom_terms:
        token = str(_record_get(row, "term", "") or "").strip()
        slot_key = prompt_template_slot_key(str(_record_get(row, "category_label", "") or ""))
        if not token or not slot_key:
            continue
        metadata[token] = PromptTemplateTokenMetadata(
            token=token,
            slot_key=slot_key,
            slot_label=PROMPT_TEMPLATE_SLOT_DEFINITIONS[slot_key]["label"],
        )
    for row in alias_rules:
        token = str(_record_get(row, "representative_token", "") or "").strip()
        slot_key = prompt_template_slot_key(str(_record_get(row, "category_label", "") or ""))
        if not token or not slot_key:
            continue
        metadata[token] = PromptTemplateTokenMetadata(
            token=token,
            slot_key=slot_key,
            slot_label=PROMPT_TEMPLATE_SLOT_DEFINITIONS[slot_key]["label"],
        )
    return metadata


def prompt_template_slots_from_tokens(
    tokens: Iterable[str],
    token_metadata: dict[str, PromptTemplateTokenMetadata],
    *,
    scope_key: str,
) -> dict[str, list[str]]:
    slots: dict[str, list[str]] = {}
    task_scope = scope_key
    if scope_key.startswith(PROMPT_TOKEN_MODEL_SCOPE_PREFIX):
        parts = scope_key.split("|", 2)
        task_scope = parts[1] if len(parts) >= 2 else scope_key
    if task_scope in PROMPT_TEMPLATE_EDIT_TASKS:
        slots[PROMPT_TEMPLATE_EDIT_DEFAULT_SLOT] = list(PROMPT_TEMPLATE_EDIT_DEFAULT_TOKENS)

    seen_by_slot: dict[str, set[str]] = defaultdict(set)
    for token in tokens:
        metadata = token_metadata.get(str(token))
        if metadata is None:
            continue
        seen = seen_by_slot[metadata.slot_key]
        if metadata.token in seen:
            continue
        limit = PROMPT_TEMPLATE_SLOT_TOKEN_LIMITS.get(metadata.slot_key, 2)
        if len(seen) >= limit:
            continue
        seen.add(metadata.token)
        slots.setdefault(metadata.slot_key, []).append(metadata.token)
    return order_prompt_template_slots(slots)


def order_prompt_template_slots(slots: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        key: slots[key]
        for key in sorted(
            slots,
            key=lambda value: (
                PROMPT_TEMPLATE_SLOT_DEFINITIONS.get(value, {}).get("order", 10_000),
                value,
            ),
        )
    }


def prompt_template_groupable_slots(slots: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        key: values
        for key, values in slots.items()
        if key != PROMPT_TEMPLATE_EDIT_DEFAULT_SLOT and values
    }


def prompt_template_slot_signature(slots: dict[str, list[str]]) -> str:
    parts = []
    for slot_key, values in order_prompt_template_slots(slots).items():
        if not values:
            continue
        clean_values = sorted(dict.fromkeys(str(value) for value in values if value))
        if clean_values:
            parts.append(f"{slot_key}:{'|'.join(clean_values)}")
    return ";".join(parts)


def prompt_template_key(scope_key: str, slots: dict[str, list[str]]) -> str:
    signature = prompt_template_slot_signature(prompt_template_groupable_slots(slots))
    digest = hashlib.sha1(f"{scope_key}\n{signature}".encode("utf-8")).hexdigest()[:24]
    return f"tmpl_{digest}"


def prompt_template_title(scope_label: str, slots: dict[str, list[str]]) -> str:
    chunks: list[str] = []
    for slot_key, values in order_prompt_template_slots(slots).items():
        if slot_key == PROMPT_TEMPLATE_EDIT_DEFAULT_SLOT:
            continue
        slot_label = PROMPT_TEMPLATE_SLOT_DEFINITIONS.get(slot_key, {}).get("label", slot_key)
        if values:
            chunks.append(f"{slot_label}: {'/'.join(values[:3])}")
        if len(chunks) >= 4:
            break
    suffix = "；".join(chunks) if chunks else "通用提示词组合"
    return f"{scope_label} · {suffix}"


def _normalize_similarity_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return PROMPT_TEMPLATE_SIMILARITY_PUNCT_RE.sub("", normalized)


def _prompt_text_shingles(value: str | None, *, size: int = 3) -> set[str]:
    normalized = _normalize_similarity_text(value)
    if not normalized:
        return set()
    if len(normalized) <= size:
        return {normalized}
    return {normalized[index : index + size] for index in range(len(normalized) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if intersection <= 0:
        return 0.0
    return intersection / len(left | right)


def _average_pairwise_jaccard(sets: list[set[str]], *, seed: int) -> tuple[float, int]:
    count = len(sets)
    if count < 2:
        return 1.0, 0
    total_pairs = count * (count - 1) // 2
    if total_pairs <= PROMPT_TEMPLATE_SIMILARITY_MAX_PAIRS:
        total = 0.0
        sampled = 0
        for left_index in range(count):
            left = sets[left_index]
            for right_index in range(left_index + 1, count):
                total += _jaccard(left, sets[right_index])
                sampled += 1
        return (total / sampled if sampled else 0.0), sampled

    rng = random.Random(seed + count)
    seen: set[tuple[int, int]] = set()
    total = 0.0
    sampled = 0
    while sampled < PROMPT_TEMPLATE_SIMILARITY_MAX_PAIRS:
        left_index = rng.randrange(count)
        right_index = rng.randrange(count)
        if left_index == right_index:
            continue
        if left_index > right_index:
            left_index, right_index = right_index, left_index
        pair = (left_index, right_index)
        if pair in seen:
            continue
        seen.add(pair)
        total += _jaccard(sets[left_index], sets[right_index])
        sampled += 1
    return total / sampled, sampled


def prompt_template_similarity_bucket(
    cohesion_score: float,
    *,
    avg_text_jaccard: float = 1.0,
    avg_extra_token_jaccard: float = 1.0,
    unique_prompt_ratio: float = 0.0,
    slot_token_count: int = 10,
) -> str:
    if cohesion_score >= 0.52:
        bucket = "高度相似"
    elif cohesion_score >= 0.38:
        bucket = "较相似"
    elif cohesion_score >= 0.28:
        bucket = "中等相似"
    else:
        bucket = "差异较大"
    if bucket != "差异较大" and avg_text_jaccard < 0.18 and avg_extra_token_jaccard < 0.12 and unique_prompt_ratio > 0.85:
        return "差异较大"
    if bucket == "中等相似" and avg_text_jaccard < 0.16 and avg_extra_token_jaccard < 0.10 and slot_token_count <= 6:
        return "差异较大"
    return bucket


def prompt_template_similarity_for_values(
    prompt_texts: Iterable[str],
    prompt_token_sets: Iterable[set[str]],
    template_tokens: Iterable[str],
) -> tuple[str, float, dict[str, Any]]:
    texts = [str(value or "") for value in prompt_texts]
    token_sets = [set(str(token) for token in token_set if str(token)) for token_set in prompt_token_sets]
    if not token_sets:
        token_sets = [set()]
    normalized_texts = [_normalize_similarity_text(value) for value in texts]
    text_counter = Counter(normalized_texts)
    unique_prompt_ratio = (len(text_counter) / len(normalized_texts)) if normalized_texts else 0.0
    top_text_share = (text_counter.most_common(1)[0][1] / len(normalized_texts)) if normalized_texts else 0.0
    text_sets = [_prompt_text_shingles(value) for value in texts]
    template_token_set = {str(token) for token in template_tokens if str(token)}
    fixed_token_set = template_token_set | set(PROMPT_TEMPLATE_EDIT_DEFAULT_TOKENS)
    extra_token_sets = [token_set - fixed_token_set for token_set in token_sets]

    avg_text, sampled_pairs = _average_pairwise_jaccard(text_sets, seed=20260710)
    avg_token, _ = _average_pairwise_jaccard(token_sets, seed=20260711)
    avg_extra, _ = _average_pairwise_jaccard(extra_token_sets, seed=20260712)
    slot_token_count = len([token for token in template_token_set if token not in PROMPT_TEMPLATE_EDIT_DEFAULT_TOKENS])
    extra_union = set().union(*extra_token_sets) if extra_token_sets else set()
    extra_intersection = set(extra_token_sets[0]) if extra_token_sets else set()
    for token_set in extra_token_sets[1:]:
        extra_intersection &= token_set
    avg_extra_tokens = (sum(len(token_set) for token_set in extra_token_sets) / len(extra_token_sets)) if extra_token_sets else 0.0
    top_extra_counter: Counter[str] = Counter()
    for token_set in extra_token_sets:
        top_extra_counter.update(token_set)
    top_extra = [
        {"token": token, "count": count, "coverage": round(count / len(extra_token_sets), 4)}
        for token, count in top_extra_counter.most_common(8)
    ] if extra_token_sets else []
    cohesion_score = 0.42 * avg_text + 0.34 * avg_token + 0.14 * avg_extra + 0.10 * top_text_share
    bucket = prompt_template_similarity_bucket(
        cohesion_score,
        avg_text_jaccard=avg_text,
        avg_extra_token_jaccard=avg_extra,
        unique_prompt_ratio=unique_prompt_ratio,
        slot_token_count=slot_token_count,
    )
    metrics = {
        "prompt_count": len(texts),
        "slot_token_count": slot_token_count,
        "unique_prompt_ratio": round(unique_prompt_ratio, 4),
        "top_text_share": round(top_text_share, 4),
        "avg_text_jaccard": round(avg_text, 4),
        "avg_token_jaccard": round(avg_token, 4),
        "avg_extra_token_jaccard": round(avg_extra, 4),
        "extra_union_count": len(extra_union),
        "extra_intersection_count": len(extra_intersection),
        "avg_extra_tokens_per_prompt": round(avg_extra_tokens, 4),
        "top_extra_tokens": top_extra,
        "sampled_pair_count": sampled_pairs,
    }
    return bucket, round(cohesion_score, 4), metrics


def prompt_template_similarity_for_prompt_rows(rows: Iterable[Any], template_tokens: Iterable[str]) -> tuple[str, float, dict[str, Any]]:
    records = list(rows)
    return prompt_template_similarity_for_values(
        [str(_record_get(row, "prompt", "") or "") for row in records],
        [set(_normalize_prompt_row_tokens(row)) for row in records],
        template_tokens,
    )


def apply_prompt_template_similarity(aggregate: PromptTemplateAggregate) -> None:
    bucket, score, metrics = prompt_template_similarity_for_values(
        aggregate.prompt_texts,
        aggregate.prompt_token_sets,
        aggregate.tokens,
    )
    aggregate.similarity_bucket = bucket
    aggregate.similarity_score = score
    aggregate.similarity_metrics = metrics


async def fetch_prompt_template_token_metadata(conn: Any) -> dict[str, PromptTemplateTokenMetadata]:
    custom_terms = await conn.fetch(
        """
        select term, category_label
        from analytics_prompt_token_custom_terms
        where enabled is true
        """
    )
    alias_rules = await conn.fetch(
        """
        select representative_token, category_label
        from analytics_prompt_token_alias_rules
        where enabled is true
        """
    )
    deleted_tokens = {
        str(row["token"])
        for row in await conn.fetch("select token from analytics_prompt_token_deleted_rules")
    }
    allowed_tokens = {
        str(row["token"])
        for row in await conn.fetch(
            """
            select token
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
              and scope_kind = 'all'
              and prompt_count >= $4::bigint
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            PROMPT_TOKEN_ALL_TASK,
            PROMPT_TEMPLATE_MIN_TOKEN_PROMPT_COUNT,
        )
    }
    metadata = build_prompt_template_token_metadata(custom_terms, alias_rules)
    return {
        token: item
        for token, item in metadata.items()
        if token not in deleted_tokens and token in allowed_tokens
    }


async def _insert_records(conn: Any, table_name: str, columns: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    copy_records = getattr(conn, "copy_records_to_table", None)
    if copy_records is not None:
        await copy_records(table_name, records=rows, columns=columns)
        return
    placeholders = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
    await conn.executemany(
        f"insert into {table_name} ({', '.join(columns)}) values ({placeholders})",
        rows,
    )


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _record_get(record: Any, key: str, default: Any = None) -> Any:
    getter = getattr(record, "get", None)
    if getter is not None:
        return getter(key, default)
    try:
        return record[key]
    except (KeyError, TypeError):
        return default


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _scope_metric(metrics: Any, scope_key: str, fallback: Any) -> int:
    value = _json_object(metrics).get(scope_key, fallback)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(fallback or 0)


def _scope_metadata(scope_key: str) -> tuple[str, str, str | None, str | None, str | None]:
    return prompt_token_stat_scope_metadata(scope_key)


def _prompt_row_quality(row: Any) -> float:
    value = _record_get(row, "quality_score", 0) or 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_prompt_row_tokens(row: Any) -> list[str]:
    return [str(value) for value in (_record_get(row, "tokens", []) or []) if str(value)]


def _template_prompt_row(
    row: Any,
    *,
    template_key: str,
    scope_key: str,
    slots: dict[str, list[str]],
    rank: int,
) -> tuple[Any, ...]:
    uses = _scope_metric(_record_get(row, "scope_uses", {}), scope_key, _record_get(row, "uses", 0))
    users = _scope_metric(_record_get(row, "scope_users", {}), scope_key, _record_get(row, "users", 0))
    return (
        PROMPT_TEMPLATE_VERSION,
        template_key,
        str(_record_get(row, "prompt_hash", "")),
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
        scope_key,
        str(_record_get(row, "prompt", "") or ""),
        _normalize_prompt_row_tokens(row)[:PROMPT_TEMPLATE_DETAIL_TOKEN_LIMIT],
        json.dumps(slots, ensure_ascii=False),
        list(_record_get(row, "task_types", []) or []),
        list(_record_get(row, "scopes", []) or []),
        uses,
        users,
        Decimal(str(round(_prompt_row_quality(row), 2))),
        _record_get(row, "last_seen"),
        rank,
        datetime.now(timezone.utc),
    )


def _candidate_row(aggregate: PromptTemplateAggregate) -> tuple[Any, ...]:
    return (
        PROMPT_TEMPLATE_VERSION,
        aggregate.template_key,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
        aggregate.scope_key,
        aggregate.scope_kind,
        aggregate.scope_label,
        aggregate.parent_task_type,
        aggregate.model_key,
        aggregate.model_label,
        prompt_template_title(aggregate.scope_label, aggregate.token_slots),
        json.dumps(aggregate.token_slots, ensure_ascii=False),
        aggregate.slot_signature,
        aggregate.tokens[:PROMPT_TEMPLATE_KEY_TOKEN_LIMIT],
        aggregate.prompt_count,
        aggregate.use_count,
        aggregate.user_count,
        Decimal(str(aggregate.quality_score)),
        aggregate.similarity_bucket,
        Decimal(str(aggregate.similarity_score)),
        json.dumps(aggregate.similarity_metrics, ensure_ascii=False),
        aggregate.latest_prompt_at,
        datetime.now(timezone.utc),
    )


async def refresh_prompt_template_candidates(
    conn: Any,
    *,
    batch_size: int = PROMPT_TEMPLATE_BATCH_SIZE,
) -> dict[str, Any]:
    started = time.monotonic()
    await ensure_prompt_template_candidate_schema(conn)
    metadata = await fetch_prompt_template_token_metadata(conn)
    aggregates: dict[str, PromptTemplateAggregate] = {}
    scanned = 0
    matched = 0
    last_prompt_hash = ""

    while True:
        rows = await conn.fetch(
            """
            select
                prompt_hash,
                prompt,
                tokens,
                task_types,
                scopes,
                scope_uses,
                scope_users,
                uses,
                users,
                quality_score,
                last_seen
            from analytics_prompt_token_prompts
            where normalization_version = $1::text
              and token_version = $2::text
              and prompt_hash > $3::text
            order by prompt_hash
            limit $4::int
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            last_prompt_hash,
            max(1, int(batch_size)),
        )
        if not rows:
            break
        for row in rows:
            scanned += 1
            last_prompt_hash = str(row["prompt_hash"])
            tokens = _normalize_prompt_row_tokens(row)
            scopes = [str(value) for value in (row["scopes"] or []) if str(value) and str(value) != PROMPT_TOKEN_ALL_TASK]
            if not scopes:
                continue
            for scope_key in scopes:
                slots = prompt_template_slots_from_tokens(tokens, metadata, scope_key=scope_key)
                groupable_slots = prompt_template_groupable_slots(slots)
                if len(groupable_slots) < 2:
                    continue
                key = prompt_template_key(scope_key, slots)
                aggregate = aggregates.get(key)
                if aggregate is None:
                    scope_kind, scope_label, parent_task_type, model_key, model_label = _scope_metadata(scope_key)
                    signature = prompt_template_slot_signature(groupable_slots)
                    aggregate = PromptTemplateAggregate(
                        template_key=key,
                        scope_key=scope_key,
                        scope_kind=scope_kind,
                        scope_label=scope_label,
                        parent_task_type=parent_task_type,
                        model_key=model_key,
                        model_label=model_label,
                        token_slots=slots,
                        slot_signature=signature,
                        tokens=[token for values in slots.values() for token in values],
                    )
                    aggregates[key] = aggregate
                uses = _scope_metric(row["scope_uses"], scope_key, row["uses"])
                users = _scope_metric(row["scope_users"], scope_key, row["users"])
                aggregate.prompt_count += 1
                aggregate.use_count += uses
                aggregate.user_count += users
                aggregate.quality_total += _prompt_row_quality(row)
                aggregate.prompt_texts.append(str(_record_get(row, "prompt", "") or ""))
                aggregate.prompt_token_sets.append(set(tokens))
                last_seen = row["last_seen"]
                if last_seen is not None and (
                    aggregate.latest_prompt_at is None or last_seen > aggregate.latest_prompt_at
                ):
                    aggregate.latest_prompt_at = last_seen
                matched += 1

    kept = [
        aggregate
        for aggregate in aggregates.values()
        if aggregate.prompt_count >= PROMPT_TEMPLATE_MIN_MATERIALIZED_PROMPTS
    ]
    for aggregate in kept:
        apply_prompt_template_similarity(aggregate)
    kept.sort(key=lambda item: (item.prompt_count, item.quality_score, item.use_count), reverse=True)

    async with conn.transaction():
        await conn.execute("delete from analytics_prompt_template_candidate_prompts where template_version = $1", PROMPT_TEMPLATE_VERSION)
        await conn.execute("delete from analytics_prompt_template_candidates where template_version = $1", PROMPT_TEMPLATE_VERSION)

        candidate_rows = [_candidate_row(aggregate) for aggregate in kept]
        await _insert_records(
            conn,
            "analytics_prompt_template_candidates",
            (
                "template_version",
                "template_key",
                "normalization_version",
                "token_version",
                "scope_key",
                "scope_kind",
                "scope_label",
                "parent_task_type",
                "model_key",
                "model_label",
                "template_title",
                "token_slots",
                "slot_signature",
                "tokens",
                "prompt_count",
                "use_count",
                "user_count",
                "quality_score",
                "similarity_bucket",
                "similarity_score",
                "similarity_metrics",
                "latest_prompt_at",
                "refreshed_at",
            ),
            candidate_rows,
        )

        kept_keys = {aggregate.template_key for aggregate in kept}
        detail_last_prompt_hash = ""
        prompt_rows: list[tuple[Any, ...]] = []
        while kept_keys:
            rows = await conn.fetch(
                """
                select
                    prompt_hash,
                    prompt,
                    tokens,
                    task_types,
                    scopes,
                    scope_uses,
                    scope_users,
                    uses,
                    users,
                    quality_score,
                    last_seen
                from analytics_prompt_token_prompts
                where normalization_version = $1::text
                  and token_version = $2::text
                  and prompt_hash > $3::text
                order by prompt_hash
                limit $4::int
                """,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_TOKEN_VERSION,
                detail_last_prompt_hash,
                max(1, int(batch_size)),
            )
            if not rows:
                break
            for row in rows:
                detail_last_prompt_hash = str(row["prompt_hash"])
                tokens = _normalize_prompt_row_tokens(row)
                scopes = [
                    str(value)
                    for value in (row["scopes"] or [])
                    if str(value) and str(value) != PROMPT_TOKEN_ALL_TASK
                ]
                for scope_key in scopes:
                    slots = prompt_template_slots_from_tokens(tokens, metadata, scope_key=scope_key)
                    groupable_slots = prompt_template_groupable_slots(slots)
                    if len(groupable_slots) < 2:
                        continue
                    template_key = prompt_template_key(scope_key, slots)
                    if template_key not in kept_keys:
                        continue
                    prompt_rows.append(
                        _template_prompt_row(
                            row,
                            template_key=template_key,
                            scope_key=scope_key,
                            slots=slots,
                            rank=0,
                        )
                    )
                    if len(prompt_rows) >= 20_000:
                        await _insert_records(
                            conn,
                            "analytics_prompt_template_candidate_prompts",
                            PROMPT_TEMPLATE_PROMPT_COLUMNS,
                            prompt_rows,
                        )
                        prompt_rows = []
            if prompt_rows:
                await _insert_records(
                    conn,
                    "analytics_prompt_template_candidate_prompts",
                    PROMPT_TEMPLATE_PROMPT_COLUMNS,
                    prompt_rows,
                )
                prompt_rows = []

        await conn.execute(
            """
            update analytics_prompt_template_candidate_prompts target
            set rank = ranked.rank
            from (
                select
                    template_version,
                    template_key,
                    prompt_hash,
                    row_number() over (
                        partition by template_version, template_key
                        order by quality_score desc, uses desc, users desc, prompt_hash desc
                    ) as rank
                from analytics_prompt_template_candidate_prompts
                where template_version = $1::text
            ) ranked
            where target.template_version = ranked.template_version
              and target.template_key = ranked.template_key
              and target.prompt_hash = ranked.prompt_hash
            """,
            PROMPT_TEMPLATE_VERSION,
        )
        await conn.execute(
            """
            delete from analytics_prompt_template_candidate_review_marks marks
            where marks.template_version = $1::text
              and not exists (
                  select 1
                  from analytics_prompt_template_candidate_prompts prompts
                  where prompts.template_version = marks.template_version
                    and prompts.template_key = marks.template_key
                    and prompts.prompt_hash = marks.prompt_hash
              )
            """,
            PROMPT_TEMPLATE_VERSION,
        )
        await conn.execute(
            """
            delete from analytics_prompt_template_candidate_template_review_marks marks
            where marks.template_version = $1::text
              and not exists (
                  select 1
                  from analytics_prompt_template_candidates candidate
                  where candidate.template_version = marks.template_version
                    and candidate.template_key = marks.template_key
              )
            """,
            PROMPT_TEMPLATE_VERSION,
        )

        state = {
            "template_count": len(kept),
            "prompt_links": sum(aggregate.prompt_count for aggregate in kept),
            "scanned_prompts": scanned,
            "matched_links": matched,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        }
        for key, value in state.items():
            await conn.execute(
                """
                insert into analytics_prompt_template_state (key, value, updated_at)
                values ($1::text, $2::text, now())
                on conflict (key) do update set value = excluded.value, updated_at = now()
                """,
                prompt_template_state_key(key),
                json.dumps(value, ensure_ascii=False, default=_json_default) if not isinstance(value, str) else value,
            )

    await conn.execute("analyze analytics_prompt_template_candidates")
    await conn.execute("analyze analytics_prompt_template_candidate_prompts")
    await conn.execute("analyze analytics_prompt_template_candidate_review_marks")
    await conn.execute("analyze analytics_prompt_template_candidate_template_review_marks")
    return {
        "template_version": PROMPT_TEMPLATE_VERSION,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "token_version": PROMPT_TOKEN_VERSION,
        "scanned_prompts": scanned,
        "matched_links": matched,
        "template_count": len(kept),
        "prompt_links": sum(aggregate.prompt_count for aggregate in kept),
        "seconds": round(time.monotonic() - started, 2),
    }


PROMPT_TEMPLATE_PROMPT_COLUMNS = (
    "template_version",
    "template_key",
    "prompt_hash",
    "normalization_version",
    "token_version",
    "scope_key",
    "prompt",
    "tokens",
    "token_slots",
    "task_types",
    "scopes",
    "uses",
    "users",
    "quality_score",
    "last_seen",
    "rank",
    "refreshed_at",
)


def prompt_template_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh prompt template candidates")
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    parser.add_argument("--batch-size", type=int, default=PROMPT_TEMPLATE_BATCH_SIZE)
    return parser
