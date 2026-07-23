from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .api import router
from .config import get_settings
from .database import SessionLocal, create_schema_for_local, engine
from .models import User, UserRole
from .security import hash_password
from .storage import S3Storage, get_storage


settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await create_schema_for_local()
    storage = get_storage()
    if isinstance(storage, S3Storage):
        await storage.ensure_bucket()
    if settings.admin_email and settings.admin_password:
        async with SessionLocal() as db:
            email = settings.admin_email.strip().lower()
            admin = await db.scalar(select(User).where(User.email == email))
            if admin is None:
                db.add(
                    User(
                        email=email,
                        password_hash=hash_password(settings.admin_password),
                        role=UserRole.ADMIN,
                    )
                )
                await db.commit()
    yield
    await engine.dispose()


app = FastAPI(
    title="Clarity AI Media Enhancement API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "clarity-api"}
