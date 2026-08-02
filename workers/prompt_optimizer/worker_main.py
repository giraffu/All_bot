from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from minio import Minio

from workers.prompt_optimizer.executor import execute_prompt_optimization
from workers.prompt_optimizer.media import image_bytes_to_data_url
from workers.prompt_optimizer.provider import LMStudioChatProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prompt_optimizer_worker")

LANE_COUNT = 4
MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8096").rstrip("/")
AGENT_SECRET_TOKEN = os.environ["AGENT_SECRET_TOKEN"]
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "ltx-prompt-optimizer")
HEALTH_PORT = int(os.getenv("PROMPT_OPTIMIZER_HEALTH_PORT", "8097"))
POLL_SECONDS = float(os.getenv("PROMPT_OPTIMIZER_POLL_SECONDS", "1.0"))
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "user-data-test")

_state: dict[str, Any] = {"ready": False, "reason": "starting", "active_lanes": 0}
_lane_readiness: dict[int, tuple[bool, str]] = {}
_state_lock = threading.Lock()


def _set_lane_readiness(lane_number: int, ready: bool, reason: str) -> None:
    with _state_lock:
        _lane_readiness[lane_number] = (ready, reason)
        all_ready = len(_lane_readiness) == LANE_COUNT and all(
            value[0] for value in _lane_readiness.values()
        )
        _state["ready"] = all_ready
        _state["reason"] = "ready" if all_ready else reason


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path not in {"/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return
        with _state_lock:
            payload = dict(_state)
        status = 200 if self.path == "/health" or payload["ready"] else 503
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _start_health_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", HEALTH_PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def _minio_client() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000").removeprefix(
        "http://"
    ).removeprefix("https://")
    return Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=os.getenv("MINIO_SECURE", "false").lower() in {"1", "true", "yes"},
    )


async def _load_object(client: Minio, object_key: str) -> bytes:
    def _read() -> bytes:
        response = client.get_object(MINIO_BUCKET, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_read)


class CentralClient:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            base_url=MASTER_API_URL,
            headers={"Authorization": f"Bearer {AGENT_SECRET_TOKEN}"},
            timeout=30,
            trust_env=False,
        )

    async def heartbeat(self, agent_id: str, *, ready: bool, reason: str) -> None:
        response = await self.client.post(
            "/api/agent/task/heartbeat",
            json={
                "agent_id": agent_id,
                "types": "prompt_optimize",
                "status": "idle" if ready else "error",
                "health_reason": reason,
                "provider": "lmstudio",
                "runtime_profile": "prompt_optimizer",
                "model_bundle_versions": json.dumps(
                    {"model": LM_STUDIO_MODEL}, separators=(",", ":")
                ),
            },
        )
        response.raise_for_status()

    async def pop(self, agent_id: str) -> dict[str, Any] | None:
        response = await self.client.get(
            "/api/agent/task/pop",
            params={
                "types": "prompt_optimize",
                "agent_id": agent_id,
                "cancel_lock": "true",
            },
        )
        response.raise_for_status()
        return response.json().get("task")

    async def fail(self, task_id: str, agent_id: str, error: str) -> None:
        await self.client.post(
            "/api/agent/task/status",
            json={
                "task_id": task_id,
                "agent_id": agent_id,
                "status": "failed",
                "error": error[:500],
                "set_current": False,
            },
        )

    async def complete(
        self, task_id: str, agent_id: str, result: dict[str, Any]
    ) -> None:
        await self.client.post(
            "/api/agent/task/complete",
            json={
                "task_id": task_id,
                "agent_id": agent_id,
                "result": "",
                **result,
            },
        )


def _parse_params(task: dict[str, Any]) -> dict[str, Any]:
    params = task.get("params")
    if isinstance(params, str):
        params = json.loads(params)
    if not isinstance(params, dict):
        raise ValueError("task params are invalid")
    return params


async def _lane(
    lane_number: int,
    *,
    central: CentralClient,
    provider: LMStudioChatProvider,
    minio_client: Minio,
) -> None:
    agent_id = f"prompt_optimizer_test_{lane_number:02d}"
    while True:
        readiness = await provider.readiness()
        _set_lane_readiness(lane_number, False, readiness.reason)
        try:
            await central.heartbeat(
                agent_id, ready=readiness.ready, reason=readiness.reason
            )
            if not readiness.ready:
                await asyncio.sleep(5)
                continue
            _set_lane_readiness(lane_number, True, "ready")
            task = await central.pop(agent_id)
            if task is None:
                await asyncio.sleep(POLL_SECONDS)
                continue
            task_id = str(task["task_id"])
            with _state_lock:
                _state["active_lanes"] += 1
            try:
                result = await execute_prompt_optimization(
                    _parse_params(task),
                    provider=provider,
                    load_media=lambda key: _load_object(minio_client, key),
                    preprocess_media=image_bytes_to_data_url,
                )
                await central.complete(task_id, agent_id, result)
            except Exception as exc:
                logger.warning("prompt task failed task_id=%s reason=%s", task_id, type(exc).__name__)
                await central.fail(task_id, agent_id, type(exc).__name__)
            finally:
                with _state_lock:
                    _state["active_lanes"] -= 1
        except Exception as exc:
            _set_lane_readiness(
                lane_number, False, f"central_unavailable:{type(exc).__name__}"
            )
            logger.warning("lane unavailable lane=%s reason=%s", lane_number, type(exc).__name__)
            await asyncio.sleep(2)


async def main() -> None:
    _start_health_server()
    central = CentralClient()
    provider = LMStudioChatProvider(
        base_url=LM_STUDIO_BASE_URL,
        model=LM_STUDIO_MODEL,
    )
    minio_client = _minio_client()
    await asyncio.gather(
        *(
            _lane(
                lane,
                central=central,
                provider=provider,
                minio_client=minio_client,
            )
            for lane in range(1, LANE_COUNT + 1)
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
