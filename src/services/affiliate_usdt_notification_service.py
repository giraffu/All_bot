from __future__ import annotations

import logging

import aiohttp

from config import BOT_TOKEN, TELEGRAM_API_BASE_URL

logger = logging.getLogger(__name__)


async def send_affiliate_usdt_redeem_notification(
    *,
    telegram_id: int | None,
    redeem_id: int,
    amount_usdt: str,
    status: str,
    rejection_reason: str | None = None,
) -> None:
    if not BOT_TOKEN or not telegram_id:
        return
    if status == "SUCCESS":
        text = (
            "✅ 返佣兑换 USDT 已处理\n\n"
            f"申请编号：{redeem_id}\n"
            f"打款金额：{amount_usdt} USDT\n"
            "网络：TON"
        )
    else:
        text = (
            "❌ 返佣兑换 USDT 申请已拒绝\n\n"
            f"申请编号：{redeem_id}\n"
            f"申请金额：{amount_usdt} USDT\n"
            f"原因：{rejection_reason or '-'}\n"
            "冻结返佣已恢复为可用余额。"
        )
    url = f"{TELEGRAM_API_BASE_URL}/bot{BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as client:
            async with client.post(
                url,
                json={"chat_id": telegram_id, "text": text},
                proxy=None,
            ) as response:
                if response.status != 200:
                    logger.warning(
                        "Affiliate USDT notification failed: redeem_id=%s status=%s http_status=%s",
                        redeem_id,
                        status,
                        response.status,
                    )
    except Exception:
        logger.warning(
            "Affiliate USDT notification raised: redeem_id=%s status=%s",
            redeem_id,
            status,
            exc_info=True,
        )
