from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = PROJECT_ROOT / "src" / "core"
FORBIDDEN_PLATFORM_MODULES = (
    "PIL",
    "config",
    "fastapi",
    "httpx",
    "sqlalchemy",
    "src.database",
    "src.services",
    "telegram",
)


def _is_forbidden(module: str | None) -> bool:
    normalized = str(module or "")
    return any(
        normalized == forbidden or normalized.startswith(f"{forbidden}.")
        for forbidden in FORBIDDEN_PLATFORM_MODULES
    )


def test_core_does_not_import_platform_or_infrastructure_modules():
    violations: list[str] = []
    for path in sorted(CORE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module]
            else:
                continue
            for module in modules:
                if _is_forbidden(module):
                    rel_path = path.relative_to(PROJECT_ROOT)
                    violations.append(f"{rel_path}:{node.lineno} imports {module}")

    assert violations == []
