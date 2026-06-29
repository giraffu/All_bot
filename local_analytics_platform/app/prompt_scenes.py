from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg
import numpy as np

from .prompt_mart import PROMPT_NORMALIZATION_VERSION
from .prompt_vectors import (
    DEFAULT_VECTOR_DATA_DIR,
    DEFAULT_VECTOR_MODEL_ID,
    DEFAULT_VECTOR_MODEL_KEY,
    EMBEDDING_DTYPE,
    embedding_from_bytes,
    embedding_to_bytes,
    prompt_hash_to_key,
)


PROMPT_SCENE_ALGORITHM_VERSION = "semantic-scenes-v1"
DEFAULT_TARGET_SCENE_COUNT = 1_000
DEFAULT_MAX_SCENES_PER_TASK = 220
DEFAULT_CANDIDATES_PER_SCENE = 30
DEFAULT_STRICT_SEED_MAX_SIMILARITY = 0.78
DEFAULT_RELAXED_SEED_MAX_SIMILARITY = 0.86
DEFAULT_SEED_RELAX_TRIGGER_RATIO = 0.80
DEFAULT_HIGH_CONFIDENCE_THRESHOLD = 0.70
DEFAULT_MEDIUM_CONFIDENCE_THRESHOLD = 0.55
DEFAULT_ASSIGNMENT_BATCH_SIZE = 2_048
DEFAULT_SEED_POOL_MULTIPLIER = 160
DEFAULT_MIN_SEED_POOL_SIZE = 5_000


CREATE_PROMPT_SCENE_SCHEMA_SQL = [
    """
    create table if not exists analytics_prompt_semantic_scene_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_semantic_scenes (
        scene_id text primary key,
        model_id text not null,
        normalization_version text not null,
        algorithm_version text not null,
        task_type text not null,
        representative_hash text not null,
        representative_prompt text not null,
        manual_label text,
        member_count bigint not null,
        candidate_count bigint not null,
        high_confidence_count bigint not null default 0,
        medium_confidence_count bigint not null default 0,
        low_confidence_count bigint not null default 0,
        min_similarity numeric(8, 6) not null,
        avg_similarity numeric(8, 6) not null,
        max_similarity numeric(8, 6) not null,
        total_uses bigint not null default 0,
        total_users bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        centroid_dim integer not null,
        centroid_dtype text not null default 'float16',
        centroid_f16 bytea not null,
        created_at timestamptz not null default now(),
        refreshed_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_semantic_scene_members (
        scene_id text not null,
        prompt_hash text not null,
        task_type text not null,
        similarity_to_scene numeric(8, 6) not null,
        confidence_band text not null,
        member_rank integer not null,
        candidate_rank integer,
        created_at timestamptz not null default now(),
        primary key (scene_id, prompt_hash),
        constraint chk_prompt_scene_confidence_band check (confidence_band in ('high', 'medium', 'low'))
    )
    """,
    "create index if not exists idx_prompt_semantic_scenes_task on analytics_prompt_semantic_scenes(model_id, normalization_version, task_type, member_count desc)",
    "create index if not exists idx_prompt_semantic_scenes_score on analytics_prompt_semantic_scenes(model_id, normalization_version, quality_score desc)",
    "create index if not exists idx_prompt_semantic_scene_members_scene on analytics_prompt_semantic_scene_members(scene_id, member_rank)",
    "create index if not exists idx_prompt_semantic_scene_members_prompt on analytics_prompt_semantic_scene_members(prompt_hash)",
    "create index if not exists idx_prompt_semantic_scene_members_confidence on analytics_prompt_semantic_scene_members(confidence_band, candidate_rank)",
    "alter table analytics_prompt_semantic_scenes add column if not exists manual_label text",
    "alter table analytics_prompt_semantic_scenes add column if not exists high_confidence_count bigint not null default 0",
    "alter table analytics_prompt_semantic_scenes add column if not exists medium_confidence_count bigint not null default 0",
    "alter table analytics_prompt_semantic_scenes add column if not exists low_confidence_count bigint not null default 0",
]


PROMPT_SCENE_READY_SQL = """
select
    to_regclass('public.analytics_prompt_semantic_scene_state') is not null
    and to_regclass('public.analytics_prompt_semantic_scenes') is not null
    and to_regclass('public.analytics_prompt_semantic_scene_members') is not null
    as ready
"""


