import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.responses import JSONResponse


ROOT = Path(__file__).resolve().parents[2]
WORKERS_DIR = ROOT / "workers"
if str(WORKERS_DIR) not in sys.path:
    sys.path.insert(0, str(WORKERS_DIR))

if "minio" not in sys.modules and importlib.util.find_spec("minio") is None:
    minio_module = ModuleType("minio")
    minio_module.Minio = object
    sys.modules["minio"] = minio_module

from local_relay import relay_main as relay  # noqa: E402


class FakeRequest:
    def __init__(self, payload, *, query_params=None):
        self._payload = payload
        self.query_params = query_params or {}

    async def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_relay_preserves_preferred_types_query_params(monkeypatch):
    calls = []

    async def fake_forward(method, path, *, params=None, json_body=None, retry=True):
        calls.append((method, path, dict(params), retry))
        return JSONResponse({"task": None})

    monkeypatch.setattr(relay, "_forward_request", fake_forward)
    query = {
        "types": "img2img,scail2_face_swap_v2",
        "preferred_types": "scail2_face_swap_v2",
    }

    await relay.pop_task(FakeRequest(None, query_params=query))
    await relay.peek_task(FakeRequest(None, query_params=query))

    assert calls == [
        ("GET", "/api/agent/task/pop", query, True),
        ("GET", "/api/agent/task/peek", query, True),
    ]


@pytest.mark.asyncio
async def test_ready_checks_upstream_and_clients():
    class FakeClient:
        async def get(self, path, timeout=None):
            assert path == "/health"
            assert timeout == relay.RELAY_READY_TIMEOUT_SECONDS
            return SimpleNamespace(status_code=200)

    relay.state.client = FakeClient()
    relay.state.minio_client = object()
    relay.state.pending_statuses = {"task-1": {"status": "running"}}

    response = await relay.ready()

    assert response["status"] == "ok"
    assert response["upstream_ok"] is True
    assert response["client_ready"] is True
    assert response["upload_client_ready"] is True
    assert response["pending_statuses"] == 1


@pytest.mark.asyncio
async def test_ready_returns_503_when_upstream_unhealthy():
    class FakeClient:
        async def get(self, path, timeout=None):
            return SimpleNamespace(status_code=503)

    relay.state.client = FakeClient()
    relay.state.minio_client = object()
    relay.state.pending_statuses = {}

    response = await relay.ready()

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_ready_returns_503_when_upstream_raises():
    class FakeClient:
        async def get(self, path, timeout=None):
            raise RuntimeError("network unreachable")

    relay.state.client = FakeClient()
    relay.state.minio_client = object()
    relay.state.pending_statuses = {}

    response = await relay.ready()

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_relay_coalesces_non_terminal_status_updates():
    relay.state.pending_statuses = {}
    relay.state.status_lock = asyncio.Lock()

    first = {
        "task_id": "task-1",
        "agent_id": "agent-1",
        "status": "running",
        "progress": 0.1,
    }
    latest = {**first, "progress": 0.8}

    assert await relay.update_status(FakeRequest(first)) == {
        "status": "ok",
        "relayed": "queued",
    }
    assert await relay.update_status(FakeRequest(latest)) == {
        "status": "ok",
        "relayed": "queued",
    }

    assert relay.state.pending_statuses == {"task-1": latest}


@pytest.mark.asyncio
async def test_relay_forwards_terminal_status_synchronously(monkeypatch):
    calls = []
    relay.state.pending_statuses = {
        "task-1": {"task_id": "task-1", "status": "running", "progress": 0.5}
    }
    relay.state.status_lock = asyncio.Lock()

    async def fake_forward(method, path, *, params=None, json_body=None, retry=True):
        calls.append((method, path, json_body, retry))
        return JSONResponse({"status": "ok"})

    monkeypatch.setattr(relay, "_forward_request", fake_forward)
    payload = {
        "task_id": "task-1",
        "agent_id": "agent-1",
        "status": "failed",
        "error": "boom",
    }

    response = await relay.update_status(FakeRequest(payload))

    assert response.status_code == 200
    assert calls == [
        ("POST", "/api/agent/task/status", payload, True),
    ]
    assert relay.state.pending_statuses == {}


@pytest.mark.asyncio
async def test_relay_drops_queued_progress_before_forwarding_complete(monkeypatch):
    calls = []
    relay.state.pending_statuses = {
        "task-1": {"task_id": "task-1", "status": "running", "progress": 0.9}
    }
    relay.state.status_lock = asyncio.Lock()

    async def fake_forward(method, path, *, params=None, json_body=None, retry=True):
        calls.append((method, path, json_body, retry))
        return JSONResponse({"status": "ok"})

    monkeypatch.setattr(relay, "_forward_request", fake_forward)
    payload = {
        "task_id": "task-1",
        "agent_id": "agent-1",
        "result": "result.png",
    }

    response = await relay.complete_task(FakeRequest(payload))

    assert response.status_code == 200
    assert calls == [
        ("POST", "/api/agent/task/complete", payload, True),
    ]
    assert relay.state.pending_statuses == {}


@pytest.mark.asyncio
async def test_upload_result_puts_all_assets_and_cleans_spool_files(tmp_path):
    primary_path = tmp_path / "primary.png"
    extra_path = tmp_path / "last_frame.png"
    primary_path.write_bytes(b"primary")
    extra_path.write_bytes(b"extra")
    uploads = []

    class FakeMinio:
        def fput_object(self, bucket, object_name, file_path, content_type):
            uploads.append((bucket, object_name, Path(file_path).read_bytes(), content_type))

    relay.state.minio_client = FakeMinio()
    request = relay.UploadResultRequest(
        task_id="task-1",
        result_bucket="user-data-prod",
        primary=relay.UploadAsset(
            file_path=str(primary_path),
            object_name="primary.png",
            content_type="image/png",
        ),
        extra_outputs={
            "last_frame": relay.UploadAsset(
                file_path=str(extra_path),
                object_name="last_frame.png",
                content_type="image/png",
                media_type="image",
            )
        },
    )

    result = await relay.upload_result(request)

    assert result == {
        "status": "ok",
        "extra_outputs": {
            "last_frame": {"path": "last_frame.png", "media_type": "image"}
        },
    }
    assert uploads == [
        ("user-data-prod", "primary.png", b"primary", "image/png"),
        ("user-data-prod", "last_frame.png", b"extra", "image/png"),
    ]
    assert not primary_path.exists()
    assert not extra_path.exists()


@pytest.mark.asyncio
async def test_upload_retry_logs_the_underlying_spool_error(monkeypatch, tmp_path, caplog):
    missing_path = tmp_path / "missing.png"
    relay.state.minio_client = object()
    monkeypatch.setattr(relay, "UPLOAD_RETRY_ATTEMPTS", 1)
    asset = relay.UploadAsset(
        file_path=str(missing_path),
        object_name="result.png",
        content_type="image/png",
    )

    with caplog.at_level("WARNING", logger="local_relay"):
        with pytest.raises(RuntimeError, match="R2 upload failed"):
            await relay._upload_asset_with_retry(bucket="user-data-test", asset=asset)

    assert "upload_asset_attempt_failed" in caplog.text
    assert "FileNotFoundError" in caplog.text
    assert "spool file not found" in caplog.text
