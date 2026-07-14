import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from minio import Minio  # type: ignore
from pydantic import BaseModel, Field


LOG_LEVEL = os.getenv("LOCAL_RELAY_LOG_LEVEL", "INFO").upper()
CENTRAL_API_URL = os.getenv("CENTRAL_API_URL") or os.getenv(
    "RELAY_UPSTREAM_URL",
    "http://127.0.0.1:8000",
)
AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("RELAY_REQUEST_TIMEOUT_SECONDS", "30"))
REQUEST_RETRY_ATTEMPTS = int(os.getenv("RELAY_REQUEST_RETRY_ATTEMPTS", "3"))
RELAY_READY_TIMEOUT_SECONDS = float(os.getenv("RELAY_READY_TIMEOUT_SECONDS", "3"))
STATUS_FLUSH_INTERVAL_SECONDS = float(
    os.getenv("RELAY_STATUS_FLUSH_INTERVAL_SECONDS", "0.5")
)
UPLOAD_RETRY_ATTEMPTS = int(os.getenv("UPLOAD_SIDECAR_RETRY_ATTEMPTS", "3"))
UPLOAD_RETRY_BASE_SECONDS = float(
    os.getenv("UPLOAD_SIDECAR_RETRY_BASE_SECONDS", "0.5")
)
RESULT_SPOOL_DIR = os.getenv("RESULT_SPOOL_DIR", "/app/spool")
SPOOL_ORPHAN_MAX_AGE_SECONDS = float(
    os.getenv("SPOOL_ORPHAN_MAX_AGE_SECONDS", str(6 * 60 * 60))
)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("local_relay")


class RelayState:
    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None
        self.minio_client: Minio | None = None
        self.pending_statuses: dict[str, dict[str, Any]] = {}
        self.status_lock = asyncio.Lock()
        self.flush_task: asyncio.Task | None = None
        self.running = False


state = RelayState()


class UploadAsset(BaseModel):
    file_path: str
    object_name: str
    content_type: str = "application/octet-stream"
    media_type: str | None = None


class UploadResultRequest(BaseModel):
    task_id: str
    result_bucket: str
    primary: UploadAsset
    extra_outputs: dict[str, UploadAsset] = Field(default_factory=dict)


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if AGENT_SECRET_TOKEN:
        headers["Authorization"] = f"Bearer {AGENT_SECRET_TOKEN}"
    return headers


def _json_response_from_upstream(response: httpx.Response) -> JSONResponse:
    try:
        content = response.json()
    except ValueError:
        content = {"detail": response.text}
    return JSONResponse(status_code=response.status_code, content=content)


async def _forward_request(
    method: str,
    path: str,
    *,
    params: Any = None,
    json_body: Any = None,
    retry: bool = True,
) -> JSONResponse:
    if state.client is None:
        raise HTTPException(status_code=503, detail="Relay upstream client is not ready")

    attempts = max(1, REQUEST_RETRY_ATTEMPTS if retry else 1)
    last_error: Exception | None = None
    started = time.monotonic()

    for attempt in range(1, attempts + 1):
        try:
            response = await state.client.request(
                method,
                path,
                params=params,
                json=json_body,
            )
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.info(
                "relay_forward method=%s path=%s status=%s attempts=%s elapsed_ms=%.1f",
                method,
                path,
                response.status_code,
                attempt,
                elapsed_ms,
            )
            if response.status_code >= 500 and attempt < attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 5))
                continue
            return _json_response_from_upstream(response)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            await asyncio.sleep(min(2 ** (attempt - 1), 5))

    elapsed_ms = (time.monotonic() - started) * 1000
    logger.error(
        "relay_forward_failed method=%s path=%s attempts=%s elapsed_ms=%.1f error=%s",
        method,
        path,
        attempts,
        elapsed_ms,
        last_error,
    )
    raise HTTPException(status_code=502, detail="Central API relay failed")


async def _flush_status_once() -> None:
    async with state.status_lock:
        pending = list(state.pending_statuses.values())
        state.pending_statuses.clear()

    for payload in pending:
        try:
            await _forward_request(
                "POST",
                "/api/agent/task/status",
                json_body=payload,
                retry=True,
            )
        except Exception as exc:
            task_id = payload.get("task_id", "")
            logger.warning("status_flush_failed task_id=%s error=%s", task_id, exc)
            async with state.status_lock:
                state.pending_statuses[task_id] = payload


