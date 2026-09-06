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


def _src_import_components() -> list[set[str]]:
    paths = list((ROOT / "src").rglob("*.py"))
    modules = {
        ".".join(path.relative_to(ROOT).with_suffix("").parts): path
        for path in paths
    }
    graph = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported: set[str] = set()
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(
                    f"{node.module}.{alias.name}" for alias in node.names
                )
            graph[module].update(imported & modules.keys())

    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    def visit(module: str) -> None:
        nonlocal index
        indices[module] = index
        lowlinks[module] = index
        index += 1
        stack.append(module)
        on_stack.add(module)
        for dependency in graph[module]:
            if dependency not in indices:
                visit(dependency)
                lowlinks[module] = min(lowlinks[module], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[module] = min(lowlinks[module], indices[dependency])
        if lowlinks[module] != indices[module]:
            return
        component: set[str] = set()
        while stack:
            dependency = stack.pop()
            on_stack.remove(dependency)
            component.add(dependency)
            if dependency == module:
                break
        components.append(component)

    for module in graph:
        if module not in indices:
            visit(module)
    return components


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


def test_task_web_finalizer_does_not_import_web_layer_services():
    modules = _imported_modules("src/services/task_web_finalizer.py")

    assert not {module for module in modules if module.startswith("src.web_api")}


def test_quick_video_submission_router_stays_below_hotspot_budget():
    tree = ast.parse(
        (ROOT / "src/services/quick_video_submission_service.py").read_text(
            encoding="utf-8"
        )
    )
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_quick_video_submission_plan"
    )

    assert builder.end_lineno - builder.lineno + 1 <= 45
    assert sum(isinstance(node, ast.If) for node in ast.walk(builder)) <= 2


def test_continuation_policies_do_not_import_task_executor_implementations():
    executor_modules = {
        "src.services.task_service_generation_image",
        "src.services.task_service_entrypoints_video",
        "src.services.task_service_entrypoints_specialized",
        "src.services.wan22_video_v2_extension_service",
    }

    assert _imported_modules(
        "src/services/private_qqcc_continuation_service.py"
    ).isdisjoint(executor_modules)
    assert "src.services.task_service_generation_image" not in _imported_modules(
        "src/services/scail2_face_swap_pipeline_service.py"
    )


def test_task_execution_import_cycles_stay_below_module_budget():
    task_components = [
        component
        for component in _src_import_components()
        if any(
            module.startswith(("src.services.task_", "src.task_"))
            for module in component
        )
    ]

    assert max(map(len, task_components), default=1) < 10
