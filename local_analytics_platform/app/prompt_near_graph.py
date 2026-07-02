from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np

from .prompt_mart import PROMPT_NORMALIZATION_VERSION
from .prompt_vectors import (
    DEFAULT_VECTOR_DATA_DIR,
    DEFAULT_VECTOR_MODEL_ID,
    DEFAULT_VECTOR_MODEL_KEY,
    EmbeddedPrompt,
    fetch_embedded_prompts,
    prompt_hash_to_key,
)


DEFAULT_NEAR_GRAPH_LOWER_BOUND = 0.90
DEFAULT_NEAR_GRAPH_THRESHOLD = 0.95
DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS = 512
PROMPT_NEAR_GRAPH_ALGORITHM_VERSION = "near-graph-v1"
PROMPT_NEAR_GRAPH_LAYOUT_ALGORITHM = "pca-v1"


CREATE_PROMPT_NEAR_GRAPH_SCHEMA_SQL = [
    """
    create table if not exists analytics_prompt_near_graph_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_near_graph_edges (
        model_id text not null,
        normalization_version text not null,
        task_type text not null,
        source_hash text not null,
        target_hash text not null,
        similarity numeric(8, 6) not null,
        created_at timestamptz not null default now(),
        primary key (model_id, normalization_version, task_type, source_hash, target_hash)
    )
    """,
    "create index if not exists idx_prompt_near_graph_edges_task on analytics_prompt_near_graph_edges(model_id, normalization_version, task_type, similarity desc)",
    "create index if not exists idx_prompt_near_graph_edges_source on analytics_prompt_near_graph_edges(model_id, normalization_version, source_hash)",
    "create index if not exists idx_prompt_near_graph_edges_target on analytics_prompt_near_graph_edges(model_id, normalization_version, target_hash)",
]


PROMPT_NEAR_GRAPH_READY_SQL = """
select
    to_regclass('public.analytics_prompt_near_graph_state') is not null
    and to_regclass('public.analytics_prompt_near_graph_edges') is not null
    as ready
"""


@dataclass(frozen=True)
class PromptNearGraphConfig:
    model_id: str = DEFAULT_VECTOR_MODEL_ID
    model_key: str = DEFAULT_VECTOR_MODEL_KEY
    data_dir: str = DEFAULT_VECTOR_DATA_DIR
    lower_bound: float = DEFAULT_NEAR_GRAPH_LOWER_BOUND
    max_neighbors: int = DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS
    task_type: str | None = None
    batch_insert_size: int = 5000
    progress_interval: int = 10000


@dataclass(frozen=True)
class NearGraphEdge:
    task_type: str
    source_hash: str
    target_hash: str
    similarity: float


@dataclass
class NearGraphPromptStats:
    prompt_hash: str
    task_type: str
    prompt: str
    quality_score: float = 0
    uses: int = 0
    users: int = 0
    last_seen: Any = None
    embedding: np.ndarray | None = None
    result_likes: int = 0
    result_dislikes: int = 0
    gallery_applies: int = 0
    prompt_unlocks: int = 0
    char_count: int | None = None


@dataclass
class NearGraphFamily:
    family_id: str
    task_type: str
    member_hashes: list[str]
    center_hash: str
    center_similarity: dict[str, float]
    pair_similarities: list[float]
    bridged_degree: int = 0


@dataclass
class NearGraphBridge:
    source_family_id: str
    target_family_id: str
    prompt_edge_count: int = 0
    similarity_sum: float = 0
    max_similarity: float = 0
    examples: list[dict[str, Any]] = field(default_factory=list)

    @property
    def avg_similarity(self) -> float:
        if not self.prompt_edge_count:
            return 0.0
        return self.similarity_sum / self.prompt_edge_count


@dataclass
class NearGraphBuildResult:
    families: list[NearGraphFamily]
    bridges: list[NearGraphBridge]
    edge_count: int


