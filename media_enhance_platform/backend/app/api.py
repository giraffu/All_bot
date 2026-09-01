from __future__ import annotations

import asyncio
import json
import mimetypes
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import get_settings
from .database import get_db
from .models import (
    CreditEntry,
    MediaFile,
    MediaKind,
    RefreshToken,
    SmsVerificationChallenge,
    Task,
    TaskAttempt,
    TaskStatus,
    Ticket,
    TicketKind,
    TicketStatus,
    User,
    Worker,
    utcnow,
)
from .pricing import public_catalog
from .schemas import (
    AdminAdjustmentRequest,
    AdminRefundRequest,
    AdminTicketUpdateRequest,
    AuthResponse,
    CopyrightCreateRequest,
    LoginRequest,
    MediaView,
    PhoneSendRequest,
    PhoneSendResponse,
    PhoneVerifyRequest,
    RegisterRequest,
    TaskCreateRequest,
    TaskView,
    TicketCreateRequest,
    TicketView,
    UserView,
    WorkerClaimRequest,
    WorkerFailureRequest,
    WorkerHeartbeatRequest,
    WorkerProgressRequest,
    WorkerProviderBindingRequest,
)
from .security import (
    create_access_token,
    get_current_user,
    get_optional_user,
    hash_password,
    new_refresh_token,
    refresh_hash,
    require_admin,
    require_agent,
    verify_password,
)
from .sms_verification import (
    SmsProviderError,
    SmsVerificationProvider,
    get_sms_provider,
    mask_phone,
    normalize_mainland_phone,
    phone_digest,
)
from .services import (
    ACTIVE_STATUSES,
    add_audit,
    apply_credit_entry,
    capture_reservation,
    create_task,
    release_reservation,
    task_view,
)
from .storage import get_storage


settings = get_settings()
router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "clarity_refresh",
        token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        max_age=settings.refresh_token_days * 86400,
        path="/api/auth",
    )


async def issue_auth(db: AsyncSession, user: User, response: Response) -> AuthResponse:
    raw, token_hash = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_days),
        )
    )
    await db.commit()
    set_refresh_cookie(response, raw)
    return AuthResponse(access_token=create_access_token(user), user=UserView.model_validate(user))


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    if not payload.accepted_terms:
        raise HTTPException(status_code=422, detail="terms_required")
    email = normalize_email(str(payload.email))
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="email_exists")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        available_points=settings.welcome_points,
    )
    db.add(user)
    await db.flush()
    db.add(
        CreditEntry(
            user_id=user.id,
            kind="welcome",
            available_delta=settings.welcome_points,
            reserved_delta=0,
            idempotency_key=f"welcome:{user.id}",
        )
    )
    return await issue_auth(db, user, response)


@router.post("/auth/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await db.scalar(
        select(User).where(User.email == normalize_email(str(payload.email)))
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    return await issue_auth(db, user, response)


@router.post("/auth/refresh", response_model=AuthResponse)
async def refresh(
    response: Response,
    clarity_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    if not clarity_refresh:
        raise HTTPException(status_code=401, detail="refresh_missing")
    record = await db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == refresh_hash(clarity_refresh)
        )
    )
    now = datetime.now(timezone.utc)
    if (
        record is None
        or record.revoked_at is not None
        or record.expires_at.replace(tzinfo=timezone.utc) <= now
    ):
        raise HTTPException(status_code=401, detail="refresh_invalid")
    record.revoked_at = now
    user = await db.get(User, record.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="refresh_invalid")
    return await issue_auth(db, user, response)


@router.post("/auth/logout")
async def logout(
    response: Response,
    clarity_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if clarity_refresh:
        record = await db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == refresh_hash(clarity_refresh)
            )
        )
        if record and record.revoked_at is None:
            record.revoked_at = utcnow()
            await db.commit()
    response.delete_cookie("clarity_refresh", path="/api/auth")
    return {"logged_out": True}


@router.get("/auth/me", response_model=UserView)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


