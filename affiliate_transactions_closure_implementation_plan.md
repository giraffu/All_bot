# RFC：`affiliate_transactions` 二期闭环实施方案

本文档是 `affiliate_transactions` 二期闭环的实施 RFC。它不再重复一期的完整设计论证，而是基于**当前代码、当前数据库、以及 2026-05-18 维护窗口已完成的补账上线结果**，明确以下内容：

1. 一期已经交付了什么，以及当前系统的真实基线
2. 二期要新增哪些能力，不做哪些能力
3. 二期必须遵守的实现约束、锁模型、幂等模型与统计口径
4. 推荐的落地顺序、测试要求与上线验收方式

---

## 1. 当前基线

### 1.1 已上线能力

当前线上已经完成并验证以下能力：

- `affiliate_transactions` 已扩展为可用账本表，包含 `direction`、`reference_type`、`reference_id`、`idempotency_key`
- 三条支付成功链路（RMB / TON / Stars）都已接入返佣固化与账本写入
- 支付成功后的返佣入账，已经做到**订单成功、佣金固化、账本写入同事务提交**
- `affiliate_transactions` 入账幂等已切到数据库级，核心键为 `affiliate:commission:order:{order.id}`
- 历史补账脚本 `scripts/backfill_affiliate_transactions.py` 已支持 `--dry-run` / `--apply`
- 补账脚本已经按“历史已固化佣金回放”口径修正；当前候选筛选以 `orders.status = SUCCESS && commission_usdt > 0` 为准，不再依赖 `payment_channel / paid_at` 等支付字段是否存在
- 用户侧 `query_invitation_recharge_stats()` 已切换为：
  - `total_commission_usdt` 继续来自 `orders.commission_usdt`
  - `spent_commission_usdt` 来自账本 `OUT/SUCCESS`
  - `available_balance_usdt` 来自账本净额
- Dashboard / Admin 侧 `query_referral_rewards()` 仍保留历史聚合路径，二期需要与用户侧一起统一口径与字段命名

### 1.2 维护窗口结果快照

以下结果仅作为背景记录，不应写死进脚本断言；后续仍以实时 SQL 为准。

- 历史补账 `dry-run` 结果：
  - `candidate_orders = 2388`
  - `should_insert = 2388`
  - `missing_referral = 0`
  - `amount_total = 1595.5474`
- 历史补账 `apply` 结果：
  - `inserted = 2388`
  - `skipped_during_apply = 0`
  - `error = 0`
- 补账后对账结果：
  - `affiliate_transactions_count = 2388`
  - `should_backfill_remaining = 0`
  - `orders.commission_usdt > 0` 数量与账本 `COMMISSION_ACCRUAL / IN / SUCCESS` 数量一致
  - `orders.commission_usdt` 金额总和与账本入账金额总和一致
  - `idempotency_key` 无重复

### 1.3 当前数据口径

当前系统可以视为已经进入“一期已闭环、二期待扩展”的状态：

- `orders.commission_usdt` 是订单层固化佣金事实
- `affiliate_transactions` 是返佣余额主账本
- 当前账本里已存在且在线新增的主要都是：
  - `transaction_type = 'COMMISSION_ACCRUAL'`
  - `direction = 'IN'`
  - `status = 'SUCCESS'`
- 当前 `available_balance_usdt` 的定义仍是：
  - `SUM(IN, SUCCESS) - SUM(OUT, SUCCESS)`
- 这意味着：
  - **二期内部消费**可以直接复用 `OUT/SUCCESS` 账本语义
  - **二期提现**不应继续拿“空想的 `OUT/PENDING`”伪装冻结余额，而应单独建模

---

## 2. 二期目标与推荐顺序

二期的目标不是继续修补一期，而是把“返佣可入账”升级为“返佣可安全使用”。

推荐按以下顺序推进：

1. **二期 A：返佣兑换灵石**
2. **二期 B：返佣兑换身份 / 月卡权益**
3. **二期 C：提现申请 / 审核 / 打款闭环**

排序理由：

- A / B 都是站内闭环，外部依赖少，事务边界清晰
- C 涉及冻结、审核、外部打款与失败补偿，是风险最高的一段
- 若一开始把提现与站内消费混做，会同时放大余额语义、风控规则与后台流程复杂度

---

## 3. 范围与非范围

### 3.1 本期建议纳入范围

二期建议纳入：

1. 返佣兑换灵石
2. 返佣兑换身份或会员时长
3. 提现申请单模型
4. 提现冻结余额模型
5. 审核通过后的实际出账
6. 拒绝 / 取消后的冻结释放
7. 返佣账本在消费与提现场景下的完整对账能力

### 3.2 本期不建议纳入范围

当前二期先不要扩展：

- 复杂费率模板系统
- 多层级邀请返佣
- 历史 inviter 快照回溯修复
- 用户自行修改提现账户的版本对账系统
- 自动打款机器人
- 财务总账对接外部 ERP

---

## 4. 核心设计原则

### 4.1 账本继续只承载“已生效事实”

延续一期原则：

- `affiliate_transactions` 只记录已经生效的资产事实
- 不把“待审核”“待打款”“待确认”这种中间态直接塞进账本主表

因此：

- 返佣兑换灵石 / 身份：业务成功即写 `OUT/SUCCESS`
- 提现申请：先进入**提现业务表**，冻结余额通过业务表状态体现
- 提现打款成功：再写账本 `OUT/SUCCESS`

### 4.2 可用余额与冻结余额分离

二期起建议把余额语义拆成：

- `ledger_balance_usdt = SUM(IN,SUCCESS) - SUM(OUT,SUCCESS)`
- `frozen_balance_usdt = SUM(active withdrawal frozen amount)`
- `available_balance_usdt = ledger_balance_usdt - frozen_balance_usdt`

实现前提与锁模型统一如下：

- 当前系统不存在独立的 affiliate balance 行；余额来自账本与提现业务表聚合
- 因此所有“校验余额后再消费 / 提现”的流程，都必须在**同一用户级串行化事务**内重算余额后再决定是否落业务单与 `OUT/SUCCESS`
- 二期默认沿用 `users FOR UPDATE` 作为用户级串行化锁；若未来改成 advisory lock，必须做全项目统一迁移
- 对于影响 inviter 可用返佣余额的用户主动操作，固定锁顺序为：
  - `users FOR UPDATE`
  - 业务幂等 claim
  - 余额重算
  - 业务单创建或补完
  - 状态落定 / 账本写入
- 对于后台提现流转，固定锁顺序为：`users FOR UPDATE -> affiliate_withdrawals FOR UPDATE -> 状态检查/幂等 -> 状态更新或账本落账`
- invitee 支付成功触发的返佣入账**不额外**抢 inviter 的 `users` 锁；当前首单返佣资格仍以 `Referral(invitee_id) FOR UPDATE` 串行化，消费侧通过“持锁重算余额”避免双花

需要明确：

