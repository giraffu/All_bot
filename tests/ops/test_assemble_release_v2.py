import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "assemble_release_v2.py"
SHA = "a" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location("assemble_release_v2", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(name: str, digit: str) -> dict:
    return {
        "kind": "image",
        "ref": f"ghcr.io/giraffu/{name}@sha256:{digit * 64}",
        "digest": f"sha256:{digit * 64}",
        "source_sha": SHA,
        "oci_revision": SHA,
    }


def test_assembler_writes_three_manifests_and_resolves_base_digest(tmp_path):
    module = _load_module()
    catalog = {
        "schema_version": 2,
        "artifacts": {
            "base": {
                "track": "control-plane",
                "kind": "image",
                "base": None,
                "inputs": [],
            },
            "api": {
                "track": "control-plane",
                "kind": "image",
                "base": "base",
                "inputs": [],
            },
            "worker": {
                "track": "test-execution",
                "kind": "image",
                "base": "base",
                "inputs": [],
            },
            "i2i": {
                "track": "gpu-execution",
                "kind": "gpu-image",
                "base": None,
                "inputs": [],
                "profile": {
                    "task_types": ["i2i"],
                    "target_gpu": ["RTX 4090"],
                    "startup_args": [],
                },
            },
        },
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    results = tmp_path / "results"
    results.mkdir()
    for name, digit in (("base", "1"), ("api", "2"), ("worker", "3"), ("i2i", "4")):
        result = _result(name, digit)
        if name == "i2i":
            result["model_manifest"] = {
                "key": "models/i2i/manifest.json",
                "size": 10,
                "sha256": "5" * 64,
            }
        (results / f"{name}.json").write_text(json.dumps(result), encoding="utf-8")

    index_path = module.assemble(
        catalog_path=catalog_path,
        results_dir=results,
        output_dir=tmp_path / "release",
        source_sha=SHA,
        ci_run="https://github.com/giraffu/All_bot/actions/runs/1",
    )

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert set(index["manifests"]) == {
        "control-plane",
        "test-execution",
        "gpu-execution",
    }
    control = json.loads(
        (index_path.parent / "control-plane-manifest.json").read_text(encoding="utf-8")
    )
    assert control["artifacts"]["api"]["base_image_digest"] == "sha256:" + "1" * 64
    gpu = json.loads(
        (index_path.parent / "gpu-execution-manifest.json").read_text(encoding="utf-8")
    )
    assert gpu["completeness"] == "complete"
    assert gpu["missing_artifacts"] == []


def test_assembler_publishes_incomplete_gpu_track_without_canary_result(tmp_path):
    module = _load_module()
    catalog = {
        "schema_version": 2,
        "artifacts": {
            "base": {
                "track": "control-plane",
                "kind": "image",
                "base": None,
                "inputs": [],
            },
            "worker": {
                "track": "test-execution",
                "kind": "image",
                "base": "base",
                "inputs": [],
            },
            "i2i": {
                "track": "gpu-execution",
                "kind": "gpu-image",
                "base": None,
                "inputs": [],
                "profile": {
                    "task_types": ["i2i"],
                    "target_gpu": ["RTX 4090"],
                    "startup_args": [],
                },
            },
        },
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    results = tmp_path / "results"
    results.mkdir()
    for name, digit in (("base", "1"), ("worker", "2")):
        (results / f"{name}.json").write_text(
            json.dumps(_result(name, digit)), encoding="utf-8"
        )
    stale_gpu = _result("i2i", "3")
    stale_gpu["model_manifest"] = {
        "key": "models/i2i/old-manifest.json",
        "size": 10,
        "sha256": "4" * 64,
    }
    (results / "i2i.json").write_text(json.dumps(stale_gpu), encoding="utf-8")

    index_path = module.assemble(
        catalog_path=catalog_path,
        results_dir=results,
        output_dir=tmp_path / "release",
        source_sha=SHA,
        ci_run="https://github.com/giraffu/All_bot/actions/runs/1",
        unavailable_artifacts={"i2i"},
    )

    gpu = json.loads(
        (index_path.parent / "gpu-execution-manifest.json").read_text(encoding="utf-8")
    )
    assert gpu["artifacts"] == {}
    assert gpu["completeness"] == "incomplete"
    assert gpu["missing_artifacts"] == ["i2i"]
