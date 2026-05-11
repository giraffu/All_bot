# 分享赚灵石（联盟系统）基础数据结构与清洗方案

本方案旨在为“分享赚灵石”的后续提现与转换功能夯实底层数据基础。此次实施**不涉及任何前端（Bot/Web）的 UI 交互与业务入口暴露**，专注于数据库表结构的演进、核心计费 API 的封装，以及对历史订单佣金的彻底清洗与固化，从而根除汇率波动导致的资产倒挂风险。

---

## 🚨 核心风险与应对策略 (Critical Risks & Solutions)

1. **汇率波动导致资产倒挂 (致命缺陷)**
   * **问题**：若实时计算历史佣金，汇率下跌会导致用户的可用余额缩水甚至出现负数。
   * **策略**：引入**佣金固化机制**。在订单表新增 `commission_usdt` 字段。所有历史与未来订单，均在满足条件时立刻计算并永久记录其产生的 USDT 佣金，后续查询仅进行 `SUM` 累加。
2. **ACID 事务割裂与并发超卖**
   * **问题**：现有的 `quota_manager.deduct_credits` 在内部强绑定了 `AsyncSessionLocal`，无法支持外部透传 `session`，导致扣减 USDT 余额与增加灵石/发放身份无法保证在同一个事务中完成。
   * **策略**：在新建的 `billing_core.py` 中封装纯净的数据库操作函数（如 `add_credits_with_session` 和 `grant_membership_with_session`），强制要求透传 `session`，结合 Redis 并发锁防止超卖。
3. **发货与佣金计算逻辑分散**
   * **问题**：RMB 易支付、TON 链上支付、Telegram Stars 的发货回调分散在三个不同的文件中，极易漏算佣金。
   * **策略**：将“首单判定及佣金计算”逻辑抽离为公共方法，并要求在现存的三个发货入口同步调用。

---

## 一、 数据库结构演进 (Alembic Migration)

必须通过 Alembic 创建新的迁移脚本（Migration），一次性完成字段新增、新表创建及历史数据的清洗。

### 1. 固化订单佣金 (修改 `orders` 表)
在 `orders` 表中新增 `commission_usdt` 字段，用于永久固化该笔订单产生的联盟收益。
* **字段定义**：`commission_usdt = Column(DECIMAL(10, 4), default=0)`

### 2. 新增流水表：`affiliate_transactions` (为未来转换做准备)
记录所有后续发生的收益转换与提现请求。
```python
class AffiliateTransaction(Base):
    __tablename__ = "affiliate_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True) # 对齐 User.id 的 BigInteger
    amount_usdt = Column(DECIMAL(10, 4), nullable=False) # 消耗的 USDT 金额
    transaction_type = Column(String(50), nullable=False) # CONVERT_CREDITS, CONVERT_IDENTITY, WITHDRAW
    status = Column(String(20), default="PENDING") # PENDING, SUCCESS, REJECTED
    details = Column(JSON, nullable=True) # 存储 plan_id, wallet_address 等附加信息
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
```

---

## 二、 历史存量数据清洗规范 (Data Migration)

**核心原则：仅给历史被邀请人的首单补发现金佣金。**
在同一个 Alembic 迁移脚本的 `upgrade()` 阶段，执行原生 SQL 进行数据清洗。

### 1. 清洗规则
* **目标群体**：`orders.telegram_id` 在 `referrals.invitee_id` 中存在记录的用户。
* **首单判定**：筛选出上述用户状态为 `SUCCESS` 且 `original_price > 0` 的订单中，按 `created_at` 排序的**第一笔**订单。
* **汇率折算规则** (基于 `src.exchange_rates` 固化)：
  * **RMB 订单** (标识: `order_id` 类似 `RMB_%`)：`commission_usdt = original_price * (1.0 / 6.7) * 0.10`
  * **Stars 订单** (标识: `order_id` 类似 `XTR_%` 或 `original_price >= 100`)：`commission_usdt = original_price * 0.013 * 0.10`
  * **TON 订单** (标识: 其他情况)：`commission_usdt = original_price * 1.4 * 0.10`
* **非首单处理**：不符合上述条件的订单，其 `commission_usdt` 保持为 `0`。