- 上述是**二期目标锁序**，不是对现网所有资产链路现状的描述
- 当前确有多条资产链路已复用 `users FOR UPDATE`，但完整锁顺序并未全量统一，例如 RMB 发货仍是“先锁订单再锁用户”
- 因此二期开工前必须先完成 `users.credits` 写路径审计，至少覆盖 RMB / TON / Stars / 签到 / 邀请奖励 / 任务扣费，并明确哪些链路仍与目标锁序不一致

禁止：

- 在事务外先读一次 `available_balance_usdt`，事务内直接假设余额未变化
- 在 affiliate 新链路里写成“先 claim `idempotency_key`，再锁 `users`”
- 只对“用户申请提现”加锁，却让后台审核 / 打款 / 取消 / 拒绝绕开同一把锁
- 要求“返佣入账也必须抢 inviter 锁”，但又不给出全链路锁序审计与死锁评估

### 4.3 一切消费都必须可追溯到业务引用

二期所有新的 `OUT/SUCCESS` 都必须可追溯：

- 兑换灵石：引用兑换单或兑换操作 id
- 兑换身份：引用权益订单或兑换操作 id
- 提现打款：引用 `withdrawal.id`

禁止：

- 只写一条模糊的 `OUT` 流水，不带业务引用
- 用自由文本备注代替结构化 `reference_type/reference_id`

### 4.4 幂等必须分层，且业务级唯一

二期不能只设计“账本幂等”，还必须同时设计“业务请求幂等”。

建议拆成两层：

- **第一层：业务请求幂等**
  - `affiliate_redeems.idempotency_key`：保护“创建兑换单”本身
  - `affiliate_withdrawals.idempotency_key_apply`：保护“创建提现申请单”本身
  - 这层必须靠数据库唯一约束直接 claim，不能靠先查后插
  - **claim、业务单创建/补完、余额校验、状态落定必须放在同一个主事务内完成**
  - 对于用户主动发起、且会影响返佣余额的操作，claim 必须服从上一节锁顺序：**先拿 `users FOR UPDATE`，再在同事务内 claim**
  - **不允许**在主事务外先占住 `idempotency_key` 再进入后续事务，否则失败后会留下不可恢复的“占坑键”
- **第二层：账本/结算幂等**
  - `affiliate:redeem:credits:{redeem.id}`
  - `affiliate:redeem:membership:{redeem.id}`
  - `affiliate:withdrawal:payout:{withdrawal.id}`
  - 这层用于保护 `affiliate_transactions` 的真实 `OUT/SUCCESS` 落账

额外要求：

- 提现成功回写除了 `idempotency_key_payout` 外，还要对外部回单号 `paid_reference` 加唯一约束，避免同一外部打款回单被重复认领到不同提现单
- 若业务请求命中重复 `idempotency_key`，应返回既有业务单或既有成功结果，而不是再创建第二张业务单
- 若主事务回滚，则本次业务 claim 也必须一并回滚，不允许留下“键已占用但业务单不存在 / 状态未定”的半完成状态

禁止：

- 用 `user_id + timestamp` 这类弱幂等键
- 只给账本加幂等，业务表本身却允许重复创建
- 依赖“先查后插”作为唯一防重手段
- 在事务外单独插入一条“占坑记录”或提前提交 `idempotency_key`，再在第二个事务里做真实扣账 / 落单

### 4.5 用户侧审计流水（`UserLog`）契约

二期需要额外明确：当前 `affiliate_transactions` 是返佣主账本，但用户侧仍已有一套以 `user_logs` 为载体的灵石审计流水。

- `affiliate_transactions` 继续作为返佣主账本，只承载返佣资产事实
- `user_logs` 只作为**用户可见审计流水 / 附属账**，不承载返佣主余额事实
- 因此二期不能把“是否成功写 `user_logs`”作为返佣主资产提交与否的判断条件

建议固定以下约定：

- `affiliate_redeem_credits`：
  - `credit_change = +credits_granted`
  - `current_balance` 为兑换后的 `users.credits`
- `affiliate_redeem_membership`：
  - 首版若需要给用户侧留痕，可记 `credit_change = 0`
  - 若暂不需要用户侧可见流水，至少保留业务表审计信息
- `affiliate_withdrawal_paid`：
  - 建议记 `credit_change = 0`
  - 用于把“返佣余额提现成功”展示为用户可追溯事件，而不是灵石变更事件

`extra_info` 至少建议包含：

- `reference_type`
- `reference_id`
- `amount_usdt`
- `idempotency_key`
- `source`

补充约束：

- 若沿用当前会自开 session / 自提交的 `LogService`，则 `user_logs` 只能在主事务提交成功后以 best-effort 方式补写
- 不允许把当前自提交 `LogService` 直接塞进返佣主资产事务中，作为“必须一起提交”的一环
- 若未来要把 `user_logs` 也纳入同事务，则必须先提供接受调用方 `AsyncSession` 的事务内审计原语，再统一迁移

---

## 5. 二期 A：返佣兑换灵石

### 5.1 目标

允许 inviter 使用返佣余额兑换站内 `credits`。

这是二期最适合先上的子阶段，因为：

- 不涉及外部支付渠道
- 成功与失败完全可在本地事务内收敛
- 余额扣减和灵石增加可以同事务完成

### 5.2 推荐业务流

首版建议：

- **只支持固定兑换档位，不开放任意自定义 `amount_usdt`**
- 原因很简单：当前 `users.credits`、`user_logs.credit_change`、`membership_plans.reward_credits` 都是整数语义，若一开始就开放任意金额兑换，必须同步定死量化规则、最小步长与舍入协议，否则幂等返回、展示文案与审计都会出现分叉

若未来要开放自定义金额，必须额外同时写死：

- `requested_amount_usdt` 的最小精度
- `settled_amount_usdt` 的量化精度
- `credits_granted` 的整数化规则
- `rounding_mode`（如 `ROUND_DOWN` / `ROUND_HALF_UP`）

在上述规则未拍板前，二期 A 正文默认都按“固定档位兑换”描述。

推荐业务流：

1. 用户提交兑换请求，输入目标兑换档位
2. 后端开启**同一个主事务**，先以 `user_id` 锁定同一用户串行化入口（默认 `users FOR UPDATE`）
3. 在持有该锁的同一事务里，对 `affiliate_redeems.idempotency_key` 做数据库级 claim；若命中重复键，则返回既有业务单或既有成功结果
4. 在单事务内：
   - 在锁内实时重算 `ledger_balance_usdt / available_balance_usdt`
   - 创建或补完兑换业务记录，并在该事务内落定业务状态
   - 校验当前 `available_balance_usdt`
   - 写一笔 `affiliate_transactions` 的 `OUT/SUCCESS`
   - 通过统一的“事务内 credits 变更原语”给用户增加 `credits`
   - 记录兑换业务日志 / 审计信息
5. 提交成功后删返佣缓存
6. 返回最新余额与 credits

