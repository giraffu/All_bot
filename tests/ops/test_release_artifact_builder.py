import importlib.util
import json
from copy import deepcopy
from pathlib import Path


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
    previous_catalog["central-api"]["inputs"] = ["old-central-api/**"]

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
    ]


def test_gpu_catalog_matches_canonical_runtime_contracts():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)

    assert catalog["pornmaster_flux2_edit_bf16"]["profile"][
        "model_manifest_key"
    ] == "pornmaster_flux2_edit_bf16/2026-07-12/manifest.json"
    assert catalog["pornmaster_flux2_edit"]["profile"]["task_types"] == [
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    ]
    assert catalog["scail2"]["profile"]["task_types"] == [
        "scail2_action_transfer",
        "scail2_video_replacement",
    ]
    assert catalog["ltx_video"]["profile"]["task_types"] == [
        "ltx_video",
        "ltx_video_flf2v",
        "ltx_video_v2v_audio",
    ]
    assert catalog["img2img"]["profile"]["model_manifest_key"] == (
        "img2img_lora/2026-06-10/manifest.json"
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
