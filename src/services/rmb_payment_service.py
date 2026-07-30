import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger("rmb_payment")
RMB_AMOUNT_QUANT = Decimal("0.01")

HUANYUY_PID = os.getenv("HUANYUY_PID")
HUANYUY_KEY = os.getenv("HUANYUY_KEY")
HUANYUY_GATEWAY = os.getenv("HUANYUY_GATEWAY")
HUANYUY_NOTIFY_URL = os.getenv("HUANYUY_NOTIFY_URL")
HUANYUY_RETURN_URL = os.getenv("HUANYUY_RETURN_URL")
HUANYUY_SITENAME = os.getenv("HUANYUY_SITENAME")
HUANYUY_QUERY_URL = os.getenv("HUANYUY_QUERY_URL")


class RMBOrderQueryStatus(str, Enum):
    PAID = "paid"
    NOT_PAID = "not_paid"


@dataclass(frozen=True)
class RMBOrderQueryResult:
    status: RMBOrderQueryStatus
    out_trade_no: str
    external_trade_no: str | None = None
    paid_amount: Decimal | None = None


class RMBPaymentService:
    @staticmethod
    def _format_amount(amount: Decimal | str | int) -> str:
        normalized = Decimal(str(amount)).quantize(
            RMB_AMOUNT_QUANT, rounding=ROUND_HALF_UP
        )
        return f"{normalized:.2f}"

    @staticmethod
    def generate_sign(params: dict, key: str) -> str:
        """
        生成易支付签名
        """
        filtered_params = {
            k: str(v)
            for k, v in params.items()
            if v not in (None, "") and k not in ("sign", "sign_type")
        }
        sorted_keys = sorted(filtered_params.keys())
        sign_str = "&".join(f"{k}={filtered_params[k]}" for k in sorted_keys)
        final_str = f"{sign_str}{key}"
        return hashlib.md5(final_str.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_callback_sign(params: dict, key: str) -> bool:
        """
        验证回调签名
        """
        if not key:
            return False
        received_sign = str(params.get("sign", "")).lower()
        expected_sign = RMBPaymentService.generate_sign(params, key).lower()
        return bool(received_sign) and hmac.compare_digest(
            received_sign,
            expected_sign,
        )

    @staticmethod
    async def create_payment_url(
        out_trade_no: str,
        plan_name: str,
        amount: Decimal | str | int,
        pay_type: str = "alipay",
        return_url: str = None,
    ) -> dict:
        """
        发起支付请求，获取 pay_url
        """
        if not HUANYUY_GATEWAY or not HUANYUY_PID or not HUANYUY_KEY:
            logger.error("RMB payment gateway configuration is incomplete")
            return {"code": 0, "msg": "Payment gateway unavailable"}
        gateway_url = urlparse(HUANYUY_GATEWAY)
        if gateway_url.scheme.lower() != "https" or not gateway_url.hostname:
            logger.error("RMB payment gateway requires HTTPS")
            return {"code": 0, "msg": "Payment gateway unavailable"}

        params = {
            "money": RMBPaymentService._format_amount(amount),
            "name": plan_name,
            "notify_url": HUANYUY_NOTIFY_URL,
            "out_trade_no": out_trade_no,
            "pid": HUANYUY_PID,
            "return_url": return_url or HUANYUY_RETURN_URL,
            "sitename": HUANYUY_SITENAME,
            "type": pay_type,
        }

        # 易支付的签名规则：将所有参数按键名升序排列，用&拼接，然后加上key再md5
        sign_params = {
            k: str(v)
            for k, v in params.items()
            if v not in (None, "") and k not in ("sign", "sign_type", "return_type")
        }
        sorted_keys = sorted(sign_params.keys())
        sign_str = "&".join(f"{k}={sign_params[k]}" for k in sorted_keys)
        final_str = f"{sign_str}{HUANYUY_KEY}"
        sign = hashlib.md5(final_str.encode("utf-8")).hexdigest()

        submit_params = params.copy()
        submit_params["return_type"] = "json"
        submit_params["sign"] = sign
        submit_params["sign_type"] = "MD5"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    HUANYUY_GATEWAY,
                    data=submit_params,
                    timeout=15,
                    allow_redirects=False,
                ) as resp:
                    if 300 <= resp.status < 400:
                        await resp.read()
                        logger.error(
                            "RMB payment creation rejected redirect http_status=%s",
                            resp.status,
                        )
                        return {
                            "code": 0,
                            "msg": "Payment gateway redirect rejected",
                        }
                    try:
                        data = await resp.json(content_type=None)
                        if not isinstance(data, dict):
                            raise ValueError("payment response is not an object")
                        logger.info(
                            "RMB payment creation completed http_status=%s code=%s",
                            resp.status,
                            data.get("code"),
                        )
                        return data
                    except Exception:
                        await resp.read()
                        logger.error(
                            "RMB payment creation returned invalid JSON "
                            "http_status=%s",
                            resp.status,
                        )
                        return {"code": 0, "msg": "Invalid response format"}
        except Exception as exc:
            logger.error(
                "RMB payment creation failed error_type=%s",
                type(exc).__name__,
            )
            return {"code": 0, "msg": "Payment gateway request failed"}

    @staticmethod
    async def query_order(
        *,
        out_trade_no: str,
        expected_amount: Decimal | str | int,
        query_url: str | None = None,
        timeout_seconds: int = 5,
    ) -> RMBOrderQueryResult:
        target_url = query_url or HUANYUY_QUERY_URL
        if not target_url:
            raise ValueError("HUANYUY_QUERY_URL is required")
        if not HUANYUY_PID or not HUANYUY_KEY:
            raise ValueError("RMB payment gateway credentials are incomplete")

        params = {
            "act": "order",
            "pid": HUANYUY_PID,
            "key": HUANYUY_KEY,
            "out_trade_no": out_trade_no,
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "AllBot-RMB-Reconciler/1.0",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                target_url,
                params=params,
                timeout=timeout_seconds,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    await resp.read()
                    raise ValueError(
                        f"RMB order query returned HTTP {resp.status}"
                    )
                try:
                    data = await resp.json(content_type=None)
                except Exception as exc:
                    await resp.read()
                    raise ValueError("RMB order query returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise ValueError("RMB order query response is not an object")

        status = data.get("status")
        code = data.get("code")
        if str(code) != "1":
            raise ValueError("RMB order query was rejected")
        if str(status) not in {"0", "1"}:
            raise ValueError("RMB order query returned an unknown status")
        if str(status) == "0":
            return RMBOrderQueryResult(
                status=RMBOrderQueryStatus.NOT_PAID,
                out_trade_no=out_trade_no,
            )

        returned_order_id = str(data.get("out_trade_no") or "")
        external_trade_no = str(data.get("trade_no") or "")
        returned_amount = data.get("money")
        if returned_order_id != out_trade_no:
            raise ValueError("RMB order query returned a different order")
        if not external_trade_no or returned_amount in (None, ""):
            raise ValueError("RMB paid order query is missing required fields")
        normalized_amount = Decimal(str(returned_amount)).quantize(
            RMB_AMOUNT_QUANT,
            rounding=ROUND_HALF_UP,
        )
        if normalized_amount != Decimal(str(expected_amount)).quantize(
            RMB_AMOUNT_QUANT,
            rounding=ROUND_HALF_UP,
        ):
            raise ValueError("RMB paid order query amount mismatch")

        return RMBOrderQueryResult(
            status=RMBOrderQueryStatus.PAID,
            out_trade_no=returned_order_id,
            external_trade_no=external_trade_no,
            paid_amount=normalized_amount,
        )
