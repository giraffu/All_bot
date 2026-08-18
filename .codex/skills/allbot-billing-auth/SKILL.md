---
name: "allbot-billing-auth"
description: "处理 Web 鉴权、JWT、password_version、支付履约、affiliate 账本与兑换、会员和任务扣费退款。开发充值、登录、返佣或资产流水时必须调用。"
---

# AllBot 计费与鉴权

本 Skill 只保留钱与权限的稳定入口、高压不变量和验证路由。套餐价格、任务价格、
通道配置、当前部署状态与历史迁移以代码、focused tests 和专项文档为准。
支付、扣费、退款或身份 bug 叠加 `allbot-diagnosing-bugs`；修改副作用叠加
`allbot-tdd`。

## 1. 按需阅读

| 任务 | 先读 |
| --- | --- |
| JWT、Telegram 验签、密码与权限 | `docs/子模块_用户认证与权限_user_auth_permission.md` |
| 订单、支付通道、会员、affiliate、退款 | `docs/子模块_计费与支付_billing_payment.md` |
| 任务扣费、取消退款、多阶段 Saga | `docs/子模块_任务调度_task_scheduler.md` |
| Gallery 提示词解锁与用户间转账 | `docs/子模块_社区与存储_gallery_storage.md` |
| 标准邀请奖励和业务口径 | `docs/business/02_BIZ_商业化与会员资产板块.md` |
| 付费群只读资格 | `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` |
| 发布、支付轮询开关与环境配置 | `allbot-ops-deployment` 及其按需文档 |

只读取命中的一行；跨域改动才组合多篇。先用 `rg` 找公开入口、调用方和 focused
tests，再读取对应章节，不要为单一鉴权改动加载全部计费资料。

## 2. 稳定入口与 seam

- Web 认证入口负责 Telegram Mini App/Login Widget 验签、密码登录、JWT
  签发与聚合用户返回。`password_version`/`pwd_ver` 与 Redis 黑名单共同使
  旧会话失效。
- 支付专用 Telegram 会话只放宽支付路由的身份准入；它仍需验签、JWT、
  `password_version` 和订单归属校验，且不能访问普通 Web 路由。
- RMB、原生 TON、USDT-TON Jetton、Telegram Stars 收口到
  `payment_fulfillment_service.fulfill_payment_command(...)`；通道 adapter
  只解析通知、金额与外部流水。legacy wrapper 只能保持兼容返回语义。
- RMB Webhook 与主动查单共用上述履约入口；查单必须由新订单的持久化
  reconciliation job 驱动，严格核对业务单、金额和外部流水。没有稳定服务端
  查单接口时保持关闭，禁止抓取商户后台或自动点击补发。
- Affiliate、会员结算、灵石转账和任务退款必须穿过现有账本/provider seam，
  不允许入口直接改余额。
- Affiliate 人工兑 USDT 使用 `PENDING OUT` 冻结，确认时原流水转 `SUCCESS`，
  拒绝时转 `REJECTED`；禁止用第二笔 OUT 表示确认成功。
- `QuotaManager.transfer_credits(...)` 在同一事务锁定双方、扣减、入账并写
  双方审计；Gallery 提示词解锁复用该入口。
- Bot、Web、Payment API 和 Dashboard 中会调用 billing core 的入口负责执行
  `ensure_billing_core_providers_registered()`；core 不在 import 时自动注册。
- 付费群资格入口只读 `users/orders`，不调用履约或产生资产副作用。

## 3. 资产与身份不变量

- 禁止手写 `UPDATE users SET credits = ...` 绕过账本。
- 每个资产副作用必须先有唯一业务单、外部流水或幂等键；重复通知、重复终态和
  重放只能返回首次结果，不能重复发货、扣费或退款。
- 同一业务动作的扣减、入账、会员结算、affiliate 流水和审计保持同事务或同一
  幂等锚点。外部 `AsyncSession` 的调用方负责最终提交。
- 任务取消退款使用根业务任务的既有扣费事实和
  `credit_idempotency_key`；多阶段任务后续阶段不得二次扣费，任一阶段失败
  按根业务身份幂等收口。
- 具体任务价格和套餐权益只以 registry/domain config、履约代码及对应测试为
  事实源；不要从 workflow 名、Worker override 或旧 History 类型推断价格。
- 标准邀请只在本次请求真实创建用户时绑定；历史用户不得补绑。各阶段奖励按
  账本已有流水补到目标值，不能简单重复加固定值。
- 改密必须递增 `password_version`，使旧 token 失效并执行安全通知链路。
- 金额、汇率、merchant、套餐或结算参数缺失/冲突时 fail fast，不能静默降级。
- Affiliate 缓存只在事务提交成功后失效。
- TON / USDT-TON 轮询游标只有在目标交易成功处理后才前移；抓链或履约失败
  保持原位。USDT-TON 还必须校验官方 Jetton master、目标钱包、未中止交易、
  六位精度金额和订单 forward payload。
- `billing-reconciler` 是 TON 与 USDT-TON 轮询的目标宿主，两个通道由独立
  supervisor 运行；模块/profile 默认禁用。迁移必须先启用并确认 channel health
  与 checkpoint 继续前移，再关闭 `MAIN_BOT_PAYMENT_POLLING_ENABLED`。旧宿主
  默认开启，发布代码本身不得改变支付轮询归属。
- 低阶用户容量准入只使用目标 Worker pool 的健康 enabled 快照；观测缺失或
  请求异常按领域文档的 fail-open 语义告警，不能扩大成全体停服。

## 4. 修改顺序

1. 明确用户身份、业务单、资产类型、幂等键和事务所有者。
2. 找到公开 facade/provider seam 及全部入口；禁止只修一个通道 adapter。
3. 先补失败的行为测试：重复通知、并发、回滚、权限隔离或旧 token 失效。
4. 实现最小纵切，保持 adapter、core、ledger 和通知职责分离。
5. 若入口、claim、价格、异常、ID、provider 或环境开关变化，同步专项文档和
   `allbot-kb-auto-updater`；价格表不复制回本 Skill。

## 5. 最小验证

- 认证：验签失败、错误密码、限流、改密后旧 token 失效、支付 channel 与普通
  channel 隔离。
- 履约：相同外部流水幂等、金额不符 fail fast、事务回滚无部分资产、通知失败
  不改变履约事实；RMB GET/POST 回调、查单竞态、lease 恢复和退避耗尽。
- 账本：并发扣费/兑换/转账、同幂等同参数稳定返回、同键不同参数冲突。
- 任务：单阶段与多阶段只扣一次，重复取消/终态只退一次，History/workflow
  override 不改变业务价格。
- 邀请：历史用户无副作用，新用户关系唯一，各阶段按既有流水补差额。
- 付费群：只读 SQL/handler 测试，确认不改会员、订单、灵石或审计。
- 交付说明触及的公开 API、账本、迁移、配置与测试；本地测试不得描述成线上
  支付或生产配置已验证。
