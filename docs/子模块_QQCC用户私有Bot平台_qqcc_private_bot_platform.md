# 子模块: QQCC 用户私有 Bot 平台 (QQCC Private Bot Platform)

## 1. 定位与稳定业务规则

QQCC 用户私有 Bot 平台允许已注册 AllBot 用户把一个全新的 Telegram Bot 接入懒人 Bot 功能。申请不收费、不审核，token 通过 Telegram `getMe` / `getWebhookInfo` 验证后立即创建绑定并注册 webhook。

长期不变量：

- 一个 `owner_user_id` 只能有一条有效私有 Bot 绑定，一个 `telegram_bot_id` 也只能属于一个 owner；数据库唯一约束和事务锁共同兜底并发申请。
- 私有 Bot 可以被其他 Telegram 用户公开使用。实际操作者仍按自己的 AllBot 用户、余额、会员与并发权限扣费，owner 不替访客付费。
- 首次创建复制当时官方 QQCC 的完整配置，之后配置版本、提示词、模型、菜单、场景和示范媒体独立演进；私有 Bot 内不展示再次申请“私有bot”的入口。
- owner 可以保存配置、暂停、恢复、重试接入和轮换同一 `telegram_bot_id` 的 token。绑定另一个 Bot 前必须由管理员永久解绑。
- 管理员可以查看 owner、Bot 身份、运行状态、脱敏错误、审计和完整配置，并可禁用、恢复、永久解绑；任何 API、页面、日志或审计 metadata 都不得返回 token 明文。
- 管理员禁用优先于 owner 状态。重新发 token、owner 暂停/恢复或 webhook 重试都不能清除 `admin_enabled=false`。
- 暂停或禁用只拒绝新 update/新任务；已经扣费并进入执行面的任务继续完成和投递，不主动取消或退款。

## 2. 申请、凭据与状态模型

官方 QQCC 主菜单的 `私有bot` 入口注册独立 token FSM。管理后台“主菜单”的 `main_buttons.private_bot` 默认开启，只控制官方 QQCC 的申请/管理入口；它与 `PRIVATE_QQCC_BOT_ENABLED` 总 gate 叠加，但不会停止 private worker 或禁用既有私有 Bot。开关关闭后新菜单隐藏入口，旧键盘点击回复 `功能暂未开放`；若用户已经停留在 token 步骤，收到消息后仍先尽力删除 token，再拒绝创建并结束会话。首次进入会说明通过 `@BotFather` 执行 `/newbot` 的步骤，并要求使用未接入其它系统的新 Bot。收到 token 后先尽力删除用户原消息；禁止回显 token、把 token 写入日志、异常、审计 `details` 或监控标签。

凭据与身份校验：

- 调用 `getMe` 和 `getWebhookInfo`，拒绝无效 token、官方主 Bot/QQCC/测试/付费群 Bot、已被绑定的 Bot，以及首次绑定时已有 webhook 的 Bot。
- token 使用版本化 AES-256-GCM 加密保存，`webhook_public_id` 作为 associated data；token 指纹使用独立 32-byte HMAC key，数据库只保存 ciphertext、key version 和指纹。
- Webhook secret 只在注册 Telegram webhook 时使用；数据库保存 SHA-256 hash，不保存 secret 明文。管理视图只展示 Telegram Bot ID、username 和脱敏指纹尾段。
- 同一 `telegram_bot_id` 的新 token 即使仍有已扣费或 active task 也可以救援轮换，避免旧 token 被 BotFather 撤销后 owner 永久无法恢复结果投递。轮换会在 admission fence 内先把实例切到 `provisioning`，worker 看到 token 指纹变化后关闭旧 Application 并用新凭据重建；不同 Bot ID 不视为轮换，必须由管理员永久解绑后才能重新申请。永久解绑本身仍会在存在 active task 时返回冲突，不能借解绑截断已扣费任务。

