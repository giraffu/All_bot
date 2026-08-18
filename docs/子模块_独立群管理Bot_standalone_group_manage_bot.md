# 子模块：独立群管理 Bot

## 定位

`standalone_group_manage_bot/` 是普通 Telegram 群消息治理入口。它只订阅目标群
的 `message` update，支持删除链接和违禁词消息，不注册、不接收、不处理
`chat_join_request`。它与付费群审核 Bot 使用不同 token、进程、配置、日志和
Dashboard API。

稳定入口：

```bash
python -m standalone_group_manage_bot
```

## 配置与行为

- `GROUP_MANAGE_BOT_TOKEN`：独立 Bot token，必须与其它 polling Bot 不同。
- `GROUP_MANAGE_CHAT_ID`：唯一目标群的 Telegram 数值 ID。
- `GROUP_MANAGE_MODERATION_CONFIG_FILE`：默认
  `/app/runtime/group-manage/config.json`。
- `GROUP_MANAGE_MODERATION_LOG_FILE`：默认
  `/app/logs/group_manage_moderation.jsonl`。
- 配置包含 `enabled`、`dry_run`、`block_links`、`allowed_domains`、
  `forbidden_words`、`exempt_user_ids`；保存采用原子替换，Bot 按 mtime 热加载，
  下一条消息生效。
- 管理员和豁免用户不删除；管理员身份查询失败时 fail-open。
- BotFather group privacy 必须 Disabled，群管理员权限必须包含删除消息。

## Dashboard

独立 Tab“群管理Bot”使用以下 API，不与“群审核Bot”混用：

- `GET /api/group-manage/config`
- `PUT /api/group-manage/config`
- `GET /api/group-manage/logs`

Dashboard Backend 与 `group-manage-bot` 只共享宿主目录
`runtime/group-manage`；日志共享宿主 `logs` 目录。

## 发布

正式模块名为 `group-manage-bot`，Compose service 同名，profile 为
`group-manage`。代码和 Compose 变化分别通过精确 main SHA 构建
`group-manage-bot`、`dashboard-backend`、`dashboard-frontend` 与
`compose-contract`，再按精确 digest 逐模块部署 prod。Token 只进入正式
config contract/环境投影，不写入 Git。

最小验证：

```bash
pytest -q tests/standalone_group_manage_bot tests/dashboard/test_group_manage_admin_service.py
npm --prefix dashboard/frontend run typecheck
python3 scripts/doc_quality_checker.py
```
