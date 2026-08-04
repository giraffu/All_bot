from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "workers" / "runpod_profiles" / "minimax_h3" / "Dockerfile"
BUILD_SCRIPT = ROOT / "scripts" / "build_runpod_profile_image.sh"


def test_minimax_h3_image_pins_runtime_and_keeps_weights_external():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "0764232429b8cfb10b79b6f186c8cb23e0b22897" in dockerfile
    assert "f6c759658513b120678bd5f96c2ec0b046a46a46" in dockerfile
    assert "1289b52fbb6d64a339a4047b9ea74cf7758ccf1e" in dockerfile
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
        "VAEDecodeAudio",
        "VHS_VideoCombine",
    ):
        assert node_type in build_script
