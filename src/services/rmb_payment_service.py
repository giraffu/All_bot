import hashlib
import logging
import os

import aiohttp

logger = logging.getLogger("rmb_payment")

# 配置项，生产环境请在环境变量中设置
HUANYUY_PID = os.getenv("HUANYUY_PID", "10001") 
HUANYUY_KEY = os.getenv("HUANYUY_KEY", "your_key_here") 
HUANYUY_GATEWAY = os.getenv("HUANYUY_GATEWAY", "http://huanyuy.com/submit.php")
HUANYUY_NOTIFY_URL = os.getenv("HUANYUY_NOTIFY_URL", "https://rmb.aivison.it.com/api/pay/notify/huanyuy")
HUANYUY_RETURN_URL = os.getenv("HUANYUY_RETURN_URL", "https://rmb.aivison.it.com/pay/result")
HUANYUY_SITENAME = os.getenv("HUANYUY_SITENAME", "合欢宗账房")

class RMBPaymentService:
    @staticmethod
    def generate_sign(params: dict, key: str) -> str:
        """
        生成易支付签名
        """
        filtered_params = {
            k: str(v) for k, v in params.items()
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
        received_sign = str(params.get("sign", "")).lower()
        expected_sign = RMBPaymentService.generate_sign(params, key).lower()
        return received_sign == expected_sign

    @staticmethod
    async def create_payment_url(out_trade_no: str, plan_name: str, amount: float, pay_type: str = "alipay", return_url: str = None) -> dict:
        """
        发起支付请求，获取 pay_url
        """
        import urllib.parse
        
        params = {
            "money": f"{amount:.2f}",
            "name": plan_name,
            "notify_url": HUANYUY_NOTIFY_URL,
            "out_trade_no": out_trade_no,
            "pid": HUANYUY_PID,
            "return_url": return_url or HUANYUY_RETURN_URL,
            "sitename": HUANYUY_SITENAME,
            "type": pay_type,
        }
        
        # 易支付的签名规则：将所有参数按键名升序排列，用&拼接，然后加上key再md5
        sign_params = {k: str(v) for k, v in params.items() if v not in (None, "") and k not in ("sign", "sign_type", "return_type")}
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
                query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in submit_params.items())
                request_url = f"{HUANYUY_GATEWAY}?{query_string}"
                
                logger.info(f"Sending GET request to {request_url}")
                async with session.get(request_url, timeout=15) as resp:
                    try:
                        data = await resp.json(content_type=None)
                        logger.info(f"Payment creation response: {data}")
                        return data
                    except Exception:
                        text_resp = await resp.text()
                        logger.error(f"Failed to parse JSON response: {text_resp}")
                        return {"code": 0, "msg": "Invalid response format"}
        except Exception as e:
            logger.error(f"Error creating RMB payment: {e}")
            return {"code": 0, "msg": str(e)}
