from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from src.core.task_core_types import SubmissionJournal
from src.services import private_bot_submission_ledger


class PrivateBotSubmissionJournal(SubmissionJournal):
    """Durable QQCC ledger adapter for debit, dispatch, and compensation phases."""

    def __init__(
        self,
        *,
        submission: Any,
        ledger_request: Any,
        registry_task_id: str,
        owner_token: str,
        compensate_func: Callable[..., Awaitable[bool]],
    ) -> None:
        self.submission = submission
        self.ledger_request = ledger_request
        self.registry_task_id = registry_task_id
        self.owner_token = owner_token
        self.compensate_func = compensate_func
        self.dispatching_persisted = False
        self.compensation_requested = False
        self.compensation_cost = 0
        self.compensation_debit_confirmed = False
        self._refresh_deadlines(
            private_bot_submission_ledger.PRIVATE_BOT_PREPARATION_HARD_DEADLINE_SECONDS
        )

    def _refresh_deadlines(self, timeout_seconds: int) -> None:
        self.owner_deadline_at = datetime.now() + timedelta(seconds=timeout_seconds)
        self.reconcile_not_before_at = self.owner_deadline_at + timedelta(
            seconds=private_bot_submission_ledger.PRIVATE_BOT_DISPATCH_SETTLE_GRACE_SECONDS
        )

    async def before_debit(self, *, cost: int, **_event) -> None:
        self._refresh_deadlines(
            private_bot_submission_ledger.PRIVATE_BOT_DISPATCH_HARD_DEADLINE_SECONDS
        )
        await private_bot_submission_ledger.record_private_bot_submission_cost(
            request=self.ledger_request,
            actual_cost=cost,
            owner_token=self.owner_token,
            owner_deadline_at=self.owner_deadline_at,
            reconcile_not_before_at=self.reconcile_not_before_at,
        )

    async def after_debit(
        self, *, cost: int, credits_deducted: bool, **_event
    ) -> None:
        try:
            await self.before_debit(cost=cost)
        except Exception:
            if credits_deducted:
                await self.compensate_func(
                    submission=self.submission,
                    ledger_request=self.ledger_request,
                    actual_cost=int(cost),
                    registry_task_id=self.registry_task_id,
                    debit_confirmed=True,
                )
            raise

    async def before_dispatch(
        self, *, registry_task_id: str, cost: int, saved_inputs: list[str], **_event
    ) -> None:
        self._refresh_deadlines(
            private_bot_submission_ledger.PRIVATE_BOT_DISPATCH_HARD_DEADLINE_SECONDS
        )
        await private_bot_submission_ledger.mark_private_bot_submission_dispatching(
            request=self.ledger_request,
            registry_task_id=registry_task_id,
            actual_cost=cost,
            saved_inputs=saved_inputs,
            owner_token=self.owner_token,
            owner_deadline_at=self.owner_deadline_at,
            reconcile_not_before_at=self.reconcile_not_before_at,
        )
        self.dispatching_persisted = True

    def should_compensate(self, error: Exception) -> bool:
        return (
            not self.dispatching_persisted
            or private_bot_submission_ledger.is_definitive_dispatch_rejection(error)
        )

    async def before_compensation(
        self, *, cost: int, credits_deducted: bool, **_event
    ) -> None:
        await private_bot_submission_ledger.mark_private_bot_submission_failed(
            request=self.ledger_request,
            actual_cost=cost,
            error_code="submission_failed_before_dispatch",
            error_message="Task submission failed before a durable dispatch outcome.",
        )
        self.compensation_requested = True
        self.compensation_cost = int(cost)
        self.compensation_debit_confirmed = bool(credits_deducted)

    async def compensate_if_requested(self) -> None:
        if not self.compensation_requested:
            return
        await self.compensate_func(
            submission=self.submission,
            ledger_request=self.ledger_request,
            actual_cost=self.compensation_cost,
            registry_task_id=self.registry_task_id,
            debit_confirmed=self.compensation_debit_confirmed,
        )