### 2. 清洗 SQL 示例思路 (PostgreSQL/SQLite 通用逻辑)
```sql
-- 在 Alembic upgrade 中执行
WITH FirstOrders AS (
    SELECT 
        o.id as order_pk,
        o.order_id,
        o.telegram_id,
        o.original_price,
        ROW_NUMBER() OVER(PARTITION BY o.telegram_id ORDER BY o.created_at ASC) as rn
    FROM orders o
    JOIN referrals r ON o.telegram_id = r.invitee_id
    WHERE o.status = 'SUCCESS' AND o.original_price > 0
)
UPDATE orders
SET commission_usdt = 
    CASE 
        WHEN fo.order_id LIKE 'RMB_%' THEN fo.original_price * (1.0 / 6.7) * 0.10
        WHEN fo.order_id LIKE 'XTR_%' OR fo.original_price >= 100 THEN fo.original_price * 0.013 * 0.10
        ELSE fo.original_price * 1.4 * 0.10
    END
FROM FirstOrders fo
WHERE orders.id = fo.order_pk AND fo.rn = 1;
```

---

## 三、 核心层代码适配与封装 (Core Logic Adjustments)

为避免业务代码耦合，在 `src/core/` 目录下新增/修改计费逻辑。

### 1. 统一佣金计算入口 (`src/core/billing_core.py`)
新建 `calculate_and_set_commission(session, order: Order)` 方法：
* **输入**：当前正在处理的 `Order` 对象及事务 `session`。
* **逻辑**：
  1. 检查该订单的用户是否由他人邀请 (`select(Referral).where(Referral.invitee_id == order.telegram_id)`)。
  2. 检查该用户是否已有其他成功的非 0 订单，若有，说明不是首单，`commission_usdt` 设为 0 并返回。
  3. 若为首单，根据 `order.order_id` 及其 `original_price`，按上述汇率规则计算出 `usdt` 金额。
  4. 将金额赋值给 `order.commission_usdt`。
* **应用位置**：此方法**必须**同步植入到现存的三个发货入口中（状态变更为 `SUCCESS` 前调用）：
  - `src/services/payment_fulfillment_service.py` (`fulfill_order`)
  - `src/services/payment_validator.py` (`_process_order`)
  - `src/handlers/payment_handler.py` (`successful_payment_callback`)

### 2. 纯净的基础资产操作 (`src/core/billing_core.py`)
为未来的兑换功能提前封装支持外部传入 `session` 的方法：
* `add_credits_with_session(session, user_id: int, amount: int)`：原子化增加/扣减灵石。
* `grant_membership_with_session(session, user: User, plan: MembershipPlan)`：将 `payment_fulfillment_service.py` 中冗长复杂的身份折算逻辑（新旧比例换算）抽离至此，实现复用。

### 3. 重构邀请数据统计 (`src/services/permission_service.py`)
改造现有的 `get_invitation_recharge_stats` 方法。
因为历史数据已清洗完毕且新订单已实时固化，废弃掉原本复杂的内存累加逻辑，直接使用简单的连表查询获取收益：
```python
# 伪代码：获取历史总佣金
stmt = select(func.sum(Order.commission_usdt)).join(
    Referral, Referral.invitee_id == Order.telegram_id
).where(
    Referral.inviter_id == user_id,
    Order.status == 'SUCCESS'
)
total_commission = await session.scalar(stmt) or 0.0

# 伪代码：获取已消耗佣金 (为未来准备)
stmt_spent = select(func.sum(AffiliateTransaction.amount_usdt)).where(
    AffiliateTransaction.user_id == user_id,
    AffiliateTransaction.status.in_(["SUCCESS", "PENDING"])
)
spent_commission = await session.scalar(stmt_spent) or 0.0

available_balance = total_commission - spent_commission
```

---

## 四、 跨端支持说明 (Bot & Web Support)

本基础方案的实施完全兼容 Bot 端与 Web 端未来的接入：
1. **统一数据源**：所有前端的“可提现余额”展示均统一通过 `permission_service.get_invitation_recharge_stats` 改造后的新 SQL 计算得出，确保两端数据绝对一致。
2. **Web 端 API 铺垫**：支持传入 `session` 的 `billing_core.py` 资产操作方法，能直接被 Web API（FastAPI）和 Bot 的 FSM 状态机调用，无需重复造轮子。
3. **无缝演进**：完成本次底层改造后，旧版的“分享赚灵石”展示逻辑可以平滑过渡，为下一步在 Bot 端引入 FSM 交互（提现/转换）以及在 Web Dashboard 增加审核管理面板扫清障碍。