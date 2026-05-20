# Affiliate 二期「返佣兑换身份」实施方案（测试环境可落地版 V2.3）

## 1. 目标

本版把“测试环境先落地”和“全量统一收敛”拆成两个层次，避免因为支付协议与前端改造阻塞返佣兑换身份主链。

### 1.1 本次在测试环境必须交付

1. 返佣余额兑换会员身份 / 月卡权益
2. `MEMBERSHIP_REDEEM / OUT / SUCCESS` 返佣账本闭环
3. 会员结算新 primitive 与 apply helper 落地，并由返佣兑换身份主链真实复用

### 1.2 本次明确不阻塞 MVP 的事项

- 不改 TON 支付前端
- 不改 RMB 支付前端
- 不要求先完成 Stars `ORDER_V2` 全量切换
- 不要求先完成 RMB / TON / Stars 全链路迁到统一写路径

补充红线：

- 本方案任一 Phase 都不得把“修改 TON / RMB 支付前端”作为前置条件
- 若后端协议收敛需要兼容旧前端，必须通过后端双读 / 兼容返回完成，不得把成本转嫁到本次前端改造

### 1.3 后续正式全量版目标

在测试环境 MVP 跑通后，再继续完成：

1. 支付 / 后台赠送迁移到统一写路径
2. `Order.business_order_id + settlement_snapshot + ORDER_V2` 协议收敛
3. 全项目统一到一套会员结算规则、一套写路径、一套审计协议

### 1.4 本期不做

- 提现申请、冻结、审核、打款
- 独立返佣商城
- 复杂失败状态机
- 为返佣兑换身份新增 TON / RMB 前端交互改造

### 1.5 首版业务限制

- 前端只提交 `option_key`、`idempotency_key`
- 前端不得直传 `target_identity`、`duration_days`、`amount_usdt`、`grant_reward_credits`
- 首版只开放 `内门弟子`、`核心弟子`、`真传弟子`
- 首版不开放纯灵石套餐参与返佣兑换
- 首版固定 `grant_reward_credits = false`

## 2. 分层落地策略

### 2.1 MVP（测试环境可落地）

MVP 只要求打通以下主链：

1. `calculate_membership_settlement(...)`
2. `apply_membership_settlement_in_session(...)`
3. `affiliate_redeems` membership 字段兼容迁移
4. `redeem_affiliate_balance_to_membership(...)`
5. `POST /me/affiliate/redeem-membership`
6. PostgreSQL 并发与幂等集成测试

MVP 明确允许：

- RMB / TON / Stars 保持现有前端与现有下单协议
- 现有支付链路暂时继续走 legacy 结算逻辑
- 新 primitive / apply helper 先只服务于 affiliate membership redeem

MVP 验收边界：

- “测试环境可完整测试”仅指返佣兑换身份实施范围可完整验证
- 不包含 TON / RMB 支付前端改造
- 不包含 `ORDER_V2` 全量切换
- 不包含支付链路全部迁到统一写路径后的最终形态回归

### 2.2 Full（正式统一收敛）

Full 阶段再继续完成：

1. `admin_gift_plan()` 迁到业务单 + snapshot + apply helper
2. RMB / Stars / TON 后端迁到统一写路径
3. `Order.business_order_id`、`settlement_snapshot`、`ORDER_V2`
4. 旧支付发货逻辑与重复 `recharge` 日志清理

Full 阶段约束：

- Full 阶段默认也不要求 TON / RMB 支付前端立即改造
- 若未来要彻底删除旧订单标识读法，应单独立项做前端迁移，不属于本次 affiliate membership redeem 实施范围

## 3. 开工前置条件

### 3.1 测试环境 MVP 前置条件

以下条件满足后，即可在测试环境开发并验证返佣兑换身份主链：

1. 统一会员结算 primitive 已落地
2. 统一事务 apply helper 已落地
3. `affiliate_redeems` 已完成字段兼容迁移
4. 测试环境 PostgreSQL 集成测试可运行
5. 已提供灰度开关 `AFFILIATE_MEMBERSHIP_REDEEM_ENABLED`

### 3.2 正式全量上线前置条件

以下条件未完成前，不得把“全量统一版”定义为正式完成：

