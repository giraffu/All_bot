from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.private_qqcc_bot_owner_auth import (
    PrivateBotOwnerAuthError,
    decode_private_bot_owner_token,
    exchange_private_bot_owner_ticket,
)
from dashboard.backend.qqcc_config_auth import (
    TokenData,
    get_current_qqcc_config_user,
)
from src.database.core import get_db
from src.database.models import (
    PrivateQqccBot,
    PrivateQqccBotAuditLog,
    User,
)
from src.services.private_qqcc_bot_credentials import PrivateBotCredentialError
from src.services.private_qqcc_bot_management import (
    PrivateBotConfigMediaScopeError,
    PrivateBotConfigLimitError,
    PrivateBotConfigVersionConflict,
    build_private_bot_admin_summary,
    build_private_bot_audit_payload,
    build_private_bot_config_payload,
    update_private_bot_config_record,
)
from src.services.private_qqcc_bot_metrics import collect_private_qqcc_runtime_metrics
from src.services.private_qqcc_bot_service import (
    PrivateBotConflictError,
    PrivateBotNotFoundError,
    PrivateBotServiceError,
    PrivateBotValidationError,
)
from src.services.private_qqcc_bot_runtime import (
    build_private_qqcc_bot_lifecycle_service,
    private_bot_admission_lock,
)
from src.services.qqcc_demo_media_service import (
    QqccDemoMediaValidationError,
    build_qqcc_demo_preview_url,
    upload_qqcc_demo_media,
)
from src.services.qqcc_demo_generation_service import (
    QqccDemoGenerationError,
    get_qqcc_demo_generation,
    submit_qqcc_demo_generation,
)
from src.services.qqcc_video_scene_chain_service import QqccVideoSceneChainError
from src.services.qqcc_config_service import normalize_qqcc_config
from src.services.redis_client import redis_client

router = APIRouter(prefix="/api/private-bots", tags=["private-bots"])


class OwnerTicketExchangeRequest(BaseModel):
    ticket: SecretStr


class OwnerConfigUpdateRequest(BaseModel):
    config_version: int = Field(ge=1)
    config: dict[str, Any]


class OwnerCredentialUpdateRequest(BaseModel):
    token: SecretStr


class OwnerDemoGenerationRequest(BaseModel):
    scene: dict[str, Any]


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PrivateBotNotFoundError):
        status = 404
    elif isinstance(exc, PrivateBotConflictError):
        status = 409
    elif isinstance(exc, (PrivateBotValidationError, QqccDemoMediaValidationError)):
        status = 400
    elif isinstance(exc, PrivateBotCredentialError):
        status = 503
    elif isinstance(exc, PrivateBotServiceError):
        status = 503
    else:
        status = 500
    return HTTPException(
        status_code=status,
        detail={
            "code": getattr(exc, "code", "private_bot_error"),
            "message": str(exc),
        },
    )


