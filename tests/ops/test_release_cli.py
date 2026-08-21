import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release.py"
CATALOG_PATH = ROOT / "deploy" / "module-catalog.json"


@pytest.fixture(autouse=True)
def _clear_build_proxy_environment(monkeypatch):
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "FTP_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "ftp_proxy",
        "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


def test_release_catalog_has_dedicated_ltx_unified_gpu_artifact():
    catalog = json.loads(CATALOG_PATH.read_text())["modules"]["ltx_unified"]

    assert catalog["kind"] == "gpu"
    assert catalog["adapter"] == "gpu"
    assert catalog["image"] == "allbot-gpu-ltx-unified"
    assert catalog["dockerfile"] == "workers/runpod_profiles/ltx_unified/Dockerfile"


def test_test_postgres_uses_current_supported_major_15_minor():
    catalog = json.loads(CATALOG_PATH.read_text())["modules"]["postgres"]

    assert catalog["ref"] == "docker.io/library/postgres:15.18-bookworm"
    assert catalog["environments"] == ["test"]


def test_ltx_unified_uses_current_digest_pinned_ltx_t2v_runtime():
    dockerfile = (
        ROOT / "workers/runpod_profiles/ltx_unified/Dockerfile"
    ).read_text(encoding="utf-8")

    assert (
        "ARG BASE_IMAGE=ghcr.io/giraffu/allbot-gpu-ltx-t2v"
        "@sha256:0059724ddde5cda5b9e62611381e0facb24455a43b8cd9a961a620487bf5f53b"
    ) in dockerfile
    assert (
        "COPY shared /opt/allbot/runtime/runpod_worker/shared"
        in dockerfile
    )
    assert (
        "from shared.character_reference_sheet import "
        "compose_ingredients_character_panel"
        in dockerfile
    )


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


def test_worker_agent_is_build_only_because_cloud_compose_has_no_service():
    catalog = json.loads(CATALOG_PATH.read_text())["modules"]["worker-agent"]

    assert catalog["adapter"] == "build-only"
    assert "service" not in catalog


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


def test_loopback_build_proxy_fails_before_build(monkeypatch):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    calls = []
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:7890")

    dependencies = module.ReleaseDependencies(
        run=lambda command, **_kwargs: calls.append(command)
        or module.CommandResult(0, "", ""),
        temporary_checkout=lambda _sha: module.null_checkout(ROOT),
    )

    with pytest.raises(module.ReleaseError, match="container-reachable"):
        module.build_modules(
            catalog,
            ["python-runtime-base"],
            sha="a" * 40,
            image_prefix="ghcr.io/example",
            dependencies=dependencies,
        )

    assert calls == []


def test_build_only_identity_uses_inputs_and_base_digest(tmp_path):
    module = _load_module()
    dockerfile = tmp_path / "Dockerfile"
    requirements = tmp_path / "requirements.txt"
    dockerfile.write_text("FROM scratch\n")
    requirements.write_text("example==1\n")
    contract = {
        "target": "base",
        "dockerfile": "Dockerfile",
        "build_inputs": ["requirements.txt"],
    }

    first = module.build_input_identity(
        "base", contract, checkout=tmp_path, base_artifact=None
    )
    assert first == module.build_input_identity(
        "base", contract, checkout=tmp_path, base_artifact=None
    )

    requirements.write_text("example==2\n")
    changed_input = module.build_input_identity(
        "base", contract, checkout=tmp_path, base_artifact=None
    )
    dockerfile.write_text("FROM scratch\nRUN true\n")
    changed_dockerfile = module.build_input_identity(
        "base", contract, checkout=tmp_path, base_artifact=None
    )
    changed_base = module.build_input_identity(
        "base",
        contract,
        checkout=tmp_path,
        base_artifact="ghcr.io/example/base@sha256:" + "1" * 64,
    )

    assert len({first, changed_input, changed_dockerfile, changed_base}) == 4


