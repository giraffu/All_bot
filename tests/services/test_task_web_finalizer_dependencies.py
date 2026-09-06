import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.services import task_web_finalizer_dependencies
from src.services.task_web_finalizer_dependencies import (
    TaskWebFinalizerDependencies,
    configure_task_web_finalizer_dependencies,
    get_task_web_finalizer_dependencies,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_task_web_finalizer_dependencies_fail_closed_before_configuration(
    monkeypatch,
):
    monkeypatch.setattr(
        task_web_finalizer_dependencies,
        "_configured_dependencies",
        None,
    )

    with pytest.raises(RuntimeError, match="not configured"):
        get_task_web_finalizer_dependencies()


def test_task_web_finalizer_dependencies_return_explicit_configuration(monkeypatch):
    monkeypatch.setattr(
        task_web_finalizer_dependencies,
        "_configured_dependencies",
        None,
    )
    dependencies = TaskWebFinalizerDependencies(
        store_prompt_result=AsyncMock(),
        store_prompt_failure_result=AsyncMock(),
        finalize_character_reference=AsyncMock(),
        finalize_official_asset=AsyncMock(),
    )

    configure_task_web_finalizer_dependencies(dependencies)

    assert get_task_web_finalizer_dependencies() is dependencies


def test_task_web_finalizer_hosts_explicitly_configure_web_adapters():
    for relative_path in ("src/web_api/main.py", "src/task_control_worker.py"):
        tree = ast.parse((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "configure_task_web_finalizer_providers" in calls, relative_path