补充要求：

- 若用“先插业务表、冲突即读取既有行”完成幂等 claim，也必须发生在拿到 `users FOR UPDATE` 之后
- “增加 `credits`”不能复用当前会自己开新 session 并提交的通用灵石接口
- 必须先提供**接受调用方 `AsyncSession` 的事务内 credits 变更原语**
- `users.credits` 写路径收敛是二期 A 的**阻塞前置条件**，不是优化项
- 用户日志若继续沿用现有独立提交模式，应只视为审计附属；主资产闭环以“兑换单 + 账本 + `users.credits` 同事务成功”为准
- 若首版采用固定档位，`amount_usdt` 必须直接来自档位配置快照，而不是运行时临时计算值
- `credits_granted` 必须是整数，并作为结算事实持久化，不能只在返回 DTO 时临时换算

### 5.3 数据建模建议

建议新增表：`affiliate_redeems`

建议字段：

- `id`
- `user_id`：**内部用户 ID（FK -> users.id / internal_user_id）**，不是 Telegram `user.id`
- `redeem_type`：`CREDITS`
- `requested_amount_usdt`：用户请求金额；首版固定档位时可与 `amount_usdt` 相同
- `amount_usdt`：最终结算并写主账本的金额
- `credits_granted`：**整数**
- `exchange_rate_snapshot`
- `rounding_mode`：首版固定档位可写死为 `FIXED_TIER`
- `status`：首版建议只落 `SUCCESS`；校验失败或系统异常统一整单回滚，不持久化“失败占坑单”
- `idempotency_key`
- `details`
- `created_at`

建议约束：

- `UNIQUE(idempotency_key)`：保护同一兑换请求不重复创建业务单

补充约定：

- 首版不建议把“失败重试协议”与“失败单审计”一起做复杂：若主事务失败，则兑换单与幂等 claim 一并回滚，让同一请求可以安全重试
- 若未来确实要持久化 `FAILED` 终态，则必须同时补充：同一 `idempotency_key` 命中失败时是返回旧失败、还是要求客户端更换新 key 后重试；在该协议明确前，不要先落 `FAILED`
- 若未来开放自定义金额，仍不允许直接把 `amount_usdt * 汇率` 的小数结果原样塞进 `credits`；必须先按已固定的 `rounding_mode` 量化为整数 `credits_granted`

### 5.4 账本写法

建议记账：

- `transaction_type = 'CREDITS_REDEEM'`
- `direction = 'OUT'`
- `status = 'SUCCESS'`
- `reference_type = 'AFFILIATE_REDEEM'`
- `reference_id = str(redeem.id)`
- `idempotency_key = affiliate:redeem:credits:{redeem.id}`

### 5.5 实施约束

除第 4 节全局原则外，二期 A 还必须满足：

- 兑换比例必须有明确快照，不能只依赖动态配置
- 首版兑换协议必须明确为“固定档位 -> 整数 `credits_granted`”，不要一边落整数字段、一边开放任意金额自由换算
- 幂等保护落在 `affiliate_redeems.idempotency_key` 的数据库唯一约束上，且 claim 必须留在主事务内
- 写 `OUT/SUCCESS` 与增加 `credits` 必须同事务
- 任何异常回滚后，不允许出现“余额扣了但 credits 没加”
- 不要直接调用当前会自提交的通用 `QuotaManager / LogService` 作为主资产事务的一部分
- 若需要补写 `user_logs`，也必须遵守 `4.5`：主事务成功后再 best-effort 补写，不能反向影响主资产提交

---

## 6. 二期 B：返佣兑换身份 / 月卡权益

### 6.1 目标

允许 inviter 使用返佣余额兑换身份、月卡天数或指定会员套餐。

### 6.2 为什么放在灵石兑换之后

因为它虽然仍属站内闭环，但会复用和影响现有充值逻辑里的：

- 身份优先级
- 到期时间折算
- 升级 / 降级处理
- 灵石赠送与权益边界

如果直接和提现一起做，复杂度会明显拉高。

### 6.3 推荐业务流

1. 用户选择可兑换权益
2. 后端根据配置算出所需 `amount_usdt`
3. 开启主事务并先按 `user_id` 获取 `users FOR UPDATE`
4. 在持锁事务内对业务请求幂等键做数据库级 claim；若命中重复键，返回既有业务单或既有成功结果
5. 在单事务内：
   - 在锁内实时重算 `available_balance_usdt`
   - 校验 `available_balance_usdt`
   - 创建权益兑换记录
   - 写 `affiliate_transactions` 的 `OUT/SUCCESS`
   - 调用统一的 membership settlement 核心入口更新用户身份 / 到期时间 / 结算附带信息
6. 提交成功后删缓存

### 6.4 数据建模建议

建议与灵石兑换共用 `affiliate_redeems`，或者单独建 `affiliate_membership_redeems`。

若共用 `affiliate_redeems`，增加：

- `redeem_type`：`CREDITS` / `MEMBERSHIP`
- `target_plan_id`
- `target_identity`
- `duration_days`
- `applied_membership_snapshot`

### 6.5 账本写法

建议记账：

- `transaction_type = 'MEMBERSHIP_REDEEM'`
- `direction = 'OUT'`
- `status = 'SUCCESS'`
- `reference_type = 'AFFILIATE_REDEEM'`
- `reference_id = str(redeem.id)`
- `idempotency_key = affiliate:redeem:membership:{redeem.id}`

### 6.6 风险点

- 身份折算逻辑必须和支付购买逻辑保持一致
- 若权益兑换成功后再单独异步写账，会破坏闭环
- 必须明确“返佣兑换身份”是否赠送 credits；建议默认**不赠送**，避免变相套利
- 当前代码里的身份折算逻辑仍分散在多条支付链路里，二期 B 开发前应先以 `src/core/billing_core.py` 为收敛落点，但**不要**只把现有逻辑硬塞进 `calculate_identity_conversion()` 这个双返回值 helper
- 更可落地的做法是：在 `billing_core` 新增或升级为统一的 membership settlement 原语，输出至少包含：
  - `final_identity`
  - `identity_expire_at`
  - `converted_days`
  - `is_downgrade`
  - `is_pure_credit`
  - `granted_credits`（若该套餐语义确实会送灵石）
- 收敛顺序必须是：先审计并对齐现有 RMB / TON / Stars 三条链路的真实语义，再把三条支付链路迁移到同一 settlement 原语，最后才让返佣兑换身份复用这套实现
- 收敛时要特别补齐“纯灵石套餐 / `duration_days == 0` 不改变 `current_identity` 与 `identity_expire_at`”的语义，避免统一过程中把现有特例回归掉
- 若短期无法一次性迁移完三条支付链路，则二期 B 不应先上线；不要让返佣兑换身份先吃一套“新规则”，现金购买仍停留在旧分支

---

## 7. 二期 C：提现申请 / 审核 / 打款

### 7.1 目标