def test_build_command_uses_builder_registry_cache_progress_and_reachable_proxy(
    monkeypatch,
):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    calls = []
    digest = "sha256:" + "1" * 64
    monkeypatch.setenv("http_proxy", "http://172.17.0.1:7890")

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            if "--format" in command:
                return module.CommandResult(0, digest, "")
            return module.CommandResult(1, "", "not found")
        return module.CommandResult(0, "", "")

    module.build_modules(
        catalog,
        ["python-runtime-base"],
        sha="a" * 40,
        image_prefix="ghcr.io/example",
        builder="allbot-builder",
        registry_cache_prefix="ghcr.io/example/cache",
        build_progress="plain",
        dependencies=module.ReleaseDependencies(
            run=fake_run,
            temporary_checkout=lambda _sha: module.null_checkout(ROOT),
        ),
    )

    build = next(call for call in calls if call[:3] == ["docker", "buildx", "build"])
    assert build[3:5] == ["--builder", "allbot-builder"]
    assert ["--progress", "plain"] == build[5:7]
    assert "--cache-from" in build and "--cache-to" in build
    assert "http_proxy" in build
    assert all("172.17.0.1:7890" not in value for value in build)
    assert any(":input-" in value for value in build)


def test_runpod_gpu_build_emits_single_linux_amd64_manifest_without_provenance():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    calls = []
    digest = "sha256:" + "2" * 64

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            if "--format" in command:
                return module.CommandResult(0, digest, "")
            return module.CommandResult(1, "", "not found")
        return module.CommandResult(0, "", "")

    module.build_modules(
        catalog,
        ["i2i_pro"],
        sha="b" * 40,
        image_prefix="ghcr.io/example",
        dependencies=module.ReleaseDependencies(
            run=fake_run,
            temporary_checkout=lambda _sha: module.null_checkout(ROOT),
        ),
    )

    build = next(call for call in calls if call[:3] == ["docker", "buildx", "build"])
    adjacent_arguments = [
        build[index : index + 2] for index in range(len(build) - 1)
    ]
    assert ["--platform", "linux/amd64"] in adjacent_arguments
    assert "--provenance=false" in build


def test_gpu_build_injects_canonical_runtime_and_workflow_hashes():
    from workers.comfy_agent.runtime_manifest import hash_runtime_package

    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    calls = []
    digest = "sha256:" + "2" * 64

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            if "--format" in command:
                return module.CommandResult(0, digest, "")
            return module.CommandResult(1, "", "not found")
        return module.CommandResult(0, "", "")

    module.build_modules(
        catalog,
        ["minimax_h3"],
        sha="b" * 40,
        image_prefix="ghcr.io/example",
        dependencies=module.ReleaseDependencies(
            run=fake_run,
            temporary_checkout=lambda _sha: module.null_checkout(ROOT),
        ),
    )

    build = next(call for call in calls if call[:3] == ["docker", "buildx", "build"])
    adjacent_arguments = [
        build[index : index + 2] for index in range(len(build) - 1)
    ]
    runtime_hash = hash_runtime_package(ROOT / "workers/comfy_agent")
    workflow_hash = hashlib.sha256(
        (ROOT / "workers/comfy_agent/workflows/mappings.json").read_bytes()
    ).hexdigest()
    assert [
        "--build-arg",
        f"ALLBOT_RUNTIME_PACKAGE_SHA256={runtime_hash}",
    ] in adjacent_arguments
    assert [
        "--build-arg",
        f"ALLBOT_WORKFLOW_MAPPING_SHA256={workflow_hash}",
    ] in adjacent_arguments


def test_gpu_build_accepts_declared_exact_external_base_ref():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    calls = []
    digest = "sha256:" + "2" * 64
    base_ref = (
        "127.0.0.1:15000/allbot/comfyui-boot@sha256:"
        "09c810dd10ee5185cd7ee6e7d5d1b108118d85965838ad8c5ee1be425de1d5c1"
    )

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:4] == ["docker", "buildx", "imagetools", "inspect"]:
            if "--format" in command:
                return module.CommandResult(0, digest, "")
            return module.CommandResult(1, "", "not found")
        return module.CommandResult(0, "", "")

    module.build_modules(
        catalog,
        ["minimax_h3"],
        sha="b" * 40,
        image_prefix="127.0.0.1:15000/allbot",
        external_base_ref=base_ref,
        dependencies=module.ReleaseDependencies(
            run=fake_run,
            temporary_checkout=lambda _sha: module.null_checkout(ROOT),
        ),
    )

    build = next(call for call in calls if call[:3] == ["docker", "buildx", "build"])
    assert ["--build-arg", f"BASE_IMAGE={base_ref}"] in [
        build[index : index + 2] for index in range(len(build) - 1)
    ]


