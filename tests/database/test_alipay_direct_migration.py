import importlib.util
from pathlib import Path
from types import SimpleNamespace


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "f3a4b5c6d7e8_add_alipay_direct_payment_routing.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("alipay_direct_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_alipay_direct_migration_is_additive_and_backfills_only_rmb_orders():
    module = _load_migration()
    calls = []
    module.op = SimpleNamespace(
        add_column=lambda table, column: calls.append(
            (
                "add_column",
                table,
                column.name,
                column.nullable,
                str(column.server_default.arg) if column.server_default else None,
            )
        ),
        create_index=lambda *args, **kwargs: calls.append(("create_index", args, kwargs)),
        create_check_constraint=lambda *args, **kwargs: calls.append(
            ("create_check_constraint", args, kwargs)
        ),
        execute=lambda statement: calls.append(("execute", str(statement))),
    )

    module.upgrade()

    assert module.down_revision == "e2f3a4b5c6d7"
    assert (
        "add_column",
        "users",
        "alipay_direct_enabled",
        False,
        "false",
    ) in calls
    assert any(
        call[:4] == ("add_column", "orders", "payment_provider", True)
        for call in calls
    )
    backfill = next(call[1] for call in calls if call[0] == "execute")
    assert "payment_channel = 'RMB'" in backfill
    assert "payment_provider IS NULL" in backfill