async def _drop_pending_status(task_id: str) -> None:
    if not task_id:
        return
    async with state.status_lock:
        state.pending_statuses.pop(task_id, None)


async def _status_flush_loop() -> None:
    while state.running:
        await asyncio.sleep(STATUS_FLUSH_INTERVAL_SECONDS)
        await _flush_status_once()


def _cleanup_orphan_spool_files() -> None:
    spool_dir = Path(RESULT_SPOOL_DIR)
    spool_dir.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - SPOOL_ORPHAN_MAX_AGE_SECONDS
    for path in spool_dir.rglob("*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                logger.info("removed_orphan_spool_file path=%s", path)
        except Exception as exc:
            logger.warning("orphan_spool_cleanup_failed path=%s error=%s", path, exc)


async def startup() -> None:
    state.client = httpx.AsyncClient(
        base_url=CENTRAL_API_URL,
        headers=_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    state.minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )
    await asyncio.to_thread(_cleanup_orphan_spool_files)
    state.running = True
    state.flush_task = asyncio.create_task(_status_flush_loop())
    logger.info("local_relay_started upstream=%s spool_dir=%s", CENTRAL_API_URL, RESULT_SPOOL_DIR)


async def shutdown() -> None:
    state.running = False
    if state.flush_task:
        state.flush_task.cancel()
        try:
            await state.flush_task
        except asyncio.CancelledError:
            pass
    await _flush_status_once()
    if state.client:
        await state.client.aclose()
    logger.info("local_relay_stopped")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await startup()
    try:
        yield
    finally:
        await shutdown()


app = FastAPI(title="AllBot Local Worker Relay", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "upstream": CENTRAL_API_URL}


@app.get("/ready")
async def ready() -> Any:
    checks: dict[str, Any] = {
        "upstream": CENTRAL_API_URL,
        "upstream_ok": False,
        "client_ready": state.client is not None,
        "upload_client_ready": state.minio_client is not None,
        "pending_statuses": len(state.pending_statuses),
    }
    if state.client is None:
        checks["error"] = "upstream client is not ready"
        return JSONResponse(status_code=503, content={"status": "error", **checks})
    if state.minio_client is None:
        checks["error"] = "upload client is not ready"
        return JSONResponse(status_code=503, content={"status": "error", **checks})

    try:
        response = await state.client.get(
            "/health",
            timeout=RELAY_READY_TIMEOUT_SECONDS,
        )
        checks["upstream_status_code"] = response.status_code
        checks["upstream_ok"] = response.status_code < 500
    except Exception as exc:
        checks["error"] = str(exc)
        return JSONResponse(status_code=503, content={"status": "error", **checks})

    if not checks["upstream_ok"]:
        return JSONResponse(status_code=503, content={"status": "error", **checks})
    return {"status": "ok", **checks}


@app.get("/api/agent/task/pop")
async def pop_task(request: Request) -> JSONResponse:
    return await _forward_request(
        "GET",
        "/api/agent/task/pop",
        params=request.query_params,
        retry=True,
    )


@app.get("/api/agent/task/peek")
async def peek_task(request: Request) -> JSONResponse:
    return await _forward_request(
        "GET",
        "/api/agent/task/peek",
        params=request.query_params,
        retry=True,
    )


@app.get("/api/agent/task/check/{task_id}")
async def check_task(task_id: str) -> JSONResponse:
    return await _forward_request(
        "GET",
        f"/api/agent/task/check/{task_id}",
        retry=True,
    )


@app.post("/api/agent/task/status")
async def update_status(request: Request):
    payload = await request.json()
    status = str(payload.get("status", ""))
    if status in {"failed", "cancelled"}:
        await _drop_pending_status(str(payload.get("task_id", "")))
        return await _forward_request(
            "POST",
            "/api/agent/task/status",
            json_body=payload,
            retry=True,
        )

    task_id = str(payload.get("task_id", ""))
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")

    async with state.status_lock:
        state.pending_statuses[task_id] = payload
    return {"status": "ok", "relayed": "queued"}


@app.post("/api/agent/task/complete")
async def complete_task(request: Request) -> JSONResponse:
    payload = await request.json()
    await _drop_pending_status(str(payload.get("task_id", "")))
    return await _forward_request(
        "POST",
        "/api/agent/task/complete",
        json_body=payload,
        retry=True,
    )


@app.post("/api/agent/task/heartbeat")
async def heartbeat(request: Request) -> JSONResponse:
    return await _forward_request(
        "POST",
        "/api/agent/task/heartbeat",
        json_body=await request.json(),
        retry=True,
    )


@app.post("/api/agent/task/task_heartbeat")
async def task_heartbeat(request: Request) -> JSONResponse:
    return await _forward_request(
        "POST",
        "/api/agent/task/task_heartbeat",
        json_body=await request.json(),
        retry=True,
    )


def _upload_one_asset(*, client: Minio, bucket: str, asset: UploadAsset) -> None:
    file_path = Path(asset.file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"spool file not found: {file_path}")
    client.fput_object(
        bucket,
        asset.object_name,
        str(file_path),
        content_type=asset.content_type,
    )


async def _upload_asset_with_retry(*, bucket: str, asset: UploadAsset) -> None:
    if state.minio_client is None:
        raise HTTPException(status_code=503, detail="Upload client is not ready")

    last_error: Exception | None = None
    for attempt in range(1, max(1, UPLOAD_RETRY_ATTEMPTS) + 1):
        try:
            await asyncio.to_thread(
                _upload_one_asset,
                client=state.minio_client,
                bucket=bucket,
                asset=asset,
            )
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "upload_asset_attempt_failed object_name=%s attempt=%s/%s "
                "error_type=%s error=%s",
                asset.object_name,
                attempt,
                max(1, UPLOAD_RETRY_ATTEMPTS),
                type(exc).__name__,
                exc,
            )
            if attempt >= max(1, UPLOAD_RETRY_ATTEMPTS):
                break
            delay = min(UPLOAD_RETRY_BASE_SECONDS * (2 ** (attempt - 1)), 5)
            await asyncio.sleep(delay)

    raise RuntimeError(f"R2 upload failed for {asset.object_name}") from last_error


