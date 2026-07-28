import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release.py"
CATALOG_PATH = ROOT / "deploy" / "module-catalog.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("release", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_explicit_payment_build_closure_has_no_unrelated_modules():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    assert module.build_closure(catalog, ["payment-api"]) == [
        "python-runtime-base",
        "payment-api",
    ]


def test_explicit_multiple_modules_preserve_dependency_order():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    result = module.build_closure(catalog, ["payment-api", "worker-agent"])

    assert result.index("python-runtime-base") < result.index("payment-api")
    assert result.index("python-runtime-base") < result.index("python-worker-base")
    assert result.index("python-worker-base") < result.index("worker-agent")
    assert "dashboard-backend" not in result


def test_build_never_reads_changed_paths_or_release_bundle(tmp_path):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    calls = []

    dependencies = module.ReleaseDependencies(
        run=lambda command, **_kwargs: calls.append(command)
        or module.CommandResult(0, "sha256:" + "1" * 64, ""),
        temporary_checkout=lambda _sha: module.null_checkout(ROOT),
    )
    result = module.build_modules(
        catalog,
        ["payment-api"],
        sha="a" * 40,
        image_prefix="ghcr.io/example",
        dependencies=dependencies,
    )

    assert set(result) == {"python-runtime-base", "payment-api"}
    rendered = "\n".join(" ".join(call) for call in calls)
    assert "git diff" not in rendered
    assert "release-index" not in rendered
    assert "gpu" not in rendered


def test_prod_deploy_requires_confirmation_only():
    module = _load_module()
    with pytest.raises(module.ReleaseError, match="--confirm-prod"):
        module.validate_deploy_request(
            environment="prod",
            module_name="payment-api",
            artifact="ghcr.io/example/payment@sha256:" + "1" * 64,
            confirm_prod=False,
        )

    module.validate_deploy_request(
        environment="prod",
        module_name="payment-api",
        artifact="ghcr.io/example/payment@sha256:" + "1" * 64,
        confirm_prod=True,
    )


def test_deploy_failure_rolls_back_only_target_module(tmp_path):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    events = []
    adapter = module.FunctionAdapter(
        inspect=lambda *_args: "old@sha256:" + "0" * 64,
        deploy=lambda *_args: (_ for _ in ()).throw(RuntimeError("unhealthy")),
        rollback=lambda *_args: events.append("rollback"),
        status=lambda *_args: {"health": "healthy"},
    )

    with pytest.raises(module.ReleaseError, match="rolled back"):
        module.deploy_module(
            catalog,
            environment="prod",
            module_name="payment-api",
            artifact="ghcr.io/example/payment@sha256:" + "1" * 64,
            confirm_prod=True,
            state_root=tmp_path,
            adapters={"compose-image": adapter},
        )

    assert events == ["rollback"]


def test_migration_failure_is_reported_without_rollback(tmp_path):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    events = []
    adapter = module.FunctionAdapter(
        inspect=lambda *_args: None,
        deploy=lambda *_args: (_ for _ in ()).throw(RuntimeError("migration failed")),
        rollback=lambda *_args: events.append("rollback"),
        status=lambda *_args: {},
    )

    with pytest.raises(module.ReleaseError, match="migration failed"):
        module.deploy_module(
            catalog,
            environment="prod",
            module_name="database-migration",
            artifact="ghcr.io/example/migration@sha256:" + "2" * 64,
            confirm_prod=True,
            state_root=tmp_path,
            adapters={"database-migration": adapter},
        )

    assert events == []


def test_status_reads_module_local_state(tmp_path):
    module = _load_module()
    path = tmp_path / "prod" / "payment-api" / "current.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"current": "digest", "previous": "old"}) + "\n")

    assert module.read_status(tmp_path, "prod", "payment-api")["current"] == "digest"
