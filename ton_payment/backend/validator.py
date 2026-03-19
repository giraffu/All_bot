import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class TonPaymentValidator:
    def __init__(self, api_base: str = "https://toncenter.com/api/v2/jsonRPC"):
        self.api_base = api_base
        
    async def check_transaction(self, wallet_address: str, amount_nanotons: int, comment: str) -> bool:
        """
        验证指定钱包是否收到了特定金额和备注的交易
        :param wallet_address: 您的收款钱包地址
        :param amount_nanotons: 期望收到的金额（单位：nanotons）
        :param comment: 期望的备注（订单号）
        :return: 是否找到匹配的交易
        """
        async with aiohttp.ClientSession() as session:
            try:
                # 获取最近的交易记录
                payload = {
                    "method": "getTransactions",
                    "params": {
                        "address": wallet_address,
                        "limit": 10,
                        "archival": True
                    },
                    "id": 1,
                    "jsonrpc": "2.0"
                }
                
                async with session.post(self.api_base, json=payload) as resp:
                    data = await resp.json()
                    
                    if "result" not in data:
                        logger.error(f"Failed to fetch transactions: {data}")
                        return False
                        
                    transactions = data["result"]
                    
                    for tx in transactions:
                        in_msg = tx.get("in_msg", {})
                        if not in_msg:
                            continue
                            
                        # 检查金额
                        if int(in_msg.get("value", 0)) != amount_nanotons:
                            continue
                            
                        # 检查备注 (通常在 message -> body -> value -> text)
                        msg_data = in_msg.get("message", "")
                        # 注意：实际解析需要解码 BOC 或使用更高级的库如 pytoniq
                        # 这里是一个简化示例，假设 API 返回了解码后的 message
                        if comment in str(in_msg): 
                            return True
                            
                    return False
            except Exception as e:
                logger.error(f"Error validating payment: {e}")
                return False

# 示例用法
# validator = TonPaymentValidator()
# is_paid = await validator.check_transaction("EQ...", 1000000000, "ORDER_123")
