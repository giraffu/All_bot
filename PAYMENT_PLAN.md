# Telegram Bot 支付系统实现方案

## 1. 方案概述

本方案旨在为 Telegram Bot 集成支付功能，实现虚拟货币（灵石/积分）的充值。根据需求，系统将支持三种支付方式：
- **Telegram Stars (XTR)**: Telegram 原生内置的虚拟货币，用户体验最流畅。
- **TON**: 通过 `@CryptoBot` (Crypto Pay API) 支持原生 TON 支付。
- **USDT-TON**: 通过 `@CryptoBot` (Crypto Pay API) 支持 TON 链上的 USDT 支付。

整体架构采用**异步解耦**设计，支付服务独立于现有的核心业务，通过 `PaymentService` 统一管理账单，并在支付成功后通过 `PermissionService` 的 `add_credits` 为用户增加额度。

---

## 2. 依赖与配置准备

### 2.1 新增依赖
```bash
# 安装 Crypto Pay 的官方异步 Python SDK
pip install aiocryptopay
```

### 2.2 环境变量配置 (`.env`)
```env
# Crypto Pay 申请的 API Token (通过 @CryptoBot 申请)
CRYPTO_PAY_TOKEN=123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ
# 当前环境：testnet 或 mainnet
CRYPTO_PAY_NETWORK=mainnet
# 用于接收 Crypto Pay 回调的 Webhook (生产环境推荐) 或使用长轮询
```

*(注：Telegram Stars 支付直接使用现有的 Bot Token，无需额外申请配置)*

---

## 3. 数据库设计 (新增表)

在 `src/database/models.py` 中新增 `Payment` (账单) 表，用于记录每一笔支付状态，保证**幂等性**（防止重复加分）。

```python
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Float
from datetime import datetime

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True, nullable=False)
    
    # 支付渠道：'stars', 'crypto_pay_ton', 'crypto_pay_usdt'
    provider = Column(String(50), nullable=False)
    
    # 外部账单ID (Telegram Stars 对应的 provider_payment_charge_id 或 Crypto Pay 的 invoice_id)
    invoice_id = Column(String(100), unique=True, nullable=False)
    
    # 支付金额与货币类型
    amount = Column(Float, nullable=False)
    currency = Column(String(20), nullable=False) # 'XTR', 'TON', 'USDT'
    
    # 兑换的本站积分/灵石数量
    credits_amount = Column(Integer, nullable=False)
    
    # 支付状态: 'pending', 'paid', 'expired'
    status = Column(String(20), default='pending', index=True)
    
    created_at = Column(DateTime, default=datetime.now)
    paid_at = Column(DateTime, nullable=True)
```

---

## 4. 核心模块开发

### 4.1 支付服务层 (`src/services/payment_service.py`)

统一负责生成账单和处理支付回调。

**功能点**：
1. **`create_stars_invoice(user_id, amount, credits)`**: 调用 `python-telegram-bot` 的 `context.bot.send_invoice` 接口生成 Stars 账单。
2. **`create_crypto_invoice(user_id, asset, amount, credits)`**: 调用 `aiocryptopay` SDK 的 `create_invoice` 方法生成 TON 或 USDT 账单，返回支付链接。
3. **`process_payment_success(invoice_id)`**: 支付成功的回调处理，包含更新 `Payment` 表状态，调用 `UserLog` 记录日志，并为对应 `User` 增加积分。

### 4.2 支付交互层 (`src/handlers/payment_handler.py`)

处理用户的 UI 交互（命令、按钮）。

1. **入口命令 `/buy` 或 `/topup`**:
   - 展示商品列表（Inline Keyboard），例如：
     - `[ 💰 100 灵石 - 100 Stars ]`
     - `[ 💎 500 灵石 - 1 TON ]`
     - `[ 💵 1000 灵石 - 5 USDT ]`
2. **处理按钮回调 (`CallbackQueryHandler`)**:
   - 如果用户选择 Stars，直接下发 Telegram Invoice 消息。
   - 如果用户选择 TON/USDT，调用 Crypto Pay API 生成 URL，并下发带有 `[ 点击前往支付 ]` URL 按钮的消息。
3. **Stars 支付的特殊处理器**:
   - `PreCheckoutQueryHandler`: 必须在 10 秒内响应 `answer_pre_checkout_query(ok=True)`。
   - `MessageHandler(filters.SUCCESSFUL_PAYMENT)`: 接收 Stars 支付成功的消息，调用业务层发货。

### 4.3 Crypto Pay 回调处理

