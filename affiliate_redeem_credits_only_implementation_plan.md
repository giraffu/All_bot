# RFC：Affiliate 二期灵石兑换实施方案（仅返佣兑换灵石）

本文档基于当前仓库真实代码与已上线返佣账本能力，给出一份更小范围、可直接推进的二期实施方案。

本版只实现一件事：

1. 返佣兑换灵石

以下能力本期不做，只在文末保留后续扩展边界：

- 返佣兑换身份 / 月卡权益
- 返佣提现

---

## 1. 简要背景

当前 affiliate 一期已经解决了“返佣如何安全入账”的问题，但还没有完成“返佣如何安全花出去”的闭环。

结合现有代码，当前线上已经具备以下事实基础：

- `orders.commission_usdt` 已作为订单级返佣固化字段存在
- `affiliate_transactions` 已具备账本字段：`direction`、`reference_type`、`reference_id`、`idempotency_key`
- RMB / TON / Stars 三条支付成功链路已经在成功事务内写入返佣入账
- 历史补账脚本已可按 `orders.status = SUCCESS && commission_usdt > 0` 的口径回放历史入账
- 用户侧返佣统计已经部分基于账本聚合，而不是只读单一历史字段

与本文档直接相关的现有实现包括：

- 返佣计算与入账：`src/core/affiliate_core.py`
- RMB 发货：`src/services/payment_fulfillment_service.py`
- TON 发货：`src/services/payment_validator.py`
- Stars 发货：`src/handlers/payment_handler.py`
- 用户侧返佣统计：`src/services/referral_stats_service.py`

一句话概括当前状态：

- 一期已经解决“返佣入账”
- 本文档只解决“返佣如何先兑换成站内灵石”

---

## 2. 当前已上线内容

本节只保留与“返佣兑换灵石”直接相关的基线，不重复更大范围 RFC 的全部背景。

### 2.1 已上线能力

- `affiliate_transactions` 已可作为返佣主账本使用
- 返佣入账幂等已切到数据库级，当前核心键为 `affiliate:commission:order:{order.id}`
- `query_invitation_recharge_stats()` 已返回：
  - `commission_usdt`
  - `total_commission_usdt`
  - `spent_commission_usdt`
  - `available_balance_usdt`
- 历史补账脚本 `scripts/backfill_affiliate_transactions.py` 已可对已固化返佣订单补写入账流水

### 2.2 当前真实余额语义

现阶段系统里最稳定的返佣语义是：

- `orders.commission_usdt`：历史累计返佣事实
- `affiliate_transactions`：返佣余额主账本
- `available_balance_usdt`：当前主要按账本净额理解

因此，二期最适合先做的第一条消费链路就是：

- 返佣兑换灵石

原因：

- 这是纯站内闭环
- 不涉及外部支付渠道
- 不涉及会员规则收敛
- 可以完整做成“业务单 + 账本 + `users.credits`”同事务提交

---

## 3. 本期范围与非范围

### 3.1 本期纳入范围

本期只做：

1. 返佣兑换灵石
2. 站内消费型 `OUT / SUCCESS` 账本闭环
3. 用户侧余额与消费统计的最小迁移

### 3.2 本期不纳入范围

本期先不做：

- 返佣兑换身份 / 月卡权益
- 提现申请单
- 冻结余额模型
- 审核流转
- 外部打款
- 打款失败补偿
- 提现风控后台

原因：

- 灵石兑换是本地事务闭环，复杂度最低
- 身份兑换会依赖会员规则统一收敛
- 提现会引入冻结、审核、外部幂等和失败补偿，复杂度显著更高

---

## 4. 核心设计原则

### 4.1 账本只记录已生效事实

延续一期原则：

- `affiliate_transactions` 只承载已经生效的资产事实
- 本期只有在兑换成功后才写 `OUT / SUCCESS`
- 不在账本中引入“处理中”“待确认”之类中间态

因此，本期账本语义非常直接：

- 灵石兑换成功：写一笔 `OUT / SUCCESS`

### 4.2 用户主动消费必须串行化

所有会消耗返佣余额的用户主动操作，都必须在同一用户级串行化事务内执行。

当前默认继续沿用：

- `users FOR UPDATE`

但这里要明确一条前置约束：

- 不是只“审计” `users.credits` 写路径就够了
- 在返佣兑换灵石正式上线前，至少要把会并发写 `users.credits` 的高风险路径收敛到统一事务原语或统一锁序

原因来自当前真实代码：

