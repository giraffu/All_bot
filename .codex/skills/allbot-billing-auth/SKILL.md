---
name: "allbot-billing-auth"
description: "处理 Web 鉴权、JWT、password_version、支付履约、affiliate 账本与 affiliate 兑换灵石/会员。开发充值、登录、返佣、流水逻辑时必须调用本技能。"
---

# AllBot 计费与权限体系 (Billing & Auth)

本技能覆盖 AllBot 中最敏感的“钱与权”边界，适用于所有会改变 `users.credits`、会员身份、会话有效性、支付状态或 affiliate 账本的开发任务。

涉及支付、扣费、退款、身份或 affiliate bug 时，叠加 `allbot-diagnosing-bugs` 建立可复现反馈环；新增或修复资产副作用时，叠加 `allbot-tdd` 用行为测试锁定幂等、事务和审计。

## 1. 模块功能描述
- **Web 认证与会话安全**：支持 Telegram Mini App / Login Widget 验签、用户名密码登录、绑定密码、改密后 `password_version` 失效旧 token 与安全通知；`POST /api/auth/telegram/payment` 只签发支付会话，允许低阶用户访问支付路由，但普通 Web 路由必须拒绝该 channel，即使用户自身已满足身份/境界门禁也不能借支付会话访问。
- **JWT 体系**：JWT 由 Web 安全层签发，当前认证链会把 `pwd_ver` / `channel` 等 claim 纳入令牌语义；旧 token 失效依赖 `password_version` 与 Redis 黑名单协同收口。
- **多支付通道履约**：RMB、TON、Telegram Stars 均收口到 `payment_fulfillment_service.fulfill_payment_command(...)` 的共享履约内核；RMB `fulfill_order(...)` 仅作为兼容包装保留，TON / Stars 适配层只负责通道解析、金额校验输入与通知适配。
- **标准邀请奖励**：仅当用户 facade 在本次邀请请求中真实创建用户（`is_new=True`）时，才允许记录邀请关系和被邀请人 `welcome_bonus = +6`；历史用户即使 `invited_by` 为空也不得补绑。邀请人不发注册奖励；入群阶段邀请人累计补到 5 灵石，首次生成阶段累计补到 10 灵石，历史 `referral_reward_initial` 需计入目标防重复发。
- **Affiliate 账本闭环**：支付成功后可计算首单返佣并落 `affiliate_transactions`；affiliate 余额既可兑换灵石，也可兑换会员/权益，并保留完整审计流水。
- **站内灵石转账**：用户之间的灵石转移使用 `QuotaManager.transfer_credits(...)`，在同一事务内锁定双方用户、扣减买家、增加收款方并写入双方 `user_logs`；Gallery 提示词解锁固定走此入口。
- **付费群审核资格**：`paid_group_guard_bot` 只读查询 `users.telegram_id`、`users.user_group` 与 `orders`，默认允许历史成功支付订单、后台赠送套餐订单、筑基期及以上修为对应的 Telegram 用户入群；该路径不做资产副作用。
- **Provider 化 billing core**：billing core 相关默认能力已收口到 provider/dependencies 模式，新增逻辑应优先走 provider 注册与依赖注入边界。
- **低阶用户容量准入**：`billing_core.check_concurrency_lock(..., task_type=...)` 在扣费前按目标 Worker 执行池检查 projected pending；只限制外门弟子中的凡人/练气期，不再读取全局 `queue_size > 300`。
- **自由P图版本定价**：主 Bot/Web 的 `free_edit_v2_5` 单图 3 灵石、双图 7 灵石并走标准单阶段 Saga，扣费前必须按实际图片数确定成本；自由P图 v3 固定 5 灵石并把 BF16→换脸视为同一根任务，第二阶段不得重复扣费。两者失败/取消退款都以根业务任务的实际扣费和账本幂等键收口；QQCC 自由P图 v3 仍保持 6 灵石，不随主入口调整。
- **图片换脸版本定价**：独立 legacy `face_swap` 固定 1 灵石，独立 `face_swap_v2` 固定 2 灵石；快速/随机换脸仍提交 legacy 类型。i2i_pro worker 把 legacy 类型 override 到 `face_swap_v2.json` 只改变实际 workflow，绝不能据此改成 2 灵石或改业务/History 类型。自由P图 v3、SCAIL-2 首帧预处理等组合任务中的 V2 已包含在根任务总价，禁止二次扣费；SCAIL-2 两阶段任一失败或取消都必须使用根业务 ID 的既有幂等键全额退款，第二阶段自身成本固定为 0。QQCC 场景未配置 `credit_cost` 时每个原脸恢复步骤仍显式增加 2 灵石，配置固定总价后则属于根场景价格、不得二次扣费。幻想换脸继续提交 `i2i_pro` 并保持 6 灵石。
- **QQCC 场景固定总价**：`video_scenes`、`ai_video_scenes`、`draw_scenes`、`filter_scenes` 的根场景可配置正整数 `credit_cost`。固定价链只在第一个真实任务用 `cost_override` 扣一次，后续任务必须 `deduct_quota=false`；后续生成或最终投递失败以 `qqcc_scene_refund:<billing_id>` 全额幂等退款。`null`/缺失保持旧逐段计费与退款，快速换脸不受影响。
- **入口负责 provider 注册**：Bot、Web API、Payment API 和 Dashboard Backend 只要会调用 billing core，都必须在启动入口调用 `ensure_billing_core_providers_registered()`。Dashboard 的退款、强制终止和资产类管理接口也会进入 billing core；只注册 task core provider 会触发 `Billing core providers 未注册`。

