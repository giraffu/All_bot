from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_maintenance", ROOT / "scripts/release_maintenance.py"
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(module)


def test_maintenance_targets_are_fixed():
    assert module.environment_contract("test") == (
        "allbot-do-sgp1-test-control",
        "/var/lib/allbot/test",
    )
    assert module.environment_contract("prod") == (
        "allbot-do-sgp1-control",
        "/var/lib/allbot/prod",
    )


def test_disable_script_refuses_unknown_owner_and_active_transaction():
    script = module.mutation_script(
        environment="prod",
        enabled=False,
        expected_enabled=True,
        reason="done",
        operation_id="maintenance-one",
    )
    assert "lan-resource-manager" in script
    assert "active release transaction" in script
    assert "GENERATION_MAINTENANCE" in script
    assert "/app/MAINTENANCE" not in script
