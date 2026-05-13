# 联盟返佣后续实施方案

本文档用于承接已上线的 `affiliate_implementation_plan.md`，聚焦后续三个用户可见能力：

- 返佣兑换灵石
- 返佣兑换身份
- 返佣提现申请

本方案基于当前仓库真实代码状态整理，目标不是重复描述“首单返佣如何产生”，而是补齐“返佣如何被安全消费”的账务、接口、审核与风控闭环。

---

## 一、当前代码状态结论

当前仓库已经具备以下基础能力：

1. `orders.commission_usdt` 已落地并作为返佣固化字段
2. `orders.payment_channel` / `orders.paid_at` 已落地并参与首单判定
3. RMB / TON / Stars 三条支付链路均已在成功订单写入返佣
4. 用户侧与 Dashboard 侧已有返佣统计读取入口
5. `affiliate_transactions` 表已存在，但目前仅为预留表

同时，当前代码还存在以下关键缺口：

1. `spent_commission_usdt` 仍是占位返回值，当前没有真实扣减来源
2. `available_balance_usdt` 目前等于总返佣，不代表可安全消费余额
3. `affiliate_transactions` 没有业务写入、状态流转、冻结解冻、失败回滚逻辑
4. Web / Bot / Dashboard 都没有正式的提现、返佣兑灵石、返佣兑身份入口
5. 现有模型还不足以支撑提现审核、打款回执、幂等与审计

因此，**当前系统还不能直接对用户开放这三个功能**，但已经具备继续实施的底座。

---

## 二、总体落地原则

### 1. 先做账本，再做消费入口

返佣产生已经固化在 `orders.commission_usdt`，但返佣消费尚未形成账本闭环。

后续所有“返佣被使用”的场景，必须先经过统一联盟账本服务记账，再触发用户资产变化或提现审核流。

### 2. 可用余额必须通过账本聚合得到

未来统一定义：

- `total_commission_usdt`：来自 `orders.commission_usdt` 的累计已赚返佣
- `spent_commission_usdt`：站内已消耗返佣
- `frozen_commission_usdt`：提现申请中冻结返佣
- `available_balance_usdt`：`total - spent - frozen`

禁止继续使用“总返佣直接等于可用余额”的临时口径。

### 3. 先做站内闭环，再做站外资金流

落地顺序固定为：

1. 返佣兑换灵石
2. 返佣兑换身份
3. 返佣提现申请

原因：

- 灵石兑换只影响站内余额，最容易验证
- 身份兑换涉及套餐价值换算，但仍是站内闭环
- 提现涉及审核、冻结、回执、人工打款和风控，不应先做

### 4. 所有消费场景必须幂等

返佣消费一旦开放，就必须防止：

- 用户重复点击
- 网络重试
- 并发双花
- 审核重复操作

因此每一类联盟消费操作都必须具备：

- 业务幂等键
- 短事务行锁或条件更新
- 成功 / 失败 / 回滚的确定性状态迁移

### 5. 用户资产变更与账本记账必须同事务

站内能力包括灵石变化与身份变化。联盟账本扣减与对应资产变更必须放在同一数据库事务中提交，禁止出现：

- 返佣扣了，但灵石没加
- 身份升了，但返佣没扣
- 提现冻结成功，但申请单没生成

---

## 三、推荐实施顺序

### 第一阶段：先把 `affiliate_transactions` 升级为真实账本

本阶段不开放用户入口，只做底层账本能力。

完成目标：

1. 明确返佣总额、已花、冻结、可用余额四个口径
2. 实现联盟账本统一写入服务
3. 让用户中心与 Dashboard 都读取真实余额
4. 为后续三个功能提供公共事务入口

### 第二阶段：开放返佣兑换灵石

本阶段最先交付用户功能。

完成目标：

1. 用户可以将返佣余额按固定汇率兑换成 `credits`
2. 扣减返佣与增加灵石同事务
3. 写入 `affiliate_transactions` 与 `user_logs`
4. 用户中心与后台都能查到兑换记录