- `QuotaManager.deduct_credits()` 仍是无锁先查后改
- 邀请奖励、频道奖励等路径仍在分散写 `users.credits`
- Dashboard 后台仍存在直接绝对赋值或无锁加灵石路径
- 模板审核奖励等后台运营路径也会直接写 `users.credits`
- RMB / TON / Stars 发货链路也各自内联了灵石更新逻辑

其中上线前至少要纳入收敛清单的真实高风险路径包括：

- `src/quota.py`
  - `QuotaManager.deduct_credits()`
  - `QuotaManager.process_channel_reward()`
- `dashboard/backend/routers/users.py`
  - `update_user_credits()`
  - `admin_gift_plan()`
- `dashboard/backend/routers/templates.py`
  - `approve_contribution()`

这里要特别强调一条现实约束：

- 当前风险不只是“有些路径没加锁”
- 更大的风险是“带锁增减”和“无锁绝对赋值”混跑
- 如果不先收敛这些写路径，即使返佣兑换主链路本身实现正确，最终也可能出现：
  - `affiliate_redeems` 已成功
  - `affiliate_transactions` 已成功出账
  - `users.credits` 却被别的后台路径覆盖回旧值或错误值

因此本期固定顺序为：

1. `users FOR UPDATE`
2. 业务幂等 claim
3. 余额重算
4. 业务单创建或补完
5. 账本 `OUT / SUCCESS`
6. `users.credits` 更新
7. 提交事务

禁止：

- 在事务外先读返佣余额，再在事务内直接使用旧结果
- 在拿到 `users FOR UPDATE` 之前先 claim 幂等键
- 在返佣兑换主事务里调用会自己开 session 并提交的老接口

### 4.3 幂等必须分业务层和账本层

本期灵石兑换必须有两层幂等：

- 业务请求幂等：防止重复创建兑换单
- 账本落账幂等：防止同一兑换单重复写 `OUT / SUCCESS`

建议规则：

- 业务表使用 `UNIQUE(user_id, idempotency_key)`，避免不同用户误撞同一个客户端 key
- 账本表继续使用全局唯一 `idempotency_key`

推荐账本键：

- `affiliate:redeem:credits:{redeem.id}`

### 4.3.1 幂等返回协议必须先定义

本期除了“不能重复扣账”，还必须明确“重复请求返回什么”。

建议首版直接定义为：

- 同一 `user_id + idempotency_key` 且请求参数一致时：
  - 不重复创建兑换单
  - 不重复写账本
  - 不重复增加 `users.credits`
  - 接口返回第一次成功的兑换结果
- 同一 `user_id + idempotency_key` 但请求参数不一致时：
  - 返回显式冲突错误
  - 不允许把同一个幂等键复用于不同兑换档位

建议返回字段至少固定为：

- `redeem_id`
- `redeem_type`
- `amount_usdt`
- `credits_granted`
- `status`
- `idempotency_key`

这样可以避免客户端因为超时重试时，虽然数据库未重复扣账，但接口层返回不稳定。

### 4.4 `user_logs` 仍只是附属审计

本期必须继续维持以下边界：

- `affiliate_transactions` 是返佣主账本
- `user_logs` 只是用户可见审计流水

当前 `LogService.log_action()` 会自行创建 session 并独立提交，因此不能把它直接塞进返佣主资产事务里，作为必须一起成功的部分。

因此本期约定：

- 主资产闭环以“兑换单 + 账本 + `users.credits`”同事务成功为准
- `user_logs` 如需要展示，只能在主事务提交成功后 best-effort 补写

---

## 5. 本期数据模型建议

本期建议新增业务表：

- `affiliate_redeems`

建议字段：

- `id`
- `user_id`
- `redeem_type`：首版固定为 `CREDITS`
- `redeem_option_key`：首版固定档位 key，便于审计与幂等比对
- `requested_amount_usdt`
- `amount_usdt`
- `credits_granted`
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
- 余额不足、参数非法、系统异常都应直接整单回滚
- 不建议首版为了失败留痕引入复杂失败状态机

---

## 6. 返佣兑换灵石实施方案

### 6.1 目标

允许 inviter 使用返佣余额兑换站内 `credits`。

这是当前最适合先落地的子阶段，因为：

- 不涉及外部支付
- 不涉及会员规则迁移
- 可以完整落成“业务单 + 账本 + `users.credits`”同事务闭环

### 6.2 首版协议

首版建议只支持固定兑换档位，不开放任意金额兑换。

原因：

- 当前 `users.credits` 是整数语义
- `user_logs.credit_change` 也是整数语义
- 如果一开始开放任意金额兑换，就必须同时拍板：
  - 金额最小步长
  - 汇率快照
  - 整数化规则
  - 舍入模式
  - 幂等返回协议

因此本期默认：