def _normalize_phone_or_422(phone_number: str) -> str:
    try:
        return normalize_mainland_phone(phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid_phone_number") from exc


def _request_audit_details(request: Request) -> dict:
    client = request.client
    return {
        "peer_ip": client.host if client else None,
        "peer_port": client.port if client else None,
        "forwarded_for": request.headers.get("x-forwarded-for", "")[:500],
        "destination_host": (request.url.hostname or "")[:255],
        "destination_port": request.url.port,
        "user_agent": request.headers.get("user-agent", "")[:500],
        "path": request.url.path,
    }


async def require_verified_phone(
    user: User = Depends(get_current_user),
) -> User:
    if not user.phone_verified:
        raise HTTPException(status_code=403, detail="phone_verification_required")
    return user


@router.post(
    "/auth/phone/send", response_model=PhoneSendResponse, status_code=202
)
async def send_phone_verification(
    payload: PhoneSendRequest,
    request: Request,
    user: User = Depends(get_current_user),
    provider: SmsVerificationProvider = Depends(get_sms_provider),
    db: AsyncSession = Depends(get_db),
) -> PhoneSendResponse:
    if user.phone_verified:
        raise HTTPException(status_code=409, detail="phone_already_verified")
    phone_number = _normalize_phone_or_422(payload.phone_number)
    digest = phone_digest(phone_number)
    existing_owner = await db.scalar(
        select(User.id).where(User.phone_hash == digest, User.id != user.id)
    )
    if existing_owner:
        raise HTTPException(status_code=409, detail="phone_already_bound")

    now = utcnow()
    cooldown_cutoff = now - timedelta(seconds=settings.sms_send_cooldown_seconds)
    latest = await db.scalar(
        select(SmsVerificationChallenge)
        .where(
            or_(
                SmsVerificationChallenge.user_id == user.id,
                SmsVerificationChallenge.phone_hash == digest,
            ),
            SmsVerificationChallenge.created_at >= cooldown_cutoff,
        )
        .order_by(SmsVerificationChallenge.created_at.desc())
    )
    if latest:
        raise HTTPException(
            status_code=429,
            detail="sms_send_too_frequent",
            headers={"Retry-After": str(settings.sms_send_cooldown_seconds)},
        )

    daily_cutoff = now - timedelta(days=1)
    daily_count = await db.scalar(
        select(func.count())
        .select_from(SmsVerificationChallenge)
        .where(
            or_(
                SmsVerificationChallenge.user_id == user.id,
                SmsVerificationChallenge.phone_hash == digest,
            ),
            SmsVerificationChallenge.created_at >= daily_cutoff,
        )
    )
    if (daily_count or 0) >= settings.sms_daily_send_limit:
        raise HTTPException(status_code=429, detail="sms_daily_limit_reached")

    challenge = SmsVerificationChallenge(
        id=str(uuid.uuid4()),
        user_id=user.id,
        phone_hash=digest,
        phone_masked=mask_phone(phone_number),
        expires_at=now + timedelta(seconds=settings.sms_challenge_seconds),
    )
    try:
        challenge.provider_reference = await provider.send_code(
            phone_number, challenge.id
        )
    except SmsProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.add(challenge)
    add_audit(
        db,
        actor_id=user.id,
        action="phone_verification_sent",
        target_type="sms_challenge",
        target_id=challenge.id,
        details={
            "phone_masked": challenge.phone_masked,
            **_request_audit_details(request),
        },
    )
    await db.commit()
    return PhoneSendResponse(
        challenge_id=challenge.id,
        expires_in=settings.sms_challenge_seconds,
        resend_after=settings.sms_send_cooldown_seconds,
    )


@router.post("/auth/phone/verify", response_model=UserView)
async def verify_phone_number(
    payload: PhoneVerifyRequest,
    request: Request,
    user: User = Depends(get_current_user),
    provider: SmsVerificationProvider = Depends(get_sms_provider),
    db: AsyncSession = Depends(get_db),
) -> User:
    if user.phone_verified:
        raise HTTPException(status_code=409, detail="phone_already_verified")
    phone_number = _normalize_phone_or_422(payload.phone_number)
    digest = phone_digest(phone_number)
    challenge = await db.scalar(
        select(SmsVerificationChallenge)
        .where(
            SmsVerificationChallenge.id == payload.challenge_id,
            SmsVerificationChallenge.user_id == user.id,
        )
        .with_for_update()
    )
    if challenge is None or challenge.phone_hash != digest:
        raise HTTPException(status_code=404, detail="sms_challenge_not_found")
    if challenge.consumed_at is not None:
        raise HTTPException(status_code=409, detail="sms_challenge_consumed")
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= utcnow():
        raise HTTPException(status_code=410, detail="sms_challenge_expired")
    if challenge.verify_attempts >= settings.sms_max_verify_attempts:
        raise HTTPException(status_code=429, detail="sms_verify_attempts_exceeded")

    challenge.verify_attempts += 1
    try:
        passed = await provider.check_code(
            phone_number, payload.verify_code, challenge.id
        )
    except SmsProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not passed:
        add_audit(
            db,
            actor_id=user.id,
            action="phone_verification_failed",
            target_type="sms_challenge",
            target_id=challenge.id,
            details={"attempt": challenge.verify_attempts, **_request_audit_details(request)},
        )
        await db.commit()
        raise HTTPException(status_code=422, detail="invalid_verify_code")

    existing_owner = await db.scalar(
        select(User.id).where(User.phone_hash == digest, User.id != user.id)
    )
    if existing_owner:
        raise HTTPException(status_code=409, detail="phone_already_bound")
    now = utcnow()
    user.phone_hash = digest
    user.phone_masked = challenge.phone_masked
    user.phone_verified_at = now
    challenge.consumed_at = now
    add_audit(
        db,
        actor_id=user.id,
        action="phone_verified",
        target_type="user",
        target_id=user.id,
        details={
            "phone_masked": challenge.phone_masked,
            "challenge_id": challenge.id,
            **_request_audit_details(request),
        },
    )
    await db.commit()
    return user


@router.get("/catalog")
async def catalog() -> dict:
    return public_catalog()


def _extension_for(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
    }.get(mime_type, mimetypes.guess_extension(mime_type) or ".bin")


def _probe_image(path: Path) -> tuple[str, int, int]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            detected = Image.MIME.get(image.format or "")
            if detected not in {"image/jpeg", "image/png", "image/webp"}:
                raise HTTPException(status_code=415, detail="unsupported_image")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 100_000_000:
                raise HTTPException(status_code=422, detail="invalid_image_dimensions")
            return detected, width, height
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail="invalid_image") from exc