允许 inviter 把返佣余额提现到外部账户，同时满足：

- 申请时冻结余额
- 审核前不真实出账
- 审核拒绝时释放冻结
- 打款成功后才写账本真实 `OUT/SUCCESS`

### 7.2 强约束

二期提现必须遵守以下红线：

- **禁止**做成 `WITHDRAW_APPLY / OUT / PENDING`
- **禁止**在申请阶段就向账本写“假出账”
- **禁止**审核拒绝后用“补一笔 IN”去掩盖坏模型

提现必须单独建模。

### 7.3 推荐模型

建议新增表：`affiliate_withdrawals`

建议字段：

- `id`
- `user_id`：**内部用户 ID（FK -> users.id / internal_user_id）**，不是 Telegram `user.id`
- `amount_usdt`
- `fee_usdt`
- `net_amount_usdt`
- `currency`
- `payout_channel`
- `payout_account_snapshot`
- `status`
- `reviewer_id`
- `reviewed_at`
- `paid_at`
- `paid_reference`
- `payout_request_id`
- `reject_reason`
- `cancel_reason`
- `idempotency_key_apply`
- `idempotency_key_payout`
- `last_payout_error`
- `last_payout_failed_at`
- `payout_retry_count`
- `created_at`
- `updated_at`

建议约束：

- `UNIQUE(idempotency_key_apply)`：保护同一提现申请请求不重复创建
- `UNIQUE(idempotency_key_payout)`：保护同一提现单成功打款回写不重复结算
- `UNIQUE(payout_request_id)`（允许 `NULL`）：保护同一提现单对外打款请求使用稳定的外部幂等请求号
- `UNIQUE(paid_reference)`（允许 `NULL`）：保护同一外部回单号不会被两个提现单重复认领

建议状态：

- `APPLIED`
- `APPROVED`
- `PAYING`
- `PAY_FAILED`
- `PAID`
- `REJECTED`
- `CANCELED`

状态语义必须额外写死：

- `PAYING`：已生成并持久化 `payout_request_id`，且已进入“等待外部结果确认”阶段；此时仍计入冻结
- `PAY_FAILED`：渠道已明确返回失败，或人工核验确认本次 `payout_request_id` 对应的打款动作未成功；此时默认**继续计入冻结**
- `PAID`：外部成功且已完成返佣主账本 `OUT/SUCCESS` 落账

字段口径必须提前定死：

- `amount_usdt`：用户返佣主余额实际扣减的毛额
- `fee_usdt`：提现手续费
- `net_amount_usdt = amount_usdt - fee_usdt`：外部实际打款净额

推荐口径：

- 冻结按 `amount_usdt` 计算
- 打款成功时账本 `OUT/SUCCESS.amount_usdt` 也按 `amount_usdt` 记录
- `fee_usdt / net_amount_usdt` 只作为提现业务表与运营审计口径，不替代主账本扣减金额

禁止：

- 冻结冻结毛额，但账本只记净额，导致手续费游离在主账本之外

### 7.4 冻结余额模型

推荐规则：

- `APPLIED / APPROVED / PAYING / PAY_FAILED` 这几个状态的 `amount_usdt` 计入 `frozen_balance_usdt`
- `PAID / REJECTED / CANCELED` 不再计入冻结

因此：

- 申请成功后，`ledger_balance_usdt` 不变
- 但 `available_balance_usdt` 会下降，因为被冻结金额被扣除了
- 真正的账本 `OUT/SUCCESS` 只在 `PAID` 时写入
- `PAY_FAILED` 不自动释放冻结；应由后台在同一状态机下选择“修正后重试打款”或“驳回/取消并释放冻结”

### 7.5 推荐业务流

#### 7.5.1 申请提现

1. 用户提交提现金额与收款信息
2. 开启主事务并先按 `user_id` 获取 `users FOR UPDATE`
3. 在持锁事务内对 `affiliate_withdrawals.idempotency_key_apply` 做数据库级 claim；若命中重复键，返回既有提现单或既有成功结果
4. 在锁内实时重算 `ledger_balance_usdt / frozen_balance_usdt / available_balance_usdt`
5. 校验 `available_balance_usdt`
6. 创建 `affiliate_withdrawals` 记录，状态置为 `APPLIED`
7. 不写账本 `OUT`
8. 提交成功后删缓存

#### 7.5.2 审核通过

1. 后台审核通过时，先按 `withdrawal.user_id` 获取 `users FOR UPDATE`，再对目标 `affiliate_withdrawals` 行 `FOR UPDATE`
2. 校验当前状态只允许 `APPLIED -> APPROVED`
3. 更新状态为 `APPROVED`
4. 不写账本
5. 冻结继续生效
6. 提交成功后删缓存

#### 7.5.3 打款成功

1. **发起外部打款前**，先按 `withdrawal.user_id` 获取 `users FOR UPDATE`，再对目标 `affiliate_withdrawals` 行 `FOR UPDATE`
2. 在同一事务内完成：
   - 校验当前状态只允许 `APPROVED -> PAYING`
   - 生成并 claim 稳定的 `payout_request_id`（外部请求幂等键）
   - 将状态更新为 `PAYING`
   - 提交事务
3. 使用该 `payout_request_id` 调用外部打款渠道；若渠道支持幂等请求号，必须原样透传；若是人工打款，也必须先把该请求号落库后再导出/执行，禁止“未持久化请求号就直接打款”
4. 若外部调用超时或结果未知：
   - 优先用同一个 `payout_request_id` 查询渠道结果或做幂等重试
   - **禁止**在未判定前一次请求最终结果前，为同一 `withdrawal` 重新生成第二个 `payout_request_id`
5. 外部确认成功后，在事务内：
   - 继续按 `users FOR UPDATE -> affiliate_withdrawals FOR UPDATE` 的顺序进入
   - 校验当前状态只允许 `PAYING -> PAID`，避免跳状态或重复回写
   - 校验 `payout_request_id` 与本次外部成功结果匹配
   - 校验并占用 `idempotency_key_payout`
   - 写入并校验全局唯一的 `paid_reference`
   - 状态改为 `PAID`
   - 写一笔 `affiliate_transactions` 的 `OUT/SUCCESS`
   - 该笔账本 `amount_usdt` 记录 `withdrawal.amount_usdt`（毛额），`fee_usdt / net_amount_usdt` 保留在提现业务表或 details 中
6. 提交成功后删缓存

补充说明：

- `idempotency_key_payout` 只负责保护“提现成功结算回写 / 账本落账”不重复
- `payout_request_id` 才负责保护“对外打款动作本身”不重复
- 没有 `payout_request_id` 的方案，最多只能防重复记账，**不能**防重复打款；因此该字段与流程属于提现链路的必选项，不是可选优化

#### 7.5.4 打款明确失败

