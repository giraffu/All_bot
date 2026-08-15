from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "workers" / "runpod_profiles" / "minimax_h3" / "Dockerfile"
BUILD_SCRIPT = ROOT / "scripts" / "build_runpod_profile_image.sh"


def test_minimax_h3_image_pins_runtime_and_keeps_weights_external():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "7fe8a6138504f90ff7be82f3babf416da32876b1" in dockerfile
    assert "f6c759658513b120678bd5f96c2ec0b046a46a46" in dockerfile
    assert "1289b52fbb6d64a339a4047b9ea74cf7758ccf1e" in dockerfile
    assert "ComfyUI-MiniMax-H3-Turbo" not in dockerfile
    assert "COMFYUI_ARCHIVE_SHA256=9b2ecedfe742e5b182ab2aa6e6b210a66b3f920e8a97ead8624daed5a2ccffc3" in dockerfile
    assert "ComfyUI-MiniMax-ContextIR" not in dockerfile
    assert "be93b9375ebe8b24fa431609f56fa8f441b4b37f" in dockerfile
    assert "22124250c3da2f3b6cab6ebda7158d281144f6cfa9423c65f20b50112f29465c" in dockerfile
    assert "192.168.1.115:5000/allbot/comfyui-boot@sha256:09c810dd" in dockerfile
    assert "ghcr.io" not in dockerfile
    assert "get_cuda_arch_versions" not in dockerfile
    assert "SAGEATTENTION_REPO" not in dockerfile
    assert "MiniMaxH3ImageToVideo" in dockerfile
    assert "LoraLoaderModelOnly" in dockerfile
    assert "grep -q 'MiniMaxH3SigmaShift' \"${COMFYUI_INSTALL_DIR}/comfy_extras/nodes_minimax_h3.py\"" in dockerfile
    assert "ReservedVRAMSetter" in dockerfile
    assert "ModelAttentionBackend" in dockerfile
    assert "MiniMaxH3ReferenceToVideo" not in dockerfile
    assert "MiniMaxH3MemoryEfficientSageAttentionPatch" not in dockerfile
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
    assert '"comfy kitchen attention" in attention' in build_script
    for node_type in (
        "MiniMaxH3ImageToVideo",
        "LoraLoaderModelOnly",
        "ReservedVRAMSetter",
        "ModelAttentionBackend",
        "MiniMaxH3SigmaShift",
        "DaSiWa_ResolutionScaleCalculator",
        "VAEDecodeAudio",
        "VHS_VideoCombine",
    ):
        assert node_type in build_script
