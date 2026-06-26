import pytest

from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import (
    CREATE_PROMPT_VECTOR_SCHEMA_SQL,
    DEFAULT_VECTOR_MODEL_ID,
    CandidatePrompt,
    EmbeddedPrompt,
    PromptVectorConfig,
    _build_exact_edges,
    embedding_from_bytes,
    embedding_to_bytes,
    normalize_embedding,
    refresh_prompt_embeddings,
    refresh_prompt_similarity_clusters,
)


def test_prompt_vector_schema_contains_persistent_tables_and_indexes():
    schema_sql = "\n".join(CREATE_PROMPT_VECTOR_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_embeddings" in schema_sql
    assert "embedding_f16 bytea" in schema_sql
    assert "primary key (model_id, normalization_version, prompt_hash)" in schema_sql
    assert "create table if not exists analytics_prompt_similarity_edges" in schema_sql
    assert "source_hash text not null" in schema_sql
    assert "neighbor_hash text not null" in schema_sql
    assert "band in ('duplicate', 'similar')" in schema_sql
    assert "create table if not exists analytics_prompt_similarity_clusters" in schema_sql
    assert "representative_hash text not null" in schema_sql
    assert "create table if not exists analytics_prompt_similarity_members" in schema_sql
    assert "create table if not exists analytics_prompt_vector_state" in schema_sql
    assert "idx_prompt_embeddings_task" in schema_sql
    assert "idx_prompt_similarity_clusters_task" in schema_sql


def test_prompt_embedding_is_l2_normalized_float16_bytes():
    vector = normalize_embedding([3.0, 4.0])
    assert vector.dtype.name == "float16"
    restored = embedding_from_bytes(embedding_to_bytes(vector), 2)
    assert restored.dtype.name == "float16"
    assert float((restored.astype("float32") ** 2).sum()) == pytest.approx(1.0, abs=0.001)


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


def test_similarity_edges_are_built_inside_one_task_type_only():
    config = PromptVectorConfig(
        model_id=DEFAULT_VECTOR_MODEL_ID,
        top_k=2,
        duplicate_threshold=0.92,
        similar_threshold=0.80,
    )
    prompts = [
        EmbeddedPrompt(
            prompt_hash="a" * 32,
            task_type="edit",
            prompt="portrait",
            quality_score=10,
            uses=5,
            users=2,
            last_seen=None,
            embedding=normalize_embedding([1.0, 0.0]),
        ),
        EmbeddedPrompt(
            prompt_hash="b" * 32,
            task_type="edit",
            prompt="portrait soft light",
            quality_score=8,
            uses=3,
            users=2,
            last_seen=None,
            embedding=normalize_embedding([0.95, 0.05]),
        ),
    ]

    edges = _build_exact_edges("edit", prompts, config)

    assert edges
    assert {edge[2] for edge in edges} == {"edit"}
    assert {edge[3] for edge in edges} <= {"a" * 32, "b" * 32}
    assert {edge[4] for edge in edges} <= {"a" * 32, "b" * 32}
    assert all(edge[3] != edge[4] for edge in edges)
    assert all(edge[7] == "duplicate" for edge in edges)


class FakeClusterConn:
    def __init__(self):
        self.executed = []
        self.executemany_calls = []

    async def fetch(self, query, *args):
        self.executed.append((query, args))
        lower = query.lower()
        if "from analytics_prompt_similarity_edges" in lower:
            return [
                {"task_type": "edit", "source_hash": "a" * 32, "neighbor_hash": "b" * 32, "similarity": 0.95},
                {"task_type": "edit", "source_hash": "b" * 32, "neighbor_hash": "a" * 32, "similarity": 0.95},
                {"task_type": "image", "source_hash": "c" * 32, "neighbor_hash": "d" * 32, "similarity": 0.91},
            ]
        if "select cluster_id" in lower:
            return []
        if "from analytics_prompt_slim_candidates" in lower:
            return [
                {
                    "prompt_hash": "a" * 32,
                    "prompt": "better prompt",
                    "task_type": "edit",
                    "quality_score": 30.0,
                    "uses": 10,
                    "users": 5,
                    "last_seen": None,
                },
                {
                    "prompt_hash": "b" * 32,
                    "prompt": "similar prompt",
                    "task_type": "edit",
                    "quality_score": 10.0,
                    "uses": 50,
                    "users": 9,
                    "last_seen": None,
                },
            ]
        raise AssertionError(f"unexpected query: {query}")

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "OK"

    async def executemany(self, query, rows):
        self.executemany_calls.append((query, rows))


@pytest.mark.asyncio
async def test_similarity_clusters_use_duplicate_edges_and_choose_quality_representative():
    conn = FakeClusterConn()
    config = PromptVectorConfig(model_id=DEFAULT_VECTOR_MODEL_ID, duplicate_threshold=0.92)

    status = await refresh_prompt_similarity_clusters(conn, config)

    assert status == {"cluster_count": 1, "member_count": 2}
    cluster_query, cluster_rows = conn.executemany_calls[0]
    member_query, member_rows = conn.executemany_calls[1]
    assert "analytics_prompt_similarity_clusters" in cluster_query
    assert "analytics_prompt_similarity_members" in member_query
    assert cluster_rows[0][4] == "a" * 32
    assert cluster_rows[0][6] == 2
    assert cluster_rows[0][7] == 1
    assert {row[1] for row in member_rows} == {"a" * 32, "b" * 32}
    assert any(row[1] == "a" * 32 and row[4] is True for row in member_rows)
