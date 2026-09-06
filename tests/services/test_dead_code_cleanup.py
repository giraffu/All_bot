import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _imported_names(relative_path: str) -> set[str]:
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _imported_modules(relative_path: str) -> set[str]:
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_confirmed_unused_imports_stay_removed():
    assert _imported_names("media_enhance_platform/backend/app/api.py").isdisjoint(
        {"os", "secrets", "Form", "AuditLog", "TaskType"}
    )
    assert "BinaryIO" not in _imported_names(
        "media_enhance_platform/backend/app/storage.py"
    )
    assert "AdvancedVideoProSubmissionError" not in _imported_names(
        "src/handlers/callbacks/advanced_video_prompt_callbacks.py"
    )


def test_quota_manager_has_no_empty_initializer():
    tree = ast.parse((ROOT / "src" / "quota.py").read_text(encoding="utf-8"))
    quota_manager = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "QuotaManager"
    )

    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "__init__"
        for node in quota_manager.body
    )


def test_web_submission_orchestrator_stays_below_hotspot_budget():
    tree = ast.parse(
        (ROOT / "src/web_api/services/task_submission_service.py").read_text(
            encoding="utf-8"
        )
    )
    submit = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "submit_generation_task"
    )

    assert submit.end_lineno - submit.lineno + 1 <= 140
    assert sum(isinstance(node, ast.If) for node in ast.walk(submit)) <= 5


def test_reference_assets_depend_on_prompt_media_policy_not_orchestrator():
    modules = _imported_modules(
        "src/web_api/services/reference_asset_service.py"
    )

    assert "src.web_api.services.prompt_media_policy" in modules
    assert "src.web_api.services.prompt_optimization_service" not in modules
