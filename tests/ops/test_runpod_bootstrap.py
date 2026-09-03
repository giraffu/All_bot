from pathlib import Path
import json
import os
import shutil
import subprocess
import sys


BOOTSTRAP_SCRIPT = Path("workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh")
ENTRYPOINT_SCRIPT = Path("workers/runpod_runtime/scripts/runpod_entrypoint.sh")
BAKED_ENTRYPOINT_SCRIPT = Path(
    "workers/runpod_runtime/scripts/runpod_baked_runtime_entrypoint.sh"
)
EMBEDDED_TEST_AGENT_SCRIPT = Path(
    "workers/runpod_runtime/scripts/runpod_embedded_test_agent.sh"
)
PROFILE_DOCKERFILE = Path("workers/runpod_profiles/img2img_lora/Dockerfile")
PROFILE_LOCAL_DOCKERFILE = Path(
    "workers/runpod_profiles/img2img_lora/Dockerfile.local-kjnodes"
)
WAN22_PROFILE_DOCKERFILE = Path("workers/runpod_profiles/wan22_aio_video/Dockerfile")
I2I_PRO_PROFILE_DOCKERFILE = Path("workers/runpod_profiles/i2i_pro/Dockerfile")
PORNMASTER_PROFILE_DOCKERFILE = Path(
    "workers/runpod_profiles/pornmaster_flux2_edit/Dockerfile"
)
LTX_T2V_RUNTIME_REFRESH_DOCKERFILE = Path(
    "workers/runpod_profiles/ltx_t2v/Dockerfile.runtime-refresh"
)
LAN_ALL_PROFILE_DOCKERFILE = Path("workers/runpod_profiles/all/Dockerfile")
LAN_ALL_RUNTIME_REFRESH_DOCKERFILE = Path(
    "workers/runpod_profiles/all/Dockerfile.runtime-refresh"
)
SCAIL2_FLEX_DOCKERFILE = Path("workers/runpod_profiles/scail2_flex/Dockerfile")
MODULE_CATALOG = Path("deploy/module-catalog.json")
PROFILE_BUILD_SCRIPT = Path("scripts/build_runpod_profile_image.sh")
WAN22_PROVEN_COMFY_CU128_BASE = "yanwk/comfyui-boot:cu128-slim"
RUNTIME_REFRESH_MODULES = {
    "i2i_pro_runtime_refresh": (
        "allbot-gpu-i2i-pro",
        "i2i_pro",
        "d5366bd4f9ac8c046b9f9348b80c9e693e3cd021d558b79fb4b9c3959e891df8",
        True,
    ),
    "wan22_video_v2_runtime_refresh": (
        "allbot-gpu-wan22-aio-video",
        "wan22_aio_video",
        "ef8b23ed217bece3461bff46ebd14715a98342e24eeea44a6b4d451228abede6",
        True,
    ),
    "minimax_h3_runtime_refresh": (
        "allbot-gpu-minimax-h3",
        "minimax_h3",
        "c19e747dcac67a6efcbe3a360de0ce56180d06e9e70f2cda7665a8a16c05686a",
        True,
    ),
    "img2img_runtime_refresh": (
        "allbot-gpu-img2img-lora",
        "img2img_lora",
        "1045a42a0baaccecb956a566f836e732d14de8fcf317142584a29b7e6bf5e4f3",
        True,
    ),
    "ltx_video_runtime_refresh": (
        "allbot-gpu-ltx-video-v2",
        "ltx_video",
        "abc5f9f1261563ad0a946ee065504b70792e7e701b165e6c1b62cd49ef5d4a86",
        True,
    ),
    "ltx_t2v_runtime_refresh": (
        "allbot-gpu-ltx-t2v",
        "ltx_t2v",
        "b956eb3ff3ee1518c92314a40d44b10d0734d91de5ed09cea05214df30511897",
        True,
    ),
    "pornmaster_flux2_edit_bf16_runtime_refresh": (
        "allbot-gpu-pornmaster-flux2-edit-bf16",
        "pornmaster_flux2_edit",
        "505b455a1b028d2642a1e4cc659eb1b1153f0e6751d763941a8ff81e8e7ea587",
        True,
    ),
    "scail2_runtime_refresh": (
        "allbot-gpu-scail2",
        "scail2",
        "6bd4017e3a515ce13f58e5db969e56902861c024fac38c620176b29a1cbc0916",
        True,
    ),
    "lan_scail2_flex_runtime_refresh": (
        "allbot-gpu-lan-scail2-flex",
        "scail2_flex",
        "04222c3921dcceadf7a0fa0e5f6c7c7becd8bb038cce7bfc097a5b69ff168dfa",
        False,
    ),
}