def test_gpu_build_rejects_mutable_external_base_ref():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    with pytest.raises(module.ReleaseError, match="exact repository@sha256 digest"):
        module.build_modules(
            catalog,
            ["minimax_h3"],
            sha="b" * 40,
            image_prefix="127.0.0.1:15000/allbot",
            external_base_ref="127.0.0.1:15000/allbot/comfyui-boot:latest",
            dependencies=module.ReleaseDependencies(
                run=lambda *_args, **_kwargs: module.CommandResult(0, "", ""),
                temporary_checkout=lambda _sha: module.null_checkout(ROOT),
            ),
        )


def test_remote_state_backend_reads_and_atomically_writes_target_isolated_state():
    module = _load_module()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1].startswith("cat "):
            return module.CommandResult(
                0,
                json.dumps(
                    {"environment": "prod", "module": "payment-api", "current": "x"}
                ),
                "",
            )
        return module.CommandResult(0, "", "")

    backend = module.RemoteStateBackend(
        host="deploy@target",
        root=Path("/var/lib/allbot/module-release-state"),
        run=fake_run,
    )

    assert backend.read("prod", "payment-api")["current"] == "x"
    backend.write(
        "test",
        "main-bot",
        {"environment": "test", "module": "main-bot", "current": "y"},
    )

    write_script = calls[-1][1]["input"]
    assert "/test/main-bot/current.json" in write_script
    assert "mktemp" in write_script
    assert "mv " in write_script


def test_revision_labels_follow_expensive_runtime_install_steps():
    python_base = (
        ROOT / "deploy/docker/Dockerfile.python-runtime-base"
    ).read_text(encoding="utf-8")
    ffmpeg_base = (
        ROOT / "deploy/docker/Dockerfile.python-ffmpeg-runtime-base"
    ).read_text(encoding="utf-8")
    control = (
        ROOT / "deploy/docker/Dockerfile.control-plane"
    ).read_text(encoding="utf-8")

    assert python_base.index("pip install") < python_base.index(
        "org.opencontainers.image.revision"
    )
    assert ffmpeg_base.index("apt-get install") < ffmpeg_base.index(
        "org.opencontainers.image.revision"
    )
    assert "apt-get install -y --no-install-recommends ffmpeg" not in control


def test_self_hosted_workflows_are_manual_main_gated_and_least_privilege():
    build = (ROOT / ".github/workflows/module-build.yml").read_text()
    deploy = (ROOT / ".github/workflows/module-deploy.yml").read_text()

    assert "workflow_dispatch:" in build
    assert "pull_request:" not in build + deploy
    assert "allbot-build-sgp1" in build and "allbot-build-sgp1" in deploy
    assert "packages: write" in build
    assert "packages: write" not in deploy
    assert "secrets.GHCR_TOKEN || github.token" in build
    assert "git rev-parse origin/main" in build
    assert "actions/setup-node@v4" in build
    assert "node-version: 24" in build
    assert build.index("actions/setup-node@v4") < build.index(
        "python3 scripts/release.py build"
    )
    assert "GPU module must be built locally" not in build
    assert "environment: ${{ inputs.environment }}" in deploy
    assert "confirm_production" in deploy
    assert "@sha256:[0-9a-f]{64}" in deploy
    assert "--confirm-prod" in deploy
    assert "--state-backend remote" in deploy
    assert "\n          python -" not in build
    assert "python3 scripts/release.py build" in build
    assert "--build-progress plain | tee module-digests.json" in build


def test_active_knowledge_uses_only_current_release_commands():
    roots = [ROOT / ".codex" / "skills", ROOT / "docs"]
    sources = []
    for root in roots:
        for path in root.rglob("*.md"):
            relative = path.relative_to(ROOT)
            if relative.parts[:2] == ("docs", "archive"):
                continue
            if relative.parts[:2] == ("docs", "release_evidence"):
                continue
            if relative.parts[:2] == ("docs", "adr") and path.name not in {
                "README.md",
                "0009-operator-decides-module-release.md",
            }:
                continue
            sources.append(path.read_text(encoding="utf-8"))
    sources.extend(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "scripts" / "update_cloud_test_with_maintenance.sh",
            ROOT / "scripts" / "update_cloud_prod_with_maintenance.sh",
            ROOT / "scripts" / "sync_test_release_config.py",
            ROOT / "scripts" / "validate_deploy_env.py",
        )
    )
    active_text = "\n".join(sources)

    for retired in (
        "scripts/release.py promote",
        "scripts/release.py plan",
        "scripts/release.py preflight",
        "release.py --strategy",
        "--track control-plane",
        "config-plan",
        "config-apply",
        "CI release manifest",
    ):
        assert retired not in active_text


