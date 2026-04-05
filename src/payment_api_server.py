import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
import uvicorn
from src.services.rmb_payment_service import RMBPaymentService, HUANYUY_KEY
from src.services.payment_fulfillment_service import fulfill_order

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payment_api")

app = FastAPI(title="RMB Payment Webhook API")

@app.get("/api/pay/notify/huanyuy", response_class=PlainTextResponse)
async def huanyuy_notify(request: Request):
    """
    易支付异步回调通知接口
    """
    params = dict(request.query_params)
    logger.info(f"Received notify callback: {params}")

    # 1. 验证签名
    if not RMBPaymentService.verify_callback_sign(params, HUANYUY_KEY):
        logger.error("Signature verification failed")
        return "fail"
        
    # 2. 检查支付状态
    if params.get("trade_status") != "TRADE_SUCCESS":
        logger.error(f"Trade not successful: {params.get('trade_status')}")
        return "fail"
        
    out_trade_no = params.get("out_trade_no")
    trade_no = params.get("trade_no")
    money = params.get("money")
    
    if not all([out_trade_no, trade_no, money]):
        logger.error("Missing required parameters")
        return "fail"
        
    # 3. 触发统一发货逻辑
    try:
        success = await fulfill_order(out_trade_no, trade_no, float(money))
        if success:
            logger.info(f"Order {out_trade_no} fulfilled successfully")
            return "SUCCESS"
        else:
            logger.error(f"Failed to fulfill order {out_trade_no}")
            return "fail"
    except Exception as e:
        logger.error(f"Exception in fulfillment: {e}")
        return "fail"

@app.get("/pay/result", response_class=HTMLResponse)
async def payment_result(request: Request):
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
    uvicorn.run(app, host="0.0.0.0", port=8021)
