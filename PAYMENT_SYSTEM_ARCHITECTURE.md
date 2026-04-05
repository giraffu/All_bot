# All_bot 支付系统架构与发货指南

本文档全面梳理了当前机器人项目中并存的三套支付体系（TON、Telegram Stars、人民币/易支付），并详细说明了订单状态流转、身份折算规则以及代码分布情况，作为后续维护与二次开发的参考依据。

---

## 1. 支付体系总览

系统目前支持以下三种充值方式，所有充值套餐均读取自 PostgreSQL 的 `membership_plans` 表。不同支付方式在“建单时机”、“回调监听”和“发货处理”上存在差异，但最终都会归拢到统一的数据库落库标准。

| 支付通道 | 前端入口 | 定价字段 | 订单创建时机 | 异步通知方式 | 发货逻辑位置 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TON 区块链** | 内嵌 WebApp | `price_ton` | 轮询查到交易后建单 | 内部定时器 `poll_transactions` 轮询 | `payment_validator.py` |
| **Telegram Stars** | 原生 Invoice | `price_stars` | 收到成功回调后建单 | Telegram 原生 `successful_payment` | `payment_handler.py` |
| **RMB (易支付)** | Inline 按钮 | `price_rmb` | **用户点击前预建单** (`PENDING`) | 独立 FastAPI 接收 HTTP `GET` | `payment_fulfillment_service.py` |

---

## 2. 核心业务规则 (发货与折算逻辑)

当用户支付成功后，系统会进行身份升降级和天数折算。当前采用的权数为：
- 外门弟子：1
- 内门弟子：2
- 核心弟子：5
- 真传弟子：10

### 2.1 灵石直充 (`duration_days == 0`)
- **逻辑**：仅增加 `credits`，不改变用户当前的身份级别，也不改变当前的身份到期时间 (`identity_expire_at`)。
- **注意**：目前 TON 体系并未在 WebApp 中提供直充套餐，因此 TON 代码未包含此防御逻辑。Stars 和 RMB 均完美支持直充逻辑。

### 2.2 同级续费
- **逻辑**：若购买的新套餐与当前身份相同，则在当前到期时间的基础上直接累加 `duration_days`。

### 2.3 升级 (购买更高级别套餐)
- **逻辑**：将当前身份的**剩余天数**，按权数比例折算为新身份的天数，然后加上新买套餐的天数。
- **公式**：`新到期时间 = 现在 + 新买天数 + ceil(剩余天数 * 旧权数 / 新权数)`
- **效果**：用户立刻获得高级身份，且不损失之前充值的残余价值。

### 2.4 降级或跨级购买 (保护机制)
- **逻辑**：若购买的套餐级别**低于**当前身份，系统会**拒绝降级**。保持用户的当前高级身份不变，将新买的低级天数折算给高级身份。
- **公式**：`新到期时间 = 原有到期时间 + ceil(新买天数 * 新买权数 / 当前高级权数)`

---

## 3. 人民币 (RMB) 支付体系深度解析

作为最新接入且架构最规范的通道，RMB 支付采用了**标准异步网关模式**，具有最强的健壮性和扩展性。

### 3.1 架构数据流
1. **预建单**：用户在 Bot 中点击“支付宝/微信付款”时，系统立即在 `orders` 表插入一条 `status="PENDING"` 的记录。`tx_hash` 临时使用内部订单号规避唯一键冲突。
2. **拉起支付**：通过 `rmb_payment_service.py` 生成易支付签名，并向网关发送 `GET` 请求获取带 `urlencode` 的 `pay_url`。
3. **异步发货**：独立部署的 `payment-api` 容器监听 8021 端口（配置了 CF Tunnel）。当收到 `TRADE_SUCCESS` 时，调用 `payment_fulfillment_service.py` 进行严格的金额校验、签名校验和幂等判断。
4. **统一通知**：发货完成后，主动通过 Telegram API 给用户发送 HTML 格式的到账提醒和折算明细。

### 3.2 部署与环境变量
RMB 支付依赖以下环境变量（配置在 `.env` 中）：
```env
HUANYUY_PID=10337
HUANYUY_KEY=你的易支付密钥
HUANYUY_GATEWAY=http://huanyuy.com/submit.php
HUANYUY_NOTIFY_URL=https://<你的域名>/api/pay/notify/huanyuy
HUANYUY_RETURN_URL=https://<你的域名>/pay/result
```

---

## 4. 后续维护与架构优化建议

1. **统一发货收口**：
   目前 TON 和 Stars 都有自己独立的发货代码块。在后续的版本迭代中，建议将它们统统重构为调用 `src/services/payment_fulfillment_service.py`，彻底消灭重复代码，确保三种支付手段共享同一套“升降级折算”标准。
2. **Stars 支付的竞态条件**：
   Stars 支付是在收到 Telegram 成功回调时才建单。虽然 Telegram 并发几率极低，但在高并发场景下存在通过查询 `tx_hash` 阻断不及时而导致“双花”的风险。建议后续改造为像 RMB 支付一样的“发起支付前先建 `PENDING` 单”。
3. **下线旧通道**：
   如果未来决定下线 Stars 或 TON 支付，只需在 `src/handlers/message_handler.py` 和 `src/handlers/callback_handler.py` 中移除对应的 InlineKeyboardButton 即可，后端代码可完全保留互不干扰。