@dataclass(frozen=True)
class PromptSceneConfig:
    model_id: str = DEFAULT_VECTOR_MODEL_ID
    model_key: str = DEFAULT_VECTOR_MODEL_KEY
    target_scene_count: int = DEFAULT_TARGET_SCENE_COUNT
    max_scenes_per_task: int = DEFAULT_MAX_SCENES_PER_TASK
    candidates_per_scene: int = DEFAULT_CANDIDATES_PER_SCENE
    strict_seed_max_similarity: float = DEFAULT_STRICT_SEED_MAX_SIMILARITY
    relaxed_seed_max_similarity: float = DEFAULT_RELAXED_SEED_MAX_SIMILARITY
    seed_relax_trigger_ratio: float = DEFAULT_SEED_RELAX_TRIGGER_RATIO
    high_confidence_threshold: float = DEFAULT_HIGH_CONFIDENCE_THRESHOLD
    medium_confidence_threshold: float = DEFAULT_MEDIUM_CONFIDENCE_THRESHOLD
    assignment_batch_size: int = DEFAULT_ASSIGNMENT_BATCH_SIZE
    seed_pool_multiplier: int = DEFAULT_SEED_POOL_MULTIPLIER
    min_seed_pool_size: int = DEFAULT_MIN_SEED_POOL_SIZE
    task_type: str | None = None
    data_dir: str = DEFAULT_VECTOR_DATA_DIR


@dataclass(frozen=True)
class ScenePrompt:
    prompt_hash: str
    task_type: str
    prompt: str
    quality_score: float
    uses: int
    users: int
    last_seen: datetime | None
    embedding: np.ndarray


@dataclass(frozen=True)
class SceneBuildResult:
    scene_rows: list[tuple[Any, ...]]
    member_rows: list[tuple[Any, ...]]


def _scene_state_key(model_id: str, normalization_version: str, key: str) -> str:
    return f"{model_id}:{normalization_version}:{PROMPT_SCENE_ALGORITHM_VERSION}:{key}"


async def ensure_prompt_scene_schema(conn: Any) -> None:
    for statement in CREATE_PROMPT_SCENE_SCHEMA_SQL:
        await conn.execute(statement)


async def set_scene_state(conn: Any, model_id: str, values: dict[str, Any]) -> None:
    for key, value in values.items():
        await conn.execute(
            """
            insert into analytics_prompt_semantic_scene_state (key, value, updated_at)
            values ($1::text, $2::text, now())
            on conflict (key) do update set value = excluded.value, updated_at = now()
            """,
            _scene_state_key(model_id, PROMPT_NORMALIZATION_VERSION, key),
            json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value,
        )


def allocate_scene_targets(
    task_counts: dict[str, int],
    *,
    target_total: int = DEFAULT_TARGET_SCENE_COUNT,
    max_per_task: int = DEFAULT_MAX_SCENES_PER_TASK,
) -> dict[str, int]:
    positive = {task: int(count) for task, count in task_counts.items() if int(count) > 0}
    if not positive:
        return {}
    caps = {task: max(1, min(max_per_task, count)) for task, count in positive.items()}
    total_cap = sum(caps.values())
    target_total = min(max(len(positive), int(target_total)), total_cap)
    weights = {task: math.sqrt(count) for task, count in positive.items()}
    targets = {task: 1 for task in positive}
    remaining = target_total - len(targets)
    while remaining > 0:
        open_tasks = [task for task, target in targets.items() if target < caps[task]]
        if not open_tasks:
            break
        weight_sum = sum(weights[task] for task in open_tasks)
        allocations: dict[str, int] = {}
        for task in open_tasks:
            share = weights[task] / weight_sum if weight_sum else 1 / len(open_tasks)
            allocations[task] = min(caps[task] - targets[task], max(0, int(math.floor(remaining * share))))
        if not any(allocations.values()):
            for task in sorted(open_tasks, key=lambda item: (-weights[item], item)):
                if remaining <= 0:
                    break
                targets[task] += 1
                remaining -= 1
            continue
        for task, amount in sorted(allocations.items()):
            if remaining <= 0:
                break
            amount = min(amount, remaining)
            targets[task] += amount
            remaining -= amount
    return targets


