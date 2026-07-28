import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release_artifacts_v2.py"
CATALOG_PATH = ROOT / "deploy" / "release-artifacts-v2.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_artifacts_v2", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_dependency_change_rebuilds_bases_and_every_descendant():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(catalog, ["requirements.txt"], has_previous=True)

    assert "python-runtime-base" in plan.build
    assert {
        "central-api",
        "web-api",
        "payment-api",
        "main-bot",
        "python-worker-base",
        "worker-agent",
        "worker-relay",
    } <= plan.build
    assert "dashboard-frontend" not in plan.build


def test_leaf_change_rebuilds_only_modules_whose_input_closure_matches():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(
        catalog,
        ["dashboard/backend/services/runpod_autoscaler_service.py"],
        has_previous=True,
    )

    assert plan.build == {"dashboard-backend", "qqcc-config-backend"}
    assert "central-api" in plan.reuse


@pytest.mark.parametrize(
    "changed_path",
    [
        "deploy/docker/Dockerfile.media-runtime-base",
        "deploy/docker/media-intelligence-requirements.txt",
        "deploy/docker/YUNET_LICENSE.txt",
    ],
)
def test_media_runtime_change_rebuilds_only_qqcc_media_consumers(changed_path):
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(
        catalog,
        [changed_path],
        has_previous=True,
    )

    assert plan.build == {
        "python-media-runtime-base",
        "qqcc-bot",
        "private-bot-worker",
        "dashboard-backend",
        "qqcc-config-backend",
    }
    assert {"central-api", "web-api", "payment-api", "main-bot"} <= plan.reuse


def test_gpu_control_operator_change_rebuilds_dashboard_but_not_gpu_images():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(
        catalog,
        ["ops/gpu_pool_controller/lan_aio_prod.py"],
        has_previous=True,
    )

    assert plan.build == {"dashboard-backend"}
    assert {
        name
        for name, artifact in catalog.items()
        if artifact["track"] == "gpu-execution"
    } <= plan.reuse


def test_gpu_host_operator_change_reuses_every_release_artifact():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(
        catalog,
        ["scripts/lan_aio_fleet_prod_ops.py"],
        has_previous=True,
    )

    assert plan.build == set()
    assert {
        name
        for name, artifact in catalog.items()
        if artifact["kind"] != "external-image"
    } == plan.reuse
    assert {"imgproxy", "postgres", "redis"} == plan.resolve


def test_gpu_rollout_runtime_dependencies_rebuild_dashboard():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    for changed_path in (
        "scripts/gpu_release_rollout.py",
        "scripts/release_manifest_v2.py",
        "scripts/release_strategy.py",
    ):
        plan = module.plan_builds(catalog, [changed_path], has_previous=True)
        assert plan.build == {"dashboard-backend"}, changed_path


def test_gpu_worker_change_rebuilds_gpu_images_but_not_dashboard():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(
        catalog,
        ["workers/runpod_runtime/comfy_agent/workflow_task_patchers.py"],
        has_previous=True,
    )

    assert "dashboard-backend" not in plan.build
    assert {
        name
        for name, artifact in catalog.items()
        if artifact["track"] == "gpu-execution"
    } <= plan.build


def test_character_runtime_overlay_rebuilds_only_pornmaster_gpu_profile():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(
        catalog,
        ["workers/comfy_agent/workflow_task_patchers.py"],
        has_previous=True,
    )

    assert "worker-agent" in plan.build
    assert {
        name for name in plan.build if catalog[name]["track"] == "gpu-execution"
    } == {"pornmaster_flux2_edit_bf16"}

    profile = catalog["pornmaster_flux2_edit_bf16"]
    assert "workers/comfy_agent/workflow_task_patchers.py" in profile["inputs"]
    assert "workers/comfy_agent/agent_result_materialization.py" in profile["inputs"]
    dockerfile = (ROOT / profile["dockerfile"]).read_text(encoding="utf-8")
    runtime_copy = dockerfile.index(
        "COPY workers/runpod_runtime /opt/allbot/runtime/runpod_worker"
    )
    patcher_overlay = dockerfile.index(
        "COPY workers/comfy_agent/workflow_task_patchers.py "
        "/opt/allbot/runtime/runpod_worker/comfy_agent/workflow_task_patchers.py"
    )
    materializer_overlay = dockerfile.index(
        "COPY workers/comfy_agent/agent_result_materialization.py "
        "/opt/allbot/runtime/runpod_worker/comfy_agent/agent_result_materialization.py"
    )
    assert runtime_copy < patcher_overlay < materializer_overlay


