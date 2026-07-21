import importlib.util
import json
from pathlib import Path

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