### 第三阶段：开放返佣兑换身份

本阶段在灵石兑换稳定后再做。

完成目标：

1. 用户可以使用返佣余额兑换指定身份套餐
2. 沿用现有身份折算逻辑，不重写 `billing_core.py`
3. 将兑换时采用的身份、天数、汇率、价格快照写入联盟账本

### 第四阶段：开放提现申请与后台审核

本阶段只建议先做“申请 + 审核 + 人工打款回执”，不建议直接自动打款。

完成目标：

1. 用户提交提现申请
2. 申请创建时冻结返佣余额
3. 后台审核通过后保留冻结并等待人工打款登记
4. 审核拒绝或打款失败时解冻余额
5. 用户和后台都能看到提现状态链路

---

## 四、账本模型改造方案

### 1. 保留 `orders.commission_usdt` 作为返佣来源

该字段已经承载“返佣是如何产生”的最终固化语义，后续不再改造为流水来源。

未来关系应为：

- `orders.commission_usdt` 负责记录返佣收入
- `affiliate_transactions` 负责记录返佣消费、冻结、解冻、提现申请与提现完成

### 2. 扩展 `affiliate_transactions`

现有表字段不足以支持真实账务。建议通过 Alembic 扩展，而不是新起一套平行表。

建议新增字段：

- `biz_no = Column(String(64), nullable=False, unique=True, index=True)`
  - 业务单号，作为每笔联盟账务主键
- `idempotency_key = Column(String(64), nullable=True, unique=True)`
  - 防重复请求
- `related_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)`
  - 关联来源订单或消费对象
- `direction = Column(String(10), nullable=False)`
  - `IN` / `OUT` / `FREEZE` / `UNFREEZE`
- `balance_before_usdt = Column(DECIMAL(10, 4), nullable=False)`
- `balance_after_usdt = Column(DECIMAL(10, 4), nullable=False)`
- `frozen_before_usdt = Column(DECIMAL(10, 4), nullable=False, server_default='0')`
- `frozen_after_usdt = Column(DECIMAL(10, 4), nullable=False, server_default='0')`
- `operator_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)`
  - 后台审核或人工处理人
- `audit_status = Column(String(20), nullable=True)`
  - `PENDING` / `APPROVED` / `REJECTED` / `PAID`
- `audit_reason = Column(String(255), nullable=True)`
- `audit_at = Column(DateTime, nullable=True)`
- `external_reference = Column(String(128), nullable=True)`
  - 打款流水号、收款渠道流水号等

### 3. 统一交易类型

建议统一枚举：

- `CONVERT_CREDITS`
- `CONVERT_IDENTITY`
- `WITHDRAW_APPLY`
- `WITHDRAW_REJECT`
- `WITHDRAW_PAID`
- `WITHDRAW_UNFREEZE`
- `ADMIN_ADJUST`

说明：

- 收入端仍然来自 `orders.commission_usdt`，不强制补做 `EARN` 流水
- 如果后续希望完全双账本化，再评估是否为历史佣金回补收入流水

### 4. 统一余额计算规则

未来任何地方都必须通过统一 service 计算：

```text
total_commission_usdt = SUM(orders.commission_usdt)
spent_commission_usdt = SUM(affiliate_transactions.amount_usdt WHERE transaction_type IN 消费类成功状态)
frozen_commission_usdt = SUM(affiliate_transactions.amount_usdt WHERE transaction_type IN 提现冻结类且仍有效)
available_balance_usdt = total_commission_usdt - spent_commission_usdt - frozen_commission_usdt
```

禁止在 router 层自行拼接临时 SQL 口径。

---

## 五、核心服务拆分建议

### 1. 新增 `src/core/affiliate_wallet_core.py`

职责：

1. 聚合返佣余额
2. 校验可用余额是否充足
3. 在事务中写联盟流水
4. 提供灵石兑换、身份兑换、提现申请三类统一入口

建议提供以下 helper：

