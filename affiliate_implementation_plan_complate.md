# 分享赚灵石（联盟系统）实施状态

本文档基于**当前工作区代码（含未提交修复）+ 当前数据库实查结果**整理，仅保留当前有效结论，作为联盟返佣二期的简明状态说明。

## 1. 范围

本期只处理底层数据与结算语义，不涉及：

- Bot / Web 新 UI
- 新菜单入口
- 提现审核流

## 2. 核心口径

当前实现统一遵循以下规则：

- `orders.telegram_id` 实际存的是 `users.id`（内部用户 ID）
- `referrals.inviter_id` / `referrals.invitee_id` 也都是 `users.id`
- 佣金固化以 `orders.commission_usdt` 为准
- 渠道分类以 `orders.payment_channel` 为准
- 首单判定以 `orders.paid_at` 为准
- 返佣统计统一按内部用户 ID 聚合

## 3. 已完成

### 3.1 数据库与迁移

已落地：

- `orders.commission_usdt`
- `orders.payment_channel`
- `orders.paid_at`
- `affiliate_transactions` 表

迁移脚本：

- `migrations/versions/9d7f1c2a4b11_add_affiliate_fields_and_transactions.py`

已实现的历史回填：

- 按保守规则回填 `payment_channel`
- 按保守规则回填 `paid_at`
- 仅对 `paid_at` 可判定的历史首单补 `commission_usdt`

### 3.2 支付链路

已完成三条支付链路接入：

- RMB：`SELECT ... FOR UPDATE` 锁单幂等，成功后写入 `payment_channel='RMB'`、`paid_at`
- TON：成功建单时写入 `payment_channel='TON'`、`paid_at`
- Stars：成功建单时写入 `payment_channel='XTR'`、`paid_at`

统一佣金入口已落地：

- `src/core/affiliate_core.py`
- `calculate_and_set_commission_for_paid_order()`

### 3.3 统计层

共享统计服务已落地：

- `src/services/referral_stats_service.py`

已接入路径：

- `src/services/permission_service.py`
- `dashboard/backend/routers/referrals.py`

当前未统一切换、仍保留局部直查的路径：

- `dashboard/backend/routers/stats.py`
- `dashboard/backend/routers/users.py`

当前统计规则：

- 充值金额按 `payment_channel` 分类累计
- 返佣金额只统计 `orders.commission_usdt`
- 不再按 `order_id` 前缀、金额阈值或旧字段临时猜渠道
- `payment_channel IS NULL` 的历史异常单不计入渠道汇总

## 4. 本次补充验证

### 4.1 SQL 验证

已对当前数据库执行最小验证 SQL，确认：

- 用户侧邀请充值统计与数据库聚合一致
- Dashboard 返佣榜的主字段与数据库聚合一致

验证字段包括：

- `recharged_invitees_count`
- `total_recharge_count`
- `total_ton`
- `total_rmb`
- `total_stars`
- `commission_usdt`
- `total_invitations`
- `conversion_rate`

### 4.2 接口巡检

已完成以下接口巡检：

- 用户侧：`GET /api/users/me`
- Dashboard：`GET /api/referrals/rewards`

巡检结论：

- 用户侧 `invitation_recharge` 与 SQL 完全一致
- Dashboard 原先仅 `commission_usdt` 存在轻微舍入漂移，当前工作区已修复

## 5. 当前工作区补充修复

### 5.1 修复内容

当前工作区已修复 Dashboard `commission_usdt` 舍入漂移问题：

- 问题根因：`query_referral_rewards()` 之前在 invitee 维度中间过程提前 `round(..., 2)`
- 修复方式：内部累计阶段保留原始精度，只在最终出参前统一 round

涉及文件：

- `src/services/referral_stats_service.py`

### 5.2 修复后结果

修复后已再次对比：

- SQL 聚合结果
- `/api/referrals/rewards` 接口返回结果

当前工作区下，`commission_usdt` 已与数据库聚合一致。

## 6. 已补测试

已新增并在当前工作区通过以下测试：

- `tests/services/test_referral_stats_service.py`
  - 锁定 service 层 `commission_usdt` 汇总精度
- `tests/dashboard/test_dashboard_referrals_rewards.py`
  - 锁定 Dashboard 路由 `/api/referrals/rewards` 的真实返回口径

当前已明确覆盖：

- 多笔小额佣金汇总时不再发生中间舍入漂移
- Dashboard 鉴权中间件 + 路由层 + service 汇总链路可正确返回结果

## 7. 现网巡检快照

基于本次实查，当前数据库状态如下：

- `payment_channel = 'RMB'`：`5097`
- `payment_channel = 'TON'`：`133`
- `payment_channel = 'XTR'`：`886`
- `payment_channel IS NULL`：`36`
- `paid_at IS NOT NULL`：`3639`
- `status = 'SUCCESS' AND paid_at IS NULL`：`36`
- `commission_usdt > 0`：`2378`
- `affiliate_transactions` 当前记录数：`0`

说明：

- 历史保守回填已实际生效
- 仍保留一批无法安全判定的历史单，不参与自动补佣

## 8. 尚未完成

以下内容仍未落地或仅保留占位：

- `affiliate_transactions` 账务闭环尚未接入实际业务写入
- `spent_commission_usdt` 当前仍固定为 `0`
- `available_balance_usdt` 当前仍等于总返佣
- 提现、兑换灵石、兑换身份等后续流程尚未实现
- 历史回填的“抽样校验 / 复核清单”能力仍偏弱，当前以计数输出为主
- 计划中的完整支付并发 / 历史回填回归测试还未全部补齐

## 9. 当前结论

截至目前，联盟返佣底座已经完成以下关键目标：

- `orders` 联盟字段已落地
- 三条支付链路已接入首单佣金固化
- 历史数据已在可确定范围内回填
- 用户中心与 Dashboard 返佣榜已切换到统一返佣统计口径
- Dashboard 其他统计入口仍存在局部直查，尚未全部收口到共享统计服务
- Dashboard `commission_usdt` 舍入漂移已在当前工作区修复并补测试锁定

可作为当前准确版本继续使用；后续若提交当前工作区修复并推进账本闭环，再单独追加文档即可。
