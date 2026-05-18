# `affiliate_transactions` 账本闭环实施方案（可实施版）

目标只有两件事：

1. 把返佣从 `orders.commission_usdt` 的统计结果，升级为真实账本入账
2. 在历史补账完成后，把用户余额切换为账本净额

本文档基于当前工作区代码、当前数据库快照与已确认结论整理，重点补齐：

- 首单返佣并发锁策略
- 历史补账的可执行前提
- 上线前后可直接跑的验收 SQL
- 需要补齐的最小测试集

## 1. 当前确认现状

代码与数据库当前已确认：

- `orders.commission_usdt`、`payment_channel`、`paid_at` 已落地
- 三条支付成功链路都已接入 `calculate_and_set_commission_for_paid_order()`
- `affiliate_transactions` 表已存在，但当前仍是空表
- `orders.telegram_id`、`referrals.inviter_id`、`referrals.invitee_id` 实际都是内部 `users.id`
- `orders.tx_hash` 有唯一约束
- `orders.order_id` 不是唯一键，不能作为账本唯一引用
- 当前库内已存在重复 `orders.order_id`，因此账本引用必须使用 `order.id`
- 当前 `commission_usdt > 0` 的订单都还能找到有效 referral，不存在“正佣金但 referral 丢失”的孤儿数据

当前数据库快照以实时 SQL 为准，不以文档历史数字为准。当前实查结果：

- `affiliate_transactions`：`0`
- `orders.commission_usdt > 0`：`2380`
- `payment_channel IS NULL`：`36`
- `status = 'SUCCESS' AND paid_at IS NULL`：`36`

注意：

- 上述数量会继续变化
- 后续补账、验收、切口径都必须以执行时 SQL 查询结果为基线，不能把本文数字写死进脚本或测试断言

## 2. 本期范围

本期只做：

1. 扩展 `affiliate_transactions`
2. 支付成功后写返佣入账流水
3. 提供历史补账脚本
4. 历史补账完成后切换余额口径

本期不做：

- 提现申请 / 审核 / 驳回
- 冻结余额
- 返佣消费闭环
- 新 UI

## 3. 核心规则

### 3.1 口径

- `total_commission_usdt = SUM(orders.commission_usdt)`
- `spent_commission_usdt = SUM(affiliate_transactions.amount_usdt WHERE direction='OUT' AND status='SUCCESS')`
- `available_balance_usdt = SUM(IN,SUCCESS) - SUM(OUT,SUCCESS)`

说明：

- `orders.commission_usdt` 是订单层固化结果
- `affiliate_transactions` 是余额主口径
- 本期不引入 `pending_balance_usdt`

### 3.2 精度

- 订单与账本都使用 `DECIMAL(10, 4)`
- 聚合全程使用 `Decimal`
- 只在最终返回前格式化到 2 位
- 不允许在 invitee 中间层或循环中提前 round

### 3.3 引用与幂等

- `reference_type = 'ORDER'`
- `reference_id = str(order.id)`
- `idempotency_key = affiliate:commission:order:{order.id}`

禁止：

- 用 `orders.order_id` 做唯一引用
- 用“先查再插”实现幂等

要求：

- 账本写入必须使用数据库级幂等
- 推荐 `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING`
- 冲突时按“已存在，幂等成功”处理，不能回滚整单

## 4. 当前必须先补的风险

当前代码存在一个必须在账本接入前处理的风险：

- `calculate_and_set_commission_for_paid_order()` 目前的“首单返佣”判定不是并发安全的
- 现在逻辑是：检查当前订单之前是否存在更早的成功已支付订单
- 但这个查询没有对同一 `invitee` 做串行化锁

这会导致的最坏情况：

1. 同一受邀用户在极短时间内出现两笔成功支付
2. 两个事务都看不到对方尚未提交的成功订单
3. 两笔订单都被判成“首单”
4. 两笔订单的 `commission_usdt` 都被固化为正数
5. 后续账本按 `order.id` 幂等时，会合法写入两笔 `IN/SUCCESS`

结论：

- 仅有 `idempotency_key = affiliate:commission:order:{order.id}` 不足以防止“双首单返佣”
- 必须先把“首单资格判定”做成并发安全，再接账本写入

