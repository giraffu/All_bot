from __future__ import annotations

import inspect

from src.services.alipay_direct_service import (
    get_alipay_direct_service,
    is_alipay_direct_enabled,
)
from src.services.rmb_payment_service import RMBPaymentService

HUANYUY = "HUANYUY"
ALIPAY_DIRECT = "ALIPAY_DIRECT"
VALID_RMB_PAYMENT_PROVIDERS = {HUANYUY, ALIPAY_DIRECT}


def select_rmb_payment_provider(*, user, pay_type: str) -> str:
    if (
        str(pay_type).lower() == "alipay"
        and is_alipay_direct_enabled()
        and bool(getattr(user, "alipay_direct_enabled", False))
    ):
        return ALIPAY_DIRECT
    return HUANYUY


def detect_rmb_client_type(user_agent: str | None) -> str:
    normalized = str(user_agent or "").lower()
    mobile_markers = (
        "android",
        "iphone",
        "ipad",
        "ipod",
        "mobile",
        "windows phone",
    )
    return "mobile" if any(item in normalized for item in mobile_markers) else "desktop"


async def create_rmb_payment_url(
    *,
    provider: str,
    out_trade_no: str,
    plan_name: str,
    amount,
    pay_type: str,
    client_type: str,
    return_url: str | None = None,
) -> dict:
    if provider == HUANYUY:
        return await RMBPaymentService.create_payment_url(
            out_trade_no=out_trade_no,
            plan_name=plan_name,
            amount=amount,
            pay_type=pay_type,
            return_url=return_url,
        )
    if provider != ALIPAY_DIRECT:
        raise ValueError("Unknown RMB payment provider")
    result = get_alipay_direct_service().create_payment_url(
        out_trade_no=out_trade_no,
        subject=plan_name,
        amount=amount,
        product="wap" if client_type == "mobile" else "page",
        return_url=return_url,
    )
    return await result if inspect.isawaitable(result) else result


async def query_rmb_order(
    *,
    provider: str,
    out_trade_no: str,
    expected_amount,
    query_url: str | None = None,
):
    if provider == HUANYUY:
        return await RMBPaymentService.query_order(
            out_trade_no=out_trade_no,
            expected_amount=expected_amount,
            query_url=query_url,
        )
    if provider == ALIPAY_DIRECT:
        return await get_alipay_direct_service().query_order(
            out_trade_no=out_trade_no,
            expected_amount=expected_amount,
        )
    raise ValueError("Unknown RMB payment provider")
