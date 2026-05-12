# 分享赚灵石（联盟系统）安全落地修订稿

本方案是基于**当前仓库真实代码状态**整理后的安全实施版。目标是完成：

- `orders` 表联盟字段补齐
- 三条支付链路接入首单佣金固化
- 历史数据在**可确定范围内**回填
- 用户中心与 Dashboard 统一返佣统计口径

本次仍然**不涉及** Bot / Web 新 UI、新菜单或提现审核流，只处理底层数据与结算语义。

---

## 一、先确认现网代码事实

在开始实现前，必须先接受以下现状，后续设计全部以此为准：

1. `orders.telegram_id` 这个字段名虽然叫 `telegram_id`，但当前实际存的是 `users.id`（内部用户 ID），不是 Telegram 原始 ID。
2. `referrals.inviter_id` / `referrals.invitee_id` 也都是 `users.id`。
3. RMB 链路是**先建 `PENDING` 订单，后异步回调改成 `SUCCESS`**。
4. TON / Stars 链路是**确认支付成功后才创建订单**，通常创建即成功。
5. 因为 RMB 与 TON / Stars 的建单时机不同，**不能再用 `orders.created_at` 代表“实际支付成功时间”**。
6. 当前用户中心、Dashboard 总览、Dashboard 返佣明细、Dashboard 用户详情存在多套旧口径，仍在使用 `RMB_ / XTR_ / 金额阈值` 猜渠道。
7. 当前 Dashboard 返佣明细接口还存在关联键语义错误，不能继续沿用现有 join 写法。

因此，本方案的核心修订是：

- 新增 `paid_at`，把“支付成功时间”显式建模。
- 首单判定统一改为按 `paid_at` 排序，而不是按 `created_at`。
- 历史佣金回填只对**`paid_at` 可安全判定**的订单执行，宁可少补，不可错补。
- Dashboard 与用户侧统一改为基于内部用户 ID 聚合，不能再把 `Referral.*_id` 与 `User.telegram_id` 做 join。

---

## 二、核心设计原则

### 1. 佣金必须固化，不可查询时动态重算

未来统计统一基于 `orders.commission_usdt` 聚合，避免后续汇率调整导致历史返佣漂移。

### 2. 支付渠道必须显式建模

未来所有新订单都必须写入 `payment_channel`，禁止继续依赖 `order_id` 前缀或金额阈值推断。

### 3. 首单必须按“支付成功时间”判定

联盟语义是“首笔成功付费订单”，不是“最早创建的订单”。因此必须以 `paid_at` 为准。

### 4. 历史回填必须保守

对于现有历史订单，只对能可靠恢复 `payment_channel` 与 `paid_at` 的数据自动补佣；无法确认的保留 `commission_usdt = 0` 并输出复核清单，不做冒进猜测。

### 5. 旧字段名可以保留，旧实现不能保留

对外返回的旧字段名继续兼容，但内部统计逻辑必须完全切换到新口径。

### 6. RMB 幂等方案本期只保留一种主路径

本期只采用 `SELECT ... FOR UPDATE` 锁单方案，避免和 CAS 条件更新混用后出现实现歧义。

---

## 三、数据库结构演进（Alembic）

必须通过 Alembic 新建迁移脚本，一次性完成结构变更与保守型历史回填。

### 1. 修改 `orders` 表

本次迁移至少新增以下字段：

- `commission_usdt = Column(DECIMAL(10, 4), nullable=False, server_default='0')`
  - 记录该订单实际产生的联盟佣金，默认 `0`
- `payment_channel = Column(String(20), nullable=True, index=True)`
  - 统一取值：`RMB`、`TON`、`XTR`
- `paid_at = Column(DateTime, nullable=True, index=True)`
  - 表示该订单真正完成支付并进入成功态的时间

说明：

