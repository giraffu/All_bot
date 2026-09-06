import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "3c7e9a1b5d20_link_gallery_posts_to_history.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("gallery_history_link", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Op:
    def __init__(self):
        self.calls = []

    def add_column(self, *args, **kwargs):
        self.calls.append(("add_column", args, kwargs))

    def create_foreign_key(self, *args, **kwargs):
        self.calls.append(("create_foreign_key", args, kwargs))

    def create_index(self, *args, **kwargs):
        self.calls.append(("create_index", args, kwargs))

    def execute(self, statement):
        self.calls.append(("execute", str(statement)))


def test_gallery_history_link_backfills_only_unambiguous_owned_history():
    migration = _load_migration()
    fake_op = _Op()
    migration.op = fake_op

    migration.upgrade()

    sql = next(call[1].lower() for call in fake_op.calls if call[0] == "execute")
    assert "h.task_id = gp.task_id" in sql
    assert "h.user_id = gp.user_id" in sql
    assert "having count(h.id) = 1" in sql
    assert migration.down_revision == "2a6c8e1f4b90"

    fk = next(call for call in fake_op.calls if call[0] == "create_foreign_key")
    assert fk[1][0] == "fk_gallery_posts_history_id_history"
    assert fk[2]["ondelete"] == "SET NULL"