1. 支付链路与后台赠送已迁到统一写路径
2. `Order.business_order_id` 已完成双写、回填、唯一化
3. Stars `ORDER_V2` 兼容矩阵已完整落地
4. 老 `PENDING` 订单兼容 cutover 已明确并执行完毕

说明：

- 上述前置条件用于定义“全量统一版完成”，不是测试环境 MVP 的阻塞条件
- 即使这些条件尚未完成，也不影响返佣兑换身份在测试环境的完整功能测试

## 4. 硬约束

### 4.1 唯一资产 owner

在测试环境 MVP 范围内：

- `apply_membership_settlement_in_session(...)` 是 `affiliate membership redeem` 的唯一资产 owner：
  - 身份变更
  - 到期时间变更
  - 可选赠送灵石
  - `operation_type="recharge"` 审计日志
- `redeem_affiliate_balance_to_membership(...)` 外层不得再补发币
- `redeem_affiliate_balance_to_membership(...)` 外层不得再补写第二条 `recharge` 日志

在 Full 阶段：

- 该唯一 owner 约束再扩展到支付链路与后台赠送

实现约束：

- `QuotaManager.add_credits()/adjust_credits()` 现状会在复用外部事务时自动写 `user_logs`
- 因此 V2.2 必须先给 `QuotaManager` 增加 `audit_mode`，至少支持：
  - `auto`：保持现状，自动写日志
  - `skip`：只改余额，不写日志
- `apply_membership_settlement_in_session(...)` 只能调用 `audit_mode="skip"` 的 credits primitive
- 统一 `recharge` 日志由 `apply_membership_settlement_in_session(...)` 单独写入一次

### 4.2 统一幂等原则

V2.2 允许在测试环境内短期并存“新旧两套会员结算写路径”，但要求边界清晰：

- affiliate membership redeem 必须走新 primitive + apply helper
- legacy 支付链路在 Full 阶段前允许暂留，但不得阻塞 MVP 上线
- 新链路与旧链路都必须遵守“先唯一锚点，后资产副作用，提交后再失效缓存”的原则

affiliate redeem 链路固定保持短事务模型：

1. 先锁定用户
2. 再检查幂等键是否已占用
3. 再验余额与计算结算结果
4. 最后创建成功态业务记录与账本
5. 提交成功后再做缓存失效

约束：

- affiliate redeem 不引入 `PENDING/FAILED` redeem 状态机
- 不得先发币，再用唯一键兜底“重复成功”
- 不得在提交前失效缓存

### 4.3 不可变 settlement snapshot

V2.2 拆成两层要求：

#### MVP 强制要求

- `affiliate membership redeem` 的首次成功快照必须不可变
- 快照必须完全由固定 option 配置 + 当前结算结果生成
- 幂等重放只能读取首次成功快照，不能回查可变 `MembershipPlan`

#### Full 强制要求

- 订单创建时必须持久化不可变 settlement snapshot
- 后台赠送时必须持久化同类 snapshot
- 发货 / 结算只能读取 snapshot，不能在履约时重新读取可变 `MembershipPlan`

最小 snapshot 字段：

- `schema_version`
- `plan_id`
- `plan_name`
- `display_name`
- `target_identity`
- `duration_days`
- `reward_credits`
- `grant_reward_credits`
- `allow_pure_credit_plan`

### 4.4 纯灵石语义进入 core

`duration_days == 0` 必须由新 primitive 原生表达，不允许再由渠道侧各自补丁。

统一语义：

- 纯灵石套餐不改身份
- 纯灵石套餐不改到期时间
- 是否赠送灵石由 `grant_reward_credits` 与 snapshot 决定

注：

- MVP 的 affiliate membership redeem 首版不开放纯灵石 option
- 但 primitive 必须把该语义原生支持好，避免后续再次改 core

### 4.5 identity 与时间基线

为避免渠道迁移后出现隐性语义漂移，V2.2 写死以下基线：

- `current_identity is None` 或未知身份时，一律按 `外门弟子` 处理
- `current_expire_at is None` 视为当前无有效身份
- 结算内部统一使用单一时间源，默认要求收敛为项目统一时钟函数；在统一时钟函数落地前，所有新 primitive 与 apply helper 必须显式复用同一个 `now`
- API 输出格式统一不等于内部计算基线统一；内部时间基线必须在 primitive 层固定，禁止渠道侧自行调用各自的 `datetime.now()`