- `commission_usdt` 是未来所有联盟统计的唯一金额来源。
- `payment_channel` 是未来所有渠道统计的唯一分类来源。
- `paid_at` 是首单判定的唯一排序字段，必须和 `commission_usdt` 一起落地。

### 2. 新增流水表 `affiliate_transactions`

该表保留，作为未来“佣金兑换灵石 / 兑换身份 / 提现申请”的账务留痕，不参与本期首单佣金判定。

```python
class AffiliateTransaction(Base):
    __tablename__ = "affiliate_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    amount_usdt = Column(DECIMAL(10, 4), nullable=False)
    transaction_type = Column(String(50), nullable=False)  # CONVERT_CREDITS / CONVERT_IDENTITY / WITHDRAW
    status = Column(String(20), default="PENDING")  # PENDING / SUCCESS / REJECTED
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
```

---

## 四、历史数据迁移策略（保守补齐，不冒进补佣）

### 1. 总原则

历史迁移分为两个目标：

1. 先尽量补齐 `payment_channel`
2. 再仅对 `paid_at` 可可靠恢复的订单补 `commission_usdt`

本期明确拒绝以下危险做法：

- 禁止按 `created_at` 直接认定 RMB 历史首单
- 禁止按 `membership_plans.price_stars` 推断历史 Stars 单
- 禁止按纯金额阈值直接区分 TON / Stars

### 2. `payment_channel` 历史回填规则

优先采用以下规则：

1. `order_id LIKE 'RMB_%' OR order_id LIKE 'WEB_%'` -> `RMB`
2. `order_id LIKE 'ORDER:%'` 的订单，先做迁移前抽样校验
3. 抽样确认后，才允许使用当前经验规则：
   - `LENGTH(COALESCE(tx_hash, '')) > 50` -> 暂定 `XTR`
   - `LENGTH(COALESCE(tx_hash, '')) <= 50` -> 暂定 `TON`
4. 无法确认的订单，`payment_channel` 保持 `NULL`

注意：

- 第 3 条不是业务真理，只是针对当前库形态的迁移启发式规则。
- Alembic 脚本必须先输出各类命中数量与样本，确认后再执行正式 `UPDATE`。

### 3. `paid_at` 历史回填规则

必须分渠道处理：

#### TON / XTR 历史单

基于当前代码，TON 与 Stars 都是在支付成功后才创建订单，因此对已成功订单可以安全回填：

- `status = 'SUCCESS' AND payment_channel IN ('TON', 'XTR')` -> `paid_at = created_at`

#### RMB 历史单

RMB 不能直接用 `created_at` 作为支付成功时间，因为当前代码是先创建 `PENDING` 再异步回调成功。

本期保守策略：

- `status = 'SUCCESS' AND payment_channel = 'RMB' AND tx_hash IS NOT NULL AND tx_hash != order_id`
  - 可暂按 `paid_at = updated_at` 回填
- 其他 RMB 历史单
  - `paid_at` 保持 `NULL`
  - 不参与自动首单补佣

说明：

- 当前 RMB 成功回调会把 `tx_hash` 更新成第三方交易号，因此 `tx_hash != order_id` 可以帮助识别确实完成过履约的订单。
- `updated_at` 不是完美历史真相，但在现有代码里是当前能安全利用的最保守近似值。
- 对 `paid_at` 仍不可信的 RMB 历史单，不做自动补佣，交由后续离线复核脚本处理。

### 4. 历史佣金回填范围

仅对满足以下条件的订单补 `commission_usdt`：

- `status = 'SUCCESS'`
- `final_price > 0`
- `payment_channel IN ('RMB', 'TON', 'XTR')`
- `paid_at IS NOT NULL`
- `orders.telegram_id` 在 `referrals.invitee_id` 中存在

首单定义统一为：

- 同一 `orders.telegram_id`
- 按 `paid_at ASC, id ASC`
- 第一笔成功付费订单

佣金折算规则：

