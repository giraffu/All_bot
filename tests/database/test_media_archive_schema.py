import importlib.util
from pathlib import Path

from src.database.models import MediaArchiveOutbox, MediaArchiveReceipt


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "a4c8e2f6b901_add_media_archive_outbox.py"
)


def test_archive_models_have_idempotency_and_delete_gate_constraints():
    outbox_constraints = {
        item.name for item in MediaArchiveOutbox.__table__.constraints
    }
    receipt_constraints = {
        item.name for item in MediaArchiveReceipt.__table__.constraints
    }

    assert "uq_media_archive_outbox_history" in outbox_constraints
    assert "uq_media_archive_receipt_asset" in receipt_constraints
    assert MediaArchiveReceipt.__table__.c.sha256.nullable is False
    assert MediaArchiveReceipt.__table__.c.verified_at.nullable is False
    assert MediaArchiveOutbox.__table__.c.manifest_hash.nullable is False


def test_archive_migration_creates_outbox_before_receipts():
    spec = importlib.util.spec_from_file_location(
        "media_archive_migration", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    calls = []
    original = module.op.create_table
    module.op.create_table = lambda name, *args, **kwargs: calls.append(name)
    module.op.create_index = lambda *args, **kwargs: None
    try:
        module.upgrade()
    finally:
        module.op.create_table = original

    assert calls == ["media_archive_outbox", "media_archive_receipts"]
