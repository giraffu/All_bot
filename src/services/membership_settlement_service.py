from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.billing_core import MembershipSettlementResult
from src.core.billing_core import calculate_membership_settlement
from src.database.models import MembershipPlan, User
from src.quota import QuotaManager
from src.services.log_service import LogService

quota_manager = QuotaManager()


@dataclass(frozen=True)
class MembershipSettlementAuditSource:
    source: str
    source_channel: str | None = None
    source_order_id: str | None = None
    source_tx_hash: str | None = None
    option_key: str | None = None


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_plan_settlement_snapshot(
    plan: MembershipPlan,
    *,
    grant_reward_credits: bool = True,
    schema_version: str = "legacy_plan_v1",
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "plan_id": int(plan.id),
        "plan_name": plan.name,
        "display_name": plan.name,
        "target_identity": plan.identity_name,
        "duration_days": int(plan.duration_days or 0),
        "reward_credits": int(plan.reward_credits or 0),
        "grant_reward_credits": grant_reward_credits,
        "allow_pure_credit_plan": int(plan.duration_days or 0) == 0,
    }


async def apply_membership_settlement_in_session(
    *,
    locked_user: User,
    settlement_snapshot: dict[str, Any],
    settlement_result: MembershipSettlementResult,
    audit_source: MembershipSettlementAuditSource,
    session: AsyncSession,
) -> dict[str, Any]:
    locked_user.current_identity = settlement_result.final_identity
    locked_user.identity_expire_at = settlement_result.final_expire_at

    current_balance = int(locked_user.credits or 0)
    if settlement_result.credits_to_grant > 0:
        credit_change = await quota_manager.add_credits(
            user_id=locked_user.id,
            credits=settlement_result.credits_to_grant,
            username=locked_user.username,
            task_type="membership_settlement_reward",
            session=session,
            extra_info={
                "source": audit_source.source,
                "source_channel": audit_source.source_channel,
                "option_key": audit_source.option_key,
            },
            audit_mode="skip",
        )
        current_balance = credit_change.new_balance

    await session.flush()

    audit_extra = {
        "source": audit_source.source,
        "source_channel": audit_source.source_channel,
        "source_order_id": audit_source.source_order_id,
        "source_tx_hash": audit_source.source_tx_hash,
        "plan_id": settlement_snapshot.get("plan_id"),
        "plan_name": settlement_snapshot.get("plan_name"),
        "option_key": audit_source.option_key,
        "settlement_reason": settlement_result.settlement_reason,
        "converted_days": settlement_result.converted_days,
        "final_identity": settlement_result.final_identity,
        "final_expire_at": _serialize_datetime(settlement_result.final_expire_at),
        "credits_granted": settlement_result.credits_to_grant,
        "target_identity": settlement_snapshot.get("target_identity"),
        "duration_days": settlement_snapshot.get("duration_days"),
    }
    await LogService.log_action(
        user_id=locked_user.id,
        username=locked_user.username,
        operation_type="recharge",
        credit_change=settlement_result.credits_to_grant,
        current_balance=current_balance,
        extra_info=audit_extra,
        session=session,
    )

    return {
        **settlement_snapshot,
        **asdict(settlement_result),
        "final_expire_at": _serialize_datetime(settlement_result.final_expire_at),
        "current_identity": settlement_result.final_identity,
        "identity_expire_at": _serialize_datetime(settlement_result.final_expire_at),
        "current_credits": current_balance,
        "credits_granted": settlement_result.credits_to_grant,
    }


async def settle_membership_plan_in_session(
    *,
    locked_user: User,
    plan: MembershipPlan,
    audit_source: MembershipSettlementAuditSource,
    session: AsyncSession,
    now: datetime,
    grant_reward_credits: bool = True,
    schema_version: str = "legacy_plan_v1",
) -> dict[str, Any]:
    settlement_snapshot = build_plan_settlement_snapshot(
        plan,
        grant_reward_credits=grant_reward_credits,
        schema_version=schema_version,
    )
    settlement_result = calculate_membership_settlement(
        current_identity=locked_user.current_identity,
        current_expire_at=locked_user.identity_expire_at,
        target_identity=plan.identity_name,
        duration_days=int(plan.duration_days or 0),
        reward_credits=int(plan.reward_credits or 0),
        grant_reward_credits=grant_reward_credits,
        now=now,
    )
    return await apply_membership_settlement_in_session(
        locked_user=locked_user,
        settlement_snapshot=settlement_snapshot,
        settlement_result=settlement_result,
        audit_source=audit_source,
        session=session,
    )
