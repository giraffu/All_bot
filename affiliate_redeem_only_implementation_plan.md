# RFC：Affiliate 二期站内兑换实施方案（仅灵石兑换与身份兑换）

本文档基于当前仓库的真实代码与已上线返佣账本能力，给出一份更聚焦的二期实施方案。

本版只覆盖两类站内闭环能力：

1. 返佣兑换灵石
2. 返佣兑换身份 / 月卡权益

提现链路本期不做，只在文末保留后续扩展约束，避免本阶段把冻结、审核、外部打款和站内消费混在一起实现。

---

## 1. 简要背景

当前 affiliate 一期已经解决了“返佣如何安全入账”的问题，但还没有完成“返佣如何安全花出去”的闭环。

结合现有代码，当前线上已具备以下事实基础：

- `orders.commission_usdt` 已作为订单级返佣固化字段存在
- `affiliate_transactions` 已具备账本字段：`direction`、`reference_type`、`reference_id`、`idempotency_key`
- RMB / TON / Stars 三条支付成功链路都已经在成功事务内写入返佣入账
- 历史补账脚本已经按 `orders.status = SUCCESS && commission_usdt > 0` 的口径完成回放
- 用户侧余额统计已经不是简单读 `commission_usdt`，而是部分基于账本聚合

与本文档直接相关的现有实现包括：

- 返佣计算与入账：`src/core/affiliate_core.py`
- RMB 发货：`src/services/payment_fulfillment_service.py`
- TON 发货：`src/services/payment_validator.py`
- Stars 发货：`src/handlers/payment_handler.py`
- 用户侧返佣统计：`src/services/referral_stats_service.py`

一句话概括当前状态：

- 一期已经解决“返佣入账”
- 本文档解决“返佣先在站内安全消费”

---

## 2. 当前已上线内容

本节只保留与二期站内兑换直接相关的基线，不重复完整补账 RFC。

### 2.1 已上线能力

- `affiliate_transactions` 已可作为返佣主账本使用
- 返佣入账幂等已切到数据库级，当前核心键为 `affiliate:commission:order:{order.id}`
- `query_invitation_recharge_stats()` 已同时返回：
  - `commission_usdt`
  - `total_commission_usdt`
  - `spent_commission_usdt`
  - `available_balance_usdt`
- 历史补账脚本 `scripts/backfill_affiliate_transactions.py` 已可用于对已固化返佣订单补写入账流水

### 2.2 当前真实余额语义

现阶段系统里最稳定的返佣语义是：

- `orders.commission_usdt`：历史累计返佣事实
- `affiliate_transactions`：返佣余额主账本
- `available_balance_usdt`：当前主要按账本净额理解

因此，二期最适合优先做的是站内消费型 `OUT / SUCCESS`：

- 兑换灵石
- 兑换身份 / 月卡权益

这两类能力都可以在本地数据库事务中闭环，不需要引入提现冻结和外部打款状态机。

---

## 3. 本期范围与非范围

### 3.1 本期纳入范围

本期只做：

1. 返佣兑换灵石
2. 返佣兑换身份 / 月卡权益
3. 站内消费型 `OUT / SUCCESS` 账本闭环
4. 用户侧余额与消费统计的最小迁移

### 3.2 本期不纳入范围

本期先不做：

- 提现申请单
- 冻结余额模型
- 审核流转
- 外部打款
- 打款失败补偿
- 提现风控后台

原因很明确：

- 站内兑换是单事务本地闭环
- 提现会引入冻结、审核、外部渠道幂等和失败补偿，复杂度高一个量级
- 当前仓库更适合先把站内消费语义跑通，再为提现扩展预留清晰边界

---

## 4. 核心设计原则

### 4.1 账本只记录已生效事实

延续一期原则：

- `affiliate_transactions` 只承载已经生效的资产事实
- 本期所有站内消费成功后才写 `OUT / SUCCESS`
- 不在账本中引入“待确认”“处理中”之类的中间态

因此本期的账本含义非常简单：

- 灵石兑换成功：写一笔 `OUT / SUCCESS`
- 身份兑换成功：写一笔 `OUT / SUCCESS`

### 4.2 用户主动消费必须串行化