def test_i2i_pro_profile_uses_the_regional_pypi_mirror_for_comfyui_dependencies():
    dockerfile = I2I_PRO_PROFILE_DOCKERFILE.read_text(encoding="utf-8")

    install_at = dockerfile.index("python3 -m pip install --no-cache-dir")
    mirror_at = dockerfile.index(
        "-i https://mirrors.aliyun.com/pypi/simple/", install_at
    )
    requirements_at = dockerfile.index(
        '-r "${comfyui_dir}/requirements.txt"', mirror_at
    )

    assert install_at < mirror_at < requirements_at


def test_i2i_pro_profile_pins_the_persisted_workspace_aimdo_contract():
    dockerfile = I2I_PRO_PROFILE_DOCKERFILE.read_text(encoding="utf-8")

    assert '"comfy-aimdo==0.3.0"' in dockerfile


def test_i2i_pro_profile_bakes_the_shared_result_materialization_runtime():
    dockerfile = I2I_PRO_PROFILE_DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY shared /opt/allbot/runtime/runpod_worker/shared" in dockerfile
    assert "from shared.character_reference_sheet import" in dockerfile


def test_wan22_profile_bakes_the_shared_result_materialization_runtime():
    dockerfile = WAN22_PROFILE_DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY shared /opt/allbot/runtime/runpod_worker/shared" in dockerfile
    assert "from shared.character_reference_sheet import" in dockerfile


def test_every_gpu_profile_bakes_the_shared_result_materialization_runtime():
    catalog = json.loads(MODULE_CATALOG.read_text(encoding="utf-8"))["modules"]
    dockerfiles = {
        Path(module["dockerfile"])
        for module in catalog.values()
        if module.get("kind") == "gpu" and module.get("dockerfile")
    }

    missing_shared = []
    missing_smoke_import = []
    for path in sorted(dockerfiles):
        dockerfile = path.read_text(encoding="utf-8")
        if "COPY workers/runpod_runtime " not in dockerfile:
            continue
        if "COPY shared /opt/allbot/runtime/runpod_worker/shared" not in dockerfile:
            missing_shared.append(str(path))
        if "from shared.character_reference_sheet import" not in dockerfile:
            missing_smoke_import.append(str(path))

    assert missing_shared == []
    assert missing_smoke_import == []


def test_every_gpu_profile_bakes_worker_dependencies_for_offline_startup():
    catalog = json.loads(MODULE_CATALOG.read_text(encoding="utf-8"))["modules"]
    dockerfiles = {
        Path(module["dockerfile"])
        for module in catalog.values()
        if module.get("kind") == "gpu" and module.get("dockerfile")
    }

    missing_install = []
    for path in sorted(dockerfiles):
        dockerfile = path.read_text(encoding="utf-8")
        if "COPY workers/runpod_runtime " not in dockerfile:
            continue
        normalized = " ".join(dockerfile.split())
        installs_dependencies = (
            "python3 -m pip install --no-cache-dir -r "
            "/opt/allbot/runtime/runpod_worker/requirements.txt"
        ) in normalized or (
            "python3 -m pip install --no-cache-dir -r "
            "/opt/allbot/runpod_worker/requirements.txt"
        ) in normalized
        dependency_closed_refresh = "RUNTIME_REQUIREMENTS_SHA256" in dockerfile
        if not installs_dependencies and not dependency_closed_refresh:
            missing_install.append(str(path))

    assert missing_install == []


