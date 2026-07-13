from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = PROJECT_ROOT / "src" / "core"
FORBIDDEN_PLATFORM_MODULES = ("fastapi", "telegram")


def _import_root(module: str | None) -> str:
    return (module or "").split(".", 1)[0]


def test_core_does_not_import_web_or_telegram_platform_modules():
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
                if _import_root(module) in FORBIDDEN_PLATFORM_MODULES:
                    rel_path = path.relative_to(PROJECT_ROOT)
                    violations.append(f"{rel_path}:{node.lineno} imports {module}")

    assert violations == []