Crypto Pay 有两种状态同步方式，根据服务器环境二选一：
- **方案 A (长轮询 Polling - 适合无公网 IP/开发环境)**: 在 Bot 启动时，启动一个后台 asyncio Task，使用 `crypto.get_invoices(status='paid')` 定期轮询未处理的订单。
- **方案 B (Webhook - 适合生产环境)**: 结合 `FastAPI` 或 `aiohttp` 提供一个 `POST /crypto-webhook` 接口，接收 `@CryptoBot` 发来的异步通知，验签后处理。

---

## 5. 执行计划路线图

### 第一阶段：基础设施 (1天)
- [ ] 申请 `@CryptoBot` 应用 Token (测试网和主网各一份)。
- [ ] 修改 `models.py` 增加 `Payment` 实体，并生成迁移/建表脚本。
- [ ] 引入 `aiocryptopay` 依赖并配置环境变量。

### 第二阶段：支付核心逻辑 (1-2天)
- [ ] 编写 `src/services/payment_service.py`。
- [ ] 封装 Crypto Pay SDK 的初始化。
- [ ] 封装与 `PermissionService` 的联动（加分、记录 UserLog）。

### 第三阶段：Telegram UI 与交互 (1天)
- [ ] 编写 `payment_handler.py`，实现商品列表的 Inline Keyboard。
- [ ] 接入 Telegram Stars `send_invoice` 流程和相关的 Handlers。
- [ ] 接入 Crypto Pay 的 URL 按钮下发。

### 第四阶段：测试与安全审计 (1天)
- [ ] **幂等性测试**：确保多次收到同一账单的成功回调，只会加一次分。
- [ ] **沙盒测试**：使用 Testnet Crypto Bot 模拟 TON/USDT 支付。使用 Telegram 测试环境模拟 Stars 支付。
- [ ] **并发安全**：在处理充值更新时使用数据库行锁 (e.g., `with_for_update()`)。

---

## 6. 安全与注意事项
1. **幂等性防刷**：回调接口在增加积分前，必须使用 `SELECT ... FOR UPDATE` 检查 `Payment.status` 是否已是 `paid`。
2. **Stars 提现规则**：Telegram Stars 的变现周期为 21 天，并且会收取平台手续费（约 30% 到 5% 不等，通过 Fragment 提取），请在定价时考虑到这部分成本。
---

## 7. 补充方案：Trust Wallet 收款方案

如果您希望用户使用 **Trust Wallet**（或其他去中心化钱包如 MetaMask、TP 钱包）来向您付款，这与 Crypto Pay 的中心化网关模式完全不同。Trust Wallet 是**去中心化自托管钱包**，这意味着我们需要直接与区块链网络交互。

针对 Trust Wallet 收款，有以下三种常见方案，可根据您的开发精力和对**手续费**的容忍度进行选择：

### 方案 A：原生链上转账 + TxID 凭证（最轻量、0 抽成，推荐初期使用）
*   **交互流程**：
    1. 用户在 Bot 点击购买，Bot 下发您的**固定收款地址**（如 TRC20 或 BEP20 地址）。
    2. 用户打开 Trust Wallet，向该地址转账 USDT。
    3. 用户将转账成功的 **交易哈希 (TxID)** 发给 Bot。
    4. Bot 调用区块链浏览器 API (如 TronGrid / BscScan)，验证该 TxID：
        - 是否属于您的收款地址。
        - 交易是否成功 (SUCCESS)。
        - 金额是否满足。
        - **最重要**：检查该 TxID 是否在 `Payment` 表中已被使用过（防重放攻击）。
    5. 验证通过，自动为用户增加灵石。
*   **优点**：资金 100% 直达您的钱包，无需任何第三方抽成，无账期。
*   **缺点**：用户体验有轻微割裂，需要用户手动复制并发送 TxID。

### 方案 B：使用第三方聚合网关 (如 NowPayments / Plisio)（最省心、体验最好）
*   **交互流程**：
    1. Bot 调用网关 API 创建账单，给用户返回一个支付链接。
    2. 用户点击链接打开网页，可以选择连接 Trust Wallet 支付，或者扫码转账。
    3. 用户支付后，网关会通过 Webhook 通知您的 Bot。
    4. Bot 收到 Webhook，为用户加分。
    5. 网关会自动将这笔 USDT 结算到您绑定的 Trust Wallet 地址。
*   **优点**：开发体验与 Crypto Pay 几乎一致，支持各种币种，用户体验极佳。
*   **缺点**：第三方网关会收取约 `0.5% - 1%` 的手续费，且提现可能有最小额度限制。