- 始终基于 `final_price`
- 固定汇率取自 `src/exchange_rates.py`
- 返佣比例 `10%`

即：

- RMB：`commission_usdt = final_price * (1.0 / 6.7) * 0.10`
- TON：`commission_usdt = final_price * 1.4 * 0.10`
- XTR：`commission_usdt = final_price * 0.013 * 0.10`

### 5. 历史回填 SQL 思路

下面仅展示迁移思路，正式 Alembic 应拆成“统计输出 -> 校验 -> 更新”三段：

```sql
-- Step 1: 回填 payment_channel
UPDATE orders
SET payment_channel =
    CASE
        WHEN order_id LIKE 'RMB_%' OR order_id LIKE 'WEB_%' THEN 'RMB'
        WHEN order_id LIKE 'ORDER:%' AND LENGTH(COALESCE(tx_hash, '')) > 50 THEN 'XTR'
        WHEN order_id LIKE 'ORDER:%' AND LENGTH(COALESCE(tx_hash, '')) <= 50 THEN 'TON'
        ELSE NULL
    END
WHERE payment_channel IS NULL;

-- Step 2: 回填 paid_at
UPDATE orders
SET paid_at = created_at
WHERE status = 'SUCCESS'
  AND payment_channel IN ('TON', 'XTR')
  AND paid_at IS NULL;

UPDATE orders
SET paid_at = updated_at
WHERE status = 'SUCCESS'
  AND payment_channel = 'RMB'
  AND tx_hash IS NOT NULL
  AND tx_hash <> order_id
  AND paid_at IS NULL;

-- Step 3: 仅对 paid_at 可判定的历史单补佣
WITH first_paid_orders AS (
    SELECT
        o.id AS order_pk,
        o.telegram_id,
        o.final_price,
        o.payment_channel,
        ROW_NUMBER() OVER (
            PARTITION BY o.telegram_id
            ORDER BY o.paid_at ASC, o.id ASC
        ) AS rn
    FROM orders o
    JOIN referrals r ON r.invitee_id = o.telegram_id
    WHERE
        o.status = 'SUCCESS'
        AND o.final_price > 0
        AND o.paid_at IS NOT NULL
        AND o.payment_channel IN ('RMB', 'TON', 'XTR')
)
UPDATE orders
SET commission_usdt =
    CASE
        WHEN f.payment_channel = 'RMB' THEN f.final_price * (1.0 / 6.7) * 0.10
        WHEN f.payment_channel = 'TON' THEN f.final_price * 1.4 * 0.10
        WHEN f.payment_channel = 'XTR' THEN f.final_price * 0.013 * 0.10
        ELSE 0
    END
FROM first_paid_orders f
WHERE orders.id = f.order_pk
  AND f.rn = 1;
```

### 6. 迁移产物要求

Alembic 迁移必须打印或记录以下统计信息：

- `payment_channel` 各类型回填数量
- `paid_at` 成功回填数量
- 因 `paid_at IS NULL` 而未参与补佣的历史成功单数量
- `commission_usdt > 0` 的订单数量

实现目标是**可审计**，而不是“看起来补全了”。

---

## 五、核心代码改造方案

### 1. 模块边界

`src/core/billing_core.py` 已存在且被任务计费链路广泛依赖，不能重写。

本期推荐做法：

- 优先在 `src/core/affiliate_core.py` 新建联盟逻辑
- 若确实需要复用部分计费 helper，可从 `billing_core.py` 提炼短事务工具
- 禁止为了联盟功能重构现有任务扣费 Saga 主链路

### 2. 统一佣金计算入口

建议新增：

```python
async def calculate_and_set_commission_for_paid_order(
    session,
    order: Order,
) -> None:
    ...
```

前置约束：

1. `order.id` 已存在；若为空必须先 `flush()`
2. `order.status == "SUCCESS"`
3. `order.payment_channel in {"RMB", "TON", "XTR"}`
4. `order.paid_at is not None`

