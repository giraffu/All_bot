import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "classify_ci_change.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("classify_ci_change", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_governance_changes_use_the_lightweight_ci_path():
    module = _load_module()

    decision = module.classify_change_scope(
        [
            "AGENTS.md",
            ".codex/skills/allbot-ops-deployment/SKILL.md",
            ".github/workflows/control-plane-release.yml",
            "deploy/release-policy.yml",
            "docs/子模块_Git不可变发布_git_immutable_release.md",
            "scripts/classify_ci_change.py",
            "scripts/doc_quality_checker.py",
            "scripts/manage_ai_workspaces.py",
            "scripts/release_strategy.py",
            "scripts/validate_upstream_ci_run.py",
            "tests/ops/test_classify_ci_change.py",
        ]
    )

    assert decision.scope == "lightweight"
    assert decision.requires_full_ci is False
    assert decision.runtime_paths == ()


def test_any_runtime_or_unknown_path_restores_full_ci():
    module = _load_module()

    decision = module.classify_change_scope(
        [
            "docs/README.md",
            "src/core/task_dispatcher.py",
            "deploy/docker-compose-cloud-base.yml",
            "scripts/release.py",
            "unexpected/runtime.bin",
        ]
    )

    assert decision.scope == "runtime"
    assert decision.requires_full_ci is True
    assert decision.runtime_paths == (
        "deploy/docker-compose-cloud-base.yml",
        "scripts/release.py",
        "src/core/task_dispatcher.py",
        "unexpected/runtime.bin",
    )


def test_empty_change_set_fails_closed_to_full_ci():
    module = _load_module()

    decision = module.classify_change_scope([])

    assert decision.scope == "runtime"
    assert decision.requires_full_ci is True
    assert decision.runtime_paths == ("<empty-change-set>",)
