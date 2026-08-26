import importlib.util
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "5c2a7e9d1b40_add_history_type_filter_index.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_history_type", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MigrationContext:
    def __init__(self, calls):
        self._calls = calls

    @contextmanager
    def autocommit_block(self):
        self._calls.append(("autocommit", "enter"))
        try:
            yield
        finally:
            self._calls.append(("autocommit", "exit"))


class _Op:
    def __init__(self):
        self.calls = []
        self._context = _MigrationContext(self.calls)

    def get_context(self):
        return self._context

    def create_index(self, *args, **kwargs):
        self.calls.append(("create_index", args, kwargs))

    def drop_index(self, *args, **kwargs):
        self.calls.append(("drop_index", args, kwargs))


def test_history_type_filter_index_is_created_concurrently():
    migration = _load_migration()
    fake_op = _Op()
    migration.op = fake_op

    migration.upgrade()

    create_call = next(call for call in fake_op.calls if call[0] == "create_index")
    assert create_call[1] == ("ix_history_type", "history", ["type"])
    assert create_call[2]["postgresql_concurrently"] is True
    assert fake_op.calls.index(("autocommit", "enter")) < fake_op.calls.index(
        create_call
    )
    assert fake_op.calls.index(create_call) < fake_op.calls.index(
        ("autocommit", "exit")
    )


def test_history_type_filter_index_is_dropped_concurrently():
    migration = _load_migration()
    fake_op = _Op()
    migration.op = fake_op

    migration.downgrade()

    drop_call = next(call for call in fake_op.calls if call[0] == "drop_index")
    assert drop_call[1] == ("ix_history_type",)
    assert drop_call[2]["postgresql_concurrently"] is True
