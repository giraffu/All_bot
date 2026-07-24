from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import uuid4

from src.core.billing_core import refund_credits
from src.services.task_service_generation_common import resolve_internal_user_id


RefundCredits = Callable[..., Awaitable[bool]]


def new_qqcc_scene_billing_id() -> str:
    return uuid4().hex


def resolve_qqcc_scene_fixed_credit_cost(scene: dict[str, Any] | None) -> int | None:
    if not isinstance(scene, dict):
        return None
    value = scene.get("credit_cost")
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1
        else None
    )


@dataclass
class QqccSceneBillingState:
    fixed_credit_cost: int | None
    billing_id: str
    submitted_task_count: int = 0
    successful_task_count: int = 0
    root_task_id: str | None = None
    actual_charged_cost: int = 0
    refund_completed: bool = False

    def allocate_task_billing(self) -> dict[str, Any]:
        if self.fixed_credit_cost is None:
            return {}
        is_first = self.submitted_task_count == 0
        self.submitted_task_count += 1
        if is_first:
            return {"cost_override": self.fixed_credit_cost}
        return {"deduct_quota": False}

    def mark_task_succeeded(
        self,
        *,
        root_task_id: str | None = None,
        actual_cost: int | None = None,
    ) -> None:
        if self.fixed_credit_cost is None:
            return
        self.successful_task_count += 1
        if self.successful_task_count == 1:
            self.root_task_id = str(root_task_id or "").strip() or None
            self.actual_charged_cost = (
                actual_cost
                if isinstance(actual_cost, int) and actual_cost > 0
                else self.fixed_credit_cost
            )

    @property
    def requires_chain_refund(self) -> bool:
        return bool(
            self.fixed_credit_cost is not None
            and self.successful_task_count > 0
            and not self.refund_completed
        )


async def refund_qqcc_scene_fixed_charge(
    *,
    billing_state: QqccSceneBillingState,
    telegram_user_id: int,
    username: str | None,
    refund_credits_func: RefundCredits = refund_credits,
) -> bool:
    if not billing_state.requires_chain_refund:
        return False
    internal_user_id = await resolve_internal_user_id(telegram_user_id, username)
    amount = billing_state.actual_charged_cost or billing_state.fixed_credit_cost or 0
    refunded = await refund_credits_func(
        internal_user_id,
        amount,
        username=username,
        task_type="refund_qqcc_scene_fixed_cost",
        idempotency_key=f"qqcc_scene_refund:{billing_state.billing_id}",
    )
    billing_state.refund_completed = True
    return refunded