def _state_key(model_id: str, key: str) -> str:
    return f"{model_id}:{PROMPT_NORMALIZATION_VERSION}:{PROMPT_NEAR_GRAPH_ALGORITHM_VERSION}:{key}"


async def ensure_prompt_near_graph_schema(conn: Any) -> None:
    for statement in CREATE_PROMPT_NEAR_GRAPH_SCHEMA_SQL:
        await conn.execute(statement)


async def set_near_graph_state(conn: Any, model_id: str, values: dict[str, Any]) -> None:
    for key, value in values.items():
        await conn.execute(
            """
            insert into analytics_prompt_near_graph_state (key, value, updated_at)
            values ($1::text, $2::text, now())
            on conflict (key) do update set value = excluded.value, updated_at = now()
            """,
            _state_key(model_id, key),
            json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value,
        )


def near_graph_family_id(task_type: str, member_hashes: list[str], threshold: float) -> str:
    fingerprint = hashlib.md5(
        f"{PROMPT_NEAR_GRAPH_ALGORITHM_VERSION}|{task_type}|{threshold:.3f}|{'|'.join(sorted(member_hashes))}".encode(
            "utf-8"
        )
    ).hexdigest()
    return f"near-family:{fingerprint}"


def representative_score(stats: NearGraphPromptStats | dict[str, Any]) -> tuple[float, int, int, float]:
    getter = stats.get if isinstance(stats, dict) else lambda key, default=None: getattr(stats, key, default)
    last_seen = getter("last_seen")
    if isinstance(last_seen, datetime):
        last_seen_score = last_seen.timestamp()
    else:
        last_seen_score = 0.0
    return (
        float(getter("quality_score", 0) or 0),
        int(getter("uses", 0) or 0),
        int(getter("users", 0) or 0),
        last_seen_score,
    )


def _cosine_from_normalized(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(left.astype(np.float32), right.astype(np.float32)))


def _normalized_centroid(vectors: list[np.ndarray]) -> np.ndarray | None:
    if not vectors:
        return None
    centroid = np.mean(np.stack(vectors).astype(np.float32, copy=False), axis=0)
    norm = float(np.linalg.norm(centroid))
    if not math.isfinite(norm) or norm <= 0:
        return None
    return (centroid / norm).astype(np.float32)


def choose_family_center(member_hashes: list[str], stats_by_hash: dict[str, NearGraphPromptStats]) -> tuple[str, dict[str, float]]:
    vectors = [stats_by_hash[prompt_hash].embedding for prompt_hash in member_hashes if stats_by_hash[prompt_hash].embedding is not None]
    centroid = _normalized_centroid([vector for vector in vectors if vector is not None])
    if centroid is None:
        center = max(member_hashes, key=lambda prompt_hash: (*representative_score(stats_by_hash[prompt_hash]), prompt_hash))
        return center, {prompt_hash: (1.0 if prompt_hash == center else 0.0) for prompt_hash in member_hashes}
    similarities = {
        prompt_hash: _cosine_from_normalized(stats_by_hash[prompt_hash].embedding, centroid)
        for prompt_hash in member_hashes
        if stats_by_hash[prompt_hash].embedding is not None
    }
    center = max(
        member_hashes,
        key=lambda prompt_hash: (
            similarities.get(prompt_hash, -1.0),
            *representative_score(stats_by_hash[prompt_hash]),
            prompt_hash,
        ),
    )
    return center, {prompt_hash: round(float(similarities.get(prompt_hash, 0.0)), 6) for prompt_hash in member_hashes}


