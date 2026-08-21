import importlib.util
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "9b4e6f8a1c20_expand_character_asset_views_and_templates.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("character_asset_views_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_character_asset_migration_adds_optional_slots_and_multi_template_table(monkeypatch):
    module = _load_migration()
    calls = []
    for method in (
        "drop_constraint",
        "create_check_constraint",
        "add_column",
        "execute",
        "create_table",
        "create_index",
    ):
        monkeypatch.setattr(
            module.op,
            method,
            lambda *args, _method=method, **kwargs: calls.append((_method, args, kwargs)),
        )

    module.upgrade()

    constraints = " ".join(str(call) for call in calls if call[0] == "create_check_constraint")
    assert "body_front_nude" in constraints
    assert "body_front_clothed" in constraints
    assert "torso_front" in constraints
    assert "pelvis_back" in constraints
    assert "custom_4" in constraints
    assert any(call[0] == "create_table" and call[1][0] == "character_view_image_templates" for call in calls)
    sql = " ".join(call[1][0] for call in calls if call[0] == "execute")
    assert "SET view_type = 'body_front_nude'" in sql
    assert "body_side" in sql and "body_back" in sql
