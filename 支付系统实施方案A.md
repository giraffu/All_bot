# 仙侠主题 Telegram Bot 会员支付系统开发实施方案 (方案A)

## 1. 技术架构设计

本系统采用 **前后端分离 + 异步事件驱动** 架构：
*   **前端 (Telegram Mini App)**：基于 `React 19` + `Vite` + `@twa-dev/sdk` + `@tonconnect/ui-react`，负责渲染充值界面、价格计算器和唤起 TON 钱包签名。
*   **后端服务 (Python 核心后端)**：集成在现有的 Bot 服务中，增加独立的 `Pricing Engine`（定价引擎）和 `Order Service`（订单服务）。
*   **区块链交互层**：前端构造包含订单 Payload 的交易，后端通过监听/轮询 TON 区块链确认交易，确保资金安全。

### 核心模块划分：
*   **Pricing Engine (定价引擎)**：负责计算动态价格（原价 -> 叠加首充优惠 -> 叠加修仙等级折扣 -> 最终价格）。
*   **Identity Manager (身份管家)**：管理“内门弟子”、“核心弟子”、“真传弟子”的身份授予与过期逻辑。

---

## 2. 数据库表结构设计 (PostgreSQL + SQLAlchemy)

为了支持灵活的定价和动态折扣，需新增/修改以下数据表：

**1. `membership_plans` (会员套餐配置表)**
| 字段名 | 类型 | 说明 | 方案A初始数据 |
| :--- | :--- | :--- | :--- |
| `id` | INT (PK) | 套餐ID | 1, 2, 3 |
| `name` | VARCHAR | 套餐名称 | 基础月卡, 高级月卡, 至尊月卡 |
| `identity_name` | VARCHAR | 修仙身份 | 内门弟子, 核心弟子, 真传弟子 |
| `price_ton` | DECIMAL(10,2) | 基础价格(TON) | 1.99, 4.99, 9.9 |
| `reward_credits` | INT | 赠送灵石数量 | 400, 1200, 3000 |
| `duration_days` | INT | 有效期 | 30 |

**2. `discount_rules` (动态折扣规则表)**
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `rule_type` | VARCHAR | 规则类型（如: `FIRST_CHARGE`, `LEVEL_DISCOUNT`） |
| `target_level` | VARCHAR | 适用的修仙等级（如: `化神期`） |
| `discount_rate` | DECIMAL(3,2) | 折扣率（如 0.85 代表 8.5折，0.5 代表 5折） |
| `is_active` | BOOLEAN | 是否启用 |

**3. `orders` (充值订单流水表)**
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `order_id` | VARCHAR (PK)| 唯一订单号（用于生成 TON 交易 Payload） |
| `telegram_id` | BIGINT | 用户 TG ID |
| `plan_id` | INT (FK) | 购买的套餐ID |
| `original_price` | DECIMAL | 原价 |
| `final_price` | DECIMAL | 实际应付价格（动态计算后） |
| `status` | VARCHAR | `PENDING` (待支付), `SUCCESS` (已完成), `FAILED` |
| `tx_hash` | VARCHAR | TON 链上交易哈希（成功后记录） |

**4. `users` (扩展现有的用户表)**
新增字段：`current_identity` (当前身份：凡人/内门/核心/真传)，`identity_expire_at` (身份过期时间)，`is_first_charge` (是否首充)。

---

## 3. API接口定义与业务逻辑实现

后端将提供以下 RESTful API 供 Mini App 调用：

### 3.1 价格与套餐查询 (`GET /api/memberships/plans`)
*   **请求头**：携带 Telegram `initData` 以校验身份并提取 `telegram_id`。
*   **业务逻辑**：
    1. 查询 `membership_plans` 获取基础套餐配置 (1.99 / 4.99 / 9.9)。
    2. 查询用户的 `is_first_charge` 和 `修仙等级`。
    3. 调用 **Pricing Engine** 计算每个套餐的最终价格。
*   **响应示例**：返回各套餐的原价、折后价、赠送灵石、适用折扣说明（如：“已触发首充5折”）。

### 3.2 创建订单 (`POST /api/orders/create`)
*   **入参**：`plan_id`。
*   **业务逻辑**：生成唯一 `order_id`，按实时价格锁定 `final_price`，状态记为 `PENDING`。将 `order_id` 转换为 BOC 编码作为返回的 `payload`。
*   **出参**：`order_id`, `amount_nanotons`, `merchant_address`, `payload_boc`。

### 3.3 交易状态轮询/Webhook (`POST /api/orders/webhook`)
*   **业务逻辑**：
    1. 接收链上交易确认，解析 Payload 获取 `order_id`。
    2. 校验转账金额是否与 `final_price` 匹配。
    3. 校验通过后，更新订单状态为 `SUCCESS`。
    4. 调用现有服务：给用户发放灵石（+400/1200/3000），更新 `current_identity` 为对应的弟子身份，设置 30 天过期时间。
    5. 通过 Bot 下发 Telegram 消息：“🎉 恭喜道友，成功晋升【核心弟子】，1200 灵石已入账！”

---

## 4. 前端界面开发 (React Mini App)

界面需契合“修仙”国风主题，采用暗黑/金配色。

*   **页面一：会员方案展示区 (Pricing Plans)**
    *   采用三张精美的横向/纵向卡片，分别展示“内门弟子”、“核心弟子”、“真传弟子”。
    *   高亮显示：对应的灵石收益（400/1200/3000）和当月价格。
*   **页面二：动态价格计算器 (Price Calculator)**
    *   当用户选中某个套餐时，下方弹出计算器明细。
    *   例如：选中“核心弟子” -> 显示原价 4.99 TON -> 显示“首充半价 (-2.49 TON)” -> 显示最终支付 2.49 TON。
*   **页面三：权益对比表格 (Comparison Table)**
    *   实现一个可折叠的对比视图，清晰列出不同身份的特权差异（例如：排队优先级、生成清晰度、赠送积分等）。
*   **支付交互**：
    *   底部悬浮固定按钮：`[ 唤起 TON 钱包支付 2.49 TON ]`。
    *   处理 `tonConnectUI.sendTransaction` 的回调状态（Loading 态、成功动画、失败提示）。

---

## 5. 测试策略

*   **单元测试 (Unit Testing)**：
    *   重点测试 **Pricing Engine**：编写多组测试用例，覆盖“纯首充”、“无首充但有修仙等级折扣”、“两者叠加”等场景，确保浮点数计算精度无误。
    *   测试 BOC Payload 生成与解析算法。
*   **集成测试 (Integration Testing)**：
    *   模拟 Telegram `initData` 请求，测试前端到后端的 API 链路。
    *   在 TON Testnet（测试网）完成全链路测试：前端发交易 -> 测试网出块 -> 后端验证 -> 数据库发货。
*   **性能测试 (Performance Testing)**：
    *   使用 `Locust` 或 `JMeter` 模拟高并发查询价格接口。
    *   针对 RPC 轮询机制，测试在高并发订单下的表现，确保不触发 TON Center 的 HTTP 429 限制。

---