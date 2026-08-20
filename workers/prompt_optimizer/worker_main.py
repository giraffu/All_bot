from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Awaitable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TypeVar

import httpx
from minio import Minio

from workers.prompt_optimizer.executor import (
    PromptOptimizationExecutionError,
    execute_prompt_optimization,
)
from workers.prompt_optimizer.media import image_bytes_to_data_url
from workers.prompt_optimizer.provider import LMStudioChatProvider, ModelResponseError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prompt_optimizer_worker")

LANE_COUNT = 4
MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8096").rstrip("/")
AGENT_SECRET_TOKEN = os.environ["AGENT_SECRET_TOKEN"]
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "ltx-prompt-optimizer")
HEALTH_PORT = int(os.getenv("PROMPT_OPTIMIZER_HEALTH_PORT", "8097"))
POLL_SECONDS = float(os.getenv("PROMPT_OPTIMIZER_POLL_SECONDS", "1.0"))
TASK_HEARTBEAT_SECONDS = 15.0
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "user-data-test")
_T = TypeVar("_T")

_state: dict[str, Any] = {
    "ready": False,
    "reason": "starting",
    "active_lanes": 0,
    "ready_lanes": 0,
    "draining": False,
}
_lane_readiness: dict[int, tuple[bool, str]] = {}
_state_lock = threading.Lock()
_SAFE_FAILURE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def _safe_failure_reason(exc: Exception) -> str:
    error_type = type(exc).__name__
    if isinstance(exc, (PromptOptimizationExecutionError, ModelResponseError)):
        code = str(exc).strip()
        if _SAFE_FAILURE_CODE_PATTERN.fullmatch(code):
            return f"{error_type}:{code}"
    return error_type


def _set_lane_readiness(lane_number: int, ready: bool, reason: str) -> None:
    with _state_lock:
        _lane_readiness[lane_number] = (ready, reason)
        all_ready = len(_lane_readiness) == LANE_COUNT and all(
            value[0] for value in _lane_readiness.values()
        )
        _state["ready_lanes"] = sum(
            1 for ready_state, _ in _lane_readiness.values() if ready_state
        )
        _state["ready"] = all_ready and not _state["draining"]
        _state["reason"] = (
            "draining" if _state["draining"] else ("ready" if all_ready else reason)
        )


class HealthHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, Any], status: int) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path not in {"/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return
        with _state_lock:
            payload = dict(_state)
        status = 200 if self.path == "/health" or payload["ready"] else 503
        self._send_json(payload, status)

    def do_POST(self):
        if self.path not in {"/drain", "/resume"}:
            self._send_json({"detail": "not found"}, 404)
            return
        with _state_lock:
            _state["draining"] = self.path == "/drain"
            all_ready = len(_lane_readiness) == LANE_COUNT and all(
                value[0] for value in _lane_readiness.values()
            )
            _state["ready"] = all_ready and not _state["draining"]
            _state["reason"] = "draining" if _state["draining"] else "resuming"
            payload = dict(_state)
        self._send_json(payload, 200)

    def log_message(self, _format, *_args):
        return


def _start_health_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", HEALTH_PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def _minio_client() -> Minio:
    endpoint = (
        os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
        .removeprefix("http://")
        .removeprefix("https://")
    )
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

