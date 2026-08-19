from __future__ import annotations

import asyncio
import hashlib
import logging
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import Order
from src.services.alipay_direct_service import get_alipay_direct_service
from src.services.payment_fulfillment_service import (
    deliver_rmb_payment_success_notification,
    fulfill_rmb_order,
)
from src.services.rmb_payment_provider_service import ALIPAY_DIRECT

logger = logging.getLogger("alipay_payment_callback")
router = APIRouter()
_notification_tasks: set[asyncio.Task] = set()


def _order_log_key(order_id: str | None) -> str:
    return hashlib.sha256(str(order_id or "").encode()).hexdigest()[:12]


async def deliver_notification(result) -> None:
    task = asyncio.create_task(deliver_rmb_payment_success_notification(result))
    _notification_tasks.add(task)

    def _finish(completed: asyncio.Task) -> None:
        _notification_tasks.discard(completed)
        if completed.cancelled():
            return
        try:
            completed.result()
        except Exception as exc:
            logger.error(
                "Alipay notification delivery failed error_type=%s",
                type(exc).__name__,
            )

    task.add_done_callback(_finish)


async def validate_alipay_callback_order(params: dict[str, str]) -> bool:
    order_id = str(params.get("out_trade_no") or "")
    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_id == order_id))
        ).scalar_one_or_none()
    if order is None:
        return False
    if order.payment_channel != "RMB":
        return False
    if order.payment_provider != ALIPAY_DIRECT:
        return False
    expected = Decimal(str(order.final_price)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    try:
        received = Decimal(str(params.get("total_amount"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except Exception:
        return False
    return expected == received


@router.post("/api/pay/notify/alipay", response_class=PlainTextResponse)
async def alipay_notify(request: Request):
    try:
        form = await request.form()
        params = {str(key): str(value) for key, value in form.items()}
        service = get_alipay_direct_service()
    except Exception:
        logger.warning("Alipay callback rejected reason=invalid_request")
        return PlainTextResponse("fail")
    order_key = _order_log_key(params.get("out_trade_no"))
    if not service.verify_callback(params):
        logger.warning(
            "Alipay callback rejected order_key=%s reason=signature_or_identity",
            order_key,
        )
        return PlainTextResponse("fail")
    if not await validate_alipay_callback_order(params):
        logger.warning(
            "Alipay callback rejected order_key=%s reason=order_validation",
            order_key,
        )
        return PlainTextResponse("fail")
    try:
        result = await fulfill_rmb_order(
            params["out_trade_no"],
            params["trade_no"],
            params["total_amount"],
            source="alipay_direct_callback",
        )
    except Exception as exc:
        logger.error(
            "Alipay callback fulfillment failed order_key=%s error_type=%s",
            order_key,
            type(exc).__name__,
        )
        return PlainTextResponse("fail")
    if result.status not in {"success", "noop"}:
        return PlainTextResponse("fail")
    if result.status == "success":
        await deliver_notification(result)
    logger.info(
        "Alipay callback acknowledged order_key=%s result=%s",
        order_key,
        result.status,
    )
    return PlainTextResponse("success")

