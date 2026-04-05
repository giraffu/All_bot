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
    }
    
    # 不参与签名的字段
    exclude_sign = ["sign", "sign_type", "return_type"]
    
    # 签名计算
    sign_params = {k: str(v) for k, v in params.items() if v not in (None, "") and k not in exclude_sign}
    sorted_keys = sorted(sign_params.keys())
    sign_str = "&".join(f"{k}={sign_params[k]}" for k in sorted_keys)
    final_str = f"{sign_str}{HUANYUY_KEY}"
    print(f"Sign String: {final_str}")
    sign = hashlib.md5(final_str.encode("utf-8")).hexdigest()
    print(f"MD5 Sign: {sign}")
    
    # 最终提交的参数 (加入不参与签名的 return_type)
    submit_params = params.copy()
    submit_params["return_type"] = "json"
    submit_params["sign"] = sign
    submit_params["sign_type"] = "MD5"
    
    # 测试 POST
    async with aiohttp.ClientSession() as session:
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        async with session.post("http://huanyuy.com/submit.php", data=submit_params, headers=headers) as resp:
            text = await resp.text()
            print("POST with exclude return_type Response:")
            if "订单号" in text:
                print("Error: 订单号不能为空")
            elif "签名" in text:
                print("Error: 签名不正确")
            else:
                print(text)

if __name__ == "__main__":
    asyncio.run(test())
