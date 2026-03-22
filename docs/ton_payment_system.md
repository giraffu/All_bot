# TON 区块链支付系统架构与对账逻辑详解

本项目集成了一个基于 TON (The Open Network) 区块链的去中心化支付系统。为了避免暴露公开的 REST API 从而导致跨国网络延迟或复杂的 Webhook 部署，我们采用了**前端拉起支付 + 后端主动轮询对账**的无状态架构。

---

## 一、 系统架构概览

支付系统由两部分组成：
1. **前端 (Telegram Mini App)**：基于 React 部署在 Cloudflare Pages，负责渲染商品列表、计算价格，并通过 TON Connect SDK 唤起用户的 Web3 钱包进行链上签名与转账。
2. **后端 (Payment Agent)**：位于 Bot 源码 `src/services/payment_validator.py` 中，作为守护协程随 Bot 启动，主动向 TON Center RPC 节点发起轮询请求，解析链上数据并执行发货。

### 核心优势：
*   **无需公网 Webhook**：后端不需要暴露 HTTP 端口，极其适合在本地或内网环境部署的 Bot。
*   **抗篡改设计**：订单信息通过加密 BOC (Bag of Cells) 写入链上，金额由后端通过链上数据反向校验，前端无法伪造支付成功状态。

---

## 二、 核心工作流 (Data Flow)

### 1. 前端发起支付
*   用户在 Bot 内点击“💎 充值”，拉起 Web App。
*   用户选择套餐（如：基础月卡、至尊月卡）。
*   前端生成一个特定格式的明文备注：`ORDER:{tgUserId}:{planId}:{timestamp}`（例如：`ORDER:123456789:1:1710000000`）。
*   前端调用 TON Connect，将接收地址 (`VITE_MERCHANT_ADDRESS`)、支付金额和**序列化为 BOC 格式**的备注发送给钱包（如 Tonkeeper）请求签名。

### 2. 后端轮询监听 (`TonPaymentValidator.poll_transactions`)
*   Bot 启动时（`post_init` 阶段），创建一个无限循环的异步任务。
*   每隔 **15 秒**，通过 `aiohttp` 向 `https://toncenter.com/api/v2/jsonRPC` 发送 `getTransactions` 请求，拉取商家钱包地址的最新 20 条交易。
*   维护一个 `last_lt` (Logical Time) 游标，确保只处理比上次轮询更新的交易。

### 3. 解析与校验链上数据 (`_check_new_transactions`)
*   提取交易中的 `in_msg`（入账信息）。
*   如果转账金额 (`value`) <= 0，直接跳过。
*   **BOC 备注解析**：调用 `pytoniq_core` 库，从交易的 `msg_data_boc` 中反序列化出最初前端写入的 `ORDER:...` 字符串。

### 4. 核心对账与防双花逻辑 (`_process_order`)
*   **提取参数**：将 `ORDER:{tgUserId}:{planId}:{timestamp}` 切割，获得用户 ID 和套餐 ID。
*   **防双花 (Double-Spend Prevention)**：
    *   通过链上交易唯一的哈希值 `tx_hash` 查询 `orders` 表。
    *   如果 `tx_hash` 已存在，说明这笔交易已经被处理过，直接跳过（保证幂等性）。
*   **金额校验**：
    *   根据 `planId` 从数据库读取该套餐应付的 TON 金额。
    *   将链上实际收到的 `amount_nanotons` 与应付金额比对。
    *   *容错设计：允许 0.01 TON 的极小滑点或精度误差。*
    *   如果金额不足，订单标记为 `FAILED`，拦截发货；如果充足，标记为 `SUCCESS`。

### 5. 自动发货与通知 (Fulfillment)
*   如果订单状态为 `SUCCESS`，开启数据库事务进行原子更新：
    1.  **增加灵石**：`User.credits += plan.reward_credits`。
    2.  **更新身份**：将 `current_identity` 更新为套餐对应的 VIP（如：核心弟子）。
    3.  **计算并更新有效期 (残值折算系统)**：
        *   **同套餐续费**：直接在当前 `identity_expire_at` 基础上累加新套餐的 `duration_days`。
        *   **跨套餐升级/降级**：
            *   根据用户的当前身份查询老套餐定价。
            *   计算老套餐的剩余价值（残值）：`老套餐日均价 × 剩余天数`。
            *   将残值折算为新套餐的天数：`残值 ÷ 新套餐日均价`。
            *   最终到期时间 = `当前时间 + 新套餐自带天数 + 残值折算天数`。
        *   如果当前身份已过期或为免费身份，则直接从当前时间开始计算 `duration_days`。
    4.  **记录流水**：在 `user_logs` 表插入一条 `recharge` 操作日志，附带订单号和套餐名。
    5.  提交事务 (`db.commit()`)。
*   **下发通知**：通过 Telegram Bot API 主动向该 `tgUserId` 发送包含 HTML 格式的充值成功贺电。如果触发了残值折算，贺电中会明确提示**“⚖️ 老套餐残值已折算为 X 天新套餐时长”**。

---

## 三、 异常处理与容灾机制

1. **RPC 节点限流或宕机**：
   * 轮询任务被包在 `try...except` 块中，如果网络请求失败，记录 Error 日志，并在 15 秒后自动进行下一次尝试。系统不会崩溃。
2. **数据库事务回滚**：
   * 在发货的第 4 步中，如果出现数据库锁或连接异常，会触发 `await db.rollback()`，该订单本次不会被标记为已处理。由于 `last_lt` 不会更新，下一次轮询会**自动重试**这笔交易，保证用户充值不丢单。
3. **用户体验优化 (UX)**：
   * 由于区块链打包出块需要 10-30 秒，且后端轮询间隔为 15 秒，前端支付完成后不会立刻关闭页面，而是展示“Payment broadcasted, waiting for blockchain confirmation...”的加载动画，安抚用户情绪。<mccoremem id="01KM1ZDN1Q9888G1WD9VC40X7C" />
