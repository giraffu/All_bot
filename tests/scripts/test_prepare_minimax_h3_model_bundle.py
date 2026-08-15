import hashlib

import pytest
import yaml

from ops.gpu_pool_controller.model_repo import ModelRegistry
from scripts import prepare_minimax_h3_model_bundle as module


def test_split_author_stack_uses_exact_six_pinned_assets():
    files = {entry[0]: entry for entry in module.FILES}

    assert files[
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_fl2va_beta2_pruned.safetensors"
    ][1:4] == (
        "57da2b2a12b9efc89eeaa6d751e1ef46ef3e406ca227684c31848abc749f1b20",
        40_222_933_592,
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/47aa7e38dc2aca9a1e71a5b01b7ffefd462b57b5/10Eros_Max_h3_fl2va_beta2_pruned.safetensors",
    )
    assert files["text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"][1:3] == (
        "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6",
        15_687_142_551,
    )
    assert files["vae/MiniMaxH3/minimax_h3_video_vae_fp16.safetensors"][1:3] == (
        "7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522",
        5_207_808_496,
    )
    assert files["loras/MiniMaxH3/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"][1:3] == (
        "2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e",
        1_956_193_000,
    )
    assert files["loras/MiniMaxH3/NaughtyTimes_pruned_r256_v2.safetensors"][1:4] == (
        "947efec5a357505bb93bdc1b050d33786ec150aa1c85f24337f0d59f39aaf31a",
        2_242_444_272,
        "https://civitai.red/api/download/models/3212436?fileId=3094173",
    )
    assert len(files) == 6


def test_naughtytimes_download_requires_civitai_token(monkeypatch):
    monkeypatch.delenv("CIVITAI_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="CIVITAI_API_TOKEN"):
        module._request(
            "https://civitai.red/api/download/models/3212436?fileId=3094173",
            offset=0,
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


def test_prepare_reuses_four_existing_blobs_and_downloads_only_two(monkeypatch, tmp_path):
    payloads = [f"asset-{index}".encode() for index in range(6)]
    assets = tuple(
        (
            f"kind/asset-{index}.safetensors",
            hashlib.sha256(payload).hexdigest(),
            len(payload),
            f"https://assets.example/{index}",
        )
        for index, payload in enumerate(payloads)
    )
    monkeypatch.setattr(module, "FILES", assets)
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 1)
    registry = ModelRegistry(tmp_path / "registry")
    registry.ensure_layout()
    for (_path, sha256, _size, _url), payload in zip(assets[:4], payloads[:4]):
        blob = registry.blob_path(sha256)
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(payload)

    downloads = []

    def download(url, target):
        index = int(url.rsplit("/", 1)[1])
        downloads.append(index)
        target.write_bytes(payloads[index])

    monkeypatch.setattr(module, "_download", download)

    manifest_path = module.prepare(registry)
    manifest = yaml.safe_load(manifest_path.read_text())

    assert downloads == [4, 5]
    assert [item["relative_path"] for item in manifest["files"]] == [
        item[0] for item in assets
    ]