```python
async def get_affiliate_wallet_snapshot(session, user_id: int) -> AffiliateWalletSnapshot:
    ...

async def consume_affiliate_balance(
    session,
    *,
    user_id: int,
    amount_usdt: Decimal,
    transaction_type: str,
    idempotency_key: str,
    details: dict | None = None,
) -> AffiliateTransaction:
    ...

async def freeze_affiliate_balance_for_withdraw(
    session,
    *,
    user_id: int,
    amount_usdt: Decimal,
    idempotency_key: str,
    details: dict | None = None,
) -> AffiliateTransaction:
    ...

async def unfreeze_affiliate_balance(
    session,
    *,
    user_id: int,
    amount_usdt: Decimal,
    related_biz_no: str,
    operator_user_id: int | None = None,
    reason: str | None = None,
) -> AffiliateTransaction:
    ...
```

### 2. 继续复用 `billing_core.py`

身份兑换不能绕开现有折算逻辑，建议：

1. 兑换身份时先读取目标套餐
2. 返佣扣减成功后，调用 `billing_core.py` 既有身份折算 helper
3. 禁止在新模块中复制一份身份转换算法

### 3. 继续复用 `LogService`

站内资产变化必须同时写现有用户日志：

- 灵石兑换：写 `user_logs.operation_type = "affiliate_convert_credits"`
- 身份兑换：写 `user_logs.operation_type = "affiliate_convert_identity"`
- 提现申请：不改 `users.credits`，但可写管理日志或专用操作日志

---

## 六、返佣兑换灵石实施方案

### 1. 功能定义

用户使用可用返佣余额，按固定汇率兑换成系统 `credits`。

### 2. 汇率原则

建议第一版采取固定兑换规则，并写死到配置层，不做动态汇率：

- `1 USDT` 返佣余额 = `N` 灵石

其中 `N` 应由业务明确后写入常量，例如：

- `AFFILIATE_USDT_TO_CREDITS = 100`

### 3. 接口建议

Web API：

- `POST /api/users/me/affiliate/convert-credits`
- `GET /api/users/me/affiliate/transactions`

请求参数建议：

```json
{
  "amount_usdt": "5.0000",
  "idempotency_key": "uuid"
}
```

### 4. 事务流程

单事务内执行：

1. 锁定该用户返佣钱包快照
2. 校验 `available_balance_usdt >= amount_usdt`
3. 计算应增加的 `credits`
4. 写入 `affiliate_transactions(CONVERT_CREDITS)`
5. 增加 `users.credits`
6. 写入 `user_logs`
7. 提交事务

### 5. 最低风控要求

- 单次最小兑换额
- 单日最大兑换次数
- 单日最大兑换总额
- 幂等键去重
- 金额统一保留四位小数

### 6. 上线优先级

此功能优先级最高，建议作为后续第一批上线功能。

---

## 七、返佣兑换身份实施方案

### 1. 功能定义

用户使用返佣余额购买指定身份套餐或身份时长。

### 2. 推荐实现方式

第一版不要新做“返佣专用身份商品”，而是复用现有 `membership_plans`：

1. 由后台为可兑换身份配置专门套餐
2. 套餐价格新增 `affiliate_price_usdt`，或在 `details` 中配置返佣价格
3. 用户兑换时按该价格消耗返佣余额

### 3. 必须遵循的边界

1. 身份到期时间与折算逻辑统一复用 `billing_core.py`
2. 返佣扣减与身份变更必须同事务
3. 必须将兑换时采用的价格、套餐、身份、时长快照写入 `affiliate_transactions.details`

### 4. 接口建议

Web API：

- `GET /api/users/me/affiliate/identity-plans`
- `POST /api/users/me/affiliate/convert-identity`

请求参数建议：

```json
{
  "plan_id": 123,
  "idempotency_key": "uuid"
}
```

### 5. 事务流程

1. 查询可兑换套餐
2. 锁定返佣余额
3. 校验余额充足
4. 写入 `affiliate_transactions(CONVERT_IDENTITY)`
5. 调用现有身份折算逻辑更新 `users.current_identity` / `identity_expire_at`
6. 如套餐附带灵石，也同步增加 `users.credits`
7. 写入 `user_logs`
8. 提交事务