1. 当渠道返回明确失败，或人工核验确认本次 `payout_request_id` 未打款成功时，先按 `users FOR UPDATE -> affiliate_withdrawals FOR UPDATE` 进入事务
2. 校验当前状态只允许 `PAYING -> PAY_FAILED`
3. 记录：
   - `last_payout_error`
   - `last_payout_failed_at`
   - `payout_retry_count = payout_retry_count + 1`
4. 不写账本 `OUT`
5. 不释放冻结；冻结继续保持，直到后续：
   - 基于**同一提现单**重新进入 `PAYING` 并再次发起外部打款
   - 或被后台驳回 / 取消后释放冻结
6. 若要再次打款，必须先明确本次重试是否复用原 `payout_request_id`：
   - 渠道明确声明“失败且未受理”，可允许生成新的 `payout_request_id`
   - 渠道结果不可信、状态未知或可能已受理时，必须继续围绕原 `payout_request_id` 查询与对账，**禁止**贸然生成第二个请求号

补充约束：

- `PAY_FAILED` 的存在是为了区分“结果未知的 `PAYING`”与“结果已确认失败但仍冻结待处置”的场景
- 不允许把渠道明确失败直接回写成 `APPROVED`，否则会丢失一次真实打款尝试的审计事实
- 若后续决定采用“失败即回退到 `APPROVED`”模型，则必须整体替换本 RFC 中的冻结口径、重试规则与审计字段，不能只改一个状态名

#### 7.5.5 审核拒绝 / 用户取消

1. 无论是后台审核拒绝还是用户取消，均先按 `withdrawal.user_id` 获取 `users FOR UPDATE`，再对目标 `affiliate_withdrawals` 行 `FOR UPDATE`
2. 校验允许的状态迁移后，更新 `affiliate_withdrawals.status`
3. 不写账本 `OUT`
4. 冻结自然释放
5. 提交成功后删缓存

### 7.6 提现账本写法

提现成功打款时建议记账：

- `transaction_type = 'WITHDRAWAL_PAYOUT'`
- `direction = 'OUT'`
- `status = 'SUCCESS'`
- `reference_type = 'AFFILIATE_WITHDRAWAL'`
- `reference_id = str(withdrawal.id)`
- `idempotency_key = affiliate:withdrawal:payout:{withdrawal.id}`

### 7.7 后台与风控要求

提现至少需要：

- 最低提现门槛
- 单笔上限 / 单日上限
- 账户信息快照
- 操作人审计日志
- 审核备注
- 稳定的外部打款请求号（`payout_request_id`）
- 打款流水号
- 重复打款防重机制（`payout_request_id` + `idempotency_key_payout` + `paid_reference` 唯一约束）

---

## 8. 统计口径在二期需要怎样调整

### 8.1 用户侧余额口径

二期之后建议返回以下字段：

- `commission_usdt`（兼容字段，过渡期 alias）
- `total_commission_usdt`
- `ledger_balance_usdt`
- `frozen_balance_usdt`
- `available_balance_usdt`
- `spent_commission_usdt`

建议定义：

- `commission_usdt = total_commission_usdt`（仅作为兼容 alias，供旧 Web / Bot 消费；新代码不要再把它当“当前余额”）
- `total_commission_usdt = SUM(orders.commission_usdt)`
- `ledger_balance_usdt = SUM(IN,SUCCESS) - SUM(OUT,SUCCESS)`
- `frozen_balance_usdt = SUM(active withdrawals amount)`
- `available_balance_usdt = ledger_balance_usdt - frozen_balance_usdt`
- `spent_commission_usdt = SUM(OUT,SUCCESS)`（仅在二期 A 单独上线、尚未引入提现 `OUT/SUCCESS` 时可继续沿用“已消费返佣”语义）

字段命名在二期要额外收敛：

- 一旦二期 C 提现成功也开始写 `OUT/SUCCESS`，`spent_commission_usdt` 就不再是严格意义上的“已消费返佣”
- 因此必须在二期实现前二选一并写死：
  - **方案 A（更推荐）**：把 `spent_commission_usdt` 重命名为 `total_out_balance_usdt` 或 `used_balance_usdt`，明确其语义是“所有成功出账总额”
  - **方案 B（更细粒度）**：拆成 `redeemed_commission_usdt`（站内兑换）与 `withdrawn_commission_usdt`（提现成功）两个字段
- 若短期为了兼容保留 `spent_commission_usdt`，也必须在 schema / 注释 / 前端文案中明确它在二期 C 后表示“累计成功出账”，不能继续只按“已消费未提现”理解

### 8.2 用户侧与后台统计必须同步迁移

本节的核心要求只有一句话：**不能只改用户侧 `query_invitation_recharge_stats()`，必须与后台 `query_referral_rewards()`、前端消费端和缓存层一起迁移。**

当前现状：

- 后端用户侧 schema 已经暴露 `commission_usdt / total_commission_usdt / spent_commission_usdt / available_balance_usdt`
- 但 Web 用户中心、Bot 文案与部分前端类型仍主要消费旧字段
- Dashboard / Admin 侧仍主要走 `query_referral_rewards()` 的历史聚合路径，尚未与用户侧对齐字段语义
- 当前 `commission_usdt` 仍被多处直接消费，因此二期不能直接删除该字段，必须保留兼容迁移窗口

至少要点名以下现有消费端，避免实施时漏改：

- Web 用户侧 `frontend/src/stores/auth.ts` 的 `InvitationRechargeStats` 类型目前只声明 `commission_usdt`
- Bot 文案 `src/handlers/message_handler.py` 当前仍只展示“预估分成 `commission_usdt`”
- Dashboard 前端 `dashboard/frontend/src/components/ReferralTable.vue` 仍以 `commission_usdt` 作为主展示字段，顶部汇总还在本地用 JS `number` 继续累加

迁移要求：

- 过渡期保留 `commission_usdt`，并显式令其等于 `total_commission_usdt`
- 所有新增展示与新前端代码统一优先使用 `total_commission_usdt / ledger_balance_usdt / frozen_balance_usdt / available_balance_usdt`
- 删除 `commission_usdt` 之前，必须先完成接口契约检查与消费端 grep，确认仓内无直接依赖

后端改造要求：

- `query_invitation_recharge_stats()` 在二期提现后新增 `ledger_balance_usdt / frozen_balance_usdt`，并把 `available_balance_usdt` 改为 `ledger_net - frozen`
- 聚合链路全程使用 `Decimal`，只在最终出参前做 2 位格式化
- `query_referral_rewards()` 明确区分“历史累计返佣业绩”和“当前可用余额”
- 若 Dashboard 榜单继续按历史推广业绩排序，则应继续基于 `orders.commission_usdt`，但字段命名要显式改为 `total_commission_usdt` 或 `historical_commission_usdt`
- 若 Dashboard 展示当前可消费 / 可提现余额，则必须额外返回 `ledger_balance_usdt / frozen_balance_usdt / available_balance_usdt`
- 当前 `query_referral_rewards()` 修复的是 `commission_usdt` 聚合路径的 Decimal 累加，不是整条函数已全量 Decimal 化；`total_rmb / total_ton / total_usdt` 仍需继续收敛