async def get_current_private_bot_owner_id(
    authorization: str | None = Header(default=None),
) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return decode_private_bot_owner_token(authorization.split(" ", 1)[1])
    except PrivateBotOwnerAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def _load_owner_bot(
    db: AsyncSession,
    owner_user_id: int,
    *,
    for_update: bool = False,
) -> PrivateQqccBot:
    stmt = select(PrivateQqccBot).where(
        PrivateQqccBot.owner_user_id == owner_user_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    bot = result.scalar_one_or_none()
    if bot is None:
        raise HTTPException(status_code=404, detail="Private Bot was not found")
    return bot


@router.post("/owner/auth/exchange")
async def exchange_owner_ticket(payload: OwnerTicketExchangeRequest):
    try:
        return await exchange_private_bot_owner_ticket(
            ticket=payload.ticket.get_secret_value(),
            redis=redis_client.redis,
        )
    except PrivateBotOwnerAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/owner/me")
async def get_owner_private_bot(
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _load_owner_bot(db, owner_user_id)
    return build_private_bot_config_payload(bot)


@router.put("/owner/config")
async def update_owner_private_bot_config(
    payload: OwnerConfigUpdateRequest,
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _load_owner_bot(db, owner_user_id, for_update=True)
    before_status = bot.runtime_status
    try:
        update_private_bot_config_record(
            bot,
            expected_version=payload.config_version,
            raw_config=payload.config,
        )
    except PrivateBotConfigVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PrivateBotConfigMediaScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PrivateBotConfigLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except QqccVideoSceneChainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(
        PrivateQqccBotAuditLog(
            private_bot=bot,
            owner_user_id=bot.owner_user_id,
            telegram_bot_id=bot.telegram_bot_id,
            actor_type="owner",
            actor_identifier=str(owner_user_id),
            action="config_updated",
            before_status=before_status,
            after_status=bot.runtime_status,
            details={"config_version": bot.config_version},
        )
    )
    await db.commit()
    await db.refresh(bot)
    return build_private_bot_config_payload(bot)


@router.post("/owner/pause")
async def pause_owner_private_bot(
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        bot = await build_private_qqcc_bot_lifecycle_service(db).pause(owner_user_id=owner_user_id)
    except (PrivateBotServiceError, PrivateBotCredentialError) as exc:
        raise _service_error(exc) from exc
    return build_private_bot_config_payload(bot)


@router.post("/owner/resume")
async def resume_owner_private_bot(
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        bot = await build_private_qqcc_bot_lifecycle_service(db).resume(owner_user_id=owner_user_id)
    except (PrivateBotServiceError, PrivateBotCredentialError) as exc:
        raise _service_error(exc) from exc
    return build_private_bot_config_payload(bot)


@router.post("/owner/retry")
async def retry_owner_private_bot(
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        bot = await build_private_qqcc_bot_lifecycle_service(db).retry(owner_user_id=owner_user_id)
    except (PrivateBotServiceError, PrivateBotCredentialError) as exc:
        raise _service_error(exc) from exc
    return build_private_bot_config_payload(bot)


@router.put("/owner/credentials")
async def rotate_owner_private_bot_credentials(
    payload: OwnerCredentialUpdateRequest,
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await build_private_qqcc_bot_lifecycle_service(db).rotate_credentials(
            owner_user_id=owner_user_id,
            token=payload.token.get_secret_value(),
        )
    except (PrivateBotServiceError, PrivateBotCredentialError) as exc:
        raise _service_error(exc) from exc
    bot = await _load_owner_bot(db, owner_user_id)
    response = build_private_bot_config_payload(bot)
    response["provision"] = {
        "created": result.created,
        "runtime_status": result.runtime_status,
    }
    return response


@router.post("/owner/demo-media/{scene_kind}/{scene_id}/{slot}")
async def upload_owner_private_bot_demo_media(
    scene_kind: str,
    scene_id: str,
    slot: str,
    file: UploadFile = File(...),
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _load_owner_bot(db, owner_user_id)
    try:
        async with private_bot_admission_lock(int(bot.id)):
            bot = await _load_owner_bot(db, owner_user_id)
            if not bot.admin_enabled:
                raise HTTPException(
                    status_code=409,
                    detail="Private Bot is disabled by an administrator",
                )
            media = await upload_qqcc_demo_media(
                scene_kind=scene_kind,
                scene_id=scene_id,
                slot=slot,
                upload=file,
                object_prefix=f"qqcc/private/{bot.id}/demo",
            )
    except QqccDemoMediaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PrivateBotServiceError as exc:
        raise _service_error(exc) from exc
    return {"media": media, "preview_url": build_qqcc_demo_preview_url(media)}


@router.post("/owner/demo-generation/{scene_kind}")
async def submit_owner_private_bot_demo_generation(
    scene_kind: str,
    payload: OwnerDemoGenerationRequest,
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _load_owner_bot(db, owner_user_id)
    if not bot.admin_enabled:
        raise HTTPException(status_code=409, detail="Private Bot is disabled by an administrator")
    try:
        return await submit_qqcc_demo_generation(
            scene_kind=scene_kind,
            scene=payload.scene,
            object_prefix=f"qqcc/private/{bot.id}/demo",
            config=normalize_qqcc_config(bot.config or {}),
        )
    except QqccDemoGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Demo generation unavailable") from exc


@router.get("/owner/demo-generation/{scene_kind}/{scene_id}/{generation_id}")
async def get_owner_private_bot_demo_generation(
    scene_kind: str,
    scene_id: str,
    generation_id: str,
    owner_user_id: int = Depends(get_current_private_bot_owner_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _load_owner_bot(db, owner_user_id)
    try:
        return await get_qqcc_demo_generation(
            scene_kind=scene_kind,
            scene_id=scene_id,
            generation_id=generation_id,
            object_prefix=f"qqcc/private/{bot.id}/demo",
        )
    except QqccDemoGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Demo generation unavailable") from exc


@router.get("/admin")
async def list_private_bots_for_admin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    runtime_status: str | None = Query(default=None),
    status: str | None = Query(default=None),
    admin_enabled: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    owner: str | None = Query(default=None, max_length=100),
    username: str | None = Query(default=None, max_length=64),
    _admin: TokenData = Depends(get_current_qqcc_config_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    selected_status = (status or runtime_status or "").strip()
    if selected_status:
        filters.append(PrivateQqccBot.runtime_status == selected_status)
    if admin_enabled is not None:
        filters.append(PrivateQqccBot.admin_enabled.is_(admin_enabled))
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        filters.append(
            or_(
                PrivateQqccBot.telegram_username.ilike(pattern),
                User.username.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )
    normalized_owner = (owner or "").strip()
    if normalized_owner:
        owner_pattern = f"%{normalized_owner}%"
        owner_filters = [
            User.username.ilike(owner_pattern),
            User.full_name.ilike(owner_pattern),
        ]
        if normalized_owner.isdigit():
            numeric_owner = int(normalized_owner)
            owner_filters.extend(
                [
                    User.id == numeric_owner,
                    User.telegram_id == numeric_owner,
                ]
            )
        filters.append(or_(*owner_filters))
    normalized_username = (username or "").strip().lstrip("@")
    if normalized_username:
        filters.append(
            PrivateQqccBot.telegram_username.ilike(f"%{normalized_username}%")
        )
    count_result = await db.execute(
        select(func.count(PrivateQqccBot.id))
        .join(User, User.id == PrivateQqccBot.owner_user_id)
        .where(*filters)
    )
    total = int(count_result.scalar() or 0)
    result = await db.execute(
        select(PrivateQqccBot, User)
        .join(User, User.id == PrivateQqccBot.owner_user_id)
        .where(*filters)
        .order_by(PrivateQqccBot.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            build_private_bot_admin_summary(bot, owner)
            for bot, owner in result.all()
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/admin/metrics")
async def get_private_bot_runtime_metrics_for_admin(
    _admin: TokenData = Depends(get_current_qqcc_config_user),
):
    return await collect_private_qqcc_runtime_metrics(redis_client.redis)


async def _load_admin_bot(db: AsyncSession, private_bot_id: int):
    result = await db.execute(
        select(PrivateQqccBot, User)
        .join(User, User.id == PrivateQqccBot.owner_user_id)
        .where(PrivateQqccBot.id == private_bot_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Private Bot was not found")
    return row


@router.get("/admin/{private_bot_id}")
async def get_private_bot_admin_detail(
    private_bot_id: int,
    _admin: TokenData = Depends(get_current_qqcc_config_user),
    db: AsyncSession = Depends(get_db),
):
    bot, owner = await _load_admin_bot(db, private_bot_id)
    audit_result = await db.execute(
        select(PrivateQqccBotAuditLog)
        .where(PrivateQqccBotAuditLog.private_bot_id == bot.id)
        .order_by(PrivateQqccBotAuditLog.created_at.desc())
        .limit(100)
    )
    payload = build_private_bot_admin_summary(bot, owner)
    owner_payload = build_private_bot_config_payload(bot)
    payload.update(
        {
            "config": owner_payload["config"],
            "config_version": owner_payload["config_version"],
            "options": owner_payload["options"],
            "audit_logs": [
                build_private_bot_audit_payload(item)
                for item in audit_result.scalars().all()
            ],
        }
    )
    return payload


async def _set_admin_enabled(
    *,
    private_bot_id: int,
    enabled: bool,
    admin: TokenData,
    db: AsyncSession,
):
    bot, _owner = await _load_admin_bot(db, private_bot_id)
    try:
        updated = await build_private_qqcc_bot_lifecycle_service(db).set_admin_enabled(
            owner_user_id=int(bot.owner_user_id),
            enabled=enabled,
            admin_identifier=str(admin.username or "admin"),
            expected_private_bot_id=private_bot_id,
        )
    except (PrivateBotServiceError, PrivateBotCredentialError) as exc:
        raise _service_error(exc) from exc
    return build_private_bot_config_payload(updated)


@router.post("/admin/{private_bot_id}/disable")
async def disable_private_bot_for_admin(
    private_bot_id: int,
    admin: TokenData = Depends(get_current_qqcc_config_user),
    db: AsyncSession = Depends(get_db),
):
    return await _set_admin_enabled(
        private_bot_id=private_bot_id,
        enabled=False,
        admin=admin,
        db=db,
    )


@router.post("/admin/{private_bot_id}/enable")
async def enable_private_bot_for_admin(
    private_bot_id: int,
    admin: TokenData = Depends(get_current_qqcc_config_user),
    db: AsyncSession = Depends(get_db),
):
    return await _set_admin_enabled(
        private_bot_id=private_bot_id,
        enabled=True,
        admin=admin,
        db=db,
    )


@router.delete("/admin/{private_bot_id}")
async def delete_private_bot_for_admin(
    private_bot_id: int,
    admin: TokenData = Depends(get_current_qqcc_config_user),
    db: AsyncSession = Depends(get_db),
):
    bot, _owner = await _load_admin_bot(db, private_bot_id)
    try:
        await build_private_qqcc_bot_lifecycle_service(db).delete_binding(
            owner_user_id=int(bot.owner_user_id),
            admin_identifier=str(admin.username or "admin"),
            expected_private_bot_id=private_bot_id,
        )
    except (PrivateBotServiceError, PrivateBotCredentialError) as exc:
        raise _service_error(exc) from exc
    return {"status": "deleted", "private_bot_id": private_bot_id}
