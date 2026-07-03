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
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError

from dashboard.backend.qqcc_config_auth import (
    auth_router,
    get_current_qqcc_config_user,
)
from dashboard.backend.routers import qqcc
from src.database.core import init_db

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        public_paths = {"/api/auth/login", "/api/health"}
        if request.url.path not in public_paths:
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
                    request.url.path,
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
