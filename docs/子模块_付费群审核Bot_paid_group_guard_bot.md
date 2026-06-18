# 子模块: 付费群审核 Bot (Paid Group Guard Bot)

## 1. 模块定位

`paid_group_guard_bot/` 是独立 Telegram Bot 入口，用于付费群或付费超级群的入群申请审核。它与主业务 Bot 分离：

- 使用独立 BotFather token：`PAID_GROUP_BOT_TOKEN`
- 只订阅 `chat_join_request` update
- 只处理一个目标群：`PAID_GROUP_CHAT_ID`
- 复用主项目数据库读取用户与订单资格
- 不承载 FSM、生成任务、支付回调、文件下载、菜单、私聊客服等主业务流程

稳定启动入口为：

```bash
python -m paid_group_guard_bot
```

## 2. 文件结构

| 文件 | 职责 |
| :--- | :--- |
| `paid_group_guard_bot/main.py` | 构建独立 PTB Application，注册 `ChatJoinRequestHandler`，仅 polling `chat_join_request` |
| `paid_group_guard_bot/config.py` | 读取 `PAID_GROUP_*` 环境变量，复用主项目 Telegram Local API 默认口径 |
| `paid_group_guard_bot/eligibility.py` | 付费群入群资格查询 |
| `paid_group_guard_bot/handlers.py` | 入群申请审核动作：approve / 保留待审 / decline |
| `paid_group_guard_bot/.env.example` | 无密钥示例环境变量 |
| `tests/paid_group_guard_bot/` | 资格 SQL 与审核动作 focused tests |

## 3. 资格判定口径

用户必须满足：

1. `users.telegram_id` 等于申请人的 Telegram user id。
2. 对应内部用户存在至少一条成功订单，且该订单满足以下任一条件：
   - 真实支付或有效履约订单：`orders.status = 'SUCCESS' AND orders.paid_at IS NOT NULL`
   - 后台赠送套餐订单：`orders.tx_hash LIKE 'manual_%'` 或 `orders.order_id LIKE 'GIFT:%'`

这覆盖“历史上付费过的用户”和“后台赠送过免费套餐的用户”。如果管理员只是直接手动改 `current_identity`，但没有通过后台赠送套餐接口生成订单，则不会被自动通过。

## 4. 审核行为

- 命中资格：调用 `approve_chat_join_request(...)` 自动通过。
- 未命中资格：默认保留 pending，供管理员人工确认。
- 如设置 `PAID_GROUP_DECLINE_UNQUALIFIED=true`，未命中资格时调用 `decline_chat_join_request(...)` 自动拒绝。
- 如设置 `PAID_GROUP_DRY_RUN=true`，只记录日志，不执行 approve/decline。
- 收到非目标群的 join request 会被忽略并记录 warning，防止同一个审核 Bot 误管理其它群。

## 5. 环境变量

| 变量 | 必填 | 说明 |
| :--- | :--- | :--- |
| `PAID_GROUP_BOT_TOKEN` | 是 | 独立审核 Bot token，不能复用主业务 `BOT_TOKEN` |
| `PAID_GROUP_CHAT_ID` | 是 | 目标付费群 ID，通常为 `-100...` |
| `PAID_GROUP_DECLINE_UNQUALIFIED` | 否 | 默认 `false`，不合资格时保留待审 |
| `PAID_GROUP_DRY_RUN` | 否 | 默认 `false`；联调时可设为 `true` |
| `DATABASE_URL` | 是 | 复用主项目数据库连接 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 否 | 独立 Bot 建议较小连接池 |
| `PAID_GROUP_BOT_BASE_URL` | 否 | 默认复用主项目 Telegram Local API base URL |
| `PAID_GROUP_BOT_BASE_FILE_URL` | 否 | 该 Bot 不下载文件，主要用于保持 PTB base_file_url 口径一致 |

## 6. Telegram 侧设置

1. 使用 BotFather 创建专用审核 Bot。
2. 将审核 Bot 加入私密付费群。
3. 将审核 Bot 设置为管理员，并授予邀请/审核入群请求权限。
4. 通过“需要管理员批准”的邀请链接让用户发起入群申请。

## 7. 部署边界

- 研发和联调默认先走云测试控制面；正式上线需用户明确确认。
- 该 Bot 应作为单独 compose service 部署，复用项目根 `Dockerfile`，command 使用 `python -m paid_group_guard_bot`。
- 不要把它合并到 `src/bot_main.py`，也不要让它复用主业务 `BOT_TOKEN`。
- 如果后续写入云正式 compose，必须同步更新云正式部署文档、技能说明和部署验证清单。

## 8. 验证

当前 focused tests：

```bash
pytest -q tests/paid_group_guard_bot
python -m compileall -q paid_group_guard_bot
```

上线前还需要在目标 Telegram 群做一次 dry-run join request 验证，确认 Bot 收到目标群的申请、资格查询命中预期、日志不含 token 或敏感 env。

