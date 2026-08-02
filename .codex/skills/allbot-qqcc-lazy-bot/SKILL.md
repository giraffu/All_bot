---
name: "allbot-qqcc-lazy-bot"
description: "处理官方 QQCC 懒人 Bot、用户私有 Bot、场景配置、租户任务归属以及 polling/webhook 部署红线。"
---

# AllBot QQCC 懒人 Bot

修改 `qqcc_bot/`、`qqcc_private_bot/`、QQCC Config、私有 Bot 凭据或
`bot:qqcc*` 任务恢复时必须加载本技能。对话流叠加 `allbot-tg-fsm`，任务链
叠加 `allbot-task-engine`，发布叠加 `allbot-ops-deployment`，公网入口叠加
`allbot-cloudflare-ops`，行为改动叠加 `allbot-tdd`。

## 1. 按需阅读

| 场景 | 必读事实源 |
| --- | --- |
| 官方菜单、场景、Config Web、示范媒体 | `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`、`src/services/qqcc_config_service.py` |
| 用户私有 Bot、凭据、webhook、续跑 | `docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md` |
| quick image/video FSM 与 callback | `allbot-tg-fsm`、`src/services/quick_image_submission_service.py`、`quick_video_submission_service.py` |
| 扣费、continuation、恢复和清理 | `allbot-task-engine`、`docs/子模块_生成任务全链路_task_full_chain.md` |
| Config/Bot 独立发布 | `allbot-ops-deployment`、`docs/子模块_Git不可变发布_git_immutable_release.md` |

不要把完整场景字段、模型枚举、迁移流水或某次线上状态复制回本 Skill。

## 2. 稳定入口

- 官方 Bot：`qqcc_bot/main.py`，使用独立 token 和 polling。
- 运行时配置：`src/services/qqcc_config_service.py`，checkpoint
  `qqcc_lazy_bot_config:v1`。
- Config API：`dashboard/backend/qqcc_config_main.py` 与
  `dashboard/backend/routers/qqcc.py`。
- Config UI：`dashboard/frontend/src/QqccConfigApp.vue` 与
  `QqccBotSettings.vue`。
- 私有 Bot 申请：`qqcc_bot/private_bot_fsm.py`，只注册在官方 QQCC。
- 私有 webhook：`src/web_api/routers/private_bots.py` → Redis stream →
  `python -m qqcc_private_bot.worker`。
- 租户凭据和生命周期：`private_qqcc_bot_credentials.py`、
  `private_qqcc_bot_service.py`、`private_qqcc_bot_runtime.py`。
- 公共上下文判断：`src/services/qqcc_runtime_context.py`。

## 3. 官方 QQCC 边界

- QQCC 是简化 Bot，只注册 quick image/video FSM、QQCC 市集和最小 callback。
  不注册主 Bot 高级 FSM、充值、affiliate、TON、完整 Gallery 或支付回调。
- 官方菜单由配置归一化后生成。V1/V2 场景开关、排序、显隐和旧 callback
  兼容的完整契约以 QQCC 专项文档和配置 service 为准，前端不得另存默认
  场景或模型事实表。
- quick image/video FSM 只处理 Telegram 状态、文件、额度提示和清理。
  场景归一、后处理链、尾帧链、固定价格和执行 payload 必须留在 submission
  service，不能重新堆回 handler。
- 只有链路第一个真实任务按普通规则排队并允许取消；后续 stage 是
  continuation，必须高优先级、隐藏排队/取消，并由 core runtime 权威拒绝
  旧取消入口。
- QQCC 自生成结果不允许投稿或公开。最终文案、History 和重生成 metadata
  必须保持根功能/场景语义，不暴露内部绘图、换脸或尾帧 stage。
- QQCC 市集只原生应用安全单图模板；复杂多图、多视频、SCAIL-2、LTX 和
  拼接模板只能 Web handoff。原生提交必须带 `source_post_id`、
  `allow_contribute=False` 和 `client_type=bot:qqcc`，点击按钮不得预增
  `applied_count`。
- 场景示范媒体先发媒体、再发上传提示。Telegram file ID 缓存失效时回退
  当前 R2 对象；失败只能降级为文字提示。Config Backend 与 Bot 的 object
  key allowlist 是共享契约，修改时必须同轮更新并回归“写一个缓存不删除
  其它媒体”。
- Config 示例生成不扣费、不占用户并发、不写 History。长时监视不得持有
  request-scoped DB session；浏览器关闭后仍应由服务端完成监视和幂等回写。
- 主 Bot 的旧懒人入口只跳转 QQCC 或提示入口未配置，不能恢复任务提交；
  QQCC 自身的版本化场景 callback 和必要 legacy callback 继续按配置处理。

## 4. 任务归属与私有 Bot

- 官方 QQCC 必须写入 `client_type=bot:qqcc`。主 Bot 只恢复 `bot`/legacy，
  官方 QQCC 只恢复 `bot:qqcc`，私有实例只恢复
  `bot:qqcc-private:<private_bot_id>` exact match。
