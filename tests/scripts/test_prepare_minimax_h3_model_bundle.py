import hashlib

import pytest

from ops.gpu_pool_controller.model_repo import ModelRegistry
from scripts import prepare_minimax_h3_model_bundle as module


def test_redmix_fixed_stack_uses_pinned_model_encoder_and_int8_video_vae():
    files = {entry[0]: entry for entry in module.FILES}

    assert files[
        "diffusion_models/MiniMaxH3/REDMix-MiniMaxH3-A2A-pruned-int8-convrot-ComfyMCP.safetensors"
    ][1:4] == (
        "fc99ff051283ee05f29b1ebcb14e0d7b36c03e93512ac5479411cdfa2e284122",
        20_970_384_488,
        "https://civitai.red/api/download/models/3226037?fileId=3108292",
    )
    assert files["text_encoders/qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors"][1:3] == (
        "a166c7bbbe66a22065159e478335fee4a633c4a3e3bb34c8e8ac4cc91bf4996f",
        15_683_129_587,
    )
    assert files["vae/MiniMaxH3/minimax_h3_video_vae_int8_convrot.safetensors"][1:3] == (
        "9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410",
        3_171_670_912,
    )
    assert len(files) == 4
    assert not any(path.startswith("loras/") for path in files)


def test_redmix_download_requires_civitai_token(monkeypatch, tmp_path):
    monkeypatch.delenv("CIVITAI_API_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="CIVITAI_API_TOKEN"):
        module._download(
            "https://civitai.red/api/download/models/3226037?fileId=3108292",
            tmp_path / "redmix.part",
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


def test_prepare_minimax_h3_bundle_registers_complete_partial_without_eof_range(
    monkeypatch, tmp_path
):
    payload = b"complete-official-minimax-h3-blob"
    sha256 = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        module,
        "FILES",
        (("diffusion_models/MiniMaxH3/test.safetensors", sha256, len(payload), "test.safetensors"),),
    )
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 1)
    monkeypatch.setattr(
        module,
        "_download",
        lambda *_args: pytest.fail("complete partial must not issue an EOF range request"),
    )
    registry = ModelRegistry(tmp_path / "registry")
    registry.ensure_layout()
    partial = (
        registry.root
        / "tmp"
        / f"{module.BUNDLE}-{module.VERSION}"
        / f"{sha256}.part"
    )
    partial.parent.mkdir(parents=True)
    partial.write_bytes(payload)

    module.prepare(registry)

    assert registry.blob_path(sha256).read_bytes() == payload
