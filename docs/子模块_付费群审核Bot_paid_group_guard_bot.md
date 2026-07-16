# 子模块: 付费群审核 Bot (Paid Group Guard Bot)

## 1. 模块定位

`paid_group_guard_bot/` 是独立 Telegram Bot 入口，用于付费群或付费超级群的入群申请审核。它与主业务 Bot 分离：

- 使用独立 BotFather token：`PAID_GROUP_BOT_TOKEN`
- 订阅 `chat_join_request` 与目标群普通 `message` update
- 只处理一个目标群：`PAID_GROUP_CHAT_ID`
- 复用主项目数据库读取用户与订单资格
- 可做轻量群管理：删除非管理员链接、删除违禁词消息、写结构化审核日志
- 不承载 FSM、生成任务、支付回调、文件下载、菜单、私聊客服等主业务流程

稳定启动入口为：

```bash
python -m paid_group_guard_bot
```

## 2. 文件结构

| 文件 | 职责 |
| :--- | :--- |
| `paid_group_guard_bot/main.py` | 构建独立 PTB Application，注册入群申请与群消息审核 handler |
| `paid_group_guard_bot/config.py` | 读取 `PAID_GROUP_*` 环境变量，复用主项目 Telegram Local API 默认口径 |
| `paid_group_guard_bot/eligibility.py` | 付费群入群资格查询 |
| `paid_group_guard_bot/handlers.py` | 入群申请审核动作：approve / 保留待审 / decline |
| `paid_group_guard_bot/moderation.py` | 群管理配置、链接/违禁词判断、结构化日志写入 |
| `paid_group_guard_bot/moderation_handlers.py` | 目标群普通消息审核动作：管理员豁免 / dry-run / delete |
| `paid_group_guard_bot/.env.example` | 无密钥示例环境变量 |
| `.env.paid-group.local.example` | 本地容器 dry-run 环境变量模板 |
| `deploy/docker-compose-paid-group-local.yml` | 本地容器化运行入口，复用项目根 `Dockerfile` |
| `tests/paid_group_guard_bot/` | 资格 SQL、入群审核与群消息审核 focused tests |

## 3. 资格判定口径

用户必须满足：

1. `users.telegram_id` 等于申请人的 Telegram user id。
2. 对应内部用户满足以下任一准入条件：
   - 真实支付或有效履约订单：存在 `orders.status = 'SUCCESS' AND orders.paid_at IS NOT NULL`
   - 后台赠送套餐订单：存在 `orders.status = 'SUCCESS'` 且 `orders.tx_hash LIKE 'manual_%'` 或 `orders.order_id LIKE 'GIFT:%'`
   - 修为门槛：`users.user_group` 为 `筑基期` 及以上，即 `筑基期`、`金丹期`、`元婴期`、`化神期`、`炼虚期`、`合体期`、`大乘期`、`渡劫期`

这覆盖“历史上付费过的用户”、“后台赠送过免费套餐的用户”和“修为达到筑基期及以上的用户”。该路径仍然只读，不写入订单、身份、灵石或日志；如果管理员只是直接手动改 `current_identity`，不会因此自动通过。

## 4. 审核行为

- 命中资格：调用 `approve_chat_join_request(...)` 自动通过。
- 未命中资格：默认保留 pending，供管理员人工确认。
- 如设置 `PAID_GROUP_DECLINE_UNQUALIFIED=true`，未命中资格时调用 `decline_chat_join_request(...)` 自动拒绝。
- 如设置 `PAID_GROUP_DRY_RUN=true`，只记录日志，不执行 approve/decline。
- 收到非目标群的 join request 会被忽略并记录 warning，防止同一个审核 Bot 误管理其它群。

## 5. 群管理行为

- 只审核 `PAID_GROUP_CHAT_ID` 对应目标群的普通消息。
- 管理员、群主和 `exempt_user_ids` 配置中的用户永远豁免。
- 管理员状态查询失败时 fail-open：不删除消息，只写 warning，避免 Telegram API 短暂异常导致误删。
- `block_links=true` 时，非管理员发送普通 URL、`www.`、`t.me/...`、Telegram `url/text_link` entity 会被删除；`allowed_domains` 命中的域名及其子域名会放行。
- `forbidden_words` 使用简单包含匹配；中文原样匹配，英文大小写不敏感，v1 不支持正则。
- 配置文件按 mtime 热加载，Dashboard 保存后下一条消息自动使用新规则。
- 结构化删除日志写入 JSONL：`timestamp/chat_id/message_id/user_id/username/full_name/reason/matched_value/text_snippet/action/error`。`text_snippet` 只保留短片段，不保存完整原文。
- BotFather 必须将该 Bot 的 group privacy 设为 Disabled，且群内管理员权限必须包含删除消息。

默认共享路径：

```text
/app/runtime/paid-group-guard/config.json
/app/logs/paid_group_moderation.jsonl
```

默认配置语义：

```json
{
  "enabled": true,
  "dry_run": false,
  "block_links": true,
  "allowed_domains": [],
  "forbidden_words": [],
  "exempt_user_ids": []
}
```

## 6. 环境变量