固定迁移 checklist：

- 后端 schema / service：`InvitationRechargeStats`、`query_invitation_recharge_stats()`、`query_referral_rewards()`
- 用户侧消费端：`frontend/src/stores/auth.ts`、相关 Profile / 账户页展示组件
- Bot 消费端：`src/handlers/message_handler.py` 的邀请充值展示文案
- Dashboard 消费端：`dashboard/backend/routers/referrals.py`、`dashboard/frontend/src/components/ReferralTable.vue`
- 缓存与测试：`permission_service` 缓存 payload、前后端字段断言、真实 PostgreSQL 集成测试

---

## 9. 建议新增的服务与接口

### 9.1 核心服务

建议新增：

- `src/services/affiliate_redeem_service.py`
- `src/services/affiliate_withdrawal_service.py`
- `src/services/affiliate_admin_service.py`

建议职责：

- `affiliate_redeem_service`：处理兑换灵石 / 权益
- `affiliate_withdrawal_service`：处理提现申请、冻结、打款落账
- `affiliate_admin_service`：后台审核、批量状态流转、审计导出

补充前置改造：

- 在 `affiliate_redeem_service` 正式开发前，先落地一个可复用的事务内 credits 变更原语，明确由调用方传入 `AsyncSession`
- 在接入该原语前，先完成全项目 `users.credits` 写路径审计，至少覆盖 RMB / TON / Stars 发货、任务扣费、签到、邀请奖励等入口
- 在 `affiliate_withdrawal_service` / `affiliate_admin_service` 实现前，先把“后台状态流转也共享 `users FOR UPDATE`”收敛成统一 helper 或固定代码模板，避免不同入口各写各的锁顺序
- 在二期 B 实现前，先提供统一的 membership settlement 原语，再让 RMB / TON / Stars 和 affiliate redeem 共同复用
- 新增业务表与 API 时，所有对外参数若出现 TG 用户号，必须先在入口层转换为 `internal_user_id`，核心 service 与持久化层统一只接受 `users.id`

### 9.2 路由层

建议新增或扩展：

- 用户侧 API：
  - 查询可提现余额
  - 创建兑换单
  - 创建提现申请
  - 查询提现记录
- 管理后台 API：
  - 提现列表
  - 审核通过 / 拒绝
  - 标记打款成功 / 失败

### 9.3 Bot 侧

若 Bot 也开放操作，需要明确：

- 兑换与提现是否都支持 Bot 端
- 若支持，先只开放查询与申请，不要在 Bot 端做复杂审核动作

---

## 10. 推荐实施顺序

### 10.1 二期 A：返佣兑换灵石

1. 先审计全项目 `users.credits` 写路径，并收敛统一的事务内 credits 变更原语
2. 固定 affiliate 用户主动操作的锁顺序：`users FOR UPDATE -> 业务幂等 claim -> 余额重算 -> 业务单落定 -> 账本写入`
3. 设计 `affiliate_redeems` 表，并把业务幂等 claim 明确落在主事务内
4. 新增兑换 service
5. 打通用户 API
6. 写 `OUT/SUCCESS` 账本闭环
7. 补单测与事务回归测试
8. 上线后先灰度给少量用户

### 10.2 二期 B：返佣兑换身份

1. 先以 `src/core/billing_core.py` 为落点，审计 RMB / TON / Stars 当前真实身份结算语义
2. 提供统一的 membership settlement 原语，而不是只改一个双返回值 helper 名称
3. 先让 RMB / TON / Stars 三条支付链路迁移到这套统一原语
4. 再复用或扩展 `affiliate_redeems`
5. 接入会员权益更新逻辑
6. 回归测试身份折算与文案附带信息
7. 补文案与前端展示
8. 小流量灰度

### 10.3 二期 C：提现闭环

1. 新建 `affiliate_withdrawals` 表
2. 固定后台与用户侧共用的锁顺序：`users FOR UPDATE -> affiliate_withdrawals FOR UPDATE -> 状态检查/幂等 -> 状态更新或账本写入`
3. 接入冻结余额统计
4. 完成用户申请接口
5. 完成后台审核接口
6. 完成打款成功后的账本 `OUT/SUCCESS`
7. 补审核 / 打款 / 拒绝 / 取消 / 重试全链路测试
8. 最后再灰度上线

推荐不要把三段一起上。

---

## 11. 实施前置条件 Checklist

以下事项属于**开工前必须完成或明确结论**的前置条件。未完成前，不应进入对应子阶段开发。

### 11.1 全局前置项

- [ ] 已完成 `users.credits` 写路径审计，覆盖 RMB / TON / Stars 发货、任务扣费、签到、邀请奖励等入口
- [ ] 已明确各资产链路当前真实锁顺序与事务边界，并标注哪些链路仍未收敛到二期目标锁序
- [ ] 已确认 affiliate 二期继续使用 `users FOR UPDATE` 作为用户级串行化锁，不引入与现有链路并存的第二套用户级锁模型
- [ ] 已确认所有 affiliate 新业务表与核心 service 统一使用 `internal_user_id` / `users.id`，入口层负责完成 Telegram ID 到内部 ID 的转换
- [ ] 已明确 `commission_usdt` 的兼容迁移策略，不会在消费端未迁移完成前直接删除 legacy alias
- [ ] 已确定测试策略包含真实 PostgreSQL 集成测试，而不是只做 fake-session 单测

### 11.2 二期 A 前置项

- [ ] 已提供接受调用方 `AsyncSession` 的事务内 credits 变更原语
- [ ] 已确认返佣兑换灵石的汇率来源、快照字段与配置更新策略
- [ ] 已明确二期 A 首版只支持固定兑换档位，或已同步拍板任意金额兑换的量化规则、最小步长与 `rounding_mode`
- [ ] 已确认 `affiliate_redeems` 的幂等键规则、状态模型与失败回滚策略
- [ ] 已确认兑换链路不会直接调用会自提交的 `QuotaManager / LogService`
- [ ] 已确认 `user_logs` 在 affiliate redeem / withdrawal 场景下的写入策略、`operation_type` 命名与 best-effort 语义
- [ ] 已准备兑换 API、缓存失效与账本 `OUT/SUCCESS` 的联调方案

### 11.3 二期 B 前置项

- [ ] 已审计 RMB / TON / Stars 当前真实身份结算语义，确认无遗漏分支
- [ ] 已设计统一的 membership settlement 原语，输出字段覆盖 `final_identity / identity_expire_at / converted_days / is_downgrade / is_pure_credit / granted_credits`
- [ ] 已确认纯灵石套餐 / `duration_days == 0` 的现有语义会被完整保留
- [ ] 已决定返佣兑换身份是否允许赠送 credits，避免与现金购买形成套利差异
- [ ] 已明确返佣兑换身份只能在现金购买链路迁移到统一 settlement 原语之后上线

