from pathlib import Path
import os
import subprocess


BOOTSTRAP_SCRIPT = Path("remote_workers/scripts/runpod_bootstrap_from_git.sh")
PROFILE_DOCKERFILE = Path("remote_workers/docker/runpod_profiles/img2img_lora/Dockerfile")
PROFILE_LOCAL_DOCKERFILE = Path(
    "remote_workers/docker/runpod_profiles/img2img_lora/Dockerfile.local-kjnodes"
)
WAN22_PROFILE_DOCKERFILE = Path("remote_workers/docker/runpod_profiles/wan22_aio_video/Dockerfile")
PROFILE_BUILD_SCRIPT = Path("scripts/build_runpod_profile_image.sh")


def test_runpod_bootstrap_script_has_valid_bash_syntax():
    subprocess.run(
        ["bash", "-n", str(BOOTSTRAP_SCRIPT)],
        check=True,
    )


def test_runpod_bootstrap_installs_kjnodes_before_starting_comfyui():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    install_call_index = script.index("install_comfyui_custom_nodes\n")
    comfy_start_index = script.index('log "starting ComfyUI')

    assert "ComfyUI-KJNodes" in script
    assert "RUNPOD_COMFY_KJNODES_ENABLED" in script
    assert install_call_index < comfy_start_index


def test_runpod_bootstrap_patches_remote_worker_pop_agent_id():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    assert "comfy_agent/agent_main.py" in script
    assert '"params: dict[str, str] = {\\"agent_id\\": AGENT_ID}"' in script


def test_runpod_bootstrap_patches_model_sync_for_resume_downloads():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    assert "scripts/runpod_sync_models_from_r2.py" in script
    assert "_download_object_with_resume" in script
    assert "RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS" in script
    assert "RUNPOD_MODEL_DOWNLOAD_PROGRESS_BYTES" in script
    assert "offset=current_size" in script


def test_runpod_profile_build_script_has_valid_bash_syntax():
    subprocess.run(
        ["bash", "-n", str(PROFILE_BUILD_SCRIPT)],
        check=True,
    )


def test_img2img_lora_profile_image_bakes_custom_nodes_not_business_models():
    dockerfile = PROFILE_DOCKERFILE.read_text(encoding="utf-8")
    local_dockerfile = PROFILE_LOCAL_DOCKERFILE.read_text(encoding="utf-8")
    build_script = PROFILE_BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "ComfyUI-KJNodes" in dockerfile
    assert "KJNODES_REF=7967a946c296a74901606e6a8d1195aa2b6f9215" in dockerfile
    assert "COPY ComfyUI-KJNodes" in local_dockerfile
    assert "Qwen-Rapid-AIO-NSFW-v23.safetensors" in dockerfile
    assert "Qwen-Rapid-AIO-NSFW-v23.safetensors" in local_dockerfile
    assert "Business model file unexpectedly present" in dockerfile
    assert "Business model file unexpectedly present" in local_dockerfile
    assert "--kjnodes-source" in build_script
    assert "RUNPOD_MODEL_SYNC_ENABLED=true" in build_script
    assert "Business model files must stay out of the profile image" in build_script


def test_wan22_profile_image_bakes_video_custom_nodes_not_business_models():
    dockerfile = WAN22_PROFILE_DOCKERFILE.read_text(encoding="utf-8")
    build_script = PROFILE_BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "ComfyUI-KJNodes" in dockerfile
    assert "ComfyUI-VideoHelperSuite" in dockerfile
    assert "rgthree-comfy" in dockerfile
    assert "ComfyUI-Frame-Interpolation" in dockerfile
    assert "ComfyUI-GGUF" in dockerfile
    assert "ComfyUI-DaSiWa-Nodes" in dockerfile
    assert "comfyui-WhiteRabbit" in dockerfile
    assert "ffmpeg" in dockerfile
    assert "torchlanc" in dockerfile
    assert "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors" in dockerfile
    assert "DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors" in dockerfile
    assert "Business model file unexpectedly present" in dockerfile
    assert "wan22_aio_video" in build_script
    assert "WAN22_CUSTOM_NODES_PRESENT=true" in build_script


def test_profile_build_script_accepts_wan22_profile_without_running_real_docker(tmp_path):
    calls = tmp_path / "docker-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$DOCKER_CALLS\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_CALLS": str(calls),
    }

    subprocess.run(
        [
            "bash",
            str(PROFILE_BUILD_SCRIPT),
            "--profile",
            "wan22_aio_video",
            "--image-ref",
            "allbot/comfy-runpod-wan22-aio-video:test",
            "--no-smoke",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    rendered = calls.read_text(encoding="utf-8")
    assert "remote_workers/docker/runpod_profiles/wan22_aio_video/Dockerfile" in rendered
    assert "allbot.runpod.profile=wan22_aio_video" in rendered
    assert "allbot/comfy-runpod-wan22-aio-video:test" in rendered


def test_profile_build_script_rejects_unknown_profile_before_docker(tmp_path):
    calls = tmp_path / "docker-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$DOCKER_CALLS\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_CALLS": str(calls),
    }

    result = subprocess.run(
        ["bash", str(PROFILE_BUILD_SCRIPT), "--profile", "unknown"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Unsupported RunPod profile: unknown" in result.stderr
    assert not calls.exists()