def test_baked_bootstrap_skips_network_install_when_dependencies_are_present():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    assert "verify_worker_dependencies" in bootstrap
    assert "if verify_worker_dependencies; then" in bootstrap
    assert (
        'log "baked Worker dependencies are ready; skipping pip install"' in bootstrap
    )
    assert "RUNPOD_WORKER_DEPENDENCY_MODE:-auto" in bootstrap
    assert "RUNPOD_WORKER_DEPENDENCY_MODE:-baked" in BAKED_ENTRYPOINT_SCRIPT.read_text(
        encoding="utf-8"
    )
    assert bootstrap.index("if verify_worker_dependencies; then") < bootstrap.index(
        "python3 -m pip install -r requirements.txt"
    )


def test_runpod_bootstrap_script_has_valid_bash_syntax():
    subprocess.run(
        ["bash", "-n", str(BOOTSTRAP_SCRIPT)],
        check=True,
    )


def test_scail2_flex_artifact_is_a_restricted_union_runtime():
    dockerfile = SCAIL2_FLEX_DOCKERFILE.read_text(encoding="utf-8")
    catalog = MODULE_CATALOG.read_text(encoding="utf-8")

    assert "AllBot LAN SCAIL-2 flex runtime" in dockerfile
    assert 'allbot.lan.profile="scail2_flex"' in dockerfile
    assert "scail2_action_transfer" in dockerfile
    assert "scail2_action_transfer_long" in dockerfile
    assert "scail2_video_replacement" in dockerfile
    assert "scail2_face_swap_v2" in dockerfile
    assert "img2img" in dockerfile
    assert "img2img_lora" in dockerfile
    assert '"lan_scail2_flex"' in catalog


def test_runpod_entrypoint_script_has_valid_bash_syntax():
    for path in (
        ENTRYPOINT_SCRIPT,
        BAKED_ENTRYPOINT_SCRIPT,
        EMBEDDED_TEST_AGENT_SCRIPT,
    ):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_ltx25_embedded_test_worker_is_narrow_and_test_isolated():
    script = EMBEDDED_TEST_AGENT_SCRIPT.read_text(encoding="utf-8")

    assert 'SUPPORTED_TASK_TYPES="${RUNPOD_TEST_SUPPORTED_TASK_TYPES:-ltx25_video_upscale}"' in script
    assert 'POOL_RUNTIME_PROFILE="${RUNPOD_TEST_RUNTIME_PROFILE:-ltx25_video_upscale}"' in script
    assert 'MINIO_INPUT_BUCKET="$bucket"' in script
    assert 'MINIO_RESULT_BUCKET="$bucket"' in script
    assert 'COMFY_API_URL="http://127.0.0.1:8188"' in script
    assert 'POOL_MANAGED="false"' in script
    assert "RUNPOD_TEST_CENTRAL_API_URL" in script
    assert "RUNPOD_TEST_AGENT_SECRET_TOKEN" in script
    assert "RUNPOD_TEST_MINIO_ACCESS_KEY" in script
    assert "RUNPOD_TEST_MINIO_SECRET_KEY" in script

    for entrypoint in (ENTRYPOINT_SCRIPT, BOOTSTRAP_SCRIPT):
        text = entrypoint.read_text(encoding="utf-8")
        assert "runpod_embedded_test_agent.sh" in text
        assert "RUNPOD_EMBEDDED_TEST_AGENT_ENABLED" in text
        assert "EMBEDDED_TEST_AGENT_PID" in text


def test_runpod_runtime_requires_baked_agent_and_never_clones_allbot_at_startup():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    baked_entrypoint = BAKED_ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    assert 'git clone --depth 1 --branch "$REPO_BRANCH"' not in bootstrap
    assert "baked AllBot RunPod worker bundle is missing" in bootstrap
    assert "ALLBOT_RUNPOD_REPO_DIR:-/opt/allbot/runtime" in baked_entrypoint
    assert "${runtime_root}/runpod_worker" in baked_entrypoint
    assert "comfy_agent/workflows" in baked_entrypoint


def test_runpod_bootstrap_and_entrypoint_supervise_managed_processes():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    for script in (bootstrap, entrypoint):
        assert "shutdown_children" in script
        assert "wait -n" in script
        assert "stopping container for restart policy" in script


def test_runpod_entrypoints_start_the_baked_runpod_relay():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    for script in (bootstrap, entrypoint):
        assert "python3 -m runpod_relay.relay_main" in script


