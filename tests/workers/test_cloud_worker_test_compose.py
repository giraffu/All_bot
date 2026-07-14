from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "workers" / "docker-compose-cloud-worker-test.yml"
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
