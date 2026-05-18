# Affiliate 账本闭环维护窗口发布清单

## 1. 适用场景

本清单用于以下发布方式：

1. 先开启维护窗口
2. 在维护窗口内部署整包代码
3. 在服务未恢复前执行历史补账 `--apply`
4. 完成补账后对账与 smoke test
5. 最后恢复服务

适用前提：

- 本次发布包含：
  - 在线支付成功后写 `affiliate_transactions`
  - `affiliate_transactions` 扩表与索引
  - `scripts/backfill_affiliate_transactions.py`
  - `referral_stats_service.py` 余额切到账本净额
- 维护窗口内可以真正停止所有生产写入口

不适用场景：

- 只能关闭前端页面，但无法停止 Bot、支付回调、链上轮询
- 无法控制是否还有其他实例继续写同一个生产库

## 2. 发布目标

本次维护窗口要一次性完成以下目标：

1. 生产环境部署 affiliate 账本闭环代码
2. 历史返佣通过 `--apply` 回填到 `affiliate_transactions`
3. 确认数量、金额、幂等性全部对账通过
4. 在用户恢复访问前，确保余额口径已与账本一致

## 3. 维护前确认

### 3.1 发布包范围

本次发布包应包含：

- `src/core/affiliate_core.py`
- `src/database/models.py`
- `migrations/versions/5a8d9f3c1b2e_add_affiliate_transaction_ledger_fields.py`
- `src/services/payment_fulfillment_service.py`
- `src/services/payment_validator.py`
- `src/handlers/payment_handler.py`
- `src/payment_api_server.py`
- `src/services/rmb_payment_service.py`
- `src/web_api/routers/payment.py`
- `src/services/referral_stats_service.py`
- `scripts/backfill_affiliate_transactions.py`

### 3.2 维护前必须确认

- 已准备好维护公告
- 已确认维护期间暂停所有生产写入口
- 已确认当前代码已通过定向测试与 smoke
- 已确认 migration 已在生产环境执行，或准备在维护窗口内执行
- 已确认补账脚本使用的是生产库连接
- 已确认没有其他测试/备用实例继续连接同一个生产库写数据

## 4. 必须停止的服务

维护窗口开始后，先停止所有可能写生产库的入口。

至少包括：

- Web API
- Telegram Bot 主进程
- 支付回调服务
- TON 轮询/支付校验进程
- 任何备用实例、测试实例、定时任务、消费者进程

原则：

- 不是“用户看不到页面”就算维护
- 而是“没有任何生产写入口继续处理支付成功链路”

## 5. 维护窗口执行顺序

### 5.1 开启维护

- 发布维护公告
- 停掉所有生产写入口
- 确认维护期间不会继续处理新支付成功事件

建议检查项：

```bash
docker compose ps
```

若有多套 compose / 多容器 / 多机部署，需要全部核对。

### 5.2 部署整包代码

- 更新代码到目标版本
- 若有未挂载代码卷的容器，必须重建镜像或重建容器
- 确保运行中的就是本次发布代码，而不是旧容器旧镜像

若使用 Docker Compose，按你的生产实际命令执行。重点是确认：

- `web-api`
- Bot
- 支付回调服务
- 相关 worker / poller

都已经切到新代码版本。<mccoremem id="03g1gli4ucd4tvryej8ch2sdr" />

### 5.3 确认数据库结构已到位

若生产环境尚未执行 migration，则先执行：

```bash
alembic upgrade head
```

确认点：

- `affiliate_transactions` 已包含：
  - `direction`
  - `reference_type`
  - `reference_id`
  - `idempotency_key`
- 唯一约束与索引已存在

### 5.4 重新跑补账前最新基线

注意：

- 维护窗口内必须重新跑一次
- 不要沿用之前聊天记录里的历史数字

执行：

```bash
python scripts/backfill_affiliate_transactions.py --dry-run
```

记录输出中的：

- `candidate_orders`
- `should_insert`
- `already_exists`
- `missing_referral`
- `error`
- `inviter_count`
- `amount_total`

### 5.5 跑补账前验收 SQL

#### 5.5.1 基线确认

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

#### 5.5.2 检查正佣金订单是否都能关联 referral

