# Affiliate Ledger Code Review Handoff

## 背景

本次改动的目标是把 affiliate 返佣从 `orders.commission_usdt` 的订单级统计，升级为真实账本闭环。

当前状态：

- 代码还未提交
- 代码还未上线
- 数据库 schema migration 已执行
- 历史补账只做了 `--dry-run` 和 SQL 对账，还没有执行 `--apply`

请审查时重点关注 Python 代码和测试文件，不要把本目录下其他文档文件的增删改视为本次功能实现的一部分。

## 本次实现范围

本次已完成：

1. 扩展 `affiliate_transactions` 模型与 Alembic migration
2. 在 `affiliate_core` 中补齐首单并发锁和账本入账 helper
3. 接入 RMB / TON / Stars 三条支付成功链路
4. 切换 `referral_stats_service` 的余额读口径
5. 新增历史补账脚本
6. 补充最小核心测试、支付链路回归测试、统计测试、补账脚本测试

本次未完成：

- 还未执行补账 `--apply`
- 还未上线
- 还未做最终线上 smoke test
- 还未做补账后的最终金额 / 数量对账

## 关键代码文件

建议重点审查以下文件：

- `src/core/affiliate_core.py`
- `src/database/models.py`
- `migrations/versions/5a8d9f3c1b2e_add_affiliate_transaction_ledger_fields.py`
- `src/services/payment_fulfillment_service.py`
- `src/services/payment_validator.py`
- `src/handlers/payment_handler.py`
- `src/services/referral_stats_service.py`
- `scripts/backfill_affiliate_transactions.py`

测试文件：

- `tests/core/test_affiliate_core.py`
- `tests/services/test_payment_fulfillment_service_affiliate.py`
- `tests/services/test_payment_validator_affiliate.py`
- `tests/handlers/test_payment_handler_affiliate.py`
- `tests/services/test_referral_stats_service.py`
- `tests/scripts/test_backfill_affiliate_transactions.py`

## 已完成的模型与迁移改动

`AffiliateTransaction` 已新增字段：

- `direction`
- `reference_type`
- `reference_id`
- `idempotency_key`

已新增索引 / 约束：

- `UNIQUE(idempotency_key)`
- `INDEX(user_id, status, direction)`
- `INDEX(reference_type, reference_id)`

相关文件：

- `src/database/models.py`
- `migrations/versions/5a8d9f3c1b2e_add_affiliate_transaction_ledger_fields.py`

## 已完成的核心返佣逻辑改动

在 `src/core/affiliate_core.py` 中：

- `calculate_and_set_commission_for_paid_order()` 现在会先查询并锁定 `Referral` 行
- 在同一事务里重新做首单判定
- 返回已加锁的 `Referral | None`，供后续账本写入复用
- 新增 `record_affiliate_commission_transaction()`
- 使用 PostgreSQL `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING`
- `idempotency_key` 固定为 `affiliate:commission:order:{order.id}`
- `reference_type` 固定为 `ORDER`
- `reference_id` 固定为 `str(order.id)`

账本 `details` 目前包含：

- `order_pk`
- `order_id`
- `tx_hash`
- `invitee_user_id`
- `inviter_id`
- `payment_channel`
- `commission_usdt`
- `source`

缓存逻辑也做了调整：

- 不再在事务中途提前删缓存
- 改为 `commit()` 成功后再调用 `invalidate_invitation_recharge_cache()`

## 已接入的支付链路

### RMB

文件：`src/services/payment_fulfillment_service.py`

改动：

- 支付成功后设置订单状态、`payment_channel`、`paid_at`
- `flush()`
- 调用带锁的 `calculate_and_set_commission_for_paid_order()`
- 若 `commission_usdt > 0`，调用 `record_affiliate_commission_transaction()`
- `commit()` 成功后再删邀请统计缓存

### TON

文件：`src/services/payment_validator.py`

改动：

- 在 `_process_order()` 成功路径中接入同一套返佣固化和账本入账逻辑
- 保留原有 `tx_hash` 幂等边界
- 同时补上账本层幂等
- `commit()` 成功后再删邀请统计缓存

### Stars

文件：`src/handlers/payment_handler.py`

改动：

- 成功支付创建订单后
- `flush()`
- 调用带锁的 `calculate_and_set_commission_for_paid_order()`
- 若 `commission_usdt > 0`，调用 `record_affiliate_commission_transaction()`
- `commit()` 成功后再删邀请统计缓存

## 已切换的统计口径

文件：`src/services/referral_stats_service.py`

`query_invitation_recharge_stats()` 当前逻辑：

- `commission_usdt` / `total_commission_usdt` 仍来自 `orders.commission_usdt`
- `spent_commission_usdt` 来自账本 `OUT / SUCCESS`
- `available_balance_usdt` 来自账本净额

返回字段名没有变化，仍保持兼容：

- `commission_usdt`
- `total_commission_usdt`
- `spent_commission_usdt`
- `available_balance_usdt`

## 已新增的补账脚本

文件：`scripts/backfill_affiliate_transactions.py`

支持参数：

- `--dry-run`
- `--apply`
- `--user-id`
- `--order-id`
- `--limit`

实现方式：

