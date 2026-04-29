import logging
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.database.core import engine
from src.web_api.routers import auth, gallery, storage, tasks, users, utils

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    # Startup: setup resources if needed
    logger.info("Web BFF API is starting up...")
    yield
    # Shutdown: cleanup resources
    logger.info("Web BFF API is shutting down...")
    await engine.dispose()

app = FastAPI(
    title="All_bot Web BFF API",
    description="Backend for Frontend serving the Vue3 App",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://web.aivison.it.com",
        "http://localhost:8085",
        "http://localhost:5173"
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Trace-ID")

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(gallery.router, prefix="/api/gallery", tags=["Gallery"])
app.include_router(utils.router, prefix="/api/utils", tags=["Utils"])

@app.get("/api/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "Web BFF is running"}
