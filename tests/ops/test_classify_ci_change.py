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
            "deploy/test-acceptance.example.json",
            "docs/子模块_Git不可变发布_git_immutable_release.md",
            "scripts/classify_ci_change.py",
            "scripts/doc_quality_checker.py",
            "scripts/manage_ai_workspaces.py",
            "scripts/release.py",
            "scripts/validate_upstream_ci_run.py",
            "tests/ops/test_classify_ci_change.py",
        ]
    )

    assert decision.scope == "lightweight"
    assert decision.requires_full_ci is False
    assert decision.requires_operator_ci is False
    assert decision.requires_release_bundle is False
    assert decision.operator_paths == ()
    assert decision.runtime_paths == ()


def test_git_quoted_unicode_doc_path_uses_the_lightweight_ci_path():
    module = _load_module()

    decision = module.classify_change_scope(
        [
            '"docs/\\345\\255\\220\\346\\250\\241\\345\\235\\227_'
            'Git\\344\\270\\215\\345\\217\\257\\345\\217\\230'
            '\\345\\217\\221\\345\\270\\203_git_immutable_release.md"'
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
            "unexpected/runtime.bin",
        ]
    )

    assert decision.scope == "runtime"
    assert decision.requires_full_ci is True
    assert decision.requires_operator_ci is False
    assert decision.requires_release_bundle is True
    assert decision.operator_paths == ()
    assert decision.runtime_paths == (
        "deploy/docker-compose-cloud-base.yml",
        "src/core/task_dispatcher.py",
        "unexpected/runtime.bin",
    )


def test_empty_change_set_fails_closed_to_full_ci():
    module = _load_module()

    decision = module.classify_change_scope([])

    assert decision.scope == "runtime"
    assert decision.requires_full_ci is True
    assert decision.requires_operator_ci is False
    assert decision.requires_release_bundle is True
    assert decision.runtime_paths == ("<empty-change-set>",)


def test_gpu_operator_changes_use_focused_ci_but_still_build_release_artifacts():
    module = _load_module()

    decision = module.classify_change_scope(
        [
            "docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md",
            "ops/gpu_pool_controller/lan_aio_prod.py",
            "scripts/lan_aio_fleet_prod_ops.py",
            "tests/ops/test_lan_aio_prod.py",
        ]
    )

    assert decision.scope == "operator"
    assert decision.requires_full_ci is False
    assert decision.requires_operator_ci is True
    assert decision.requires_release_bundle is True
    assert decision.operator_paths == (
        "ops/gpu_pool_controller/lan_aio_prod.py",
        "scripts/lan_aio_fleet_prod_ops.py",
    )
    assert decision.runtime_paths == ()


def test_operator_and_application_changes_restore_full_ci():
    module = _load_module()

    decision = module.classify_change_scope(
        [
            "ops/gpu_pool_controller/runtime.py",
            "src/core/task_dispatcher.py",
        ]
    )

    assert decision.scope == "runtime"
    assert decision.requires_full_ci is True
    assert decision.requires_operator_ci is False
    assert decision.requires_release_bundle is True
    assert decision.operator_paths == ("ops/gpu_pool_controller/runtime.py",)
    assert decision.runtime_paths == ("src/core/task_dispatcher.py",)


def test_shared_release_strategy_change_keeps_full_ci():
    module = _load_module()

    decision = module.classify_change_scope(["scripts/release_strategy.py"])

    assert decision.scope == "runtime"
    assert decision.requires_full_ci is True
    assert decision.requires_operator_ci is False
    assert decision.requires_release_bundle is True
    assert decision.operator_paths == ()
    assert decision.runtime_paths == ("scripts/release_strategy.py",)


def test_gpu_release_artifact_catalog_change_keeps_full_ci():
    module = _load_module()

    decision = module.classify_change_scope(["deploy/release-artifacts-v2.json"])

    assert decision.scope == "runtime"
    assert decision.requires_full_ci is True
    assert decision.requires_operator_ci is False
    assert decision.requires_release_bundle is True


def test_github_outputs_expose_independent_test_and_bundle_decisions(tmp_path):
    module = _load_module()
    output = tmp_path / "github-output.txt"
    decision = module.classify_change_scope(["ops/gpu_pool_controller/lan_aio_prod.py"])

    module._write_github_output(output, decision)

    assert output.read_text(encoding="utf-8").splitlines() == [
        "scope=operator",
        "requires_full_ci=false",
        "requires_operator_ci=true",
        "requires_release_bundle=true",
    ]