def _probe_video(path: Path) -> tuple[str, float, int | None, int | None]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=format_name,duration:stream=codec_type,width,height",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=30
        )
        data = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=415, detail="invalid_video") from exc
    formats = set(str(data.get("format", {}).get("format_name", "")).split(","))
    mime = (
        "video/webm"
        if "webm" in formats
        else "video/quicktime"
        if "mov" in formats and "mp4" not in formats
        else "video/mp4"
    )
    if not formats.intersection({"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "webm", "matroska"}):
        raise HTTPException(status_code=415, detail="unsupported_video")
    duration = float(data.get("format", {}).get("duration") or 0)
    stream = next(
        (item for item in data.get("streams", []) if item.get("codec_type") == "video"),
        {},
    )
    if duration <= 0 or duration > settings.max_video_seconds or not stream:
        raise HTTPException(status_code=422, detail="invalid_video_duration")
    return mime, duration, stream.get("width"), stream.get("height")


async def _save_upload(
    file: UploadFile,
    user: User,
    db: AsyncSession,
    *,
    is_output: bool = False,
    forced_kind: MediaKind | None = None,
) -> MediaFile:
    declared = (file.content_type or "").lower()
    is_image = declared.startswith("image/")
    is_video = declared.startswith("video/")
    if not (is_image or is_video):
        raise HTTPException(status_code=415, detail="unsupported_media")
    limit = settings.max_image_bytes if is_image else settings.max_video_bytes
    size = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temporary:
            temp_path = Path(temporary.name)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="file_too_large")
                temporary.write(chunk)
        if is_image:
            detected, width, height = await asyncio.to_thread(_probe_image, temp_path)
            media_kind = MediaKind.IMAGE
            duration = None
        else:
            detected, duration, width, height = await asyncio.to_thread(
                _probe_video, temp_path
            )
            media_kind = MediaKind.VIDEO
        if forced_kind and media_kind != forced_kind:
            raise HTTPException(status_code=422, detail="media_kind_mismatch")
        object_key = (
            f"users/{user.id}/{'outputs' if is_output else 'sources'}/"
            f"{uuid.uuid4()}{_extension_for(detected)}"
        )
        await get_storage().put_file(object_key, temp_path, detected)
        media = MediaFile(
            owner_id=user.id,
            object_key=object_key,
            original_name=Path(file.filename or "media").name[:255],
            mime_type=detected,
            media_kind=media_kind,
            size_bytes=size,
            duration_seconds=duration,
            width=width,
            height=height,
            is_output=is_output,
        )
        db.add(media)
        await db.flush()
        return media
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


@router.post("/uploads", response_model=MediaView, status_code=201)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_verified_phone),
    db: AsyncSession = Depends(get_db),
) -> MediaFile:
    media = await _save_upload(file, user, db)
    add_audit(
        db,
        actor_id=user.id,
        action="media_uploaded",
        target_type="media_file",
        target_id=media.id,
        details={
            "mime_type": media.mime_type,
            "size_bytes": media.size_bytes,
            "media_kind": media.media_kind.value,
            **_request_audit_details(request),
        },
    )
    await db.commit()
    return media