def test_runpod_bootstrap_installs_kjnodes_before_starting_comfyui():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    install_call_index = script.index("install_comfyui_custom_nodes\n")
    comfy_start_index = script.index('log "starting ComfyUI')

    assert "ComfyUI-KJNodes" in script
    assert "RUNPOD_COMFY_KJNODES_ENABLED" in script
    assert install_call_index < comfy_start_index


def test_runpod_runtime_bakes_agent_id_into_pop_requests():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    coordinator = Path("workers/comfy_agent/agent_pipeline_coordinator.py").read_text(
        encoding="utf-8"
    )

    assert 'params: dict[str, str] = {"agent_id": agent_id}' in coordinator
    assert "write_text(" not in bootstrap


def test_runpod_runtime_bakes_wan22_node_inputs():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    patchers = Path("workers/comfy_agent/workflow_task_patchers.py").read_text(
        encoding="utf-8"
    )

    assert "WAN22_VIDEO_V2_LAST_FRAME_FALLBACK_INDEX = 4095" in patchers
    assert 'input_name="resolution_preset"' in patchers
    assert 'input_name="swap_aspect_when_not_image"' in patchers
    assert 'input_name="aspect_preset_when_not_image"' in patchers
    assert 'input_name="custom_aspect_width"' in patchers
    assert 'input_name="custom_aspect_height"' in patchers
    assert "write_text(" not in bootstrap


def test_runpod_runtime_bakes_resumable_model_sync():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    sync_script = Path(
        "workers/runpod_runtime/scripts/runpod_sync_models_from_r2.py"
    ).read_text(encoding="utf-8")

    assert "_download_object_with_resume" in sync_script
    assert "RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS" in sync_script
    assert "RUNPOD_MODEL_DOWNLOAD_PROGRESS_BYTES" in sync_script
    assert "offset=current_size" in sync_script
    assert "write_text(" not in bootstrap


def test_runpod_bootstrap_checks_wan22_rife_cache_before_starting_comfyui():
    script = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    assert "ensure_wan22_rife_cache.py" in script
    assert script.index("ensure_wan22_rife_cache\n") < script.index(
        'log "starting ComfyUI'
    )
    assert "ensure_wan22_rife_cache.py" in entrypoint
    assert '\nensure_wan22_rife_cache\n\nif [ -n "${COMFYUI_DIR:-}" ]' in entrypoint


def test_runpod_entrypoints_expose_the_actual_comfy_artifact_directories():
    for path in (BOOTSTRAP_SCRIPT, ENTRYPOINT_SCRIPT):
        script = path.read_text(encoding="utf-8")
        assert "export COMFY_ARTIFACT_INPUT_DIR=" in script
        assert "export COMFY_ARTIFACT_OUTPUT_DIR=" in script
        assert "export COMFY_ARTIFACT_TEMP_DIR=" in script


def test_runpod_bootstrap_and_entrypoint_recognize_baked_comfyui_dir_marker():
    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    assert "/opt/allbot-comfyui-dir" in bootstrap
    assert "resolve_baked_comfyui_dir" in bootstrap
    assert 'log "starting ComfyUI from ${baked_comfyui_dir}"' in bootstrap
    assert "/opt/allbot-comfyui-dir" in entrypoint
    assert "resolve_baked_comfyui_dir" in entrypoint
    assert 'cd "$baked_comfyui_dir"' in entrypoint


def test_baked_entrypoint_links_external_model_target_into_baked_comfyui():
    entrypoint = BAKED_ENTRYPOINT_SCRIPT.read_text(encoding="utf-8")

    assert "prepare_baked_model_target" in entrypoint
    assert "RUNPOD_MODEL_TARGET_DIR" in entrypoint
    assert "/opt/allbot-comfyui-dir" in entrypoint
    assert '-name "*.safetensors"' in entrypoint
    assert "contains weights; refusing to replace it" in entrypoint
    assert 'ln -s "$model_target" "$baked_models"' in entrypoint
    assert entrypoint.index("prepare_baked_model_target") < entrypoint.index(
        'exec bash "${RUNPOD_BOOTSTRAP_SCRIPT:-/opt/allbot/runpod_bootstrap_from_git.sh}"'
    )