### 6. 风险点

- 兑换价格变更后，必须保留历史快照，不能回看当前套餐价
- 不允许用户在一个请求中同时兑换多个套餐，先保持单笔单套餐

---

## 八、提现申请实施方案

### 1. 功能定位

第一版提现只做：

1. 用户提交申请
2. 后台审核
3. 人工打款后登记回执

不建议第一版接入自动打款。

### 2. 提现状态机

建议统一为：

- `PENDING`
- `APPROVED`
- `REJECTED`
- `PAID`
- `FAILED`

语义说明：

- `PENDING`：已申请，金额已冻结，待审核
- `APPROVED`：审核通过，待人工打款
- `REJECTED`：审核拒绝，金额已解冻
- `PAID`：已打款完成
- `FAILED`：打款失败，金额已解冻

### 3. 提现资料快照

提现申请必须在 `details` 中写入收款快照，例如：

- 提现渠道
- 收款账号
- 收款人姓名
- 用户提交备注
- 风控截图或补充说明

后续即使用户修改账户资料，历史申请仍应保留原快照。

### 4. 用户接口建议

Web API：

- `POST /api/users/me/affiliate/withdraw`
- `GET /api/users/me/affiliate/withdrawals`

请求参数建议：

```json
{
  "amount_usdt": "20.0000",
  "channel": "ALIPAY",
  "account_name": "xxx",
  "account_no": "xxx",
  "note": "optional",
  "idempotency_key": "uuid"
}
```

### 5. 后台接口建议

Dashboard API：

- `GET /api/referrals/withdrawals`
- `POST /api/referrals/withdrawals/{biz_no}/approve`
- `POST /api/referrals/withdrawals/{biz_no}/reject`
- `POST /api/referrals/withdrawals/{biz_no}/mark-paid`
- `POST /api/referrals/withdrawals/{biz_no}/mark-failed`

### 6. 事务与冻结规则

#### 用户发起申请

单事务：

1. 锁定返佣余额
2. 校验可提现余额
3. 写 `affiliate_transactions(WITHDRAW_APPLY, status=PENDING, direction=FREEZE)`
4. 提交事务

说明：

- 申请创建即冻结，不等审核时再冻结
- 否则用户可在审核前继续消费该笔返佣

#### 后台审核通过

单事务：

1. 将申请状态改为 `APPROVED`
2. 记录审核人、审核时间、备注
3. 不解冻金额

#### 后台审核拒绝

单事务：

1. 将申请状态改为 `REJECTED`
2. 写一笔 `WITHDRAW_UNFREEZE`
3. 释放冻结余额

#### 后台登记打款成功

单事务：

1. 将申请状态改为 `PAID`
2. 保持冻结转为实际消耗
3. 记录外部打款流水号

#### 后台登记打款失败

单事务：

1. 将申请状态改为 `FAILED`
2. 写一笔 `WITHDRAW_UNFREEZE`
3. 释放冻结余额

### 7. 最低风控要求

提现第一版至少加入：

1. 最小提现门槛
2. 单日提现次数限制
3. 单日提现总额限制
4. 黑名单用户禁提
5. 后台二次确认
6. 审核人与申请人操作留痕

### 8. 暂不纳入第一版的能力

以下能力建议明确排除在第一版之外：

- 自动打款
- 多级审核流
- KYC 体系
- 手续费阶梯策略
- 多币种提现

---

## 九、接口与模块落点建议

### 1. 新增服务模块

建议新增：

- `src/core/affiliate_wallet_core.py`
- `src/services/affiliate_transaction_service.py`
- `src/web_api/routers/affiliate.py`
- `dashboard/backend/routers/affiliate_withdrawals.py`

### 2. 现有模块需要改造

- `src/services/referral_stats_service.py`
  - 改为返回真实 `spent_commission_usdt` / `available_balance_usdt`
- `src/services/permission_service.py`
  - 继续复用统一统计 service，不再返回占位余额
