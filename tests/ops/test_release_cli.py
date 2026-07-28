import importlib.util
import json
from pathlib import Path
import shutil
import tarfile

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


def test_public_web_oras_push_uses_checkout_relative_archive(tmp_path):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:3] == ["oras", "manifest", "fetch"] and "--descriptor" not in command:
            return module.CommandResult(1, "", "not found")
        if command[:4] == ["oras", "manifest", "fetch", "--descriptor"]:
            return module.CommandResult(
                0, json.dumps({"digest": "sha256:" + "1" * 64}), ""
            )
        return module.CommandResult(0, "", "")

    dependencies = module.ReleaseDependencies(
        run=fake_run,
        temporary_checkout=lambda _sha: module.null_checkout(tmp_path),
    )

    module.build_modules(
        catalog,
        ["public-web"],
        sha="a" * 40,
        image_prefix="ghcr.io/example",
        dependencies=dependencies,
    )

    push = next(command for command in calls if command[:2] == ["oras", "push"])
    archive_argument = push[-1].split(":", 1)[0]
    assert archive_argument == ".module-output/public-web/public-web-dist.tgz"
    assert not Path(archive_argument).is_absolute()


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


def test_pages_deploy_injects_target_runtime_config_and_release_sha(
    tmp_path, monkeypatch
):
    module = _load_module()
    artifact = "ghcr.io/example/public-web@sha256:" + "1" * 64
    release_sha = "a" * 40
    archive = tmp_path / "public-web-dist.tgz"
    source = tmp_path / "source"
    (source / "dist").mkdir(parents=True)
    (source / "dist" / "index.html").write_text("<html></html>")
    (source / "dist" / "allbot-runtime-config.js").write_text(
        "window.__ALLBOT_CONFIG__ = window.__ALLBOT_CONFIG__ || Object.freeze({});"
    )
    assert module._run(
        ["tar", "-czf", str(archive), "-C", str(source), "dist"]
    ).returncode == 0
    runtime_config = tmp_path / "runtime-config.yml"
    runtime_config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "test": {
                    "api_base_url": "https://api-test.example/api",
                    "telegram_bot_username": "test_bot",
                },
                "prod": {
                    "api_base_url": "https://api.example/api",
                    "telegram_bot_username": "prod_bot",
                },
            }
        )
    )
    token_file = tmp_path / "pages.token"
    token_file.write_text("test-token")
    token_file.chmod(0o600)
    deployed = {}

    def fake_run(command, **_kwargs):
        if command[:3] == ["oras", "manifest", "fetch"]:
            return module.CommandResult(
                0,
                json.dumps(
                    {
                        "annotations": {
                            "org.opencontainers.image.revision": release_sha
                        }
                    }
                ),
                "",
            )
        if command[:2] == ["oras", "pull"]:
            output = Path(command[command.index("-o") + 1])
            shutil.copy2(archive, output / archive.name)
            return module.CommandResult(0, "", "")
        if command[:2] == ["tar", "-xzf"]:
            with tarfile.open(command[2], "r:gz") as bundle:
                bundle.extractall(command[command.index("-C") + 1], filter="data")
            return module.CommandResult(0, "", "")
        if command[:2] == ["npm", "ci"]:
            return module.CommandResult(0, "", "")
        if command[:2] == ["curl", "-fsS"]:
            return module.CommandResult(0, deployed["runtime_script"], "")
        raise AssertionError(command)

    def fake_subprocess_run(command, **_kwargs):
        dist = Path(command[command.index("deploy") + 1])
        deployed["runtime_script"] = (
            dist / "allbot-runtime-config.js"
        ).read_text()
        deployed["command"] = command
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module.subprocess, "run", fake_subprocess_run)

    module.SystemAdapters({})._deploy_pages(
        "test",
        artifact,
        {
            "cloudflare_token_file": str(token_file),
            "web_runtime_config": str(runtime_config),
        },
    )

    assert '"api_base_url":"https://api-test.example/api"' in deployed[
        "runtime_script"
    ]
    assert '"telegram_bot_username":"test_bot"' in deployed["runtime_script"]
    assert f'"release_sha":"{release_sha}"' in deployed["runtime_script"]
    assert deployed["command"][-2:] == ["--commit-hash", release_sha]


def test_web_runtime_config_keeps_test_and_prod_isolated(tmp_path):
    module = _load_module()
    path = tmp_path / "runtime-config.yml"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "test": {
                    "api_base_url": "https://api-test.example/api",
                    "telegram_bot_username": "test_bot",
                },
                "prod": {
                    "api_base_url": "https://api.example/api",
                    "telegram_bot_username": "prod_bot",
                },
            }
        )
    )

    test_values, test_revision = module.load_web_runtime_config(path, "test")
    prod_values, prod_revision = module.load_web_runtime_config(path, "prod")

    assert test_values["api_base_url"] == "https://api-test.example/api"
    assert prod_values["api_base_url"] == "https://api.example/api"
    assert test_values["telegram_bot_username"] == "test_bot"
    assert prod_values["telegram_bot_username"] == "prod_bot"
    assert test_revision != prod_revision


def test_repository_web_runtime_config_uses_canonical_environment_endpoints():
    module = _load_module()

    test_values, _ = module.load_web_runtime_config(
        ROOT / "frontend" / "runtime-config.yml", "test"
    )
    prod_values, _ = module.load_web_runtime_config(
        ROOT / "frontend" / "runtime-config.yml", "prod"
    )

    assert test_values["api_base_url"] == "https://api-cf-test.aivison.it.com/api"
    assert test_values["telegram_bot_username"] == "testAIvison_bot"
    assert prod_values["api_base_url"] == "https://api.aivison.it.com/api"
    assert prod_values["telegram_bot_username"] == "AIVision1111_bot"