### 方案 C：为每个用户生成专属地址 / HD 钱包（开发成本最高，不推荐初期使用）
*   **交互流程**：
    1. Bot 基于一套助记词，为每个点击充值的用户动态派生出一个独一无二的收款地址。
    2. 后台启动一个定时任务，轮询所有分配出去的地址的余额变动。
    3. 只要该地址收到款，就给对应用户加分。
*   **优点**：用户只需打款，无需提供 TxID，全自动化。
*   **缺点**：开发非常复杂，且资金分散在大量小地址中。后续您需要将资金归集到主钱包时，还要额外花费大量 Gas (如 TRX / BNB) 作为网络手续费。

---

## 8. 补充方案：支付宝/微信收款方案

针对中国大陆用户的支付习惯，接入支付宝（Alipay）和微信支付（WeChat Pay）是提升转化率的关键。然而，由于 Telegram Bot 业务的特殊性（特别是涉及 AI 生成、NSFW 内容或跨境服务），直接申请官方接口门槛极高且容易被封禁。

以下是适用于 Telegram Bot 的四种支付宝/微信收款方案，按推荐程度排序：

### 方案 A：使用第三方免签/四方支付平台（推荐度：⭐⭐⭐⭐，最适合独立开发者）
*   **交互流程**：
    1. 注册第三方支付平台（如“易支付”系列、V免签 等）。
    2. Bot 调用平台的 API 生成支付链接（包含商品金额、Bot 订单号等参数）。
    3. 用户点击链接跳出 Telegram，在浏览器中打开收银台页面，选择支付宝或微信扫码/拉起 App 支付。
    4. 支付成功后，第三方平台通过 Webhook（异步通知）向您的 Bot 发送 `trade_status=TRADE_SUCCESS` 的通知。
    5. Bot 验签通过后，为用户增加灵石。
*   **优点**：开发极其简单（与接第三方加密网关类似），全自动化发货。无需企业资质。
*   **缺点**：
    1. **跑路风险**：这类平台鱼龙混杂，资金不过自己手，建议找“T+0”（秒结算）或信誉好的平台，且账户内不要留存过多资金。
    2. **费率较高**：通常会收取 2% - 5% 不等的手续费。
    3. **域名风控**：支付链接容易被微信/支付宝拦截，可能需要频繁更换入口域名。

### 方案 B：使用个人免签监控方案 (V免签 原理)（推荐度：⭐⭐⭐，资金绝对安全）
*   **交互流程**：
    1. 开发者自己在服务器上部署一套开源的“免签系统”（如 V免签）。
    2. 开发者在自己的一台安卓备用机上安装监控 App，并保持支付宝/微信常驻后台。
    3. 用户在 Bot 中点击购买，Bot 从您的系统中获取一张**您个人支付宝/微信的收款码**发给用户。
    4. 用户扫码转账到您的个人账户。
    5. 备用机上的监控 App 捕捉到“支付宝/微信到账通知”，将金额和时间上报给您的系统。
    6. 系统匹配订单金额，通知 Bot 自动发货。
*   **优点**：资金 **100% 直达您的个人账户**，0 手续费，无跑路风险。
*   **缺点**：
    1. 必须有一台安卓备用机 24 小时开机联网监控通知，运维成本高。
    2. 如果同一金额并发极高，容易匹配错订单（通常系统会要求用户支付如 `9.91`, `9.92` 等带小数的金额来区分订单）。
    3. 收款频繁可能导致个人支付宝/微信账号被风控限制收款。

### 方案 C：发卡网/卡密兑换模式（推荐度：⭐⭐⭐⭐，最稳妥合规）
*   **交互流程**：
    1. 开发者在第三方发卡平台（如 面包多、爱发卡 等）上架虚拟商品（如“100 灵石兑换码”）。
    2. 发卡平台原生支持极其稳定的支付宝/微信支付通道。
    3. 用户在 Bot 中点击购买，Bot 回复发卡网的商品链接。
    4. 用户在发卡网完成购买，获取一串**卡密**（CDK，如 `ABCD-1234-EFGH`）。
    5. 用户回到 Telegram Bot，输入 `/redeem ABCD-1234-EFGH`。
    6. Bot 校验卡密有效性后，销毁卡密并为用户增加灵石。
