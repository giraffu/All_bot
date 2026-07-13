from __future__ import annotations

import contextlib
from dataclasses import dataclass

from src.core.billing_core import refund_credits
from src.core.task_core_runtime import (
    cancel_backend_task_best_effort,
    cleanup_task_runtime_state,
)
from src.services import private_bot_submission_ledger


@dataclass(frozen=True, slots=True)
class PrivateBotTaskFinalizationResult:
    acquired: bool
    completed: bool
    refunded: bool
    cancelled: bool


async def finalize_private_bot_submission(
    *,
    request,
    internal_user_id: int | None,
    username: str | None,
    actual_cost: int,
    registry_task_id: str,
    credits_deducted: bool,
    reason_code: str,
    reason_message: str,
    backend_task_id: str | None = None,
    cancel_backend: bool = False,
    refund_credits_func=None,
    cleanup_task_runtime_state_func=None,
    cancel_backend_task_func=None,
) -> PrivateBotTaskFinalizationResult:
    """Run every private-task full refund through one durable finalization CAS."""

    refund_credits_func = refund_credits_func or refund_credits
    cleanup_task_runtime_state_func = (
        cleanup_task_runtime_state_func or cleanup_task_runtime_state
    )
    cancel_backend_task_func = (
        cancel_backend_task_func or cancel_backend_task_best_effort
    )
    snapshot = await (
        private_bot_submission_ledger.request_private_bot_submission_compensation(
            request=request,
            error_code=reason_code,
            error_message=reason_message,
        )
    )
    lease_token = await (
        private_bot_submission_ledger.claim_private_bot_submission_compensation(
            request=snapshot,
        )
    )
    if lease_token is None:
        return PrivateBotTaskFinalizationResult(
            acquired=False,
            completed=snapshot.compensation_status == "completed",
            refunded=False,
            cancelled=False,
        )

    try:
        refunded = False
        if credits_deducted and internal_user_id is not None and actual_cost > 0:
            refunded = bool(
                await refund_credits_func(
                    int(internal_user_id),
                    int(actual_cost),
                    task_type="refund_private_submission",
                    username=username,
                    idempotency_key=(
                        private_bot_submission_ledger.private_bot_submission_refund_idempotency_key(
                            registry_task_id
                        )
                    ),
                )
            )
        cancelled = False
        if cancel_backend and backend_task_id:
            cancelled = bool(
                await cancel_backend_task_func(
                    backend_task_id=backend_task_id,
                    registry_task_id=registry_task_id,
                )
            )
        await cleanup_task_runtime_state_func(
            internal_user_id=int(internal_user_id or 0),
            registry_task_id=registry_task_id,
            release_lock=internal_user_id is not None,
            release_idempotency_key=(
                private_bot_submission_ledger.private_bot_submission_release_idempotency_key(
                    registry_task_id
                )
            ),
            raise_on_error=True,
        )
        await private_bot_submission_ledger.complete_private_bot_submission_compensation(
            request=snapshot,
            lease_token=lease_token,
        )
        return PrivateBotTaskFinalizationResult(
            acquired=True,
            completed=True,
            refunded=refunded,
            cancelled=cancelled,
        )
    except Exception as exc:
        with contextlib.suppress(Exception):
            await private_bot_submission_ledger.record_private_bot_submission_compensation_error(
                request=snapshot,
                lease_token=lease_token,
                error_message=str(exc),
            )
        raise