### 11.4 二期 C 前置项

- [ ] 已确认提现状态模型、状态迁移图与冻结口径
- [ ] 已确认 `amount_usdt / fee_usdt / net_amount_usdt` 的业务语义，尤其是账本只记毛额
- [ ] 已确认 `payout_request_id / idempotency_key_payout / paid_reference` 三层防重职责与唯一约束
- [ ] 已确认渠道明确失败时采用 `PAY_FAILED` 持续冻结模型，并明确失败后的重试、驳回、取消口径
- [ ] 已确认支持的提现渠道、最低门槛、手续费、审核 SLA 与是否允许用户取消未审核提现
- [ ] 已确认后台审核、打款、拒绝、取消动作与用户申请 / 兑换共享同一把 `users FOR UPDATE` 锁

---

## 12. 里程碑 / DoD

本节定义各子阶段的完成定义（Definition of Done）。只有满足对应 DoD，才应视为该阶段达到可灰度或可上线状态。

### 12.1 二期 A DoD：返佣兑换灵石

满足以下条件时，二期 A 才算完成：

- [ ] `affiliate_redeems` 表、兑换 service、用户 API 已落地
- [ ] 兑换请求已具备数据库级业务幂等，重复请求返回既有结果，不重复扣账
- [ ] `affiliate_transactions` 已落 `CREDITS_REDEEM / OUT / SUCCESS`
- [ ] `users.credits` 增加与账本出账已实现同事务提交
- [ ] 兑换链路已使用事务内 credits 原语，不再复用自提交接口
- [ ] 二期 A 首版兑换协议已固定为“档位 -> 整数 `credits_granted`”，不存在任意金额下的未定义量化行为
- [ ] 若启用 `user_logs` 展示，已按 `affiliate_redeem_credits` 约定正确补写，且日志失败不会反向污染主资产事务
- [ ] 并发兑换在真实 PostgreSQL 下验证无双花
- [ ] 缓存失效、接口断言、回归测试全部通过
- [ ] 已完成小流量灰度，未发现余额、账本、credits 三者不一致

### 12.2 二期 B DoD：返佣兑换身份 / 月卡权益

满足以下条件时，二期 B 才算完成：

- [ ] 统一 membership settlement 原语已落地，并被 RMB / TON / Stars 真实支付链路复用
- [ ] 返佣兑换身份链路已复用同一 settlement 原语，不存在“返佣走新规则、现金走旧规则”的双轨行为
- [ ] `affiliate_transactions` 已落 `MEMBERSHIP_REDEEM / OUT / SUCCESS`
- [ ] 身份、到期时间、折算天数、纯灵石套餐语义在回归测试中全部与预期一致
- [ ] 是否赠送 credits 的规则已固化到实现与文案，而不是停留在口头约定
- [ ] 用户展示文案、后台查看字段与审计输出已覆盖 settlement 附带信息
- [ ] 真实 PostgreSQL 集成测试与支付链路回归测试全部通过
- [ ] 已完成小流量灰度，未出现身份错配、折算回归或账本缺失

### 12.3 二期 C DoD：提现闭环

满足以下条件时，二期 C 才算完成：

- [ ] `affiliate_withdrawals` 表、用户申请接口、后台审核接口、打款回写入口已落地
- [ ] 冻结余额模型已接入用户侧统计，`ledger_balance_usdt / frozen_balance_usdt / available_balance_usdt` 语义正确
- [ ] 申请阶段不写假出账，`OUT / SUCCESS` 仅在 `PAID` 时落账
- [ ] `payout_request_id / idempotency_key_payout / paid_reference` 三层防重全部生效
- [ ] 打款成功后主账本扣减金额严格等于 `withdrawal.amount_usdt`，而不是 `net_amount_usdt`
- [ ] 审核拒绝 / 用户取消会自然释放冻结，不通过“补一笔 IN”修模型
- [ ] `PAYING / PAY_FAILED / PAID` 语义已通过真实链路验证，不存在“明确失败却永远卡在 `PAYING`”的状态黑洞
- [ ] 若启用 `user_logs` 展示，`affiliate_withdrawal_paid` 已正确补写，且不会反向影响主资产提交
- [ ] 并发申请、申请与兑换并发、重复打款、超时重试等场景已在真实 PostgreSQL 下验证通过
- [ ] 验收 SQL、后台列表、用户查询接口与运营审计口径一致
- [ ] 已完成灰度上线，未出现冻结穿透、重复打款或账实不符

---

## 13. 二期必须补的测试

### 13.1 兑换灵石测试

至少覆盖：

1. 可用余额足够时成功兑换，账本写一笔 `OUT/SUCCESS`
2. 同一兑换请求 `idempotency_key` 重复提交时，不重复创建业务单也不重复扣账
3. 账本写入失败时，用户 `credits` 不增加
4. 用户 `credits` 更新失败时，账本不落 `OUT`
5. 固定档位兑换能稳定落出整数 `credits_granted`，不存在未定义的舍入结果
6. 若未来开放自定义金额，`requested_amount_usdt / amount_usdt / credits_granted / rounding_mode` 的量化协议在重复请求与重试下保持稳定
7. 缓存仅在事务成功后失效
8. 两个并发兑换请求竞争同一余额时，不会双花
9. 兑换链路确实遵守 `users FOR UPDATE -> 业务幂等 claim` 的既定锁顺序，不引入反向锁序
10. 若启用 `user_logs`，其补写失败不会影响“兑换单 + 账本 + `users.credits`”主事务成功

### 13.2 兑换身份测试

至少覆盖：

1. 兑换成功后身份升级正确
2. 兑换续期时到期时间叠加正确
3. 同一兑换请求 `idempotency_key` 重复提交时，不重复创建业务单也不重复扣账
4. 兑换失败不会扣余额
5. 与直接充值购买的身份折算逻辑保持一致
6. 与 RMB / TON / Stars 购买在同样输入下落到完全一致的身份 / 到期时间结果
7. 纯灵石套餐 / `duration_days == 0` 语义在统一核心入口后仍不改变身份与到期时间
8. 统一 settlement 原语能返回文案与审计需要的附带信息（如 `converted_days / is_downgrade / is_pure_credit`）

### 13.3 提现测试

至少覆盖：

