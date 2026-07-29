import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from sqlalchemy import text

from config import MINIO_BUCKET
from src.database.core import engine
from src.database.models import User
from src.services.redis_client import redis_client
from src.services.storage import storage
from src.web_api.dependencies import get_current_user, get_db
from src.web_api.routers import storage as storage_router
from src.web_api.schemas.auth_schema import UserLoginRequest, UserResponse
from src.web_api.schemas.character_schema import (
    CharacterBuildRequest,
    CharacterResponse,
)
from src.web_api.services.auth_api_service import login_with_password_payload
from src.web_api.services.character_reference_service import (
    create_character_draft,
    list_characters,
)
from src.web_api.services.user_task_api_service import get_current_user_profile_payload

from .schemas import (
    FixtureBuildResponse,
    MiniCharacterResponse,
    ModelAssetResponse,
    RenderCreateRequest,
    RenderJobResponse,
)
from .service import (
    cancel_render_job,
    create_fixture_build,
    create_render_job,
    get_owned_asset,
    get_owned_render_job,
    list_mini_characters,
    serialize_asset,
    serialize_render_job,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await redis_client.close()
    await engine.dispose()


app = FastAPI(
    title="AllBot Avatar Mini App API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/api/auth/login")
async def login(req: UserLoginRequest, request: Request):
    return await login_with_password_payload(req=req, request=request)


@app.get("/api/users/me", response_model=UserResponse)
async def current_user_profile(
    current_user: User = Depends(get_current_user),
):
    return await get_current_user_profile_payload(current_user)


app.include_router(storage_router.router, prefix="/api/storage", tags=["Storage"])


@app.get("/api/characters", response_model=list[CharacterResponse])
async def characters(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await list_characters(db=db, user_id=current_user.id)


@app.post("/api/characters/drafts", response_model=CharacterResponse)
async def character_draft(
    payload: CharacterBuildRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await create_character_draft(
        db=db,
        current_user=current_user,
        payload=payload,
    )


@app.get("/api/miniapp/characters", response_model=list[MiniCharacterResponse])
async def mini_characters(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await list_mini_characters(db=db, user_id=current_user.id)


@app.post(
    "/api/miniapp/characters/{character_id}/fixture-build",
    response_model=FixtureBuildResponse,
)
async def fixture_build(
    character_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await create_fixture_build(
        db=db,
        user_id=current_user.id,
        character_id=character_id,
    )


@app.get(
    "/api/miniapp/model-assets/{asset_id}",
    response_model=ModelAssetResponse,
)
async def model_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    asset = await get_owned_asset(db=db, user_id=current_user.id, asset_id=asset_id)
    return serialize_asset(asset)


@app.post("/api/miniapp/renders", response_model=RenderJobResponse)
async def render_create(
    payload: RenderCreateRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await create_render_job(db=db, user_id=current_user.id, payload=payload)


@app.get("/api/miniapp/renders/{render_id}", response_model=RenderJobResponse)
async def render_status(
    render_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = await get_owned_render_job(
        db=db,
        user_id=current_user.id,
        render_id=render_id,
    )
    return serialize_render_job(job)


@app.post(
    "/api/miniapp/renders/{render_id}/cancel",
    response_model=RenderJobResponse,
)
async def render_cancel(
    render_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await cancel_render_job(
        db=db,
        user_id=current_user.id,
        render_id=render_id,
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "avatar-miniapp-api"}


@app.get("/api/ready")
async def ready(db=Depends(get_db)):
    await db.execute(text("SELECT 1"))
    await redis_client.redis.ping()
    if storage.client is None or not await asyncio.to_thread(
        storage.client.bucket_exists,
        MINIO_BUCKET,
    ):
        raise RuntimeError("OBJECT_STORAGE_UNAVAILABLE")
    return {"status": "ready"}