## 5. 并发锁策略

### 5.1 锁目标

对同一个 `invitee` 的首单返佣判定，必须串行化。

推荐锁点：

- 在 `src/core/affiliate_core.py` 内，先查 `Referral.invitee_id == order.telegram_id`
- 找到 referral 后，立刻对这条 referral 行执行 `SELECT ... FOR UPDATE`

原因：

- `referrals.invitee_id` 现有设计为唯一键，一名 invitee 只对应一条 referral
- 锁 referral 行即可把“同一 invitee 的返佣资格判定”串行化
- 锁粒度小于锁整张用户表或订单表，冲突面更小

### 5.2 推荐流程

在统一 helper 内执行以下顺序：

1. 保证 `order.id` 已存在
2. 若 `order.status != 'SUCCESS'`、`paid_at is NULL`、`payment_channel` 非法、`final_price <= 0`，直接置 `commission_usdt = 0`
3. 按 `Referral.invitee_id == order.telegram_id` 查询 referral
4. 若无 referral，直接置 `commission_usdt = 0`
5. 若有 referral，对该 referral 行执行 `SELECT ... FOR UPDATE`
6. 在同一事务内重新执行“是否存在更早成功付费单”的首单判断
7. 仅当当前订单仍为首单时，固化 `order.commission_usdt`
8. 若 `commission_usdt > 0`，继续在同一事务写 `affiliate_transactions`
9. 提交事务后再删缓存

关键点：

- “加锁”必须发生在“首单判定”之前
- “固化佣金”和“写账本”必须在同一事务里
- 不允许先提交订单，再异步补一笔账本

### 5.3 为什么不只靠订单幂等

现有三条支付链路的幂等边界分别是：

- RMB：锁单 + 已成功直接返回
- TON：基于 `tx_hash`
- Stars：基于截断后的 `tx_hash`

这些只能防止：

- 同一订单重复回调
- 同一链上交易重复处理

但不能防止：

- 同一个 invitee 的两笔不同成功订单同时争抢“首单资格”

因此订单幂等和首单并发锁必须同时存在，二者不可互相替代。

## 6. 模型调整

`affiliate_transactions` 保留现有字段，并新增：

- `direction`
- `reference_type`
- `reference_id`
- `idempotency_key`

索引：

- `UNIQUE(idempotency_key)`
- `INDEX(user_id, status, direction)`
- `INDEX(reference_type, reference_id)`

本期不要新增：

- `balance_after`
- `frozen_amount`
- `pending_reason`

字段语义要求：

- `direction`：`IN` / `OUT`
- `reference_type`：本期固定为 `ORDER`
- `reference_id`：本期固定为字符串化后的 `order.id`
- `status`：本期实际只写 `SUCCESS`

## 7. 入账实现

在 `src/core/affiliate_core.py` 新增统一入口：

```python
async def record_affiliate_commission_transaction(
    session: AsyncSession,
    order: Order,
    referral: Referral,
) -> None:
    ...
```

这里建议显式传入已加锁的 `referral`，不要在函数内部再重复按 invitee 查一次，避免锁语义分散。

职责：

1. 要求 `order.id` 已存在
2. 要求 `order.status == "SUCCESS"`
3. 要求 `order.commission_usdt > 0`
4. 使用已加锁的 `referral.inviter_id`
5. 写一笔 `COMMISSION_ACCRUAL / IN / SUCCESS`
6. 使用数据库级幂等写入
7. 成功写入或命中幂等后返回成功语义

建议写入：

- `user_id = referral.inviter_id`
- `amount_usdt = order.commission_usdt`
- `transaction_type = 'COMMISSION_ACCRUAL'`
- `direction = 'IN'`
- `status = 'SUCCESS'`
- `reference_type = 'ORDER'`
- `reference_id = str(order.id)`
- `idempotency_key = f"affiliate:commission:order:{order.id}"`

`details` 最少保留：

- `order_pk`
- `order_id`
- `tx_hash`
- `invitee_user_id`
- `inviter_id`
- `payment_channel`
- `commission_usdt`
- `source`

要求：

