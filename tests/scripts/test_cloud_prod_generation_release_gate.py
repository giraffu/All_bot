import asyncio
import json

from scripts import cloud_prod_generation_release_gate as gate


def test_load_env_file_strips_quotes_and_export(tmp_path):
    env_file = tmp_path / ".env.cloud.prod"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                'export CLOUD_PROD_REDIS_URL="redis://app"',
                "CLOUD_PROD_WORKER_REDIS_URL='redis://worker'",
                "EMPTY=",
                "BAD_LINE",
            ]
        ),
        encoding="utf-8",
    )

    values = gate.load_env_file(env_file)

    assert values["CLOUD_PROD_REDIS_URL"] == "redis://app"
    assert values["CLOUD_PROD_WORKER_REDIS_URL"] == "redis://worker"
    assert values["EMPTY"] == ""
    assert "BAD_LINE" not in values


def test_configure_process_env_maps_prod_redis_and_bucket(monkeypatch):
    for key in (
        "REDIS_URL",
        "WORKER_REDIS_URL",
        "DATABASE_URL",
        "BOT_TYPE",
        "MINIO_BUCKET",
    ):
        monkeypatch.delenv(key, raising=False)

    gate.configure_process_env(
        {
            "CLOUD_PROD_REDIS_URL": "redis://app",
            "CLOUD_PROD_WORKER_REDIS_URL": "redis://worker",
            "CLOUD_PROD_DATABASE_URL": "postgresql+asyncpg://db",
            "MINIO_BUCKET": "user-data-prod",
        }
    )

    assert gate.os.environ["REDIS_URL"] == "redis://app"
    assert gate.os.environ["WORKER_REDIS_URL"] == "redis://worker"
    assert gate.os.environ["DATABASE_URL"] == "postgresql+asyncpg://db"
    assert gate.os.environ["BOT_TYPE"] == "PROD"
    assert gate.os.environ["MINIO_BUCKET"] == "user-data-prod"


def test_generation_maintenance_uses_dedicated_marker(capsys):
    gate.set_maintenance("prod-host", enabled=True, execute=False)

    output = capsys.readouterr().out

    assert "/app/GENERATION_MAINTENANCE" in output
    assert "/app/MAINTENANCE" not in output


class FakeRedis:
    def __init__(self, *, pending=None, running=None, active_tasks=None):
        self.pending = list(pending or [])
        self.running = set(running or [])
        self.active_tasks = dict(active_tasks or {})
        self.hash_writes = []
        self.published = []

    async def zrange(self, key, start, end):
        assert key == gate.PENDING_KEY
        assert start == 0
        assert end == -1
        return list(self.pending)

    async def smembers(self, key):
        assert key == gate.RUNNING_KEY
        return set(self.running)

    async def hgetall(self, key):
        assert key == "prod_bot_active_tasks"
        return dict(self.active_tasks)

    async def zrem(self, key, item):
        assert key == gate.PENDING_KEY
        if item not in self.pending:
            return 0
        self.pending.remove(item)
        return 1

    async def hset(self, key, mapping):
        self.hash_writes.append((key, mapping))

    async def srem(self, key, item):
        assert key == gate.RUNNING_KEY
        self.running.discard(item)

    async def publish(self, channel, payload):
        self.published.append((channel, payload))


def test_build_queue_snapshot_maps_pending_backend_ids():
    worker_redis = FakeRedis(pending=["backend-1", "orphan"], running=["running-1"])
    app_redis = FakeRedis(
        active_tasks={
            "registry-1": json.dumps(
                {"backend_task_id": "backend-1", "user_id": 1001}
            ),
            "registry-2": json.dumps(
                {"backend_task_id": "backend-2", "user_id": 1002}
            ),
        }
    )

    snapshot = asyncio.run(
        gate.build_queue_snapshot(worker_redis, app_redis, "prod_bot_")
    )

    assert snapshot["pending_count"] == 2
    assert snapshot["running_count"] == 1
    assert snapshot["active_task_count"] == 2
    assert snapshot["mapped_pending_count"] == 1
    assert snapshot["orphan_pending_count"] == 1
    assert snapshot["registry_by_backend"]["backend-1"] == "registry-1"


def test_cancel_backend_pending_marks_cancelled_and_publishes_event():
    worker_redis = FakeRedis(pending=["backend-1"], running=["backend-1"])

    cancelled = asyncio.run(gate.cancel_backend_pending(worker_redis, "backend-1"))

    assert cancelled is True
    assert worker_redis.pending == []
    assert worker_redis.running == set()
    assert worker_redis.hash_writes == [
        (
            "comfy:task:backend-1",
            {
                "status": "cancelled",
                "cancel_requested": 0,
                "cancel_requested_at": "",
                "cancel_locked": 0,
                "execution_phase": "",
                "cancel_locked_at": "",
            },
        )
    ]
    assert worker_redis.published == [
        ("comfy:task_events:backend-1", json.dumps({"status": "cancelled"}))
    ]
