import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _function(relative_path: str, name: str):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _span(node) -> int:
    return node.end_lineno - node.lineno + 1


def test_qqcc_ai_video_normalizer_stays_a_policy_facade():
    config_facade = _function(
        "src/services/qqcc_config_service.py", "normalize_qqcc_config"
    )
    facade = _function(
        "src/services/qqcc_config_service.py", "_normalize_ai_video_scene"
    )
    policy = _function(
        "src/services/qqcc_ai_video_scene_policy.py",
        "normalize_qqcc_ai_video_scene",
    )

    assert _span(config_facade) <= 60
    assert _span(facade) <= 25
    assert _span(policy) <= 90


def test_quick_video_planning_and_execution_stay_phase_oriented():
    path = "src/services/quick_video_submission_service.py"

    assert _span(_function(path, "_build_qqcc_ai_video_submission_plan")) <= 100
    assert _span(_function(path, "_build_qqcc_video_submission_plan")) <= 120
    assert _span(_function(path, "run_quick_video_submission_plan")) <= 250


def test_worker_h3_patcher_stays_specialized_and_ltx_dead_path_stays_removed():
    h3 = _function(
        "workers/comfy_agent/workflow_minimax_h3_patcher.py",
        "patch_minimax_h3_workflow",
    )
    ltx = _function(
        "workers/comfy_agent/workflow_task_patchers.py",
        "_patch_ltx_t2v_workflow",
    )

    assert _span(h3) <= 50
    assert _span(ltx) <= 90
