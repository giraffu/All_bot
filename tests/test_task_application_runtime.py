import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.task_application import TaskApplication
from src import task_application_runtime


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_task_application_runtime_fails_closed_before_explicit_configuration(
    monkeypatch,
):
    monkeypatch.setattr(task_application_runtime, "_configured_task_application", None)

    with pytest.raises(RuntimeError, match="TaskApplication is not configured"):
        task_application_runtime.get_task_application()


def test_configure_task_application_builds_once_from_explicit_dependencies(monkeypatch):
    dependencies = MagicMock()
    monkeypatch.setattr(task_application_runtime, "_configured_task_application", None)
    build_dependencies = MagicMock(return_value=dependencies)
    monkeypatch.setattr(
        task_application_runtime,
        "build_runtime_default_task_core_process_dependencies",
        build_dependencies,
    )

    configured = task_application_runtime.configure_task_application()
    configured_again = task_application_runtime.configure_task_application()

    assert isinstance(configured, TaskApplication)
    assert configured_again is configured
    assert task_application_runtime.get_task_application() is configured
    build_dependencies.assert_called_once_with()


def test_all_task_serving_entrypoints_explicitly_configure_task_application():
    entrypoints = (
        "src/web_api/main.py",
        "src/bot_main.py",
        "qqcc_bot/main.py",
        "dashboard/backend/main.py",
    )
    for relative_path in entrypoints:
        tree = ast.parse((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "configure_task_application" in calls, relative_path


def test_production_code_no_longer_imports_legacy_submission_facade():
    roots = (
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "dashboard",
        PROJECT_ROOT / "qqcc_bot",
    )
    violations = []
    for root in roots:
        for path in root.rglob("*.py"):
            if path == PROJECT_ROOT / "src/core/task_core.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if any(alias.name == "process_and_submit_task" for alias in node.names):
                    violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert violations == []
