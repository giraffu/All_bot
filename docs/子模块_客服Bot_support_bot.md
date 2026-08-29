# 子模块：独立客服 Bot

## 1. 定位与入口

`support_bot.main` 是独立 Telegram polling 入口，catalog 模块与 Compose service
均为 `support-bot`。它使用 `SUPPORT_BOT_TOKEN` 轮询并服务工单用户；管理员通知
只使用 `OBSERVER_BOT_TOKEN` 对应的 `@qq_notification_bot` 做 outbound
`sendMessage`。`support-bot` 不用通知 token 调用 `getUpdates`，通知 token 的唯一
polling owner 仍是 `observer-bot`。主 Bot、QQCC 和付费群审核 Bot 不参与这条链路。

客服 Bot 不读取生成维护标记、不提交生成任务，也不承载支付履约。它负责收集
工单；Dashboard 负责已认证管理员的查看、备注、状态处理、附件访问和回复。

Dashboard 的独立“通知中心 → 通知设置”允许管理员配置最多 20 个 Telegram 数字
用户 ID。接收者必须先私聊并启动 `@qq_notification_bot`；Telegram Bot 不能仅凭普通用户
的 `@username` 主动发起私聊。留空保存会关闭全部新工单通知。

## 2. 工单提交契约

用户可选择充值问题、Bug 反馈、意见反馈、商业合作四类工单；未先选择分类的
内容进入“未分类”草稿。草稿支持连续文字、图片和文件：

- 草稿只保存在当前进程内，容器异常重启会丢失未提交内容。
- 点击“结束提交”、切换分类或最后一次内容后 300 秒超时，才在一个数据库事务
  中创建工单、全部消息，以及当时每位已配置接收者各自的 outbox 投递任务。
- 空草稿切换或超时不创建工单；同类按钮重复点击不重复创建草稿。
- 数据库提交失败时保留进程内草稿，用户可以重试。
- Dashboard 在事务提交前看不到草稿。
- 通知文本在事务中形成不可变快照，包含工单元数据、用户逐段提交的文字和附件
  文件名；超长内容在 Telegram 单消息上限前截断，并引导管理员到 Dashboard 查看
  完整工单。接收者列表同样按提交时配置快照，不因稍后改配置而改变已排队任务。
- 用户提交成功后不等待 Telegram。客服 Bot 内的有界异步 dispatcher 每 5 秒用
  `FOR UPDATE SKIP LOCKED` 短事务领取一批任务，事务外通过
  `@qq_notification_bot` 投递，再用短事务记录结果；单个接收者失败不阻塞其他人。
- 临时网络错误和 Telegram `RetryAfter` 使用有上限的退避并最多尝试 8 次；
  `BadRequest`/`Forbidden` 直接进入失败终态。领取租约过期后可由同一或新实例恢复，
  因此容器重启不丢任务。投递语义为 at-least-once：极少数“Telegram 已接收、成功
  回写前进程退出”的窗口可能产生重复通知，优先保证通知不静默丢失。

分类枚举与展示格式以 `support_bot/main.py`、support ticket service 和
Dashboard tests 为事实源。未知历史分类必须显示原始值，不能产生空标题。

## 3. 附件与权限

图片和文件通过当前 Bot 的 Telegram file base 下载，再上传到私有对象存储的
`support/<telegram-user-id>/<message-id>/...` key。约束如下：

- 超过入口上限的附件在下载前拒绝；下载与上传失败不能回复“已记录”。
- 数据库只保存私有 object key 和必要 metadata，不保存公开 URL。
- 只有已认证 Dashboard 可生成短时访问链接。
- 图片可预览，其他文件提供下载；日志、工单和发布状态不得包含 token、R2
  secret 或预签名 URL。

配置事实源为 `deploy/service-env-contract.yml`。正式环境只向 `support-bot` 与需要
回复/签名附件的 Dashboard Backend 投影 `SUPPORT_BOT_TOKEN`；其它服务不得获得
该 token。`OBSERVER_BOT_TOKEN` 额外投影给 `support-bot` 只提供管理员通知的 outbound
能力，不授予 Observer 数据库或 handler；启动时必须验证两个 token 不同且 outbound
身份正是 `@qq_notification_bot`，否则 fail closed。

通知配置 API 为已认证的
`GET/PUT /api/support-tickets/notification-settings`，持久化事实源是数据库表
`support_notification_recipients`，不是 env、运行时内存或 Git 配置。Dashboard
Backend 只管理接收者 ID；通知任务由 `support-bot` 创建和投递，Telegram 发送身份
统一为 `@qq_notification_bot`。

持久事实源位于主数据库：

- `support_notification_outbox`：每个工单、每个接收者一行，保存 payload 快照、
  当前状态、尝试次数、下一次投递时间、租约和最终结果；唯一键防止重复入队。
- `support_notification_attempts`：每次领取即创建记录，保存 processing、retry、
  sent、failed 或租约失效 abandoned 结果以及 Telegram message ID/有限错误信息。

前端不再在客服工单页面内嵌通知弹窗；统一通过“通知中心”调用聚合接口
`GET/PUT /api/notification-center/settings`。旧 support notification API 保留为
后端兼容入口，持久化位置和发送者均不改变。

## 4. 发布与迁移

`deploy/module-catalog.json` 当前把 `support-bot` 声明为 prod-only 独立
模块。Dashboard Backend、Dashboard Frontend 和客服 Bot 不再作为一个
`support-platform` 组合发布；需要同时更新时也必须分别构建、部署和保存状态。

```bash
python3 scripts/release.py build \
  --module support-bot --sha <40位main-sha>

python3 scripts/release.py deploy \
  --env prod --module support-bot \
  --artifact <repository@sha256:digest> --confirm-prod
```

以上 prod 命令只有在用户明确授权正式 mutation 后才能执行。schema 变化使用
独立 `database-migration` 模块；先备份并核对单 Alembic head、目标 migration
和 downgrade 风险，不能把历史 migration 编号当作当前部署入口。

## 5. 最小验证

```bash
.venv/bin/python -m pytest -q tests/support_bot \
  tests/services/test_support_ticket_submission_service.py \
  tests/database/test_support_ticket_schema.py \
  tests/ops/test_runtime_env_contract.py
python3 scripts/doc_quality_checker.py
```

行为验收至少覆盖：

- 分类、未分类、切换分类、空草稿和 300 秒超时。
- 重复结束、数据库失败重试和单事务可见性。
- 附件大小门禁、Local API 下载、私有 R2 上传失败与短时访问链接。
- token 只投影到允许的服务，多个 polling Bot 不共用 token。
- 独立 `support-bot` exact-digest 发布不会替换 Dashboard 或其它正式容器。
- 通知接收者保存去重、空列表关闭、无效 ID 拒绝、最多 20 人。
- 工单、消息和每接收者 outbox 原子提交；用户成功响应不等待 Telegram。
- 通知包含全部文字与附件名；接收者局部失败不阻塞其余接收者；重启后租约恢复、
  有界重试、永久错误终止和每次尝试记录均保持可审计。
- 客服 token 只 polling 客服更新，通知 token 只由 Observer polling，客服进程仅用
  后者发送且启动时校验 `@qq_notification_bot` 身份。

本地测试通过不表示正式 Bot、数据库、R2 或 Dashboard 已验证。