def test_image_digest_reader_accepts_buildx_json_string_for_oci_index(tmp_path):
    module = _load_module()
    calls = []
    digest = "sha256:" + "1" * 64
    dependencies = module.ReleaseDependencies(
        run=lambda command, **_kwargs: calls.append(command)
        or module.CommandResult(0, json.dumps(digest), ""),
        temporary_checkout=lambda _sha: module.null_checkout(tmp_path),
    )

    assert (
        module._digest_for_ref(
            "registry.local/image:sha",
            kind="gpu",
            dependencies=dependencies,
            cwd=tmp_path,
        )
        == digest
    )
    assert calls == [
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            "registry.local/image:sha",
            "--format",
            "{{json .Manifest.Digest}}",
        ]
    ]


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


def test_compose_deploy_waits_for_target_health(monkeypatch):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    captured = {}

    def fake_remote_shell(host, script):
        captured["host"] = host
        captured["script"] = script
        return module.CommandResult(0, "", "")

    monkeypatch.setattr(module, "_remote_shell", fake_remote_shell)

    module.SystemAdapters(catalog)._deploy_compose(
        "prod",
        catalog["dashboard-backend"],
        "ghcr.io/example/dashboard@sha256:" + "1" * 64,
        {"remote_host": "prod-control"},
    )

    assert captured["host"] == "prod-control"
    assert "compose=(sudo -n docker compose" in captured["script"]
    assert (
        "up -d --no-deps --force-recreate --wait --wait-timeout 120 "
        "dashboard-backend"
    ) in captured["script"]
    assert 'org.opencontainers.image.revision' in captured["script"]
    assert "release image has no valid source revision" in captured["script"]
    assert "grep -v '^ALLBOT_RELEASE_SHA='" in captured["script"]


def test_compose_deploy_uses_active_compose_contract_by_default(monkeypatch):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    captured = {}

    def fake_remote_shell(_host, script):
        captured["script"] = script
        return module.CommandResult(0, "", "")

    monkeypatch.setattr(module, "_remote_shell", fake_remote_shell)

    module.SystemAdapters(catalog)._deploy_compose(
        "test",
        catalog["dashboard-frontend"],
        "ghcr.io/example/dashboard@sha256:" + "1" * 64,
        {"remote_host": "test-control"},
    )

    script = captured["script"]
    assert "root=/var/lib/allbot/module-contracts/test/compose-contract/current" in script
    assert 'test -f "$root/deploy/docker-compose-cloud-base.yml"' in script
    assert 'test -f "$root/deploy/docker-compose-cloud-test.overlay.yml"' in script
    assert "/home/deploy/APP/All_bot-release/repo" not in script


def test_compose_deploy_allows_explicit_remote_root_override(monkeypatch):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    captured = {}

    def fake_remote_shell(_host, script):
        captured["script"] = script
        return module.CommandResult(0, "", "")

    monkeypatch.setattr(module, "_remote_shell", fake_remote_shell)

    module.SystemAdapters(catalog)._deploy_compose(
        "test",
        catalog["dashboard-frontend"],
        "ghcr.io/example/dashboard@sha256:" + "1" * 64,
        {
            "remote_host": "test-control",
            "remote_root": "/srv/allbot/emergency-contract",
        },
    )

    assert "root=/srv/allbot/emergency-contract" in captured["script"]


def test_config_contract_deploy_activates_service_projections(monkeypatch):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    captured = {}

    def fake_run(command, **_kwargs):
        output = Path(command[command.index("-o") + 1])
        archive = output / "config-contract.tgz"
        with tarfile.open(archive, "w:gz"):
            pass
        return module.CommandResult(0, "", "")

    def fake_remote_shell(_host, script):
        captured["script"] = script
        return module.CommandResult(0, "", "")

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_remote_shell", fake_remote_shell)

    module.SystemAdapters(catalog)._deploy_contract(
        "test",
        "config-contract",
        "ghcr.io/example/config-contract@sha256:" + "1" * 64,
        {"remote_host": "test-control"},
    )

    script = captured["script"]
    assert "runtime_env_contract.py activate" in script
    assert "--env-file /etc/allbot/test.env" in script
    assert "--root /var/lib/allbot/config/test" in script