- 前端只传兑换档位
- 后端从档位配置中得到 `amount_usdt`
- `credits_granted` 作为整数结算事实持久化

### 6.2.1 档位配置来源

为了控制首版复杂度，建议：

- 首版兑换档位使用后端静态配置，不做数据库后台动态编辑
- 每个档位至少固化：
  - `redeem_option_key`
  - `amount_usdt`
  - `credits_granted`
  - `exchange_rate_snapshot`
  - `rounding_mode`
- 配置变更只影响新请求，不回写历史兑换单

原因：

- 本期核心目标是把资产事务做对，而不是先引入一套配置后台
- 档位若支持随时热更新，会让历史单解释、审计与幂等返回协议复杂化

### 6.3 推荐业务流

1. 用户提交兑换档位与 `idempotency_key`
2. 后端开启主事务
3. `users FOR UPDATE`
4. 在同一事务内对 `affiliate_redeems(user_id, idempotency_key)` 做数据库级 claim
5. 在锁内实时重算返佣余额
6. 校验余额是否足够
7. 创建兑换单，或命中已有成功单后直接返回既有结果
8. 写 `affiliate_transactions` 一笔 `CREDITS_REDEEM / OUT / SUCCESS`
9. 用统一的事务内 credits 原语增加 `users.credits`
10. 提交事务
11. 提交成功后失效返佣缓存
12. 如需要，best-effort 补写 `user_logs`

补充约束：

- 若同一 `idempotency_key` 命中已有成功兑换单，应直接返回该单结果，而不是再次尝试扣账
- 若命中相同幂等键但请求档位不一致，应返回冲突错误
- 不允许把“余额不足”也做成可复用的失败态缓存；首版失败直接回滚，由客户端重新发起新幂等键请求

### 6.4 账本写法

建议：

- `transaction_type = 'CREDITS_REDEEM'`
- `direction = 'OUT'`
- `status = 'SUCCESS'`
- `reference_type = 'AFFILIATE_REDEEM'`
- `reference_id = str(redeem.id)`
- `idempotency_key = affiliate:redeem:credits:{redeem.id}`

### 6.5 前置条件

本期开发前，必须先满足：

- 已提供接受调用方 `AsyncSession` 的事务内 credits 变更原语
- 已收敛以下高风险 `users.credits` 写路径，不能只停留在审计层：
  - `src/quota.py::QuotaManager.deduct_credits()`
  - `src/quota.py::QuotaManager.process_channel_reward()`
  - `dashboard/backend/routers/users.py::update_user_credits()`
  - `dashboard/backend/routers/users.py::admin_gift_plan()`
  - `dashboard/backend/routers/templates.py::approve_contribution()`
- 已确定兑换档位、汇率来源、快照字段和配置更新策略
- 已明确 `affiliate_redeems` 的幂等键规则和回滚协议
- 已明确重复请求命中成功单时的返回协议
- 已确认不会在主事务中直接调用自提交的 `QuotaManager / LogService`

未满足以上条件前，本期功能最多只能进入开发联调或预发布验证，不能直接灰度上线。

### 6.6 DoD

- `affiliate_redeems` 表与兑换 service 已落地
- 重复请求命中相同 `idempotency_key` 时不重复扣账
- 重复请求命中相同 `idempotency_key` 时可稳定返回第一次成功结果
- `affiliate_transactions` 已正确落 `CREDITS_REDEEM / OUT / SUCCESS`
- `users.credits` 增加与账本出账同事务提交
- 并发兑换在真实 PostgreSQL 下验证无双花
- 缓存失效与接口断言已补齐

---

## 7. 统计与接口的最小调整

本期虽然只做灵石兑换，但消费后的字段语义仍需要先收敛好。

### 7.1 用户侧字段建议

本期建议继续保留兼容字段，同时明确语义：

- `commission_usdt`
- `total_commission_usdt`
- `spent_commission_usdt`
- `available_balance_usdt`

过渡期建议定义：

- `commission_usdt = total_commission_usdt`
- `total_commission_usdt = 历史累计返佣`
- `spent_commission_usdt = 当前所有成功出账总额`
- `available_balance_usdt = 当前账本净额`

由于本期只有灵石兑换，`spent_commission_usdt` 仍可近似理解为“已消费返佣”。

同时要明确一条展示规则：

- 新展示默认优先使用 `available_balance_usdt` 表达“当前可兑换余额”
- `total_commission_usdt` 只表达“历史累计返佣”
- `commission_usdt` 仅作为兼容别名保留
- 新文案不应再把 `commission_usdt` 单独展示成“预估分成”或“当前可用余额”

