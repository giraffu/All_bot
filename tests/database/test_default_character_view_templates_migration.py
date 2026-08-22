import importlib.util
from pathlib import Path
from unittest.mock import MagicMock


MIGRATION = (
    Path(__file__).parents[2]
    / "migrations"
    / "versions"
    / "a6d2f8c4e1b9_add_default_character_view_templates.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("default_character_templates", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_default_character_template_migration_adds_one_default_per_view_type(monkeypatch):
    migration = _load_migration()
    op = MagicMock()
    monkeypatch.setattr(migration, "op", op)

    migration.upgrade()

    column = op.add_column.call_args.args[1]
    assert column.name == "is_default"
    assert column.nullable is False
    op.create_index.assert_called_once()
    args, kwargs = op.create_index.call_args
    assert args[:3] == (
        "uq_character_view_image_templates_default_type",
        "character_view_image_templates",
        ["view_type"],
    )
    assert kwargs["unique"] is True
    assert str(kwargs["postgresql_where"]) == "is_default"
