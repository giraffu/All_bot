# TON 支付系统集成计划 (方案一：纯后端轮询查账)

## 概述
本方案采用“前端发送带用户 ID 的交易 + 后端轮询查账”的模式，实现无缝、安全的 TON 支付与自动发货闭环。无需在服务器开放额外端口，完全集成于现有的 Bot 进程中。

## 核心流程
1. 用户在 Telegram 内点击“充值”按钮，打开 Mini App (`https://pay.aivison.it.com`)。
2. 前端通过 `Telegram.WebApp` API 自动获取当前用户的 `telegram_id`。
3. 用户在 Mini App 内选择套餐并支付，前端将 `telegram_id` 作为“备注 (payload/comment)” 附加在 TON 交易中。
4. 主 Bot 的后台启动一个定时任务 (JobQueue)，每 15 秒通过公共 API (如 Toncenter) 查询收款钱包的新入账。
5. 发现新入账时，提取交易的“备注”，获取 `telegram_id`，并验证金额。
6. 验证通过后，调用现有数据库逻辑为该用户增加灵石，并推送 Telegram 消息通知用户。

---

## 具体修改步骤

### 步骤一：前端改造 (`ton_payment/frontend/index.html`)

**目标**：引入 Telegram Web App JS SDK，获取用户 ID，并在支付时将其作为 payload。

**修改内容**：
1. 在 `<head>` 中引入 Telegram Web App JS：
   ```html
   <script src="https://telegram.org/js/telegram-web-app.js"></script>
   ```
2. 在 JavaScript 初始化部分，获取用户信息：
   ```javascript
   let tgUserId = "unknown";
   if (window.Telegram && window.Telegram.WebApp) {
       const initDataUnsafe = window.Telegram.WebApp.initDataUnsafe;
       if (initDataUnsafe && initDataUnsafe.user) {
           tgUserId = initDataUnsafe.user.id.toString();
       }
   }
   ```
3. 修改 `sendTransaction` 函数，将 `tgUserId` 加入到 `messages[0].payload` 中：
   *注意：TON Connect 要求的 payload 必须是 base64 编码的 BOC (Bag of Cells)。如果只是简单文本备注，前端需要将 `tgUserId` 编码为带特定前缀的 base64。*

### 步骤二：后端验证器升级 (`ton_payment/backend/validator.py`)

**目标**：增强现有验证逻辑，使其能返回未处理的交易列表，提取备注并防止重复发货。

**修改内容**：
1. **添加已处理记录**：使用数据库表（推荐）或简单的本地文件/内存集合，记录已处理的交易 Hash，防止每次轮询重复加分。
2. **解析 Payload**：从 Toncenter API 返回的 `in_msg.message` 中提取并解码出用户的 `telegram_id`。
3. **方法重构**：将 `check_transaction` 改为 `get_new_payments(wallet_address, last_lt)`，每次只查询增量交易。

### 步骤三：主 Bot 集成 (`src/bot_test.py` 等)

**目标**：将支付入口和后台查账任务接入现有的运行环境。

**修改内容**：
1. **添加入口 UI**：在 `src/handlers/` 中处理 `/buy` 命令，发送包含 `WebAppInfo(url="https://pay.aivison.it.com")` 的 Inline Keyboard 按钮。
2. **注册定时任务**：在 Bot 启动代码（如 `post_init` 钩子）中，使用 `python-telegram-bot` 的 `JobQueue` 添加轮询任务：
   ```python
   # 伪代码示例
   async def poll_ton_payments(context: ContextTypes.DEFAULT_TYPE):
       new_payments = await validator.get_new_payments(MY_WALLET)
       for payment in new_payments:
           user_id = payment['user_id']
           amount_ton = payment['amount']
           # 计算灵石并加分
           credits_to_add = calculate_credits(amount_ton)
           await add_credits_to_db(user_id, credits_to_add)
           # 通知用户
           await context.bot.send_message(chat_id=user_id, text=f"充值成功！已增加 {credits_to_add} 灵石。")

   # 在 main 函数或 post_init 中
   application.job_queue.run_repeating(poll_ton_payments, interval=15, first=10)
   ```

---

## 需要考虑的风险与细节

1. **Payload 编码问题**：TON 网络的文本备注并不是简单的字符串，而是特定的 BOC 格式。前端生成交易时，必须正确地将纯文本 `telegram_id` 转换为 BOC base64。可以使用 `@ton/core` 库在前端实现：
   ```javascript
   import { beginCell } from "@ton/core";
   const body = beginCell()
       .storeUint(0, 32) // 0 表示纯文本注释
       .storeStringTail(tgUserId)
       .endCell();
   const payloadBase64 = body.toBoc().toString("base64");
   ```
2. **防重放攻击 (Idempotency)**：后端必须严格记录每一个已经处理过的 `transaction_hash`。如果在加分过程中崩溃，重启后不应重复加分。建议在现有的 PostgreSQL 数据库中新建一张 `payment_logs` 表。
3. **网络问题**：`Toncenter API` 的免费版有速率限制 (Rate Limit)，如果轮询过快可能会被封 IP。建议使用 API Key 或者将频率设置在 10-15 秒/次。

## 后续行动
当您确认此计划后，我们可以按步骤开始：
1. 我提供修改后的 `index.html`，您将其部署到 Cloudflare。
2. 我们在您的 PostgreSQL 中新建一张支付记录表。
3. 我帮您编写并接入轮询发货的 Python 代码。