def _scene_id(model_id: str, task_type: str, seed_hash: str) -> str:
    raw = f"{model_id}\x1f{PROMPT_NORMALIZATION_VERSION}\x1f{PROMPT_SCENE_ALGORITHM_VERSION}\x1f{task_type}\x1f{seed_hash}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _scene_score(prompt: ScenePrompt) -> tuple[float, int, int, float, str]:
    last_seen_score = prompt.last_seen.timestamp() if isinstance(prompt.last_seen, datetime) else 0.0
    return (prompt.quality_score, prompt.uses, prompt.users, last_seen_score, prompt.prompt_hash)


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(left.astype(np.float32), right.astype(np.float32)))


def _confidence_band(similarity: float, config: PromptSceneConfig) -> str:
    if similarity >= config.high_confidence_threshold:
        return "high"
    if similarity >= config.medium_confidence_threshold:
        return "medium"
    return "low"


def _build_seed_index(dim: int):
    try:
        from usearch.index import Index
    except ImportError:
        return None
    return Index(ndim=dim, metric="cos", dtype="f16")


def _nearest_seed_similarity(
    prompt: ScenePrompt,
    seeds: list[ScenePrompt],
    seed_index: Any | None,
    key_to_seed: dict[int, ScenePrompt],
) -> float:
    if not seeds:
        return -1.0
    if seed_index is not None:
        matches = seed_index.search(prompt.embedding, count=1)
        match_keys = getattr(matches, "keys", matches[0] if isinstance(matches, tuple) else [])
        if len(match_keys):
            seed = key_to_seed.get(int(match_keys[0]))
            if seed is not None:
                return _cosine(prompt.embedding, seed.embedding)
    return max(_cosine(prompt.embedding, seed.embedding) for seed in seeds)


def _add_seed(
    seed: ScenePrompt,
    seeds: list[ScenePrompt],
    seed_index: Any | None,
    key_to_seed: dict[int, ScenePrompt],
) -> None:
    seeds.append(seed)
    if seed_index is not None:
        key = prompt_hash_to_key(seed.prompt_hash)
        key_to_seed[key] = seed
        seed_index.add(np.asarray([key], dtype=np.uint64), np.asarray([seed.embedding], dtype=np.float16))


def select_scene_seeds(
    prompts: list[ScenePrompt],
    target_count: int,
    config: PromptSceneConfig,
) -> list[ScenePrompt]:
    if target_count <= 0 or not prompts:
        return []
    target_count = min(int(target_count), len(prompts))
    ordered = sorted(prompts, key=_scene_score, reverse=True)
    pool_limit = min(
        len(ordered),
        max(config.min_seed_pool_size, target_count * max(1, config.seed_pool_multiplier)),
    )
    pool = ordered[:pool_limit]
    dim = int(pool[0].embedding.size)
    seed_index = _build_seed_index(dim)
    seeds: list[ScenePrompt] = []
    key_to_seed: dict[int, ScenePrompt] = {}

    for prompt in pool:
        if len(seeds) >= target_count:
            break
        if _nearest_seed_similarity(prompt, seeds, seed_index, key_to_seed) <= config.strict_seed_max_similarity:
            _add_seed(prompt, seeds, seed_index, key_to_seed)

    relaxed_target = math.ceil(target_count * config.seed_relax_trigger_ratio)
    if len(seeds) < relaxed_target:
        selected = {seed.prompt_hash for seed in seeds}
        for prompt in pool:
            if len(seeds) >= target_count:
                break
            if prompt.prompt_hash in selected:
                continue
            if _nearest_seed_similarity(prompt, seeds, seed_index, key_to_seed) <= config.relaxed_seed_max_similarity:
                _add_seed(prompt, seeds, seed_index, key_to_seed)
                selected.add(prompt.prompt_hash)

    if len(seeds) < target_count:
        selected = {seed.prompt_hash for seed in seeds}
        for prompt in ordered:
            if len(seeds) >= target_count:
                break
            if prompt.prompt_hash in selected:
                continue
            _add_seed(prompt, seeds, seed_index, key_to_seed)
            selected.add(prompt.prompt_hash)

    return seeds


