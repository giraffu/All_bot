from decimal import Decimal

from src.services.order_v2_service import get_order_public_id


def build_payment_plan_item(plan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "description": f"获得 {plan.reward_credits} 灵石",
        "price_rmb": float(plan.price_rmb),
        "price_ton": float(plan.price_ton),
        "duration_days": plan.duration_days,
        "identity_override": plan.identity_name,
        "credits_granted": plan.reward_credits,
        "type": "monthly" if plan.duration_days > 0 else "one_time",
    }


def build_payment_plans_payload(
    plans,
    *,
    ton_payment_enabled: bool,
    ton_receiver_address: str | None,
) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": {
            "plans": [build_payment_plan_item(plan) for plan in plans],
            "ton_payment_enabled": ton_payment_enabled,
            "ton_receiver_address": (
                ton_receiver_address if ton_payment_enabled else None
            ),
        },
    }


def build_rmb_order_payload(order, pay_url: str) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": {
            "order_id": get_order_public_id(order),
            "business_order_id": order.business_order_id,
            "legacy_order_id": order.order_id,
            "pay_url": pay_url,
        },
    }


def build_ton_order_payload(
    *,
    order,
    ton_comment: str,
    amount_ton,
    ton_receiver_address: str,
) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": {
            "order_id": get_order_public_id(order),
            "business_order_id": order.business_order_id,
            "legacy_order_id": order.order_id,
            "ton_comment": ton_comment,
            "ton_receiver_address": ton_receiver_address,
            "amount_ton": float(amount_ton),
            "amount_nanotons": str(
                int(Decimal(str(amount_ton)) * Decimal("1000000000"))
            ),
        },
    }


def build_order_status_payload(order, *, account=None) -> dict:
    data = {
        "status": order.status,
        "order_id": get_order_public_id(order),
        "business_order_id": order.business_order_id,
        "legacy_order_id": order.order_id,
    }
    if order.status == "SUCCESS" and account is not None:
        data["account"] = {
            "credits": account.credits,
            "current_identity": account.current_identity,
            "identity_expire_at": account.identity_expire_at,
            "user_group": account.user_group,
        }
    return {
        "code": 0,
        "message": "success",
        "data": data,
    }
