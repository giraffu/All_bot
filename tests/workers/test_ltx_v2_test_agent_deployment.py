from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "deploy" / "docker-compose-ltx-v2-test-agent.yml"


def test_ltx_v2_test_agent_is_exact_image_and_source_mount_free():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    service = compose["services"]["ltx-v2-test-agent"]

    assert service["image"] == (
        "${ALLBOT_LTX_V2_TEST_AGENT_IMAGE:?exact digest-pinned image is required}"
    )
    assert "build" not in service
    assert "depends_on" not in service
    assert service["restart"] == "no"
    assert service["network_mode"] == "host"
    assert all("/src" not in volume for volume in service["volumes"])
    assert all("/workflows" not in volume for volume in service["volumes"])


def test_ltx_v2_test_agent_has_a_narrow_canary_contract():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    service = compose["services"]["ltx-v2-test-agent"]
    environment = service["environment"]

    assert service["container_name"] == "cloud-comfy-agent-test-ltx-v2-01"
    assert environment["AGENT_ID"] == "cloud_worker_test_ltx_v2_01"
    assert environment["SUPPORTED_TASK_TYPES"] == (
        "ltx_video_v2,ltx_video_v2_flf2v,ltx_t2v,ltx_t2v_ic"
    )
    assert environment["POOL_MANAGED"] == "false"
    assert environment["POOL_NODE_ID"] == "gpu-177"
    assert environment["POOL_GPU_INDEX"] == "1"
    assert environment["POOL_RUNTIME_PROFILE"] == "ltx_unified"
    assert environment["PREFETCH_ENABLED"] == "false"
    assert environment["PIPELINE_ENABLED"] == "false"
    assert environment["COMFY_API_URL"] == "http://192.168.1.177:8191"