逻辑要求：

1. 使用 `Referral.invitee_id == order.telegram_id` 判断该用户是否存在邀请关系
2. 若无邀请关系，直接令 `order.commission_usdt = 0`
3. 查询该用户是否存在**更早的成功付费订单**
4. 排序与比较逻辑必须使用 `paid_at`，不能使用 `created_at`
5. 必须用 `Order.id != order.id` 排除当前单
6. 若存在更早成功付费单，则当前单不是首单，`commission_usdt = 0`
7. 若不存在更早成功付费单，则按 `payment_channel + final_price` 固化佣金
8. 该 helper 内部严禁解析 `order_id` 猜渠道

建议查询条件：

- 同一用户：`Order.telegram_id == order.telegram_id`
- 成功订单：`Order.status == 'SUCCESS'`
- 有效付费：`Order.final_price > 0`
- 成功时间已知：`Order.paid_at IS NOT NULL`
- 更早订单：
  - `Order.paid_at < order.paid_at`
  - 或 `Order.paid_at == order.paid_at AND Order.id < order.id`

### 3. 三个支付入口的接入方式

#### `src/services/payment_fulfillment_service.py`（RMB）

当前现状：

- 订单提前创建为 `PENDING`
- 履约函数先查状态，后更新成功，存在并发重复履约窗口

本期统一改为：

1. `SELECT ... FOR UPDATE` 按 `order_id` 锁定订单行
2. 若订单不存在，返回失败
3. 若订单已是 `SUCCESS`，直接幂等返回
4. 校验金额
5. 查询套餐与用户
6. 设置：
   - `order.status = 'SUCCESS'`
   - `order.payment_channel = 'RMB'`
   - `order.tx_hash = external_trade_no`
   - `order.paid_at = now`
7. `flush()`
8. 调用 `calculate_and_set_commission_for_paid_order(session, order)`
9. 再执行用户灵石 / 身份更新与日志写入
10. `commit()`

注意：

- 本期不再同时保留 CAS 条件更新实现，避免两套幂等思路并存。
- 若未来改为 CAS，需要单独补设计，不属于本次联盟改造范围。

#### `src/services/payment_validator.py`（TON）

当前现状是成功后才创建订单，这与联盟首单语义兼容。

要求改为：

1. 创建 `Order` 时显式写入：
   - `telegram_id`
   - `final_price`
   - `status`
   - `payment_channel = 'TON'`
   - `paid_at = now`（仅成功时）
2. `db.add(new_order)`
3. `await db.flush()`
4. 若成功，调用 `calculate_and_set_commission_for_paid_order()`
5. 再做用户权益更新与日志
6. 最后 `commit()`

#### `src/handlers/payment_handler.py`（Stars）

要求改为：

1. 创建 `Order` 时显式写入：
   - `telegram_id = user.id`
   - `final_price = successful_payment.total_amount`
   - `status = 'SUCCESS'`
   - `payment_channel = 'XTR'`
   - `paid_at = now`
2. `session.add(new_order)`
3. `await session.flush()`
4. 调用 `calculate_and_set_commission_for_paid_order()`
5. 再提交事务

### 4. 新订单字段一致性要求

今后三种支付方式写入 `orders` 时，必须保证以下字段语义一致：

- `telegram_id`：实际存内部 `users.id`
- `final_price`：实际成交金额
- `status`：订单状态
- `payment_channel`：显式渠道
- `tx_hash`：第三方唯一流水或链上哈希
- `paid_at`：仅成功订单写入

渠道映射固定为：

- RMB -> `RMB`
- TON -> `TON`
- Stars -> `XTR`

---

## 六、统计层统一改造规范

### 1. 共享统计入口

必须抽出共享查询逻辑，推荐单独新增：

- `src/services/referral_stats_service.py`

由它统一产出用户中心与 Dashboard 需要的返佣统计数据。