`private_qqcc_bots` 保存 owner/Bot 唯一身份、加密凭据、独立配置及版本、webhook public ID/secret hash、`owner_enabled`、`admin_enabled`、运行状态、脱敏错误和健康时间戳。`private_qqcc_bot_audit_logs` 保存 owner/admin/system 的创建、配置、状态、轮换和异常事件。运行状态只能是：

- `provisioning`：记录已建立，正在注册 webhook。
- `active`：owner 与 admin 均启用且 webhook 已注册。
- `paused`：owner 主动暂停。
- `disabled`：管理员强制禁用，优先级最高。
- `error`：Telegram webhook 注册失败或运行异常；保留同一记录供重试，不重复创建绑定。

## 3. Webhook 与多租户运行时

官方 QQCC Bot 继续使用单实例 long polling。私有 Bot 只使用 Telegram HTTPS webhook；[Telegram Bot API](https://core.telegram.org/bots/api) 明确要求标准 Bot API 请求使用 HTTPS，并规定 `getUpdates` 与 webhook 两种更新方式互斥。入口为：

```text
POST /api/private-bots/webhook/{public_id}
```

Web API 按 `public_id` 读取私有 Bot，常量时间校验 `X-Telegram-Bot-Api-Secret-Token` 的 hash，并在入队前校验 `owner_enabled`、`admin_enabled` 和 `runtime_status=active`。update 必须是 JSON object 且含正整数 `update_id`。

Redis Lua 在一个原子脚本内按 `(private_bot_id, update_id)` 做 24 小时去重，并写入 `${REDIS_PREFIX}private_qqcc_bot:webhook:updates` stream；重复 update 返回 2xx，Redis 无法可靠接收时返回 503，让 Telegram 重试。更新 JSON 不进入应用日志。

独立进程入口为：

```text
python -m qqcc_private_bot.worker
```

worker 通过 consumer group 消费 stream，按私有 Bot ID 装配共享 QQCC Application factory：

- 注入该租户的配置加载器、`private_bot_id` 和 `client_type=bot:qqcc-private:<private_bot_id>`。
- 私有 Bot 之间允许并发；同一 Bot 的 update 保持顺序处理。
- Application 不启动 polling，不注册私有 Bot 申请入口，也不能在单实例 shutdown 时关闭进程共享 Redis。
- 进程重启只恢复 `bot:qqcc-private:<id>` 完全匹配的 active task；官方 `bot:qqcc`、主 Bot和其它私有 Bot 不得互相恢复或发送结果。

频道会员资格不能用各租户 Bot 身份查询。private worker 按 `BOT_TYPE` 只在进程内创建一个官方 QQCC membership checker：正式读取 `QQCC_BOT_TOKEN`，测试读取 `QQCC_BOT_TOKEN_TEST`，只调用官方 Bot 的频道成员查询，不启动 `getUpdates`、polling 或任何官方 QQCC handler。租户 Application 只拿到 checker callable，拿不到官方 token/Bot 对象；进程内对同一 Telegram 用户 singleflight，Redis 在租户间共享缓存，正向结果缓存 60 秒、负向结果缓存 5 秒。

单任务提交会把私有 Bot 的结果展示 contract 写入 active registry 的 `_bot_task_recovery`，包括是否发送结果、用户可见 task type/prompt、结果输入索引、QQCC 重生成 metadata、完成文案和语言。worker 重启恢复最终任务时按该 contract 投递，不能把内部换脸或后处理任务误当成最终功能发送。缺少 contract 的旧私有任务按 fail-closed 处理。

`private_bot_task_submissions` 是私有 Bot 单任务的持久幂等与补偿账本。它在任何并发资源获取前落盘 submission owner/deadline/fence，以确定性 registry/dispatch ID 区分实际 backend ID；Central 同 ID 同指纹只返回既有任务，指纹冲突才返回 409。扣费日志与 `debit_confirmed_at` 在同一数据库事务内写入；orphan sweep 已封闭的 submission 会使迟到扣费整个回滚。退款统一使用 `task_refund:task:<registry_task_id>`，并发所有权使用 TaskRegistry 持久的 `concurrency_acquisition_key`；终态收口会按该字段存在/缺失自动区分新 keyed release 与升级前旧任务的一次 legacy DECR，不要求发布前人工 drain 旧任务。

账本清理默认保留 90 天，可用 `PRIVATE_QQCC_BOT_SUBMISSION_RETENTION_DAYS` 调整但不得低于 30 天。每轮最多删除 200 条，且只删除超期的 `submitted + not_required` 或 `failed + completed` 终态记录，必须排除当前 TaskRegistry 仍活跃的 ID；`reserved` / `dispatching` / pending/processing compensation 永远不得被 retention 删除。该清理不删除独立的管理审计表和用户 History。

私有 QQCC 多阶段链由 `src/services/private_qqcc_continuation_service.py` 使用 Redis durable checkpoint 编排，已覆盖多步 `draw -> draw/filter`、`original_face_swap_enabled` 内部换脸和 AI动图尾帧链。新建原脸恢复 stage 固定写 `task_type=face_swap_v2`；恢复升级前 checkpoint 时，仅在该 continuation 内把原脸恢复 stage 的旧 `face_swap` 归一为 V2，不能改变官方/私有快速换脸的 V1 路由。用户原始图片必须先上传持久存储，再创建包含完整 JSON stage plan、租户/update、确定性 submission sequence/registry ID、当前输入输出和 `ready|running|delivery_pending|completed|failed` 状态的 checkpoint。任务结果必须先 CAS 写入 checkpoint，中间阶段才能清理 registry 并进入下一步；checkpoint 写入失败时保留 active registry 与用户锁等待恢复。阶段失败只能在 checkpoint 仍是同一 stage/registry/executor token 的 `running` 状态时 CAS 写入，不得覆盖已推进的 ready/delivery/completed 状态。最终可见阶段先进入 `delivery_pending`，由持有续跑租约的 owner 发送 Telegram 媒体，成功后再 CAS 标记 delivered；Telegram 没有投递幂等键，仅保留 send 成功到 delivered CAS 之间的最小重复窗口。

当前 worker 为每个 `private_bot_id` 建一个有界 `asyncio.Queue` 并串行消费，通过全局 semaphore 控制 Bot 间并发。默认全局最多保留 64 个 inflight update、每个 Bot 最多预取 8 个 update、内存只额外保存最多 1024 个 deferred stream message ID；update body 继续留在 Redis stream/PEL，需要恢复时按 ID 用 `XRANGE` 取回。单 Bot 队列已满后，其后续 ID 必须按原顺序进入该 Bot 的 deferred deque，不能让较新的 `>` update 越过旧 pending；到达全局或 deferred 上限时停止继续 `XREADGROUP`，由 Redis 承担持久背压，不能扩张无界内存队列。

worker 启动先用持久 cursor `XAUTOCLAIM(min_idle_time=0)` 完整追平前任 consumer 的 PEL；在 startup catch-up barrier 完成前不得读取新的 `>` 消息，容量不足时保留 cursor 等待释放后继续。inflight message ID 去重还必须防止长处理 update 被周期 `XAUTOCLAIM` 重复排入同一 Bot。Application 懒加载后缓存；token 指纹变化时先关闭旧实例再重建，进程优雅退出时关闭全部实例。pending sweeper 周期扫描 webhook pending、active registry 和 continuation checkpoint，即使 TaskRegistry 为空也会续跑 ready/delivery 阶段；租约丢失会取消旧执行 owner，running orphan 只在旧续跑锁失效后 rewind。暂停/管理员禁用阻止新 update，但 recovery Application 可为已扣费链路继续后续阶段和结果投递；inactive update 遇到仍有付费 monitor/continuation 的 `bg_tasks` 时不得 stop/shutdown Application，必须等后台任务结束后再由 idle eviction 回收。永久解绑后停止。

私有 webhook update 只有在 handler 及其持久化后台提交均成功后才能 ACK。全局错误处理器自身若连用户提示也发送失败，必须先把当前 private admission scope 标记为 failed 再抛出，让 stream entry 保留待重试。通用 `clean_zombies()`（包括无 `client_type` 的手工入口）必须无条件跳过 `bot:qqcc-private:<id>`；私有任务只能通过 submission ledger、monitor lease 和租户 Application 感知的 `clean_private_qqcc_zombies()` 收口，不能落回通用退款/并发释放路径。

stream/group 运行契约：

- `PRIVATE_QQCC_BOT_WORKER_CONSUMER_GROUP`：测试默认 `private-qqcc-bot-workers-test`，正式默认 `private-qqcc-bot-workers`。
- `PRIVATE_QQCC_BOT_WORKER_CONSUMER_NAME`：可选；缺省由 hostname 与 pid 生成，水平扩展实例必须不同名。
- `PRIVATE_QQCC_BOT_WORKER_CONCURRENCY=16`、`PRIVATE_QQCC_BOT_WORKER_BATCH_SIZE=50`、`PRIVATE_QQCC_BOT_WORKER_BLOCK_MS=1000`、`PRIVATE_QQCC_BOT_WORKER_PENDING_IDLE_MS=60000`、`PRIVATE_QQCC_BOT_WORKER_RETRY_SECONDS=1` 是当前默认调优值。
- `PRIVATE_QQCC_BOT_WORKER_MAX_INFLIGHT_UPDATES=64`、`PRIVATE_QQCC_BOT_WORKER_PER_BOT_PREFETCH=8`、`PRIVATE_QQCC_BOT_WORKER_MAX_DEFERRED_UPDATES=1024` 是内存背压上限；只能按 Redis/进程内存和顺序回归结果调优，不能用放大值掩盖 stream 堆积。
- `PRIVATE_QQCC_BOT_METRICS_PUBLISH_SECONDS=15` 控制 worker heartbeat 发布频率；heartbeat Redis TTL 为 90 秒。

Webhook Lua 累计 `webhook_enqueued_total`、`webhook_duplicates_total` 和延迟回写的 `webhook_queue_errors_total`。worker heartbeat 发布 active Application、inflight/max/deferred、处理失败、DLQ 和恢复失败；管理员只读接口 `GET /api/private-bots/admin/metrics` 同时返回 stream `XLEN`、consumer group pending、counters、worker heartbeat 与 freshness。指标不可使用 token、username、update JSON 或其它高基数敏感标签。

## 4. Owner WebApp 与管理员后台

官方 QQCC Bot 生成 256-bit 随机一次性 ticket；Redis 只保存 ticket SHA-256 对应的 owner ID，5 分钟过期并通过 `GETDEL` 单次兑换。兑换后签发 audience/scope 固定、12 小时有效的 owner JWT，不复用主 Web 修为等级门禁。

Owner API：

- `POST /api/private-bots/owner/auth/exchange`
- `GET /api/private-bots/owner/me`
- `PUT /api/private-bots/owner/config`
- `POST /api/private-bots/owner/pause`
- `POST /api/private-bots/owner/resume`
- `POST /api/private-bots/owner/retry`
- `PUT /api/private-bots/owner/credentials`
- `POST /api/private-bots/owner/demo-media/{kind}/{scene_id}/{slot}`

配置保存必须携带 `config_version`，并发旧版本返回 409。私有示范媒体对象键限定在 `qqcc/private/<private_bot_id>/demo/...`，不能引用官方或其它租户对象。

管理员 API 继续挂在受 `QQCC_CONFIG_*` 身份验证和 Cloudflare Access 保护的 QQCC Config Backend，提供分页搜索、详情、禁用、恢复和永久解绑，不提供审核/批准/拒绝。管理员永久解绑先删除 webhook，再删除绑定/凭据和该租户示范媒体引用；用户生成 History 不删除。

管理员运行指标入口为 `GET /api/private-bots/admin/metrics`，继续使用 QQCC Config 管理员 JWT，不能暴露到 owner Host。

同一 QQCC Config 前端镜像承载两个 Host：

- `PRIVATE_QQCC_BOT_OWNER_HOST`：公开 owner WebApp，只允许 owner 页面及 `/api/private-bots/owner/**`；其它 `/api/**` 按 Host 返回 404。
- `QQCC_CONFIG_ADMIN_HOST`：管理员页面 Host，必须继续由 Cloudflare Access 管理员 allowlist 保护。
- 其它未知 Host：Nginx `default_server` 无条件返回 404，不能回落到管理员 SPA/API。Cloudflare Tunnel 即使从 `127.0.0.1` 回源，安全边界也必须依赖 Host 路由和应用认证，不能只依赖源 IP allowlist。

Owner origin 还按路径限制请求体：ticket exchange 与 credentials 为 4 KiB，config 为 1 MiB，普通 owner API 为 4 KiB，只有 `demo-media` 为匹配后端 50 MiB 视频上限而放行 55 MiB。不得把 owner server 全局 body limit 直接放大到媒体上限。

`/api/private-bots/owner/auth/exchange` 使用独立 Nginx limiter（`50r/s`、`burst=500`、`nodelay`），不复用管理员登录的 `2r/s` / `burst=5` 窄桶；这是因为 cloudflared 可能把大量 Telegram WebView 用户汇聚到同一 origin 地址，一次性 256-bit ticket 与 Redis `GETDEL` 仍是兑换权威。owner CSP 的 `connect-src` 只允许 `'self'`，图片/媒体才允许受控 HTTPS；Nginx Host 路由之外，QQCC Config Backend 也会再次按 owner/admin Host 对相反路径返回 404。

owner public hostname 是否存在必须以 Cloudflare 运行态为准。2026-07-12 已创建 `private-bot.aivison.it.com` proxied CNAME，并插入现有 `allbot-admin-dashboard-prod` Tunnel 的 catch-all 404 前；owner Host 不创建 Access app，原 `qqcc-admin` Access policy 保持不变。后续 Cloudflare 变更仍必须单独取得生产发布确认。

## 5. 环境变量契约

以下值只能写入 ignored 的环境文件或受控 secret store，不能进入 Git、文档、聊天、compose 渲染输出或日志：

| 变量 | 消费者 | 约束 |
| :--- | :--- | :--- |
| `PRIVATE_QQCC_BOT_ENABLED` | 官方 QQCC、Web API、QQCC Config Backend、private worker/发布校验 | 总发布闸门；缺失/`false` 时隐藏或拒绝私有入口且 worker 拒绝启动；2026-07-12 云正式为 `true` |
| `PRIVATE_QQCC_BOT_TOKEN_KEYRING` | 官方 QQCC、QQCC Config Backend、private worker | JSON object；key 是整数版本，value 是 URL-safe Base64 编码的 32-byte AES key |
| `PRIVATE_QQCC_BOT_TOKEN_ACTIVE_KEY_VERSION` | 同上 | 必须存在于 keyring；轮换时先保留旧 key 解密能力，再切 active version |
| `PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY` | 官方 QQCC、QQCC Config Backend | URL-safe Base64 编码的独立 32-byte HMAC key；不得复用 AES/JWT secret |
| `PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS` | 官方 QQCC、QQCC Config Backend | 逗号或空白分隔的正整数 Bot ID；必须显式覆盖主 Bot、QQCC、测试和付费群等所有官方 Bot，缺失/非法时申请 fail closed |
| `PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL` | 官方 QQCC、QQCC Config Backend、private worker | 默认/推荐 `https://api.telegram.org`；必须是 HTTPS，严禁继承现有公网明文 Local Bot API URL |
| `PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL` | private worker | 默认/推荐 `https://api.telegram.org/file/bot`；必须与 API base 使用同一受信传输边界 |
| `PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS` | 同上 | 仅自建 TLS/mTLS/Tailscale HTTPS Bot API 时填写允许 host；不能用来放行任意 HTTP endpoint |
| `PRIVATE_QQCC_BOT_OWNER_JWT_SECRET` | QQCC Config Backend | 独立的 URL-safe Base64 32-byte key；不得复用 AES keyring、fingerprint、`QQCC_CONFIG_SECRET_KEY`、`JWT_SECRET_KEY` 或 Dashboard secret |
| `PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL` | 官方 QQCC、QQCC Config Backend | 完整 HTTPS 前缀，例如 `https://<api-host>/api/private-bots/webhook`；代码再追加 public ID |
| `PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL` | 官方 QQCC | 完整 HTTPS owner 页面 URL；Bot 会把一次性 `ticket` 追加到 URL fragment，避免它进入 HTTP 请求与边缘日志 |
| `PRIVATE_QQCC_BOT_OWNER_HOST` | 官方 QQCC、QQCC Config Frontend/Nginx | 只填 hostname，不含 scheme/path；必须与 owner WebApp URL hostname 一致 |
| `QQCC_CONFIG_ADMIN_HOST` | QQCC Config Frontend/Nginx | 管理员 Host；必须与 owner Host 不同，公网仍由 Cloudflare Access 保护 |
| `QQCC_BOT_TOKEN` / `QQCC_BOT_TOKEN_TEST` | 官方 QQCC polling、private worker | private worker 只用环境对应的官方 QQCC token 做统一频道会员查询，不启动 polling；gate 为 `true` 时 validator 要求对应 token 存在 |
| `PRIVATE_QQCC_BOT_WORKER_MAX_INFLIGHT_UPDATES` | private worker | 全局 inflight update 上限，默认 `64` |
| `PRIVATE_QQCC_BOT_WORKER_PER_BOT_PREFETCH` | private worker | 单 Bot 有界队列预取上限，默认 `8`，且不会超过全局 inflight 上限 |
| `PRIVATE_QQCC_BOT_WORKER_MAX_DEFERRED_UPDATES` | private worker | 进程内 deferred message ID 上限，默认 `1024`；body 仍留在 Redis |
| `PRIVATE_QQCC_BOT_METRICS_PUBLISH_SECONDS` | private worker | worker 指标 heartbeat 周期，默认 `15` 秒 |
| `PRIVATE_QQCC_BOT_SUBMISSION_RETENTION_DAYS` | private worker recovery/ledger cleanup | 私有任务幂等账本保留天数，默认 `90`，代码强制最小 `30`；只清理无活跃 registry 引用的安全终态 |

private worker 不读取“共享私有 Bot token”，而是按租户从数据库解密各自凭据；它额外读取环境对应的官方 QQCC token，仅用于统一频道会员检查。该官方 token 不得传给管理后端，也不能在 private worker 中启动 polling。
管理后端必须依赖 `PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS` 做保留身份拒绝，不得为了派生 Bot ID 而向管理容器新增或复制任何官方 Bot token。

现有 `TELEGRAM_API_BASE_URL=http://...` 可继续服务受控的官方 Bot 历史链路，但绝不能承载用户私有 token：Bot API 把 token 放在 URL path，公网 HTTP 会直接泄漏凭据。私有 Bot 专用 API/file base 在启动时必须 fail closed 校验 HTTPS；只有明确受信的自建 HTTPS host 才能通过 `PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS` 放行。

三个私有密钥必须分别生成，每次命令输出只能用于一个变量，不得复制同一结果：

```bash
python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

将第一次输出放入 keyring 的 version `1`，第二次用于 fingerprint key，第三次用于 owner JWT key。不要把生成结果写入 shell history、文档或完整 compose 输出。

## 6. Compose、发布与回滚

云测试与云正式 compose 均定义独立服务：

- `qqcc-private-bot-worker-test` / container `cloud-qqcc-private-bot-worker-test`
- `qqcc-private-bot-worker-prod` / container `cloud-qqcc-private-bot-worker-prod`
- profile：`qqcc-private-bots`

profile 不会被默认控制面 `up` 启动。2026-07-12 云正式已完成 Alembic `3e9c7a1b5d24`、严格 env validator、Web/API/QQCC Config/官方 QQCC 镜像发布、`PRIVATE_QQCC_BOT_ENABLED=true`、`cloud-qqcc-private-bot-worker-prod` 启动，以及生产 webhook/owner public Host；管理员 Access 入口保持独立。首次发布 smoke 时私有 Bot/审计表均为 0 行，等待 owner 手动申请验证。

private worker 运行在 Python 3.10。所有 `asyncio.wait_for(...)` 的周期循环必须捕获 `asyncio.TimeoutError`，不能使用裸 `TimeoutError`；两者在 Python 3.10 不是同一异常类，错误捕获会让 metrics heartbeat、pending/zombie sweeper 等后台循环在第一次 timeout 后静默退出。回归测试必须模拟这一差异，并在生产验证 heartbeat TTL 持续刷新。

发布顺序：

1. 确认 `python -m alembic heads` 为单 head，在云测试显式执行 `alembic upgrade head`。
2. 配置云测试独立 keyring/fingerprint/JWT、测试 webhook base 和测试 owner Host/URL；不得复用正式密钥或域名。
3. 重建云测试 Web API、QQCC Config Backend/Frontend 与官方 QQCC Bot，再显式启动 `--profile qqcc-private-bots` 的 test worker。
4. 验证 token 消息删除、重复/官方/已有 webhook 拒绝、同 owner 并发唯一、owner ticket 单次兑换、Host 隔离、暂停/恢复/禁用优先级、Redis 去重、跨租户配置/任务/结果隔离及单任务重启恢复；同时验证私有多阶段绘图/原图换脸/尾帧视频在结果到下一步注册、TaskRegistry 为空、租约丢失、暂停/禁用和 delivery 故障后仍可幂等续跑，中间结果不发送、最终结果先落 checkpoint 再投递。
5. 完成至少 500 个租户元数据和 webhook burst 验证，观察 stream lag、pending、active Application、Webhook 4xx/5xx、Telegram 注册失败与恢复失败。
6. 只有用户再次明确确认正式发布后，才可执行正式 migration、填正式 secret、创建/修改 Cloudflare owner public hostname、重建相关正式服务并启动 `qqcc-private-bot-worker-prod`。

截至 2026-07-12，尚未完成真实 Redis/PostgreSQL/PTB/Telegram HTTP 组合下的 500 租户与 webhook burst 压测；单元测试或内存 fake 的 500 租户用例不能替代负载验收。正式环境已按用户确认进入首个 owner 手动试用阶段，但该缺口仍是容量残余风险，不能写成已完成负载验证或 500 租户容量承诺。

`safe_deploy_cloud_test.sh` / `safe_deploy_cloud_prod.sh` 以 `scripts/validate_private_qqcc_bot_env.py --allow-disabled` 做条件校验：gate 缺失或为 `false` 且 profile 未启用时，不要求 activation secrets，避免普通控制面重建被未启用 profile 阻断；gate 为 `true` 时仍严格校验全部 activation secrets、环境对应的官方 QQCC token、32-byte Base64URL 密钥独立性、forbidden IDs、owner URL/Host 一致性与 trusted Telegram HTTPS host。直接运行 validator 且不传 `--allow-disabled` 是启用前严格模式，gate 缺失/`false` 也会失败。

QQCC Config Frontend 健康检查必须携带 admin Host，维护式 test/prod wrapper 的远端验证也遵循同一 Host 规则。任何启用态 preflight 失败都先修 env，不允许临时把 unknown Host 回落到管理员站点。compose 对 private profile 的 activation secret 插值保持可选，只为保证 gate/profile 未启用时能完成普通 `config -q`；这不削弱 gate=`true` 的 validator 门禁。

回滚优先停止 private worker 并阻止新 webhook update；不要删除 History 或直接回滚已承载数据的 migration。若需关闭入口，先管理员禁用/删除 Telegram webhook，再评估数据库回滚。

## 7. 最小验证

- `docker-compose -f deploy/docker-compose-cloud-test.yml config -q`
- `docker-compose -f deploy/docker-compose-cloud-prod.yml config -q`
- `python -m alembic heads`
- `python scripts/doc_quality_checker.py`
- 未启用门禁校验：`python scripts/validate_private_qqcc_bot_env.py --env-file <ignored-test-or-prod-env> --allow-disabled`
- 启用前严格校验：`python scripts/validate_private_qqcc_bot_env.py --env-file <ignored-test-or-prod-env>`
- `bash -n scripts/safe_deploy_cloud_test.sh scripts/safe_deploy_cloud_prod.sh scripts/update_cloud_test_with_maintenance.sh scripts/update_cloud_prod_with_maintenance.sh`
- `pytest -q tests/ops/test_ops_wrappers.py`
- focused tests 覆盖 schema/加密、申请 FSM/lifecycle、同 Bot active-task 救援轮换、owner auth/API 与 limiter/Host、webhook queue/入口与 metrics、private worker 有界背压/startup PEL catch-up、官方 membership checker、运行时配置、确定性 submission/debit/refund/concurrency 幂等、迟到扣费 fence、账本 retention 和恢复过滤。

Nginx build 后还要对同一 origin 做 Host 矩阵验收（以下变量只放 hostname）：

```bash
# Owner Host：首页 200；owner auth/API 可达；管理员 API 和 /api/health 必须 404。
curl -fsS -H "Host: ${PRIVATE_QQCC_BOT_OWNER_HOST}" http://127.0.0.1:8088/ >/dev/null
test "$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: ${PRIVATE_QQCC_BOT_OWNER_HOST}" http://127.0.0.1:8088/api/private-bots/admin)" = 404
test "$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: ${PRIVATE_QQCC_BOT_OWNER_HOST}" http://127.0.0.1:8088/api/health)" = 404

# Admin Host：首页/API health 200；公网外层还必须验证 Cloudflare Access 跳转。
curl -fsS -H "Host: ${QQCC_CONFIG_ADMIN_HOST}" http://127.0.0.1:8088/ >/dev/null
curl -fsS -H "Host: ${QQCC_CONFIG_ADMIN_HOST}" http://127.0.0.1:8088/api/health >/dev/null

# 未知 Host：首页和 API 都必须 404，不能回落到 admin。
test "$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: unknown.invalid' http://127.0.0.1:8088/)" = 404
test "$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: unknown.invalid' http://127.0.0.1:8088/api/health)" = 404

# Owner 允许 Telegram WebView 嵌入，且不得发送冲突的 X-Frame-Options。
owner_headers="$(curl -sSI -H "Host: ${PRIVATE_QQCC_BOT_OWNER_HOST}" http://127.0.0.1:8088/)"
grep -Fiq "connect-src 'self';" <<<"$owner_headers"
grep -Fiq "frame-ancestors 'self' https://*.telegram.org https://telegram.org" <<<"$owner_headers"
! grep -Fiq 'x-frame-options:' <<<"$owner_headers"

# Admin 与 unknown Host 仍不可嵌入。
admin_headers="$(curl -sSI -H "Host: ${QQCC_CONFIG_ADMIN_HOST}" http://127.0.0.1:8088/)"
grep -Fiq 'x-frame-options: DENY' <<<"$admin_headers"
grep -Fiq "frame-ancestors 'none'" <<<"$admin_headers"
unknown_headers="$(curl -sSI -H 'Host: unknown.invalid' http://127.0.0.1:8088/)"
grep -Fiq 'x-frame-options: DENY' <<<"$unknown_headers"
grep -Fiq "frame-ancestors 'none'" <<<"$unknown_headers"
```

Compose 校验必须使用安全 dummy env 且只运行 `config -q`；禁止打印包含真实 secret 或数据库 URL 的完整 `docker compose config`。