### 4.6 幂等命名空间

V2 不修改 `affiliate_redeems` 的唯一键设计，继续保留：

- `(user_id, idempotency_key)` 全局唯一

结论：

- 同一用户下，`credits redeem` 与 `membership redeem` 共享幂等命名空间
- 前端必须为不同 redeem_type 生成不同前缀的幂等键

## 5. 统一会员结算模型

### 5.1 纯规则层

在 `src/core/billing_core.py` 新增：

- `calculate_membership_settlement(...)`

输入：

- `current_identity`
- `current_expire_at`
- `target_identity`
- `duration_days`
- `reward_credits`
- `grant_reward_credits`
- `now`

返回：

- `final_identity`
- `final_expire_at`
- `credits_to_grant`
- `converted_days`
- `settlement_reason`
- `is_pure_credit_plan`
- `kept_current_identity`
- `is_upgrade`
- `is_downgrade`
- `is_same_identity_renewal`

`settlement_reason` 固定枚举：

- `PURE_CREDIT_PLAN`
- `NEW_PURCHASE`
- `RENEWAL`
- `UPGRADE_CONVERSION`
- `DOWNGRADE_EXTENSION`
- `EXPIRED_REPLACE`

### 5.2 事务应用层

新增：

- `src/services/membership_settlement_service.py::apply_membership_settlement_in_session(...)`

输入：

- 已锁定的 `User`
- 不可变 settlement snapshot
- `calculate_membership_settlement(...)` 的结果
- 审计来源信息
- `AsyncSession`

职责：

1. 应用 `final_identity` / `final_expire_at`
2. 按 `credits_to_grant` 调用 `audit_mode="skip"` 的 credits primitive
3. 写唯一一条统一 `recharge` 审计日志
4. 返回完整 settlement snapshot

旧函数处理：

- `calculate_identity_conversion()`
- `calculate_identity_manual_conversion()`

保留为兼容包装层，内部转调新 primitive；新代码不得再直接依赖旧语义。

## 6. 返佣兑换配置

返佣兑换身份不直接依赖可变 `MembershipPlan` 语义，使用固定配置：

- `AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS = {option_key: {...}}`

每个 option 至少包含：

- `schema_version`
- `plan_id`
- `plan_name`
- `display_name`
- `target_identity`
- `duration_days`
- `redeem_amount_usdt`
- `reward_credits`
- `grant_reward_credits`
- `allow_pure_credit_plan`
- `is_enabled`

首版固定：

- `grant_reward_credits = false`
- `allow_pure_credit_plan = false`

约束：

- `affiliate membership redeem` 的首次成功快照必须完全由固定 option 配置生成
- `target_plan_name`、展示名等返回字段不得回查可变 `MembershipPlan.name`
- `MembershipPlan` 在该链路中只允许用于存在性校验或后台关联展示，不得参与快照拼装

## 7. `affiliate_redeems` 与接口

### 7.1 表结构

继续复用 `affiliate_redeems`，新增字段：

- `target_plan_id`
- `target_identity`
- `duration_days`
- `grant_reward_credits`
- `settlement_reason`

必须先改为可空：

- `exchange_rate_snapshot`
- `rounding_mode`

原因：

- `membership redeem` 不存在汇率与 rounding 语义
- 不允许写假值污染数据

`membership redeem` 写法：

- `redeem_type = "MEMBERSHIP"`
- `redeem_option_key = option_key`
- `amount_usdt = redeem_amount_usdt`
- `credits_granted = 实际赠送灵石数`
- `details = 首次成功快照`

### 7.2 快照要求

`affiliate_redeems.details` 至少保存：

- `schema_version`
- `requested_option_key`
- `redeem_option_key`
- `target_plan_id`
- `target_plan_name`
- `target_display_name`
- `target_identity`
- `duration_days`
- `reward_credits`
- `grant_reward_credits`
- `credits_granted`
- `amount_usdt`
- `final_identity`
- `final_expire_at`
- `converted_days`
- `settlement_reason`
- `available_balance_usdt`
- `current_credits`

作用：

