# Affiliate 二期「返佣兑换身份」实施方案（可执行版 V2.1）

## 1. 目标

本期只交付三件事：

1. 返佣余额兑换会员身份 / 月卡权益
2. `MEMBERSHIP_REDEEM / OUT / SUCCESS` 返佣账本闭环
3. 全项目会员结算统一到一套规则、一套写路径、一套审计协议

本期不做：

- 提现申请、冻结、审核、打款
- 独立返佣商城
- 复杂失败状态机

首版业务限制：

- 前端只提交 `option_key`、`idempotency_key`
- 前端不得直传 `target_identity`、`duration_days`、`amount_usdt`、`grant_reward_credits`
- 首版只开放 `内门弟子`、`核心弟子`、`真传弟子`
- 首版不开放纯灵石套餐参与返佣兑换
- 首版固定 `grant_reward_credits = false`

## 2. 开工前置条件

以下条件未完成前，不得开发或上线返佣兑换身份主链：

1. 统一会员结算 primitive 已落地
2. 统一事务 apply helper 已落地
3. 支付链路与后台赠送已迁到统一写路径
4. `affiliate_redeems` 已完成字段兼容迁移
5. Stars `ORDER_V2` 兼容矩阵已完整落地

## 3. 硬约束

### 3.1 唯一资产 owner

- `apply_membership_settlement_in_session(...)` 是以下动作的唯一 owner：
  - 身份变更
  - 到期时间变更
  - 可选赠送灵石
  - `operation_type="recharge"` 审计日志
- 任何外层调用方不得再补发币
- 任何外层调用方不得再补写第二条 `recharge` 日志

实现约束：

- `QuotaManager.add_credits()/adjust_credits()` 现状会在复用外部事务时自动写 `user_logs`
- 因此 V2 必须先给 `QuotaManager` 增加 `audit_mode`，至少支持：
  - `auto`：保持现状，自动写日志
  - `skip`：只改余额，不写日志
- `apply_membership_settlement_in_session(...)` 只能调用 `audit_mode="skip"` 的 credits primitive
- 统一 `recharge` 日志由 `apply_membership_settlement_in_session(...)` 单独写入一次

### 3.2 统一幂等原则

V2.1 不再强行要求所有链路共用完全相同的事务顺序，只统一幂等原则与资产副作用边界。

支付 / 后台赠送链路必须遵守：

1. 解析请求 / 回调
2. 先持久化唯一业务单或唯一外部流水
3. 再锁定用户
4. 再执行资产副作用
5. 同事务写账本 / 审计
6. 提交成功后再做缓存失效和外部通知

affiliate redeem 链路保持现有短事务模型：

1. 先锁定用户
2. 再检查幂等键是否已占用
3. 再验余额与计算结算结果
4. 最后创建成功态业务记录与账本
5. 提交成功后再做缓存失效

约束：

- 支付 / 后台赠送不得先改 `users.credits/current_identity/identity_expire_at`，再插业务单
- affiliate redeem 不引入 `PENDING/FAILED` 业务状态机
- 所有链路都不得先发币，再用唯一键兜底“重复成功”
- 所有链路都不得在提交前失效缓存

### 3.3 不可变 settlement snapshot

统一 settlement primitive 只解决“怎么算”，不能解决“按什么语义算”。V2.1 明确要求：

- 订单创建时必须持久化不可变 settlement snapshot
- 后台赠送时必须持久化同类 snapshot
- 发货 / 结算只能读取 snapshot，不能在履约时重新读取可变 `MembershipPlan` 作为真实语义源

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

### 3.4 纯灵石语义进入 core

`duration_days == 0` 必须由新 primitive 原生表达，不允许再由渠道侧各自补丁。

统一语义：

- 纯灵石套餐不改身份
- 纯灵石套餐不改到期时间
- 是否赠送灵石由 `grant_reward_credits` 与 snapshot 决定

### 3.5 identity 与时间基线

为避免渠道迁移后出现隐性语义漂移，V2.1 写死以下基线：

- `current_identity is None` 或未知身份时，一律按 `外门弟子` 处理
- `current_expire_at is None` 视为当前无有效身份
- 结算内部统一使用单一时间源，默认要求收敛为项目统一时钟函数；在统一时钟函数落地前，所有新 primitive 与 apply helper 必须显式复用同一个 `now`
- API 输出格式统一不等于内部计算基线统一；内部时间基线必须在 primitive 层固定，禁止渠道侧自行调用各自的 `datetime.now()`

### 3.6 幂等命名空间

V2 不修改 `affiliate_redeems` 的唯一键设计，继续保留：

- `(user_id, idempotency_key)` 全局唯一

结论：

- 同一用户下，`credits redeem` 与 `membership redeem` 共享幂等命名空间
- 前端必须为不同 redeem_type 生成不同前缀的幂等键

## 4. 统一会员结算模型

### 4.1 纯规则层

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

### 4.2 事务应用层

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

## 5. 订单与赠送模型调整

### 5.1 订单侧

