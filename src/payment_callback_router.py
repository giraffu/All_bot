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
from src.services.rmb_payment_service import RMBOrderQueryStatus

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


async def load_alipay_callback_order(order_id: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(select(Order).where(Order.order_id == order_id))
        ).scalar_one_or_none()


async def validate_alipay_callback_order(params: dict[str, str]) -> bool:
    order_id = str(params.get("out_trade_no") or "")
    order = await load_alipay_callback_order(order_id)
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


async def query_verified_alipay_callback_payment(service, params: dict[str, str]):
    """Resolve a rejected notification through Alipay's signed query response.

    The callback contributes only the local order lookup. Provider and amount are
    loaded from the database, and fulfillment identifiers come exclusively from
    the signed query response.
    """

    order_id = str(params.get("out_trade_no") or "")
    if not order_id:
        return None
    if params.get("trade_status") not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
        return None
    order = await load_alipay_callback_order(order_id)
    if order is None:
        return None
    if order.payment_channel != "RMB" or order.payment_provider != ALIPAY_DIRECT:
        return None
    try:
        result = await service.query_order(
            out_trade_no=order_id,
            expected_amount=order.final_price,
        )
    except Exception as exc:
        logger.warning(
            "Alipay callback query fallback failed order_key=%s error_type=%s",
            _order_log_key(order_id),
            type(exc).__name__,
        )
        return None
    if result.status != RMBOrderQueryStatus.PAID:
        return None
    if result.external_trade_no is None or result.paid_amount is None:
        return None
    return result


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
        query_result = await query_verified_alipay_callback_payment(service, params)
        if query_result is None:
            logger.warning(
                "Alipay callback rejected order_key=%s "
                "reason=signature_or_identity_and_query_unverified",
                order_key,
            )
            return PlainTextResponse("fail")
        external_trade_no = query_result.external_trade_no
        paid_amount = query_result.paid_amount
        source = "alipay_direct_callback_query_fallback"
        logger.info(
            "Alipay callback recovered by signed query order_key=%s",
            order_key,
        )
    else:
        if not await validate_alipay_callback_order(params):
            logger.warning(
                "Alipay callback rejected order_key=%s reason=order_validation",
                order_key,
            )
            return PlainTextResponse("fail")
        external_trade_no = params["trade_no"]
        paid_amount = params["total_amount"]
        source = "alipay_direct_callback"
    try:
        result = await fulfill_rmb_order(
            params["out_trade_no"],
            external_trade_no,
            paid_amount,
            source=source,
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
