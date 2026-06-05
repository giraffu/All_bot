---
name: "allbot-billing-auth"
description: "处理 Web 鉴权、JWT、password_version、支付履约、affiliate 账本与 affiliate 兑换灵石/会员。开发充值、登录、返佣、流水逻辑时必须调用本技能。"
---

# AllBot 计费与权限体系 (Billing & Auth)

本技能覆盖 AllBot 中最敏感的“钱与权”边界，适用于所有会改变 `users.credits`、会员身份、会话有效性、支付状态或 affiliate 账本的开发任务。

## 1. 模块功能描述
- **Web 认证与会话安全**：支持 Telegram Mini App / Login Widget 验签、用户名密码登录、绑定密码、改密后 `password_version` 失效旧 token 与安全通知。
- **JWT 体系**：JWT 由 Web 安全层签发，当前认证链会把 `pwd_ver` / `channel` 等 claim 纳入令牌语义；旧 token 失效依赖 `password_version` 与 Redis 黑名单协同收口。
- **多支付通道履约**：RMB、TON、Telegram Stars 均收口到 `payment_fulfillment_service.fulfill_payment_command(...)` 的共享履约内核；RMB `fulfill_order(...)` 仅作为兼容包装保留，TON / Stars 适配层只负责通道解析、金额校验输入与通知适配。
- **Affiliate 账本闭环**：支付成功后可计算首单返佣并落 `affiliate_transactions`；affiliate 余额既可兑换灵石，也可兑换会员/权益，并保留完整审计流水。
- **站内灵石转账**：用户之间的灵石转移使用 `QuotaManager.transfer_credits(...)`，在同一事务内锁定双方用户、扣减买家、增加收款方并写入双方 `user_logs`；Gallery 提示词解锁固定走此入口。
- **Provider 化 billing core**：billing core 相关默认能力已收口到 provider/dependencies 模式，新增逻辑应优先走 provider 注册与依赖注入边界。

## 2. 输入输出规范
### 认证
- **接口**：`POST /api/auth/telegram`
- **输入**：`initData` 或 Login Widget 字段
- **输出**：`access_token`、`token_type`、聚合后的 `user`

- **接口**：`POST /api/auth/login`
- **输入**：`username`、`password`
- **输出**：`access_token`、`token_type`、聚合后的 `user`

- **接口**：密码绑定 / 修改密码相关认证入口
- **语义**：成功后需更新 `password_version` 并触发安全通知链路

### 支付履约
- **共享入口**：`fulfill_payment_command(PaymentFulfillmentCommand(...), dependencies=...)`
- **兼容入口**：RMB `fulfill_order(...)` 仍返回旧 bool 语义
- **输入**：通道、订单定位信息、外部流水、实付金额/单位、通知适配函数
- **输出**：`PaymentFulfillmentResult(status, user_id, plan_name, applied_snapshot)`
- **红线**：履约与会员结算、审计、affiliate 副作用必须保持同事务或同一幂等锚点语义

### Affiliate 兑换
- **灵石兑换**：`redeem_affiliate_balance_to_credits(...)`
- **会员兑换**：affiliate 余额可进一步兑换会员权益，需遵守统一结算语义与审计链

### 站内灵石转账
- **接口/入口**：`QuotaManager.transfer_credits(...)`
- **语义**：同事务完成转出方扣减、转入方增加与双方 `user_logs`；调用方可复用外部 `AsyncSession` 并负责最终提交。
- **典型场景**：Gallery 提示词解锁，买家消耗 1 灵石，作者获得 1 灵石。

## 3. 核心红线
- 严禁手写 `UPDATE users SET credits = ...` 绕过账本与既有结算逻辑。
- 任何资产副作用前，必须先有唯一业务单、外部流水或幂等键作为锚点。
- 用户间灵石转账不得拆成两个独立事务；必须用同一幂等锚点与同一事务保证扣减、入账、审计一致。
- 复用外部 `AsyncSession` 时，`user_logs`、affiliate 流水与会员结算审计必须保持同事务语义。
- Affiliate 缓存失效必须放在最终提交成功后执行，不能在提交前删除缓存。
- 汇率缺失、金额不匹配或结算参数冲突时必须 fail fast，不能静默降级。
- 新增 billing/auth 改动优先走 provider/dependency 注入模式，不回退到 core 直连基础设施实现。
- TON 轮询游标必须持久化到 `runtime_checkpoints`，key 形如 `ton:<merchant_address>:last_lt`；抓链失败或履约失败时不得前移游标。

## 4. 边界条件处理
- **密码改密**：必须递增 `password_version` 并使旧 token 失效。
- **重复支付通知**：RMB / TON / Stars 都必须保持幂等履约。
- **TON 轮询重启**：`last_lt` 从 `RuntimeCheckpoint` 恢复；只有成功处理到新的链上交易后才更新 checkpoint。
- **同幂等键重放**：Affiliate 兑换相同参数返回首次成功快照；不同参数必须冲突失败。
- **纯灵石套餐**：`duration_days == 0` 时只增加灵石，不改变身份。
- **RMB 会员结算**：新老路径兼容时，文档与代码都必须明确“主路径 + legacy fallback”的职责边界。

## 5. 测试要求
- 同一回调或同一链上流水不能重复发货。
- 密码登录需覆盖 Redis 限流、错误口令、改密后旧 token 失效与安全通知。
- Affiliate 兑换需覆盖 PostgreSQL 并发、同幂等稳定返回、同幂等参数冲突。
- 若修改会员结算或 affiliate 会员兑换，必须补对应 focused tests 与审计断言。
