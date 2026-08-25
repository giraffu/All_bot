from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select

from src.database.models import Order
from src.services.alipay_checkout_service import (
    AlipayCheckoutSession,
    load_alipay_checkout_session,
    validate_alipay_launch_url,
)
from src.services.alipay_direct_service import get_alipay_direct_service
from src.services.rmb_payment_provider_service import ALIPAY_DIRECT


_AMOUNT_QUANT = Decimal("0.01")


def _format_amount(value) -> str:
    amount = Decimal(str(value)).quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"


def _checkout_error(status_code: int, reason: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"reason": reason, "message": message},
    )


async def _load_bound_checkout(
    *,
    db,
    token: str,
    session_loader=load_alipay_checkout_session,
) -> tuple[AlipayCheckoutSession, Order]:
    try:
        checkout = await session_loader(token)
    except ValueError as exc:
        raise _checkout_error(
            404,
            "ALIPAY_CHECKOUT_NOT_FOUND",
            "Payment session was not found.",
        ) from exc
    if checkout is None:
        raise _checkout_error(
            410,
            "ALIPAY_CHECKOUT_EXPIRED",
            "Payment session has expired.",
        )

    result = await db.execute(
        select(Order).where(
            Order.business_order_id == checkout.public_order_id,
            Order.order_id == checkout.out_trade_no,
        )
    )
    order = result.scalar_one_or_none()
    if (
        order is None
        or order.payment_channel != "RMB"
        or order.payment_provider != ALIPAY_DIRECT
        or _format_amount(order.final_price) != checkout.amount
    ):
        raise _checkout_error(
            404,
            "ALIPAY_CHECKOUT_NOT_FOUND",
            "Payment session was not found.",
        )
    return checkout, order


async def get_alipay_checkout_payload(
    *,
    db,
    token: str,
    session_loader=load_alipay_checkout_session,
) -> dict:
    checkout, order = await _load_bound_checkout(
        db=db,
        token=token,
        session_loader=session_loader,
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "order_id": checkout.public_order_id,
            "subject": checkout.subject,
            "amount": checkout.amount,
            "status": order.status,
            "created_at": checkout.created_at,
        },
    }


async def get_alipay_checkout_launch_url(
    *,
    db,
    token: str,
    session_loader=load_alipay_checkout_session,
    gateway_url: str | None = None,
) -> str:
    checkout, order = await _load_bound_checkout(
        db=db,
        token=token,
        session_loader=session_loader,
    )
    if order.status != "PENDING":
        reason = (
            "ALIPAY_CHECKOUT_ALREADY_PAID"
            if order.status == "SUCCESS"
            else "ALIPAY_CHECKOUT_NOT_PAYABLE"
        )
        raise _checkout_error(409, reason, "Payment order is not payable.")

    trusted_gateway = gateway_url
    if trusted_gateway is None:
        trusted_gateway = get_alipay_direct_service().config.gateway_url
    validate_alipay_launch_url(
        checkout.pay_url,
        gateway_url=trusted_gateway,
    )
    return checkout.pay_url
