# ruff: noqa: E402
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

import fastapi.responses
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError

from dashboard.backend.qqcc_config_auth import (
    auth_router,
    get_current_qqcc_config_user,
)
from dashboard.backend.routers import private_bots, qqcc
from src.database.core import init_db
from src.services.private_qqcc_bot_management import PRIVATE_BOT_CONFIG_MAX_BYTES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qqcc_config")
DB_INIT_RETRY_ATTEMPTS = 5
DB_INIT_RETRY_DELAY_SECONDS = 2


def _initial_health() -> dict:
    return {
        "database_ready": False,
        "startup_complete": False,
        "database_error": None,
    }


async def startup_event() -> None:
    database_ready = await _initialize_database_with_retries(
        attempts=DB_INIT_RETRY_ATTEMPTS,
        phase="startup",
    )
    app.state.qqcc_config_health["database_ready"] = database_ready
    app.state.qqcc_config_health["startup_complete"] = True


async def _initialize_database_with_retries(
    *,
    attempts: int,
    phase: str,
) -> bool:
    import asyncio

    for attempt in range(1, attempts + 1):
        try:
            await init_db()
            logger.info("QQCC config database initialized during %s", phase)
            app.state.qqcc_config_health["database_error"] = None
            return True
        except Exception as exc:
            app.state.qqcc_config_health["database_error"] = str(exc)
            if attempt >= attempts:
                logger.error(
                    "Failed to initialize QQCC config database during %s after %s attempts: %s",
                    phase,
                    attempts,
                    exc,
                )
                return False
            logger.warning(
                "QQCC config database initialization failed during %s on attempt %s/%s: %s",
                phase,
                attempt,
                attempts,
                exc,
            )
            await asyncio.sleep(DB_INIT_RETRY_DELAY_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await startup_event()
    yield


app = FastAPI(title="QQCC Config API", lifespan=lifespan)
app.state.qqcc_config_health = _initial_health()

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(qqcc.router)
app.include_router(private_bots.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def sanitized_validation_error_handler(_request: Request, _exc):
    return fastapi.responses.JSONResponse(
        status_code=422,
        content={"detail": "Invalid request payload"},
    )


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


@app.middleware("http")
async def check_auth_header(request: Request, call_next):
    request_path = request.url.path
    request_host = str(request.url.hostname or "").lower().rstrip(".")
    owner_host = (
        os.getenv("PRIVATE_QQCC_BOT_OWNER_HOST", "")
        .strip()
        .lower()
        .rstrip(".")
    )
    admin_host = os.getenv("QQCC_CONFIG_ADMIN_HOST", "").strip().lower().rstrip(".")
    if request_path.startswith("/api/private-bots/owner/"):
        if owner_host and request_host != owner_host:
            return fastapi.responses.JSONResponse(
                status_code=404,
                content={"detail": "Not found"},
            )
    elif request_path.startswith("/api/private-bots/admin"):
        if (owner_host and request_host == owner_host) or (
            admin_host and request_host != admin_host
        ):
            return fastapi.responses.JSONResponse(
                status_code=404,
                content={"detail": "Not found"},
            )

    if request_path.startswith("/api/private-bots") and os.getenv(
        "PRIVATE_QQCC_BOT_ENABLED",
        "false",
    ).strip().lower() not in {"1", "true", "yes", "on"}:
        return fastapi.responses.JSONResponse(
            status_code=404,
            content={"detail": "Not found"},
        )

    if request.method == "OPTIONS":
        return await call_next(request)

    if (
        request.method == "PUT"
        and request_path == "/api/private-bots/owner/config"
    ):
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError:
            content_length = PRIVATE_BOT_CONFIG_MAX_BYTES + 1
        if content_length > PRIVATE_BOT_CONFIG_MAX_BYTES + 64 * 1024:
            return fastapi.responses.JSONResponse(
                status_code=413,
                content={"detail": "Private Bot config payload is too large"},
            )

    sensitive_owner_paths = {
        ("POST", "/api/private-bots/owner/auth/exchange"),
        ("PUT", "/api/private-bots/owner/credentials"),
    }
    if (request.method, request_path) in sensitive_owner_paths:
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError:
            content_length = 2049
        if content_length > 2048:
            return fastapi.responses.JSONResponse(
                status_code=413,
                content={"detail": "Sensitive request payload is too large"},
            )

    if request_path.startswith("/api/"):
        public_paths = {
            "/api/auth/login",
            "/api/health",
            "/api/private-bots/owner/auth/exchange",
        }
        owner_path = request_path.startswith("/api/private-bots/owner/")
        if request_path not in public_paths and not owner_path:
            try:
                auth_header = request.headers.get("Authorization")
                if not auth_header or not auth_header.startswith("Bearer "):
                    return _build_auth_error_response(request, "Not authenticated")
                token = auth_header.split(" ", 1)[1]
                await get_current_qqcc_config_user(token)
            except HTTPException as exc:
                return _build_auth_error_response(
                    request,
                    str(exc.detail or "Could not validate credentials"),
                )
            except JWTError:
                return _build_auth_error_response(
                    request,
                    "Could not validate credentials",
                )
            except Exception:
                logger.exception(
                    "Unexpected QQCC config auth middleware failure for path=%s",
                    request_path,
                )
                return _build_auth_error_response(
                    request,
                    "Could not validate credentials",
                )
    return await call_next(request)


@app.get("/api/health")
async def health_check(request: Request):
    health_state = getattr(request.app.state, "qqcc_config_health", {})
    database_ready = bool(health_state.get("database_ready"))
    startup_complete = bool(health_state.get("startup_complete"))
    payload = {
        "status": "ok" if database_ready and startup_complete else "degraded",
        "database_ready": database_ready,
        "startup_complete": startup_complete,
        "database_error": health_state.get("database_error"),
    }
    status_code = 200 if payload["status"] == "ok" else 503
    return fastapi.responses.JSONResponse(status_code=status_code, content=payload)


@app.get("/")
async def root():
    return {"message": "QQCC Config Backend is Running", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8045)
