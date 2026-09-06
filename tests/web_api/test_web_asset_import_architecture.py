import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(relative_path: str) -> set[str]:
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_web_asset_services_keep_submission_dependencies_one_way():
    character_modules = _imported_modules(
        "src/web_api/services/character_reference_service.py"
    )
    reference_modules = _imported_modules(
        "src/web_api/services/reference_asset_service.py"
    )

    assert "src.web_api.services.task_submission_service" not in character_modules
    assert "src.web_api.services.character_reference_service" not in reference_modules