- `details` 在在线写入与历史补账中保持同构
- 便于后续抽样校验与人工追账

## 8. 支付链路接入

接入点：

- `src/services/payment_fulfillment_service.py`
- `src/services/payment_validator.py`
- `src/handlers/payment_handler.py`

统一顺序：

1. 支付成功
2. 固化 `payment_channel`
3. 固化 `paid_at`
4. 调“带并发锁”的 `calculate_and_set_commission_for_paid_order()`
5. 若 `commission_usdt > 0`，在同一事务内调 `record_affiliate_commission_transaction()`
6. 提交事务
7. 提交成功后删缓存

硬性要求：

- 第 4 步和第 5 步必须在同一事务内
- 订单层幂等与账本层幂等必须同时存在
- 缓存失效应尽量放到事务成功之后执行

## 9. 缓存规则

缓存 key：

- `allbot:stats:invitation_recharge:{user_id}`

以下场景统一失效：

- 佣金固化且事务成功后
- 账本入账成功或命中幂等且事务成功后
- 补账成功后
- 后续任何成功出账后

建议：

- 缓存失效逻辑仍沉到 `affiliate_core.py`
- 但要避免“事务未提交就先删缓存”
- 要么显式在调用方 `commit()` 成功后删
- 要么统一封装成“事务成功后触发”的单一出口

## 10. 历史补账

### 10.1 为什么必须独立脚本

- 补账属于数据修复，不属于 schema 迁移
- 不能放进 Alembic
- 必须支持反复 dry-run 与局部复跑

脚本支持：

- `--dry-run`
- `--apply`
- `--user-id`
- `--order-id`
- `--limit`

### 10.2 补账范围

补账候选范围严格限定为：

- `orders.status = 'SUCCESS'`
- `orders.commission_usdt > 0`
- 能找到有效邀请关系
- 账本中不存在同一 `idempotency_key`

不从“所有成功单”重新推导，不重算佣金，不重判首单。

原因：

- `orders.commission_usdt` 已是当前线上唯一可信的订单层固化结果
- 现网还存在 `payment_channel IS NULL`、`paid_at IS NULL` 的历史异常成功单
- 若补账脚本自行重判首单，会把在线逻辑、历史修复和未来逻辑搅在一起，难以审计

### 10.3 补账前提

补账前必须满足以下前提：

1. `affiliate_transactions` 扩表已完成
2. 在线支付三链路的新写账逻辑已上线
3. `commission_usdt > 0` 的订单可以找到 referral
4. 业务接受“补账按当前 referral 关系归属 inviter”

第 4 条必须明确：

- 当前 `Order` 没有保存历史 `inviter_id` 快照
- 补账时只能依据当前 `Referral.invitee_id -> inviter_id` 关系找归属人
- 如果历史上发生过用户合并、邀请关系修正，补账结果默认按当前关系落账

执行建议：

- 先跑一轮 dry-run，抽样核对高佣金 inviter
- 若发现 referral 被修正过且业务不能接受“按当前关系补账”，则先停补账，先补归属快照策略，不要硬上

### 10.4 补账写入要求

- 复用线上同一套 `idempotency_key`
- 复用线上同一套 `details`
- 命中幂等时视为成功，不报错
- 输出 `should_insert / already_exists / missing_referral / error`
- `--dry-run` 与 `--apply` 的筛选条件必须完全一致，不能两套逻辑

### 10.5 补账脚本建议输出

至少输出：

- 候选订单数
- 应写入数
- 已存在数
- referral 缺失数
- 错误数
- 涉及 inviter 数
- 涉及金额总和

## 11. 余额切换

切换位置：

- `src/services/referral_stats_service.py`

切换后：

- `total_commission_usdt` 继续来自 `orders`
- `spent_commission_usdt` 来自账本 `OUT/SUCCESS`
- `available_balance_usdt` 来自账本净额

注意：

- 这次切换不只影响 `GET /api/users/me`
- 还会影响登录返回、依赖鉴权、Bot 个人资料页等所有复用 `query_invitation_recharge_stats()` 的路径
- 所以必须在历史补账完成后再切，不能先切再补

实现要求：

