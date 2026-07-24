import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_release_environment_neutral.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_neutrality", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checked_in_release_sources_are_environment_neutral():
    _load_module().validate(ROOT)


def test_build_context_requires_recursive_env_excludes():
    module = _load_module()

    assert {"**/.env", "**/.env.*"} <= module.REQUIRED_CONTEXT_EXCLUDES


def test_dockerfile_cannot_bake_token_or_env_file(tmp_path):
    module = _load_module()
    docker = tmp_path / "deploy" / "docker"
    docker.mkdir(parents=True)
    (docker / "Dockerfile.bad").write_text(
        "FROM scratch\nARG API_TOKEN\nCOPY .env /app/.env\n", encoding="utf-8"
    )

    with pytest.raises(module.NeutralityError):
        module.validate_dockerfiles(tmp_path)


def test_public_web_dist_cannot_bake_test_or_prod_sentinel(tmp_path):
    module = _load_module()
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<script src="/allbot-runtime-config.js"></script>', encoding="utf-8"
    )
    (frontend / "runtime-config.yml").write_text(
        '{"test":{"url":"test"},"prod":{"url":"prod"}}', encoding="utf-8"
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "app.js").write_text("https://api.aivison.it.com/api", encoding="utf-8")

    with pytest.raises(module.NeutralityError, match="sentinel"):
        module.validate_public_web_sources(tmp_path, dist=dist)


def test_runtime_source_cannot_auto_load_dotenv(tmp_path):
    module = _load_module()
    for relative in module.RUNTIME_SOURCE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SAFE = True\n", encoding="utf-8")
    (tmp_path / "config.py").write_text("load_dotenv()\n", encoding="utf-8")

    with pytest.raises(module.NeutralityError, match="dotenv"):
        module.validate_runtime_sources(tmp_path)


def test_runtime_identity_gate_applies_only_to_runnable_service_artifacts():
    module = _load_module()

    assert module._requires_runtime_identity("central-api") is True
    assert module._requires_runtime_identity("worker-relay") is True
    assert module._requires_runtime_identity("python-runtime-base") is False
    assert module._requires_runtime_identity("python-media-runtime-base") is False
    assert module._requires_runtime_identity("python-worker-base") is False
    assert module._requires_runtime_identity("dashboard-frontend") is False
    assert module._requires_runtime_identity("qqcc-config-frontend") is False


def test_gpu_execution_images_do_not_claim_control_plane_runtime_identity():
    module = _load_module()

    assert (
        module._requires_runtime_identity(
            "wan22_video_v2", track="gpu-execution"
        )
        is False
    )
    assert (
        module._requires_runtime_identity("worker-relay", track="test-execution")
        is True
    )


def test_release_image_scan_can_select_only_artifacts_built_for_target_sha(tmp_path):
    module = _load_module()
    target_sha = "a" * 40
    inherited_sha = "b" * 40
    manifest = {
        "schema_version": 2,
        "track": "control-plane",
        "source_sha": target_sha,
        "artifacts": {
            "dashboard-backend": {
                "kind": "image",
                "ref": "registry/dashboard@sha256:" + "1" * 64,
                "source_sha": target_sha,
            },
            "web-api": {
                "kind": "image",
                "ref": "registry/web@sha256:" + "2" * 64,
                "source_sha": inherited_sha,
            },
        },
    }
    (tmp_path / "control-plane-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "release-index.json").write_text(
        json.dumps(
            {
                "source_sha": target_sha,
                "manifests": {"control-plane": "control-plane-manifest.json"},
            }
        ),
        encoding="utf-8",
    )

    images = list(
        module._release_images(
            tmp_path / "release-index.json", only_source_sha=target_sha
        )
    )

    assert images == [
        ("dashboard-backend", "registry/dashboard@sha256:" + "1" * 64)
    ]


def test_main_workflow_scans_only_images_built_for_current_main_sha():
    workflow = (ROOT / ".github/workflows/modular-release-v2.yml").read_text(
        encoding="utf-8"
    )

    assert '--only-source-sha "$SOURCE_SHA"' in workflow


