# Affiliate 二期「返佣兑换灵石」本轮改动记录

## 1. 目标需求

- 落地 affiliate 二期第一阶段：返佣兑换灵石
- 先完成最小资产闭环，而不是只加一个接口
- 重点解决三件事：
  - 返佣余额可兑换为站内 `credits`
  - `affiliate_transactions` 与 `users.credits` 同事务提交
  - 旧扣费/退款链不再依赖负数扣费复用语义

## 2. 本轮实际修改范围

### 2.1 credits 事务原语治理

- 在 `src/quota.py` 新增可复用的事务内 credits 变更原语：
  - `adjust_credits()`
  - `deduct_credits()`
  - `add_credits()`
- 支持调用方传入 `AsyncSession`，用于和主事务复用
- 扣费改为锁内原子校验，不再是“先查后扣”
- 退款改为显式加币，不再允许 `deduct_credits(-cost)`

### 2.2 旧调用链迁移

- `src/core/billing_core.py`
  - `check_and_deduct_credits()` 改为直接走原子扣费
  - `refund_credits()` 改为走显式 `add_credits()`
- `src/services/permission_service.py`
  - `increment_quota()` 改为显式加币语义
  - 新增 `refund_quota()`
- 已同步迁移退款调用点：
  - `src/services/recovery_service.py`
  - `src/services/zombie_cleaner_service.py`
  - `dashboard/backend/routers/system.py`
  - `scripts/clear_stuck_tasks.py`

### 2.3 affiliate 兑换主链

- 新增业务表模型：`affiliate_redeems`
- 新增 Alembic 迁移：`migrations/versions/f1c9a6d7e2b3_add_affiliate_redeems_table.py`
- 新增兑换 service：`src/services/affiliate_redeem_service.py`
- 新增用户侧 API：
  - `POST /me/affiliate/redeem-credits`
- 新增 schema：
  - `src/web_api/schemas/affiliate_redeem_schema.py`

## 3. 当前实现口径

- 当前采用灵活 USDT 兑换，不是固定档位
- 兑换比例：`1 USDT = 90 credits`
- `amount_usdt` 服务端按 4 位小数处理
- `credits_granted = amount_usdt * 90` 后按 `ROUND_HALF_UP` 四舍五入
- 账本写法固定为：
  - `transaction_type = CREDITS_REDEEM`
  - `direction = OUT`
  - `status = SUCCESS`
  - `reference_type = AFFILIATE_REDEEM`

## 4. 展示层本轮调整

### 4.1 已做

- TG 个人中心已改为区分：
  - 历史累计返佣
  - 已兑换返佣
  - 当前可兑换余额
- Dashboard 已明确为“历史累计返佣榜”，不再表述成当前余额面板

### 4.2 未做

- Web 端展示本轮按要求未改

## 5. 测试覆盖

- 已补基础回归测试：
  - `tests/core/test_billing_core.py`
  - `tests/services/test_affiliate_redeem_service.py`
  - `tests/web_api/test_users_affiliate_redeem.py`
  - `tests/handlers/test_message_handler.py`
- 已补 PostgreSQL 并发集成测试：
  - `tests/integration/test_affiliate_redeem_integration.py`
- 当前已验证场景：
  - 并发兑换不双花
  - 同一 `idempotency_key` 稳定返回首次成功结果
  - 同一 `idempotency_key` 不同金额返回冲突

## 6. 影响说明

- 正向影响：
  - affiliate 兑换灵石已具备最小可联调闭环
  - 主扣费/退款链语义更清晰，风险比原来低
  - TG / Dashboard 对返佣字段的展示语义更准确
- 仍未完成：
  - Web 展示迁移
  - “兑换 vs 支付发货加返佣”交叉并发回归
  - 后台高风险绝对赋值入口的进一步隔离
