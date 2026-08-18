import importlib.util
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "d1e2f3a4b5c6_harden_gallery_uniqueness.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("gallery_consistency_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Context:
    def __init__(self, calls):
        self.calls = calls

    @contextmanager
    def autocommit_block(self):
        self.calls.append(("autocommit", "enter"))
        try:
            yield
        finally:
            self.calls.append(("autocommit", "exit"))


class _Op:
    def __init__(self):
        self.calls = []
        self.context = _Context(self.calls)
        self.bind = type(
            "Bind", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()}
        )()

    def get_bind(self):
        return self.bind

    def get_context(self):
        return self.context

    def execute(self, statement):
        self.calls.append(("execute", str(statement)))

    def create_index(self, *args, **kwargs):
        self.calls.append(("create_index", args, kwargs))


def test_gallery_unique_indexes_fail_closed_and_build_concurrently():
    migration = _load_migration()
    fake_op = _Op()
    migration.op = fake_op

    migration.upgrade()

    execute = next(call for call in fake_op.calls if call[0] == "execute")
    assert "duplicate posts" in execute[1]
    indexes = [call for call in fake_op.calls if call[0] == "create_index"]
    assert [call[1][0] for call in indexes] == [
        "uq_gallery_posts_task_user",
        "uq_user_interactions_apply",
        "uq_user_interactions_reaction",
    ]
    assert all(call[2]["postgresql_concurrently"] is True for call in indexes)
    assert fake_op.calls.index(("autocommit", "enter")) < fake_op.calls.index(execute)
    assert fake_op.calls.index(indexes[-1]) < fake_op.calls.index(
        ("autocommit", "exit")
    )


def test_gallery_orm_uses_the_same_partial_unique_indexes():
    from src.database.models import GalleryPost, UserInteraction

    post_indexes = {index.name: index for index in GalleryPost.__table__.indexes}
    interaction_indexes = {
        index.name: index for index in UserInteraction.__table__.indexes
    }

    assert post_indexes["uq_gallery_posts_task_user"].unique is True
    assert interaction_indexes["uq_user_interactions_apply"].unique is True
    assert interaction_indexes["uq_user_interactions_reaction"].unique is True
    assert "action_type = 'apply'" in str(
        interaction_indexes["uq_user_interactions_apply"].dialect_options[
            "postgresql"
        ]["where"]
    )
    assert "like" in str(
        interaction_indexes["uq_user_interactions_reaction"].dialect_options[
            "postgresql"
        ]["where"]
    )