def test_image_scan_source_filter_must_match_release_index(tmp_path):
    module = _load_module()
    (tmp_path / "release-index.json").write_text(
        json.dumps({"source_sha": "a" * 40, "manifests": {}}), encoding="utf-8"
    )

    with pytest.raises(module.NeutralityError, match="does not match"):
        module.validate_image_config(
            tmp_path / "release-index.json", only_source_sha="b" * 40
        )


def _write_release_index(tmp_path, artifacts):
    manifest_path = tmp_path / "gpu-execution-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "track": "gpu-execution",
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "release-index.json"
    index_path.write_text(
        json.dumps(
            {
                "source_sha": "a" * 40,
                "manifests": {
                    "gpu-execution": "gpu-execution-manifest.json"
                },
            }
        ),
        encoding="utf-8",
    )
    return index_path


def test_image_scan_deduplicates_shared_exact_ref(tmp_path, monkeypatch, capsys):
    module = _load_module()
    ref = "registry/wan22@sha256:" + "1" * 64
    index_path = _write_release_index(
        tmp_path,
        {
            "image_to_video": {
                "kind": "image",
                "ref": ref,
                "source_sha": "a" * 40,
            },
            "wan22_video_v2": {
                "kind": "image",
                "ref": ref,
                "source_sha": "a" * 40,
            },
        },
    )
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        stdout = (
            '[{"Config":{"Env":[]}}]'
            if command[:3] == ["docker", "image", "inspect"]
            else ""
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module, "_validate_image_filesystem", lambda _ref: calls.append(["filesystem"])
    )

    module.validate_image_config(index_path, only_source_sha="a" * 40)

    assert sum(command[:2] == ["docker", "pull"] for command in calls) == 1
    assert calls.count(["filesystem"]) == 1
    output = capsys.readouterr().out
    assert "image_to_video,wan22_video_v2" in output
    assert "phase=pull" in output


def _tar_bytes(name: str) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.size = 0
        archive.addfile(info)
    return payload.getvalue()


def test_filesystem_scan_uses_only_application_roots_not_docker_export(monkeypatch):
    module = _load_module()
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:2] == ["docker", "create"]:
            return subprocess.CompletedProcess(command, 0, stdout="container-id\n", stderr="")
        if command[:2] == ["docker", "cp"]:
            kwargs["stdout"].write(_tar_bytes("safe/config.py"))
            return subprocess.CompletedProcess(command, 0, stdout=None, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module._validate_image_filesystem("registry/app@sha256:" + "2" * 64)

    assert not any(command[:2] == ["docker", "export"] for command in commands)
    copied = [command[2].split(":", 1)[1] for command in commands if command[:2] == ["docker", "cp"]]
    assert copied == ["/app/.", "/opt/allbot/.", "/usr/src/app/."]


@pytest.mark.parametrize("name", ["nested/.env.prod", "keys/id.pem", "keys/id.key"])
def test_filesystem_scan_still_rejects_environment_material(
    name, monkeypatch
):
    module = _load_module()

    def fake_run(command, **kwargs):
        if command[:2] == ["docker", "create"]:
            return subprocess.CompletedProcess(command, 0, stdout="container-id\n", stderr="")
        if command[:2] == ["docker", "cp"]:
            kwargs["stdout"].write(_tar_bytes(name))
            return subprocess.CompletedProcess(command, 0, stdout=None, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(module.NeutralityError, match="environment material"):
        module._validate_image_filesystem("registry/app@sha256:" + "3" * 64)


def test_image_pull_timeout_fails_closed_without_ref_disclosure(
    tmp_path, monkeypatch
):
    module = _load_module()
    ref = "registry/private@sha256:" + "4" * 64
    index_path = _write_release_index(
        tmp_path,
        {
            "private-artifact": {
                "kind": "image",
                "ref": ref,
                "source_sha": "a" * 40,
            }
        },
    )

    def fake_run(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=module.PULL_TIMEOUT_SECONDS)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(module.NeutralityError, match="pull timed out") as exc:
        module.validate_image_config(index_path, only_source_sha="a" * 40)
    assert ref not in str(exc.value)