- 聚合仍使用 `Decimal`
- 只在最终出参前做 2 位格式化
- 保持 `total_commission_usdt` 与 `orders.commission_usdt` 聚合一致

## 12. 验收 SQL

以下 SQL 作为上线前后验收基线，执行时以实时结果为准。

### 12.1 上线前基线确认

```sql
SELECT COUNT(*) AS affiliate_transactions_count
FROM affiliate_transactions;

SELECT COUNT(*) AS commission_gt_0_orders
FROM orders
WHERE commission_usdt > 0;

SELECT COUNT(*) AS success_orders_missing_paid_at
FROM orders
WHERE status = 'SUCCESS' AND paid_at IS NULL;

SELECT COUNT(*) AS success_orders_missing_channel
FROM orders
WHERE status = 'SUCCESS' AND payment_channel IS NULL;
```

### 12.2 检查 `order_id` 不能用作账本引用

```sql
SELECT order_id, COUNT(*) AS cnt, string_agg(id::text, ',' ORDER BY id) AS order_pks
FROM orders
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY cnt DESC, order_id
LIMIT 20;
```

预期：

- 允许查出重复 `order_id`
- 这正是账本必须使用 `order.id` 的原因

### 12.3 检查正佣金订单是否都能关联 referral

```sql
SELECT COUNT(*) AS missing_referral_orders
FROM orders o
LEFT JOIN referrals r ON r.invitee_id = o.telegram_id
WHERE o.commission_usdt > 0
  AND r.id IS NULL;
```

预期：

- 上线前最好为 `0`
- 若不为 `0`，先排查归属数据，再决定是否补账

### 12.4 补账 dry-run 后应写入数量核对

```sql
SELECT COUNT(*) AS should_backfill
FROM orders o
JOIN referrals r ON r.invitee_id = o.telegram_id
LEFT JOIN affiliate_transactions at
  ON at.idempotency_key = ('affiliate:commission:order:' || o.id::text)
WHERE o.status = 'SUCCESS'
  AND o.commission_usdt > 0
  AND at.id IS NULL;
```

预期：

- 该数量应与补账 dry-run 输出里的 `should_insert` 一致

### 12.5 补账后账本入账数与订单正佣金数对账

```sql
SELECT
  (SELECT COUNT(*) FROM orders WHERE commission_usdt > 0) AS order_commission_count,
  (
    SELECT COUNT(*)
    FROM affiliate_transactions
    WHERE transaction_type = 'COMMISSION_ACCRUAL'
      AND direction = 'IN'
      AND status = 'SUCCESS'
  ) AS ledger_in_count;
```

预期：

- 两边数量一致

### 12.6 补账后金额对账

```sql
SELECT
  (
    SELECT COALESCE(SUM(commission_usdt), 0)
    FROM orders
    WHERE commission_usdt > 0
  ) AS order_commission_sum,
  (
    SELECT COALESCE(SUM(amount_usdt), 0)
    FROM affiliate_transactions
    WHERE transaction_type = 'COMMISSION_ACCRUAL'
      AND direction = 'IN'
      AND status = 'SUCCESS'
  ) AS ledger_in_sum;
```

预期：

- 两边金额一致

### 12.7 检查账本幂等键重复

```sql
SELECT idempotency_key, COUNT(*) AS cnt
FROM affiliate_transactions
GROUP BY idempotency_key
HAVING COUNT(*) > 1;
```

预期：

- 结果为空

### 12.8 检查余额口径是否符合账本净额

```sql
SELECT
  user_id,
  COALESCE(SUM(CASE WHEN direction = 'IN'  AND status = 'SUCCESS' THEN amount_usdt ELSE 0 END), 0) AS total_in,
  COALESCE(SUM(CASE WHEN direction = 'OUT' AND status = 'SUCCESS' THEN amount_usdt ELSE 0 END), 0) AS total_out,
  COALESCE(SUM(CASE
    WHEN direction = 'IN'  AND status = 'SUCCESS' THEN amount_usdt
    WHEN direction = 'OUT' AND status = 'SUCCESS' THEN -amount_usdt
    ELSE 0
  END), 0) AS net_available
FROM affiliate_transactions
GROUP BY user_id
ORDER BY net_available DESC
LIMIT 50;
```

