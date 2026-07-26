from pathlib import Path
import os
import subprocess


BOOTSTRAP_SCRIPT = Path("remote_workers/scripts/runpod_bootstrap_from_git.sh")
ENTRYPOINT_SCRIPT = Path("remote_workers/scripts/runpod_entrypoint.sh")
BAKED_ENTRYPOINT_SCRIPT = Path(
    "remote_workers/scripts/runpod_baked_runtime_entrypoint.sh"
)
PROFILE_DOCKERFILE = Path("remote_workers/docker/runpod_profiles/img2img_lora/Dockerfile")
PROFILE_LOCAL_DOCKERFILE = Path(
    "remote_workers/docker/runpod_profiles/img2img_lora/Dockerfile.local-kjnodes"
)
WAN22_PROFILE_DOCKERFILE = Path("remote_workers/docker/runpod_profiles/wan22_aio_video/Dockerfile")
LTX_T2V_RUNTIME_REFRESH_DOCKERFILE = Path(
    "remote_workers/docker/runpod_profiles/ltx_t2v/Dockerfile.runtime-refresh"
)
PROFILE_BUILD_SCRIPT = Path("scripts/build_runpod_profile_image.sh")
WAN22_PROVEN_COMFY_CU128_BASE = "yanwk/comfyui-boot:cu128-slim"


def test_runpod_bootstrap_script_has_valid_bash_syntax():
    subprocess.run(
        ["bash", "-n", str(BOOTSTRAP_SCRIPT)],
        check=True,
    )


def test_runpod_entrypoint_script_has_valid_bash_syntax():
    for path in (ENTRYPOINT_SCRIPT, BAKED_ENTRYPOINT_SCRIPT):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_runpod_runtime_requires_baked_agent_and_never_clones_allbot_at_startup():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    baked_entrypoint = BAKED_ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    assert "git clone --depth 1 --branch \"$REPO_BRANCH\"" not in bootstrap
    assert "baked AllBot remote worker bundle is missing" in bootstrap
    assert "ALLBOT_RUNPOD_REPO_DIR:-/opt/allbot/runtime" in baked_entrypoint
    assert "${runtime_root}/remote_workers" in baked_entrypoint
    assert "comfy_agent/workflows" in baked_entrypoint


def test_runpod_bootstrap_and_entrypoint_supervise_managed_processes():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    for script in (bootstrap, entrypoint):
        assert "shutdown_children" in script
        assert "wait -n" in script
        assert "stopping container for restart policy" in script


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


def test_runpod_bootstrap_patches_wan22_runtime_node_inputs():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    assert "comfy_agent/workflow_task_patchers.py" in script
    assert "WAN22_VIDEO_V2_LAST_FRAME_FALLBACK_INDEX = 4095" in script
    assert 'input_name="resolution_preset"' in script
    assert 'input_name="swap_aspect_when_not_image"' in script
    assert 'input_name="aspect_preset_when_not_image"' in script
    assert 'input_name="custom_aspect_width"' in script
    assert 'input_name="custom_aspect_height"' in script


def test_runpod_bootstrap_patches_model_sync_for_resume_downloads():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    assert "scripts/runpod_sync_models_from_r2.py" in script
    assert "_download_object_with_resume" in script
    assert "RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS" in script
    assert "RUNPOD_MODEL_DOWNLOAD_PROGRESS_BYTES" in script
    assert "offset=current_size" in script


def test_runpod_bootstrap_checks_wan22_rife_cache_before_starting_comfyui():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    assert "ensure_wan22_rife_cache.py" in script
    assert script.index("ensure_wan22_rife_cache\n") < script.index(
        'log "starting ComfyUI'
    )
    assert "ensure_wan22_rife_cache.py" in entrypoint
    assert (
        "\nensure_wan22_rife_cache\n\nif [ -n \"${COMFYUI_DIR:-}\" ]"
        in entrypoint
    )


def test_runpod_bootstrap_and_entrypoint_recognize_baked_comfyui_dir_marker():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    assert "/opt/allbot-comfyui-dir" in bootstrap
    assert "resolve_baked_comfyui_dir" in bootstrap
    assert 'log "starting ComfyUI from ${baked_comfyui_dir}"' in bootstrap
    assert "/opt/allbot-comfyui-dir" in entrypoint
    assert "resolve_baked_comfyui_dir" in entrypoint
    assert "cd \"$baked_comfyui_dir\"" in entrypoint


