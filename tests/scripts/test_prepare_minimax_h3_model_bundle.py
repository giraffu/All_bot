import hashlib

import pytest

from ops.gpu_pool_controller.model_repo import ModelRegistry
from scripts import prepare_minimax_h3_model_bundle as module


def test_lightx2v_source_is_pinned_to_repository_commit():
    lightx2v = next(entry for entry in module.FILES if "lightx2v" in entry[0])

    assert "/resolve/37ae5cbe1d6f2243484812fc511f9fa427b12a30/" in lightx2v[3]


def test_anatomy_loras_are_pinned_with_author_strength_pair_files():
    files = {entry[0]: entry for entry in module.FILES}

    assert files["loras/MiniMaxH3/HMBreasts_085e0750_e40.safetensors"][1:3] == (
        "039b6d5399def81c9a459d7cca8ccf749195fcb5f766f0899a387ba2fa6ad967",
        310_168_344,
    )
    assert files["loras/MiniMaxH3/vagassist_e40.safetensors"][1:3] == (
        "2c2fdb66bf558de1aabda504a81d4ada5f4cebc20e8f519dc6ed3bb6d4be8c9a",
        310_168_344,
    )
    assert files["loras/MiniMaxH3/hmpussy_v6_epoch30.safetensors"][1:3] == (
        "3080f4fbcbba4fc06bd09240c7eedb6a5128eb0e19feb001cdf97a7a0941a6ee",
        626_294_968,
    )
    assert files["loras/MiniMaxH3/hmpussy_v6_epoch30.safetensors"][3].endswith(
        "?fileId=3097100"
    )


def test_prepare_minimax_h3_bundle_validates_and_registers_download(monkeypatch, tmp_path):
    payload = b"official-minimax-h3-test-blob"
    sha256 = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(module, "FILES", (("diffusion_models/MiniMaxH3/test.safetensors", sha256, len(payload), "test.safetensors"),))
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 1)
    monkeypatch.setattr(module, "_download", lambda _url, target: target.write_bytes(payload))

    registry = ModelRegistry(tmp_path / "registry")
    manifest = module.prepare(registry)

    assert manifest.is_file()
    assert registry.blob_path(sha256).read_bytes() == payload
    assert "minimax_h3_runtime" in manifest.read_text()


def test_prepare_minimax_h3_bundle_rejects_hash_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "FILES", (("vae/test.safetensors", "0" * 64, 3, "test.safetensors"),))
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 1)
    monkeypatch.setattr(module, "_download", lambda _url, target: target.write_bytes(b"bad"))

    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        module.prepare(ModelRegistry(tmp_path / "registry"))