*   **发卡平台推荐**：
    *   **面包多 (mianbaoduo.com)**：**极其推荐！** 创作者平台，极其合规、稳定，绝不跑路。原生支持微信/支付宝，页面好看转化率高。缺点是手续费约 5% 左右。
    *   **自建发卡网 (独角数卡 + 虎皮椒/易支付)**：如果你懂一点技术，可以在服务器上部署开源的 `独角数卡 (Duojiao Shuka)`，然后对接 `虎皮椒` 这种正规的个人支付接口（钱直接进你的微信/支付宝）。**自由度最高，无跑路风险**。
    *   **传统发卡网 (如 1号发卡 / 爱发卡)**：专门做卡密售卖的平台，功能齐全，但这类平台鱼龙混杂，务必找老牌平台，且**必须做到天天提现，绝不把钱留在平台过夜**。
*   **优点**：将“收款”与“Bot 业务”完全物理隔离，Bot 代码极其简单（只需做卡密验证），无需处理复杂的支付回调和掉单问题。发卡网通常支持非常稳定和官方的支付宝/微信通道。
*   **缺点**：用户体验有割裂感（需跳出 Bot 购买，再回来复制粘贴），多了一步操作。

### 方案 D：申请官方支付接口（企业级）（推荐度：⭐，门槛最高）
*   **交互流程**：
    以企业主体的身份，向支付宝开放平台（或微信支付商户平台）申请“当面付”、“手机网站支付”或“电脑网站支付”接口。Bot 直接调用官方 SDK 生成账单。
*   **优点**：费率极低（0.6%），最稳定，资金绝对安全。
*   **缺点**：
    1. 需要真实的**营业执照**。
    2. 业务审核极其严格，一旦发现用于虚拟货币、VPN、NSFW 或违规 AI 生成服务，会立刻被冻结商户号和资金。不适合绝大多数独立开发者。

### 方案 E：高匿名性收款方案 (适合涉及敏感业务/灰产的 Telegram Bot)

如果您的业务属于不希望留下任何实名痕迹（如：不需要绑定本人身份证、银行卡，不怕被追查溯源），并且**同时要求必须支持微信/支付宝收款**，您可以考虑以下高匿名方案：

#### 1. 匿名易支付 + USDT 结算 (推荐度：⭐⭐⭐⭐)
*   **原理**：市面上有许多由海外团队或灰产团队运营的“易支付”平台。这类平台**完全不需要你实名认证**（用邮箱或假信息即可注册）。买家用微信/支付宝付款给平台，平台将人民币按汇率转换成 **USDT (泰达币)** 结算到您的去中心化钱包（如 Trust Wallet / TRON 地址）。
*   **优点**：
    *   **极高匿名性**：切断了法币（人民币）到你真实身份的最后一步。哪怕买家报警，查到的也只是代收平台的账号，查不到您本人。
    *   **买家体验好**：买家依然是正常扫码用微信/支付宝付钱。
*   **缺点**：
    *   **跑路风险极高**：这类平台通常游走在法律边缘，寿命极短，随时可能卷款跑路。
    *   **手续费高昂**：通常会有 `5% - 10%` 的手续费，外加 USDT 提现的矿工费。
    *   **操作建议**：**必须选择支持 D+0（当天结算）或满几十U自动提现的平台，绝不在平台内留钱！** (可通过 Telegram 搜索“易支付 USDT 结算”找到此类平台)。

#### 2. 自建独角数卡 + V免签/监控App (推荐度：⭐⭐⭐，防跑路但稍有痕迹)
*   **原理**：你自己购买一台海外服务器，部署“独角数卡”发卡网。然后在淘宝买一套别人实名过的“微信/支付宝小号”，在二手安卓手机上挂上 `V免签` 的监控脚本。
*   **优点**：钱进的是那个买来的小号里，平台不抽成，也不怕第三方跑路。
*   **缺点**：如果买家去微信/支付宝投诉，那个小号很容易被封。你需要不断购买新的小号（黑产常说的“买码”或“跑分”模式），维护成本极高。

#### 3. 彻底放弃法币，纯 Crypto 支付 (推荐度：⭐⭐⭐⭐⭐，终极答案)
*   **原理**：彻底关掉微信/支付宝通道，只允许用户使用 TON、USDT 或 Telegram Stars 充值（即回到我们最初的 Crypto Pay 或 Trust Wallet 方案）。
*   **现实情况**：在 Telegram 生态里，那些真正涉及黑灰产、搞颜色的头部大 Bot（如各种脱衣 Bot、社工库 Bot），**几乎清一色只收 Crypto 或 Stars**。他们宁可牺牲掉一部分没有加密货币的“小白用户”，也绝对不碰支付宝和微信，这是他们生存的底线。