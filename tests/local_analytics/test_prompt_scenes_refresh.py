from datetime import datetime, timezone

from local_analytics_platform.app.prompt_scenes import (
    CREATE_PROMPT_SCENE_SCHEMA_SQL,
    DEFAULT_MAX_SCENES_PER_TASK,
    PROMPT_SCENE_ALGORITHM_VERSION,
    PromptSceneConfig,
    ScenePrompt,
    allocate_scene_targets,
    build_semantic_scene_rows,
    select_scene_seeds,
)
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID, normalize_embedding


def scene_prompt(
    suffix: str,
    vector,
    *,
    task_type: str = "edit",
    quality_score: float = 10.0,
    uses: int = 1,
    users: int = 1,
) -> ScenePrompt:
    return ScenePrompt(
        prompt_hash=f"{suffix:0<32}"[:32],
        task_type=task_type,
        prompt=f"prompt {suffix}",
        quality_score=quality_score,
        uses=uses,
        users=users,
        last_seen=datetime(2026, 6, 29, tzinfo=timezone.utc),
        embedding=normalize_embedding(vector),
    )


def test_prompt_scene_schema_contains_scene_tables_and_state():
    schema_sql = "\n".join(CREATE_PROMPT_SCENE_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_semantic_scenes" in schema_sql
    assert "manual_label text" in schema_sql
    assert "centroid_f16 bytea" in schema_sql
    assert "create table if not exists analytics_prompt_semantic_scene_members" in schema_sql
    assert "candidate_rank integer" in schema_sql
    assert "confidence_band in ('high', 'medium', 'low')" in schema_sql
    assert "create table if not exists analytics_prompt_semantic_scene_state" in schema_sql


def test_scene_target_allocation_is_sqrt_weighted_and_capped():
    targets = allocate_scene_targets(
        {
            "edit": 211_422,
            "img2img_lora": 153_147,
            "custom_video": 132_036,
            "tiny": 1,
        },
        target_total=1_000,
        max_per_task=DEFAULT_MAX_SCENES_PER_TASK,
    )

    assert sum(targets.values()) <= 1_000
    assert targets["edit"] <= DEFAULT_MAX_SCENES_PER_TASK
    assert targets["img2img_lora"] <= DEFAULT_MAX_SCENES_PER_TASK
    assert targets["tiny"] == 1
    assert targets["edit"] >= targets["custom_video"] >= targets["tiny"]


def test_scene_seed_selection_filters_near_duplicates_then_relaxes_when_needed():
    config = PromptSceneConfig(
        model_id=DEFAULT_VECTOR_MODEL_ID,
        strict_seed_max_similarity=0.78,
        relaxed_seed_max_similarity=0.95,
        seed_relax_trigger_ratio=0.80,
        min_seed_pool_size=10,
        seed_pool_multiplier=10,
    )
    prompts = [
        scene_prompt("a", [1.0, 0.0], quality_score=100),
        scene_prompt("b", [0.99, 0.01], quality_score=99),
        scene_prompt("c", [0.0, 1.0], quality_score=98),
    ]

    seeds = select_scene_seeds(prompts, 3, config)

    assert [seed.prompt_hash[0] for seed in seeds] == ["a", "c", "b"]


def test_scene_assignment_does_not_depend_on_top_k_similarity_edges():
    config = PromptSceneConfig(
        model_id=DEFAULT_VECTOR_MODEL_ID,
        target_scene_count=1,
        candidates_per_scene=30,
        assignment_batch_size=4,
    )
    prompts = [
        scene_prompt("a", [1.0, 0.0], quality_score=100, uses=10, users=8),
        scene_prompt("b", [0.95, 0.05], quality_score=90, uses=9, users=7),
        scene_prompt("c", [0.90, 0.10], quality_score=80, uses=8, users=6),
        scene_prompt("d", [0.85, 0.15], quality_score=70, uses=7, users=5),
    ]

    result = build_semantic_scene_rows(prompts, target_count=1, config=config)

    assert len(result.scene_rows) == 1
    assert len(result.member_rows) == 4
    assert result.scene_rows[0][7] == 4
    assert {row[1][0] for row in result.member_rows} == {"a", "b", "c", "d"}
    assert PROMPT_SCENE_ALGORITHM_VERSION in result.scene_rows[0]


def test_scene_top_candidates_prefer_confidence_then_quality_signals():
    config = PromptSceneConfig(
        model_id=DEFAULT_VECTOR_MODEL_ID,
        target_scene_count=1,
        candidates_per_scene=2,
        high_confidence_threshold=0.70,
        medium_confidence_threshold=0.55,
        assignment_batch_size=8,
    )
    prompts = [
        scene_prompt("a", [1.0, 0.0], quality_score=100, uses=1, users=1),
        scene_prompt("b", [0.95, 0.05], quality_score=10, uses=1, users=1),
        scene_prompt("c", [0.90, 0.10], quality_score=90, uses=20, users=10),
        scene_prompt("d", [0.40, 0.60], quality_score=200, uses=50, users=30),
    ]

    result = build_semantic_scene_rows(prompts, target_count=1, config=config)
    ranked_candidates = [row for row in result.member_rows if row[6] is not None]

    assert len(ranked_candidates) == 2
    assert [row[6] for row in ranked_candidates] == [1, 2]
    assert {row[4] for row in ranked_candidates} <= {"high", "medium"}
