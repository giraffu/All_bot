import pytest
import asyncpg

from local_analytics_platform.app.refresh_prompt_vectors import _is_closed_connection_error
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import (
    CREATE_PROMPT_VECTOR_SCHEMA_SQL,
    DEFAULT_VECTOR_MODEL_ID,
    PromptVectorConfig,
    config_from_args,
    embedding_from_bytes,
    embedding_to_bytes,
    normalize_embedding,
    prompt_vector_arg_parser,
    refresh_prompt_embeddings,
)


def test_prompt_vector_schema_contains_persistent_tables_and_indexes():
    schema_sql = "\n".join(CREATE_PROMPT_VECTOR_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_embeddings" in schema_sql
    assert "embedding_f16 bytea" in schema_sql
    assert "primary key (model_id, normalization_version, prompt_hash)" in schema_sql
    assert "create table if not exists analytics_prompt_vector_state" in schema_sql
    assert "idx_prompt_embeddings_task" in schema_sql
    assert "analytics_prompt_similarity_edges" not in schema_sql
    assert "analytics_prompt_similarity_clusters" not in schema_sql
    assert "analytics_prompt_similarity_members" not in schema_sql


def test_prompt_embedding_is_l2_normalized_float16_bytes():
    vector = normalize_embedding([3.0, 4.0])
    assert vector.dtype.name == "float16"
    restored = embedding_from_bytes(embedding_to_bytes(vector), 2)
    assert restored.dtype.name == "float16"
    assert float((restored.astype("float32") ** 2).sum()) == pytest.approx(1.0, abs=0.001)


def test_refresh_prompt_vectors_treats_asyncpg_connection_errors_as_retryable():
    assert _is_closed_connection_error(asyncpg.ConnectionDoesNotExistError("server closed"))
    assert _is_closed_connection_error(asyncpg.InterfaceError("connection is closed"))


class FakeEmbeddingConn:
    def __init__(self):
        self.executed = []
        self.executemany_calls = []

    async def fetch(self, query, *args):
        self.executed.append((query, args))
        assert "not exists" in query.lower()
        assert args[0] == PROMPT_NORMALIZATION_VERSION
        assert args[2] == DEFAULT_VECTOR_MODEL_ID
        return [
            {"prompt_hash": "a" * 32, "task_type": "edit", "prompt": "cinematic portrait"},
            {"prompt_hash": "b" * 32, "task_type": "edit", "prompt": "cinematic portrait, soft light"},
        ]

    async def executemany(self, query, rows):
        self.executemany_calls.append((query, rows))

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "OK"


class FakeEmbeddingClient:
    def embed(self, texts):
        assert texts == ["cinematic portrait", "cinematic portrait, soft light"]
        return [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]]


@pytest.mark.asyncio
async def test_refresh_prompt_embeddings_batches_and_stores_float16_vectors():
    conn = FakeEmbeddingConn()
    config = PromptVectorConfig(model_id=DEFAULT_VECTOR_MODEL_ID, batch_size=2, limit=2, skip_lm_check=True)

    status = await refresh_prompt_embeddings(conn, FakeEmbeddingClient(), config)

    assert status["selected"] == 2
    assert status["embedded"] == 2
    assert status["embedding_dim"] == 3
    query, rows = conn.executemany_calls[0]
    assert "analytics_prompt_embeddings" in query
    assert rows[0][0] == "a" * 32
    assert rows[0][6] == 3
    assert rows[0][7] == "float16"
    assert embedding_from_bytes(rows[0][8], 3).dtype.name == "float16"


def test_prompt_vector_cli_keeps_embed_only_compatibility_and_rejects_similarity_modes():
    parser = prompt_vector_arg_parser()

    config = config_from_args(parser.parse_args(["--embed-only"]))
    assert config.embed_only is True

    with pytest.raises(SystemExit):
        parser.parse_args(["--similarity-only"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--cluster-only"])