def test_runpod_profile_build_script_has_valid_bash_syntax():
    subprocess.run(
        ["bash", "-n", str(PROFILE_BUILD_SCRIPT)],
        check=True,
    )


def test_ltx_t2v_runtime_refresh_is_digest_based_and_revalidates_fixed_graphs():
    dockerfile = LTX_T2V_RUNTIME_REFRESH_DOCKERFILE.read_text(encoding="utf-8")

    assert (
        "BASE_IMAGE=192.168.1.115:5000/allbot/comfy-runpod-ltx-t2v@sha256:"
        "124cd638cab69e87c39946190a7e17169b6223e35c7d946e9df540719ddb385b"
        in dockerfile
    )
    assert "LTX 2.3 Sulphur Ingredients T2V.json" in dockerfile
    assert 'ic["26:91"]["inputs"]["latent"] == ["26:153",0]' in dockerfile
    assert "LTX model files must stay out of the runtime refresh image" in dockerfile


def test_pornmaster_profile_smoke_requires_bf16_workflow_and_mapping():
    build_script = PROFILE_BUILD_SCRIPT.read_text(encoding="utf-8")
    smoke_command = next(
        line
        for line in build_script.splitlines()
        if line.startswith('RUNTIME_ROOT="${runtime_root}" python3 -c')
    )

    assert (
        "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_"
        "V1_2026_05_27.api.json" in build_script
    )
    assert (
        "PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_"
        "V1_2026_05_27.api.json" in build_script
    )
    assert '\\"pornmaster_flux2_multi_edit_bf16\\"} <= mappings.keys()' in build_script
    assert '\\"pornmaster_flux2_edit_bf16\\" in validation' in build_script
    assert '\\"pornmaster_flux2_multi_edit_bf16\\" in validation' in build_script
    assert "BF16_WORKFLOW_AND_MAPPING_PRESENT=true" in build_script
    assert "'" not in smoke_command


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

    assert f"ARG BASE_IMAGE={WAN22_PROVEN_COMFY_CU128_BASE}" in dockerfile
    assert "COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git" in dockerfile
    assert "COMFYUI_REF=master" in dockerfile
    assert "COMFYUI_INSTALL_DIR=/opt/ComfyUI" in dockerfile
    assert "ARG REUSE_BASE_CUSTOM_NODES=false" in dockerfile
    assert "Reusing baked custom nodes from base image" in dockerfile
    assert "require_existing_node" in dockerfile
    assert "sys.exit(\"REUSE_BASE_CUSTOM_NODES=true" in dockerfile
    assert "if missing else 0" in dockerfile
    assert "Reusing baked ComfyUI_Fill-Nodes from base image" in dockerfile
    assert "Reusing baked ComfyUI-LTXVideo from base image" in dockerfile
    assert "git clone --filter=blob:none" in dockerfile
    assert 'rm -rf "${target}/.git"' in dockerfile
    assert "python3 -m pip cache purge" in dockerfile
    assert "ComfyUI-KJNodes" in dockerfile
    assert "ComfyUI-VideoHelperSuite" in dockerfile
    assert "2984ec4c4b93292421888f38db74a5e8802a8ff8" in dockerfile
    assert "rgthree-comfy" in dockerfile
    assert "683836c46e898668936c433502504cc0627482c5" in dockerfile
    assert "ComfyUI-Frame-Interpolation" in dockerfile
    assert "26545cc2dd95bc3d27f056016300673bdeee78f5" in dockerfile
    assert "ComfyUI_Fill-Nodes" in dockerfile
    assert "2c94c3b675e7832ae18986e7062365c7d025b802" in dockerfile
    assert "RIFE49_URL=https://huggingface.co/lividtm/RIFE/resolve/main/rife49.pth" in dockerfile
    assert "RIFE49_SHA256=e55fd00f3cc184e3c65961f4bb827a9da022e78eed36b055242c0ac30000d533" in dockerfile
    assert "ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth" in dockerfile
    assert "ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth" in dockerfile
    assert "ComfyUI-LTXVideo" in dockerfile
    assert "229437c6b65796d6a7a63ae34be2bd5ba31fa543" in dockerfile
    assert "LTXVSpatioTemporalTiledVAEDecode" in dockerfile
    assert "NODE_CLASS_MAPPINGS = dict(RUNTIME_NODE_CLASS_MAPPINGS)" in dockerfile
    assert (
        "COPY remote_workers/scripts/runpod_bootstrap_from_git.sh "
        "/opt/allbot/runpod_bootstrap_from_git.sh"
    ) in dockerfile
    assert "COPY remote_workers /opt/allbot/runtime/remote_workers" in dockerfile
    assert (
        'CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]'
        in dockerfile
    )
    assert (
        "# Keep the FL_RIFE provider in a final small layer" in dockerfile
    )
    assert dockerfile.index('echo "${comfyui_dir}" > /opt/allbot-comfyui-dir') < dockerfile.index(
        "# Keep the FL_RIFE provider in a final small layer"
    )
    assert "ComfyUI-GGUF" in dockerfile
    assert "ComfyUI-DaSiWa-Nodes" in dockerfile
    assert "comfyui-WhiteRabbit" in dockerfile
    assert "ffmpeg" in dockerfile
    assert "torchlanc" in dockerfile
    assert "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors" in dockerfile
    assert "DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors" in dockerfile
    assert "Business model file unexpectedly present" in dockerfile
    assert "wan22_aio_video" in build_script
    assert WAN22_PROVEN_COMFY_CU128_BASE in build_script
    assert "--comfyui-ref" in build_script
    assert "--reuse-base-custom-nodes" in build_script
    assert "REUSE_BASE_CUSTOM_NODES" in build_script
    assert "ComfyUI_Fill-Nodes" in build_script
    assert "ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth" in build_script
    assert "ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth" in build_script
    assert "ComfyUI-LTXVideo" in build_script
    assert "LTXVSpatioTemporalTiledVAEDecode" in build_script
    assert "module.NODE_CLASS_MAPPINGS" in build_script
    assert "WAN22_CUSTOM_NODES_PRESENT=true" in build_script