```sql
SELECT COUNT(*) AS missing_referral_orders
FROM orders o
LEFT JOIN referrals r ON r.invitee_id = o.telegram_id
WHERE o.commission_usdt > 0
  AND r.id IS NULL;
```

#### 5.5.3 核对 `dry-run` 数量

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

#### 5.5.4 核对 `dry-run` 金额

```sql
SELECT COALESCE(SUM(o.commission_usdt), 0) AS should_backfill_sum
FROM orders o
JOIN referrals r ON r.invitee_id = o.telegram_id
LEFT JOIN affiliate_transactions at
  ON at.idempotency_key = ('affiliate:commission:order:' || o.id::text)
WHERE o.status = 'SUCCESS'
  AND o.commission_usdt > 0
  AND at.id IS NULL;
```

#### 5.5.5 核对涉及 inviter 数

```sql
SELECT COUNT(DISTINCT r.inviter_id) AS distinct_inviters_should_backfill
FROM orders o
JOIN referrals r ON r.invitee_id = o.telegram_id
LEFT JOIN affiliate_transactions at
  ON at.idempotency_key = ('affiliate:commission:order:' || o.id::text)
WHERE o.status = 'SUCCESS'
  AND o.commission_usdt > 0
  AND at.id IS NULL;
```

要求：

- SQL 数字必须与 `--dry-run` 输出一致
- 若不一致，先暂停，不要执行 `--apply`

### 5.6 执行历史补账

执行：

```bash
python scripts/backfill_affiliate_transactions.py --apply
```

要求：

- 维护窗口内执行
- 服务仍保持未开放状态
- 执行结束后保留完整输出

### 5.7 跑补账后对账 SQL

#### 5.7.1 数量对账

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

#### 5.7.2 金额对账

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

#### 5.7.3 幂等键重复检查

```sql
SELECT idempotency_key, COUNT(*) AS cnt
FROM affiliate_transactions
GROUP BY idempotency_key
HAVING COUNT(*) > 1;
```

#### 5.7.4 余额净额抽样

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

#### 5.7.5 高风险 inviter 抽样

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

验收标准：

- 数量一致
- 金额一致
- `idempotency_key` 无重复
- 抽样 inviter 金额与预期一致

### 5.8 最终 smoke test

在服务仍处于维护状态下，完成最小冒烟。

至少验证：

1. Dashboard / 接口侧返回正常
2. Bot 个人资料页依赖的邀请统计接口无报错
3. 支付链路主逻辑可正常加载
4. 若条件允许，至少做 1 条真实或准真实支付成功链路验证

建议命令：

```bash
pytest tests/dashboard/test_dashboard_referrals_rewards.py tests/services/test_referral_stats_service.py tests/services/test_payment_fulfillment_service_affiliate.py tests/services/test_payment_validator_affiliate.py tests/handlers/test_payment_handler_affiliate.py -q
```

如需更强验证，可加：

```bash
pytest tests/integration/test_affiliate_payment_integration.py -q
```

### 5.9 清缓存

恢复服务前，建议清理邀请统计缓存，避免旧缓存污染新口径展示。

关注缓存 key：

```text
allbot:stats:invitation_recharge:{user_id}
```

### 5.10 恢复服务

- 恢复 Web API
- 恢复 Telegram Bot
- 恢复支付回调服务
- 恢复 TON 轮询/后台消费者
- 观察启动日志与错误日志

## 6. 维护后观察项

恢复服务后重点观察：

1. 新成功支付是否写入 `orders` 与 `affiliate_transactions`
2. `available_balance_usdt` 是否与账本净额一致
3. 是否出现重复账本、回调异常、支付成功但未发货
4. 是否有用户反馈返佣余额异常归零或翻倍

建议再次抽样执行：

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

## 7. 回滚原则

若在以下阶段发现异常，应保持维护状态，不要立即开放服务：

- `dry-run` 与 SQL 不一致
- `--apply` 过程中错误数异常
- 补账后数量或金额对不上
- `idempotency_key` 出现重复
- smoke test 失败

回滚原则：

1. 先保持服务关闭
2. 先查明是代码问题、数据问题还是部署问题
3. 未确认账本状态正确前，不恢复外部访问