import asyncio
import aiohttp
import hashlib

async def test():
    HUANYUY_PID = "10337"
    HUANYUY_KEY = "35uholim2ymkntjphievarfufqjpa9k5"
    
    params = {
        "money": "30.00",
        "name": "200 Star",
        "notify_url": "https://rmb.aivison.it.com/api/pay/notify/huanyuy",
        "out_trade_no": "RMB_8626302135_5_1775271408",
        "pid": HUANYUY_PID,
        "return_url": "https://rmb.aivison.it.com/pay/result",
        "sitename": "合欢宗账房",
        "type": "wxpay",
        "return_type": "json"
    }
    
    # 签名计算
    sign_params = {k: str(v) for k, v in params.items() if v not in (None, "") and k not in ("sign", "sign_type")}
    sorted_keys = sorted(sign_params.keys())
    sign_str = "&".join(f"{k}={sign_params[k]}" for k in sorted_keys)
    final_str = f"{sign_str}{HUANYUY_KEY}"
    print(f"Sign String: {final_str}")
    sign = hashlib.md5(final_str.encode("utf-8")).hexdigest()
    print(f"MD5 Sign: {sign}")
    
    params["sign"] = sign
    params["sign_type"] = "MD5"
    
    # 测试 POST
    async with aiohttp.ClientSession() as session:
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        async with session.post("http://huanyuy.com/submit.php", data=params, headers=headers) as resp:
            text = await resp.text()
            print("POST with URL-encoded Response:")
            if "订单号" in text:
                print("Error: 订单号不能为空")
            elif "签名" in text:
                print("Error: 签名不正确")
            else:
                print(text[:200])

if __name__ == "__main__":
    asyncio.run(test())
