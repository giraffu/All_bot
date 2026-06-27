from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .prompt_mart import PROMPT_NORMALIZATION_VERSION


DEFAULT_VECTOR_MODEL_KEY = "text-embedding-qwen3-embedding-8b"
DEFAULT_VECTOR_MODEL_ID = "qwen3-embedding-8b"
DEFAULT_LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_VECTOR_DATA_DIR = "/app/data/prompt_vectors"
DEFAULT_TOP_K = 20
DEFAULT_DUPLICATE_THRESHOLD = 0.92
DEFAULT_SIMILAR_THRESHOLD = 0.86
EMBEDDING_DTYPE = "float16"


CREATE_PROMPT_VECTOR_SCHEMA_SQL = [
    """
    create table if not exists analytics_prompt_vector_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_embeddings (
        prompt_hash text not null,
        task_type text not null,
        model_id text not null,
        normalization_version text not null,
        prompt text not null,
        prompt_checksum text not null,
        embedding_dim integer not null,
        embedding_dtype text not null default 'float16',
        embedding_f16 bytea,
        status text not null default 'embedded',
        error text,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        embedded_at timestamptz,
        primary key (model_id, normalization_version, prompt_hash)
    )
    """,
    """
    create table if not exists analytics_prompt_similarity_edges (
        model_id text not null,
        normalization_version text not null,
        task_type text not null,
        source_hash text not null,
        neighbor_hash text not null,
        similarity numeric(8, 6) not null,
        rank integer not null,
        band text not null,
        created_at timestamptz not null default now(),
        primary key (model_id, normalization_version, source_hash, neighbor_hash),
        constraint chk_prompt_similarity_band check (band in ('duplicate', 'similar'))
    )
    """,
    """
    create table if not exists analytics_prompt_similarity_clusters (
        cluster_id text primary key,
        model_id text not null,
        normalization_version text not null,
        task_type text not null,
        representative_hash text not null,
        representative_prompt text not null,
        member_count bigint not null,
        duplicate_edge_count bigint not null,
        min_similarity numeric(8, 6) not null,
        avg_similarity numeric(8, 6) not null,
        max_similarity numeric(8, 6) not null,
        total_uses bigint not null default 0,
        total_users bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        created_at timestamptz not null default now(),
        refreshed_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_similarity_members (
        cluster_id text not null,
        prompt_hash text not null,
        task_type text not null,
        similarity_to_representative numeric(8, 6) not null,
        is_representative boolean not null default false,
        member_rank integer not null,
        created_at timestamptz not null default now(),
        primary key (cluster_id, prompt_hash)
    )
    """,
    "create index if not exists idx_prompt_embeddings_task on analytics_prompt_embeddings(model_id, normalization_version, task_type)",
    "create index if not exists idx_prompt_embeddings_status on analytics_prompt_embeddings(status, updated_at desc)",
    "create index if not exists idx_prompt_similarity_edges_task on analytics_prompt_similarity_edges(model_id, normalization_version, task_type, similarity desc)",
    "create index if not exists idx_prompt_similarity_edges_source on analytics_prompt_similarity_edges(model_id, normalization_version, source_hash)",
    "create index if not exists idx_prompt_similarity_edges_neighbor on analytics_prompt_similarity_edges(model_id, normalization_version, neighbor_hash)",
    "create index if not exists idx_prompt_similarity_clusters_task on analytics_prompt_similarity_clusters(model_id, normalization_version, task_type, member_count desc)",
    "create index if not exists idx_prompt_similarity_clusters_score on analytics_prompt_similarity_clusters(model_id, normalization_version, quality_score desc)",
    "create index if not exists idx_prompt_similarity_members_cluster on analytics_prompt_similarity_members(cluster_id, member_rank)",
    "create index if not exists idx_prompt_similarity_members_prompt on analytics_prompt_similarity_members(prompt_hash)",
    "alter table analytics_prompt_embeddings add column if not exists prompt_checksum text not null default ''",
    "alter table analytics_prompt_embeddings add column if not exists embedding_f16 bytea",
    "alter table analytics_prompt_embeddings add column if not exists error text",
    "alter table analytics_prompt_embeddings add column if not exists embedded_at timestamptz",
    "alter table analytics_prompt_similarity_clusters add column if not exists representative_prompt text not null default ''",
]


