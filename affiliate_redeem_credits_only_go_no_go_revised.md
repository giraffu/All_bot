# Affiliate 二期「返佣兑换灵石」修正版 Go/No-Go 审核稿

本文档基于当前仓库真实代码状态，对 `affiliate_redeem_credits_only_implementation_plan.md` 做审校后给出一版更适合直接执行的修正版审核稿。

本稿只覆盖一件事：

1. 返佣兑换灵石

以下内容仍不纳入本期上线范围：

- 返佣兑换身份 / 月卡权益
- 返佣提现

---

## 1. 修正版审核结论

### 1.1 总体判断

- 返佣兑换灵石仍然是 affiliate 二期最适合先落地的子阶段
- 该方向与当前代码基线相容，且具备账本基础、统计基础和并发测试基础
- 但它不是“加一张表 + 加一个接口”的普通功能，而是一次最小资产链路治理

### 1.2 修正版结论

当前代码基线下，本项目可以开发并联调“返佣兑换灵石”，但只有在以下硬门槛满足后，才可对真实用户灰度开放：

1. 返佣兑换主链实现为单事务闭环
2. `users.credits` 主业务写路径最小治理完成
3. 退款链和主业务扣费链不再依赖旧的负数扣费复用语义
4. 展示层明确区分“历史累计返佣”和“当前可兑换余额”
5. 兑换金额精度、展示精度和比较精度口径固定
6. 真实 PostgreSQL 并发回归通过
7. 高风险后台入口已被列为受控例外并具备最小操作隔离

### 1.3 审核口径

本稿固定使用以下结论：

- `Go`：允许灰度
- `No-Go`：只允许开发联调、测试环境验证或预发布验证

若任一 `No-Go` 条件命中，本期不得对真实用户开放。

---

## 2. 当前代码基线

### 2.1 已具备的正向基础

结合当前真实代码，当前已具备以下事实基础：

- `orders.commission_usdt` 已作为订单级返佣固化字段
- `affiliate_transactions` 已具备 `direction`、`reference_type`、`reference_id`、`idempotency_key`
- RMB / TON / Stars 成功发货链路可在成功事务内写入 affiliate 入账
- 用户侧返佣统计已经同时返回累计返佣、已消费返佣和当前净额
- 真实 PostgreSQL 并发集成测试已覆盖 affiliate 入账链和支付并发幂等主场景

相关代码基线：

- 返佣计算与入账：`src/core/affiliate_core.py`
- RMB 发货：`src/services/payment_fulfillment_service.py`
- TON 发货：`src/services/payment_validator.py`
- Stars 发货：`src/handlers/payment_handler.py`
- 用户侧返佣统计：`src/services/referral_stats_service.py`
- 用户侧 schema：`src/web_api/schemas/auth_schema.py`
- 支付并发回归：`tests/integration/test_affiliate_payment_integration.py`

### 2.2 当前真实余额语义

当前最符合代码现状的返佣语义如下：

- `commission_usdt`：历史累计返佣展示值
- `total_commission_usdt`：历史累计返佣展示值，当前与 `commission_usdt` 等值
- `spent_commission_usdt`：账本中所有成功出账总额
- `available_balance_usdt`：账本净额，即 `SUM(IN, SUCCESS) - SUM(OUT, SUCCESS)`

因此，本期最适合先做的消费型闭环仍然是：

- 返佣兑换灵石

原因：

- 纯站内事务闭环
- 不涉及外部打款
- 不涉及会员折算统一原语
- 可以完整实现为“业务单 + 账本 + `users.credits`”同事务提交

---

## 3. 修正版范围定义

### 3.1 本期纳入范围

本期纳入以下内容：

1. 返佣兑换灵石
2. 消费型 `OUT / SUCCESS` 账本闭环
3. 用户侧余额与消费统计展示迁移
4. `users.credits` 主业务写路径最小治理
5. 退款链语义收敛
6. PostgreSQL 并发回归和上线评审材料

### 3.2 本期明确不纳入范围

本期不做：

- 返佣兑换身份 / 月卡权益
- 提现申请单
- 冻结余额模型
- 审核流转
- 外部打款
- 打款失败补偿
- 提现风控后台

---

## 4. 修正版审核关注点

### 4.1 账本仍然只记录已生效事实

