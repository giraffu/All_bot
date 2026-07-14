import importlib.util
import json
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


def test_build_matrix_contains_base_before_descendants_and_profile_metadata():
    module = _load_module()
    catalog = module.load_catalog(CATALOG_PATH)
    plan = module.plan_builds(catalog, ["requirements.txt"], has_previous=True)

    matrix = module.build_matrix(catalog, plan)

    assert matrix[0]["name"] == "python-runtime-base"
    assert next(row for row in matrix if row["name"] == "central-api")["base"] == (
        "python-runtime-base"
    )
    assert catalog["i2i_pro"]["profile"]["task_types"] == ["i2i_pro"]


def test_catalog_is_json_and_every_artifact_has_one_track():
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert all(
        value["track"] in {"control-plane", "test-execution", "gpu-execution"}
        for value in raw["artifacts"].values()
    )