### 7.2 现有消费端迁移要求

至少要检查以下消费端：

- `frontend/src/stores/auth.ts`
- `frontend/src/views/Profile.vue`
- `src/handlers/message_handler.py`
- `src/services/referral_stats_service.py`
- `dashboard/backend/routers/referrals.py`
- `dashboard/frontend/src/components/ReferralTable.vue`

要求：

- 新展示优先使用 `total_commission_usdt` 和 `available_balance_usdt`
- 兼容期内不直接删除 `commission_usdt`
- 聚合链路尽量保持 `Decimal` 到最终格式化前再转展示值

### 7.3 Dashboard 语义边界

当前 `query_referral_rewards()` 更接近“历史邀请返佣表现榜”，而不是“当前可兑换余额面板”。

因此本期需要明确：

- 如果 Dashboard 只是看排行与历史表现，可以继续保留现有榜单接口，但要修正文案语义
- 如果 Dashboard 要展示“当前可用返佣余额”或“已消费返佣”，则必须新增基于 `affiliate_transactions` 的聚合，不能直接复用现有榜单聚合
- 不应把历史累计返佣、当前账本净额、当前已消费返佣混在同一列语义中展示

---

## 8. 推荐实施顺序

建议按以下顺序推进：

1. P0：收敛 `users.credits` 事务内变更原语，并消灭无锁绝对赋值高风险路径
2. P1：完成返佣兑换灵石闭环与幂等返回协议
3. P2：补用户侧字段、缓存与展示迁移
4. P3：完成真实 PostgreSQL 并发回归测试
5. P4：小流量灰度上线

这里要实事求是地说明：

- 本期虽然业务目标只做“返佣兑换灵石”
- 但工程范围并不只是新增一张表和一个接口
- 它实际包含一轮 `users.credits` 资产写路径治理

---

## 9. 本期必须补的测试

### 9.1 灵石兑换

至少覆盖：

1. 余额足够时兑换成功
2. 重复 `idempotency_key` 不重复扣账
3. 重复 `idempotency_key` 返回第一次成功结果
4. 相同 `idempotency_key` 但不同兑换档位返回冲突
5. 账本写入失败时 `users.credits` 不增加
6. `users.credits` 更新失败时账本不落 `OUT`
7. 并发兑换不双花
8. 缓存仅在事务成功后失效
9. `user_logs` 补写失败不影响主资产事务成功

### 9.2 测试分层要求

本期不能只写 fake-session 单测，还必须补真实 PostgreSQL 集成测试。

至少应覆盖：

1. 并发灵石兑换
2. 同一用户下多个兑换请求竞争同一返佣余额
3. 业务幂等与账本幂等同时生效
4. 幂等成功返回与参数冲突返回都符合协议

---

## 10. 后续扩展预留

本期虽然不做身份兑换和提现，但文档层面需要先保留清晰边界，避免后续把灵石兑换模型推翻重来。

### 10.1 身份兑换扩展预留

后续若要支持返佣兑换身份 / 月卡权益，必须继续遵守：

- 先在 `src/core/billing_core.py` 收敛统一的 membership settlement 原语
- 先让 RMB / TON / Stars 复用同一原语
- 再让 affiliate redeem 身份兑换复用这套实现
- 必须保留纯灵石套餐 / `duration_days == 0` 的既有语义
- 必须明确返佣兑换身份是否赠送 credits，避免套利

也就是说，身份兑换不能先于现金购买链路的会员规则收敛单独上线。

### 10.2 提现扩展预留

后续若要支持返佣提现，必须继续遵守：

- 提现申请单必须独立建模，不把冻结中伪装成账本 `OUT`
- `affiliate_transactions` 仍只记录真实生效的出账事实
- 冻结余额应由独立业务表状态体现，而不是靠假流水模拟
- 对外打款必须区分：
  - 外部打款请求幂等
  - 成功回写幂等
  - 外部回单号唯一认领

也就是说，当前这份文档的目标不是回避后续扩展，而是先把最小可闭环的灵石兑换模型做对，再让身份兑换和提现可以在同一账本语义上自然扩展。

---

## 11. 结论

基于当前代码状态，最稳妥的路径是：

1. 先完成 `users.credits` 高风险写路径治理
2. 再完成返佣兑换灵石
3. 身份兑换作为下一阶段扩展，前提是先完成 membership settlement 统一收敛
4. 提现继续保留扩展位，不在本期实现

一句话总结：

- 本期先解决“返佣如何稳定兑换成灵石”，但前提是先把 `users.credits` 的高风险并发写路径收敛掉
- 后续再解决“返佣如何兑换身份”和“返佣如何提现”