延续一期原则：

- `affiliate_transactions` 只记录已生效资产事实
- 本期只有兑换成功后才写 `OUT / SUCCESS`
- 不在返佣账本中为灵石兑换引入处理中、中间态或冻结态

本期账本语义固定为：

- 灵石兑换成功：写一笔 `OUT / SUCCESS`

### 4.2 主风险仍然在 `users.credits` 混写

当前真实代码中，返佣兑换最大的上线风险仍然不是“会不会多扣一笔返佣”，而是同一张 `users` 表上并存：

- 带锁增减
- 无锁先查后改
- 后台绝对赋值

如果不先做最小治理，即使返佣兑换主链本身实现正确，也仍可能出现：

1. `affiliate_redeems` 已成功
2. `affiliate_transactions` 已成功出账
3. `users.credits` 被后台入口或旧奖励路径覆盖回旧值

这会导致：

- 账本事实正确，但用户余额错误
- 对账能证明兑换成功，但用户前台余额不可信
- 上线后需要人工对账和补偿

### 4.3 包装层 TOCTOU 仍需治理，但要区分硬门槛与建议项

以下路径仍保留分步余额语义，应进入本期治理范围：

- `src/core/billing_core.py::check_and_deduct_credits()`
- `src/core/billing_core.py::refund_credits()`
- `src/quota.py::QuotaManager.deduct_credits()`
- `src/services/permission_service.py::increment_quota()`
- 退款调用点：
  - `src/services/recovery_service.py`
  - `src/services/zombie_cleaner_service.py`

需要修正的一点是：

- `src/services/permission_service.py::check_quota()` 应视为需要收敛的预检读路径
- 但它不是与余额写路径同等级的资产一致性 `No-Go`
- 它更适合作为“建议同步治理项”而不是单独卡死上线的最高硬门槛

### 4.4 展示层必须迁移，但要按真实契约迁移

当前后端返回字段已经具备：

- `commission_usdt`
- `total_commission_usdt`
- `spent_commission_usdt`
- `available_balance_usdt`

因此本期展示层问题不在于“后端字段不存在”，而在于前端和 TG 文案仍把累计返佣当主余额展示。

若后端先上线兑换，而消费端不迁移，用户看到的结果会是：

- 兑换成功
- 可用返佣减少
- 但页面主文案中的“预估分成 / 分成金额”不变

这会被理解为：

- 兑换没生效
- 余额系统不可信

### 4.5 必须新增精度口径

原审核稿缺少一个必须提前固定的口径：

- 账本金额精度
- 展示金额精度
- 兑换校验精度

当前真实代码中：

- 账本金额使用 4 位小数
- 用户展示金额通常量化为 2 位小数

因此本期必须显式固定：

1. 兑换档位配置的 `amount_usdt` 使用何种精度
2. 服务端比较余额时按何种精度比较
3. 前端显示金额时允许展示多少位小数
4. 展示值向下取整、四舍五入还是仅用于展示

若不固定该口径，将直接产生：

- 前台看似余额足够
- 服务端按更高精度比较后判定不足

---

## 5. 可上线版设计结论

### 5.1 结论一：首版仍建议固定兑换档位

首版建议固定为：

- 前端只传 `redeem_option_key`
- 后端按静态配置得到 `amount_usdt`
- `credits_granted` 作为整数结算事实持久化

首版不建议开放任意金额兑换，原因：

- `users.credits` 为整数语义
- `user_logs.credit_change` 为整数语义
- 任意金额兑换会引入最小步长、汇率快照、舍入规则和幂等返回协议复杂度

### 5.2 结论二：必须新增独立业务表

本期应新增：

- `affiliate_redeems`

建议最低字段：

- `id`
- `user_id`
- `redeem_type`
- `redeem_option_key`
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

建议最低约束：

- `UNIQUE(user_id, idempotency_key)`

首版状态建议只保留：

- `SUCCESS`

理由：

- 本期只做站内事务闭环
- 参数非法、余额不足和系统异常直接回滚即可
- 首版不需要为失败留痕引入状态机复杂度

### 5.3 结论三：幂等必须分两层

必须同时具备：

- 业务请求幂等：避免重复创建兑换单
- 账本落账幂等：避免重复写 `OUT / SUCCESS`

推荐规则：

