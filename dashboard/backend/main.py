# ruff: noqa: E402
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

import fastapi.responses
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError

from dashboard.backend.auth import auth_router, get_current_user
from dashboard.backend.routers import (
    gallery,
    history,
    logs,
    paid_group_guard,
    plans,
    referrals,
    runpod,
    site_notice,
    stats,
    system,
    templates,
    users,
    workers,
)
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from dashboard.backend.services.worker_listener import start_worker_listener
from dashboard.backend.services.balance_monitor import update_external_balances
from dashboard.backend.services.runpod_autoscaler_service import (
    run_runpod_autoscaler_loop,
    should_start_runpod_autoscaler_loop,
)
from src.billing_core_provider_setup import ensure_billing_core_providers_registered
from src.database.core import init_db
from src.task_core_provider_setup import ensure_task_core_service_providers_registered

logging.basicConfig(level=logging.INFO)
background_tasks = set()
logger = logging.getLogger("dashboard")
DB_INIT_RETRY_ATTEMPTS = 5
DB_INIT_RETRY_DELAY_SECONDS = 2
DB_INIT_BACKGROUND_RETRY_ATTEMPTS = 36
DB_INIT_BACKGROUND_RETRY_DELAY_SECONDS = 5


def _initial_dashboard_health() -> dict:
    return {
        "database_ready": False,
        "startup_complete": False,
        "database_error": None,
    }


async def startup_event():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    ensure_task_core_service_providers_registered()
    ensure_billing_core_providers_registered()
    database_ready = await _initialize_database_with_retries(
        attempts=DB_INIT_RETRY_ATTEMPTS,
        delay_seconds=DB_INIT_RETRY_DELAY_SECONDS,
        phase="startup",
    )
    if not database_ready:
        db_retry_task = asyncio.create_task(
            _initialize_database_with_retries(
                attempts=DB_INIT_BACKGROUND_RETRY_ATTEMPTS,
                delay_seconds=DB_INIT_BACKGROUND_RETRY_DELAY_SECONDS,
                phase="background",
            )
        )
        background_tasks.add(db_retry_task)
        db_retry_task.add_done_callback(background_tasks.discard)

    # Start background worker listener and keep a strong reference
    task = asyncio.create_task(start_worker_listener(task_registry=background_tasks))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    # Start balance monitor
    balance_task = asyncio.create_task(update_external_balances())
    background_tasks.add(balance_task)
    balance_task.add_done_callback(background_tasks.discard)

    if should_start_runpod_autoscaler_loop():
        runpod_autoscaler_task = asyncio.create_task(run_runpod_autoscaler_loop())
        background_tasks.add(runpod_autoscaler_task)
        runpod_autoscaler_task.add_done_callback(background_tasks.discard)

    app.state.dashboard_health["startup_complete"] = True


async def _initialize_database_with_retries(
    *, attempts: int, delay_seconds: int, phase: str
) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            await init_db()
            logger.info("Database initialized successfully during %s", phase)
            app.state.dashboard_health["database_ready"] = True
            app.state.dashboard_health["database_error"] = None
            return True
        except Exception as e:
            app.state.dashboard_health["database_ready"] = False
            app.state.dashboard_health["database_error"] = str(e)
            if attempt >= attempts:
                logger.error(
                    "Failed to initialize database during %s after %s attempts: %s",
                    phase,
                    attempts,
                    e,
                )
                return False
            logger.warning(
                "Database initialization failed during %s on attempt %s/%s: %s; retrying in %ss",
                phase,
                attempt,
                attempts,
                e,
                delay_seconds,
            )
            await asyncio.sleep(delay_seconds)


async def shutdown_event():
    for task in list(background_tasks):
        task.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
    background_tasks.clear()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await startup_event()
    try:
        yield
    finally:
        await shutdown_event()


app = FastAPI(title="TeleBot Dashboard API", lifespan=lifespan)
app.state.dashboard_health = _initial_dashboard_health()

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(stats.router)
app.include_router(users.router)
app.include_router(history.router)
app.include_router(plans.router)
app.include_router(templates.router)
app.include_router(system.router)
app.include_router(logs.router)
app.include_router(paid_group_guard.router)
app.include_router(workers.router)
app.include_router(runpod.router)
app.include_router(gallery.router)
app.include_router(referrals.router)
app.include_router(site_notice.router)


def _build_auth_error_response(request: Request, detail: str):
    response = fastapi.responses.JSONResponse(
        status_code=401,
        content={"detail": detail},
    )
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_auth_header(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        public_paths = ["/api/auth/login", "/api/health", "/api/status"]
        if request.url.path not in public_paths:
            try:
                auth_header = request.headers.get("Authorization")
                if not auth_header or not auth_header.startswith("Bearer "):
                    return _build_auth_error_response(request, "Not authenticated")
                token = auth_header.split(" ")[1]
                await get_current_user(token)
            except JWTError:
                return _build_auth_error_response(
                    request, "Could not validate credentials"
                )
            except Exception:
                logger.exception(
                    "Unexpected dashboard auth middleware failure for path=%s",
                    request.url.path,
                )
                return _build_auth_error_response(
                    request, "Could not validate credentials"
                )
    return await call_next(request)


@app.get("/")
async def root():
    return {"message": "TeleBot Dashboard Backend is Running", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8043)