## 2. 输入输出规范
### 认证
- **接口**：`POST /api/auth/telegram`
- **输入**：`initData` 或 Login Widget 字段
- **输出**：`access_token`、`token_type`、聚合后的 `user`

- **接口**：`POST /api/auth/login`
- **输入**：`username`、`password`
- **输出**：`access_token`、`token_type`、聚合后的 `user`

- **接口**：`POST /api/auth/telegram/payment`
- **输入**：Telegram Mini App `initData` 或 Login Widget 字段
- **输出**：`channel=telegram_payment` 的支付会话及聚合后的 `user`
- **语义**：只跳过 Web 身份/境界准入，不跳过 Telegram 验签、JWT 校验、`password_version` 失效或订单归属校验

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

### 标准邀请奖励
- **注册邀请**：`PermissionGrowthChannelService.process_referral(...)` 必须使用 `get_or_create_user_by_telegram(...)` 返回的 `is_new` 判定资格；`QuotaManager.process_referral(...)` 还必须显式收到 `new_user_was_created=True`，才可写 `referrals/users.invited_by/referral_count` 和被邀请人的 `welcome_bonus` 审计，不给邀请人加灵石。
- **入群奖励**：`QuotaManager.process_channel_reward(...)` 以 `referral_reward_channel` 将邀请人累计补到 5 灵石。
- **首次生成奖励**：`QuotaManager.process_generation_referral_reward(...)` 以 `referral_reward_generation` 将邀请人累计补到 10 灵石。
- **幂等锚点**：按邀请人 `user_logs` 中 `referral_reward_initial/referral_reward_channel/referral_reward_generation` 且 `extra_info.invitee_id` 匹配的正向流水累加，计算差额后发放。

### 站内灵石转账
- **接口/入口**：`QuotaManager.transfer_credits(...)`
- **语义**：同事务完成转出方扣减、转入方增加与双方 `user_logs`；调用方可复用外部 `AsyncSession` 并负责最终提交。
- **典型场景**：Gallery 提示词解锁，买家消耗 1 灵石，作者获得 1 灵石。

### 付费群审核资格
- **入口**：`paid_group_guard_bot.eligibility.check_paid_group_eligibility(...)`
- **输入**：Telegram user id
- **输出**：`PaidGroupEligibilityDecision(eligible, reason, internal_user_id, matched_order_id, user_group)`
- **语义**：命中 `users.telegram_id` 且满足任一条件：存在 `orders.status = 'SUCCESS'` 的订单，其中真实支付订单要求 `paid_at IS NOT NULL`，后台赠送套餐通过 `manual_` tx_hash 或 `GIFT:` order_id 识别；或 `users.user_group` 为 `筑基期` 及以上。
- **红线**：该入口只读，不更新会员身份、灵石、订单、返佣或 user_logs。