- 业务表：`UNIQUE(user_id, idempotency_key)`
- 账本表：继续使用全局唯一 `idempotency_key`

推荐账本键：

- `affiliate:redeem:credits:{redeem.id}`

### 5.4 结论四：重复请求返回协议必须固定

接口必须定义：

- 同一 `user_id + idempotency_key` 且请求参数一致：
  - 不重复创建兑换单
  - 不重复写账本
  - 不重复增加 `users.credits`
  - 稳定返回第一次成功结果
- 同一 `user_id + idempotency_key` 但请求参数不一致：
  - 返回显式冲突错误

建议返回字段：

- `redeem_id`
- `redeem_type`
- `amount_usdt`
- `credits_granted`
- `status`
- `idempotency_key`

### 5.5 结论五：`user_logs` 在本功能中只作为附属审计

需要修正原审核稿中的一个表述：

- 当前仓库并不存在统一的“`UserLog` 永远自开 session、永远不进主事务”事实
- 真实代码状态是：`LogService.log_action()` 自开 session，而其他部分代码也存在直接在主事务中插入 `UserLog` 的写法

因此本期应明确采用以下功能级约束，而不是将其表述为全局现状：

- 返佣兑换主资产闭环只判断三件事：
  - 兑换单
  - 返佣账本出账
  - `users.credits`
- 三者同事务提交成功
- `user_logs` 作为附属审计，在主事务提交后 best-effort 补写即可

---

## 6. 可上线实现要求

### 6.1 主事务固定顺序

返佣兑换主链建议固定为以下顺序：

1. `users FOR UPDATE`
2. 业务幂等 claim
3. 锁内实时重算返佣余额
4. 创建或补完 `affiliate_redeems`
5. 写 `affiliate_transactions` 的 `OUT / SUCCESS`
6. 在同一事务内增加 `users.credits`
7. 提交事务
8. 提交成功后失效返佣缓存
9. 如需要，best-effort 补写 `user_logs`

禁止：

- 在事务外先读返佣余额，再在事务内使用旧结果
- 在拿到 `users FOR UPDATE` 之前先 claim 幂等键
- 在兑换主事务里调用自开 session 并提交的旧接口
- 在仍保留两段式包装的前提下宣称治理已完成

### 6.2 事务内统一原语要求

上线前必须提供：

- 接受调用方 `AsyncSession` 的 credits 变更原语
- 接受调用方事务的“余额检查 + 增加 / 扣减”一体化原语

上线前不得继续依赖：

- `check_credits() -> deduct_credits()`
- `deduct_credits(-cost)` 这种负数退款复用语义

### 6.3 返佣余额重算要求

返佣余额必须在锁内实时重算，不允许复用事务外缓存值。

本期账本口径固定为：

- `SUM(IN, SUCCESS) - SUM(OUT, SUCCESS)`

上线解释必须同时明确：

- 该口径保证“不双花、不错扣、不会被并发消费覆盖”
- 但它不承诺“并发支付刚入账的一笔返佣一定在本次兑换请求里可见”

这意味着：

- 用户主动发起兑换时，不会双花
- 极端并发下，刚到账返佣可能需要下一次请求才能被消费

这属于可接受的首版一致性边界。

### 6.4 精度与展示口径要求

本期必须固定如下规则：

1. 账本内部金额使用 `DECIMAL(10,4)` 语义
2. 兑换档位配置的 `amount_usdt` 使用与账本一致的 4 位小数
3. 服务端余额校验按 4 位小数比较，不按前端展示值比较
4. 用户展示可保留 2 位小数，但必须明确它只是展示值
5. 当展示值与可兑换档位存在精度差时，以服务端档位校验结果为准

如果产品侧希望彻底规避该类认知偏差，则首版可进一步限制：

- 所有兑换档位的 `amount_usdt` 均为 2 位小数

---

## 7. 修正版 Must Have 与 No-Go 条件

以下内容属于上线前必须完成的硬门槛；任一项未满足，本期只能停留在开发联调、测试环境或预发布验证阶段，不得灰度。

### 7.1 Must Have：兑换主链闭环

必须满足：