def test_first_v2_release_builds_every_owned_artifact_but_resolves_vendors():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(catalog, [], has_previous=False)

    assert "central-api" in plan.build
    assert "worker-agent" in plan.build
    assert "i2i_pro" in plan.build
    assert {"imgproxy", "postgres", "redis"} == plan.resolve


def test_catalog_contract_change_rebuilds_every_owned_artifact():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    plan = module.plan_builds(
        catalog,
        ["deploy/release-artifacts-v2.json"],
        has_previous=True,
    )

    owned = {
        name
        for name, artifact in catalog.items()
        if artifact.get("kind") != "external-image"
    }
    assert plan.build == owned
    assert plan.reuse == set()


def test_control_plane_catalog_change_does_not_schedule_gpu_track():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    previous_catalog = deepcopy(catalog)
    previous_catalog["central-api"]["image"] = "old-central-api"

    plan = module.plan_builds(
        catalog,
        ["deploy/release-artifacts-v2.json"],
        has_previous=True,
        previous_catalog=previous_catalog,
    )

    assert "central-api" in plan.build
    assert {
        name
        for name, artifact in catalog.items()
        if artifact["track"] == "gpu-execution"
    } <= plan.reuse


def test_catalog_input_boundary_change_is_planner_only():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    previous_catalog = deepcopy(catalog)
    previous_catalog["i2i_pro"]["inputs"] = [
        "workers/runpod_runtime/**",
        "workers/runpod_profiles/**",
    ]

    plan = module.plan_builds(
        catalog,
        ["deploy/release-artifacts-v2.json"],
        has_previous=True,
        previous_catalog=previous_catalog,
    )

    assert "i2i_pro" in plan.reuse
    assert "i2i_pro" not in plan.build


def test_new_all_profile_does_not_rebuild_existing_gpu_profiles():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    previous_catalog = deepcopy(catalog)
    previous_catalog.pop("lan_all")

    plan = module.plan_builds(
        catalog,
        [
            "deploy/release-artifacts-v2.json",
            "workers/runpod_profiles/all/Dockerfile",
            "workers/runpod_profiles/all/runpod_sync_models_multi_manifest.patch",
        ],
        has_previous=True,
        previous_catalog=previous_catalog,
    )

    assert plan.build == {"lan_all"}
    assert {
        name
        for name, artifact in catalog.items()
        if artifact["track"] == "gpu-execution" and name != "lan_all"
    } <= plan.reuse


def test_gpu_catalog_change_does_not_schedule_control_plane_track():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    previous_catalog = deepcopy(catalog)
    previous_catalog["i2i_pro"]["profile"]["task_types"] = ["old-i2i"]

    plan = module.plan_builds(
        catalog,
        ["deploy/release-artifacts-v2.json"],
        has_previous=True,
        previous_catalog=previous_catalog,
    )

    assert plan.build == {"i2i_pro"}
    assert {
        name
        for name, artifact in catalog.items()
        if artifact["track"] == "control-plane"
        and artifact.get("kind") != "external-image"
    } <= plan.reuse


