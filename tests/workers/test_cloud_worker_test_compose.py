from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "workers" / "docker-compose-cloud-worker-test.yml"
IMMUTABLE_COMPOSE_PATH = ROOT / "deploy" / "docker-compose-worker-base.yml"
SHARED_SPOOL_MOUNT = (
    "${CLOUD_TEST_WORKER_SPOOL_HOST_DIR:-/var/lib/allbot/test-worker/spool}"
    ":/app/spool"
)


def test_cloud_test_workers_and_release_relay_share_the_same_spool_mount():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    relay_volumes = compose["services"]["cloud-worker-relay-test"]["volumes"]
    assert SHARED_SPOOL_MOUNT in relay_volumes

    for service_name, service in compose["services"].items():
        if not service_name.startswith("cloud-comfy-agent-test-"):
            continue
        assert SHARED_SPOOL_MOUNT in service["volumes"], service_name


def test_immutable_worker_release_keeps_agents_and_relay_on_one_spool_root():
    compose = yaml.safe_load(IMMUTABLE_COMPOSE_PATH.read_text(encoding="utf-8"))
    expected_mount = (
        "${ALLBOT_WORKER_STATE_ROOT:?ALLBOT_WORKER_STATE_ROOT is required}"
        "/spool:/app/spool"
    )

    for service_name, service in compose["services"].items():
        assert expected_mount in service["volumes"], service_name


def test_shared_ltx_worker_targets_the_unified_runtime():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    service = compose["services"]["cloud-comfy-agent-test-3"]
    environment = service["environment"]

    assert "profiles" not in service
    assert service["restart"] == "always"
    assert environment["POOL_RUNTIME_PROFILE"] == (
        "${CLOUD_TEST_WORKER_03_RUNTIME_PROFILE:-ltx_unified}"
    )
    assert environment["SUPPORTED_TASK_TYPES"] == (
        "${CLOUD_TEST_WORKER_03_TASK_TYPES:-"
        "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio,ltx_t2v,ltx_t2v_ic}"
    )
    assert environment["COMFY_API_URL"] == (
        "${CLOUD_TEST_WORKER_03_COMFY_API_URL:-http://192.168.1.177:8191}"
    )


def test_shared_gpu226_worker_exposes_the_all_profile_to_cloud_test():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    service = compose["services"]["cloud-comfy-agent-test-6"]
    environment = service["environment"]
    expected_types = (
        "img2img,img2img_lora,image_to_video,wan22_video_v2,"
        "pornmaster_flux2_edit_bf16,pornmaster_flux2_multi_edit_bf16,"
        "scail2_action_transfer,scail2_action_transfer_long,"
        "scail2_video_replacement,scail2_face_swap_v2,"
        "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio,"
        "i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap,"
        "ltx_t2v,ltx_t2v_ic"
    )

    assert "profiles" not in service
    assert service["restart"] == "always"
    assert environment["POOL_NODE_ID"] == (
        "${CLOUD_TEST_WORKER_06_NODE_ID:-gpu-226}"
    )
    assert environment["POOL_RUNTIME_PROFILE"] == (
        "${CLOUD_TEST_WORKER_06_RUNTIME_PROFILE:-all}"
    )
    assert environment["SUPPORTED_TASK_TYPES"] == (
        "${CLOUD_TEST_WORKER_06_TASK_TYPES:-" + expected_types + "}"
    )
    assert environment["COMFY_API_URL"] == (
        "${CLOUD_TEST_WORKER_06_COMFY_API_URL:-http://192.168.1.226:8190}"
    )
