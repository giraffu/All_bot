---
name: "allbot-billing-auth"
description: "处理 Web 鉴权、JWT、password_version、支付履约、affiliate 账本与兑换、会员和任务扣费退款。开发充值、登录、返佣或资产流水时必须调用。"
---

# AllBot 计费与鉴权

价格、通道和部署状态以代码、focused tests 与专项文档为准。身份或资产 bug
叠加 `allbot-diagnosing-bugs`；修改副作用叠加 `allbot-tdd`。

## 1. 按需阅读

| 任务 | 先读 |
| --- | --- |
| JWT、Telegram 验签、密码与权限 | `docs/子模块_用户认证与权限_user_auth_permission.md` |
| 修为升级、身份权益、低信任与闪回瓶容量 | `docs/business/04_BIZ_用户修为与身份权限体系.md` |
| 订单、支付通道、会员、affiliate、退款 | `docs/子模块_计费与支付_billing_payment.md` |
| 任务扣费、取消退款、多阶段 Saga | `docs/子模块_任务调度_task_scheduler.md` |
| Gallery 提示词解锁与用户间转账 | `docs/子模块_社区与存储_gallery_storage.md` |
| 标准邀请奖励和业务口径 | `docs/business/02_BIZ_商业化与会员资产板块.md` |
| 付费群只读资格 | `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` |
| 发布、支付轮询开关与环境配置 | `allbot-ops-deployment` 及其按需文档 |

只读命中行；跨域组合。用 `rg` 找入口、调用方和 focused tests。

## 2. 稳定入口与 seam

- Web 入口负责 Telegram 验签、密码登录与 JWT；`password_version` 和黑名单使旧
  会话失效。支付会话仍校验验签、JWT、版本和订单归属，不能访问普通 Web 路由。
- 密码限流只消费 ASGI/可信代理层解析后的 client host，不在业务 service 内直接
  信任 `X-Real-IP` 或 `X-Forwarded-For`。Telegram 外部 ID 经统一 resolver 转换为
  `internal_user_id`，领域服务禁止双 namespace 猜测。
- RMB、TON、USDT-TON、Stars 收口到
  `payment_fulfillment_service.fulfill_payment_command(...)`；adapter 只解析通道。
  Webhook/主动查单共用该入口；无稳定查单 API 时关闭，禁止抓商户后台补发。
- RMB provider 固化在订单；支付宝直连返回短期结算链接，同笔 WAP 复用二维码与
  按钮，公开详情不含签名 URL/内部 ID，白名单失败不回退。
- Affiliate、会员、转账和退款穿过账本/provider seam；人工兑 USDT 只把原
  `PENDING OUT` 转终态。调用 core 的入口负责 provider 注册；core import 无副作用。
- 付费群只读 `users/orders`，不产生资产副作用。
- 动态等级权益以 `user_tier_policy_config:v1` 和
  `user_tier_policy_service.py` 为源；身份过期或未知时回落外门。

## 3. 资产与身份不变量

- 禁止 SQL 直改余额。副作用先有业务单/外部流水/幂等键；重放只能返回首次结果。
  扣减、入账、会员、affiliate 与审计同事务/锚点，外部 session 由调用方提交。
- 取消退款使用根任务扣费事实与 `credit_idempotency_key`；多阶段只扣一次并按根
  身份收口。
- 内置价格以 domain config 为准；可售卖目录以 `task_pricing_catalog.py` 为源，
  registry 和 workflow 不是商品目录。
- 标准邀请只绑定本次真实新建用户，各阶段按已有流水补到目标值。
- 改密递增 `password_version` 并通知；金额、汇率、merchant、套餐/结算冲突时
  fail fast；Affiliate 缓存只在提交后失效。
- TON / USDT-TON 游标仅在目标交易成功后前移；USDT 还校验官方 master、目标、
  终态、精度与 payload。轮询宿主迁移顺序和容量准入细节按专项文档执行。

## 4. 修改顺序

1. 明确身份、业务单、资产、幂等键和事务 owner。
2. 找全公开 facade/provider 与入口，先补重放、并发、回滚、权限或旧 token 测试。
3. 实现最小纵切，分离 adapter/core/ledger/通知；入口、价格、ID、provider 或开关
   变化时同步专项文档，不复制价格表到 Skill。

## 5. 最小验证

- 认证覆盖验签/密码/限流/旧 token/channel 隔离；履约覆盖外部流水幂等、金额、
  回滚、provider/RSA2、回调查单竞态和直连 token fail closed。
- 账本覆盖并发与幂等冲突；任务只扣退一次；邀请只影响真实新用户；付费群只读。
- 交付列明 API、账本、迁移、配置与测试，不把本地测试描述成生产验证。
