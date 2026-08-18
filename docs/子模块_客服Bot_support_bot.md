# 子模块：独立客服 Bot

## 1. 定位与入口

`support_bot.main` 是独立 Telegram polling 入口，catalog 模块与 Compose service
均为 `support-bot`。它只使用 `SUPPORT_BOT_TOKEN`，不得与主 Bot、QQCC、
付费群审核 Bot 或其它进程共用 token。

客服 Bot 不读取生成维护标记、不提交生成任务，也不承载支付履约。它负责收集
工单；Dashboard 负责已认证管理员的查看、备注、状态处理、附件访问和回复。

## 2. 工单提交契约

用户可选择充值问题、Bug 反馈、意见反馈、商业合作四类工单；未先选择分类的
内容进入“未分类”草稿。草稿支持连续文字、图片和文件：

- 草稿只保存在当前进程内，容器异常重启会丢失未提交内容。
- 点击“结束提交”、切换分类或最后一次内容后 300 秒超时，才在一个数据库事务
  中创建工单及全部消息。
- 空草稿切换或超时不创建工单；同类按钮重复点击不重复创建草稿。
- 数据库提交失败时保留进程内草稿，用户可以重试。
- Dashboard 在事务提交前看不到草稿。

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

配置事实源为 `deploy/service-env-contract.yml`。正式环境只向
`support-bot` 与需要回复/签名附件的 Dashboard Backend 投影
`SUPPORT_BOT_TOKEN`；其它服务不得获得该 token。

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

本地测试通过不表示正式 Bot、数据库、R2 或 Dashboard 已验证。
