import math

from local_analytics_platform.app.prompt_graph import (
    CREATE_PROMPT_GRAPH_SCHEMA_SQL,
    PROMPT_GRAPH_ALGORITHM_VERSION,
    GraphAtom,
    GraphAtomEdge,
    GraphScene,
    build_natural_scene_atom_rows,
    build_scene_layout_rows,
    graph_node_status,
)
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID, normalize_embedding


def test_prompt_graph_schema_contains_graph_tables():
    schema_sql = "\n".join(CREATE_PROMPT_GRAPH_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_graph_state" in schema_sql
    assert "create table if not exists analytics_prompt_graph_nodes" in schema_sql
    assert "create table if not exists analytics_prompt_graph_communities" in schema_sql
    assert "create table if not exists analytics_prompt_graph_memberships" in schema_sql
    assert "create table if not exists analytics_prompt_graph_community_edges" in schema_sql
    assert "create table if not exists analytics_prompt_graph_layout" in schema_sql
    assert PROMPT_GRAPH_ALGORITHM_VERSION in schema_sql
    assert PROMPT_GRAPH_ALGORITHM_VERSION == "prompt-graph-v2"


def test_graph_node_status_preserves_unclustered_candidates():
    assert graph_node_status(has_embedding=False, has_scene=False, has_micro=False) == "unembedded"
    assert graph_node_status(has_embedding=True, has_scene=False, has_micro=False) == "no_scene"
    assert graph_node_status(has_embedding=True, has_scene=True, has_micro=False) == "singleton"
    assert graph_node_status(has_embedding=True, has_scene=True, has_micro=True) == "clustered"


def test_scene_layout_is_deterministic_and_finite():
    scenes = [
        GraphScene("scene-a", "edit", 10, normalize_embedding([1.0, 0.0, 0.0])),
        GraphScene("scene-b", "edit", 8, normalize_embedding([0.0, 1.0, 0.0])),
        GraphScene("scene-c", "video", 6, normalize_embedding([0.0, 0.0, 1.0])),
    ]

    first = build_scene_layout_rows(DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, scenes)
    second = build_scene_layout_rows(DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, scenes)

    assert first == second
    assert {row[4] for row in first} == {"scene-a", "scene-b", "scene-c"}
    for row in first:
        assert math.isfinite(row[6])
        assert math.isfinite(row[7])


def test_natural_scene_atom_rows_are_task_local_and_keep_micro_singletons():
    rows = build_natural_scene_atom_rows(
        [
            GraphAtom("edit", "micro:edit-cluster"),
            GraphAtom("video", "micro:video-cluster"),
        ],
        [
            GraphAtomEdge("edit", "micro:edit-cluster", "prompt:edit-a", 0.88),
            GraphAtomEdge("edit", "prompt:edit-a", "prompt:edit-b", 0.87),
            GraphAtomEdge("video", "micro:video-cluster", "prompt:video-a", 0.88),
        ],
    )

    by_task = {}
    for scene_id, task_type, atom_kind, atom_key, _rank in rows:
        by_task.setdefault(task_type, {}).setdefault(scene_id, set()).add((atom_kind, atom_key))

    assert set(by_task) == {"edit", "video"}
    assert len(by_task["edit"]) == 1
    assert len(by_task["video"]) == 1
    assert next(iter(by_task["edit"].values())) == {
        ("micro", "edit-cluster"),
        ("prompt", "edit-a"),
        ("prompt", "edit-b"),
    }
    assert next(iter(by_task["video"].values())) == {
        ("micro", "video-cluster"),
        ("prompt", "video-a"),
    }


def test_natural_scene_atom_rows_do_not_create_isolated_prompt_scene():
    rows = build_natural_scene_atom_rows(
        [GraphAtom("edit", "micro:isolated-cluster")],
        [GraphAtomEdge("edit", "prompt:a", "prompt:a", 1.0)],
    )

    assert {row[2:4] for row in rows} == {("micro", "isolated-cluster")}