- `src/web_api/main.py`
  - 注册新的 `affiliate` router
- `dashboard/backend/routers/referrals.py`
  - 增加提现审核与联盟流水查询入口，或拆分新 router
- `src/database/models.py`
  - 扩展 `AffiliateTransaction`

### 3. 不建议改动的模块

- `src/core/billing_core.py`
  - 只复用，不重写
- `src/core/affiliate_core.py`
  - 继续专注“返佣如何产生”，不要混入返佣消费逻辑
- 三条支付成功入口
  - 除非为了接入缓存失效或统计优化，不建议再次重构

---

## 十、统计层改造要求

后续必须让以下页面都读取统一余额口径：

1. 用户中心返佣卡片
2. 用户提现记录页
3. 用户兑换记录页
4. Dashboard 邀请返佣概览
5. Dashboard 提现审核页
6. Dashboard 用户详情页

建议统一输出：

```python
{
    "total_commission_usdt": ...,
    "spent_commission_usdt": ...,
    "frozen_commission_usdt": ...,
    "available_balance_usdt": ...,
}
```

同时兼容旧字段：

- `commission_usdt`

其中：

- `commission_usdt` 可以继续等于 `total_commission_usdt`
- 但前端若要展示“可提现”或“可兑换”，必须使用 `available_balance_usdt`

---

## 十一、测试方案

### 1. 返佣兑换灵石

至少覆盖：

1. 可用余额足够时兑换成功，`users.credits` 增加
2. 重复提交同一 `idempotency_key` 只成功一次
3. 并发双击只消费一次
4. 余额不足时事务整体失败
5. `affiliate_transactions` 与 `user_logs` 同步写入

### 2. 返佣兑换身份

至少覆盖：

1. 身份首购成功
2. 同身份续期成功
3. 低身份兑换高身份时残值折算正确
4. 高身份兑换低身份时按现有规则折算时长
5. 套餐价格快照已写入流水

### 3. 提现申请

至少覆盖：

1. 申请创建即冻结余额
2. 审核拒绝后余额解冻
3. 审核通过后余额仍冻结，不能再次消费
4. 打款失败后余额恢复可用
5. 同一申请单不能重复审核
6. 用户不能取消或修改已进入审核状态的申请

### 4. 统计一致性

至少覆盖：

1. 用户中心余额与 Dashboard 用户详情一致
2. 返佣总额、已花、冻结、可用余额汇总一致
3. 历史旧订单返佣与新消费流水叠加后口径稳定

---

## 十二、建议开发排期

### 第 1 周：底层账本升级

完成：

- Alembic 扩展 `affiliate_transactions`
- 新增联盟钱包核心 service
- 统一余额聚合逻辑
- 改用户中心与 Dashboard 读真实余额

### 第 2 周：返佣兑换灵石

完成：

- Web API
- 用户中心入口
- 后台记录查询
- 幂等与并发测试

### 第 3 周：返佣兑换身份

完成：

- 可兑换套餐配置
- 身份兑换 API
- 折算逻辑接入
- 历史快照与测试

### 第 4 周：提现申请与后台审核

完成：

- 用户申请接口
- 后台审核页与审核接口
- 冻结 / 解冻 / 打款回执
- 风控阈值与审计日志

---

## 十三、最终结论

后续三个功能的正确落地顺序应为：

1. **先把 `affiliate_transactions` 变成真实账本**
2. **先开放返佣兑换灵石**
3. **再开放返佣兑换身份**
4. **最后开放提现申请与后台审核**

本阶段的核心不是继续修改“返佣如何产生”，而是补齐“返佣如何被安全消费”的完整闭环。

只有当以下条件全部满足后，才可以逐步对用户开放：

- 可用返佣余额不再使用占位口径
- 联盟消费具备幂等与防并发双花能力
- 用户资产变更与联盟账本记账同事务提交
- 后台具备提现审核与回执管理能力
- 自动化测试覆盖消费、冻结、解冻、回滚与统计一致性

在此基础上，项目即可进入联盟体系第二阶段实施。