`Order` 需要同时解决两件事：不可变 settlement snapshot 与唯一业务单标识。

`Order` 必须新增或持久化：

- `business_order_id`
- `settlement_schema_version`
- `settlement_snapshot`

硬约束：

- `business_order_id` 必须是全局唯一字段
- `ORDER_V2:{business_order_id}` 中的 `business_order_id` 指向该唯一字段，不得直接复用当前非唯一的 `orders.order_id`
- `orders.order_id` 在完成唯一化改造前，只能视为渠道侧单号，不得再被文档定义为统一幂等锚点

规则：

- 创建订单时同时写入 `business_order_id` 与 snapshot
- 履约时只读 snapshot
- `MembershipPlan` 仅用于下单阶段生成 snapshot，不参与回调阶段的最终发货语义
- RMB / Stars / TON / admin gift 统一以 `business_order_id` 或唯一外部流水作为幂等锚点

强制迁移 choreography：

1. 先给 `orders` 扩 `business_order_id`，初期允许为空，且暂不加唯一约束
2. 新建单入口开始双写 `order_id + business_order_id`
3. 所有消费方、轮询方、脚本方进入双读窗口：优先读 `business_order_id`，缺失时回退 `order_id`
4. 回填历史订单的 `business_order_id`
5. 校验无空值、无重复后，再为 `business_order_id` 加唯一约束
6. 唯一约束生效后，生产侧才允许切到 `ORDER_V2:{business_order_id}`
7. 兼容窗口结束后，删除以 `order_id` 充当业务单锚点的旧读法

双读 / 双写窗口必须覆盖：

- Web RMB 建单与状态轮询
- RMB 发货
- Stars payload 生产与消费
- TON 订单解析与去重兜底
- 返佣补账脚本及其他离线脚本

### 5.2 旧 `PENDING` 订单兼容

切换到 snapshot 发货前，必须处理已经存在但尚未支付完成的历史 `PENDING` 订单。

V2.1 采用双路径兼容：

- cutover 时间之前创建的 `PENDING` 订单继续走旧发货路径
- cutover 时间之后创建的新订单必须强制写入 `business_order_id` 与 `settlement_snapshot`
- 新发货逻辑优先读取 snapshot；若命中 cutover 前老订单，则按旧路径兼容履约

约束：

- 兼容窗口必须有明确结束时间
- 兼容窗口结束后，未支付老订单统一作废或迁移，不允许永久保留双语义
- 文档和代码都要显式区分“老订单兼容路径”和“新订单 snapshot 路径”
- 历史 `PENDING` 订单如参与 `business_order_id` 回填，必须在双读窗口内完成，避免轮询接口、回调与脚本对同一订单使用不同标识

### 5.3 后台赠送侧

`admin_gift_plan()` 不再直接改用户资产。

V2.1 统一改为：

1. 创建一条 `payment_channel="ADMIN_GIFT"` 的业务单
2. 同时写入不可变 settlement snapshot
3. 调用统一 apply helper 发货
4. 同事务写统一审计日志

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

## 9. 支付与赠送迁移要求

### 9.1 统一迁移范围

必须迁移的代码：

- `src/web_api/routers/payment.py`
- `src/services/payment_fulfillment_service.py`
- `src/services/payment_validator.py`
- `src/handlers/payment_handler.py`
- `src/handlers/callbacks/billing_callbacks.py`
- `dashboard/backend/routers/users.py::admin_gift_plan()`

统一要求：

- 删除各自内联的身份折算实现
- 删除各自直接改 `user.credits/current_identity/identity_expire_at` 的逻辑
- 统一复用 settlement primitive 与 apply helper
- 统一只保留一条 `recharge` 审计日志
- 缓存失效与外部通知全部延后到最终提交成功后

### 9.2 Stars / TON payload 协议

V2.1 新协议使用：

- `ORDER_V2:{business_order_id}`

定义：

- `business_order_id` 是全局唯一业务单标识
- 业务单创建时必须已写入不可变 settlement snapshot

结论：

- V2 payload 不再携带 `telegram_id`
- V2 payload 不再携带 `internal_user_id`
- V2 payload 不再携带 `plan_id`
- 用户定位与结算语义全部来自业务单

### 9.3 兼容矩阵

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

### 9.4 渠道具体要求

RMB：

- 保持“先锁业务单，再发货”的骨架
- 补齐 snapshot 发货
- 删除提交后单独补 `recharge` 日志的旧路径

Stars：

- 发票生成前先创建 `PENDING` 业务单
- invoice payload 改为 `ORDER_V2:{business_order_id}`
- `precheckout_callback` 必须按 payload 查单，并校验：
  - 订单存在
  - 订单归属当前用户
  - 订单状态仍为 `PENDING`
  - 支付金额与 snapshot 一致
- 上述任一条件不满足时必须 `ok=False`，不得放到 `successful_payment_callback` 再失败
- `successful_payment_callback` 先按业务单 / 外部流水做幂等，再执行资产副作用

TON：