- 幂等重放直接返回首次成功快照
- option 下线、plan 改名、配置变更后仍可稳定重放

### 7.3 API

新增：

- `POST /me/affiliate/redeem-membership`

请求体：

- `option_key`
- `idempotency_key`

响应体至少返回：

- `redeem_id`
- `redeem_type`
- `option_key`
- `target_plan_id`
- `target_identity`
- `duration_days`
- `amount_usdt`
- `credits_granted`
- `status`
- `idempotency_key`
- `available_balance_usdt`
- `current_identity`
- `identity_expire_at`
- `current_credits`
- `converted_days`
- `settlement_reason`

约束：

- 金额字段必须按字符串返回
- 时间字段必须统一时区和序列化格式
- `membership redeem` 使用独立 schema，不复用现有 credits redeem 响应模型

## 8. 返佣兑换身份事务流程

新增：

- `src/services/affiliate_redeem_service.py::redeem_affiliate_balance_to_membership(...)`

固定流程：

1. 接收 `user_id`、`option_key`、`idempotency_key`
2. 开启或复用事务
3. `select(User).with_for_update()`
4. 锁内查询既有 `(user_id, idempotency_key)` 的 `AffiliateRedeem`
5. 若已存在，则校验 `redeem_type == MEMBERSHIP`，按快照返回首次成功结果
6. 仅在未命中既有业务单时，读取固定 option 配置
7. 校验 option 启用状态
8. 锁内重算返佣可用余额
9. 校验余额是否足够
10. 调用 `calculate_membership_settlement(...)`
11. 创建 `AffiliateRedeem(redeem_type="MEMBERSHIP")`
12. 写 `AffiliateTransaction(MEMBERSHIP_REDEEM / OUT / SUCCESS)`
13. 调用 `apply_membership_settlement_in_session(...)`
14. 将首次成功快照写入 `affiliate_redeems.details`
15. 提交事务
16. 提交成功后失效返佣缓存

额外约束：

- 第 4 步必须先于读取 option 配置
- 幂等一致性校验不能只比较 `plan_id`
- 至少校验 `redeem_option_key`、`schema_version`、`target_identity`、`duration_days`、`amount_usdt`、`grant_reward_credits`
- 本流程刻意保持“先锁用户，再写成功态 redeem 记录”的短事务模型，不引入 `PENDING/FAILED` redeem 状态机

## 9. 支付与赠送迁移要求（后续 Full 阶段，不阻塞 MVP）

### 9.1 范围界定

以下迁移仍然要做，但不再作为测试环境 MVP 的阻塞前置：

- `src/web_api/routers/payment.py`
- `src/services/payment_fulfillment_service.py`
- `src/services/payment_validator.py`
- `src/handlers/payment_handler.py`
- `src/handlers/callbacks/billing_callbacks.py`
- `dashboard/backend/routers/users.py::admin_gift_plan()`

统一要求保持不变：

- 删除各自内联的身份折算实现
- 删除各自直接改 `user.credits/current_identity/identity_expire_at` 的逻辑
- 统一复用 settlement primitive 与 apply helper
- 统一只保留一条 `recharge` 审计日志
- 缓存失效与外部通知全部延后到最终提交成功后

### 9.2 明确不改前端边界

本次为了让返佣兑换身份先在测试环境落地，明确不做：

- 不改 TON 支付前端
- 不改 RMB 支付前端
- 不为了本次 MVP 强行要求 Web 支付页面改新字段
- 不为了本次 MVP 强行要求 Telegram 购买入口改 payload 协议

结论：

- TON / RMB 前端保持现状
- 需要改的是后续支付后端收敛方案，而不是当前返佣兑换身份入口
- 即使进入 Phase 3 / Phase 4，也默认优先用后端兼容层保证旧前端可继续工作
- 任何需要前端配合切换的事项，必须单独立项，不得回流阻塞本次返佣实施

### 9.3 `ORDER_V2` 协议

Full 阶段新协议仍使用：

- `ORDER_V2:{business_order_id}`

定义：

- `business_order_id` 是全局唯一业务单标识
- 业务单创建时必须已写入不可变 settlement snapshot

结论：

- V2 payload 不再携带 `telegram_id`
- V2 payload 不再携带 `internal_user_id`
- V2 payload 不再携带 `plan_id`
- 用户定位与结算语义全部来自业务单