@pytest.mark.parametrize(
    ("environment", "expected_network"),
    (("test", "--network allbot-test_default"), ("prod", None)),
)
def test_database_migration_uses_only_the_test_compose_network(
    monkeypatch, environment, expected_network
):
    module = _load_module()
    captured = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return module.CommandResult(0, "", "")

    monkeypatch.setattr(module, "_run", fake_run)

    module.SystemAdapters({})._deploy_migration(
        environment,
        "ghcr.io/example/migration@sha256:" + "1" * 64,
        {"remote_host": "control"},
    )

    remote_command = captured["command"][-1]
    assert "sudo -n docker run --rm" in remote_command
    if expected_network is None:
        assert "--network" not in remote_command
    else:
        assert expected_network in remote_command


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


@pytest.mark.parametrize(
    ("environment", "expected_api", "expected_bot", "expected_branch"),
    [
        ("test", "https://api-test.example/api", "test_bot", "test"),
        ("prod", "https://api.example/api", "prod_bot", "main"),
    ],
)
def test_pages_deploy_injects_target_runtime_config_and_release_sha(
    tmp_path,
    monkeypatch,
    environment,
    expected_api,
    expected_bot,
    expected_branch,
):
    module = _load_module()
    artifact = "ghcr.io/example/public-web@sha256:" + "1" * 64
    release_sha = "a" * 40
    archive = tmp_path / "public-web-dist.tgz"
    source = tmp_path / "source"
    (source / "dist").mkdir(parents=True)
    (source / "dist" / "index.html").write_text(
        '<html><script src="/allbot-runtime-config.js"></script></html>'
    )
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
        deployed["index"] = (dist / "index.html").read_text()
        deployed["headers"] = (dist / "_headers").read_text()
        deployed["command"] = command
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module.subprocess, "run", fake_subprocess_run)

    module.SystemAdapters({})._deploy_pages(
        environment,
        artifact,
        {
            "cloudflare_token_file": str(token_file),
            "web_runtime_config": str(runtime_config),
        },
    )

    assert f'"api_base_url":"{expected_api}"' in deployed["runtime_script"]
    assert f'"telegram_bot_username":"{expected_bot}"' in deployed["runtime_script"]
    assert f'"release_sha":"{release_sha}"' in deployed["runtime_script"]
    assert f'/allbot-runtime-config.js?release_sha={release_sha}' in deployed["index"]
    assert "/allbot-runtime-config.js" in deployed["headers"]
    assert "Cache-Control: no-store, no-cache, must-revalidate" in deployed["headers"]
    assert deployed["command"][-2:] == ["--commit-hash", release_sha]
    branch_index = deployed["command"].index("--branch")
    assert deployed["command"][branch_index + 1] == expected_branch


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
    assert test_values["enable_ltx_t2v_msr"] is False
    assert prod_values["enable_ltx_t2v_msr"] is False
    assert test_values["enable_ltx_video"] is False
    assert test_values["enable_ltx_video_v2"] is False
    assert test_values["enable_ltx_t2v"] is False
    assert test_values["enable_character_assets"] is True
    assert test_values["enable_character_explicit_views"] is True
    assert test_values["enable_minimax_h3"] is True
    assert test_values["enable_minimax_h3_entry"] is False
    assert test_values["enable_minimax_h3_ref2v"] is True
    assert prod_values["enable_ltx_video"] is True
    assert prod_values["enable_character_assets"] is False
    assert prod_values["enable_character_explicit_views"] is False
    assert prod_values["enable_minimax_h3"] is False
    assert prod_values["enable_minimax_h3_entry"] is False
    assert prod_values["enable_minimax_h3_ref2v"] is False


def test_module_archive_discovery_accepts_oras_preserved_relative_path(tmp_path):
    module = _load_module()
    archive = tmp_path / ".module-output" / "public-web" / "public-web-dist.tgz"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"artifact")

    assert module._find_single_module_archive(tmp_path, "public-web") == archive
