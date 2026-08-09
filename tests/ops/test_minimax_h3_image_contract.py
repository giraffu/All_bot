from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "workers" / "runpod_profiles" / "minimax_h3" / "Dockerfile"
BUILD_SCRIPT = ROOT / "scripts" / "build_runpod_profile_image.sh"


def test_minimax_h3_image_pins_runtime_and_keeps_weights_external():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "0764232429b8cfb10b79b6f186c8cb23e0b22897" in dockerfile
    assert "f6c759658513b120678bd5f96c2ec0b046a46a46" in dockerfile
    assert "1289b52fbb6d64a339a4047b9ea74cf7758ccf1e" in dockerfile
    assert "55fee864dd7b2976b1c4ce3c3d5f7968f181409f" in dockerfile
    assert "ComfyUI-MiniMax-H3-Turbo" in dockerfile
    assert "d1a57a546c3d395b1ffcbeecc66d81db76f3b4b5" in dockerfile
    assert "74b6667164f9e368e3799bc2ab59b9b08c4591630f1c6029560208b6fcf354c4" in dockerfile
    assert "sha256:4b9ed5fa8361736996499f64ecebf25d4ec37ff56e4d11323ccde10aa36e0c43" in dockerfile
    assert "sha256:72d3d75f2639ab82b34b29390ad3d6e0827c775befee94edda8e9976818f488d" in dockerfile
    assert "TORCH_CUDA_ARCH_LIST=12.0" in dockerfile
    assert 'torch.__version__ == "2.11.0+cu128"' in dockerfile
    assert "get_cuda_arch_versions" in dockerfile
    assert "sageattention==1.0.6" not in dockerfile
    assert "MiniMaxH3ImageToVideo" in dockerfile
    assert "MiniMaxH3ReferenceToVideo" in dockerfile
    assert "MiniMaxH3MemoryEfficientSageAttentionPatch" in dockerfile
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
        "MiniMaxH3TurboSampler",
        "VAEDecodeAudio",
        "VHS_VideoCombine",
    ):
        assert node_type in build_script