@router.get("/uploads", response_model=list[MediaView])
async def list_uploads(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MediaFile]:
    return list(
        (
            await db.scalars(
                select(MediaFile)
                .where(MediaFile.owner_id == user.id)
                .order_by(MediaFile.created_at.desc())
            )
        ).all()
    )


async def _get_owned_media(
    file_id: str, user: User, db: AsyncSession, *, admin: bool = False
) -> MediaFile:
    media = await db.get(MediaFile, file_id)
    if media is None or (not admin and media.owner_id != user.id):
        raise HTTPException(status_code=404, detail="file_not_found")
    return media


@router.get("/uploads/{file_id}/download")
async def download_media(
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    media = await _get_owned_media(file_id, user, db)
    if media.deleted_at:
        raise HTTPException(status_code=410, detail="file_deleted")
    data = await get_storage().open_bytes(media.object_key)
    return StreamingResponse(
        iter([data]),
        media_type=media.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{media.original_name}"'},
    )


async def _delete_media(
    media: MediaFile, actor: User, db: AsyncSession
) -> None:
    if media.deleted_at:
        return
    active = await db.scalar(
        select(Task.id).where(
            (Task.source_file_id == media.id) | (Task.output_file_id == media.id),
            Task.status.in_(list(ACTIVE_STATUSES | {TaskStatus.QUEUED})),
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="file_used_by_active_task")
    await get_storage().delete(media.object_key)
    media.deleted_at = utcnow()
    add_audit(
        db,
        actor_id=actor.id,
        action="file_deleted",
        target_type="media_file",
        target_id=media.id,
        details={"size_bytes": media.size_bytes, "is_output": media.is_output},
    )


@router.delete("/uploads/{file_id}")
async def delete_media(
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    media = await _get_owned_media(file_id, user, db)
    await _delete_media(media, user, db)
    await db.commit()
    return {"deleted": True}


@router.post("/tasks", response_model=TaskView, status_code=201)
async def submit_task(
    payload: TaskCreateRequest,
    user: User = Depends(require_verified_phone),
    db: AsyncSession = Depends(get_db),
) -> TaskView:
    task = await create_task(
        db,
        user_id=user.id,
        source_file_id=payload.source_file_id,
        task_type=payload.task_type,
        multiplier=payload.multiplier,
    )
    await db.commit()
    return await task_view(db, task)


@router.get("/tasks", response_model=list[TaskView])
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TaskView]:
    tasks = list(
        (
            await db.scalars(
                select(Task)
                .where(Task.user_id == user.id)
                .options(selectinload(Task.attempts))
                .order_by(Task.created_at.desc())
            )
        ).all()
    )
    return [await task_view(db, task) for task in tasks]


@router.get("/tasks/{task_id}", response_model=TaskView)
async def get_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskView:
    task = await db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.user_id == user.id)
        .options(selectinload(Task.attempts))
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return await task_view(db, task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskView)
async def cancel_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskView:
    task = await db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.user_id == user.id)
        .with_for_update()
        .options(selectinload(Task.attempts))
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.status not in (
        {TaskStatus.QUEUED, TaskStatus.CLAIMED} | ACTIVE_STATUSES
    ):
        raise HTTPException(status_code=409, detail="task_not_cancellable")
    await release_reservation(db, task, reason="user_cancel")
    task.status = TaskStatus.CANCELED
    task.status_reason = "user_cancel"
    if task.attempts:
        task.attempts[-1].status = TaskStatus.CANCELED
    await db.commit()
    return await task_view(db, task)