1. 提现申请成功后冻结增加、账本净额不变
2. 审核拒绝后冻结释放、账本不变
3. 打款成功后冻结释放且写 `OUT/SUCCESS`
4. 渠道明确失败时，状态正确进入 `PAY_FAILED`，且冻结不被错误释放
5. `PAY_FAILED` 后重试、驳回、取消三条路径都遵守既定状态迁移，不会出现卡死单
6. 同一提现单重复打款不重复出账
7. 打款失败重试不会多次写 `OUT`
8. 已冻结金额不会再次被其他兑换 / 提现占用
9. 两个并发申请 / 申请与兑换并发竞争同一余额时，不会出现双花
10. 提现账本出账金额与 `withdrawal.amount_usdt` 一致，而不是 `net_amount_usdt`
11. 同一申请 `idempotency_key_apply` 重复提交时，不重复创建提现单
12. 同一 `withdrawal` 在外部打款超时、重试或人工补触发时，始终复用同一个 `payout_request_id`，不会对外生成第二次打款请求
13. 渠道明确声明“失败且未受理”时，若允许新建 `payout_request_id`，其条件与审计字段完整可追溯
14. 同一外部 `paid_reference` 不能被两个提现单重复认领
15. 后台审核 / 打款 / 拒绝 / 取消 与用户申请 / 兑换并发时，共享 `users FOR UPDATE` 后不会出现冻结穿透或双花
16. 若启用 `user_logs`，`affiliate_withdrawal_paid` 的补写失败不会影响 `PAID + OUT/SUCCESS` 主事务

### 13.4 统计测试

至少覆盖：

1. `ledger_balance_usdt` 与账本净额一致
2. `frozen_balance_usdt` 与活跃提现单聚合一致
3. `available_balance_usdt = ledger_balance - frozen`
4. `spent_commission_usdt` 与账本 `OUT/SUCCESS` 一致
5. 整个聚合过程中无中间 round 漂移
6. 用户侧余额接口与 Dashboard / Admin 侧字段语义不混淆：累计返佣与当前可用余额分字段返回
7. `query_referral_rewards()` 不再逐 invitee 先 round 再汇总

### 13.5 测试分层要求

二期不要只补 fake-session 单测，还必须补真实 PostgreSQL 集成测试。

至少以下场景应在真实 PostgreSQL 下验证：

1. 并发兑换灵石的双花防护
2. 并发提现申请的冻结竞争
3. 兑换与提现并发竞争同一余额
4. 同一提现单重复打款的数据库级幂等
5. 打款失败重试不重复出账
6. `paid_reference` 唯一约束在并发或重试下仍能稳定防重

---

## 14. 二期上线前验收 SQL（建议草案）

说明：

- `14.1` 仅依赖当前已存在的 `affiliate_transactions`，在二期兑换类出账落地后即可执行
- `14.2 ~ 14.4` 依赖 `affiliate_withdrawals`；当前仓库尚未落地该表，这三段 SQL 属于**提现模型上线后的验收草案**，不要在现阶段直接拿现网/当前开发库执行

### 14.1 兑换类出账核对

```sql
SELECT
  transaction_type,
  COUNT(*) AS cnt,
  COALESCE(SUM(amount_usdt), 0) AS amount_sum
FROM affiliate_transactions
WHERE direction = 'OUT'
  AND status = 'SUCCESS'
GROUP BY transaction_type
ORDER BY amount_sum DESC;
```

用途：

- 看兑换灵石 / 兑换身份 / 提现打款是否按类型落账

### 14.2 活跃提现冻结核对

```sql
SELECT
  user_id,
  COUNT(*) AS withdrawal_count,
  COALESCE(SUM(amount_usdt), 0) AS frozen_sum
FROM affiliate_withdrawals
WHERE status IN ('APPLIED', 'APPROVED', 'PAYING')
GROUP BY user_id
ORDER BY frozen_sum DESC
LIMIT 50;
```

用途：

- 核对冻结余额口径

### 14.3 提现打款与账本出账对应关系

```sql
SELECT
  w.id,
  w.user_id,
  w.amount_usdt AS withdrawal_amount_usdt,
  w.fee_usdt,
  w.net_amount_usdt,
  at.amount_usdt,
  at.idempotency_key
FROM affiliate_withdrawals w
LEFT JOIN affiliate_transactions at
  ON at.reference_type = 'AFFILIATE_WITHDRAWAL'
 AND at.reference_id = w.id::text
 AND at.transaction_type = 'WITHDRAWAL_PAYOUT'
 AND at.direction = 'OUT'
 AND at.status = 'SUCCESS'
WHERE w.status = 'PAID'
ORDER BY w.id DESC
LIMIT 100;
```

用途：

- 检查“已打款成功”的提现单是否都落了真实出账
- 并核对主账本扣减金额是否等于 `withdrawal.amount_usdt`（毛额），而不是 `net_amount_usdt`

### 14.4 外部回单号唯一性核对

```sql
SELECT
  paid_reference,
  COUNT(*) AS cnt
FROM affiliate_withdrawals
WHERE paid_reference IS NOT NULL
GROUP BY paid_reference
HAVING COUNT(*) > 1
ORDER BY cnt DESC, paid_reference;
```

用途：

- 检查是否存在同一外部回单号被多个提现单重复认领的脏数据

---

## 15. 待拍板的产品决策

以下技术前提已确认并已写入正文，不再作为待确认项：

- 二期用户级串行化锁默认统一沿用 `users FOR UPDATE`
- inviter 主动消费 / 提现共享 `users FOR UPDATE`；invitee 支付触发的返佣入账不额外抢 inviter 锁，消费侧以“持锁重算余额”为唯一准则
- `src/core/billing_core.py` 可以修改，并作为身份折算统一收敛落点
- 身份结算必须收敛为可复用的 membership settlement 原语，而不是只改一个双返回值 helper 名称
- 后台提现状态流转必须与用户申请 / 兑换共享 `users FOR UPDATE`
- 外部回单号 `paid_reference` 需要唯一约束
- 业务表 `idempotency_key` claim 必须在主事务内完成，不允许事务外先占坑
- 对用户主动发起且影响返佣余额的操作，claim 必须遵循 `users FOR UPDATE -> claim` 的统一锁顺序
- 返佣兑换开发前必须先完成事务内 credits 变更原语与 `users.credits` 写路径审计

在正式开做前，仍需拍板以下产品规则：

1. 返佣兑换灵石的汇率是否固定，还是配置化
2. 返佣兑换身份是否允许和现金购买同样的套餐
3. 兑换身份是否赠送灵石
4. 二期 A 首版是否只开放固定兑换档位；若否，自定义金额兑换的最小步长与 `rounding_mode` 是什么
5. 提现最低门槛、手续费、审核 SLA
6. 提现支持哪些渠道
7. 用户是否允许取消未审核提现
8. 提现渠道明确失败时，是否统一采用 `PAY_FAILED` 持续冻结、待后台处置的模型
9. 是否需要后台批量审核与批量打款导出

这些规则不需要等开发写到一半再补。

---

## 16. 结论

基于当前线上状态，推荐按以下路径推进：

1. 一期保持稳定，不再继续大改补账逻辑
2. 二期先做**返佣兑换灵石**，尽快打通第一条真实 `OUT/SUCCESS` 消费链
3. 再做**返佣兑换身份**，复用现有会员规则
4. 最后做**提现闭环**，通过 `affiliate_withdrawals` 单独建模冻结与审核

一句话总结：一期已经解决“返佣入账”，二期要解决“返佣如何安全地花出去”。