- 已新增 `affiliate_redeems`
- 已固定首版协议为“固定档位 -> 整数 `credits_granted`”
- 已落地 `UNIQUE(user_id, idempotency_key)`
- 已固定重复请求返回协议
- 已固定账本写法为：
  - `transaction_type = 'CREDITS_REDEEM'`
  - `direction = 'OUT'`
  - `status = 'SUCCESS'`
  - `reference_type = 'AFFILIATE_REDEEM'`
  - `reference_id = str(redeem.id)`
  - `idempotency_key = affiliate:redeem:credits:{redeem.id}`

未满足则：

- `No-Go`

### 7.2 Must Have：主业务 credits 写路径最小治理

以下路径属于本期必须治理范围：

- `src/core/billing_core.py`
  - `check_and_deduct_credits()`
  - `refund_credits()`
- `src/quota.py`
  - `QuotaManager.deduct_credits()`
- `src/services/permission_service.py`
  - `increment_quota()`
- 真实退款调用点：
  - `src/services/recovery_service.py`
  - `src/services/zombie_cleaner_service.py`

最低要求：

- 主业务扣费不再依赖“两段式跨 session”
- 退款不再复用旧负数扣费语义
- 调用方在已有事务时可以直接复用统一原语

需要明确：

- `check_quota()` 仍建议同步收敛
- 但其本身不是单独定义 `No-Go` 的唯一理由
- `No-Go` 的重点是写路径和退款路径，而不是单个预检入口本身

未满足则：

- `No-Go`

### 7.3 Must Have：展示语义同步迁移

上线前必须同步完成：

- Web 个人中心若展示“当前可兑换余额”，必须使用 `available_balance_usdt`
- TG 个人中心若继续展示“预估分成”，必须明确它表示历史累计返佣，而不是当前可兑换余额
- Dashboard 若继续展示历史榜单，可继续使用 `commission_usdt / total_commission_usdt`
- 但 Dashboard 不得把 `commission_usdt / total_commission_usdt` 的文案写成“当前可兑换余额”

兼容期字段语义固定为：

- `commission_usdt = 历史累计返佣展示值`
- `total_commission_usdt = 历史累计返佣展示值`
- `spent_commission_usdt = 当前所有成功出账总额`
- `available_balance_usdt = 当前账本净额`

未满足则：

- `No-Go`

### 7.4 Must Have：精度规则固定

上线前必须完成：

1. 固定兑换档位 `amount_usdt` 的配置精度
2. 固定服务端余额校验精度
3. 固定返回字段中的金额格式
4. 固定前端展示值与服务端校验值不一致时的处理口径

未满足则：

- `No-Go`

### 7.5 Must Have：真实 PostgreSQL 并发回归

不能只写 fake-session 单测，必须补真实 PostgreSQL 集成测试，至少覆盖：

1. 并发兑换不双花
2. 重复 `idempotency_key` 稳定返回首次成功结果
3. 相同 `idempotency_key` 但不同兑换档位返回冲突
4. 账本失败时 `users.credits` 不增加
5. `users.credits` 更新失败时账本不落 `OUT`
6. 缓存仅在事务成功后失效
7. 兑换与任务扣费交叉竞争
8. 兑换与 RMB / TON / Stars 发货交叉竞争

未满足则：

- `No-Go`

### 7.6 Must Have：上线评审材料完整

上线评审前必须具备：

- `users.credits` 写路径 inventory
- 已迁移 / 受控例外 / 已废弃 三类标记
- 回滚方案
- 灰度策略
- 受控例外清单

未满足则：

- `No-Go`

---

## 8. Controlled Exception 管理要求

### 8.1 允许存在，但不能伪装成已治理完成

以下路径在本期可暂不全部迁移到统一事务原语，但只能作为“受控例外”存在：

- `dashboard/backend/routers/users.py::update_user_credits()`
- `dashboard/backend/routers/users.py::admin_gift_plan()`
- `dashboard/backend/routers/templates.py::approve_contribution()`
- `src/quota.py::checkin()`
- `src/quota.py::process_referral()`
- `src/quota.py::process_channel_reward()`

这些路径不得被表述为：

- `P0 已完成治理`
- `users.credits` 已全量闭环
- `返佣兑换与所有余额入口已天然兼容`

### 8.2 可上线版最小要求

受控例外最小要求必须满足：