- 脚本拆成可测试的函数层 + CLI 层
- `dry-run` 与 `apply` 共用同一套候选筛选逻辑

候选条件：

- `orders.status = 'SUCCESS'`
- `orders.commission_usdt > 0`
- 当前 referral 可关联
- 账本中不存在相同 `idempotency_key`

候选分类：

- `should_insert`
- `already_exists`
- `missing_referral`

汇总输出包括：

- `candidate_orders`
- `should_insert`
- `already_exists`
- `missing_referral`
- `error`
- `inviter_count`
- `amount_total`

注意：

- 脚本目前还没有执行 `--apply`

## 已完成的测试

### 核心返佣 / 账本测试

文件：`tests/core/test_affiliate_core.py`

已覆盖：

- 首单返佣
- 非首单返佣为 0
- 无 referral
- 非法支付条件直接跳过
- 账本 helper 幂等 SQL
- `details` 完整性
- 同一 invitee 并发两单时最终只有一笔正佣金

### 支付链路回归测试

RMB：

- `tests/services/test_payment_fulfillment_service_affiliate.py`
- 成功路径会写账本
- 已成功订单重复回调不重复落账

TON：

- `tests/services/test_payment_validator_affiliate.py`
- 成功路径会写账本
- 重复 `tx_hash` 不重复落账

Stars：

- `tests/handlers/test_payment_handler_affiliate.py`
- 成功路径会写账本
- 重复 `charge_id` 不重复落账

### 统计测试

文件：`tests/services/test_referral_stats_service.py`

已覆盖：

- 订单总佣金继续来自 `orders`
- 已花费 / 可用余额改为账本聚合
- 账本为空时默认回落到 0

### 补账脚本测试

文件：`tests/scripts/test_backfill_affiliate_transactions.py`

已覆盖：

- 候选分类逻辑
- 汇总逻辑
- `dry-run` / `apply` 共用候选筛选
- `apply` 只处理 `should_insert`
- 成功写入后会删缓存

## 已验证通过的命令

已通过的定向测试包括：

```bash
pytest tests/core/test_affiliate_core.py -q
pytest tests/core/test_affiliate_core.py tests/services/test_payment_fulfillment_service_affiliate.py tests/services/test_payment_validator_affiliate.py tests/handlers/test_payment_handler_affiliate.py -q
pytest tests/services/test_referral_stats_service.py tests/dashboard/test_dashboard_referrals_rewards.py -q
pytest tests/scripts/test_backfill_affiliate_transactions.py -q
```

已通过语法检查：

```bash
python -m py_compile src/core/affiliate_core.py src/services/payment_fulfillment_service.py src/services/payment_validator.py src/handlers/payment_handler.py
python -m py_compile scripts/backfill_affiliate_transactions.py tests/scripts/test_backfill_affiliate_transactions.py
```

## 已做的数据核对

已执行：

```bash
python scripts/backfill_affiliate_transactions.py --dry-run
```

当前 dry-run 结果：

```python
{
  'mode': 'dry-run',
  'candidate_orders': 2383,
  'should_insert': 2383,
  'already_exists': 0,
  'missing_referral': 0,
  'error': 0,
  'inviter_count': 782,
  'amount_total': 1591.3682
}
```

已执行关键 SQL 对账，结果与 dry-run 一致：

- `affiliate_transactions_count = 0`
- `commission_gt_0_orders = 2383`
- `missing_referral_orders = 0`
- `should_backfill = 2383`
- `should_backfill_sum = 1591.3682`
- `distinct_inviters_should_backfill = 782`

结论：

- dry-run 与 SQL 口径一致
- 当前正佣金订单都能关联 referral
- 当前账本仍为空

## 当前明确未完成的事项

- 未执行补账 `--apply`
- 未提交 git
- 未部署上线
- 未做补账后的最终数量 / 金额对账
- 未做最终接口 / Bot smoke test

## 建议重点审查的问题

请重点帮忙 review 以下方面：

1. `affiliate_core.py` 中的 referral 行锁是否足以覆盖“双首单并发”
2. `calculate_and_set_commission_for_paid_order()` 返回 `Referral | None` 的设计是否合适
3. `record_affiliate_commission_transaction()` 的事务边界与幂等处理是否存在遗漏
4. 三条支付链路是否都保持了“订单成功、佣金固化、账本入账”在同一事务内
5. 缓存失效统一放到 `commit()` 之后是否存在遗漏路径
6. `referral_stats_service.py` 切口径后，是否还存在调用方假设 `available_balance_usdt == total_commission_usdt`
7. `backfill_affiliate_transactions.py` 的筛选条件是否与实施方案完全一致
8. `--user-id` 和 `--order-id` 的过滤语义是否符合预期
9. 当前轻量 fake-session 测试是否还需要补真实数据库集成测试
10. 是否存在上线前还应补充的边界校验

## 给审核 AI 的一句话摘要

这次改动实现了 affiliate 返佣账本闭环：扩展 `affiliate_transactions`、在 `affiliate_core` 增加 referral 行锁和账本 helper、接入 RMB/TON/Stars 成功链路、切换余额统计到账本、增加历史补账脚本与测试。数据库 migration 已执行，补账只做了 `dry-run` 和 SQL 对账，还没 `apply`，也还没上线。
