import fcntl

from scripts import run_local_analytics_shadow_pipeline as pipeline


def build_config(tmp_path, **overrides):
    values = {
        "execute": True,
        "restore_from_db": "bot_db_prod_shadow_previous_20260627_050741",
        "batch_size": 128,
        "shadow_db": "bot_db_prod_shadow",
        "postgres_container": "allbot-postgres-prod-shadow-pg18",
        "analytics_container": "allbot-local-analytics-platform",
        "backup_root": tmp_path / "backups",
        "log_path": tmp_path / "pipeline.log",
        "vector_lock_path": tmp_path / "prompt_vectors" / ".refresh_prompt_vectors.lock",
    }
    values.update(overrides)
    return pipeline.PipelineConfig(**values)


class FakeRunner:
    def __init__(self):
        self.commands = []

    def run(self, cmd, *, label=None):
        self.commands.append((label, list(cmd)))

    def capture(self, cmd, *, label=None):
        self.commands.append((label, list(cmd)))
        return "img2img\nltx_video\n"


def rendered(fake):
    return "\n".join(" ".join(cmd) for _, cmd in fake.commands)


def test_pipeline_restores_refreshes_embeddings_in_order(tmp_path):
    fake = FakeRunner()
    config = build_config(tmp_path)

    result = pipeline.run_pipeline(
        config,
        runner=fake,
        lm_studio_checker=lambda _: True,
    )

    commands = rendered(fake)
    assert result["embedding"] == "attempted"
    assert "copy-local-analytics" in [label for label, _ in fake.commands]
    assert "analytics_prompt_embeddings" in commands
    assert "analytics_prompt_slim_candidates" in commands
    assert "analytics_user_profile_daily_snapshots" in commands
    assert "analytics_prompt_similarity_edges" not in commands
    assert "analytics_prompt_semantic_scenes" not in commands
    assert "analytics_prompt_graph_nodes" not in commands
    assert "local_analytics_tables.txt" in commands
    assert "--table=public.$table_name" in commands
    assert "python -m app.refresh_user_profile_snapshots --statement-timeout-ms" in commands
    assert "python -m app.refresh_prompt_mart --statement-timeout-ms" in commands
    assert "refresh_prompt_mart --full" not in commands
    assert "python -m app.refresh_prompt_slim_table" in commands
    assert "python -m app.refresh_prompt_vectors --embed-only --batch-size 128" in commands
    assert "refresh_prompt_scenes" not in commands
    assert "similarity-only" not in commands
    assert "refresh_prompt_graph" not in commands
    assert commands.index("refresh_user_profile_snapshots") < commands.index("refresh_prompt_mart")
    assert commands.index("refresh_prompt_mart") < commands.index("refresh_prompt_slim_table")
    assert commands.index("refresh_prompt_slim_table") < commands.index("refresh_prompt_vectors --embed-only")


def test_pipeline_skips_embedding_when_lm_studio_is_unavailable(tmp_path):
    fake = FakeRunner()
    config = build_config(tmp_path, restore_from_db=None)

    result = pipeline.run_pipeline(
        config,
        runner=fake,
        lm_studio_checker=lambda _: False,
    )

    commands = rendered(fake)
    assert result["embedding"] == "skipped_lm_studio_unavailable"
    assert "scenes" not in result
    assert "refresh_prompt_mart --statement-timeout-ms" in commands
    assert "refresh_user_profile_snapshots --statement-timeout-ms" in commands
    assert "refresh_prompt_mart --full" not in commands
    assert "refresh_prompt_slim_table" in commands
    assert "refresh_prompt_vectors --embed-only" not in commands
    assert "refresh_prompt_scenes" not in commands
    assert "similarity-only" not in commands
    assert "refresh_prompt_graph" not in commands


def test_pipeline_can_force_full_mart_refresh(tmp_path):
    fake = FakeRunner()
    config = build_config(tmp_path, mart_full=True)

    pipeline.run_pipeline(
        config,
        runner=fake,
        lm_studio_checker=lambda _: False,
    )

    commands = rendered(fake)
    assert "python -m app.refresh_prompt_mart --full --statement-timeout-ms" in commands


def test_pipeline_lock_prevents_overlapping_runs(tmp_path):
    config = build_config(tmp_path, restore_from_db=None)
    config.backup_root.mkdir(parents=True)
    lock_path = config.pipeline_lock_path
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = pipeline.run_pipeline(
            config,
            runner=FakeRunner(),
            lm_studio_checker=lambda _: True,
        )
        fcntl.flock(handle, fcntl.LOCK_UN)

    assert result["status"] == "skipped_lock_held"


def test_vector_lock_prevents_refresh_chain_from_starting(tmp_path):
    fake = FakeRunner()
    config = build_config(tmp_path, restore_from_db=None)
    config.vector_lock_path.parent.mkdir(parents=True)

    with config.vector_lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = pipeline.run_pipeline(
            config,
            runner=fake,
            lm_studio_checker=lambda _: True,
        )
        fcntl.flock(handle, fcntl.LOCK_UN)

    assert result["status"] == "skipped_vector_lock_held"
    assert len(fake.commands) == 1
    assert "refresh_user_profile_snapshots" in rendered(fake)
