import sys
import os
import asyncio
from pathlib import Path
import logging

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import fastapi.responses

from src.database.core import init_db
from dashboard.backend.auth import auth_router, get_current_user
from dashboard.backend.routers import stats, users, history, plans, templates, system, logs, workers, gallery, referrals
from dashboard.backend.services.worker_listener import start_worker_listener

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

app = FastAPI(title="TeleBot Dashboard API")

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(stats.router)
app.include_router(users.router)
app.include_router(history.router)
app.include_router(plans.router)
app.include_router(templates.router)
app.include_router(system.router)
app.include_router(logs.router)
app.include_router(workers.router)
app.include_router(gallery.router)
app.include_router(referrals.router)

background_tasks = set()

@app.on_event("startup")
async def startup_event():
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    
    # Start background worker listener and keep a strong reference
    task = asyncio.create_task(start_worker_listener())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def check_auth_header(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        public_paths = ["/api/auth/login", "/api/health", "/api/status"]
        if request.url.path not in public_paths:
            try:
                auth_header = request.headers.get("Authorization")
                if not auth_header or not auth_header.startswith("Bearer "):
                    return fastapi.responses.JSONResponse(
                        status_code=401,
                        content={"detail": "Not authenticated"}
                    )
                token = auth_header.split(" ")[1]
                await get_current_user(token)
            except Exception:
                return fastapi.responses.JSONResponse(
                    status_code=401,
                    content={"detail": "Could not validate credentials"}
                )
    return await call_next(request)

@app.get("/")
async def root():
    return {"message": "TeleBot Dashboard Backend is Running", "status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8043)
