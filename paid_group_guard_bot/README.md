# Paid Group Guard Bot

独立的 Telegram 入群审核 Bot，只处理付费群的 `chat_join_request` 更新，不承载主业务菜单、生成任务、支付回调或用户私聊流程。

## 运行职责

- 使用独立 BotFather token：`PAID_GROUP_BOT_TOKEN`。
- 只审核一个目标群：`PAID_GROUP_CHAT_ID`。
- 复用主项目数据库连接：`DATABASE_URL`、`DB_POOL_SIZE`、`DB_MAX_OVERFLOW`。
- 默认只自动通过符合资格的用户；不符合资格的申请默认保留待人工审核。

## 入群资格口径

用户的 Telegram ID 必须存在于 `users.telegram_id`，且满足以下任一条件：

- 该内部用户存在成功真实支付订单：`orders.status = SUCCESS` 且 `orders.paid_at IS NOT NULL`。
- 该内部用户存在后台赠送套餐订单：`orders.tx_hash` 以 `manual_` 开头，或 `orders.order_id` 以 `GIFT:` 开头。
- 该内部用户的 `users.user_group` 为 `筑基期` 及以上：`筑基期`、`金丹期`、`元婴期`、`化神期`、`炼虚期`、`合体期`、`大乘期`、`渡劫期`。

这覆盖历史成功付费用户、后台赠送免费套餐用户，以及修为达到筑基期及以上的活跃用户。单纯手动改 `current_identity` 不会被自动通过。

## Telegram 侧准备

1. 用 BotFather 创建一个新的专用审核 Bot。
2. 把它拉进私密付费群。
3. 设置为管理员，并授予邀请/审核入群请求权限。
4. 使用“需要管理员批准”的邀请链接让用户申请入群。

## 本地启动

### 直接进程

```bash
export PAID_GROUP_BOT_TOKEN="<token-from-botfather>"
export PAID_GROUP_CHAT_ID="-1000000000000"
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost/bot_db"
export TELEGRAM_API_BASE_URL="http://69.63.220.115:8081"
export TELEGRAM_FILE_BASE_URL="http://69.63.220.115:8082"

python -m paid_group_guard_bot
```

### 本地容器 dry-run

本地容器复用项目根 `Dockerfile`，并走主配置里的 Telegram Local API 地址。第一次联调建议保留 `PAID_GROUP_DRY_RUN=true`，确认日志后再改为真实审核。

```bash
cp .env.paid-group.local.example .env.paid-group.local
# Edit .env.paid-group.local locally: fill PAID_GROUP_BOT_TOKEN, PAID_GROUP_CHAT_ID, DATABASE_URL.

docker-compose -f deploy/docker-compose-paid-group-local.yml build paid-group-guard-bot-local
docker-compose -f deploy/docker-compose-paid-group-local.yml up -d paid-group-guard-bot-local
docker-compose -f deploy/docker-compose-paid-group-local.yml logs -f --tail=100 paid-group-guard-bot-local
```

真实环境不要直接 source example 文件；把变量写入对应的 `.env.cloud.test` 或 `.env.cloud.prod`，并替换 token 与群 ID。

## 后续部署建议

云测试或云正式部署时，应新增单独 compose service，复用项目根 `Dockerfile`，command 使用：

```bash
python -m paid_group_guard_bot
```

不要复用主业务 Bot 的 `BOT_TOKEN`。这个 Bot 必须使用新的 `PAID_GROUP_BOT_TOKEN`，否则会与主业务 Bot 的 polling 隔离目标相冲突。