本期所有会消耗返佣余额的用户主动操作，都必须在同一用户级串行化事务内执行。

当前默认继续沿用：

- `users FOR UPDATE`

但这里要明确一条比旧 RFC 更硬的前置约束：

- 不是只“审计” `users.credits` 写路径就够了
- 在返佣兑换正式上线前，至少要把会并发写 `users.credits` 的核心路径收敛到统一事务原语或统一锁序

原因来自真实代码现状：

- `QuotaManager.deduct_credits()` 仍是无锁先查后改
- 邀请奖励和频道奖励也存在分散写 `users.credits` 的路径
- RMB / TON / Stars 发货链路各自内联了灵石和身份结算逻辑
- 后台手工改灵石、后台赠送套餐、模板审核奖励也都仍可直接写 `users.credits`

这里不能只写“审计后择机收敛”，而要在开工前明确最小收敛清单。

至少需要纳入同一轮治理的真实写路径包括：

- 任务扣费 / 退款：`src/core/billing_core.py` -> `QuotaManager.deduct_credits()`
- 签到奖励：`src/quota.py::checkin()`
- 邀请首邀奖励：`src/quota.py::process_referral()`
- 频道奖励：`src/quota.py::process_channel_reward()`
- RMB 发货：`src/services/payment_fulfillment_service.py`
- TON 发货：`src/services/payment_validator.py`
- Stars 发货：`src/handlers/payment_handler.py`
- 后台手工改灵石：`dashboard/backend/routers/users.py::update_user_credits()`
- 后台赠送套餐：`dashboard/backend/routers/users.py::admin_gift_plan()`
- 模板审核奖励：`dashboard/backend/routers/templates.py::approve_contribution()`

本期最低要求不是把这些路径全部重写成同一个函数，而是至少满足下面之一：

- 统一改造成“调用方传入 `AsyncSession` 的事务内资产原语”
- 或明确统一到同一锁序与同一更新协议

若以上清单仍有任何高频写路径保持“无锁先查后改”或“自开 session 自提交”，则不应认为二期兑换前置条件已满足

因此本期必须把以下顺序固定下来：

1. `users FOR UPDATE`
2. 业务幂等 claim
3. 余额重算
4. 业务单创建或补完
5. 账本 `OUT / SUCCESS`
6. `users.credits` 或会员权益更新
7. 提交事务

禁止：

- 在事务外先读取返佣余额，再在事务内直接使用旧结果
- 在拿到 `users FOR UPDATE` 之前先 claim 幂等键
- 在返佣兑换主事务里调用会自己开 session 并提交的老接口

### 4.3 幂等必须分业务层和账本层

本期所有站内兑换都必须有两层幂等：

- 业务请求幂等：防止重复创建兑换单
- 账本落账幂等：防止同一兑换单重复写 `OUT / SUCCESS`

建议规则：

- 业务表使用 `UNIQUE(user_id, idempotency_key)`，避免不同用户误撞同一个客户端 key
- 账本表继续使用全局唯一 `idempotency_key`

推荐账本键：

- `affiliate:redeem:credits:{redeem.id}`
- `affiliate:redeem:membership:{redeem.id}`

### 4.4 `user_logs` 仍只是附属审计

本期必须延续一个重要边界：

- `affiliate_transactions` 是返佣主账本
- `user_logs` 只是用户可见审计流水

当前代码里的 `LogService.log_action()` 会自行创建 session 并独立提交，因此不能把它直接塞进返佣主资产事务，作为必须一起提交的一部分。

因此本期约定：

- 主资产闭环以“兑换单 + 账本 + 用户资产更新”同事务成功为准
- `user_logs` 如需展示，只能在主事务提交成功后 best-effort 补写

### 4.5 身份兑换必须复用统一 settlement 原语

当前 RMB / TON / Stars 的身份结算逻辑仍然分散在不同支付链路中，不能直接让 affiliate redeem 先吃一套新规则。

因此本期 B 的硬约束是：

- 先在 `src/core/billing_core.py` 设计并落地新的 membership settlement 原语
- 再让 RMB / TON / Stars 迁移到该原语
- 最后才让返佣身份兑换复用这一套实现

这里要特别避免一个误区：