### 9.4 兼容矩阵

兼容窗口内必须同时支持旧版与新版：

| 入口 | 旧协议 | 新协议 | 要求 |
| --- | --- | --- | --- |
| `billing_callbacks.py` | `ORDER:` | `ORDER_V2:` | 只有在消费端双读完成后才切到 `ORDER_V2:` |
| `precheckout_callback` | 接受 | 接受 | 必须查单并校验订单归属、状态、金额与 snapshot |
| `successful_payment_callback` | 解析 | 解析 | 旧版走兼容解析，新版按 `business_order_id` 取单 |
| `payment_validator.py` | 解析 | 解析 | TON 如继续消费该协议，必须同步支持 V2 |

兼容规则：

- 先上线消费端双读兼容，再切生产端到 `ORDER_V2:`
- 在消费端双读上线前，不得生产 `ORDER_V2:`
- 生产端切到 `ORDER_V2:` 后，旧 `ORDER:` 仍需在兼容窗口内继续消费
- 旧 `ORDER:` 只在兼容窗口内消费
- 兼容窗口结束后删除旧解析逻辑
- 不允许继续使用 `User.telegram_id == user_id OR User.id == user_id` 兜底查人
- `precheckout_callback` 不得只做前缀放行，必须在 `ok=True` 前完成强校验
- RMB / TON 前端若仍依赖旧字段或旧轮询标识，后端必须在兼容窗口内继续提供回退支持

## 10. 审计协议

统一 `recharge` 审计日志至少包含：

- `source`
- `source_channel`
- `source_order_id`
- `source_tx_hash`
- `plan_id`
- `plan_name`
- `option_key`
- `settlement_reason`
- `converted_days`
- `final_identity`
- `credits_granted`

约束：

- 审计日志与资产变更必须同事务提交
- 外部通知不得承担审计职责
- 同一业务单只允许存在一条最终 `recharge` 审计日志

## 11. 实施顺序

### Phase 0：基础改造

1. 给 `QuotaManager` 增加 `audit_mode`
2. 落地 `calculate_membership_settlement(...)`
3. 落地 `apply_membership_settlement_in_session(...)`
4. 将旧 `calculate_identity_*` 改为兼容包装

### Phase 1：返佣兑换身份 MVP

5. 扩展 `affiliate_redeems` 字段并将 `exchange_rate_snapshot/rounding_mode` 改为可空
6. 落地 `AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS`
7. 实现 `redeem_affiliate_balance_to_membership(...)`
8. 新增 `POST /me/affiliate/redeem-membership`
9. 补齐独立响应 schema，金额字段按字符串返回
10. 补齐单测与 PostgreSQL 集成测试

### Phase 2：测试环境验证与灰度

11. 打开 `MEMBERSHIP_SETTLEMENT_V2_ENABLED`
12. 在测试环境灰度 `AFFILIATE_MEMBERSHIP_REDEEM_ENABLED`
13. 验证账本、幂等、余额、身份、审计日志
14. 用真实测试账号走通 Web / TG 返佣兑换身份主链

### Phase 3：后台赠送与支付后端收敛

15. 迁移 `admin_gift_plan()` 到 apply helper
16. 迁移 RMB 后端到统一写路径
17. 迁移 Stars 后端到统一写路径
18. 迁移 TON 后端到统一写路径
19. 删除旧渠道内联结算与重复日志逻辑

### Phase 4：订单与协议收敛

20. 为 `Order` 增加 `business_order_id`
21. 为 `Order` 增加不可变 settlement snapshot
22. 新建单入口进入双写：统一写入 `order_id + business_order_id + settlement_snapshot`
23. 消费方、轮询方、脚本方进入双读：补齐 `business_order_id -> order_id fallback`
24. 回填历史订单的 `business_order_id`
25. 校验回填结果，无空值、无重复后，为 `business_order_id` 加唯一约束
26. 加强 `precheckout_callback`，把查单、归属、状态、金额校验变成强约束
27. 再切 `billing_callbacks.py` 生产 `ORDER_V2:{business_order_id}`
28. 落地老 `PENDING` 订单兼容策略与 cutover 时间

## 12. 测试清单