- 私有访客使用自己的 `internal_user_id`、余额、会员和并发权限；owner 只
  管理配置与启停，不替访客付费。
- 每个私有提交必须经过持久 submission ledger，保留 owner fence、确定性
  task ID、同事务 debit marker、稳定 refund/concurrency key 和安全 retention。
  不得删除待恢复、待投递或待补偿记录。
- 多阶段私有任务必须先持久化原始输入和完整 stage plan。每阶段先 CAS
  保存结果再清理 active registry；最终先进入 `delivery_pending`，发送成功
  后再标记 delivered。恢复扫描不能依赖 TaskRegistry 非空。
- 私有 zombie 只走 tenant-aware cleaner。通用或手工 `clean_zombies()`
  必须跳过所有 private client type。
- 暂停/禁用只阻止新 update，不能终止已经扣费的 monitor/continuation；
  永久解绑后才停止。相同 Bot ID 的 token 允许救援轮换，不同 Bot ID 的
  替换必须走管理员永久解绑并等待 active task 清空。
- private worker 使用 webhook，不使用租户 token polling。全局 inflight、
  单 Bot prefetch 和 deferred ID 必须有界；启动先追平旧 PEL，再读取新消息，
  同 Bot update 保持顺序。
- 频道会员检查只能使用进程共享的官方 QQCC checker callable。它只执行
  成员查询，不启动第二个 polling，也不把官方 token/Bot 对象交给租户。

## 5. 密钥、网络与进程红线

- 官方测试/正式 token、私有 token、keyring、JWT、fingerprint key 不得进入
  Git、文档、日志、工单或聊天。
- 私有 token 在数据库中使用版本化 AES-GCM ciphertext 和 HMAC fingerprint；
  管理员不能读取明文。AES、fingerprint、owner JWT 必须是不同的 32-byte
  Base64URL key。
- `PRIVATE_QQCC_BOT_ENABLED` 是总 gate。关闭时 worker 不启动；开启时
  `scripts/validate_private_qqcc_bot_env.py` 必须严格验证 keyring、forbidden
  Bot IDs、HTTPS API/file base、owner/admin Host 和对应官方 token。
- 私有 Telegram API/file base 必须是独立 HTTPS 契约，不能继承公网 HTTP
  Local Bot API。Owner/Admin/unknown Host 要在 Nginx 和 backend 双层隔离；
  unknown 或跨 Host API 返回 404。
- owner WebApp 只允许受控 Telegram WebView frame ancestor，`connect-src`
  保持 `'self'`；admin/unknown 保持禁止嵌入。
- 官方 QQCC 是唯一 polling 实例。成功空轮询也刷新 liveness；private
  Application 不启用 polling watchdog。官方 liveness 只判断 `getUpdates`
  是否停滞，业务 backlog 不得触发进程重启；官方 update 按用户串行、跨用户
  有界并发。任何启动或重建前先确认没有相同 token 的第二个 polling 进程。
- `private-bot-worker` 镜像与 artifact inputs 必须同时包含
  `qqcc_private_bot/` 和 `qqcc_bot/`，因为租户复用官方 Application factory。

## 6. 发布边界

- 代码或文档任务不授权正式发布。生产 mutation 必须由用户明确要求，并
  遵循 `allbot-ops-deployment`。
- 从完整 main SHA 分别构建 `qqcc-bot`、`qqcc-config-backend` 或
  `qqcc-config-frontend`；部署时一次只提交一个精确 digest。test/prod 状态
  按模块独立，prod 每个 mutation 都必须带 `--confirm-prod`。
- `database-migration`、`config-contract` 与 `compose-contract` 是独立模块，
  不能借 QQCC 代码部署隐式执行或绕过。
- 禁止 legacy 发布脚本、rsync、现场 build、源码 bind mount 和自由 compose。
  发布器只消费不可变 digest，并验证目标服务、single polling 和健康；失败
  只恢复该模块 previous identity。
- 私有 Bot worker 涉及 migration、Web API、QQCC Config、共享密钥和公网
  Host，不属于普通 QQCC Bot/Config 的窄发布范围。

## 7. 最小验证

- 菜单与 callback：配置开关、版本路由、旧按钮 fail closed、主 Bot 跳转、
  callback 应答和空场景隐藏。
- quick image/video：根价格、额度、首任务取消、continuation 不可取消、
  失败退款、最终 History/文案和重生成。
- Config：规范化、未知 key 丢弃、场景引用/循环拒绝、示范媒体 allowlist、
  后台监视释放 DB session。
- 私有 Bot：exact client type、ledger 幂等、跨重启 continuation、投递 fence、
  token 救援轮换、tenant cleaner 和 bounded stream。
- 安全：gate 开/关、validator、HTTPS/Host、秘密不落输出、官方 checker
  无 polling。
- 运行时：同用户 update 串行、跨用户有界并发、慢媒体 I/O 有界，以及业务
  backlog 不触发 polling watchdog 重启。
- 发布：focused tests、compose `config -q`、脚本语法、目标健康与 single
  polling；不得把代码支持或本地测试写成已部署/已完成线上验收。