def _cleanup_uploaded_files(assets: list[UploadAsset]) -> None:
    for asset in assets:
        try:
            Path(asset.file_path).unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("uploaded_spool_cleanup_failed path=%s error=%s", asset.file_path, exc)


@app.post("/api/local/upload-result")
async def upload_result(request: UploadResultRequest) -> dict[str, Any]:
    started = time.monotonic()
    all_assets = [request.primary, *request.extra_outputs.values()]
    try:
        await _upload_asset_with_retry(
            bucket=request.result_bucket,
            asset=request.primary,
        )
        extra_outputs_payload: dict[str, dict[str, Any]] = {}
        for name, asset in request.extra_outputs.items():
            await _upload_asset_with_retry(bucket=request.result_bucket, asset=asset)
            extra_outputs_payload[name] = {
                "path": asset.object_name,
                "media_type": asset.media_type or "image",
            }
    except Exception as exc:
        elapsed_ms = (time.monotonic() - started) * 1000
        logger.error(
            "sidecar_upload_failed task_id=%s elapsed_ms=%.1f error=%s",
            request.task_id,
            elapsed_ms,
            exc,
        )
        raise HTTPException(status_code=502, detail="R2 upload failed") from exc

    await asyncio.to_thread(_cleanup_uploaded_files, all_assets)
    elapsed_ms = (time.monotonic() - started) * 1000
    logger.info(
        "sidecar_upload_succeeded task_id=%s assets=%s elapsed_ms=%.1f",
        request.task_id,
        len(all_assets),
        elapsed_ms,
    )
    return {"status": "ok", "extra_outputs": extra_outputs_payload}


if __name__ == "__main__":
    uvicorn.run(
        "local_relay.relay_main:app",
        host=os.getenv("LOCAL_RELAY_HOST", "127.0.0.1"),
        port=int(os.getenv("LOCAL_RELAY_PORT", "8013")),
        log_level=LOG_LEVEL.lower(),
    )