@router.post("/tickets", response_model=TicketView, status_code=201)
async def create_support_ticket(
    payload: TicketCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Ticket:
    if payload.task_id:
        owner = await db.scalar(
            select(Task.id).where(Task.id == payload.task_id, Task.user_id == user.id)
        )
        if not owner:
            raise HTTPException(status_code=404, detail="task_not_found")
    ticket = Ticket(
        user_id=user.id,
        task_id=payload.task_id,
        kind=TicketKind.SUPPORT,
        email=user.email,
        subject=payload.subject,
        content=payload.content,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/tickets", response_model=list[TicketView])
async def list_tickets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Ticket]:
    return list(
        (
            await db.scalars(
                select(Ticket)
                .where(Ticket.user_id == user.id)
                .order_by(Ticket.created_at.desc())
            )
        ).all()
    )


@router.post(
    "/legal/copyright-complaints", response_model=TicketView, status_code=201
)
async def create_copyright_complaint(
    payload: CopyrightCreateRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> Ticket:
    ticket = Ticket(
        user_id=user.id if user else None,
        task_id=payload.task_id,
        kind=TicketKind.COPYRIGHT,
        email=normalize_email(str(payload.email)),
        subject=payload.subject,
        content=payload.content,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


# Admin API
@router.get("/admin/summary")
async def admin_summary(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    counts = {}
    for status in TaskStatus:
        counts[status.value] = (
            await db.scalar(
                select(func.count()).select_from(Task).where(Task.status == status)
            )
            or 0
        )
    return {
        "tasks": counts,
        "open_tickets": await db.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.status != TicketStatus.RESOLVED)
        )
        or 0,
        "users": await db.scalar(select(func.count()).select_from(User)) or 0,
    }


@router.get("/admin/users", response_model=list[UserView])
async def admin_users(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    return list(
        (await db.scalars(select(User).order_by(User.created_at.desc()))).all()
    )


@router.get("/admin/tasks", response_model=list[TaskView])
async def admin_tasks(
    status: TaskStatus | None = None,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TaskView]:
    statement = select(Task).options(selectinload(Task.attempts)).order_by(
        Task.created_at.desc()
    )
    if status:
        statement = statement.where(Task.status == status)
    tasks = list((await db.scalars(statement)).all())
    return [await task_view(db, task) for task in tasks]


@router.post("/admin/tasks/{task_id}/retry", response_model=TaskView)
async def admin_retry_task(
    task_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> TaskView:
    task = await db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .options(selectinload(Task.attempts))
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=409, detail="task_not_failed")
    user = await db.scalar(
        select(User).where(User.id == task.user_id).with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    number = max((item.attempt_number for item in task.attempts), default=0) + 1
    await apply_credit_entry(
        db,
        user=user,
        task_id=task.id,
        kind="task_reserve",
        available_delta=-task.cost_points,
        reserved_delta=task.cost_points,
        idempotency_key=f"task_reserve:{task.id}:{number}",
    )
    attempt = TaskAttempt(task_id=task.id, attempt_number=number)
    db.add(attempt)
    await db.flush()
    task.current_attempt_id = attempt.id
    task.status = TaskStatus.QUEUED
    task.status_reason = "no_worker_online"
    task.error_code = None
    task.error_detail = None
    task.progress = 0
    add_audit(
        db,
        actor_id=admin.id,
        action="task_retried",
        target_type="task",
        target_id=task.id,
        details={"attempt_number": number},
    )
    await db.commit()
    await db.refresh(task, attribute_names=["attempts"])
    return await task_view(db, task)


@router.post("/admin/points/adjust", response_model=UserView)
async def admin_adjust_points(
    payload: AdminAdjustmentRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.scalar(
        select(User).where(User.id == payload.user_id).with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    await apply_credit_entry(
        db,
        user=user,
        kind="admin_adjustment",
        available_delta=payload.points,
        reserved_delta=0,
        idempotency_key=payload.idempotency_key,
        details={"reason": payload.reason, "admin_id": admin.id},
    )
    add_audit(
        db,
        actor_id=admin.id,
        action="points_adjusted",
        target_type="user",
        target_id=user.id,
        details={"points": payload.points, "reason": payload.reason},
    )
    await db.commit()
    return user


@router.post("/admin/tasks/{task_id}/refund", response_model=TaskView)
async def admin_refund(
    task_id: str,
    payload: AdminRefundRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> TaskView:
    task = await db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .options(selectinload(Task.attempts))
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    existing_refund = await db.scalar(
        select(CreditEntry).where(
            CreditEntry.idempotency_key == payload.idempotency_key
        )
    )
    if existing_refund:
        if (
            existing_refund.task_id != task.id
            or existing_refund.available_delta != payload.points
            or existing_refund.kind != "admin_refund"
        ):
            raise HTTPException(status_code=409, detail="idempotency_conflict")
        return await task_view(db, task)
    remaining = task.charged_points - task.refunded_points
    if task.status != TaskStatus.SUCCEEDED or payload.points > remaining:
        raise HTTPException(status_code=409, detail="refund_exceeds_charge")
    user = await db.scalar(
        select(User).where(User.id == task.user_id).with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    await apply_credit_entry(
        db,
        user=user,
        task_id=task.id,
        kind="admin_refund",
        available_delta=payload.points,
        reserved_delta=0,
        idempotency_key=payload.idempotency_key,
        details={"reason": payload.reason, "admin_id": admin.id},
    )
    task.refunded_points += payload.points
    add_audit(
        db,
        actor_id=admin.id,
        action="task_refunded",
        target_type="task",
        target_id=task.id,
        details={"points": payload.points, "reason": payload.reason},
    )
    await db.commit()
    return await task_view(db, task)


@router.delete("/admin/files/{file_id}")
async def admin_delete_file(
    file_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    media = await db.get(MediaFile, file_id)
    if media is None:
        raise HTTPException(status_code=404, detail="file_not_found")
    await _delete_media(media, admin, db)
    await db.commit()
    return {"deleted": True}


@router.get("/admin/tickets", response_model=list[TicketView])
async def admin_tickets(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Ticket]:
    return list(
        (await db.scalars(select(Ticket).order_by(Ticket.created_at.desc()))).all()
    )


@router.patch("/admin/tickets/{ticket_id}", response_model=TicketView)
async def admin_update_ticket(
    ticket_id: str,
    payload: AdminTicketUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket_not_found")
    ticket.status = payload.status
    ticket.admin_reply = payload.admin_reply or None
    add_audit(
        db,
        actor_id=admin.id,
        action="ticket_updated",
        target_type="ticket",
        target_id=ticket.id,
        details={"status": payload.status.value},
    )
    await db.commit()
    return ticket


# Worker API
@router.post("/worker/heartbeat")
async def worker_heartbeat(
    payload: WorkerHeartbeatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    require_agent(request)
    worker = await db.get(Worker, payload.worker_id)
    capabilities = [item.value for item in payload.capabilities]
    if worker is None:
        worker = Worker(
            id=payload.worker_id,
            capabilities=capabilities,
            last_seen_at=utcnow(),
        )
        db.add(worker)
    else:
        worker.capabilities = capabilities
        worker.last_seen_at = utcnow()
    await db.commit()
    return {"worker_id": worker.id, "accepted": True}


async def _recover_expired_leases(db: AsyncSession) -> None:
    now = utcnow()
    attempts = list(
        (
            await db.scalars(
                select(TaskAttempt).where(
                    TaskAttempt.status.in_(list(ACTIVE_STATUSES)),
                    TaskAttempt.lease_expires_at < now,
                )
            )
        ).all()
    )
    for attempt in attempts:
        task = await db.get(Task, attempt.task_id)
        if task and task.current_attempt_id == attempt.id:
            if attempt.provider_task_id:
                attempt.status = TaskStatus.QUEUED
                attempt.worker_id = None
                attempt.lease_expires_at = None
                task.status = TaskStatus.QUEUED
                task.status_reason = "provider_recovery"
                continue
            attempt.status = TaskStatus.FAILED
            attempt.error_code = "lease_expired"
            attempt.retryable = True
            next_number = (
                await db.scalar(
                    select(func.max(TaskAttempt.attempt_number)).where(
                        TaskAttempt.task_id == task.id
                    )
                )
                or 0
            ) + 1
            replacement = TaskAttempt(
                task_id=task.id,
                attempt_number=next_number,
            )
            db.add(replacement)
            await db.flush()
            task.current_attempt_id = replacement.id
            task.status = TaskStatus.QUEUED
            task.status_reason = "worker_lease_expired"
            task.progress = 0


@router.post("/worker/tasks/claim")
async def worker_claim(
    payload: WorkerClaimRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    require_agent(request)
    worker = await db.get(Worker, payload.worker_id)
    if worker is None or not worker.enabled:
        raise HTTPException(status_code=403, detail="worker_disabled")
    worker.last_seen_at = utcnow()
    await _recover_expired_leases(db)
    tasks = list(
        (
            await db.scalars(
                select(Task)
                .where(Task.status == TaskStatus.QUEUED)
                .order_by(Task.created_at)
                .with_for_update(skip_locked=True)
                .limit(20)
            )
        ).all()
    )
    task = next(
        (item for item in tasks if item.task_type.value in worker.capabilities), None
    )
    if task is None:
        await db.commit()
        return None
    attempt = await db.get(TaskAttempt, task.current_attempt_id)
    if attempt is None:
        raise HTTPException(status_code=409, detail="attempt_missing")
    attempt.worker_id = worker.id
    attempt.status = TaskStatus.CLAIMED
    attempt.lease_expires_at = utcnow() + timedelta(
        seconds=settings.worker_lease_seconds
    )
    task.status = TaskStatus.CLAIMED
    task.status_reason = None
    await db.commit()
    source = await db.get(MediaFile, task.source_file_id)
    return {
        "task_id": task.id,
        "attempt_id": attempt.id,
        "attempt_number": attempt.attempt_number,
        "provider": attempt.provider,
        "provider_task_id": attempt.provider_task_id,
        "task_type": task.task_type.value,
        "multiplier": task.multiplier,
        "source": {
            "file_id": source.id if source else None,
            "mime_type": source.mime_type if source else None,
            "width": source.width if source else None,
            "height": source.height if source else None,
            "duration_seconds": source.duration_seconds if source else None,
            "download_path": f"/api/worker/files/{source.id}" if source else None,
        },
        "workflow": f"{task.task_type.value}.api.json",
        "lease_expires_at": attempt.lease_expires_at,
    }


async def _owned_attempt(
    attempt_id: str, request: Request, db: AsyncSession
) -> tuple[TaskAttempt, Task]:
    require_agent(request)
    attempt = await db.get(TaskAttempt, attempt_id)
    worker_id = request.headers.get("x-worker-id")
    if attempt is None or not worker_id or attempt.worker_id != worker_id:
        raise HTTPException(status_code=404, detail="attempt_not_found")
    task = await db.get(Task, attempt.task_id)
    if task is None or task.current_attempt_id != attempt.id:
        raise HTTPException(status_code=409, detail="stale_attempt")
    if (
        attempt.status not in ACTIVE_STATUSES
        or task.status not in ACTIVE_STATUSES
    ):
        raise HTTPException(status_code=409, detail="attempt_not_active")
    if attempt.lease_expires_at and attempt.lease_expires_at.replace(
        tzinfo=timezone.utc
    ) < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="lease_expired")
    return attempt, task


@router.post("/worker/attempts/{attempt_id}/provider")
async def worker_bind_provider_task(
    attempt_id: str,
    payload: WorkerProviderBindingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    attempt, _task = await _owned_attempt(attempt_id, request, db)
    if attempt.provider_task_id:
        if (
            attempt.provider != payload.provider
            or attempt.provider_task_id != payload.provider_task_id
        ):
            raise HTTPException(status_code=409, detail="provider_binding_conflict")
        return {"accepted": True, "provider_task_id": attempt.provider_task_id}
    attempt.provider = payload.provider
    attempt.provider_task_id = payload.provider_task_id
    await db.commit()
    return {"accepted": True, "provider_task_id": attempt.provider_task_id}


@router.get("/worker/files/{file_id}")
async def worker_download(
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    require_agent(request)
    media = await db.get(MediaFile, file_id)
    if media is None or media.deleted_at:
        raise HTTPException(status_code=404, detail="file_not_found")
    data = await get_storage().open_bytes(media.object_key)
    return StreamingResponse(iter([data]), media_type=media.mime_type)


@router.post("/worker/attempts/{attempt_id}/progress")
async def worker_progress(
    attempt_id: str,
    payload: WorkerProgressRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.status not in {
        TaskStatus.PREPROCESSING,
        TaskStatus.RUNNING,
        TaskStatus.UPLOADING,
    }:
        raise HTTPException(status_code=422, detail="invalid_progress_status")
    attempt, task = await _owned_attempt(attempt_id, request, db)
    attempt.status = payload.status
    attempt.lease_expires_at = utcnow() + timedelta(
        seconds=settings.worker_lease_seconds
    )
    task.status = payload.status
    task.progress = payload.progress
    await db.commit()
    return {"accepted": True}


@router.post("/worker/attempts/{attempt_id}/complete")
async def worker_complete(
    attempt_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    attempt, task = await _owned_attempt(attempt_id, request, db)
    user = await db.get(User, task.user_id)
    source = await db.get(MediaFile, task.source_file_id)
    if user is None or source is None:
        raise HTTPException(status_code=409, detail="task_context_missing")
    output = await _save_upload(
        file, user, db, is_output=True, forced_kind=source.media_kind
    )
    await capture_reservation(db, task)
    task.output_file_id = output.id
    task.status = TaskStatus.SUCCEEDED
    task.status_reason = None
    task.progress = 100
    task.error_code = None
    task.error_detail = None
    attempt.status = TaskStatus.SUCCEEDED
    attempt.lease_expires_at = None
    await db.commit()
    return {"accepted": True, "output_file_id": output.id}


@router.post("/worker/attempts/{attempt_id}/fail")
async def worker_fail(
    attempt_id: str,
    payload: WorkerFailureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    attempt, task = await _owned_attempt(attempt_id, request, db)
    attempt.status = TaskStatus.FAILED
    attempt.error_code = payload.error_code
    attempt.error_detail = payload.error_detail
    attempt.retryable = payload.retryable
    attempt.lease_expires_at = None
    task.status = TaskStatus.FAILED
    task.status_reason = "worker_failed"
    task.error_code = payload.error_code
    task.error_detail = payload.error_detail
    await release_reservation(db, task, reason=f"attempt_{attempt.id}")
    await db.commit()
    return {"accepted": True}
