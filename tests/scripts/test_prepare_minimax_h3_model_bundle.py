import hashlib
from pathlib import Path

import pytest
import yaml

from ops.gpu_pool_controller.model_repo import ModelRegistry
from scripts import prepare_minimax_h3_model_bundle as module


def test_split_author_stack_uses_exact_twenty_six_pinned_assets():
    files = {entry[0]: entry for entry in module.FILES}

    assert files[
        "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors"
    ][1:4] == (
        "bf34b4c9d2fa973ae84c480a1a5a04d2978958023bb6be7375b3b9e4818965e3",
        40_222_982_192,
        "https://huggingface.co/TenStrip/10Eros-Max/resolve/3c071106f5b62c02b3cb0b7d831083cdb582b289/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors",
    )
    assert files[
        "diffusion_models/MiniMaxH3/minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    ][1:4] == (
        "e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a",
        20_970_379_616,
        "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4cc1d817b6184899b41293954329f576cb5ae86b/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    )
    assert files[
        "diffusion_models/MiniMaxH3/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
    ][1:4] == (
        "9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779",
        20_970_379_616,
        "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4cc1d817b6184899b41293954329f576cb5ae86b/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
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
    assert files[
        "loras/MiniMaxH3/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
    ][1:4] == (
        "5b9ab5ade15d0775676d01a907268a69a1468dc6033b3b0d3ded5502f3ebb84c",
        1_956_193_000,
        "https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/ec01fa4c86263832faa0bd1d6d8f36a281eaabb2/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
    )
    assert files["loras/MiniMaxH3/NaughtyTimes_pruned_r256_v2.safetensors"][1:4] == (
        "947efec5a357505bb93bdc1b050d33786ec150aa1c85f24337f0d59f39aaf31a",
        2_242_444_272,
        "https://civitai.red/api/download/models/3212436?fileId=3094173",
    )
    assert files["loras/MiniMaxH3/HMNSFW-AIO-V2.5.safetensors"][1:4] == (
        "a07732a84fd733085eb5d910f602f918fa7a3658117116927e4329f5951a9d2d",
        86_040_232,
        "https://civitai.red/api/download/models/3268303?fileId=3152083",
    )
    assert files["loras/MiniMaxH3/H3_Motion_BoosterV2.safetensors"][1:4] == (
        "f6a6897162b921d2b74abe1fdebcd80c8189147e70e0e0738200756c250336c3",
        155_110_272,
        "https://civitai.red/api/download/models/3228867?fileId=3111185",
    )
    assert files["loras/MiniMaxH3/ref2VA_Motion_v2.safetensors"][1:4] == (
        "b48cf96ebb14985789528449fe61985babf786feb658740a82a88ac685167fd9",
        155_110_288,
        "https://civitai.red/api/download/models/3246346?fileId=3129119",
    )
    assert files["loras/MiniMaxH3/VBVR_H3_attn_only.safetensors"][1:4] == (
        "372597997f646301dea204bf00e899b0f470254d7b9ac345e7b7417cc2140b34",
        32_826_752,
        "https://civitai.red/api/download/models/3220766?fileId=3102749",
    )
    assert files["loras/MiniMaxH3/MysticXXX_MMH3-V4.safetensors"][1:4] == (
        "fc3e856d14c6c19557c888f48662d591e4794e281233ec0d987be5003068afba",
        155_095_800,
        "https://civitai.red/api/download/models/3266628?fileId=3150341",
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
    assert files["loras/MiniMaxH3/PenisV2_minimax-h3_epoch60.safetensors"][1:4] == (
        "017dd1adddc1be3ec0605dd2e7de97138eb2c6c6ba24be402cf47f103ac1f1b3",
        77_580_008,
        "https://civitai.red/api/download/models/3247473?fileId=3130327",
    )
    assert files["loras/MiniMaxH3/HMCumshot_V2.safetensors"][1:4] == (
        "1a5b7948bb97f27737e62c3dd5497a3afb77517f230787f45e45c7d8fe3dc24d",
        626_294_968,
        "https://civitai.red/api/download/models/3238531?fileId=3121030",
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
    assert files["loras/MiniMaxH3/Vagina_minimax-h3_epoch20.safetensors"][1:4] == (
        "373c3cad3bf27047fdd754fe111443d97e70e3108a8829f2ec63c48832466eb3",
        77_580_008,
        "https://civitai.red/api/download/models/3252213?fileId=3135252",
    )
    assert files[
        "loras/MiniMaxH3/Titjob_Titfuck_V1-MiniMaxh3_ComfyTinker.safetensors"
    ][1:4] == (
        "4a0679c613a5c52d8fd59c48455996402206eefa347939e5bbc736b530d196f5",
        155_110_304,
        "https://civitai.red/api/download/models/3252313?fileId=3135351",
    )
    assert len(files) == 26
    assert sum(entry[2] for entry in module.FILES) == 114_101_302_207
    assert module.MIN_FREE_BYTES == 110 * 1024**3


def test_naughtytimes_download_requires_civitai_token(monkeypatch):
    monkeypatch.delenv("CIVITAI_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="CIVITAI_API_TOKEN"):
        module._request(
            "https://civitai.red/api/download/models/3212436?fileId=3094173",
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
    assert manifest["source"]["revision"] == (
        "10eros-beta4=3c071106; comfy-int8=4cc1d817; "
        "comfy-support=014cd40f; lightx2v=ec01fa4c"
    )
    assert manifest["obsolete_files"] == [
        {
            "relative_path": "diffusion_models/MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta3.safetensors",
            "sha256": "ea0df6670a84dfe594fe12c1202dfd82a497dbf2a75d6f06279a6b6993ab64b2",
            "size_bytes": 40_228_492_688,
        }
    ]
    assert "official pruned INT8 ConvRot" in manifest["source"]["variant"]
    assert [item["relative_path"] for item in manifest["files"]] == sorted(
        item[0] for item in assets
    )
