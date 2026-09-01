import hashlib
from pathlib import Path

import pytest
import yaml

from ops.gpu_pool_controller.model_repo import ModelRegistry
from scripts import prepare_minimax_h3_model_bundle as module


def test_10eros_stack_uses_exact_nine_pinned_assets():
    files = {entry[0]: entry for entry in module.FILES}

    assert files[
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors"
    ][1:4] == (
        "bf34b4c9d2fa973ae84c480a1a5a04d2978958023bb6be7375b3b9e4818965e3",
        40_222_982_192,
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/3c071106f5b62c02b3cb0b7d831083cdb582b289/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors",
    )
    assert files[
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors"
    ][1:4] == (
        "54d56b15c65923b54c9ca16b494dae641bfe9455cfcb1c19c49b1008e270bbc1",
        20_967_637_320,
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/3c071106f5b62c02b3cb0b7d831083cdb582b289/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors",
    )
    assert files["text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"][1:3] == (
        "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6",
        15_687_142_551,
    )
    assert files["vae/MiniMaxH3/minimax_h3_video_vae_fp16.safetensors"][1:3] == (
        "7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522",
        5_207_808_496,
    )
    assert files["loras/MiniMaxH3/HMCumshot_V2.safetensors"][1:4] == (
        "1a5b7948bb97f27737e62c3dd5497a3afb77517f230787f45e45c7d8fe3dc24d",
        626_294_968,
        "https://civitai.red/api/download/models/3238531?fileId=3121030",
    )
    assert files["loras/MiniMaxH3/deepthroat_v02.safetensors"][1:3] == (
        "1fd239662f6290255b0bb3a220764fb53aab2859378f7fd3024030c1e1991cb2",
        298_263_792,
    )
    assert files["loras/MiniMaxH3/H3_Mis_Insrt_v07.safetensors"][1:3] == (
        "8d1ed16cdae02e25308063053f7f459b88fb4c50d7e6ea4d05ebc4950a992584",
        310_190_448,
    )
    assert files["loras/MiniMaxH3/H3_Footjob_TypeB_v1.safetensors"][1:3] == (
        "6e293977389020e2e327d5e375cdc55352659f0ac61b41f270ec5ddf453fc620",
        298_260_800,
    )
    assert set(files) == {
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors",
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors",
        "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "vae/MiniMaxH3/minimax_h3_audio_vae_fp32.safetensors",
        "vae/MiniMaxH3/minimax_h3_video_vae_fp16.safetensors",
        "loras/MiniMaxH3/deepthroat_v02.safetensors",
        "loras/MiniMaxH3/H3_Mis_Insrt_v07.safetensors",
        "loras/MiniMaxH3/H3_Footjob_TypeB_v1.safetensors",
        "loras/MiniMaxH3/HMCumshot_V2.safetensors",
    }
    assert sum(entry[2] for entry in module.FILES) == 84_223_835_375
    assert module.MIN_FREE_BYTES == 90 * 1024**3


def test_action_lora_download_requires_civitai_token(monkeypatch):
    monkeypatch.delenv("CIVITAI_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="CIVITAI_API_TOKEN"):
        module._request(
            "https://civitai.com/api/download/models/3226989?fileId=3109184",
            offset=0,
        )


def test_model_bundle_catalog_matches_prepare_script():
    catalog = yaml.safe_load(
        Path("ops/gpu_pool_controller/config/model_bundles.yml").read_text(
            encoding="utf-8"
        )
    )
    bundle = catalog["bundles"][module.BUNDLE]

    assert bundle["version"] == module.VERSION
    assert {
        item["relative_path"]: (item["sha256"], item["size_bytes"])
        for item in bundle["files"]
    } == {
        relative_path: (sha256, size_bytes)
        for relative_path, sha256, size_bytes, _url in module.FILES
    }


def test_prepare_minimax_h3_bundle_validates_and_registers_download(
    monkeypatch, tmp_path
):
    payload = b"official-minimax-h3-test-blob"
    sha256 = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        module,
        "FILES",
        (
            (
                "diffusion_models/MiniMaxH3/test.safetensors",
                sha256,
                len(payload),
                "test.safetensors",
            ),
        ),
    )
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 1)
    monkeypatch.setattr(
        module, "_download", lambda _url, target: target.write_bytes(payload)
    )

    registry = ModelRegistry(tmp_path / "registry")
    manifest = module.prepare(registry)

    assert manifest.is_file()
    assert registry.blob_path(sha256).read_bytes() == payload
    assert "minimax_h3_runtime" in manifest.read_text()


def test_prepare_minimax_h3_bundle_rejects_hash_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        module, "FILES", (("vae/test.safetensors", "0" * 64, 3, "test.safetensors"),)
    )
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 1)
    monkeypatch.setattr(
        module, "_download", lambda _url, target: target.write_bytes(b"bad")
    )

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
        (
            (
                "diffusion_models/MiniMaxH3/test.safetensors",
                sha256,
                len(payload),
                "test.safetensors",
            ),
        ),
    )
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 1)
    monkeypatch.setattr(
        module,
        "_download",
        lambda *_args: pytest.fail(
            "complete partial must not issue an EOF range request"
        ),
    )
    registry = ModelRegistry(tmp_path / "registry")
    registry.ensure_layout()
    partial = (
        registry.root / "tmp" / f"{module.BUNDLE}-{module.VERSION}" / f"{sha256}.part"
    )
    partial.parent.mkdir(parents=True)
    partial.write_bytes(payload)

    module.prepare(registry)

    assert registry.blob_path(sha256).read_bytes() == payload


def test_prepare_reuses_nine_existing_blobs_and_downloads_only_two(
    monkeypatch, tmp_path
):
    payloads = [f"asset-{index}".encode() for index in range(11)]
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
    for (_path, sha256, _size, _url), payload in zip(assets[:9], payloads[:9]):
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

    assert downloads == [9, 10]
    assert manifest["source"]["revision"] == (
        "10eros-beta4-bf16-int8=3c071106; comfy-support=014cd40f"
    )
    assert manifest["obsolete_files"] == sorted(
        module.OBSOLETE_FILES, key=lambda item: item["relative_path"]
    )
    assert (
        "10Eros-Max TURBO hybrid Beta4 BF16 and native INT8 ConvRot"
        in (manifest["source"]["variant"])
    )
    assert [item["relative_path"] for item in manifest["files"]] == sorted(
        item[0] for item in assets
    )
