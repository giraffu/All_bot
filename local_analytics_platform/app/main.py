from __future__ import annotations

import subprocess as subprocess  # noqa: F401
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .analytics_common import (
    ALL_TIME_QUERY_DAYS,
    GENERATION_OPERATION_TYPES,
    PROMPT_NORMALIZATION_VERSION,
    PROMPT_VECTOR_RESUME_LOG,
    RMB_TO_USDT,
    STATIC_DIR,
    STARS_TO_USDT,
    TON_TO_USDT,
    _builtin_prompt_templates,
    _database_url,
    _execute,
    _fetch,
    _fetchrow,
    _is_prompt_vector_refresh_lock_held,
    _normalize_prompt_text,
    close_pool,
)
from .auth import install_auth
from .routes_credit_flow import router as credit_flow_router
from .routes_finance import router as finance_router
from .routes_generation import router as generation_router
from .routes_generation_history import router as generation_history_router
from .routes_health import router as health_router
from .routes_media import router as media_router
from .routes_overview import router as overview_router
from .routes_prompts import router as prompts_router
from .routes_users import router as users_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(title="AllBot Local Analytics", version="0.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
install_auth(app, static_dir=STATIC_DIR)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


for router in (
    health_router,
    users_router,
    credit_flow_router,
    overview_router,
    finance_router,
    generation_router,
    generation_history_router,
    prompts_router,
    media_router,
):
    app.include_router(router)


__all__ = [
    "ALL_TIME_QUERY_DAYS",
    "GENERATION_OPERATION_TYPES",
    "PROMPT_NORMALIZATION_VERSION",
    "PROMPT_VECTOR_RESUME_LOG",
    "RMB_TO_USDT",
    "STARS_TO_USDT",
    "TON_TO_USDT",
    "_builtin_prompt_templates",
    "_database_url",
    "_execute",
    "_fetch",
    "_fetchrow",
    "_is_prompt_vector_refresh_lock_held",
    "_normalize_prompt_text",
    "app",
    "index",
    "lifespan",
    "subprocess",
]