PROMPT_VECTOR_READY_SQL = """
select
    to_regclass('public.analytics_prompt_vector_state') is not null
    and to_regclass('public.analytics_prompt_embeddings') is not null
    and to_regclass('public.analytics_prompt_similarity_edges') is not null
    and to_regclass('public.analytics_prompt_similarity_clusters') is not null
    and to_regclass('public.analytics_prompt_similarity_members') is not null
    as ready
"""


@dataclass(frozen=True)
class PromptVectorConfig:
    model_id: str = DEFAULT_VECTOR_MODEL_ID
    model_key: str = DEFAULT_VECTOR_MODEL_KEY
    base_url: str = DEFAULT_LM_STUDIO_BASE_URL
    batch_size: int = 8
    limit: int | None = None
    task_type: str | None = None
    top_k: int = DEFAULT_TOP_K
    duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD
    similar_threshold: float = DEFAULT_SIMILAR_THRESHOLD
    data_dir: str = DEFAULT_VECTOR_DATA_DIR
    embed_only: bool = False
    similarity_only: bool = False
    cluster_only: bool = False
    skip_lm_check: bool = False
    exact_fallback_limit: int = 10_000


@dataclass(frozen=True)
class CandidatePrompt:
    prompt_hash: str
    task_type: str
    prompt: str


@dataclass(frozen=True)
class EmbeddedPrompt:
    prompt_hash: str
    task_type: str
    prompt: str
    quality_score: float
    uses: int
    users: int
    last_seen: datetime | None
    embedding: np.ndarray