1. 已完成 inventory，并单独列出
2. 受控例外路径不得在兑换主事务中直接调用
3. 上线评审需单独披露其仍可能覆盖 `users.credits`
4. 后台绝对赋值入口必须具备操作限制

### 8.3 后台绝对赋值入口的审核意见

对于 `dashboard/backend/routers/users.py::update_user_credits()`，修正版审核意见仍为：

- 它不是可忽略的遗留入口
- 它是仍在线的余额绝对赋值能力
- 若继续在线，必须被认定为高风险受控后台能力

上线建议三选一：

1. 上线期临时禁用
2. 仅维护窗允许使用
3. 改为复用统一事务原语

若三者均未落实，则：

- 不建议给出 `Go`

---

## 9. 实际代码映射

### 9.1 返佣主账本与统计基线

- `src/core/affiliate_core.py`
  - `calculate_and_set_commission_for_paid_order()`
  - `record_affiliate_commission_transaction()`
  - `invalidate_invitation_recharge_cache()`
- `src/services/referral_stats_service.py`
  - `query_invitation_recharge_stats()`

当前含义：

- `commission_usdt / total_commission_usdt` 表示历史累计返佣展示值
- `spent_commission_usdt / available_balance_usdt` 来自 `affiliate_transactions` 聚合

### 9.2 必须治理的旧扣费与退款包装层

- `src/core/billing_core.py`
  - `check_and_deduct_credits()`
  - `refund_credits()`
- `src/quota.py`
  - `QuotaManager.deduct_credits()`
- `src/services/permission_service.py`
  - `increment_quota()`
- `src/services/recovery_service.py`
  - 退款恢复仍经 `increment_quota()`
- `src/services/zombie_cleaner_service.py`
  - 僵尸任务退款仍经 `increment_quota()`

审核意见：

- 若这些路径不先收敛，返佣兑换上线后仍会保留主业务 TOCTOU 与退款链旧语义风险

### 9.3 建议同步收敛但不单独定义为最高硬门槛的路径

- `src/services/permission_service.py::check_quota()`

审核意见：

- 它仍保留预检式读路径语义
- 建议在本期一起收敛
- 但不应将它与资金写路径本体混为同等级 `No-Go`

### 9.4 需要做交叉回归的支付发货主链

- `src/services/payment_fulfillment_service.py::fulfill_order()`
- `src/services/payment_validator.py::TonPaymentValidator._process_order()`
- `src/handlers/payment_handler.py::successful_payment_callback()`

审核意见：

- 这三条链路不一定要求本期全部重构成统一 helper
- 但必须参与“兑换 vs 发货加灵石”并发回归
- 不能在评审中被简化为“天然不会冲突”

### 9.5 必须同步调整的展示层

- `frontend/src/stores/auth.ts`
- `frontend/src/views/Profile.vue`
- `src/handlers/message_handler.py`
- `dashboard/backend/routers/referrals.py`
- `dashboard/frontend/src/components/ReferralTable.vue`

需要修正的一点是：

- `src/web_api/schemas/auth_schema.py` 当前已经具备 `total_commission_usdt / spent_commission_usdt / available_balance_usdt`
- 因此本期重点是消费端展示迁移，不是 schema 从零新增

---

## 10. 上线结果影响说明

若按本修正版要求完整实施，线上结果影响如下。

### 10.1 正向结果

- 用户将获得真正可用的“返佣 -> 灵石”闭环
- 返佣消费将具备业务幂等、账本幂等和可审计业务单
- `affiliate_transactions` 与 `users.credits` 将在同一主事务中一致提交
- 主业务退款链和扣费链的旧负数扣费复用语义将被收敛
- 主业务余额覆盖风险会显著下降

### 10.2 用户可见变化

用户侧最直观变化是：

- `available_balance_usdt` 会下降
- `spent_commission_usdt` 会上升
- `commission_usdt / total_commission_usdt` 不会因为兑换而下降

这意味着：

- “累计返佣”与“当前可兑换余额”会首次被明确区分
- 若展示层同步迁移，用户认知会更清晰
- 若展示层不同步迁移，用户会误判为“兑换没有生效”

### 10.3 Dashboard 影响

当前 Dashboard 更接近历史邀请返佣表现榜，而不是余额面板。

因此上线后：