## 3. 核心红线
- 严禁手写 `UPDATE users SET credits = ...` 绕过账本与既有结算逻辑。
- 任何资产副作用前，必须先有唯一业务单、外部流水或幂等键作为锚点。
- 任务取消退款必须带 `credit_idempotency_key` 审计字段，当前由 `task_refund:<refund_type>:<registry_task_id>` 派生，确保同一任务重复取消/重复终态收口不会重复加灵石。
- 用户间灵石转账不得拆成两个独立事务；必须用同一幂等锚点与同一事务保证扣减、入账、审计一致。
- 复用外部 `AsyncSession` 时，`user_logs`、affiliate 流水与会员结算审计必须保持同事务语义。
- 标准邀请关系只能绑定到本次请求真实创建的用户；不得用 `invited_by is None`、注册时间、余额或历史任务数量推断“新用户”，历史用户不得补绑或获得后续邀请奖励资格。
- 标准邀请奖励不得在注册节点给邀请人加灵石；入群和首次生成必须按目标值补差额，不能简单叠加固定奖励。
- Affiliate 缓存失效必须放在最终提交成功后执行，不能在提交前删除缓存。
- 汇率缺失、金额不匹配或结算参数冲突时必须 fail fast，不能静默降级。
- 新增 billing/auth 改动优先走 provider/dependency 注入模式，不回退到 core 直连基础设施实现。
- 容量准入公式固定为 `(pending + 1) > 50 × max(accepting_workers, 1)`；`accepting_workers` 只包含健康且 enabled 的节点。Central 快照/字段缺失、请求异常或未知执行池必须 fail-open 并记录告警，不能把观测故障扩大成全体低阶用户停服。
- 付费群审核资格不得绕过订单事实源去直接相信 `current_identity`，否则手动改身份、过期身份和赠送订单会混成同一语义；修为准入只读使用 `users.user_group` 的筑基期及以上等级。
- TON 轮询游标必须持久化到 `runtime_checkpoints`，key 形如 `ton:<merchant_address>:last_lt`；抓链失败或履约失败时不得前移游标。
- `TON_PAYMENT_POLLING_ENABLED=false` 可禁用 Bot 启动时的 TON 链上轮询；云测试 `bot-test` 默认关闭该轮询，避免空测试库回扫真实商户地址历史交易。生产默认仍为开启。
- TON merchant 唯一事实源是宿主 `VITE_MERCHANT_ADDRESS`，必须经 `ton_payment_config` 的 TON 地址解析校验；开关为真但地址缺失/非法时 Bot 不创建 poller，Web plans 返回 `ton_payment_enabled=false`/空地址，TON 预建单在任何 DB 查询/写入前以 `503 TON_PAYMENT_UNAVAILABLE` 拒绝。前端不得保留地址常量或订单地址兜底。
- TON 用户入口统一为主 Vue `/billing?method=ton&kind=membership`；Bot 只使用 `MINI_APP_URL` 构造该深链。独立 `ton_payment_frontend`、`WEBAPP_URL` 和 `pay.aivison.it.com` 代码兜底均已退出。
- merchant 规范化地址决定 checkpoint key；真实地址变化必须形成新 key，禁止复制旧游标。抓链或履约失败仍不得前移 `last_lt`。

## 4. 边界条件处理
- **密码改密**：必须递增 `password_version` 并使旧 token 失效。
- **重复支付通知**：RMB / TON / Stars 都必须保持幂等履约。
- **TON 轮询重启**：`last_lt` 从 `RuntimeCheckpoint` 恢复；只有成功处理到新的链上交易后才更新 checkpoint。
- **同幂等键重放**：Affiliate 兑换相同参数返回首次成功快照；不同参数必须冲突失败。
- **纯灵石套餐**：`duration_days == 0` 时只增加灵石，不改变身份。
- **RMB 会员结算**：新老路径兼容时，文档与代码都必须明确“主路径 + legacy fallback”的职责边界。

## 5. 测试要求
- 同一回调或同一链上流水不能重复发货。
- 支付专用 Telegram 会话必须覆盖“低阶用户可创建/查询本人订单、普通 Web 路由仍拒绝”的权限隔离测试。
- 密码登录需覆盖 Redis 限流、错误口令、改密后旧 token 失效与安全通知。
- Affiliate 兑换需覆盖 PostgreSQL 并发、同幂等稳定返回、同幂等参数冲突。
- 标准邀请奖励需覆盖历史用户不建关系且无账本副作用、新用户注册不发邀请人、入群补到 5、首次生成补到 10、老 `referral_reward_initial` 计入目标的 focused tests。
- 若修改会员结算或 affiliate 会员兑换，必须补对应 focused tests 与审计断言。
- 若修改付费群审核资格口径，必须补 `tests/paid_group_guard_bot` 中的 SQL/handler focused tests，并同步 `docs/子模块_付费群审核Bot_paid_group_guard_bot.md`。
