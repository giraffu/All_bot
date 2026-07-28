import asyncio
import contextlib
import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from src.billing_core_provider_setup import ensure_billing_core_providers_registered
from src.services.payment_fulfillment_service import (
    deliver_rmb_payment_success_notification,
    fulfill_rmb_order,
)
from src.services.rmb_payment_service import (
    HUANYUY_KEY,
    HUANYUY_PID,
    RMBPaymentService,
)
from src.services.rmb_payment_reconciliation_service import (
    build_rmb_payment_reconciler_if_enabled,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payment_api")

async def register_payment_api_providers():
    ensure_billing_core_providers_registered()


@asynccontextmanager
async def payment_api_lifespan(_app: FastAPI):
    await register_payment_api_providers()
    reconciler = build_rmb_payment_reconciler_if_enabled()
    _app.state.reconciler_enabled = reconciler is not None
    reconciler_task = (
        asyncio.create_task(reconciler.run_forever()) if reconciler else None
    )
    try:
        yield
    finally:
        if reconciler_task is not None:
            reconciler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reconciler_task


app = FastAPI(title="RMB Payment Webhook API", lifespan=payment_api_lifespan)
app.state.notification_tasks = set()
app.state.reconciler_enabled = False


def _order_log_key(out_trade_no: str | None) -> str:
    return hashlib.sha256(str(out_trade_no or "").encode("utf-8")).hexdigest()[:12]


def schedule_payment_notification(result) -> None:
    task = asyncio.create_task(deliver_rmb_payment_success_notification(result))
    app.state.notification_tasks.add(task)

    def _consume_result(completed_task):
        app.state.notification_tasks.discard(completed_task)
        if completed_task.cancelled():
            return
        try:
            completed_task.result()
        except Exception as exc:
            logger.error(
                "RMB payment notification task failed error_type=%s",
                type(exc).__name__,
            )

    task.add_done_callback(_consume_result)


async def _read_callback_params(request: Request) -> dict[str, str]:
    params = dict(request.query_params)
    if request.method == "GET":
        return params
    form = await request.form()
    params.update({str(key): str(value) for key, value in form.items()})
    return params


def _callback_is_valid(params: dict[str, str]) -> bool:
    if not HUANYUY_PID or not HUANYUY_KEY:
        return False
    if params.get("pid") != HUANYUY_PID:
        return False
    if str(params.get("sign_type", "")).upper() != "MD5":
        return False
    if params.get("trade_status") != "TRADE_SUCCESS":
        return False
    if not all(
        params.get(field)
        for field in ("out_trade_no", "trade_no", "money", "sign")
    ):
        return False
    return RMBPaymentService.verify_callback_sign(params, HUANYUY_KEY)


@app.api_route(
    "/api/pay/notify/huanyuy",
    methods=["GET", "POST"],
    response_class=PlainTextResponse,
)
async def huanyuy_notify(request: Request):
    started_at = time.monotonic()
    try:
        params = await _read_callback_params(request)
    except Exception:
        logger.warning("RMB callback rejected reason=invalid_request_body")
        return PlainTextResponse("fail")

    order_key = _order_log_key(params.get("out_trade_no"))
    if not _callback_is_valid(params):
        logger.warning(
            "RMB callback rejected order_key=%s reason=validation_failed",
            order_key,
        )
        return PlainTextResponse("fail")

    try:
        result = await fulfill_rmb_order(
            params["out_trade_no"],
            params["trade_no"],
            params["money"],
            source="rmb_payment_callback",
        )
    except Exception as exc:
        logger.error(
            "RMB callback fulfillment failed order_key=%s error_type=%s",
            order_key,
            type(exc).__name__,
        )
        return PlainTextResponse("fail")

    if result.status not in {"success", "noop"}:
        logger.error(
            "RMB callback fulfillment rejected order_key=%s status=%s",
            order_key,
            result.status,
        )
        return PlainTextResponse("fail")
    if result.status == "success":
        schedule_payment_notification(result)
    logger.info(
        "RMB callback acknowledged order_key=%s result=%s elapsed_ms=%d",
        order_key,
        result.status,
        int((time.monotonic() - started_at) * 1000),
    )
    return PlainTextResponse("success")


@app.get("/healthz")
async def payment_health():
    return {
        "status": "ok",
        "rmb_reconciliation_enabled": bool(app.state.reconciler_enabled),
    }


@app.get("/pay/result", response_class=HTMLResponse)
async def payment_result():
    """
    支付完成后的页面跳转
    """
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>支付结果处理中</title>
        <style>
            body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; text-align: center; padding-top: 50px; background-color: #f8f9fa; }
            .container { background-color: white; border-radius: 10px; padding: 40px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: inline-block; max-width: 400px; margin: 0 auto; }
            h1 { color: #28a745; }
            p { color: #6c757d; font-size: 16px; line-height: 1.5; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>支付已受理</h1>
            <p>您的支付请求已成功提交，正在等待平台确认。</p>
            <p>充值到账以系统通知为准，请返回 <b>Telegram 机器人</b> 查看结果。</p>
        </div>
    </body>
    </html>
    """


if __name__ == "__main__":
    port = int(os.getenv("PAYMENT_API_PORT", 8021))
    uvicorn.run(app, host="0.0.0.0", port=port)
