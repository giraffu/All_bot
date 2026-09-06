from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from src.control_worker_health import (
    build_task_control_health_payload,
    build_task_control_worker_id,
)
from src.log_redaction import install_log_redaction

logger = logging.getLogger("task-control-worker")
TASK_CONTROL_HEALTH_PORT = 8031


def task_control_enabled() -> bool:
    return os.getenv("TASK_CONTROL_WORKER_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _handle_health_request(
    _reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    payload: Callable[[], dict[str, Any]],
) -> None:
    try:
        body = json.dumps(payload(), separators=(",", ":")).encode("utf-8")
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def run_task_control_worker(
    *,
    stop_event: asyncio.Event | None = None,
    service_runner: Callable[..., Awaitable[None]] | None = None,
) -> None:
    enabled = task_control_enabled()
    worker_id = build_task_control_worker_id()
    task_states: dict[str, dict[str, Any]] = {}

    def health_payload() -> dict[str, object]:
        return build_task_control_health_payload(
            enabled=enabled,
            worker_id=worker_id,
            task_states=task_states,
        )

    server = await asyncio.start_server(
        lambda reader, writer: _handle_health_request(
            reader,
            writer,
            payload=health_payload,
        ),
        host="0.0.0.0",
        port=int(os.getenv("TASK_CONTROL_HEALTH_PORT", str(TASK_CONTROL_HEALTH_PORT))),
    )
    service_task: asyncio.Task[None] | None = None
    wait_task: asyncio.Task[bool] | None = None
    redis_resource = None
    engine_resource = None
    try:
        if enabled:
            from src.billing_core_provider_setup import (
                ensure_billing_core_providers_registered,
            )
            from src.database.core import engine, init_db
            from src.services.redis_client import redis_client
            from src.services.task_control_worker import run_task_control_services
            from src.task_application_runtime import configure_task_application
            from src.task_web_finalizer_provider_setup import (
                configure_task_web_finalizer_providers,
            )
            from src.task_core_provider_setup import (
                ensure_task_core_service_providers_registered,
            )

            redis_resource = redis_client
            engine_resource = engine
            ensure_task_core_service_providers_registered()
            configure_task_application()
            configure_task_web_finalizer_providers()
            ensure_billing_core_providers_registered()
            await init_db()
            runner = service_runner or run_task_control_services
            service_task = asyncio.create_task(
                runner(worker_id=worker_id, task_states=task_states),
                name="task-control-services",
            )
            logger.info("Task control worker enabled worker_id=%s", worker_id)
        else:
            logger.info("Task control worker is disabled; health endpoint only")

        waiter = stop_event.wait() if stop_event is not None else asyncio.Event().wait()
        wait_task = asyncio.create_task(waiter, name="task-control-stop")
        watched = {wait_task}
        if service_task is not None:
            watched.add(service_task)
        done, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
        if service_task is not None and service_task in done:
            await service_task
    finally:
        if wait_task is not None:
            wait_task.cancel()
            await asyncio.gather(wait_task, return_exceptions=True)
        if service_task is not None:
            service_task.cancel()
            await asyncio.gather(service_task, return_exceptions=True)
        server.close()
        await server.wait_closed()
        if redis_resource is not None:
            await redis_resource.close()
        if engine_resource is not None:
            await engine_resource.dispose()


def main() -> None:
    install_log_redaction()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_task_control_worker())


if __name__ == "__main__":
    main()