- 若 Dashboard 继续展示历史榜单，`commission_usdt` 不变是预期行为
- 若 Dashboard 要展示“当前可兑换余额”，必须新增基于 `affiliate_transactions` 的聚合或复用现有余额字段

### 10.4 工程结果影响

实施后工程影响包括：

- 新增 `affiliate_redeems`
- 新增兑换 service / route / schema / 配置
- 收敛 credits 统一事务原语
- 迁移旧包装层和退款调用点
- 增补 PostgreSQL 并发测试
- 调整 Web / TG / Dashboard 展示语义
- 固定金额精度和展示精度口径

换句话说，本期工程量应按“资产链路治理型功能”估算，而不是按普通接口开发估算。

### 10.5 若门槛未满足直接上线的结果

若在以下条件未满足时强行上线：

- 旧写路径与退款链未迁移
- 展示层未迁移
- 后台绝对赋值入口未受控
- 金额精度规则未固定
- PostgreSQL 并发测试未完成

则最可能出现的结果是：

1. 账本正确，但 `users.credits` 被其他路径覆盖
2. 兑换成功，但用户前台仍看到“分成没变”
3. 前台展示看似可兑，服务端按实际精度判定不足
4. 并发边界不清，排障和补偿成本高

---

## 11. 推荐实施顺序

建议按以下顺序推进：

1. P0：盘点并收敛 `users.credits` 写路径，提供统一事务原语，并迁移旧包装层和退款链
2. P1：固定兑换档位、金额精度和返回协议
3. P2：完成返佣兑换灵石闭环、业务幂等和账本幂等
4. P3：补用户侧字段、缓存与展示迁移，修正文案语义
5. P4：完成真实 PostgreSQL 并发回归测试
6. P5：完成上线前 `Go / No-Go` 评审
7. P6：小流量灰度上线

这里必须明确：

- 本期虽然业务目标只做“返佣兑换灵石”
- 但它实际包含一轮 `users.credits` 资产写路径治理

---

## 12. 修正版 Go / No-Go 决策表

### 12.1 可判定为 Go 的条件

只有同时满足以下全部条件，才可判定为：

- `Go`

条件如下：

1. `affiliate_redeems` 与兑换主链已落地
2. 统一事务原语已落地，旧包装层最小治理完成
3. 退款调用点已切换到新原语
4. 展示层语义已迁移
5. 金额精度与展示精度规则已固定
6. 真实 PostgreSQL 并发回归通过
7. 受控例外已 inventory 并具备最小操作隔离
8. 灰度方案与回滚方案已准备完成

### 12.2 直接判定为 No-Go 的条件

任一项命中即：

- `No-Go`

条件如下：

1. 仍存在未披露的 `users.credits` 主业务写路径未收敛
2. `billing_core` 仍保留旧的主调用路径且未完成最小治理
3. `recovery_service / zombie_cleaner_service` 仍走旧退款语义
4. 真实 PostgreSQL 下尚未验证“兑换 vs 任务扣费”
5. 真实 PostgreSQL 下尚未验证“兑换 vs 支付发货加灵石”
6. 对外展示仍把 `commission_usdt / total_commission_usdt` 当“当前可兑换余额”主文案
7. 金额精度规则未固定，前台展示值与服务端校验值口径未定义
8. 兑换主事务仍直接调用自提交 session 的旧接口
9. 后台绝对赋值入口未受控，仅以“评审披露”代替隔离

需要补充说明：

- `check_quota()` 若仍未收敛，不是理想状态
- 但不建议单独把“仅剩 `check_quota()` 未迁移”作为唯一 `No-Go`
- 真正的 `No-Go` 仍应聚焦资产写路径、退款路径和并发正确性

---

## 13. 最终意见

基于当前代码状态，本修正版最终意见如下：

1. 返佣兑换灵石应继续推进
2. 但它必须按“资产链路治理型功能”推进，而不是普通业务接口
3. 只有在主链闭环、旧写路径最小治理、退款语义收敛、展示语义迁移、精度规则固定和 PostgreSQL 并发回归都完成后，才可给出 `Go`
4. 若受控例外只是“记录在案”，没有最小操作隔离，则不建议给出 `Go`

一句话总结：

- 本期可以做，也值得做
- 但要按修正版审核口径推进：先补齐资产一致性和精度口径硬门槛，再谈灰度上线