def _guarded_member_groups(
    adjacency: dict[str, dict[str, float]],
    stats_by_hash: dict[str, NearGraphPromptStats],
    threshold: float,
) -> list[list[str]]:
    candidates = [prompt_hash for prompt_hash in adjacency if prompt_hash in stats_by_hash]
    ordered = sorted(
        candidates,
        key=lambda prompt_hash: (*representative_score(stats_by_hash[prompt_hash]), prompt_hash),
        reverse=True,
    )
    unassigned = set(ordered)
    groups: list[list[str]] = []

    for representative in ordered:
        if representative not in unassigned:
            continue
        members = [representative]
        neighbors = [
            neighbor
            for neighbor, similarity in adjacency.get(representative, {}).items()
            if neighbor in unassigned and neighbor in stats_by_hash and similarity >= threshold
        ]
        neighbors.sort(
            key=lambda neighbor: (
                adjacency[representative].get(neighbor, 0),
                *representative_score(stats_by_hash[neighbor]),
                neighbor,
            ),
            reverse=True,
        )
        for neighbor in neighbors:
            if all(adjacency.get(neighbor, {}).get(member, 0) >= threshold for member in members):
                members.append(neighbor)
        unassigned.discard(representative)
        if len(members) >= 2:
            for member in members[1:]:
                unassigned.discard(member)
        groups.append(members)

    return groups


def build_near_graph(
    edges: list[NearGraphEdge],
    stats_by_hash: dict[str, NearGraphPromptStats],
    *,
    threshold: float,
) -> NearGraphBuildResult:
    task_adjacency: dict[str, dict[str, dict[str, float]]] = {}
    retained_edges: list[NearGraphEdge] = []
    for edge in edges:
        if edge.similarity < threshold:
            continue
        if edge.source_hash not in stats_by_hash or edge.target_hash not in stats_by_hash:
            continue
        task = edge.task_type or stats_by_hash[edge.source_hash].task_type or "unknown"
        task_adjacency.setdefault(task, {}).setdefault(edge.source_hash, {})
        task_adjacency.setdefault(task, {}).setdefault(edge.target_hash, {})
        current = task_adjacency[task][edge.source_hash].get(edge.target_hash, 0.0)
        similarity = max(current, float(edge.similarity))
        task_adjacency[task][edge.source_hash][edge.target_hash] = similarity
        task_adjacency[task][edge.target_hash][edge.source_hash] = similarity
        retained_edges.append(NearGraphEdge(task, edge.source_hash, edge.target_hash, similarity))

    families: list[NearGraphFamily] = []
    prompt_to_family: dict[str, str] = {}
    for task_type, adjacency in sorted(task_adjacency.items()):
        for members in _guarded_member_groups(adjacency, stats_by_hash, threshold):
            center_hash, center_similarity = choose_family_center(members, stats_by_hash)
            pair_similarities = [
                adjacency[left].get(right, 0.0)
                for index, left in enumerate(members)
                for right in members[index + 1 :]
                if adjacency[left].get(right, 0.0) >= threshold
            ]
            family = NearGraphFamily(
                family_id=near_graph_family_id(task_type, members, threshold),
                task_type=task_type,
                member_hashes=members,
                center_hash=center_hash,
                center_similarity=center_similarity,
                pair_similarities=pair_similarities or [1.0],
            )
            families.append(family)
            for prompt_hash in members:
                prompt_to_family[prompt_hash] = family.family_id

    bridge_by_key: dict[tuple[str, str], NearGraphBridge] = {}
    for edge in retained_edges:
        source_family = prompt_to_family.get(edge.source_hash)
        target_family = prompt_to_family.get(edge.target_hash)
        if not source_family or not target_family or source_family == target_family:
            continue
        left, right = sorted((source_family, target_family))
        bridge = bridge_by_key.setdefault((left, right), NearGraphBridge(left, right))
        bridge.prompt_edge_count += 1
        bridge.similarity_sum += float(edge.similarity)
        bridge.max_similarity = max(bridge.max_similarity, float(edge.similarity))
        if len(bridge.examples) < 5:
            bridge.examples.append(
                {
                    "source_hash": edge.source_hash,
                    "target_hash": edge.target_hash,
                    "similarity": round(float(edge.similarity), 6),
                }
            )

    degree_by_family: dict[str, int] = {}
    for bridge in bridge_by_key.values():
        degree_by_family[bridge.source_family_id] = degree_by_family.get(bridge.source_family_id, 0) + 1
        degree_by_family[bridge.target_family_id] = degree_by_family.get(bridge.target_family_id, 0) + 1
    for family in families:
        family.bridged_degree = degree_by_family.get(family.family_id, 0)

    families.sort(
        key=lambda family: (
            family.bridged_degree,
            len(family.member_hashes),
            *representative_score(stats_by_hash[family.center_hash]),
            family.family_id,
        ),
        reverse=True,
    )
    bridges = sorted(
        bridge_by_key.values(),
        key=lambda bridge: (bridge.prompt_edge_count, bridge.max_similarity, bridge.source_family_id, bridge.target_family_id),
        reverse=True,
    )
    return NearGraphBuildResult(families=families, bridges=bridges, edge_count=len(retained_edges))


