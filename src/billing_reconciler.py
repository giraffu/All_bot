from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("billing-reconciler")
BILLING_RECONCILER_HEALTH_PORT = 8032


def billing_reconciler_enabled() -> bool:
    return os.getenv("BILLING_RECONCILER_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_health_payload(
    *, enabled: bool, worker_id: str, task_states: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    return {
        "status": "enabled" if enabled else "disabled",
        "worker_id": worker_id,
        "updated_at": time.time(),
        "channels": task_states,
    }


async def _handle_health_request(reader, writer, *, payload) -> None:
    try:
        await reader.read(4096)
        body = json.dumps(payload(), separators=(",", ":")).encode("utf-8")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


def build_notification_application(token: str):
    from telegram.ext import ApplicationBuilder

    from src.services.telegram_runtime_bootstrap import (
        build_telegram_bot_base_url,
        build_telegram_httpx_request,
        resolve_telegram_file_base_url,
    )

    request = build_telegram_httpx_request(connection_pool_size=20)
    return (
        ApplicationBuilder()
        .token(token)
        .base_url(build_telegram_bot_base_url())
        .base_file_url(resolve_telegram_file_base_url())
        .request(request)
        .build()
    )


async def run_billing_reconciler_worker(
    *,
    stop_event: asyncio.Event | None = None,
    reconciler_runner: Callable[..., Awaitable[None]] | None = None,
) -> None:
    enabled = billing_reconciler_enabled()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    task_states: dict[str, dict[str, Any]] = {}
    server = await asyncio.start_server(
        lambda reader, writer: _handle_health_request(
            reader,
            writer,
            payload=lambda: build_health_payload(
                enabled=enabled,
                worker_id=worker_id,
                task_states=task_states,
            ),
        ),
        host="0.0.0.0",
        port=int(
            os.getenv(
                "BILLING_RECONCILER_HEALTH_PORT",
                str(BILLING_RECONCILER_HEALTH_PORT),
            )
        ),
    )
    application = None
    worker_task = None
    wait_task = None
    engine_resource = None
    local_stop = stop_event or asyncio.Event()
    try:
        if enabled:
            from src.billing_core_provider_setup import (
                ensure_billing_core_providers_registered,
            )
            from src.database.core import engine, init_db
            from src.services.billing_reconciler import run_billing_reconcilers

            engine_resource = engine
            token = os.getenv("BOT_TOKEN", "").strip()
            if not token:
                raise RuntimeError("BOT_TOKEN is required when billing reconciler is enabled")
            ensure_billing_core_providers_registered()
            await init_db()
            application = build_notification_application(token)
            await application.initialize()
            runner = reconciler_runner or run_billing_reconcilers
            worker_task = asyncio.create_task(
                runner(
                    application,
                    task_states=task_states,
                    stop_event=local_stop,
                ),
                name="billing-reconciliation-channels",
            )
            logger.info("Billing reconciler enabled worker_id=%s", worker_id)
        else:
            logger.info("Billing reconciler is disabled; health endpoint only")

        wait_task = asyncio.create_task(local_stop.wait(), name="billing-stop")
        watched = {wait_task}
        if worker_task is not None:
            watched.add(worker_task)
        done, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
        if worker_task is not None and worker_task in done:
            await worker_task
    finally:
        local_stop.set()
        for task in (wait_task, worker_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (wait_task, worker_task) if task is not None),
            return_exceptions=True,
        )
        if application is not None:
            await application.shutdown()
        server.close()
        await server.wait_closed()
        if engine_resource is not None:
            await engine_resource.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_billing_reconciler_worker())


if __name__ == "__main__":
    main()
