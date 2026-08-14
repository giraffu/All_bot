from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "workers" / "runpod_profiles" / "minimax_h3" / "Dockerfile"
BUILD_SCRIPT = ROOT / "scripts" / "build_runpod_profile_image.sh"


def test_minimax_h3_image_pins_runtime_and_keeps_weights_external():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "0764232429b8cfb10b79b6f186c8cb23e0b22897" in dockerfile
    assert "f6c759658513b120678bd5f96c2ec0b046a46a46" in dockerfile
    assert "1289b52fbb6d64a339a4047b9ea74cf7758ccf1e" in dockerfile
    assert "ComfyUI-MiniMax-H3-Turbo" not in dockerfile
    assert "COMFYUI_ARCHIVE_SHA256=ba491752490e5b06ee3b918eb9ed20b637c6d60e0cc0fb68ac0e1d44fc033f81" in dockerfile
    assert "d1a57a546c3d395b1ffcbeecc66d81db76f3b4b5" in dockerfile
    assert "74b6667164f9e368e3799bc2ab59b9b08c4591630f1c6029560208b6fcf354c4" in dockerfile
    assert "192.168.1.115:5000/allbot/comfyui-boot@sha256:09c810dd" in dockerfile
    assert "192.168.1.115:5000/nvidia/cuda@sha256:45d0ca2d" in dockerfile
    assert "192.168.1.115:5000/library/python@sha256:9bde3c3a" in dockerfile
    assert "python-runtime-libs/libssl.so.3" in dockerfile
    assert "python-runtime-libs/libcrypto.so.3" in dockerfile
    assert "LD_LIBRARY_PATH=/opt/python-runtime-libs" in dockerfile
    assert "ghcr.io" not in dockerfile
    assert "TORCH_CUDA_ARCH_LIST=12.0" in dockerfile
    assert 'torch.__version__ == "2.11.0+cu128"' in dockerfile
    assert "get_cuda_arch_versions" in dockerfile
    assert "sageattention==1.0.6" not in dockerfile
    assert "MiniMaxH3ImageToVideo" in dockerfile
    assert "MiniMaxH3ReferenceToVideo" in dockerfile
    assert "MiniMaxH3MemoryEfficientSageAttentionPatch" in dockerfile
    assert "https://codeload.github.com/" in dockerfile
    assert "for attempt in 1 2 3" in dockerfile
    assert "d4dc73109ae070afd899a9844cd8b913b602a75cf10d901e2cba100e6dcc89f7" in dockerfile
    assert "external-model-manifest" in dockerfile
    assert "COPY models" not in dockerfile
    assert "COPY checkpoints" not in dockerfile
    assert "COPY *.safetensors" not in dockerfile


def test_minimax_h3_post_build_smoke_checks_registered_runtime_nodes():
    build_script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert 'elif [ "$PROFILE" = "minimax_h3" ]; then' in build_script
    assert "/object_info" in build_script
    for node_type in (
        "MiniMaxH3ImageToVideo",
        "MiniMaxH3ReferenceToVideo",
        "MiniMaxH3MemoryEfficientSageAttentionPatch",
        "MiniMaxH3SigmaShift",
        "DaSiWa_ResolutionScaleCalculator",
        "VAEDecodeAudio",
        "VHS_VideoCombine",
    ):
        assert node_type in build_script