def _run_baked_entrypoint(
    tmp_path: Path, weight: str
) -> subprocess.CompletedProcess[str]:
    comfyui_dir = tmp_path / "ComfyUI"
    models_dir = comfyui_dir / "models"
    weight_path = models_dir / weight
    weight_path.parent.mkdir(parents=True)
    weight_path.write_bytes(b"fixture-weight")
    (comfyui_dir / "main.py").write_text("", encoding="utf-8")

    worker_root = tmp_path / "runtime" / "runpod_worker"
    (worker_root / "comfy_agent" / "workflows").mkdir(parents=True)
    (worker_root / "comfy_agent" / "agent_main.py").write_text("", encoding="utf-8")
    (worker_root / "requirements.txt").write_text("", encoding="utf-8")

    marker = tmp_path / "allbot-comfyui-dir"
    marker.write_text(str(comfyui_dir), encoding="utf-8")
    bootstrap = tmp_path / "bootstrap.sh"
    bootstrap.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    model_target = tmp_path / "external-models"

    return subprocess.run(
        ["bash", str(BAKED_ENTRYPOINT_SCRIPT)],
        cwd=Path.cwd(),
        env={
            **os.environ,
            "ALLBOT_RUNPOD_REPO_DIR": str(tmp_path / "runtime"),
            "RUNPOD_MODEL_TARGET_DIR": str(model_target),
            "RUNPOD_BAKED_COMFYUI_DIR_FILE": str(marker),
            "RUNPOD_BOOTSTRAP_SCRIPT": str(bootstrap),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_baked_entrypoint_preserves_standard_vae_preview_weights(tmp_path: Path):
    result = _run_baked_entrypoint(tmp_path, "vae_approx/taesd_decoder.pth")

    assert result.returncode == 0, result.stderr
    models = tmp_path / "ComfyUI" / "models"
    assert models.is_symlink()
    assert (tmp_path / "external-models/vae_approx/taesd_decoder.pth").read_bytes() == (
        b"fixture-weight"
    )


def test_baked_entrypoint_rejects_any_non_preview_weight(tmp_path: Path):
    result = _run_baked_entrypoint(tmp_path, "checkpoints/business.safetensors")

    assert result.returncode == 78
    assert "contains weights; refusing to replace it" in result.stderr
    assert not (tmp_path / "ComfyUI" / "models").is_symlink()


def test_runpod_profile_build_script_has_valid_bash_syntax():
    subprocess.run(
        ["bash", "-n", str(PROFILE_BUILD_SCRIPT)],
        check=True,
    )


def test_lan_all_profile_uses_pinned_union_image_contract():
    dockerfile = LAN_ALL_PROFILE_DOCKERFILE.read_text(encoding="utf-8")
    build_script = PROFILE_BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "COMFYUI_REF=8a33128f2f8c5585c57486c07de481241e70a39c" in dockerfile
    assert "LTXVIDEO_REF=15d09abb5a187a8dcaea2fc31fe51ee96e6c9d0d" in dockerfile
    assert "BASE_IMAGE=192.168.1.115:5000/allbot/comfyui-boot@sha256:" in dockerfile
    assert (
        "NODE_SOURCE_IMAGE=192.168.1.115:5000/allbot/"
        "comfy-runpod-wan22-aio-video@sha256:" in dockerfile
    )
    assert "ghcr.io/" not in dockerfile
    assert "yanwk/" not in dockerfile
    assert 'allbot.lan.profile="all"' in dockerfile
    assert "allbot.runpod.profile" not in dockerfile
    assert "--cpu --quick-test-for-ci --disable-auto-launch" in dockerfile
    assert "Business model files must stay out of the LAN all image" in dockerfile
    assert "COPY shared /opt/allbot/runtime/runpod_worker/shared" in dockerfile
    assert "character_description" in dockerfile
    assert "LTX 2.3 I2V 10Eros LoRA.json" in dockerfile
    assert "LTX 2.5 IC V2V Upscale.api.json" in dockerfile
    assert '"ltx25_video_upscale"' in dockerfile
    assert "runpod_sync_models_multi_manifest.patch" not in dockerfile
    assert "all)" in build_script
    assert "allbot/comfy-lan-all:local" in build_script
    assert "cp -a workers/runpod_profiles/ltx_unified" in build_script


def test_lan_all_profile_can_reuse_digest_pinned_lan_source_images():
    dockerfile = LAN_ALL_PROFILE_DOCKERFILE.read_text(encoding="utf-8")
    build_script = PROFILE_BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "ARG SCAIL_SOURCE_IMAGE=" in dockerfile
    assert "FROM ${SCAIL_SOURCE_IMAGE} AS scail_source" in dockerfile
    assert "scail_xformers/xformers" in dockerfile
    assert "0.0.33+e70569e.d20260704" in dockerfile
    assert "ARG REUSE_BASE_CUSTOM_NODES=false" in dockerfile
    assert 'if [ "${REUSE_BASE_CUSTOM_NODES}" = "true" ]; then' in dockerfile
    assert 'echo "Reusing pinned ComfyUI and LTX sources from base image"' in dockerfile
    assert 'test -f "${comfyui_dir}/main.py"' in dockerfile
    assert 'test -d "${comfyui_dir}/custom_nodes/ComfyUI-LTXVideo"' in dockerfile
    assert (
        'profile_label_args+=(--label "allbot.lan.base-image=${BASE_IMAGE}")'
        in build_script
    )
    assert (
        "profile_label_args+=(--label "
        '"allbot.lan.node-source-image=${NODE_SOURCE_IMAGE}")' in build_script
    )
    assert (
        "profile_label_args+=(--label "
        '"allbot.lan.scail-source-image=${SCAIL_SOURCE_IMAGE}")' in build_script
    )
    assert (
        'docker_build_args+=(--build-arg "SCAIL_SOURCE_IMAGE=${SCAIL_SOURCE_IMAGE}")'
        in build_script
    )
    assert (
        'profile_label_args+=(--label "allbot.lan.source-images=local-digest-pinned")'
        in build_script
    )


def test_embedded_test_agent_allows_lan_provider_identity():
    script = Path(
        "workers/runpod_runtime/scripts/runpod_embedded_test_agent.sh"
    ).read_text(encoding="utf-8")

    assert 'POOL_PROVIDER="${RUNPOD_TEST_POOL_PROVIDER:-runpod}"' in script


def test_lan_all_runtime_refresh_is_local_digest_based_and_dependency_closed():
    dockerfile = LAN_ALL_RUNTIME_REFRESH_DOCKERFILE.read_text(encoding="utf-8")
    catalog_text = MODULE_CATALOG.read_text(encoding="utf-8")
    catalog = json.loads(catalog_text)["modules"]

    assert (
        "RUNTIME_BASE_IMAGE=192.168.1.115:5000/allbot/"
        "allbot-gpu-lan-all@sha256:"
        "3b0310cd92333ef78139fc8c776cb0993dc6b0b7746336ee55c81a92a39f1f30"
        in dockerfile
    )
    assert (
        'allbot.lan.runtime-refresh-base="sha256:'
        '3b0310cd92333ef78139fc8c776cb0993dc6b0b7746336ee55c81a92a39f1f30"'
        in dockerfile
    )
    assert "ghcr.io/" not in dockerfile
    assert "docker.io/" not in dockerfile
    assert "COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker" in dockerfile
    assert (
        "COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh "
        "/opt/allbot/runpod_bootstrap_from_git.sh" in dockerfile
    )
    assert dockerfile.count("/opt/allbot/runpod_bootstrap_from_git.sh") == 2
    assert (
        "d81a4ee4dc26db0deb2d554bd59b277dfae0bf9071454a5d955f8fff4925ed13" in dockerfile
    )
    assert "runpod_sync_models_multi_manifest.patch" not in dockerfile
    assert 'allbot.lan.profile="all"' in dockerfile
    assert '"ltx25_video_upscale"' in dockerfile
    assert "org.opencontainers.image.revision=$ALLBOT_GIT_SHA" in dockerfile
    runtime_refresh = catalog["lan_all_runtime_refresh"]
    assert runtime_refresh["dockerfile"] == (
        "workers/runpod_profiles/all/Dockerfile.runtime-refresh"
    )
    assert runtime_refresh["external_base_arg"] == "RUNTIME_BASE_IMAGE"


def test_gpu_runtime_refresh_modules_overlay_only_the_canonical_worker_package():
    catalog = json.loads(MODULE_CATALOG.read_text(encoding="utf-8"))["modules"]

    for module_name, (image, profile_dir, base_digest, single_manifest) in (
        RUNTIME_REFRESH_MODULES.items()
    ):
        dockerfile_path = (
            Path("workers") / "runpod_profiles" / profile_dir / "Dockerfile.runtime-refresh"
        )
        dockerfile = dockerfile_path.read_text(encoding="utf-8")
        module = catalog[module_name]

        assert module["image"] == image
        assert module["dockerfile"] == str(dockerfile_path)
        assert module.get("runpod_single_manifest", False) is single_manifest
        assert f"@sha256:{base_digest}" in dockerfile
        assert "rm -rf /opt/allbot/runtime/runpod_worker" in dockerfile
        assert "COPY workers/comfy_agent " in dockerfile
        assert "COPY src " in dockerfile
        assert "COPY shared " in dockerfile
        assert "load_runtime_manifest();" in dockerfile
        assert "apt-get" not in dockerfile
        assert "zypper" not in dockerfile
        assert "git clone" not in dockerfile
        assert "pip install" not in dockerfile


def test_runpod_profiles_do_not_reinstall_an_existing_ffmpeg_package():
    """Mutable upstream bases may already carry a conflicting ffmpeg package."""

    for profile in ("i2i_pro", "face_swap", "scail2"):
        dockerfile = (
            Path("workers") / "runpod_profiles" / profile / "Dockerfile"
        ).read_text(encoding="utf-8")

        assert "if ! command -v ffmpeg >/dev/null 2>&1; then" in dockerfile
        assert 'packages="${packages} ffmpeg"' in dockerfile


def test_runpod_profiles_pin_the_shared_upstream_base_by_digest():
    profiles = (
        "i2i_pro",
        "face_swap",
        "scail2",
        "wan22_aio_video",
        "img2img_lora",
        "ltx_video",
        "ltx_t2v",
    )
    expected = (
        "ARG BASE_IMAGE=yanwk/comfyui-boot:cu128-slim@sha256:"
        "4172d960fe57c630d33f6bd8891aa7ecf55e7768559565c6b74e8d57e44512a9"
    )

    for profile in profiles:
        dockerfile = (
            Path("workers") / "runpod_profiles" / profile / "Dockerfile"
        ).read_text(encoding="utf-8")
        assert expected in dockerfile


def test_ltx_t2v_runtime_refresh_is_digest_based_and_revalidates_fixed_graphs():
    dockerfile = LTX_T2V_RUNTIME_REFRESH_DOCKERFILE.read_text(encoding="utf-8")

    assert (
        "BASE_IMAGE=ghcr.io/giraffu/allbot-gpu-ltx-t2v@sha256:"
        "b956eb3ff3ee1518c92314a40d44b10d0734d91de5ed09cea05214df30511897" in dockerfile
    )
    assert "LTX 2.3 Sulphur Ingredients T2V.json" in dockerfile
    assert 't2v["26:39"]["inputs"]["width"] == 640' in dockerfile
    assert 'ic["26:39"]["inputs"]["width"] == ["5100",0]' in dockerfile
    assert 't2v["26:91"]["inputs"]["latent"] == ["26:95",0]' in dockerfile
    assert 'ic["198"]["inputs"]["latent"] == ["26:39",0]' in dockerfile
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


def test_pornmaster_profile_uses_cloud_resolvable_immutable_base():
    dockerfile = PORNMASTER_PROFILE_DOCKERFILE.read_text(encoding="utf-8")

    assert (
        "ARG BASE_IMAGE=ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro@sha256:"
        in dockerfile
    )
    assert "ARG BASE_IMAGE=192.168.1.115:5000" not in dockerfile


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
    assert 'sys.exit("REUSE_BASE_CUSTOM_NODES=true' in dockerfile
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
    assert (
        "RIFE49_URL=https://huggingface.co/lividtm/RIFE/resolve/main/rife49.pth"
        in dockerfile
    )
    assert (
        "RIFE49_SHA256=e55fd00f3cc184e3c65961f4bb827a9da022e78eed36b055242c0ac30000d533"
        in dockerfile
    )
    assert "ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth" in dockerfile
    assert "ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth" in dockerfile
    assert "ComfyUI-LTXVideo" in dockerfile
    assert "229437c6b65796d6a7a63ae34be2bd5ba31fa543" in dockerfile
    assert "LTXVSpatioTemporalTiledVAEDecode" in dockerfile
    assert "NODE_CLASS_MAPPINGS = dict(RUNTIME_NODE_CLASS_MAPPINGS)" in dockerfile
    assert (
        "COPY workers/runpod_runtime/scripts/runpod_bootstrap_from_git.sh "
        "/opt/allbot/runpod_bootstrap_from_git.sh"
    ) in dockerfile
    assert "COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker" in dockerfile
    assert (
        "python3 -m pip install --no-cache-dir -r "
        "/opt/allbot/runtime/runpod_worker/requirements.txt"
    ) in dockerfile
    assert (
        'CMD ["bash", "/opt/allbot/runpod_baked_runtime_entrypoint.sh"]' in dockerfile
    )
    assert "# Keep the FL_RIFE provider in a final small layer" in dockerfile
    assert dockerfile.index(
        'echo "${comfyui_dir}" > /opt/allbot-comfyui-dir'
    ) < dockerfile.index("# Keep the FL_RIFE provider in a final small layer")
    assert "ComfyUI-GGUF" in dockerfile
    assert "ComfyUI-DaSiWa-Nodes" in dockerfile
    assert "comfyui-WhiteRabbit" in dockerfile
    assert "4815da41473c99400da6ca4127f0e324dbfd865a" in dockerfile
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
    assert not Path(".github/workflows/runpod_wan22_profile_image.yml").exists()
    assert Path("workers/runpod_profiles/wan22_aio_video/Dockerfile").exists()


def test_face_swap_github_workflow_publishes_dedicated_revision_pinned_image():
    assert not Path(".github/workflows/runpod_face_swap_profile_image.yml").exists()
    assert Path("workers/runpod_profiles/face_swap/Dockerfile").exists()


def test_ltx_t2v_github_workflow_builds_exact_main_revision_without_models():
    assert not Path(".github/workflows/runpod_ltx_t2v_profile_image.yml").exists()
    assert Path("workers/runpod_profiles/ltx_t2v/Dockerfile").exists()


def test_profile_build_script_accepts_wan22_profile_without_running_real_docker(
    tmp_path,
):
    calls = tmp_path / "docker-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$DOCKER_CALLS"\n',
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
    assert "workers/runpod_profiles/wan22_aio_video/Dockerfile" in rendered
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
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$DOCKER_CALLS"\n',
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


def test_pornmaster_profile_stages_canonical_character_runtime(tmp_path):
    calls = tmp_path / "docker-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'context="${!#}"\n'
        'test -f "$context/workers/comfy_agent/workflow_task_patchers.py"\n'
        'test ! -e "$context/workers/runpod_profiles/pornmaster_flux2_edit/'
        'install_character_runtime_overlay.py"\n'
        'printf \'%s\\n\' "$*" >> "$DOCKER_CALLS"\n',
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
            "pornmaster_flux2_edit",
            "--image-ref",
            "allbot/comfy-runpod-pornmaster-flux2-edit:test",
            "--no-smoke",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert calls.exists()


def test_character_runtime_contract_is_part_of_canonical_worker():
    patchers = Path("workers/comfy_agent/workflow_task_patchers.py").read_text(
        encoding="utf-8"
    )
    dockerfile = PORNMASTER_PROFILE_DOCKERFILE.read_text(encoding="utf-8")

    assert 'workflow[selected_prefix + "100"]["inputs"]["unet_name"]' in patchers
    assert "install_character_runtime_overlay" not in dockerfile
    materializer = Path(
        "workers/comfy_agent/agent_result_materialization.py"
    ).read_text(encoding="utf-8")
    assert "PORNMASTER_FLUX2_BF16_UNET_NAME" in patchers
    assert "if selected_index and index != selected_index" in patchers
    assert "async def _materialize_character_reference_view" in materializer
    assert '(execution.params or {}).get("character_view_index")' in materializer


def test_profile_build_script_rejects_unknown_profile_before_docker(tmp_path):
    calls = tmp_path / "docker-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$DOCKER_CALLS"\n',
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