### 2. 必须改造的现有读取路径

本次不能只改一处，以下路径都必须切到新口径：

- `src/services/permission_service.py`
- `dashboard/backend/routers/referrals.py`
- `dashboard/backend/routers/stats.py`
- `dashboard/backend/routers/users.py`

### 3. 统一 join 语义

所有邀请统计相关 join 统一遵循：

- `Referral.inviter_id` / `invitee_id` 使用内部用户 ID
- `Order.telegram_id` 也按内部用户 ID 处理
- 与 `User` 表关联时必须使用 `User.id`

明确禁止：

- `User.telegram_id == Referral.inviter_id`
- `User.telegram_id == Referral.invitee_id`

### 4. 返回契约兼容要求

现有字段继续保留：

- `recharged_invitees_count`
- `total_recharge_count`
- `total_ton`
- `total_rmb`
- `total_stars`
- `commission_usdt`

允许追加：

- `total_commission_usdt`
- `spent_commission_usdt`
- `available_balance_usdt`

推荐返回：

```python
return {
    "recharged_invitees_count": recharged_invitees_count,
    "total_recharge_count": total_recharge_count,
    "total_ton": total_ton,
    "total_rmb": total_rmb,
    "total_stars": total_stars,
    "commission_usdt": round(total_commission_usdt, 2),
    "total_commission_usdt": round(total_commission_usdt, 2),
    "spent_commission_usdt": round(spent_commission_usdt, 2),
    "available_balance_usdt": round(available_balance_usdt, 2),
}
```

### 5. 统计口径定义

统一统计规则如下：

- 总充值量按 `payment_channel` 分类累计
- 返佣金额只统计 `orders.commission_usdt`
- 首单佣金不再在查询时临时重算
- `payment_channel IS NULL` 的历史遗留单不计入渠道汇总，也不临时猜测

这样可以保证：

- 用户中心与 Dashboard 完全同口径
- 历史异常单不会污染正常统计

---

## 七、建议实施顺序

### 第一步：先做 Alembic

完成：

- 新增 `commission_usdt`
- 新增 `payment_channel`
- 新增 `paid_at`
- 新建 `affiliate_transactions`
- 仅对可确定范围执行历史回填

### 第二步：再改三条支付入口

完成：

- RMB 改为 `FOR UPDATE` 锁单幂等
- TON / Stars 创建订单时显式写入 `payment_channel`
- 成功订单统一写入 `paid_at`
- 三条链路统一调用联盟佣金 helper

### 第三步：统一统计层

完成：

- 抽共享 `referral_stats_service`
- 改 `permission_service.get_invitation_recharge_stats()`
- 改 Dashboard 返佣明细
- 改 Dashboard 总览与用户详情中的充值分类逻辑

### 第四步：补测试

至少覆盖以下场景：

1. 同一用户先建 RMB 待支付单，后先付 TON / Stars，再回来付 RMB，首单佣金应归属于最早 `paid_at` 的成功单
2. RMB 同一 `out_trade_no` 并发回调，只能成功履约一次
3. 用户中心与 Dashboard 读取同一邀请样本时，统计结果一致
4. 历史迁移对 `paid_at IS NULL` 的 RMB 单不会误补佣
5. `payment_channel IS NULL` 的异常历史单不会被统计层错误归类

---

## 八、最终结论

本修订稿的最终落地原则如下：

- **佣金固化以 `commission_usdt` 为准**
- **渠道分类以 `payment_channel` 为准**
- **首单判定以 `paid_at` 为准**
- **历史回填只做可确认部分，不做激进猜测**
- **返佣统计统一按内部用户 ID 聚合**
- **RMB 幂等本期只采用 `FOR UPDATE` 锁单方案**
- **旧字段名保留，但旧实现必须下线**

满足以上约束后，本方案即可作为一版**按现有代码可安全落地**的正式实施文档。
