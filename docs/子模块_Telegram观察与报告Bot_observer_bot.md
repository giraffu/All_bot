# 子模块：Telegram 观察与报告 Bot

## 定位与 V1 范围

`observer_bot/` 是独立 Telegram 管理员通知与群聊报告进程。它和现有客服 Bot
部署在同一套云控制面资源上，不共享 handler、进程或业务数据库。Observer 是
`OBSERVER_BOT_TOKEN` 唯一的 polling owner；客服 Bot 仅复用该 token 的 outbound
`sendMessage` 能力，把工单管理员通知也统一显示为 `@qq_notification_bot`，不读取
`observer_prod`、不导入 Observer handler，也不调用 `getUpdates`。

V1 只包含：

- Telegram 管理员通知；
- AllBot Central 队列只读监控；
- 明确授权群的文本消息与 caption 采集；
- 日报、周报、月报和管理员手动报告；
- 通过 OpenAI-compatible HTTP 直接调用本地 LM Studio。

V1 不包含网站抓取、平台关键词监听、Civitai/Hugging Face、外部 AI 群 userbot，
也不承载客服工单、回复或主库 outbox；这些仍由客服域负责。

## 架构

```text
Telegram 管理员 / 授权群
           │ polling（独立 token）
           ▼
      observer-bot ───── GET /system/status ─────► Central API
           │
           ├──── DML ───► observer_prod（独立逻辑数据库/role）
           │
           └──── OpenAI-compatible HTTP ─────────► 本地 LM Studio
                                                   （Tailscale 私网）
```

只有一个 `observer-bot` polling 进程；PTB JobQueue 承载轮询和报告 tick，不增加 Redis、
Celery、消息总线或第二个 worker。PostgreSQL `observer_report_runs` 是报告去重和
有限重试的持久事实源。

## 稳定入口与职责

- `observer_bot/main.py`：Telegram application、依赖装配和 job 注册。
- `observer_bot/handlers.py`：授权群文本归一与采集。
- `observer_bot/queue_monitor.py`：Central client、确定性拥堵/恢复策略。
- `observer_bot/lmstudio_client.py`：`/v1/models` 与
  `/v1/chat/completions` adapter。
- `observer_bot/report_service.py`：周期窗口、分段摘要、合并和持久化。
- `observer_bot/repository.py`：observer 自有 PostgreSQL 数据访问。
- `observer_bot/schema.sql`：独立 schema 事实源。

队列监控使用 Central 的短缓存观测接口，不替代实际调度。队列拥堵告警只由管理
后台的两个数量设置值触发，条件为任一满足：

- 全局 `queue_size` 大于管理后台设置的“总排队数量”；
- 任一任务类型 `pending_count` 大于管理后台设置的“单个类型排队数量”，
  通知中列出命中的任务类型；

最长等待时间和可接单 Worker 数仍可通过管理员 `/status` 查询，但不会单独触发
队列拥堵，也不会出现在拥堵通知中。首次超限发送告警，持续超限按 cooldown
提醒，两个数量均恢复到设置值以内后发送恢复消息。连续读取 Central 失败达到
阈值也告警，重新取得状态后发送监控恢复消息。以上逻辑不调用 LLM。

## 群采集与报告

只有管理后台“通知中心”中启用的授权群 chat ID 会被保存；env 中的
`OBSERVER_AUTHORIZED_GROUP_IDS` 只在数据库首次初始化时作为可选 bootstrap。
当前只保存文本或 caption，忽略 Bot 作者和无文本媒体；编辑消息按
`(chat_id, message_id)` 更新。
需要在群内明确告知成员消息会被持久化并由本地模型分析。

报告按配置时区生成最近完成的自然日、自然周和自然月。报告 run key 由类型和
周期终点构成，重启后不会重复发送成功报告；失败最多重试三次，卡住一小时的
running run 可被接管。历史群消息按 retention 定时清理。

长周期消息先按字符预算分段，每段独立摘要，再由同一模型合并。prompt 把群消息
放在显式数据边界中，要求忽略数据里的命令和系统提示。LM Studio 不可用只会让
报告失败并稍后重试，不影响采集和队列告警。

模型选择顺序：

1. 若配置 `OBSERVER_LM_STUDIO_MODEL`，只使用该模型且缺失时失败；
2. 否则读取 `/v1/models`，优先本机已下载的 Qwen3 30B-A3B Instruct，其次
   Qwen3 14B、Qwen3 8B，再回退其它 Qwen instruction 模型；
3. embedding、reranker、vision 模型不会被选为文本摘要模型。

