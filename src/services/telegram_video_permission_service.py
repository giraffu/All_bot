"""Resolve main-Bot video settings without leaking persistence into FSM code."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol


class VideoPermissionProvider(Protocol):
    async def get_user_group(self, user_id: int) -> str: ...

    async def get_user_identity(self, user_id: int) -> str: ...

    async def get_video_permissions(
        self,
        user_id: int,
        *,
        user_group: str | None = None,
        user_identity: str | None = None,
    ) -> tuple[list[str], list[str]]: ...


@dataclass(frozen=True)
class TelegramVideoPermissions:
    internal_user_id: int
    user_group: str
    user_identity: str
    allowed_resolutions: tuple[str, ...]
    allowed_durations: tuple[str, ...]


async def resolve_telegram_video_permissions(
    telegram_user_id: int,
    *,
    get_or_create_user_func: Callable[[int], Awaitable[tuple[object, bool]]]
    | None = None,
    permission_provider: VideoPermissionProvider | None = None,
) -> TelegramVideoPermissions:
    if get_or_create_user_func is None:
        from src.core.user_core import get_or_create_user_by_telegram

        get_or_create_user_func = get_or_create_user_by_telegram
    if permission_provider is None:
        from src.services.permission_service import permission_service

        permission_provider = permission_service

    internal_user, _created = await get_or_create_user_func(telegram_user_id)
    internal_user_id = int(getattr(internal_user, "id"))
    user_group = await permission_provider.get_user_group(internal_user_id)
    user_identity = await permission_provider.get_user_identity(internal_user_id)
    (
        allowed_resolutions,
        allowed_durations,
    ) = await permission_provider.get_video_permissions(
        internal_user_id,
        user_group=user_group,
        user_identity=user_identity,
    )
    return TelegramVideoPermissions(
        internal_user_id=internal_user_id,
        user_group=user_group,
        user_identity=user_identity,
        allowed_resolutions=tuple(allowed_resolutions),
        allowed_durations=tuple(allowed_durations),
    )