def build_near_graph_layout(
    families: list[NearGraphFamily],
    stats_by_hash: dict[str, NearGraphPromptStats],
) -> dict[str, tuple[float, float]]:
    if not families:
        return {}
    vectors = [stats_by_hash[family.center_hash].embedding for family in families]
    if any(vector is None for vector in vectors):
        angles = np.linspace(0, 2 * math.pi, len(families), endpoint=False)
        return {
            family.family_id: (round(float(math.cos(angles[index])), 6), round(float(math.sin(angles[index])), 6))
            for index, family in enumerate(families)
        }
    matrix = np.stack([vector for vector in vectors if vector is not None]).astype(np.float32, copy=False)
    if len(families) == 1:
        coords = np.zeros((1, 2), dtype=np.float32)
    else:
        centered = matrix - matrix.mean(axis=0, keepdims=True)
        try:
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            components = vt[:2]
            if components.shape[0] == 1:
                components = np.vstack([components, np.zeros_like(components[0])])
            coords = centered @ components[:2].T
        except np.linalg.LinAlgError:
            angles = np.linspace(0, 2 * math.pi, len(families), endpoint=False)
            coords = np.stack([np.cos(angles), np.sin(angles)], axis=1).astype(np.float32)
        for axis in range(2):
            limit = float(np.max(np.abs(coords[:, axis])))
            if math.isfinite(limit) and limit > 0:
                coords[:, axis] = coords[:, axis] / limit
    return {
        family.family_id: (round(float(coords[index, 0]), 6), round(float(coords[index, 1]), 6))
        for index, family in enumerate(families)
    }


def near_graph_radius(member_count: int) -> float:
    return round(max(7.0, min(38.0, 6.0 + math.log1p(max(0, int(member_count))) * 3.0)), 4)


