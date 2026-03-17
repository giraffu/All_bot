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
3. **汇率波动**：TON 价格波动较大，建议商品定价以 USD (USDT) 为锚定，动态换算 TON 数量，或者直接使用固定额度的法币定价。