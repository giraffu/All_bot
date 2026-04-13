import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.web_api.routers import auth, storage, tasks, users
from src.database.core import engine

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
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
# Allows requests from any origin for development. Must be restricted in production!
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])

@app.get("/api/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "Web BFF is running"}