def prompt_preview(prompt: str, limit: int = 180) -> str:
    text = " ".join(str(prompt or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def family_record(
    family: NearGraphFamily,
    stats_by_hash: dict[str, NearGraphPromptStats],
    *,
    include_layout: bool = False,
    layout: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    center = stats_by_hash[family.center_hash]
    member_stats = [stats_by_hash[prompt_hash] for prompt_hash in family.member_hashes]
    similarities = family.pair_similarities or [1.0]
    record = {
        "id": family.family_id,
        "family_id": family.family_id,
        "task_type": family.task_type,
        "label": prompt_preview(center.prompt, 80) or family.family_id,
        "center_hash": family.center_hash,
        "representative_hash": family.center_hash,
        "center_prompt": center.prompt,
        "representative_prompt": center.prompt,
        "center_preview": prompt_preview(center.prompt),
        "representative_preview": prompt_preview(center.prompt),
        "member_count": len(family.member_hashes),
        "bridge_degree": family.bridged_degree,
        "internal_edge_count": len([value for value in similarities if value < 1.0 or len(family.member_hashes) > 1]),
        "min_similarity": round(float(min(similarities)), 6),
        "avg_similarity": round(float(sum(similarities) / len(similarities)), 6),
        "max_similarity": round(float(max(similarities)), 6),
        "total_uses": sum(item.uses for item in member_stats),
        "total_users": sum(item.users for item in member_stats),
        "quality_score": center.quality_score,
        "center_similarity": family.center_similarity.get(family.center_hash, 1.0),
        "last_seen": center.last_seen,
        "symbol_size": near_graph_radius(len(family.member_hashes)),
    }
    if include_layout and layout is not None:
        x, y = layout.get(family.family_id, (0.0, 0.0))
        record.update({"x": x, "y": y, "radius": near_graph_radius(len(family.member_hashes))})
    return record


def member_records(family: NearGraphFamily, stats_by_hash: dict[str, NearGraphPromptStats]) -> list[dict[str, Any]]:
    rows = []
    ordered = sorted(
        family.member_hashes,
        key=lambda prompt_hash: (
            family.center_similarity.get(prompt_hash, 0.0),
            *representative_score(stats_by_hash[prompt_hash]),
            prompt_hash,
        ),
        reverse=True,
    )
    for rank, prompt_hash in enumerate(ordered, start=1):
        stats = stats_by_hash[prompt_hash]
        rows.append(
            {
                "prompt_hash": prompt_hash,
                "task_type": stats.task_type,
                "prompt": stats.prompt,
                "prompt_preview": prompt_preview(stats.prompt),
                "member_rank": rank,
                "is_center": prompt_hash == family.center_hash,
                "is_representative": prompt_hash == family.center_hash,
                "similarity_to_center": round(float(family.center_similarity.get(prompt_hash, 0.0)), 6),
                "quality_score": stats.quality_score,
                "uses": stats.uses,
                "users": stats.users,
                "last_seen": stats.last_seen,
                "result_likes": stats.result_likes,
                "result_dislikes": stats.result_dislikes,
                "gallery_applies": stats.gallery_applies,
                "prompt_unlocks": stats.prompt_unlocks,
                "char_count": stats.char_count,
            }
        )
    return rows


def bridge_record(bridge: NearGraphBridge) -> dict[str, Any]:
    return {
        "source": bridge.source_family_id,
        "target": bridge.target_family_id,
        "source_family_id": bridge.source_family_id,
        "target_family_id": bridge.target_family_id,
        "prompt_edge_count": bridge.prompt_edge_count,
        "weight": round(float(bridge.avg_similarity), 6),
        "avg_similarity": round(float(bridge.avg_similarity), 6),
        "max_similarity": round(float(bridge.max_similarity), 6),
        "examples": bridge.examples,
    }


def search_result_may_be_truncated(*, returned_neighbor_count: int, max_neighbors: int, last_similarity: float | None, lower_bound: float) -> bool:
    return (
        returned_neighbor_count >= max_neighbors
        and last_similarity is not None
        and float(last_similarity) >= float(lower_bound)
    )


def _edge_row_batches_for_task(
    task_type: str,
    prompts: list[EmbeddedPrompt],
    config: PromptNearGraphConfig,
) -> Any:
    if len(prompts) < 2:
        yield [], len(prompts), 0, True
        return
    try:
        from usearch.index import Index
    except ImportError as exc:
        raise RuntimeError("usearch is required for prompt near graph edge refresh") from exc

    dim = int(prompts[0].embedding.size)
    vectors = np.stack([item.embedding for item in prompts]).astype(np.float16, copy=False)
    keys = np.asarray([prompt_hash_to_key(item.prompt_hash) for item in prompts], dtype=np.uint64)
    index = Index(ndim=dim, metric="cos", dtype="f16")
    index.add(keys, vectors)

    index_dir = Path(config.data_dir) / config.model_id / PROMPT_NORMALIZATION_VERSION
    index_dir.mkdir(parents=True, exist_ok=True)
    index.save(str(index_dir / f"{task_type}.near_graph.usearch"))

    key_to_pos = {int(key): pos for pos, key in enumerate(keys.tolist())}
    rows: list[tuple[Any, ...]] = []
    possible_truncated = 0
    search_count = min(config.max_neighbors + 1, len(prompts))
    for source_pos, source in enumerate(prompts):
        matches = index.search(vectors[source_pos], count=search_count)
        match_keys = getattr(matches, "keys", matches[0] if isinstance(matches, tuple) else [])
        neighbor_rank = 0
        last_similarity: float | None = None
        for raw_key in match_keys:
            neighbor_pos = key_to_pos.get(int(raw_key))
            if neighbor_pos is None or neighbor_pos == source_pos:
                continue
            neighbor_rank += 1
            neighbor = prompts[neighbor_pos]
            similarity = _cosine_from_normalized(source.embedding, neighbor.embedding)
            last_similarity = similarity
            if similarity < config.lower_bound:
                continue
            left, right = sorted((source.prompt_hash, neighbor.prompt_hash))
            rows.append(
                (
                    config.model_id,
                    PROMPT_NORMALIZATION_VERSION,
                    task_type,
                    left,
                    right,
                    round(float(similarity), 6),
                )
            )
            if len(rows) >= config.batch_insert_size:
                yield rows, source_pos + 1, possible_truncated, False
                rows = []
        if search_result_may_be_truncated(
            returned_neighbor_count=neighbor_rank,
            max_neighbors=config.max_neighbors,
            last_similarity=last_similarity,
            lower_bound=config.lower_bound,
        ):
            possible_truncated += 1
        if (source_pos + 1) % config.progress_interval == 0:
            yield rows, source_pos + 1, possible_truncated, False
            rows = []
    yield rows, len(prompts), possible_truncated, True


async def refresh_prompt_near_graph_edges(conn: Any, config: PromptNearGraphConfig) -> dict[str, Any]:
    await ensure_prompt_near_graph_schema(conn)
    started = time.monotonic()
    await set_near_graph_state(
        conn,
        config.model_id,
        {
            "model_id": config.model_id,
            "model_key": config.model_key,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "algorithm_version": PROMPT_NEAR_GRAPH_ALGORITHM_VERSION,
            "layout_algorithm": PROMPT_NEAR_GRAPH_LAYOUT_ALGORITHM,
            "lower_bound": config.lower_bound,
            "max_neighbors": config.max_neighbors,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    grouped = await fetch_embedded_prompts(conn, config.model_id, config.task_type)
    task_counts: dict[str, int] = {}
    possible_truncated_count = 0
    insert_sql = """
        insert into analytics_prompt_near_graph_edges (
            model_id,
            normalization_version,
            task_type,
            source_hash,
            target_hash,
            similarity,
            created_at
        )
        values ($1, $2, $3, $4, $5, $6, now())
        on conflict (model_id, normalization_version, task_type, source_hash, target_hash) do update set
            similarity = greatest(analytics_prompt_near_graph_edges.similarity, excluded.similarity),
            created_at = now()
    """
    for task_type, prompts in grouped.items():
        await conn.execute(
            """
            delete from analytics_prompt_near_graph_edges
            where model_id = $1::text
              and normalization_version = $2::text
              and task_type = $3::text
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            task_type,
        )
        task_truncated = 0
        candidate_edge_rows = 0
        for rows, processed_count, task_truncated, done in _edge_row_batches_for_task(task_type, prompts, config):
            if rows:
                candidate_edge_rows += len(rows)
                await conn.executemany(insert_sql, rows)
            should_report = done or (
                processed_count > 0
                and processed_count % config.progress_interval == 0
            )
            if should_report:
                await set_near_graph_state(
                    conn,
                    config.model_id,
                    {
                        "current_task_type": task_type,
                        "current_task_processed": processed_count,
                        "current_task_total": len(prompts),
                        "current_task_candidate_edge_rows": candidate_edge_rows,
                        "possible_truncated_count": possible_truncated_count + task_truncated,
                        "progress_updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                print(
                    json.dumps(
                        {
                            "status": "progress",
                            "task_type": task_type,
                            "processed": processed_count,
                            "total": len(prompts),
                            "candidate_edge_rows": candidate_edge_rows,
                            "possible_truncated_count": possible_truncated_count + task_truncated,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
        possible_truncated_count += task_truncated
        count_row = await conn.fetchrow(
            """
            select count(*)::bigint as count
            from analytics_prompt_near_graph_edges
            where model_id = $1::text
              and normalization_version = $2::text
              and task_type = $3::text
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            task_type,
        )
        task_counts[task_type] = int(count_row["count"] or 0)
        print(
            json.dumps(
                {
                    "status": "task_done",
                    "task_type": task_type,
                    "edge_count": task_counts[task_type],
                    "possible_truncated_count": possible_truncated_count,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    edge_count = sum(task_counts.values())
    seconds = round(time.monotonic() - started, 2)
    await set_near_graph_state(
        conn,
        config.model_id,
        {
            "edge_count": edge_count,
            "task_counts": task_counts,
            "possible_truncated_count": possible_truncated_count,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
            "seconds": seconds,
            "last_error": "",
        },
    )
    return {
        "model_id": config.model_id,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "algorithm_version": PROMPT_NEAR_GRAPH_ALGORITHM_VERSION,
        "lower_bound": config.lower_bound,
        "max_neighbors": config.max_neighbors,
        "edge_count": edge_count,
        "task_counts": task_counts,
        "possible_truncated_count": possible_truncated_count,
        "seconds": seconds,
    }


def prompt_near_graph_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh prompt near graph threshold edges from embeddings.")
    parser.add_argument("--model-id", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_ID", DEFAULT_VECTOR_MODEL_ID))
    parser.add_argument("--model-key", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_KEY", DEFAULT_VECTOR_MODEL_KEY))
    parser.add_argument("--data-dir", default=os.getenv("LOCAL_ANALYTICS_VECTOR_DATA_DIR", DEFAULT_VECTOR_DATA_DIR))
    parser.add_argument("--lower-bound", type=float, default=DEFAULT_NEAR_GRAPH_LOWER_BOUND)
    parser.add_argument("--max-neighbors", type=int, default=DEFAULT_NEAR_GRAPH_MAX_NEIGHBORS)
    parser.add_argument("--batch-insert-size", type=int, default=5000)
    parser.add_argument("--progress-interval", type=int, default=10000)
    parser.add_argument("--task-type", default=None)
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    return parser


def config_from_args(args: argparse.Namespace) -> PromptNearGraphConfig:
    return PromptNearGraphConfig(
        model_id=args.model_id,
        model_key=args.model_key,
        data_dir=args.data_dir,
        lower_bound=max(0.0, min(1.0, float(args.lower_bound))),
        max_neighbors=max(1, int(args.max_neighbors)),
        task_type=(args.task_type or "").strip() or None,
        batch_insert_size=max(1, int(args.batch_insert_size)),
        progress_interval=max(1, int(args.progress_interval)),
    )


async def _run() -> None:
    from .main import _database_url

    parser = prompt_near_graph_arg_parser()
    args = parser.parse_args()
    config = config_from_args(args)
    conn = await asyncpg.connect(dsn=_database_url())
    try:
        await conn.execute(f"set statement_timeout = {int(args.statement_timeout_ms)}")
        status = await refresh_prompt_near_graph_edges(conn, config)
        print(json.dumps(status, ensure_ascii=False, default=str, sort_keys=True))
    except Exception as exc:
        try:
            await ensure_prompt_near_graph_schema(conn)
            await set_near_graph_state(
                conn,
                config.model_id,
                {"last_error": str(exc), "last_error_at": datetime.now(timezone.utc).isoformat()},
            )
        finally:
            raise
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_run())
