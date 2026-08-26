import hashlib
from pathlib import Path

import pytest

from workers.comfy_agent.runtime_manifest import (
    build_runtime_manifest,
    load_runtime_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = ROOT / "workers" / "runpod_runtime"


def test_runpod_runtime_contains_no_copied_worker_or_domain_source():
    assert not any((RUNTIME_ROOT / "comfy_agent").rglob("*.py"))
    assert not any((RUNTIME_ROOT / "src").rglob("*.py"))


def test_runtime_manifest_hashes_canonical_package_and_mapping(tmp_path):
    package = tmp_path / "comfy_agent"
    workflows = package / "workflows"
    workflows.mkdir(parents=True)
    (package / "agent_main.py").write_text("print('canonical')\n", encoding="utf-8")
    mapping = workflows / "mappings.json"
    mapping.write_text('{"txt2img":"workflow.json"}\n', encoding="utf-8")

    manifest = build_runtime_manifest(package, git_sha="abc123")

    assert manifest["git_sha"] == "abc123"
    assert manifest["runtime_package_sha256"] == build_runtime_manifest(
        package,
        git_sha="different-sha",
    )["runtime_package_sha256"]
    assert manifest["workflow_mapping_sha256"] == hashlib.sha256(
        mapping.read_bytes()
    ).hexdigest()


def test_runtime_manifest_fails_closed_on_embedded_hash_mismatch(monkeypatch):
    monkeypatch.setenv("ALLBOT_RUNTIME_PACKAGE_SHA256", "0" * 64)

    with pytest.raises(RuntimeError, match="runtime_package_sha256"):
        load_runtime_manifest()


def test_every_gpu_profile_consumes_the_canonical_worker_package():
    dockerfiles = sorted((ROOT / "workers" / "runpod_profiles").glob("*/Dockerfile*"))
    runtime_dockerfiles = [
        path for path in dockerfiles if path.name != "Dockerfile.proddeps"
    ]
    assert runtime_dockerfiles
    for dockerfile in runtime_dockerfiles:
        content = dockerfile.read_text(encoding="utf-8")
        purge_index = content.find(
            "rm -rf /opt/allbot/runtime/runpod_worker"
        )
        runtime_copy_index = content.find(
            "COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker"
        )
        agent_copy_index = content.find(
            "COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent"
        )
        assert "COPY workers/comfy_agent " in content, dockerfile
        assert "COPY src " in content, dockerfile
        assert "COPY workers/runpod_runtime/comfy_agent" not in content, dockerfile
        assert purge_index >= 0, dockerfile
        assert purge_index < runtime_copy_index < agent_copy_index, dockerfile
        assert 'test -n "$ALLBOT_GIT_SHA"' in content, dockerfile
        assert 'test -n "$ALLBOT_RUNTIME_PACKAGE_SHA256"' in content, dockerfile
        assert 'test -n "$ALLBOT_WORKFLOW_MAPPING_SHA256"' in content, dockerfile
        assert (
            "from comfy_agent.runtime_manifest import load_runtime_manifest; "
            "load_runtime_manifest()"
        ) in content, dockerfile


def test_profile_build_stages_canonical_sources_and_hash_build_args():
    script = (ROOT / "scripts" / "build_runpod_profile_image.sh").read_text(
        encoding="utf-8"
    )
    assert '"${destination}/workers/comfy_agent"' in script
    assert '"${destination}/src"' in script
    assert "ALLBOT_RUNTIME_PACKAGE_SHA256" in script
    assert "ALLBOT_WORKFLOW_MAPPING_SHA256" in script
