import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "dashboard" / "backend" / "routers"

# Shrink this set whenever the corresponding router is moved behind an
# application service.  It must never grow.
LEGACY_TRANSACTION_ROUTERS = {
    "private_bots.py",
    "reference_assets.py",
}
TRANSACTION_METHODS = {"add", "commit", "delete", "execute", "flush", "rollback"}


def _uses_transaction_methods(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"db", "session"}
        and node.func.attr in TRANSACTION_METHODS
        for node in ast.walk(tree)
    )


def test_dashboard_router_transaction_debt_only_shrinks():
    actual = {
        path.name
        for path in ROUTERS.glob("*.py")
        if _uses_transaction_methods(path)
    }

    assert actual == LEGACY_TRANSACTION_ROUTERS