class LMStudioEmbeddingClient:
    def __init__(self, base_url: str, model_id: str, model_key: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.model_key = model_key
        self.timeout = timeout

    def check_ready(self) -> None:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(_lm_studio_help("LM Studio Server is not reachable")) from exc

        models = payload.get("data") or []
        model_ids = {str(model.get("id") or "") for model in models if isinstance(model, dict)}
        if self.model_id not in model_ids and self.model_key not in model_ids:
            raise RuntimeError(_lm_studio_help(f"embedding model is not loaded: {self.model_id}"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model_id, "input": texts}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LM Studio embedding request failed: HTTP {exc.code} {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(_lm_studio_help("LM Studio embedding request failed")) from exc

        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise RuntimeError("LM Studio embedding response shape is invalid")
        vectors = []
        for item in sorted(data, key=lambda row: row.get("index", 0)):
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise RuntimeError("LM Studio embedding response contains an empty vector")
            vectors.append(vector)
        return vectors


def _lm_studio_help(reason: str) -> str:
    return (
        f"{reason}; start and load the local embedding model first: "
        "lms server start && "
        f"lms load {DEFAULT_VECTOR_MODEL_KEY} --identifier {DEFAULT_VECTOR_MODEL_ID} --gpu max -y"
    )


def _vector_state_key(model_id: str, normalization_version: str, key: str) -> str:
    return f"{model_id}:{normalization_version}:{key}"


async def ensure_prompt_vector_schema(conn: Any) -> None:
    for statement in CREATE_PROMPT_VECTOR_SCHEMA_SQL:
        await conn.execute(statement)


async def set_vector_state(conn: Any, model_id: str, normalization_version: str, values: dict[str, Any]) -> None:
    for key, value in values.items():
        await conn.execute(
            """
            insert into analytics_prompt_vector_state (key, value, updated_at)
            values ($1::text, $2::text, now())
            on conflict (key) do update set value = excluded.value, updated_at = now()
            """,
            _vector_state_key(model_id, normalization_version, key),
            json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value,
        )


def normalize_embedding(vector: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(vector), dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("embedding norm is zero")
    return (array / norm).astype(np.float16)


def embedding_to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float16).tobytes()


def embedding_from_bytes(raw: bytes | memoryview, dim: int) -> np.ndarray:
    vector = np.frombuffer(bytes(raw), dtype=np.float16)
    if vector.size != dim:
        raise ValueError(f"embedding dimension mismatch: expected {dim}, got {vector.size}")
    return vector


def prompt_hash_to_key(prompt_hash: str) -> int:
    return int(prompt_hash[:16], 16)


def stable_cluster_id(model_id: str, normalization_version: str, task_type: str, representative_hash: str) -> str:
    raw = f"{model_id}\x1f{normalization_version}\x1f{task_type}\x1f{representative_hash}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


async def _candidate_count(conn: Any, task_type: str | None = None) -> int:
    return int(
        await conn.fetchval(
            """
            select count(*)::bigint
            from analytics_prompt_slim_candidates
            where quality_stage = 'candidate'
              and normalization_version = $1::text
              and ($2::text is null or $2::text = any(task_types))
            """,
            PROMPT_NORMALIZATION_VERSION,
            task_type,
        )
        or 0
    )


async def _embedded_count(conn: Any, model_id: str, task_type: str | None = None) -> int:
    return int(
        await conn.fetchval(
            """
            select count(*)::bigint
            from analytics_prompt_embeddings
            where model_id = $1::text
              and normalization_version = $2::text
              and status = 'embedded'
              and ($3::text is null or task_type = $3::text)
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            task_type,
        )
        or 0
    )


async def fetch_embedding_candidates(
    conn: Any,
    config: PromptVectorConfig,
    limit: int | None = None,
) -> list[CandidatePrompt]:
    rows = await conn.fetch(
        """
        select
            s.prompt_hash,
            coalesce(s.task_types[1], 'unknown') as task_type,
            s.prompt
        from analytics_prompt_slim_candidates s
        where s.quality_stage = 'candidate'
          and s.normalization_version = $1::text
          and ($2::text is null or $2::text = any(s.task_types))
          and not exists (
              select 1
              from analytics_prompt_embeddings e
              where e.model_id = $3::text
                and e.normalization_version = $1::text
                and e.prompt_hash = s.prompt_hash
                and e.status = 'embedded'
          )
        order by coalesce(s.task_types[1], 'unknown'), s.quality_score desc, s.uses desc, s.prompt_hash
        limit $4::int
        """,
        PROMPT_NORMALIZATION_VERSION,
        config.task_type,
        config.model_id,
        limit or config.limit or config.batch_size,
    )
    return [
        CandidatePrompt(
            prompt_hash=row["prompt_hash"],
            task_type=row["task_type"] or "unknown",
            prompt=row["prompt"] or "",
        )
        for row in rows
    ]


async def _upsert_embedding_batch(
    conn: Any,
    model_id: str,
    candidates: list[CandidatePrompt],
    vectors: list[np.ndarray],
) -> None:
    rows = []
    for candidate, vector in zip(candidates, vectors, strict=True):
        rows.append(
            (
                candidate.prompt_hash,
                candidate.task_type,
                model_id,
                PROMPT_NORMALIZATION_VERSION,
                candidate.prompt,
                hashlib.md5(candidate.prompt.encode("utf-8")).hexdigest(),
                int(vector.size),
                EMBEDDING_DTYPE,
                embedding_to_bytes(vector),
            )
        )
    await conn.executemany(
        """
        insert into analytics_prompt_embeddings (
            prompt_hash,
            task_type,
            model_id,
            normalization_version,
            prompt,
            prompt_checksum,
            embedding_dim,
            embedding_dtype,
            embedding_f16,
            status,
            error,
            created_at,
            updated_at,
            embedded_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'embedded', null, now(), now(), now())
        on conflict (model_id, normalization_version, prompt_hash) do update set
            task_type = excluded.task_type,
            prompt = excluded.prompt,
            prompt_checksum = excluded.prompt_checksum,
            embedding_dim = excluded.embedding_dim,
            embedding_dtype = excluded.embedding_dtype,
            embedding_f16 = excluded.embedding_f16,
            status = 'embedded',
            error = null,
            updated_at = now(),
            embedded_at = now()
        """,
        rows,
    )


async def _mark_embedding_errors(
    conn: Any,
    model_id: str,
    candidates: list[CandidatePrompt],
    error: str,
) -> None:
    rows = [
        (
            candidate.prompt_hash,
            candidate.task_type,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            candidate.prompt,
            hashlib.md5(candidate.prompt.encode("utf-8")).hexdigest(),
            0,
            EMBEDDING_DTYPE,
            error[:1000],
        )
        for candidate in candidates
    ]
    await conn.executemany(
        """
        insert into analytics_prompt_embeddings (
            prompt_hash,
            task_type,
            model_id,
            normalization_version,
            prompt,
            prompt_checksum,
            embedding_dim,
            embedding_dtype,
            status,
            error,
            created_at,
            updated_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, 'error', $9, now(), now())
        on conflict (model_id, normalization_version, prompt_hash) do update set
            task_type = excluded.task_type,
            prompt = excluded.prompt,
            prompt_checksum = excluded.prompt_checksum,
            status = 'error',
            error = excluded.error,
            updated_at = now()
        """,
        rows,
    )


async def refresh_prompt_embeddings(
    conn: Any,
    client: LMStudioEmbeddingClient,
    config: PromptVectorConfig,
) -> dict[str, Any]:
    selected = 0
    embedded = 0
    embedding_dim: int | None = None
    started = time.monotonic()
    while config.limit is None or selected < config.limit:
        remaining = None if config.limit is None else max(0, config.limit - selected)
        if remaining == 0:
            break
        batch_limit = config.batch_size if remaining is None else min(config.batch_size, remaining)
        batch = await fetch_embedding_candidates(conn, config, batch_limit)
        if not batch:
            break
        selected += len(batch)
        try:
            raw_vectors = await asyncio.to_thread(client.embed, [item.prompt for item in batch])
            vectors = [normalize_embedding(vector) for vector in raw_vectors]
            dims = {int(vector.size) for vector in vectors}
            if len(dims) != 1:
                raise RuntimeError(f"embedding dimensions are inconsistent: {sorted(dims)}")
            embedding_dim = dims.pop()
            await _upsert_embedding_batch(conn, config.model_id, batch, vectors)
            embedded += len(batch)
            await set_vector_state(
                conn,
                config.model_id,
                PROMPT_NORMALIZATION_VERSION,
                {
                    "embedding_dim": embedding_dim,
                    "embedded_in_run": embedded,
                    "last_embedding_batch_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            await _mark_embedding_errors(conn, config.model_id, batch, str(exc))
            await set_vector_state(
                conn,
                config.model_id,
                PROMPT_NORMALIZATION_VERSION,
                {"last_error": str(exc), "last_error_at": datetime.now(timezone.utc).isoformat()},
            )
            raise

    return {
        "selected": selected,
        "embedded": embedded,
        "embedding_dim": embedding_dim,
        "seconds": round(time.monotonic() - started, 2),
    }


async def fetch_embedded_prompts(conn: Any, model_id: str, task_type: str | None = None) -> dict[str, list[EmbeddedPrompt]]:
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
          and ($3::text is null or e.task_type = $3::text)
        order by e.task_type, s.quality_score desc, s.uses desc, e.prompt_hash
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        task_type,
    )
    grouped: dict[str, list[EmbeddedPrompt]] = {}
    for row in rows:
        task = row["task_type"] or "unknown"
        grouped.setdefault(task, []).append(
            EmbeddedPrompt(
                prompt_hash=row["prompt_hash"],
                task_type=task,
                prompt=row["prompt"] or "",
                quality_score=float(row["quality_score"] or 0),
                uses=int(row["uses"] or 0),
                users=int(row["users"] or 0),
                last_seen=row["last_seen"],
                embedding=embedding_from_bytes(row["embedding_f16"], int(row["embedding_dim"])),
            )
        )
    return grouped


def _top_k_exact(vectors: np.ndarray, index: int, top_k: int) -> list[tuple[int, float]]:
    query = vectors[index].astype(np.float32)
    matrix = vectors.astype(np.float32)
    sims = matrix @ query
    sims[index] = -1.0
    if len(sims) <= top_k:
        candidate_indexes = np.argsort(-sims)
    else:
        candidate_indexes = np.argpartition(-sims, top_k)[:top_k]
        candidate_indexes = candidate_indexes[np.argsort(-sims[candidate_indexes])]
    return [(int(candidate_index), float(sims[candidate_index])) for candidate_index in candidate_indexes if sims[candidate_index] > -1]


def _build_usearch_edges(
    task_type: str,
    prompts: list[EmbeddedPrompt],
    config: PromptVectorConfig,
) -> list[tuple[str, str, str, str, str, float, int, str]]:
    try:
        from usearch.index import Index
    except ImportError as exc:
        if len(prompts) > config.exact_fallback_limit:
            raise RuntimeError("usearch is required for prompt vector ANN indexing") from exc
        return _build_exact_edges(task_type, prompts, config)

    dim = int(prompts[0].embedding.size)
    vectors = np.stack([item.embedding for item in prompts]).astype(np.float16, copy=False)
    keys = np.asarray([prompt_hash_to_key(item.prompt_hash) for item in prompts], dtype=np.uint64)
    index = Index(ndim=dim, metric="cos", dtype="f16")
    index.add(keys, vectors)

    index_dir = Path(config.data_dir) / config.model_id / PROMPT_NORMALIZATION_VERSION
    index_dir.mkdir(parents=True, exist_ok=True)
    index.save(str(index_dir / f"{task_type}.usearch"))

    key_to_pos = {int(key): pos for pos, key in enumerate(keys.tolist())}
    edges = []
    for source_pos, source in enumerate(prompts):
        matches = index.search(vectors[source_pos], count=min(config.top_k + 1, len(prompts)))
        match_keys = getattr(matches, "keys", matches[0] if isinstance(matches, tuple) else [])
        rank = 0
        for raw_key in match_keys:
            neighbor_pos = key_to_pos.get(int(raw_key))
            if neighbor_pos is None or neighbor_pos == source_pos:
                continue
            neighbor = prompts[neighbor_pos]
            similarity = _cosine_from_normalized(source.embedding, neighbor.embedding)
            if similarity < config.similar_threshold:
                continue
            rank += 1
            edges.append(_edge_tuple(config, task_type, source.prompt_hash, neighbor.prompt_hash, similarity, rank))
            if rank >= config.top_k:
                break
    return edges


def _build_exact_edges(
    task_type: str,
    prompts: list[EmbeddedPrompt],
    config: PromptVectorConfig,
) -> list[tuple[str, str, str, str, str, float, int, str]]:
    vectors = np.stack([item.embedding for item in prompts]).astype(np.float16, copy=False)
    edges = []
    for source_pos, source in enumerate(prompts):
        rank = 0
        for neighbor_pos, similarity in _top_k_exact(vectors, source_pos, config.top_k):
            if similarity < config.similar_threshold:
                continue
            rank += 1
            edges.append(
                _edge_tuple(config, task_type, source.prompt_hash, prompts[neighbor_pos].prompt_hash, similarity, rank)
            )
    return edges


def _cosine_from_normalized(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(left.astype(np.float32), right.astype(np.float32)))


def _edge_tuple(
    config: PromptVectorConfig,
    task_type: str,
    source_hash: str,
    neighbor_hash: str,
    similarity: float,
    rank: int,
) -> tuple[str, str, str, str, str, float, int, str]:
    band = "duplicate" if similarity >= config.duplicate_threshold else "similar"
    return (
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        task_type,
        source_hash,
        neighbor_hash,
        round(float(similarity), 6),
        rank,
        band,
    )


async def refresh_prompt_similarity_edges(conn: Any, config: PromptVectorConfig) -> dict[str, Any]:
    grouped = await fetch_embedded_prompts(conn, config.model_id, config.task_type)
    edge_count = 0
    task_counts: dict[str, int] = {}
    for task_type, prompts in grouped.items():
        if len(prompts) < 2:
            continue
        edges = _build_usearch_edges(task_type, prompts, config)
        await conn.execute(
            """
            delete from analytics_prompt_similarity_edges
            where model_id = $1::text
              and normalization_version = $2::text
              and task_type = $3::text
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            task_type,
        )
        if edges:
            await conn.executemany(
                """
                insert into analytics_prompt_similarity_edges (
                    model_id,
                    normalization_version,
                    task_type,
                    source_hash,
                    neighbor_hash,
                    similarity,
                    rank,
                    band,
                    created_at
                )
                values ($1, $2, $3, $4, $5, $6, $7, $8, now())
                on conflict (model_id, normalization_version, source_hash, neighbor_hash) do update set
                    task_type = excluded.task_type,
                    similarity = excluded.similarity,
                    rank = excluded.rank,
                    band = excluded.band,
                    created_at = now()
                """,
                edges,
            )
        edge_count += len(edges)
        task_counts[task_type] = len(edges)
    return {"edge_count": edge_count, "task_edge_counts": task_counts}


async def refresh_prompt_similarity_clusters(conn: Any, config: PromptVectorConfig) -> dict[str, Any]:
    edge_rows = await conn.fetch(
        """
        select task_type, source_hash, neighbor_hash, similarity::float8 as similarity
        from analytics_prompt_similarity_edges
        where model_id = $1::text
          and normalization_version = $2::text
          and band = 'duplicate'
          and similarity >= $3::numeric
          and ($4::text is null or task_type = $4::text)
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        config.duplicate_threshold,
        config.task_type,
    )
    task_adjacency: dict[str, dict[str, dict[str, float]]] = {}
    edge_similarity: dict[tuple[str, str], float] = {}
    hashes: set[str] = set()
    for row in edge_rows:
        task_type = row["task_type"] or "unknown"
        source_hash = row["source_hash"]
        neighbor_hash = row["neighbor_hash"]
        similarity = float(row["similarity"] or 0)
        if similarity < config.duplicate_threshold:
            continue
        task_adjacency.setdefault(task_type, {}).setdefault(source_hash, {})
        task_adjacency.setdefault(task_type, {}).setdefault(neighbor_hash, {})
        task_adjacency[task_type][source_hash][neighbor_hash] = max(
            similarity,
            task_adjacency[task_type][source_hash].get(neighbor_hash, 0),
        )
        task_adjacency[task_type][neighbor_hash][source_hash] = max(
            similarity,
            task_adjacency[task_type][neighbor_hash].get(source_hash, 0),
        )
        edge_similarity[tuple(sorted((source_hash, neighbor_hash)))] = max(
            similarity,
            edge_similarity.get(tuple(sorted((source_hash, neighbor_hash))), 0),
        )
        hashes.add(source_hash)
        hashes.add(neighbor_hash)

    await _delete_clusters(conn, config)
    if not hashes:
        return {"cluster_count": 0, "member_count": 0}

    stats_rows = await conn.fetch(
        """
        select
            s.prompt_hash,
            s.prompt,
            coalesce(s.task_types[1], 'unknown') as task_type,
            s.quality_score::float8 as quality_score,
            s.uses::bigint as uses,
            s.users::bigint as users,
            s.last_seen,
            e.embedding_dim,
            e.embedding_f16
        from analytics_prompt_slim_candidates s
        left join analytics_prompt_embeddings e
          on e.prompt_hash = s.prompt_hash
         and e.model_id = $2::text
         and e.normalization_version = $3::text
         and e.status = 'embedded'
        where s.prompt_hash = any($1::text[])
        """,
        list(hashes),
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    stats = {}
    for row in stats_rows:
        item = dict(row)
        if item.get("embedding_f16") and item.get("embedding_dim"):
            item["_embedding"] = embedding_from_bytes(item["embedding_f16"], int(item["embedding_dim"]))
        stats[item["prompt_hash"]] = item
    cluster_rows = []
    member_rows = []
    for task_type, adjacency in task_adjacency.items():
        for representative, members in _build_guarded_similarity_groups(adjacency, stats, config.duplicate_threshold):
            representative_row = stats[representative]
            similarities = [
                edge_similarity.get(tuple(sorted((left, right))), 1.0)
                for index, left in enumerate(members)
                for right in members[index + 1 :]
                if edge_similarity.get(tuple(sorted((left, right)))) is not None
            ]
            duplicate_edge_count = len(similarities)
            if not similarities:
                similarities = [1.0]
            cluster_id = stable_cluster_id(config.model_id, PROMPT_NORMALIZATION_VERSION, task_type, representative)
            sorted_members = sorted(
                members,
                key=lambda prompt_hash: (
                    prompt_hash != representative,
                    -_representative_score(stats[prompt_hash])[0],
                    -_representative_score(stats[prompt_hash])[1],
                    -_representative_score(stats[prompt_hash])[2],
                    prompt_hash,
                ),
            )
            cluster_rows.append(
                (
                    cluster_id,
                    config.model_id,
                    PROMPT_NORMALIZATION_VERSION,
                    task_type,
                    representative,
                    representative_row["prompt"] or "",
                    len(members),
                    duplicate_edge_count,
                    round(min(similarities), 6),
                    round(sum(similarities) / len(similarities), 6),
                    round(max(similarities), 6),
                    sum(int(stats[member]["uses"] or 0) for member in members),
                    sum(int(stats[member]["users"] or 0) for member in members),
                    float(representative_row["quality_score"] or 0),
                )
            )
            for rank, member in enumerate(sorted_members, start=1):
                similarity = _member_representative_similarity(representative, member, stats, edge_similarity)
                member_rows.append(
                    (
                        cluster_id,
                        member,
                        task_type,
                        round(float(similarity), 6),
                        member == representative,
                        rank,
                    )
                )

    if cluster_rows:
        await conn.executemany(
            """
            insert into analytics_prompt_similarity_clusters (
                cluster_id,
                model_id,
                normalization_version,
                task_type,
                representative_hash,
                representative_prompt,
                member_count,
                duplicate_edge_count,
                min_similarity,
                avg_similarity,
                max_similarity,
                total_uses,
                total_users,
                quality_score,
                created_at,
                refreshed_at
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, now(), now())
            on conflict (cluster_id) do update set
                representative_hash = excluded.representative_hash,
                representative_prompt = excluded.representative_prompt,
                member_count = excluded.member_count,
                duplicate_edge_count = excluded.duplicate_edge_count,
                min_similarity = excluded.min_similarity,
                avg_similarity = excluded.avg_similarity,
                max_similarity = excluded.max_similarity,
                total_uses = excluded.total_uses,
                total_users = excluded.total_users,
                quality_score = excluded.quality_score,
                refreshed_at = now()
            """,
            cluster_rows,
        )
        await conn.executemany(
            """
            insert into analytics_prompt_similarity_members (
                cluster_id,
                prompt_hash,
                task_type,
                similarity_to_representative,
                is_representative,
                member_rank,
                created_at
            )
            values ($1, $2, $3, $4, $5, $6, now())
            on conflict (cluster_id, prompt_hash) do update set
                similarity_to_representative = excluded.similarity_to_representative,
                is_representative = excluded.is_representative,
                member_rank = excluded.member_rank,
                created_at = now()
            """,
            member_rows,
        )
    return {"cluster_count": len(cluster_rows), "member_count": len(member_rows)}


def _build_guarded_similarity_groups(
    adjacency: dict[str, dict[str, float]],
    stats: dict[str, Any],
    threshold: float,
) -> list[tuple[str, list[str]]]:
    candidates = [prompt_hash for prompt_hash in adjacency if prompt_hash in stats]
    ordered = sorted(candidates, key=lambda prompt_hash: (*_representative_score(stats[prompt_hash]), prompt_hash), reverse=True)
    unassigned = set(ordered)
    groups: list[tuple[str, list[str]]] = []

    for representative in ordered:
        if representative not in unassigned:
            continue

        members = [representative]
        neighbors = [
            neighbor
            for neighbor, similarity in adjacency.get(representative, {}).items()
            if neighbor in unassigned and neighbor in stats and similarity >= threshold
        ]
        neighbors.sort(
            key=lambda neighbor: (
                adjacency[representative].get(neighbor, 0),
                *_representative_score(stats[neighbor]),
                neighbor,
            ),
            reverse=True,
        )

        for neighbor in neighbors:
            if all(adjacency.get(neighbor, {}).get(member, 0) >= threshold for member in members):
                members.append(neighbor)

        unassigned.discard(representative)
        if len(members) < 2:
            continue
        for member in members[1:]:
            unassigned.discard(member)
        groups.append((representative, members))

    return groups


async def _delete_clusters(conn: Any, config: PromptVectorConfig) -> None:
    if config.task_type:
        cluster_ids = await conn.fetch(
            """
            select cluster_id
            from analytics_prompt_similarity_clusters
            where model_id = $1::text
              and normalization_version = $2::text
              and task_type = $3::text
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            config.task_type,
        )
        ids = [row["cluster_id"] for row in cluster_ids]
        if ids:
            await conn.execute("delete from analytics_prompt_similarity_members where cluster_id = any($1::text[])", ids)
        await conn.execute(
            """
            delete from analytics_prompt_similarity_clusters
            where model_id = $1::text
              and normalization_version = $2::text
              and task_type = $3::text
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            config.task_type,
        )
        return

    cluster_ids = await conn.fetch(
        """
        select cluster_id
        from analytics_prompt_similarity_clusters
        where model_id = $1::text
          and normalization_version = $2::text
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    ids = [row["cluster_id"] for row in cluster_ids]
    if ids:
        await conn.execute("delete from analytics_prompt_similarity_members where cluster_id = any($1::text[])", ids)
    await conn.execute(
        """
        delete from analytics_prompt_similarity_clusters
        where model_id = $1::text
          and normalization_version = $2::text
        """,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
    )


def _choose_representative(members: list[str], stats: dict[str, Any]) -> str:
    return max(members, key=lambda prompt_hash: (*_representative_score(stats[prompt_hash]), prompt_hash))


def _member_representative_similarity(
    representative: str,
    member: str,
    stats: dict[str, Any],
    edge_similarity: dict[tuple[str, str], float],
) -> float:
    if member == representative:
        return 1.0
    rep_vector = stats.get(representative, {}).get("_embedding")
    member_vector = stats.get(member, {}).get("_embedding")
    if rep_vector is not None and member_vector is not None:
        return _cosine_from_normalized(rep_vector, member_vector)
    return edge_similarity.get(tuple(sorted((representative, member))), 0.0)


def _representative_score(row: Any) -> tuple[float, int, int, float]:
    last_seen = row["last_seen"]
    if isinstance(last_seen, datetime):
        last_seen_score = last_seen.timestamp()
    else:
        last_seen_score = 0.0
    return (
        float(row["quality_score"] or 0),
        int(row["uses"] or 0),
        int(row["users"] or 0),
        last_seen_score,
    )


async def refresh_prompt_vectors(conn: Any, config: PromptVectorConfig) -> dict[str, Any]:
    await ensure_prompt_vector_schema(conn)
    candidate_count = await _candidate_count(conn, config.task_type)
    status: dict[str, Any] = {
        "model_id": config.model_id,
        "model_key": config.model_key,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "candidate_count": candidate_count,
    }
    await set_vector_state(
        conn,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        {
            "model_id": config.model_id,
            "model_key": config.model_key,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "candidate_count": candidate_count,
            "index_dir": str(Path(config.data_dir) / config.model_id / PROMPT_NORMALIZATION_VERSION),
        },
    )

    if not config.similarity_only and not config.cluster_only:
        client = LMStudioEmbeddingClient(config.base_url, config.model_id, config.model_key)
        if not config.skip_lm_check:
            await asyncio.to_thread(client.check_ready)
        status["embedding"] = await refresh_prompt_embeddings(conn, client, config)

    if not config.embed_only and not config.cluster_only:
        status["similarity"] = await refresh_prompt_similarity_edges(conn, config)

    if not config.embed_only:
        status["clusters"] = await refresh_prompt_similarity_clusters(conn, config)

    embedded_count = await _embedded_count(conn, config.model_id, config.task_type)
    edge_count = int(
        await conn.fetchval(
            """
            select count(*)::bigint
            from analytics_prompt_similarity_edges
            where model_id = $1::text
              and normalization_version = $2::text
              and ($3::text is null or task_type = $3::text)
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            config.task_type,
        )
        or 0
    )
    cluster_count = int(
        await conn.fetchval(
            """
            select count(*)::bigint
            from analytics_prompt_similarity_clusters
            where model_id = $1::text
              and normalization_version = $2::text
              and ($3::text is null or task_type = $3::text)
            """,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            config.task_type,
        )
        or 0
    )
    status.update({"embedded_count": embedded_count, "edge_count": edge_count, "cluster_count": cluster_count})
    await set_vector_state(
        conn,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        {
            "embedded_count": embedded_count,
            "edge_count": edge_count,
            "cluster_count": cluster_count,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return status


def prompt_vector_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh prompt embeddings and semantic similarity clusters.")
    parser.add_argument("--model-id", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_ID", DEFAULT_VECTOR_MODEL_ID))
    parser.add_argument("--model-key", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_KEY", DEFAULT_VECTOR_MODEL_KEY))
    parser.add_argument("--base-url", default=os.getenv("LOCAL_ANALYTICS_LMSTUDIO_BASE_URL", DEFAULT_LM_STUDIO_BASE_URL))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--task-type")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--duplicate-threshold", type=float, default=DEFAULT_DUPLICATE_THRESHOLD)
    parser.add_argument("--similar-threshold", type=float, default=DEFAULT_SIMILAR_THRESHOLD)
    parser.add_argument("--data-dir", default=os.getenv("LOCAL_ANALYTICS_VECTOR_DATA_DIR", DEFAULT_VECTOR_DATA_DIR))
    parser.add_argument("--embed-only", action="store_true")
    parser.add_argument("--similarity-only", action="store_true")
    parser.add_argument("--cluster-only", action="store_true")
    parser.add_argument("--skip-lm-check", action="store_true")
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    return parser


def config_from_args(args: argparse.Namespace) -> PromptVectorConfig:
    modes = [args.embed_only, args.similarity_only, args.cluster_only]
    if sum(1 for enabled in modes if enabled) > 1:
        raise SystemExit("--embed-only, --similarity-only, and --cluster-only are mutually exclusive")
    return PromptVectorConfig(
        model_id=args.model_id,
        model_key=args.model_key,
        base_url=args.base_url,
        batch_size=max(1, int(args.batch_size)),
        limit=args.limit,
        task_type=(args.task_type or "").strip() or None,
        top_k=max(1, int(args.top_k)),
        duplicate_threshold=float(args.duplicate_threshold),
        similar_threshold=float(args.similar_threshold),
        data_dir=args.data_dir,
        embed_only=bool(args.embed_only),
        similarity_only=bool(args.similarity_only),
        cluster_only=bool(args.cluster_only),
        skip_lm_check=bool(args.skip_lm_check),
    )