用途：

- 与接口返回的 `available_balance_usdt` 抽样比对

### 12.9 高风险 inviter 抽样核对

```sql
SELECT
  r.inviter_id,
  COUNT(*) AS order_count,
  COALESCE(SUM(o.commission_usdt), 0) AS order_commission_sum
FROM orders o
JOIN referrals r ON r.invitee_id = o.telegram_id
WHERE o.commission_usdt > 0
GROUP BY r.inviter_id
ORDER BY order_commission_sum DESC
LIMIT 20;
```

用途：

- 作为补账前后人工抽样名单
- 优先核对金额最高、受邀用户最多的 inviter

## 13. 正确实施顺序

1. 迁移模型与索引
2. 改造 `affiliate_core`，先补并发锁，再补账本 helper
3. 接入 RMB / TON / Stars 三条支付链路
4. 补支付链路回归测试
5. 先跑历史补账 `dry-run`
6. 按高风险 inviter 做抽样校验
7. 再执行历史补账 `apply`
8. 跑金额与数量对账 SQL
9. 最后切换余额读口径
10. 跑接口与 Bot 侧 smoke test
11. 清缓存并观察线上

禁止顺序：

- 先切余额口径，再补历史账
- 未补首单并发锁就先接账本

否则会出现：

- 用户余额因空账本被清零
- 并发首充被错误记成两笔返佣

## 14. 需要补的测试用例

至少补以下测试。

### 14.1 `affiliate_core` 单测

1. 有 referral 的真实首单，会固化正佣金
2. 同一 invitee 的非首单，会固化 `0`
3. 无 referral 的成功单，不返佣
4. `payment_channel` 非法或 `paid_at is NULL`，不返佣
5. 已有 referral 锁时，第二个事务不能同时把另一单判成首单

第 5 条是本期最重要新增测试。

### 14.2 账本 helper 单测

1. `commission_usdt > 0` 时写入一笔 `COMMISSION_ACCRUAL / IN / SUCCESS`
2. 同一 `order.id` 重复调用只落一笔
3. `commission_usdt = 0` 时不写账
4. 命中 `ON CONFLICT` 时按成功返回，不抛错
5. `details` 字段内容完整，包含最小审计信息

### 14.3 支付链路回归测试

1. RMB 成功回调：订单成功、佣金固化、账本写入都在同一事务内
2. TON 成功链路：重复 tx 不重复落账
3. Stars 成功链路：重复 charge 不重复落账
4. 支付成功但非首单：订单成功，账本不写返佣入账

### 14.4 补账脚本测试

1. `--dry-run` 与 `--apply` 使用相同筛选逻辑
2. 同一补账脚本重复执行不会重复补录
3. referral 缺失时被统计为 `missing_referral`
4. 指定 `--user-id` 或 `--order-id` 只处理目标范围
5. 补账后金额总和与 `orders.commission_usdt` 聚合一致

### 14.5 统计与接口测试

1. `total_commission_usdt` 仍等于订单聚合
2. `available_balance_usdt` 等于账本净额
3. `spent_commission_usdt` 等于账本 `OUT/SUCCESS` 聚合
4. 聚合过程无中间舍入漂移
5. `GET /api/users/me`、登录返回、Bot 个人资料页的余额口径一致

### 14.6 并发测试建议

若测试环境允许，增加一个偏集成的并发用例：

1. 为同一 invitee 构造两笔几乎同时成功的订单
2. 两个协程并发执行支付成功链路
3. 断言最终只有一笔订单 `commission_usdt > 0`
4. 断言最终只写入一笔 `COMMISSION_ACCRUAL`

这条测试是为了防止未来重构时把 referral 行锁删掉。

## 15. 二期边界

二期再做：

1. 返佣兑换灵石
2. 返佣兑换身份
3. 提现

提现不要做成：

- `WITHDRAW_APPLY / OUT / PENDING`
- 驳回再补一笔 `IN / SUCCESS`

正确方向：

- 要么单独建提现业务表，审核通过时再写 `OUT/SUCCESS`
- 要么先引入冻结余额语义，再谈 `PENDING OUT`
