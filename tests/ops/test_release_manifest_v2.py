import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release_manifest_v2.py"
SHA = "a" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location("release_manifest_v2", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _image(name: str, digit: str, *, base: str | None = None) -> dict:
    value = {
        "kind": "image",
        "ref": f"ghcr.io/giraffu/{name}@sha256:{digit * 64}",
        "digest": f"sha256:{digit * 64}",
        "source_sha": SHA,
        "oci_revision": SHA,
        "dependency_closure": [],
    }
    if base:
        value["base_image_digest"] = base
    return value


def _write_release(tmp_path: Path) -> Path:
    runtime = _image("allbot-python-runtime-base", "1")
    runtime.pop("base_image_digest", None)
    control = {
        "schema_version": 2,
        "track": "control-plane",
        "source_sha": SHA,
        "artifacts": {
            "python-runtime-base": runtime,
            "central-api": _image(
                "allbot-central-api", "2", base=runtime["digest"]
            ),
            "web-api": _image("allbot-web-api", "3", base=runtime["digest"]),
            "public-web": {
                "kind": "tar",
                "ref": "public-web-dist.tgz",
                "sha256": "4" * 64,
                "source_sha": SHA,
                "dependency_closure": [],
            },
        },
    }
    reused_sha = "b" * 40
    control["artifacts"]["web-api"]["source_sha"] = reused_sha
    control["artifacts"]["web-api"]["oci_revision"] = reused_sha
    control["artifacts"]["public-web"]["source_sha"] = reused_sha
    worker_base = _image(
        "allbot-python-worker-base", "5", base=runtime["digest"]
    )
    test_execution = {
        "schema_version": 2,
        "track": "test-execution",
        "source_sha": SHA,
        "artifacts": {
            "python-worker-base": worker_base,
            "worker-agent": _image(
                "allbot-worker-agent", "6", base=worker_base["digest"]
            ),
            "worker-relay": _image(
                "allbot-worker-relay", "7", base=runtime["digest"]
            ),
        },
    }
    gpu = {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": SHA,
        "artifacts": {
            "i2i_pro": {
                **_image("allbot-gpu-i2i-pro", "8"),
                "task_types": ["i2i_pro"],
                "baked_agent_revision": SHA,
                "baked_workflow_revision": SHA,
                "model_manifest": {
                    "key": "manifests/i2i_pro.json",
                    "size": 123,
                    "sha256": "9" * 64,
                },
                "target_gpu": ["NVIDIA RTX 4090"],
                "startup_args": ["--listen", "0.0.0.0"],
            }
        },
    }
    for name, payload in (
        ("control-plane-manifest.json", control),
        ("test-execution-manifest.json", test_execution),
        ("gpu-execution-manifest.json", gpu),
    ):
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    index = {
        "schema_version": 2,
        "source_sha": SHA,
        "ci_run": "https://github.com/giraffu/All_bot/actions/runs/1",
        "manifests": {
            "control-plane": "control-plane-manifest.json",
            "test-execution": "test-execution-manifest.json",
            "gpu-execution": "gpu-execution-manifest.json",
        },
    }
    path = tmp_path / "release-index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    return path


def test_release_index_loads_three_environment_neutral_tracks(tmp_path):
    module = _load_module()
    index_path = _write_release(tmp_path)

    release = module.load_release_index(index_path, expected_sha=SHA)

    assert set(release.manifests) == {
        "control-plane",
        "test-execution",
        "gpu-execution",
    }
    assert "environment" not in release.index
    assert release.manifests["control-plane"]["artifacts"]["central-api"][
        "base_image_digest"
    ] == "sha256:" + "1" * 64


@pytest.mark.parametrize("mutation", ["mutable", "environment", "bad-base"])
def test_release_index_rejects_mutable_or_environment_specific_artifacts(
    tmp_path, mutation
):
    module = _load_module()
    index_path = _write_release(tmp_path)
    manifest_path = tmp_path / "control-plane-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "mutable":
        manifest["artifacts"]["central-api"]["ref"] = "ghcr.io/x/central:latest"
    elif mutation == "environment":
        manifest["environment"] = "test"
    else:
        manifest["artifacts"]["central-api"]["base_image_digest"] = (
            "sha256:" + "f" * 64
        )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(module.ManifestV2Error):
        module.load_release_index(index_path, expected_sha=SHA)


def test_module_promotion_requires_verified_matching_digest(tmp_path):
    module = _load_module()
    release = module.load_release_index(_write_release(tmp_path), expected_sha=SHA)
    selected = module.select_artifacts(
        release, "control-plane", ["central-api", "web-api"]
    )
    verified = {
        "track": "control-plane",
        "artifacts": {
            name: {"digest": artifact["digest"], "status": "verified"}
            for name, artifact in selected.items()
        },
    }

    module.validate_promotion("control-plane", selected, verified)
    verified["artifacts"]["web-api"]["digest"] = "sha256:" + "f" * 64
    with pytest.raises(module.ManifestV2Error, match="web-api"):
        module.validate_promotion("control-plane", selected, verified)


def test_base_change_forces_all_descendants_but_leaf_change_is_local():
    module = _load_module()
    catalog = {
        "python-runtime-base": {"base": None},
        "central-api": {"base": "python-runtime-base"},
        "web-api": {"base": "python-runtime-base"},
        "python-worker-base": {"base": "python-runtime-base"},
        "worker-agent": {"base": "python-worker-base"},
        "worker-relay": {"base": "python-runtime-base"},
    }

    assert module.expand_base_rebuilds(catalog, {"python-runtime-base"}) == set(catalog)
    assert module.expand_base_rebuilds(catalog, {"worker-agent"}) == {"worker-agent"}


def test_gpu_profile_requires_baked_runtime_and_model_checksum(tmp_path):
    module = _load_module()
    index_path = _write_release(tmp_path)
    path = tmp_path / "gpu-execution-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["artifacts"]["i2i_pro"]["baked_workflow_revision"]
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(module.ManifestV2Error, match="baked_workflow_revision"):
        module.load_release_index(index_path, expected_sha=SHA)


def test_release_cli_selects_track_modules_and_services_is_control_alias(tmp_path):
    index_path = _write_release(tmp_path)
    command = [
        "python",
        str(ROOT / "scripts/release.py"),
        "plan",
        "--env",
        "test",
        "--sha",
        SHA,
        "--from-sha",
        SHA,
        "--manifest",
        str(index_path),
        "--track",
        "control-plane",
        "--modules",
        "central-api",
        "--skip-git-checks",
        "--skip-ci-checks",
        "--skip-env-checks",
    ]

    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["track"] == "control-plane"
    assert set(plan["artifacts"]) == {"central-api"}
    assert plan["services"] == ["central-api"]

    invalid = subprocess.run(
        [
            *command[: command.index("--track")],
            "--track",
            "test-execution",
            "--services",
            "worker-agent",
            "--skip-git-checks",
            "--skip-ci-checks",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert invalid.returncode == 2
    assert "only an alias" in invalid.stderr