    async def task_heartbeat(self, task_id: str, agent_id: str) -> None:
        response = await self.client.post(
            "/api/agent/task/task_heartbeat",
            json={"task_id": task_id, "agent_id": agent_id},
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

    async def fail(
        self, task_id: str, agent_id: str, error: str, *, attempt_id: str | None = None
    ) -> None:
        response = await self.client.post(
            "/api/agent/task/status",
            json={
                "task_id": task_id,
                "agent_id": agent_id,
                "status": "failed",
                "error": error[:500],
                "set_current": False,
                "attempt_id": attempt_id,
            },
        )
        response.raise_for_status()

    async def complete(
        self,
        task_id: str,
        agent_id: str,
        result: dict[str, Any],
        *,
        attempt_id: str | None = None,
    ) -> None:
        response = await self.client.post(
            "/api/agent/task/complete",
            json={
                "task_id": task_id,
                "agent_id": agent_id,
                "result": "",
                "attempt_id": attempt_id,
                **result,
            },
        )
        response.raise_for_status()

    async def text_delta(
        self,
        *,
        task_id: str,
        agent_id: str,
        attempt_id: str,
        sequence: int,
        field: str,
        delta: str,
    ) -> None:
        payload = {
            "task_id": task_id,
            "agent_id": agent_id,
            "attempt_id": attempt_id,
            "sequence": sequence,
            "field": field,
            "delta": delta,
        }
        for retry in range(3):
            try:
                response = await self.client.post(
                    "/api/agent/task/text-delta", json=payload
                )
                response.raise_for_status()
                return
            except (httpx.TimeoutException, httpx.TransportError):
                if retry == 2:
                    raise
                await asyncio.sleep((0.25, 1.0, 2.0)[retry])


class TextDeltaEmitter:
    def __init__(
        self,
        *,
        central: CentralClient,
        task_id: str,
        agent_id: str,
        attempt_id: str,
    ) -> None:
        self.central = central
        self.task_id = task_id
        self.agent_id = agent_id
        self.attempt_id = attempt_id
        self.sequence = 0
        self.buffers: dict[str, str] = {}
        self.last_flush = time.monotonic()

    async def add(self, field: str, delta: str) -> None:
        self.buffers[field] = self.buffers.get(field, "") + delta
        while len(self.buffers[field]) >= 64:
            await self._send(field, self.buffers[field][:64])
            self.buffers[field] = self.buffers[field][64:]
        if time.monotonic() - self.last_flush >= 0.05:
            await self.flush()

    async def _send(self, field: str, delta: str) -> None:
        if not delta:
            return
        next_sequence = self.sequence + 1
        await self.central.text_delta(
            task_id=self.task_id,
            agent_id=self.agent_id,
            attempt_id=self.attempt_id,
            sequence=next_sequence,
            field=field,
            delta=delta,
        )
        self.sequence = next_sequence
        self.last_flush = time.monotonic()

    async def flush(self) -> None:
        for field in tuple(self.buffers):
            delta = self.buffers[field]
            self.buffers[field] = ""
            await self._send(field, delta)


def _parse_params(task: dict[str, Any]) -> dict[str, Any]:
    params = task.get("params")
    if isinstance(params, str):
        params = json.loads(params)
    if not isinstance(params, dict):
        raise ValueError("task params are invalid")
    return params


async def _run_with_task_heartbeats(
    operation: Awaitable[_T],
    *,
    central: CentralClient,
    task_id: str,
    agent_id: str,
    interval_seconds: float = TASK_HEARTBEAT_SECONDS,
) -> _T:
    async def maintain_heartbeat() -> None:
        while True:
            try:
                await central.task_heartbeat(task_id, agent_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "task heartbeat unavailable task_id=%s reason=%s",
                    task_id,
                    type(exc).__name__,
                )
            await asyncio.sleep(interval_seconds)

    heartbeat_task = asyncio.create_task(maintain_heartbeat())
    try:
        return await operation
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


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
        with _state_lock:
            draining = bool(_state["draining"])
        if draining:
            readiness = type(readiness)(False, "draining")
        if not readiness.ready:
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
                attempt_id = str(uuid.uuid4())
                emitter = TextDeltaEmitter(
                    central=central,
                    task_id=task_id,
                    agent_id=agent_id,
                    attempt_id=attempt_id,
                )
                result = await _run_with_task_heartbeats(
                    execute_prompt_optimization(
                        _parse_params(task),
                        provider=provider,
                        load_media=lambda key: _load_object(minio_client, key),
                        preprocess_media=image_bytes_to_data_url,
                        on_text_delta=emitter.add,
                    ),
                    central=central,
                    task_id=task_id,
                    agent_id=agent_id,
                )
                await emitter.flush()
                await central.complete(task_id, agent_id, result, attempt_id=attempt_id)
            except Exception as exc:
                failure_reason = _safe_failure_reason(exc)
                logger.warning(
                    "prompt task failed task_id=%s reason=%s",
                    task_id,
                    failure_reason,
                )
                if "emitter" in locals():
                    try:
                        await emitter.flush()
                    except Exception:
                        pass
                await central.fail(
                    task_id,
                    agent_id,
                    failure_reason,
                    attempt_id=locals().get("attempt_id"),
                )
            finally:
                with _state_lock:
                    _state["active_lanes"] -= 1
        except Exception as exc:
            _set_lane_readiness(
                lane_number, False, f"central_unavailable:{type(exc).__name__}"
            )
            logger.warning(
                "lane unavailable lane=%s reason=%s", lane_number, type(exc).__name__
            )
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
