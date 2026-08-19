import hashlib

import pytest
import yaml

from ops.gpu_pool_controller.model_repo import ModelRegistry
from scripts import prepare_minimax_h3_model_bundle as module


def test_split_author_stack_uses_exact_eighteen_pinned_assets():
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
    assert files["loras/MiniMaxH3/HMNSFW_AIO_V2.safetensors"][1:3] == (
        "608e4212f2788b6063330ff1196fc1f4b4228cfd9a413a63c198a09d7e4a61cb",
        310_168_344,
    )
    assert files["loras/MiniMaxH3/H3_Motion_BoosterV2.safetensors"][1:4] == (
        "f6a6897162b921d2b74abe1fdebcd80c8189147e70e0e0738200756c250336c3",
        155_110_272,
        "https://civitai.red/api/download/models/3228867?fileId=3111185",
    )
    assert files["loras/MiniMaxH3/MysticXXX_MMH3-V2.safetensors"][1:4] == (
        "2fc32615f20465e0831a5c8069df4006422fc9638a0b7faa216e04a6ddfee8de",
        172_057_936,
        "https://civitai.red/api/download/models/3242519?fileId=3125221",
    )
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
    assert files["loras/MiniMaxH3/HMPenis_v2_e35.safetensors"][1:3] == (
        "c6c58e9fee848b45e99f97d2520aba4ac63dfc354c07e13c29ac5d8a31a68060",
        310_168_344,
    )
    assert files["loras/MiniMaxH3/breastplayjiggle_h3_v1.safetensors"][1:3] == (
        "f9cbcaa596b6b281f154388e407e7b4c4ee97ba9917614ab36bc5e86edf374f5",
        298_260_984,
    )
    assert files["loras/MiniMaxH3/HMInnie_v1_e50.safetensors"][1:3] == (
        "499196c9d0e5f81ff575ba39a82987112c3bb1e09fbede858877cd950d6c8833",
        310_168_344,
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
    assert len(files) == 18


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


def test_prepare_reuses_nine_existing_blobs_and_downloads_only_two(monkeypatch, tmp_path):
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
    assert [item["relative_path"] for item in manifest["files"]] == sorted(
        item[0] for item in assets
    )
