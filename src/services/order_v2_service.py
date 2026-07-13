import os
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select

from config import BOT_TYPE
from src.database.models import MembershipPlan, Order
from src.services.membership_settlement_service import build_plan_settlement_snapshot

ORDER_V2_ENABLED_ENV = "ORDER_V2_ENABLED"
ORDER_V2_PREFIX = "ORDER_V2:"
ORDER_LEGACY_PREFIX = "ORDER:"


def _is_feature_enabled(name: str) -> bool:
    if BOT_TYPE == "TEST":
        test_value = os.getenv(f"{name}_TEST")
        if test_value not in (None, ""):
            return test_value.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_order_v2_enabled() -> bool:
    return _is_feature_enabled(ORDER_V2_ENABLED_ENV)


def generate_business_order_id() -> str:
    return f"bo_{uuid.uuid4().hex[:24]}"


def build_order_settlement_snapshot(plan: MembershipPlan) -> dict:
    return build_plan_settlement_snapshot(
        plan,
        grant_reward_credits=True,
        schema_version="order_plan_v1",
    )


def build_order_v2_payload(business_order_id: str) -> str:
    return f"{ORDER_V2_PREFIX}{business_order_id}"


def build_legacy_order_payload(
    *,
    telegram_user_id: int,
    plan_id: int,
    timestamp: int,
) -> str:
    return f"{ORDER_LEGACY_PREFIX}{telegram_user_id}:{plan_id}:{timestamp}"


@dataclass(frozen=True)
class ParsedOrderPayload:
    kind: Literal["legacy", "v2", "unknown"]
    raw_payload: str
    business_order_id: str | None = None
    telegram_user_id: int | None = None
    plan_id: int | None = None
    timestamp: int | None = None


def parse_order_payload(payload: str) -> ParsedOrderPayload:
    if payload.startswith(ORDER_V2_PREFIX):
        business_order_id = payload[len(ORDER_V2_PREFIX) :].strip()
        return ParsedOrderPayload(
            kind="v2",
            raw_payload=payload,
            business_order_id=business_order_id or None,
        )

    if payload.startswith(ORDER_LEGACY_PREFIX):
        parts = payload.split(":")
        if len(parts) >= 4:
            try:
                return ParsedOrderPayload(
                    kind="legacy",
                    raw_payload=payload,
                    telegram_user_id=int(parts[1]),
                    plan_id=int(parts[2]),
                    timestamp=int(parts[3]),
                )
            except (TypeError, ValueError):
                return ParsedOrderPayload(kind="unknown", raw_payload=payload)
        return ParsedOrderPayload(kind="unknown", raw_payload=payload)

    return ParsedOrderPayload(kind="unknown", raw_payload=payload)


def get_order_public_id(order: Order) -> str:
    return str(order.business_order_id or order.order_id)


def build_order_public_lookup_stmt(public_id: str, *, for_update: bool = False):
    stmt = select(Order).where(
        or_(Order.business_order_id == public_id, Order.order_id == public_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return stmt