- 若继续复用订单协议，链上 memo 同步升级为 `ORDER_V2:{business_order_id}`
- 先按唯一外部流水或唯一业务单幂等落单，再执行资产副作用
- 纯灵石套餐语义改为走新 primitive，不再使用渠道侧分支

后台赠送：

- 创建业务单并写 snapshot
- 统一走 apply helper
- 保证与支付链路相同的行锁与事务审计约束

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

### Phase 1：订单与协议收敛

5. 为 `Order` 增加全局唯一 `business_order_id`
6. 为 `Order` 增加不可变 settlement snapshot
7. 新建单入口进入双写：迁移 `src/web_api/routers/payment.py` 与 `billing_callbacks.py`，统一写入 `order_id + business_order_id + settlement_snapshot`
8. 消费方、轮询方、脚本方进入双读：补齐 `precheckout_callback`、`successful_payment_callback`、`payment_validator.py`、订单状态轮询与补账脚本的 `business_order_id -> order_id fallback`
9. 回填历史订单的 `business_order_id`
10. 校验回填结果，无空值、无重复后，为 `business_order_id` 加唯一约束
11. 加强 `precheckout_callback`，把查单、归属、状态、金额校验变成强约束
12. 再切 `billing_callbacks.py` 生产 `ORDER_V2:{business_order_id}`
13. 落地老 `PENDING` 订单兼容策略与 cutover 时间
14. 迁移 `admin_gift_plan()` 到业务单 + snapshot + apply helper

### Phase 2：支付链路迁移

15. 迁移 RMB 到统一写路径
16. 迁移 Stars 到统一写路径
17. 迁移 TON 到统一写路径
18. 删除旧渠道内联结算与重复日志逻辑

### Phase 3：返佣兑换身份

19. 扩展 `affiliate_redeems` 字段并将 `exchange_rate_snapshot/rounding_mode` 改为可空
20. 实现 `redeem_affiliate_balance_to_membership(...)`
21. 新增 `POST /me/affiliate/redeem-membership`
22. 补齐单测与 PostgreSQL 集成测试
23. 通过开关灰度上线

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

### 12.2 支付与赠送回归

至少覆盖：

1. RMB / TON / Stars / admin gift 全部复用统一 primitive
2. 各链路都只保留一条统一 `recharge` 审计日志
3. Stars 新旧 payload 在兼容窗口内都可成功发货
4. TON 如消费订单协议，则新旧 payload 都可正确解析
5. 纯灵石套餐在所有渠道都不改身份
6. `precheckout_callback` 对旧新 payload 都会查单校验，不会放行已支付、过期或串号订单
7. Web 订单状态轮询在双读窗口内可同时兼容 `business_order_id` 与历史 `order_id`
8. 补账脚本在双读窗口内可同时兼容 `business_order_id` 与历史 `order_id`

### 12.3 affiliate membership redeem

至少覆盖：

1. 余额足够时兑换成功
2. 相同 `idempotency_key` 返回首次成功快照
3. 相同 `idempotency_key` + 不同快照参数返回冲突
4. option 下线或 plan 变更后仍可幂等重放
5. 账本失败时用户身份不更新
6. 身份更新失败时账本不落 `OUT`
7. 若未来开放赠币，不会出现双重加币
8. 不会出现第二条重复 `recharge` 日志

### 12.4 PostgreSQL 集成测试

至少覆盖：

1. 同一用户并发 membership redeem 不双花
2. `credits redeem` 与 `membership redeem` 并发竞争一致
3. `membership redeem` 与返佣入账并发时余额一致
4. 业务幂等与账本幂等同时生效
5. 支付链路迁移后端到端回归通过

## 13. 上线策略

开关：

- `MEMBERSHIP_SETTLEMENT_V2_ENABLED`
- `AFFILIATE_MEMBERSHIP_REDEEM_ENABLED`
- 必要时为 Stars 单独拆开关

灰度顺序：

1. 先灰度统一 settlement
2. 再灰度支付 / admin gift 迁移
3. 最后灰度 affiliate membership redeem

观测指标：

- `MEMBERSHIP_REDEEM` 账本数与业务单数是否一致
- 同幂等键重放比例
- 冲突错误占比
- 余额不足占比
- 是否出现重复 `recharge` 日志
- 是否出现重复发币

## 14. DoD

- 全项目会员结算只剩一套 primitive 和一套 apply helper
- `apply_membership_settlement_in_session(...)` 成为唯一资产 owner
- 支付、后台赠送、返佣兑换全部遵守统一幂等写路径
- 订单与后台赠送已持久化不可变 settlement snapshot
- `affiliate_redeems` 已持久化 membership redeem 关键快照
- 幂等重放稳定返回首次成功快照
- `credits_to_grant` 只有一个真实执行入口
- `recharge` 审计日志只有一个真实写入入口
- Stars / TON 的新旧 payload 在兼容窗口内都可消费
- 兼容窗口结束后旧 payload 解析逻辑可安全删除
- membership redeem 使用独立 schema，金额字段按字符串返回
- PostgreSQL 并发集成测试通过
