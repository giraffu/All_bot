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
from typing import Any, Iterable

import numpy as np

from .prompt_mart import PROMPT_NORMALIZATION_VERSION


DEFAULT_VECTOR_MODEL_KEY = "text-embedding-qwen3-embedding-8b"
DEFAULT_VECTOR_MODEL_ID = "qwen3-embedding-8b"
DEFAULT_LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_VECTOR_DATA_DIR = "/app/data/prompt_vectors"
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
    "create index if not exists idx_prompt_embeddings_task on analytics_prompt_embeddings(model_id, normalization_version, task_type)",
    "create index if not exists idx_prompt_embeddings_status on analytics_prompt_embeddings(status, updated_at desc)",
    "alter table analytics_prompt_embeddings add column if not exists prompt_checksum text not null default ''",
    "alter table analytics_prompt_embeddings add column if not exists embedding_f16 bytea",
    "alter table analytics_prompt_embeddings add column if not exists error text",
    "alter table analytics_prompt_embeddings add column if not exists embedded_at timestamptz",
]


PROMPT_VECTOR_READY_SQL = """
select
    to_regclass('public.analytics_prompt_vector_state') is not null
    and to_regclass('public.analytics_prompt_embeddings') is not null
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
    data_dir: str = DEFAULT_VECTOR_DATA_DIR
    embed_only: bool = False
    skip_lm_check: bool = False


@dataclass(frozen=True)
class CandidatePrompt:
    prompt_hash: str
    task_type: str
    prompt: str


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
        },
    )

    client = LMStudioEmbeddingClient(config.base_url, config.model_id, config.model_key)
    if not config.skip_lm_check:
        await asyncio.to_thread(client.check_ready)
    status["embedding"] = await refresh_prompt_embeddings(conn, client, config)

    embedded_count = await _embedded_count(conn, config.model_id, config.task_type)
    status.update({"embedded_count": embedded_count})
    await set_vector_state(
        conn,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        {
            "embedded_count": embedded_count,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return status


def prompt_vector_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh prompt embeddings.")
    parser.add_argument("--model-id", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_ID", DEFAULT_VECTOR_MODEL_ID))
    parser.add_argument("--model-key", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_KEY", DEFAULT_VECTOR_MODEL_KEY))
    parser.add_argument("--base-url", default=os.getenv("LOCAL_ANALYTICS_LMSTUDIO_BASE_URL", DEFAULT_LM_STUDIO_BASE_URL))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--task-type")
    parser.add_argument("--data-dir", default=os.getenv("LOCAL_ANALYTICS_VECTOR_DATA_DIR", DEFAULT_VECTOR_DATA_DIR))
    parser.add_argument("--embed-only", action="store_true", help="compatibility no-op; embeddings are the only mode")
    parser.add_argument("--skip-lm-check", action="store_true")
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    return parser


def config_from_args(args: argparse.Namespace) -> PromptVectorConfig:
    return PromptVectorConfig(
        model_id=args.model_id,
        model_key=args.model_key,
        base_url=args.base_url,
        batch_size=max(1, int(args.batch_size)),
        limit=args.limit,
        task_type=(args.task_type or "").strip() or None,
        data_dir=args.data_dir,
        embed_only=bool(args.embed_only),
        skip_lm_check=bool(args.skip_lm_check),
    )