- 目标不是“直接复用当前 `calculate_identity_conversion()` 就算完成收敛”
- 目标是定义一套能完整覆盖现网购买语义的新 primitive

原因是当前现网还存在一些该函数并未完整表达的约束，例如：

- 纯灵石套餐 / `duration_days == 0` 时不改变身份与到期时间
- 会员套餐是否附带赠送 `credits`
- 升级 / 降级 / 同套餐续期时的折算说明与回传结果
- 返佣兑换身份首版是否默认不赠送 `credits`

因此新的 settlement primitive 至少要显式输入或返回：

- 当前身份、当前到期时间
- 目标身份、`duration_days`
- `reward_credits`
- 是否纯灵石套餐
- 最终身份、最终到期时间
- 折算天数 / 折算原因
- 是否赠送 `credits`

若这个前置收敛做不完，则本期只上线灵石兑换，不强推身份兑换。

---

## 5. 本期数据模型建议

本期建议新增业务表：

- `affiliate_redeems`

建议字段：

- `id`
- `user_id`
- `redeem_type`：`CREDITS` / `MEMBERSHIP`
- `requested_amount_usdt`
- `amount_usdt`
- `credits_granted`
- `target_plan_id`
- `target_identity`
- `duration_days`
- `exchange_rate_snapshot`
- `rounding_mode`
- `status`
- `idempotency_key`
- `details`
- `created_at`
- `updated_at`

建议约束：

- `UNIQUE(user_id, idempotency_key)`：业务请求幂等

首版状态建议尽量简单：

- `SUCCESS`

原因：

- 本期只做站内闭环
- 余额不足、参数非法、系统异常等都应直接整单回滚
- 不建议首版为了“失败留痕”引入复杂失败状态机

---

## 6. 二期 A：返佣兑换灵石

### 6.1 目标

允许 inviter 使用返佣余额兑换站内 `credits`。

这是本期最优先落地的子阶段，因为：

- 不涉及外部支付
- 不涉及会员规则迁移
- 可以完整落成“业务单 + 账本 + `users.credits`”同事务闭环

### 6.2 首版协议

首版建议只支持固定兑换档位，不开放任意金额兑换。

原因：

- 当前 `users.credits` 是整数语义
- 现有 `user_logs.credit_change` 也是整数语义
- 如果一开始开放任意金额兑换，就必须先同时定义：
  - 金额最小步长
  - 汇率快照
  - 整数化规则
  - 舍入模式
  - 幂等返回格式

因此本期默认：

- 前端只传兑换档位
- 后端从档位配置中得到 `amount_usdt`
- `credits_granted` 作为整数结算事实持久化

### 6.3 推荐业务流

1. 用户提交兑换档位与 `idempotency_key`
2. 后端开启主事务
3. `users FOR UPDATE`
4. 在同一事务内对 `affiliate_redeems(user_id, idempotency_key)` 做数据库级 claim
5. 在锁内实时重算返佣余额
6. 校验余额是否足够
7. 创建或补完 `affiliate_redeems`
8. 写 `affiliate_transactions` 一笔 `CREDITS_REDEEM / OUT / SUCCESS`
9. 用统一的事务内 credits 原语增加 `users.credits`
10. 提交事务
11. 提交成功后失效返佣缓存
12. 如需要，best-effort 补写 `user_logs`

### 6.4 账本写法

建议：

- `transaction_type = 'CREDITS_REDEEM'`
- `direction = 'OUT'`
- `status = 'SUCCESS'`
- `reference_type = 'AFFILIATE_REDEEM'`
- `reference_id = str(redeem.id)`
- `idempotency_key = affiliate:redeem:credits:{redeem.id}`

### 6.5 本阶段前置条件

二期 A 开发前，必须先满足：

- 已提供接受调用方 `AsyncSession` 的事务内 credits 变更原语
- 已识别并收敛高风险 `users.credits` 写路径，不能只停留在审计层
- 已确定兑换档位、汇率来源、快照字段和配置更新策略
- 已明确 `affiliate_redeems` 的幂等键规则和回滚协议
- 已确认不会在主事务中直接调用自提交的 `QuotaManager / LogService`

### 6.6 DoD