def test_wan22_github_workflow_defaults_to_lan_proven_base_and_comfyui_ref():
    workflow = Path(".github/workflows/runpod_wan22_profile_image.yml").read_text(
        encoding="utf-8"
    )

    assert f'default: "{WAN22_PROVEN_COMFY_CU128_BASE}"' in workflow
    assert "comfyui_ref:" in workflow
    assert "reuse_base_custom_nodes:" in workflow
    assert "--comfyui-ref" in workflow
    assert "--reuse-base-custom-nodes" in workflow
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" in workflow


def test_face_swap_github_workflow_publishes_dedicated_revision_pinned_image():
    workflow = Path(".github/workflows/runpod_face_swap_profile_image.yml").read_text(
        encoding="utf-8"
    )

    assert "IMAGE_NAME: allbot-gpu-face-swap" in workflow
    assert "--profile face_swap" in workflow
    assert "ALLBOT_GIT_SHA: ${{ github.sha }}" in workflow
    assert "io.allbot.runpod.agent-revision" in workflow
    assert "io.allbot.runpod.workflow-revision" in workflow
    assert "face_swap_v2/2026-07-25/manifest.json" in workflow
    assert "docker manifest inspect" in workflow


def test_ltx_t2v_github_workflow_builds_exact_main_revision_without_models():
    workflow = Path(
        ".github/workflows/runpod_ltx_t2v_profile_image.yml"
    ).read_text(encoding="utf-8")

    assert "source_sha:" in workflow
    assert "git merge-base --is-ancestor" in workflow
    assert "IMAGE_NAME: allbot-gpu-ltx-t2v" in workflow
    assert "--profile ltx_t2v" in workflow
    assert "ALLBOT_GIT_SHA: ${{ inputs.source_sha }}" in workflow
    assert "org.opencontainers.image.revision" in workflow
    assert "io.allbot.runpod.agent-revision" in workflow
    assert "io.allbot.runpod.workflow-revision" in workflow
    assert "ltx_t2v/2026-07-22/manifest.json" in workflow
    assert "docker manifest inspect" in workflow


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
    assert f"BASE_IMAGE={WAN22_PROVEN_COMFY_CU128_BASE}" in rendered
    assert "COMFYUI_REF=master" in rendered
    assert "REUSE_BASE_CUSTOM_NODES=false" in rendered
    assert "allbot.runpod.profile=wan22_aio_video" in rendered
    assert "allbot/comfy-runpod-wan22-aio-video:test" in rendered


def test_profile_build_script_can_reuse_base_custom_nodes(tmp_path):
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
            "--base-image",
            "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:fast-base",
            "--reuse-base-custom-nodes",
            "--no-smoke",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    rendered = calls.read_text(encoding="utf-8")
    assert (
        "BASE_IMAGE=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:fast-base"
        in rendered
    )
    assert "REUSE_BASE_CUSTOM_NODES=true" in rendered


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
