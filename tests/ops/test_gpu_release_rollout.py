import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = "ghcr.io/giraffu/gpu-i2i-pro@sha256:" + "1" * 64


def _load_module():
    path = ROOT / "scripts/gpu_release_rollout.py"
    spec = importlib.util.spec_from_file_location("gpu_release_rollout", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rollout_uses_explicit_digest_without_release_index():
    module = _load_module()
    resolved = module.resolve_gpu_artifact(ARTIFACT, profile="i2i_pro")
    plan = module.rollout_plan(resolved, slot="01", operator="runpod")

    assert resolved["ref"] == ARTIFACT
    assert resolved["runpod_image_env"] == "RUNPOD_IMAGE_NAME_I2I_PRO"
    assert plan["scope"] == "single-slot"
    assert plan["failure_policy"] == "restore only this slot's previous exact image"


def test_rollout_rejects_mutable_tag():
    module = _load_module()
    with pytest.raises(module.GPURolloutError, match="exact"):
        module.resolve_gpu_artifact("ghcr.io/giraffu/gpu:latest", profile="i2i_pro")


def test_minimax_h3_resolves_the_future_runpod_image_environment_key():
    module = _load_module()
    artifact = "ghcr.io/giraffu/allbot-gpu-minimax-h3@sha256:" + "2" * 64

    resolved = module.resolve_gpu_artifact(artifact, profile="minimax_h3")

    assert resolved["runpod_image_env"] == "RUNPOD_IMAGE_NAME_MINIMAX_H3"


def test_operator_command_targets_one_slot():
    module = _load_module()
    resolved = module.resolve_gpu_artifact(ARTIFACT, profile="i2i_pro")
    command = module.operator_command(resolved, slot="07", operator="lan", execute=True)

    assert "--slot" in command
    assert command[command.index("--slot") + 1] == "07"
    assert command[command.index("--artifact") + 1] == ARTIFACT
    assert "--release-index" not in command
    assert "--strategy" not in command