| 变量 | 必填 | 说明 |
| :--- | :--- | :--- |
| `PAID_GROUP_BOT_TOKEN` | 是 | 独立审核 Bot token，不能复用主业务 `BOT_TOKEN` |
| `PAID_GROUP_CHAT_ID` | 是 | 目标付费群 ID，通常为 `-100...` |
| `PAID_GROUP_DECLINE_UNQUALIFIED` | 否 | 默认 `false`，不合资格时保留待审 |
| `PAID_GROUP_DRY_RUN` | 否 | 默认 `false`；联调时可设为 `true` |
| `PAID_GROUP_MODERATION_ENABLED` | 否 | 默认 `true`，启用目标群普通消息审核 |
| `PAID_GROUP_MODERATION_DRY_RUN` | 否 | 默认 `false`；联调时可设为 `true` |
| `PAID_GROUP_BLOCK_LINKS` | 否 | 默认 `true`，删除非管理员链接 |
| `PAID_GROUP_MODERATION_CONFIG_FILE` | 否 | 群管理配置 JSON 路径 |
| `PAID_GROUP_MODERATION_LOG_FILE` | 否 | 群管理 JSONL 日志路径 |
| `DATABASE_URL` | 是 | 复用主项目数据库连接 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 否 | 独立 Bot 建议较小连接池 |
| `PAID_GROUP_BOT_BASE_URL` | 否 | 默认复用主项目 Telegram Local API base URL |
| `PAID_GROUP_BOT_BASE_FILE_URL` | 否 | 该 Bot 不下载文件，主要用于保持 PTB base_file_url 口径一致 |
| `TELEGRAM_API_BASE_URL` | 否 | 主项目 Telegram Local API base URL；未设置 `PAID_GROUP_BOT_BASE_URL` 时会自动补 `/bot` |
| `TELEGRAM_FILE_BASE_URL` | 否 | 主项目 Telegram Local API file base URL |

## 7. Dashboard 管理入口

Dashboard 新增“群审核Bot”tab：

- `GET /api/paid-group-guard/config`：读取当前共享配置。
- `PUT /api/paid-group-guard/config`：保存配置，使用原子写文件。
- `GET /api/paid-group-guard/logs`：分页查看 JSONL 删除日志，支持 `reason/user_id/start_date/end_date` 过滤。

该入口只读写共享文件，不写正式数据库，也不需要 Alembic 迁移。

## 8. 本地容器化 dry-run

本地联调入口为：

```bash
cp .env.paid-group.local.example .env.paid-group.local
# 在 .env.paid-group.local 中填入真实 PAID_GROUP_BOT_TOKEN、PAID_GROUP_CHAT_ID、DATABASE_URL
docker-compose -f deploy/docker-compose-paid-group-local.yml build paid-group-guard-bot-local
docker-compose -f deploy/docker-compose-paid-group-local.yml up -d paid-group-guard-bot-local
docker-compose -f deploy/docker-compose-paid-group-local.yml logs -f --tail=100 paid-group-guard-bot-local
```

本地 compose 使用 `network_mode: host`，并默认通过 `TELEGRAM_API_BASE_URL=http://69.63.220.115:8081` 复用主项目 Telegram Local API 口径；`PAID_GROUP_BOT_BASE_URL` 留空时会自动派生为 `http://69.63.220.115:8081/bot`。第一次联调应保持 `PAID_GROUP_DRY_RUN=true`，只观察入群申请日志，不执行 approve/decline。

## 9. Telegram 侧设置

1. 使用 BotFather 创建专用审核 Bot。
2. 将审核 Bot 加入私密付费群。
3. 将审核 Bot 设置为管理员，并授予邀请/审核入群请求权限。
4. 通过“需要管理员批准”的邀请链接让用户发起入群申请。
5. 如启用群消息审核，BotFather `/setprivacy` 需选择该 Bot 并设为 `Disable`，群管理员权限需包含删除消息。

## 10. 部署边界

- 研发和联调默认先走云测试控制面；正式上线需用户明确确认。
- 该 Bot 应作为单独 compose service 部署，复用项目根 `Dockerfile`，command 使用 `python -m paid_group_guard_bot`。
- 不要把它合并到 `src/bot_main.py`，也不要让它复用主业务 `BOT_TOKEN`。
- 云正式 service 为 `paid-group-guard-bot-prod`，容器名 `cloud-paid-group-guard-bot-prod`。它与 Dashboard Backend 共享 `runtime/cloud-prod/paid-group-guard` 和 `logs/cloud-prod`。
- 单独发布该 Bot 与 Dashboard 管理页时，使用同一已验收 main SHA 的 `scripts/release.py plan|preflight|deploy --env prod --track control-plane --modules dashboard-backend dashboard-frontend paid-group-guard-bot`；模块参数只能扩大 planner 自动集合，真实执行仍须 `--execute --confirm-prod`。维护模式按本次正式发布独立选择，默认开启；只有用户当次明确要求且 planner 允许无维护时才关闭。禁止调用已 fail-closed 的 legacy 脚本、rsync、现场 build 或手工 compose。

## 11. 验证

当前 focused tests：

```bash
pytest -q tests/paid_group_guard_bot tests/dashboard
python -m compileall -q paid_group_guard_bot dashboard/backend
```

上线前还需要在目标 Telegram 群做一次 join request 与非管理员链接消息验证，确认 Bot 收到目标群申请、资格查询命中预期、链接删除生效、Dashboard 日志可见且日志不含 token 或敏感 env。