def _nearest_centroid_assignments(
    prompts: list[ScenePrompt],
    centroids: np.ndarray,
    *,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    vectors = np.stack([prompt.embedding for prompt in prompts]).astype(np.float16, copy=False)
    assignments = np.zeros(len(prompts), dtype=np.int32)
    similarities = np.zeros(len(prompts), dtype=np.float32)
    centroid_matrix = centroids.astype(np.float32, copy=False).T
    for start in range(0, len(prompts), max(1, batch_size)):
        end = min(start + max(1, batch_size), len(prompts))
        scores = vectors[start:end].astype(np.float32) @ centroid_matrix
        assignments[start:end] = np.argmax(scores, axis=1).astype(np.int32)
        similarities[start:end] = np.max(scores, axis=1).astype(np.float32)
    return assignments, similarities


def _centroids_from_assignments(
    prompts: list[ScenePrompt],
    assignments: np.ndarray,
    seed_vectors: np.ndarray,
) -> np.ndarray:
    dim = int(seed_vectors.shape[1])
    sums = np.zeros((len(seed_vectors), dim), dtype=np.float32)
    counts = np.zeros(len(seed_vectors), dtype=np.int32)
    for index, prompt in enumerate(prompts):
        scene_index = int(assignments[index])
        sums[scene_index] += prompt.embedding.astype(np.float32)
        counts[scene_index] += 1
    for index, count in enumerate(counts):
        if count <= 0:
            sums[index] = seed_vectors[index].astype(np.float32)
        else:
            sums[index] /= float(count)
        norm = float(np.linalg.norm(sums[index]))
        if not math.isfinite(norm) or norm <= 0:
            sums[index] = seed_vectors[index].astype(np.float32)
            norm = float(np.linalg.norm(sums[index]))
        sums[index] /= max(norm, 1e-12)
    return sums.astype(np.float16)


def _member_sort_key(
    item: tuple[ScenePrompt, float, str],
) -> tuple[int, float, float, int, int, str]:
    prompt, similarity, band = item
    band_priority = {"high": 2, "medium": 1, "low": 0}.get(band, 0)
    return (band_priority, similarity, prompt.quality_score, prompt.uses, prompt.users, prompt.prompt_hash)


def build_semantic_scene_rows(
    prompts: list[ScenePrompt],
    target_count: int,
    config: PromptSceneConfig,
) -> SceneBuildResult:
    seeds = select_scene_seeds(prompts, target_count, config)
    if not seeds:
        return SceneBuildResult(scene_rows=[], member_rows=[])
    seed_vectors = np.stack([seed.embedding for seed in seeds]).astype(np.float16, copy=False)
    first_assignments, _ = _nearest_centroid_assignments(
        prompts,
        seed_vectors,
        batch_size=config.assignment_batch_size,
    )
    centroids = _centroids_from_assignments(prompts, first_assignments, seed_vectors)
    assignments, similarities = _nearest_centroid_assignments(
        prompts,
        centroids,
        batch_size=config.assignment_batch_size,
    )

    buckets: list[list[tuple[ScenePrompt, float, str]]] = [[] for _ in seeds]
    for index, prompt in enumerate(prompts):
        similarity = round(float(similarities[index]), 6)
        band = _confidence_band(similarity, config)
        buckets[int(assignments[index])].append((prompt, similarity, band))

    scene_rows: list[tuple[Any, ...]] = []
    member_rows: list[tuple[Any, ...]] = []
    for scene_index, members in enumerate(buckets):
        if not members:
            continue
        seed = seeds[scene_index]
        member_by_hash = {item[0].prompt_hash: item for item in members}
        representative_item = member_by_hash.get(seed.prompt_hash) or max(members, key=_member_sort_key)
        representative = representative_item[0]
        ranked_members = sorted(members, key=_member_sort_key, reverse=True)
        candidate_members = sorted(
            ranked_members,
            key=lambda item: (
                1 if item[2] in {"high", "medium"} else 0,
                item[1],
                item[0].quality_score,
                item[0].uses,
                item[0].users,
                item[0].prompt_hash,
            ),
            reverse=True,
        )[: config.candidates_per_scene]
        candidate_rank_by_hash = {
            item[0].prompt_hash: rank for rank, item in enumerate(candidate_members, start=1)
        }
        similarities_for_scene = [item[1] for item in members]
        high_count = sum(1 for _, _, band in members if band == "high")
        medium_count = sum(1 for _, _, band in members if band == "medium")
        low_count = sum(1 for _, _, band in members if band == "low")
        scene_id = _scene_id(config.model_id, seed.task_type, seed.prompt_hash)
        scene_rows.append(
            (
                scene_id,
                config.model_id,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_SCENE_ALGORITHM_VERSION,
                seed.task_type,
                representative.prompt_hash,
                representative.prompt,
                len(members),
                len(candidate_members),
                high_count,
                medium_count,
                low_count,
                round(min(similarities_for_scene), 6),
                round(sum(similarities_for_scene) / len(similarities_for_scene), 6),
                round(max(similarities_for_scene), 6),
                sum(item[0].uses for item in members),
                sum(item[0].users for item in members),
                representative.quality_score,
                int(centroids[scene_index].size),
                EMBEDDING_DTYPE,
                embedding_to_bytes(centroids[scene_index]),
            )
        )
        for member_rank, (prompt, similarity, band) in enumerate(ranked_members, start=1):
            member_rows.append(
                (
                    scene_id,
                    prompt.prompt_hash,
                    seed.task_type,
                    round(float(similarity), 6),
                    band,
                    member_rank,
                    candidate_rank_by_hash.get(prompt.prompt_hash),
                )
            )
    return SceneBuildResult(scene_rows=scene_rows, member_rows=member_rows)


async def fetch_scene_task_counts(conn: Any, config: PromptSceneConfig) -> dict[str, int]:
    rows = await conn.fetch(
        """
        select e.task_type, count(*)::bigint as count
        from analytics_prompt_embeddings e
        join analytics_prompt_slim_candidates s on s.prompt_hash = e.prompt_hash
        where e.model_id = $1::text
          and e.normalization_version = $2::text
          and e.status = 'embedded'
          and e.embedding_f16 is not null
          and s.quality_stage = 'candidate'
          and s.normalization_version = $2::text
          and ($3::text is null or e.task_type = $3::text)
        group by e.task_type
        order by count desc, e.task_type
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        config.task_type,
    )
    return {str(row["task_type"] or "unknown"): int(row["count"] or 0) for row in rows}


async def fetch_scene_prompts(conn: Any, config: PromptSceneConfig, task_type: str) -> list[ScenePrompt]:
    rows = await conn.fetch(
        """
        select
            e.prompt_hash,
            e.task_type,
            e.prompt,
            e.embedding_dim,
            e.embedding_f16,
            coalesce(s.quality_score, 0)::float8 as quality_score,
            coalesce(s.uses, 0)::bigint as uses,
            coalesce(s.users, 0)::bigint as users,
            s.last_seen
        from analytics_prompt_embeddings e
        join analytics_prompt_slim_candidates s on s.prompt_hash = e.prompt_hash
        where e.model_id = $1::text
          and e.normalization_version = $2::text
          and e.status = 'embedded'
          and e.embedding_f16 is not null
          and s.quality_stage = 'candidate'
          and s.normalization_version = $2::text
          and e.task_type = $3::text
        order by s.quality_score desc, s.uses desc, s.users desc, e.prompt_hash
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        task_type,
    )
    return [
        ScenePrompt(
            prompt_hash=row["prompt_hash"],
            task_type=row["task_type"] or "unknown",
            prompt=row["prompt"] or "",
            quality_score=float(row["quality_score"] or 0),
            uses=int(row["uses"] or 0),
            users=int(row["users"] or 0),
            last_seen=row["last_seen"],
            embedding=embedding_from_bytes(row["embedding_f16"], int(row["embedding_dim"])),
        )
        for row in rows
    ]


async def _clear_task_scene_members(conn: Any, config: PromptSceneConfig, task_type: str) -> None:
    scene_rows = await conn.fetch(
        """
        select scene_id
        from analytics_prompt_semantic_scenes
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
          and task_type = $4::text
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SCENE_ALGORITHM_VERSION,
        task_type,
    )
    scene_ids = [row["scene_id"] for row in scene_rows]
    if scene_ids:
        await conn.execute(
            "delete from analytics_prompt_semantic_scene_members where scene_id = any($1::text[])",
            scene_ids,
        )


async def _delete_stale_task_scenes(
    conn: Any,
    config: PromptSceneConfig,
    task_type: str,
    current_scene_ids: list[str],
) -> None:
    if current_scene_ids:
        await conn.execute(
            """
            delete from analytics_prompt_semantic_scenes
            where model_id = $1::text
              and normalization_version = $2::text
              and algorithm_version = $3::text
              and task_type = $4::text
              and not (scene_id = any($5::text[]))
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_SCENE_ALGORITHM_VERSION,
            task_type,
            current_scene_ids,
        )
        return
    await conn.execute(
        """
        delete from analytics_prompt_semantic_scenes
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
          and task_type = $4::text
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SCENE_ALGORITHM_VERSION,
        task_type,
    )


async def _insert_scene_rows(conn: Any, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    await conn.executemany(
        """
        insert into analytics_prompt_semantic_scenes (
            scene_id,
            model_id,
            normalization_version,
            algorithm_version,
            task_type,
            representative_hash,
            representative_prompt,
            member_count,
            candidate_count,
            high_confidence_count,
            medium_confidence_count,
            low_confidence_count,
            min_similarity,
            avg_similarity,
            max_similarity,
            total_uses,
            total_users,
            quality_score,
            centroid_dim,
            centroid_dtype,
            centroid_f16,
            created_at,
            refreshed_at
        )
        values (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
            $13, $14, $15, $16, $17, $18, $19, $20, $21, now(), now()
        )
        on conflict (scene_id) do update set
            representative_hash = excluded.representative_hash,
            representative_prompt = excluded.representative_prompt,
            member_count = excluded.member_count,
            candidate_count = excluded.candidate_count,
            high_confidence_count = excluded.high_confidence_count,
            medium_confidence_count = excluded.medium_confidence_count,
            low_confidence_count = excluded.low_confidence_count,
            min_similarity = excluded.min_similarity,
            avg_similarity = excluded.avg_similarity,
            max_similarity = excluded.max_similarity,
            total_uses = excluded.total_uses,
            total_users = excluded.total_users,
            quality_score = excluded.quality_score,
            centroid_dim = excluded.centroid_dim,
            centroid_dtype = excluded.centroid_dtype,
            centroid_f16 = excluded.centroid_f16,
            refreshed_at = now()
        """,
        rows,
    )


async def _insert_member_rows(conn: Any, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    await conn.executemany(
        """
        insert into analytics_prompt_semantic_scene_members (
            scene_id,
            prompt_hash,
            task_type,
            similarity_to_scene,
            confidence_band,
            member_rank,
            candidate_rank,
            created_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, now())
        on conflict (scene_id, prompt_hash) do update set
            similarity_to_scene = excluded.similarity_to_scene,
            confidence_band = excluded.confidence_band,
            member_rank = excluded.member_rank,
            candidate_rank = excluded.candidate_rank,
            created_at = now()
        """,
        rows,
    )


async def refresh_prompt_semantic_scenes(conn: Any, config: PromptSceneConfig) -> dict[str, Any]:
    await ensure_prompt_scene_schema(conn)
    started = time.monotonic()
    task_counts = await fetch_scene_task_counts(conn, config)
    targets = allocate_scene_targets(
        task_counts,
        target_total=config.target_scene_count,
        max_per_task=config.max_scenes_per_task,
    )
    total_scenes = 0
    total_members = 0
    total_candidates = 0
    task_status: dict[str, dict[str, int]] = {}
    await set_scene_state(
        conn,
        config.model_id,
        {
            "model_id": config.model_id,
            "model_key": config.model_key,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "algorithm_version": PROMPT_SCENE_ALGORITHM_VERSION,
            "target_scene_count": config.target_scene_count,
            "max_scenes_per_task": config.max_scenes_per_task,
            "candidates_per_scene": config.candidates_per_scene,
            "strict_seed_max_similarity": config.strict_seed_max_similarity,
            "relaxed_seed_max_similarity": config.relaxed_seed_max_similarity,
            "high_confidence_threshold": config.high_confidence_threshold,
            "medium_confidence_threshold": config.medium_confidence_threshold,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    for task_type, target in targets.items():
        prompts = await fetch_scene_prompts(conn, config, task_type)
        build_result = build_semantic_scene_rows(prompts, target, config)
        async with conn.transaction():
            await _clear_task_scene_members(conn, config, task_type)
            await _insert_scene_rows(conn, build_result.scene_rows)
            await _insert_member_rows(conn, build_result.member_rows)
            await _delete_stale_task_scenes(
                conn,
                config,
                task_type,
                [str(row[0]) for row in build_result.scene_rows],
            )
        scene_count = len(build_result.scene_rows)
        member_count = len(build_result.member_rows)
        candidate_count = sum(1 for row in build_result.member_rows if row[6] is not None)
        total_scenes += scene_count
        total_members += member_count
        total_candidates += candidate_count
        task_status[task_type] = {
            "embedded_count": len(prompts),
            "target_scene_count": int(target),
            "scene_count": scene_count,
            "member_count": member_count,
            "candidate_count": candidate_count,
        }

    await set_scene_state(
        conn,
        config.model_id,
        {
            "scene_count": total_scenes,
            "member_count": total_members,
            "candidate_count": total_candidates,
            "task_scene_counts": task_status,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
            "seconds": round(time.monotonic() - started, 2),
        },
    )
    return {
        "model_id": config.model_id,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "algorithm_version": PROMPT_SCENE_ALGORITHM_VERSION,
        "target_scene_count": config.target_scene_count,
        "scene_count": total_scenes,
        "member_count": total_members,
        "candidate_count": total_candidates,
        "task_scene_counts": task_status,
        "seconds": round(time.monotonic() - started, 2),
    }


def prompt_scene_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh prompt semantic scenes from existing embeddings.")
    parser.add_argument("--model-id", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_ID", DEFAULT_VECTOR_MODEL_ID))
    parser.add_argument("--model-key", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_KEY", DEFAULT_VECTOR_MODEL_KEY))
    parser.add_argument("--target-scene-count", type=int, default=DEFAULT_TARGET_SCENE_COUNT)
    parser.add_argument("--max-scenes-per-task", type=int, default=DEFAULT_MAX_SCENES_PER_TASK)
    parser.add_argument("--candidates-per-scene", type=int, default=DEFAULT_CANDIDATES_PER_SCENE)
    parser.add_argument("--strict-seed-max-similarity", type=float, default=DEFAULT_STRICT_SEED_MAX_SIMILARITY)
    parser.add_argument("--relaxed-seed-max-similarity", type=float, default=DEFAULT_RELAXED_SEED_MAX_SIMILARITY)
    parser.add_argument("--high-confidence-threshold", type=float, default=DEFAULT_HIGH_CONFIDENCE_THRESHOLD)
    parser.add_argument("--medium-confidence-threshold", type=float, default=DEFAULT_MEDIUM_CONFIDENCE_THRESHOLD)
    parser.add_argument("--assignment-batch-size", type=int, default=DEFAULT_ASSIGNMENT_BATCH_SIZE)
    parser.add_argument("--task-type")
    parser.add_argument("--data-dir", default=os.getenv("LOCAL_ANALYTICS_VECTOR_DATA_DIR", DEFAULT_VECTOR_DATA_DIR))
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    return parser


def config_from_args(args: argparse.Namespace) -> PromptSceneConfig:
    return PromptSceneConfig(
        model_id=args.model_id,
        model_key=args.model_key,
        target_scene_count=max(1, int(args.target_scene_count)),
        max_scenes_per_task=max(1, int(args.max_scenes_per_task)),
        candidates_per_scene=max(1, int(args.candidates_per_scene)),
        strict_seed_max_similarity=float(args.strict_seed_max_similarity),
        relaxed_seed_max_similarity=float(args.relaxed_seed_max_similarity),
        high_confidence_threshold=float(args.high_confidence_threshold),
        medium_confidence_threshold=float(args.medium_confidence_threshold),
        assignment_batch_size=max(1, int(args.assignment_batch_size)),
        task_type=(args.task_type or "").strip() or None,
        data_dir=args.data_dir,
    )


async def _run() -> None:
    from .main import _database_url

    parser = prompt_scene_arg_parser()
    args = parser.parse_args()
    conn = await asyncpg.connect(dsn=_database_url())
    try:
        await conn.execute(f"set statement_timeout = {int(args.statement_timeout_ms)}")
        status = await refresh_prompt_semantic_scenes(conn, config_from_args(args))
        print(json.dumps(status, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