def test_build_matrix_contains_base_before_descendants_and_profile_metadata():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    plan = module.plan_builds(catalog, ["requirements.txt"], has_previous=True)

    matrix = module.build_matrix(catalog, plan)

    assert matrix[0]["name"] == "python-runtime-base"
    assert next(row for row in matrix if row["name"] == "central-api")["base"] == (
        "python-runtime-base"
    )
    assert catalog["i2i_pro"]["profile"]["task_types"] == [
        "i2i_pro",
        "t2i-pornmaster-turbo",
        "face_swap_v2",
        "face_swap",
    ]


def test_gpu_catalog_matches_canonical_runtime_contracts():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    assert (
        catalog["pornmaster_flux2_edit_bf16"]["profile"]["model_manifest_key"]
        == "pornmaster_flux2_edit_bf16/2026-07-12/manifest.json"
    )
    assert "pornmaster_flux2_edit" not in catalog
    assert catalog["pornmaster_flux2_edit_bf16"]["profile"]["task_types"] == [
        "character_reference_build",
        "pornmaster_flux2_edit_bf16",
        "pornmaster_flux2_multi_edit_bf16",
    ]
    assert catalog["scail2"]["profile"]["task_types"] == [
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    ]
    assert catalog["ltx_video"]["profile"]["task_types"] == [
        "ltx_video",
        "ltx_video_flf2v",
        "ltx_video_v2v_audio",
    ]
    assert catalog["ltx_t2v"]["track"] == "gpu-execution"
    assert catalog["ltx_t2v"]["dockerfile"].endswith(
        "runpod_profiles/ltx_t2v/Dockerfile"
    )
    assert catalog["ltx_t2v"]["profile"] == {
        "task_types": ["ltx_t2v", "ltx_t2v_ic"],
        "model_manifest_key": "ltx_t2v/2026-07-22/manifest.json",
        "target_gpu": ["NVIDIA GeForce RTX 5090"],
        "startup_args": ["--reserve-vram", "5"],
    }
    assert catalog["img2img"]["profile"]["model_manifest_key"] == (
        "img2img_lora/2026-06-10/manifest.json"
    )
    assert catalog["face_swap"]["image"] == "allbot-gpu-face-swap"
    assert catalog["face_swap"]["profile"]["task_types"] == [
        "face_swap",
        "face_swap_v2",
    ]
    assert catalog["face_swap"]["profile"]["model_manifest_key"] == (
        "face_swap_v2/2026-07-25/manifest.json"
    )
    assert catalog["image_to_video"]["profile"]["model_manifest_key"] == (
        "image_to_video/2026-07-18-lora5/manifest.json"
    )
    assert catalog["wan22_video_v2"]["profile"]["model_manifest_key"] == (
        "wan22_video_v2/2026-07-18-lora5/manifest.json"
    )


def test_catalog_is_json_and_every_artifact_has_one_track():
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert all(
        value["track"] in {"control-plane", "test-execution", "gpu-execution"}
        for value in raw["artifacts"].values()
    )


def test_selected_control_plane_artifact_reuses_its_existing_base():
    module = _load_module()
    catalog = {
        "python-base": {"track": "control-plane", "kind": "image"},
        "qqcc-bot": {
            "track": "control-plane",
            "kind": "image",
            "base": "python-base",
        },
        "web-api": {
            "track": "control-plane",
            "kind": "image",
            "base": "python-base",
        },
        "face-swap": {"track": "gpu-execution", "kind": "image"},
        "postgres": {"track": "control-plane", "kind": "external-image"},
    }

    plan = module.plan_selected_builds(catalog, {"qqcc-bot"}, has_previous=True)

    assert plan.build == {"qqcc-bot"}
    assert plan.reuse == {"python-base", "web-api", "face-swap"}
    assert plan.resolve == {"postgres"}


def test_selected_release_scope_rejects_gpu_artifacts():
    module = _load_module()
    catalog = {
        "qqcc-bot": {"track": "control-plane", "kind": "image"},
        "face-swap": {"track": "gpu-execution", "kind": "image"},
    }

    with pytest.raises(module.ArtifactPlanError, match="control-plane"):
        module.plan_selected_builds(catalog, {"face-swap"}, has_previous=True)