- `affiliate_redeems` 表与兑换 service 已落地
- 重复请求命中相同 `idempotency_key` 时不重复扣账
- `affiliate_transactions` 已正确落 `CREDITS_REDEEM / OUT / SUCCESS`
- `users.credits` 增加与账本出账同事务提交
- 并发兑换在真实 PostgreSQL 下验证无双花
- 缓存失效与接口断言已补齐

---

## 7. 二期 B：返佣兑换身份 / 月卡权益

### 7.1 目标

允许 inviter 使用返佣余额兑换身份、月卡时长或指定会员套餐。

### 7.2 为什么排在灵石兑换之后

因为它会直接触碰现有支付链路的核心会员规则，包括：

- 身份优先级
- 到期时间折算
- 升级 / 降级处理
- 纯灵石套餐语义
- 是否附带赠送灵石

当前这些逻辑仍分散在 RMB / TON / Stars 三条链路中，因此不能跳过收敛，直接给 affiliate redeem 单独做一套新规则。

### 7.3 推荐业务流

1. 用户选择可兑换权益
2. 后端根据配置算出 `amount_usdt`
3. 开启主事务
4. `users FOR UPDATE`
5. 在同事务内 claim `affiliate_redeems(user_id, idempotency_key)`
6. 在锁内重算返佣余额
7. 校验余额
8. 创建或补完 `affiliate_redeems`
9. 调用统一 membership settlement 原语，得到最终身份与到期结果
10. 写一笔 `MEMBERSHIP_REDEEM / OUT / SUCCESS`
11. 更新用户身份、到期时间及必要附带信息
12. 提交事务
13. 提交成功后删缓存
14. 如需要，best-effort 补写 `user_logs`

### 7.4 账本写法

建议：

- `transaction_type = 'MEMBERSHIP_REDEEM'`
- `direction = 'OUT'`
- `status = 'SUCCESS'`
- `reference_type = 'AFFILIATE_REDEEM'`
- `reference_id = str(redeem.id)`
- `idempotency_key = affiliate:redeem:membership:{redeem.id}`

### 7.5 核心约束

- 必须先完成 `billing_core` 的统一 settlement 原语
- 必须先让 RMB / TON / Stars 复用同一原语
- 后台赠送套餐 `admin_gift_plan()` 也必须迁移到同一原语，不能长期保留独立规则
- 返佣兑换身份不能先于现金购买链路完成规则收敛
- 必须保留纯灵石套餐 / `duration_days == 0` 的既有语义
- 必须明确“返佣兑换身份是否赠送 credits”，建议首版默认不赠送，避免套利
- 不应把“当前 `calculate_identity_conversion()` 被部分场景调用”视为已经完成统一；以新 primitive 覆盖支付购买、后台赠送与返佣兑换后，才算真正收敛

### 7.6 DoD

- 统一 membership settlement 原语已落地
- RMB / TON / Stars 已复用同一原语
- `admin_gift_plan()` 已复用同一原语
- affiliate redeem 身份兑换已复用同一原语
- `affiliate_transactions` 已落 `MEMBERSHIP_REDEEM / OUT / SUCCESS`
- 身份、到期时间、折算天数语义与支付购买保持一致
- 真实 PostgreSQL 集成测试与支付链路回归通过

---

## 8. 统计与接口的最小调整

本期虽然不做提现，但仍需要把消费后的字段语义先收敛好。

### 8.1 用户侧字段建议

本期建议继续保留兼容字段，同时补充更清晰的语义：

- `commission_usdt`
- `total_commission_usdt`
- `spent_commission_usdt`
- `available_balance_usdt`

过渡期建议定义：

- `commission_usdt = total_commission_usdt`
- `total_commission_usdt = 历史累计返佣`
- `spent_commission_usdt = 当前所有成功出账总额`
- `available_balance_usdt = 当前账本净额`

因为本期只有站内兑换，`spent_commission_usdt` 仍可近似理解为“已消费返佣”。

### 8.2 用户侧余额展示迁移

至少要检查以下真实消费端：

- `frontend/src/stores/auth.ts`
- `frontend/src/views/Profile.vue`
- `src/handlers/message_handler.py`

要求：