自动选择的高优先级模型若因本地显存等原因无法加载，会按排序尝试下一个已下载
模型；显式配置的模型则 fail closed，不静默换模型。

LM Studio 建议启用 server authentication、JIT model loading 和 idle unload，
只通过 Tailscale 地址向云主机开放，不公网暴露 1234 端口。Observer 不启用
LM Studio MCP 或工具调用。

## 数据库

复用现有 managed PostgreSQL 集群，但使用独立逻辑数据库 `observer_prod`；数据库
账号按当前操作者批准的部署配置复用。Observer 不使用主系统 `DATABASE_URL`，也不
查询用户、工单、History、账本或 Worker 日志表。

七张表：

- `observer_group_messages`：授权群文本；
- `observer_alert_states`：跨重启告警状态；
- `observer_report_runs`：报告 claim、状态、模型和结果。
- `observer_runtime_settings`：队列告警开关、总排队与单类型排队阈值、采集和三类
  报告开关；报告默认关闭；
- `observer_admin_recipients`：observer 管理员 Telegram 用户 ID；
- `observer_authorized_chats`：允许采集的群 ID；
- `observer_notification_logs`：发送目标、结果、错误类型和有限内容预览。

建库和 schema 应由迁移/管理员连接执行。Dashboard Backend 使用同一
`OBSERVER_DATABASE_URL` 的低流量连接管理 observer 配置和记录，不把这些表加入
AllBot 主库。schema 命令：

```bash
OBSERVER_DATABASE_ADMIN_URL=... python -m observer_bot.schema
```

该命令是数据库 mutation，正式执行前需要用户再次明确确认。管理员 URL 只在一次
性迁移环境中使用，不投影到长期运行的 `observer-bot.env`。

## 配置

必填：

- `OBSERVER_BOT_TOKEN`
- `OBSERVER_DATABASE_URL`
- `OBSERVER_LM_STUDIO_BASE_URL`

主要可选：

- `OBSERVER_ADMIN_CHAT_IDS`、`OBSERVER_AUTHORIZED_GROUP_IDS`：仅首次启动 bootstrap；
  初始化后以 Dashboard“通知中心”的数据库配置为准
- `OBSERVER_LM_STUDIO_API_KEY`
- `OBSERVER_LM_STUDIO_MODEL`
- `OBSERVER_QUEUE_ALERT_COOLDOWN_SECONDS`
- `OBSERVER_REPORT_HOUR`、`OBSERVER_TIMEZONE`
- `OBSERVER_MESSAGE_RETENTION_DAYS`
- `TELEGRAM_API_BASE_URL`、`TELEGRAM_FILE_BASE_URL`

管理员私聊命令：`/status` 查看实时 Central 快照；
`/report [daily|weekly|monthly]` 生成最近完成周期的报告。

Dashboard 独立导航页“通知中心”通过已认证接口
`GET/PUT /api/notification-center/settings` 管理 observer 管理员、授权群、工单
通知接收者、功能开关以及总排队/单类型排队阈值；
`GET /api/notification-center/reports` 与
`GET /api/notification-center/notifications` 分页查看报告及通知记录。配置由 Bot
短缓存读取，最多约 15 秒生效，不需要重启。两个数量设置值均为 `1..100000` 的
整数，默认分别为 20 和 10；实际数量严格大于设置值时触发，等于设置值时不触发。
schema 使用 `ADD COLUMN IF NOT EXISTS` 升级已有数据库，不会覆盖既有收件人、
授权群或开关设置。

`OBSERVER_BOT_TOKEN` 也由配置契约最小投影到 `support-bot`，但只用于 outbound
工单通知。改变该 token 时必须把 `observer-bot` 和 `support-bot` 都视为受影响
消费者并分别按精确 digest 重部署；任何时刻仍只能有一个 polling 实例。

## 发布与验证

正式发布模块名 `observer-bot`，Compose service 同名，profile 为 `observer`。
按不可变发布流程从完整 main SHA 构建镜像并以精确 digest 部署；不得在云主机
同步源码或 build。首次上线顺序：建独立数据库 → 执行 schema → 配置 LM
Studio/Tailscale → 投影 observer env → 构建并部署单个模块 → 验证管理员私聊、
授权群采集、队列告警和报告。

```bash
.venv/bin/python -m pytest -q tests/observer_bot
.venv/bin/python -m pytest -q tests/ops/test_modular_images.py \
  tests/ops/test_immutable_compose.py tests/ops/test_runtime_env_contract.py
python3 scripts/doc_quality_checker.py
```

代码提交或合入不代表正式环境生效；数据库和 prod mutation 必须单独获得明确确认。
