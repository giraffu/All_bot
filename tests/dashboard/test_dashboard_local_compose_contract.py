from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_local_dashboard_requires_explicit_redis_endpoints_and_probes_public_health():
    compose = (REPOSITORY_ROOT / "dashboard/docker-compose.yml").read_text()
    gateway = (
        REPOSITORY_ROOT / "dashboard/docker-compose-local-gateway.yml"
    ).read_text()

    assert "REDIS_URL=${DASHBOARD_REDIS_URL:?DASHBOARD_REDIS_URL is required}" in compose
    assert (
        "WORKER_REDIS_URL=${DASHBOARD_WORKER_REDIS_URL:?DASHBOARD_WORKER_REDIS_URL is required}"
        in compose
    )
    assert "redis://:redispassword@127.0.0.1:6379" not in compose
    assert "http://127.0.0.1:8086/api/health" in gateway
    assert "http://127.0.0.1:8086/ &&" not in gateway