### 12.1 primitive

至少覆盖：

1. 首次购买
2. 同身份续期
3. 低身份升级高身份
4. 高身份购买低身份折算延长
5. 已过期身份重新购买
6. 纯灵石套餐
7. `grant_reward_credits = false`
8. `grant_reward_credits = true`
9. `current_identity is None` 按 `外门弟子` 处理
10. 未知身份按 `外门弟子` 处理
11. 同一 `now` 输入下，多渠道 primitive 结果一致

### 12.2 affiliate membership redeem MVP

至少覆盖：

1. 余额足够时兑换成功
2. 相同 `idempotency_key` 返回首次成功快照
3. 相同 `idempotency_key` + 不同快照参数返回冲突
4. option 下线或 plan 变更后仍可幂等重放
5. 账本失败时用户身份不更新
6. 身份更新失败时账本不落 `OUT`
7. 若未来开放赠币，不会出现双重加币
8. 不会出现第二条重复 `recharge` 日志

测试完成判定：

- 当上述用例在测试环境全部通过时，可认定“返佣兑换身份实施”已在测试环境完成完整功能测试
- 该结论不依赖 TON / RMB 支付前端改造完成

### 12.3 PostgreSQL 集成测试

至少覆盖：

1. 同一用户并发 membership redeem 不双花
2. `credits redeem` 与 `membership redeem` 并发竞争一致
3. `membership redeem` 与返佣入账并发时余额一致
4. 业务幂等与账本幂等同时生效

### 12.4 Full 阶段回归

至少覆盖：

1. RMB / TON / Stars / admin gift 全部复用统一 primitive
2. 各链路都只保留一条统一 `recharge` 审计日志
3. Stars 新旧 payload 在兼容窗口内都可成功发货
4. TON 如消费订单协议，则新旧 payload 都可正确解析
5. 纯灵石套餐在所有渠道都不改身份
6. `precheckout_callback` 对旧新 payload 都会查单校验，不会放行已支付、过期或串号订单
7. Web 订单状态轮询在双读窗口内可同时兼容 `business_order_id` 与历史 `order_id`
8. 补账脚本在双读窗口内可同时兼容 `business_order_id` 与历史 `order_id`

## 13. 上线策略

开关：

- `MEMBERSHIP_SETTLEMENT_V2_ENABLED`
- `AFFILIATE_MEMBERSHIP_REDEEM_ENABLED`
- Full 阶段再视需要增加 `ORDER_V2` / Stars 独立开关

灰度顺序：

1. 先灰度统一 settlement primitive / apply helper
2. 再灰度 affiliate membership redeem
3. 测试环境验证稳定后，再进入支付 / admin gift 后端收敛
4. 最后再处理 `ORDER_V2`

观测指标：

- `MEMBERSHIP_REDEEM` 账本数与业务单数是否一致
- 同幂等键重放比例
- 冲突错误占比
- 余额不足占比
- 是否出现重复 `recharge` 日志
- 是否出现重复发币

## 14. DoD

### 14.1 测试环境 MVP DoD

- `calculate_membership_settlement(...)` 已落地并通过单测
- `apply_membership_settlement_in_session(...)` 已落地并成为 affiliate membership redeem 的唯一资产 owner
- `affiliate_redeems` 已持久化 membership redeem 关键快照
- 幂等重放稳定返回首次成功快照
- `credits_to_grant` 在新链路中只有一个真实执行入口
- `recharge` 审计日志在新链路中只有一个真实写入入口
- membership redeem 使用独立 schema，金额字段按字符串返回
- PostgreSQL 并发集成测试通过
- 测试环境可实际完成返佣兑换身份功能验证
- 上述验证结论不以 TON / RMB 支付前端改造为前提
- 测试环境可对 affiliate membership redeem 范围做完整测试，但不等于支付全链路统一重构已完成

### 14.2 Full 阶段 DoD

- 全项目会员结算只剩一套 primitive 和一套 apply helper
- 支付、后台赠送、返佣兑换全部遵守统一幂等写路径
- 订单与后台赠送已持久化不可变 settlement snapshot
- Stars / TON 的新旧 payload 在兼容窗口内都可消费
- 兼容窗口结束后旧 payload 解析逻辑可安全删除
