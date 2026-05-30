from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.database.core import AsyncSessionLocal
from src.database.models import User


def normalize_telegram_username(
    username: str | None,
    full_name: str | None,
) -> tuple[str | None, str | None]:
    import re

    if username and not re.match(r"^[a-zA-Z0-9_]{4,64}$", username):
        if not full_name:
            full_name = username
        username = None
    return username, full_name


def normalize_telegram_language_code(language_code: str | None) -> str:
    if not language_code:
        return "zh"
    if not language_code.startswith("zh"):
        return "en"
    return "zh"


async def _get_user_by_telegram_id(session, tg_id: int):
    stmt = select(User).where(User.telegram_id == tg_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_legacy_user_by_internal_id(session, tg_id: int):
    stmt = select(User).where(User.id == tg_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _is_legacy_internal_id_adopt_candidate(user, *, tg_id: int) -> bool:
    return bool(user and user.id == tg_id and not user.telegram_id)


async def _apply_existing_telegram_user_updates(
    *,
    session,
    user,
    username: str | None,
    full_name: str | None,
    language_code: str,
):
    updated = False
    if username and user.username != username and not user.hashed_password:
        user.username = username
        updated = True
    if full_name and user.full_name != full_name:
        user.full_name = full_name
        updated = True
    if language_code and not user.language_code:
        user.language_code = language_code
        updated = True

    if updated:
        user_id = user.id
        try:
            await session.flush()
            await session.commit()
        except IntegrityError:
            await session.rollback()
            user = await session.get(User, user_id)
    return user, False


async def _adopt_legacy_internal_user(session, *, user, tg_id: int):
    if _is_legacy_internal_id_adopt_candidate(user, tg_id=tg_id):
        user.telegram_id = tg_id
        await session.commit()
    return user, False


def _build_new_telegram_user(
    *,
    tg_id: int,
    username: str | None,
    full_name: str | None,
    language_code: str,
):
    return User(
        telegram_id=tg_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
        credits=6,
        last_activity=datetime.now(),
    )


async def _create_new_telegram_user(
    *,
    session,
    tg_id: int,
    username: str | None,
    full_name: str | None,
    language_code: str,
):
    new_user = _build_new_telegram_user(
        tg_id=tg_id,
        username=username,
        full_name=full_name,
        language_code=language_code,
    )
    session.add(new_user)
    try:
        await session.flush()
        await session.commit()
        return new_user, True
    except IntegrityError:
        await session.rollback()
        existing_user = await _get_user_by_telegram_id(session, tg_id)
        if existing_user:
            return existing_user, False

        fallback_user = _build_new_telegram_user(
            tg_id=tg_id,
            username=None,
            full_name=full_name,
            language_code=language_code,
        )
        session.add(fallback_user)
        try:
            await session.flush()
            await session.commit()
            return fallback_user, True
        except IntegrityError:
            await session.rollback()
            raise


async def get_or_create_user_by_telegram(
    tg_id: int,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
):
    username, full_name = normalize_telegram_username(username, full_name)
    language_code = normalize_telegram_language_code(language_code)

    async with AsyncSessionLocal() as session:
        user = await _get_user_by_telegram_id(session, tg_id)

        if user:
            return await _apply_existing_telegram_user_updates(
                session=session,
                user=user,
                username=username,
                full_name=full_name,
                language_code=language_code,
            )

        user = await _get_legacy_user_by_internal_id(session, tg_id)

        if user:
            return await _adopt_legacy_internal_user(session, user=user, tg_id=tg_id)

        return await _create_new_telegram_user(
            session=session,
            tg_id=tg_id,
            username=username,
            full_name=full_name,
            language_code=language_code,
        )


async def get_or_create_user_by_google(
    google_id: str,
    email: str,
    full_name: str | None = None,
):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.google_id == google_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            return user

        new_user = User(
            google_id=google_id,
            email=email,
            full_name=full_name,
            credits=6,
            last_activity=datetime.now(),
        )
        session.add(new_user)
        try:
            await session.flush()
            await session.commit()
            return new_user
        except IntegrityError:
            await session.rollback()
            stmt = select(User).where(User.google_id == google_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
