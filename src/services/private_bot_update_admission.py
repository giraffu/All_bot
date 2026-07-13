from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Coroutine


@dataclass(frozen=True, slots=True)
class PrivateBotSubmissionCursor:
    private_bot_id: int
    update_id: int
    next_sequence: int

    @property
    def next_submission_key(self) -> str:
        return (
            f"private_bot_update:{self.private_bot_id}:"
            f"{self.update_id}:{self.next_sequence}"
        )


@dataclass(slots=True)
class PrivateBotUpdateAdmissionScope:
    private_bot_id: int
    update_id: int
    _unsettled_backgrounds: int = 0
    _failed: bool = False
    _task_sequence: int = 0
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _backgrounds: list["PrivateBotBackgroundAdmission"] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self._event.set()

    @property
    def failed(self) -> bool:
        return self._failed

    def register_background(self) -> "PrivateBotBackgroundAdmission":
        self._unsettled_backgrounds += 1
        self._event.clear()
        admission = PrivateBotBackgroundAdmission(self)
        self._backgrounds.append(admission)
        return admission

    def mark_failed(self) -> None:
        self._failed = True

    def next_submission_key(self) -> str:
        sequence = self._task_sequence
        self._task_sequence += 1
        return (
            f"private_bot_update:{self.private_bot_id}:"
            f"{self.update_id}:{sequence}"
        )

    def _settle_background(self) -> None:
        if self._unsettled_backgrounds > 0:
            self._unsettled_backgrounds -= 1
        if self._unsettled_backgrounds == 0:
            self._event.set()

    async def wait_until_durable(self, *, timeout_seconds: float) -> None:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout_seconds)
        except TimeoutError:
            self.mark_failed()
            raise


@dataclass(slots=True)
class PrivateBotBackgroundAdmission:
    scope: PrivateBotUpdateAdmissionScope
    settled: bool = False
    task: asyncio.Task | None = None

    def settle(self) -> None:
        if self.settled:
            return
        self.settled = True
        self.scope._settle_background()


_CURRENT_SCOPE: ContextVar[PrivateBotUpdateAdmissionScope | None] = ContextVar(
    "private_bot_update_admission_scope",
    default=None,
)
_CURRENT_BACKGROUND: ContextVar[PrivateBotBackgroundAdmission | None] = ContextVar(
    "private_bot_background_admission",
    default=None,
)


@contextmanager
def activate_private_bot_update_scope(scope: PrivateBotUpdateAdmissionScope):
    token: Token = _CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_SCOPE.reset(token)


def track_private_bot_background(
    coro: Coroutine,
) -> tuple[Coroutine, PrivateBotBackgroundAdmission | None]:
    scope = _CURRENT_SCOPE.get()
    if scope is None:
        return coro, None
    admission = scope.register_background()

    async def tracked():
        token = _CURRENT_BACKGROUND.set(admission)
        try:
            return await coro
        finally:
            admission.settle()
            _CURRENT_BACKGROUND.reset(token)

    return tracked(), admission


def mark_private_bot_task_durable() -> None:
    admission = _CURRENT_BACKGROUND.get()
    if admission is not None:
        admission.settle()


def next_private_bot_submission_key() -> str | None:
    scope = _CURRENT_SCOPE.get()
    return scope.next_submission_key() if scope is not None else None


def get_private_bot_submission_cursor() -> PrivateBotSubmissionCursor | None:
    scope = _CURRENT_SCOPE.get()
    if scope is None:
        return None
    return PrivateBotSubmissionCursor(
        private_bot_id=scope.private_bot_id,
        update_id=scope.update_id,
        next_sequence=scope._task_sequence,
    )


def mark_private_bot_update_failed() -> None:
    scope = _CURRENT_SCOPE.get()
    if scope is not None:
        scope.mark_failed()
