import importlib.util
from pathlib import Path


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "6f4b0d9d8c21_add_media_metadata_to_history.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "history_media_metadata_migration",
        MIGRATION_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_history_media_metadata_migration_uses_ranked_gallery_post_backfill(monkeypatch):
    module = _load_migration_module()
    executed_sql = []

    monkeypatch.setattr(module.op, "add_column", lambda *args, **kwargs: None)
    monkeypatch.setattr(module.op, "execute", executed_sql.append)

    module.upgrade()

    assert executed_sql
    sql = executed_sql[0]
    assert "ROW_NUMBER() OVER" in sql
    assert "PARTITION BY gp.task_id" in sql
    assert "CASE WHEN gp.is_active THEN 1 ELSE 0 END DESC" in sql
    assert "billing_resolution = CASE" in sql
    assert "'custom_video'" in sql
    assert "'video_insert'" in sql
    assert "THEN '720'" in sql
    assert "ranked.row_num = 1" in sql