- 新展示优先使用 `total_commission_usdt` 和 `available_balance_usdt`
- 兼容期内不直接删除 `commission_usdt`
- `frontend/src/stores/auth.ts` 需要先补齐新字段类型声明，否则前端即使拿到返回值也不会显式消费
- `frontend/src/views/Profile.vue` 不应继续只展示 `commission_usdt`，至少要区分“累计返佣”和“可用余额”
- `src/handlers/message_handler.py` 里的“预估分成”文案需要调整为更准确的累计返佣 / 可用余额口径，避免后端语义已变但文案仍停留在旧口径
- 聚合链路尽量保持 `Decimal` 到最终格式化前再转展示值

### 8.3 Dashboard 榜单与后台接口迁移

这一部分是另一条独立任务，目标不是复用用户侧 `invitation_recharge`，而是明确 Dashboard 榜单到底展示什么语义。

至少要检查：

- `dashboard/backend/routers/referrals.py`
- `src/services/referral_stats_service.py::query_referral_rewards()`
- `dashboard/frontend/src/components/ReferralTable.vue`

要求：

- 若榜单继续展示历史累计返佣，则可以继续保留 `commission_usdt`，但要在文档和 UI 上明确其语义是“累计返佣”而不是“可用余额”
- 若榜单需要展示可用余额，则后端必须单独扩展 `query_referral_rewards()`，不能误以为用户侧已有 `available_balance_usdt` 就代表 Dashboard 已完成迁移
- Dashboard 改造应与用户侧余额展示解耦推进，避免因为榜单语义未定而阻塞二期 A 的灵石兑换闭环

---

## 9. 推荐实施顺序

建议按以下顺序推进：

1. 收敛 `users.credits` 事务内变更原语
2. 完成灵石兑换闭环
3. 完成用户侧余额展示迁移
4. 收敛 `billing_core` 的 membership settlement 原语
5. 迁移 RMB / TON / Stars 与 `admin_gift_plan()` 到统一 settlement 原语
6. 完成身份兑换闭环
7. 最后再考虑提现扩展

如果第 4 到 5 步无法在短期内稳定完成，则本期只上线灵石兑换，不强推身份兑换。

---

## 10. 本期必须补的测试

### 10.1 灵石兑换

至少覆盖：

1. 余额足够时兑换成功
2. 重复 `idempotency_key` 不重复扣账
3. 账本写入失败时 `users.credits` 不增加
4. `users.credits` 更新失败时账本不落 `OUT`
5. 并发兑换不双花
6. 缓存仅在事务成功后失效

### 10.2 身份兑换

至少覆盖：

1. 兑换成功后身份升级正确
2. 同身份续期正确
3. 降级折算语义与现金购买一致
4. 纯灵石套餐语义不回归
5. 重复 `idempotency_key` 不重复扣账
6. 并发兑换不双花

### 10.3 测试分层要求

本期不能只写 fake-session 单测，还必须补真实 PostgreSQL 集成测试。

至少应覆盖：

1. 并发灵石兑换
2. 并发身份兑换
3. 同一用户下兑换请求竞争同一返佣余额
4. 业务幂等与账本幂等同时生效

---

## 11. 提现的后续扩展预留

本期虽然不做提现，但文档层面需要先保留边界，避免后续把站内兑换模型推翻重来。

后续提现扩展时，必须继续遵守：

- 提现申请单必须独立建模，不把“冻结中”伪装成账本 `OUT`
- `affiliate_transactions` 仍只记录真实生效的出账事实
- 冻结余额应由独立业务表状态体现，而不是靠假流水模拟
- 对外打款必须区分：
  - 外部打款请求幂等
  - 成功回写幂等
  - 外部回单号唯一认领

也就是说，当前这份文档的设计目标不是回避提现，而是先把站内消费模型做对，让后续提现可以在同一账本语义上自然扩展，而不是推倒重来。

---

## 12. 结论

基于当前代码状态，最稳妥的路径是：

1. 先完成返佣兑换灵石
2. 再在统一 membership settlement 原语落地后完成返佣身份兑换
3. 提现只保留扩展位，不在本期实现

一句话总结：

- 本期先解决“返佣如何在站内安全消费”
- 下期再解决“返佣如何安全提现”
