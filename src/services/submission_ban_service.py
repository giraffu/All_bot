from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import User

DEFAULT_SUBMISSION_BAN_MESSAGE = "违禁被封，请联系管理员解封"


class SubmissionBannedError(Exception):
    """Raised when a user is not allowed to submit or publish content."""


@dataclass(slots=True)
class SubmissionBanState:
    is_banned: bool
    message: str | None = None


def build_submission_ban_message(reason: str | None = None) -> str:
    normalized_reason = (reason or "").strip()
    return normalized_reason or DEFAULT_SUBMISSION_BAN_MESSAGE


def get_submission_ban_state_from_user(user: User | None) -> SubmissionBanState:
    if user is None:
        return SubmissionBanState(is_banned=False, message=None)
    is_banned = bool(getattr(user, "is_submission_banned", False))
    if not is_banned:
        return SubmissionBanState(is_banned=False, message=None)
    return SubmissionBanState(
        is_banned=True,
        message=build_submission_ban_message(
            getattr(user, "submission_ban_reason", None)
        ),
    )


def ensure_submission_allowed_for_user(user: User | None) -> None:
    state = get_submission_ban_state_from_user(user)
    if state.is_banned:
        raise SubmissionBannedError(state.message or DEFAULT_SUBMISSION_BAN_MESSAGE)


async def ensure_submission_allowed_for_user_id(
    user_id: int,
    *,
    db=None,
    session_factory=None,
) -> None:
    if db is not None:
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        ensure_submission_allowed_for_user(user)
        return

    session_factory = session_factory or AsyncSessionLocal
    async with session_factory() as session:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        ensure_submission_allowed_for_user(user)
