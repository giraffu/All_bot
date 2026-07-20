# 子模块: 云测试控制面部署 (Cloud Test Control Plane)

> 2026-07-19：A-H 完成后以单批次 PR 合入 main，main CI 只构建一次不可变 bundle；只有用户要求测试时才部署该 main SHA。QQCC Config 前后端继续按 standard 进入专属测试实例，Dashboard 仍不进入测试站，`test-execution` 只在专项诊断时启用。状态/回滚历史按 track + artifact digest 隔离。禁止代码/env rsync、云端 build、源码 bind mount和 RunPod 启动 clone。
> 配置唯一事实源为云测试主机 `/etc/allbot/test.env`；发布器只生成权限 `600` 的逐服务投影，不把整份 env 注入全部容器。`safe_deploy_cloud_test.sh` 与旧维护脚本仅作 fail-closed 历史兼容，legacy `.env`/Compose 运行态不再是新发布事实源。
> 首次切换前如仍只有 `BOT_TOKEN_TEST`/`QQCC_BOT_TOKEN_TEST` 等旧别名，先对该主机事实源执行 `scripts/migrate_legacy_test_env.py --control-plane-only`；候选文件通过 `config-plan` 后备份并原子替换。该模式只补 canonical 控制面键，不改写任何 Worker 选择、槽位或端点。
>
> `ALLBOT_WORKER_*`、`CLOUD_TEST_WORKER_*` 与 `CLOUD_TEST_SHARED_AIO_*` 属于独立 GPU/Worker 链路。控制面配置工具保留它们的受限宿主值，但不将其计入 control-plane revision、漂移、影响服务或逐服务投影。测试 Worker 的发布、候选切换和验收继续使用 `test-execution`/GPU operator，不随控制面 `config-apply` 联动。Dashboard 消费的 `RUNPOD_*` / `LAN_AIO_*` 不在此排除集。

## 1. 目标与边界

本模块记录 DigitalOcean SGP1 独立测试 Droplet `allbot-do-sgp1-test-control` 上的云端测试控制面部署方式。当前云端测试栈用于验证 Web API、Central API、QQCC Config Backend、QQCC Config Frontend、同机测试 PostgreSQL、同机测试 Redis、R2 对象存储、imgproxy 与测试 Bot；Dashboard 不在测试站运行。

当前推荐形态是云端运行测试控制面、测试数据库、测试缓存与测试 Bot，本地主服务器运行 8 个 cloud-worker 测试容器并继续使用武汉局域网内的 ComfyUI/GPU 节点。云端与本地主服务器之间使用 Tailscale 私有网络互联；SSH 端口转发只作为应急方案。

## 2. Legacy 入口与新事实源

- 新控制面：`deploy/docker-compose-cloud-base.yml` + `deploy/docker-compose-cloud-test.overlay.yml`
- 私密配置：`/etc/allbot/test.env`；逐服务投影：`/var/lib/allbot/config/test/<revision>/<service>.env`；非敏感镜像/SHA/配置 revision：release 目录的 `release.env`
- 计划/发布：按顺序执行 `scripts/release.py plan --env test --sha <full-sha>`、`preflight --env test --sha <full-sha>`、`deploy --env test --sha <full-sha> --execute`；不得用 `--services` 人工缩小机器计算的依赖闭包。
- 发布批次：A-H 推送并 handoff 后，由集成 AI 一次组合为 release-batch，只创建一个 main PR。main CI bundle 构建成功且用户要求测试后，集成 AI直接执行 `release.py plan|preflight|deploy --env test`。默认只部署需要测试的 control-plane/公共 Web；QQCC Config 按 standard 部署专属测试前后端，Dashboard-only 不修改测试站。Worker 专项诊断显式选择 `test-execution`。
- `test-execution` 首次没有独立 `current.json` 时，release plan 必须标记 `initial-release`，从当前 legacy `cloud-comfy-agent-test-*` / `cloud-worker-relay-test` 做 allowlist 快照和受控切换；快照、release env 与回滚材料统一位于 `~/APP/All_bot-release/release-env/test-execution/<sha>/`，后续 Worker preflight 也必须从该 track-scoped 路径读取。test-execution 未选择任何 cloud service 时跳过 cloud preflight，不要求云端存在该轨的 release.env。若 control-plane 已完成而 Worker 预检失败，保持原槽位做 forward-fix，不能把候选记为已完整部署。
- 云端控制面回滚目标若是 track 隔离上线前的历史候选，可能只有 `/var/lib/allbot/releases/<sha>/release.env`。preflight、失败恢复和恢复验证必须先找 `/var/lib/allbot/releases/control-plane/<sha>/release.env`，缺失时才兼容同一 SHA 的 legacy 合约；正向候选仍只生成 track-scoped 合约，禁止回写或覆盖 legacy 文件。
- v2 两轨事务分别写 `transactions/control-plane/<sha>` 与 `transactions/test-execution/<sha>`，不能因 SHA 相同覆盖彼此；test-execution 首次切换不重跑云端 Postgres/Redis。升级前的无 track Worker 失败 journal 必须用 `release.py recover --env test --track test-execution --transaction <sha> --execute` 收口，发布器兼容读取旧路径并把恢复结果写到新路径。
- 若 control-plane 状态存在但 `allbot-test-postgres-1` / `allbot-test-redis-1` 缺失，普通 deploy 必须在 Redis drain 处失败，禁止手工 compose。先短暂启动停止的 `cloud-redis-test`，只读核对 worker DB 的 pending/running 均为 0 并立即停止；随后仅可对可信 main bundle 用 `release.py deploy --env test --track control-plane --repair-test-data-services --services postgres --services redis --confirm-legacy-cutover --confirm-empty-test-queue --execute` 做成对、维护式修复。任一队列非零不得确认。
- Web 自由P图 v2.5/v3 发布验收共用运行时开关 `enable_free_edit_v3` 和 BF16 执行池。先验收两张模式卡、v2.5 单/双图 3/7 灵石、v3 单图 5 灵石、无 LoRA、预签名上传、投稿与一键应用入口；目标 Worker 可用时分别完成“v2.5 单图”“v2.5 双图”“v3 BF16→换脸”三条黄金路径，其中双图投稿应用必须重新上传两张。Worker 不可用时记录独立待办，不得把未执行写成通过；全部适用 smoke 完成后即可执行 `verify-test`，不再等待固定 24 小时。
- 下列路径只描述首次切换前的 legacy 运行态：
- 远程主机别名：`allbot-do-sgp1-test-control`
- 远程代码目录：`/home/deploy/APP/All_bot`
- Compose 文件：`deploy/docker-compose-cloud-test.yml`
- 日常快速更新：同步必要代码后直接重建目标 service 容器
- 维护式整栈更新脚本：`scripts/update_cloud_test_with_maintenance.sh`
- 远端控制面重建脚本：`scripts/safe_deploy_cloud_test.sh`
- 环境文件：`.env.cloud.test`
- 本地 cloud-worker Compose 文件：`workers/docker-compose-cloud-worker-test.yml`
- 本地停止测试栈脚本：`scripts/stop_local_test_preserve.sh`
- 本地启动 cloud-worker 脚本：`scripts/start_cloud_worker_test.sh`

`.env.cloud.test` 只允许保存在本机和云端目标目录，已通过 `.gitignore` 忽略，不得提交到仓库。

核心运行变量：

```bash
CLOUD_TEST_BIND_IP=100.82.124.91
CLOUD_TEST_CONTROL_HOST=100.82.124.91
CLOUD_TEST_TAILSCALE_IP=100.82.124.91
MINIO_ENDPOINT=c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com
MINIO_BUCKET=user-data-test
MINIO_INPUT_BUCKET=user-data-test
MINIO_RESULT_BUCKET=user-data-test
MINIO_TEMPLATE_BUCKET=user-data-test
MINIO_SECURE=true
MINIO_PUBLIC_URL=
R2_BUCKET=user-data-test
R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com
RUNPOD_MODEL_BUCKET=allbot-model-cache
RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10
RUNPOD_MODEL_ENDPOINT=https://c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com
RUNPOD_MODEL_SECURE=true
CLOUD_TEST_DATABASE_URL=postgresql+asyncpg://postgres:<password>@postgres-test:5432/bot_db_test
CLOUD_TEST_REDIS_URL=redis://:<password>@redis-test:6379/3
CLOUD_TEST_WORKER_REDIS_URL=redis://:<password>@redis-test:6379/4
PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL=https://api-test.aivison.it.com/api/private-bots/webhook
PRIVATE_QQCC_BOT_TOKEN_KEYRING='{"1":"<urlsafe-base64-32-byte-aes-key>"}'
PRIVATE_QQCC_BOT_TOKEN_ACTIVE_KEY_VERSION=1
PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY=<urlsafe-base64-32-byte-hmac-key>
PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS=<all-official-and-test-bot-numeric-ids>
PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL=https://api.telegram.org
PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL=https://api.telegram.org/file/bot
PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS=
```

2026-07-14 首次真实 Bot 任务回归发现 legacy env 仍有 `API_BASE_TEST=http://central-api-test:8003`。由于 `BOT_TYPE=TEST` 会让 `config.py` 优先读取 `*_TEST`，只在 overlay 设置 `API_BASE=http://central-api:8003` 不足以覆盖，表现为任务派发阶段 `Errno -3` 且 Saga 退款。当前 immutable test overlay 必须对所有 Python 消费者同时设置 `API_BASE`/`API_BASE_TEST=http://central-api:8003`，发布器在写状态前进入容器校验 `config.API_BASE`。验收不得再用未经 `config.py` 解析的原始 env 作为 DNS 反馈环。

同轮恢复还暴露 SSH stdin 脚本截断：远端 `docker compose exec -T central-api ...` 会继续读取 stdin，把后续 pull/up/门禁命令吞掉，外层 SSH 仍可能返回 0。所有远端 Compose exec/run 必须追加 `</dev/null`，且发布成功必须同时看到 SHA 完成标记、实际容器 digest 与 OCI revision；只看到 release plan 或 `current.json` 更新不算部署成功。

`CLOUD_TEST_BIND_IP` 用于云端服务端口绑定；当前绑定云测试 Tailscale IP `100.82.124.91`，不直接开放公网。`CLOUD_TEST_CONTROL_HOST` 用于本地 GPU worker 访问云端 Central API，也应填 `100.82.124.91`。当前云测试对象存储直接使用 Cloudflare R2 S3 兼容接口，`MINIO_*` 是项目内兼容变量名但值指向 R2；`MINIO_PUBLIC_URL` 继续留空，`R2_PUBLIC_DOMAIN` 使用已验证的新对象公网域名。Web owner 视频结果接口只在 R2 公网 URL 可解析时返回成功，若临时清空 `R2_PUBLIC_DOMAIN`，视频任务可能在 99% / `pending_result` 等待结果 URL。

云测试 R2 变量分层：

| 变量 | 当前值或来源 | 作用 |
| :--- | :--- | :--- |
| `MINIO_*` / `R2_*` | `user-data-test` + `https://r2-test.aivison.it.com` | 用户上传、任务输入/结果、模板、历史/Gallery 媒体；不要把模型权重放入该桶 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `.env.cloud.test` 真实值；RunPod Pod 内使用 `allbot_cloud_test_r2_access_key` / `allbot_cloud_test_r2_secret_key` secret | 只读写 `user-data-test` |
| `RUNPOD_MODEL_*` | `allbot-model-cache` + `RUNPOD_MODEL_PREFIX`/`RUNPOD_MODEL_MANIFEST_KEY` | Wan22 AIO、`image_to_video` 与 `wan22_video_v2` 的下一不可变契约统一使用各自独立的 `2026-07-18-lora5` key；权重上传并完成 size/SHA metadata HEAD 前不得发布 manifest 或切换 runtime。其它 profile 版本保持现有配置。 |
| `RUNPOD_MODEL_ACCESS_KEY` / `RUNPOD_MODEL_SECRET_KEY` | `.env.cloud.test` 可保存真实值，供本地 dry-run HEAD/上传脚本使用 | 只读写 `allbot-model-cache`，不能复用 `user-data-test` 的 R2 key |
| `RUNPOD_MODEL_ACCESS_KEY_REF` / `RUNPOD_MODEL_SECRET_KEY_REF` | `allbot_model_cache_r2_access_key` / `allbot_model_cache_r2_secret_key` | RunPod create JSON 中的模型桶 secret 引用字符串，不是密钥本体 |

Cloudflare R2 页面里显示的 `cfat_...` API token 只用于 Cloudflare API，不是 S3 access key；云测试 `.env.cloud.test` 和知识库都不保存该 token。实际 S3 客户端只使用 access key id / secret access key / endpoint / bucket。

RunPod 云测试远程 worker 使用独立 worker Central 域名 `worker-central-test.aivison.it.com`，回源云测试 Central `http://100.82.124.91:8004`。2026-06-11 已在 `allbot-do-sgp1-test-control` 安装 `cloudflared` 2026.6.0，并以 Cloudflare Tunnel `RunPod-test` token 安装 systemd 服务 `cloudflared.service`；服务已能连接 Cloudflare。该 tunnel 已配置 Published application / Public hostname：

```text
Hostname: worker-central-test.aivison.it.com
Service:  http://100.82.124.91:8004
```

验收：`https://worker-central-test.aivison.it.com/health` 返回 Central API OK，`/system/status` 可读云测试队列状态。该域名只供 remote worker / RunPod Pod 访问 Central agent API，不得复用 `api.aivison.it.com`，也不要开启会拦截 worker 请求的 Cloudflare Access 登录页；先依赖 `AGENT_SECRET_TOKEN` 鉴权，并在 Cloudflare 侧加 WAF/rate limit。`cloudflared.service` 由 token-based install 创建，`systemctl status cloudflared` 可能显示 tunnel token，排障时不得把完整输出贴入文档或聊天。

Web 前端上传参考图/视频时会先调用云端 Web API 获取预签名地址，再由浏览器直接 `PUT` 到 R2 S3 endpoint。R2 `user-data-test` 桶必须配置 CORS，否则前端会显示 `Network error during upload`：

```json
[
  {
    "AllowedOrigins": [
      "https://web-test.aivison.it.com",
      "https://web.aivison.it.com",
      "https://web-cf-test.aivison.it.com",
      "https://allbot-web-cf-test.pages.dev"
    ],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

## 3. Legacy 部署命令（归档，禁止执行）

本节保留首次不可变切换前的现场事实，只用于归档与一次性 legacy 回滚设计。当前云测试发布必须执行 `scripts/release.py plan --env test --sha <full-sha>`，确认机器计算的依赖集合后再执行对应 `deploy`；不得复制执行下列 rsync/build 命令。

以下是旧流程原文：常规测试环境更新以快速为主，只同步本轮必要代码并重建对应模块容器。

1. 按改动影响确认目标 service。Bot 展示/FSM 改动重建 `bot-test`；Web API 改动重建 `web-api-test`；Central/队列 API 改动重建 `central-api-test`；Dashboard 或 QQCC Config 改动重建对应前后端 service；QQCC Bot 改动重建 `qqcc-bot-test`。
2. 用 `rsync` 同步必要文件，或按既有排除规则做整仓同步；不要同步 `.env.*`、`logs/`、`runtime/`、`backups/`、`local_analytics_platform/`、前端构建产物、密钥文件。
3. 在云测试机限定 service 重建并启动：

```bash
ssh allbot-do-sgp1-test-control
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot build bot-test
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot up -d --no-deps bot-test
```

4. 验证目标容器状态、启动日志和对应健康检查。Bot/QQCC Bot 没有 HTTP healthcheck 时，至少确认容器 `Up`、启动日志无新增异常，并做一条只读功能级 smoke。

按目标替换上例中的 service/profile：

- `web-api-test`、`central-api-test`、`imgproxy-test` 不需要 Bot profile；QQCC Config 由 immutable base 的 `owner-tools` profile 服务加测试 overlay 管理，Dashboard 不存在于测试 overlay。
- `bot-test` 使用 `--profile bot`；启动前确认本地主服务器或其它位置没有同测试 token polling 实例。
- `qqcc-bot-test` 使用 `--profile qqcc-bot`；没有独立 `QQCC_BOT_TOKEN_TEST` 时必须保持停止。

维护式整栈更新仍保留，但只在涉及迁移、跨服务契约、控制面多服务联动、边缘 Web 发布、需要排空队列验证，或用户明确要求维护窗口时使用：

```bash
scripts/update_cloud_test_with_maintenance.sh --execute
```

该脚本会写入生成维护标记、等待 Central Redis `comfy:queue:pending` 与 `comfy:queue:running` 清空、同步代码/env、执行 `scripts/safe_deploy_cloud_test.sh` 重建控制面、按需重建测试 Bot/QQCC Bot，并默认发布 `web-test.aivison.it.com` 静态前端。普通测试更新不要为提速而使用 `--skip-drain` 绕过维护式流程，直接走上面的目标 service 重建。

常用参数：

- `--bot-mode start|skip|stop|auto`：默认 `auto`，只在 Bot 原本运行时重建并启动。
- `--qqcc-bot-mode start|skip|stop|auto`：默认 `auto`，只在 QQCC Bot 原本运行时重建并启动；`start` 仍要求远端 `.env.cloud.test` 配置 `QQCC_BOT_TOKEN_TEST`。
- `--env-file FILE`：指定要同步到远端 `.env.cloud.test` 的本地测试环境文件，默认读取仓库根目录 `.env.cloud.test`。
- `--skip-env-sync`：不更新远端 `.env.cloud.test`，仅使用远端现有环境文件。
- `--skip-edge-web`：只更新控制面，不发布边缘测试 Web 静态站。
- `--keep-maintenance`：部署成功后仍保持 Web/Bot 生成维护，便于人工验收后再手动解除。
- `--skip-drain`：维护式脚本的紧急参数；普通快速测试更新不走维护式脚本，因此不需要该参数。

测试 Web/Bot/QQCC Bot compose 挂载 `../runtime/cloud-test:/app/runtime-flags`，并通过 `GENERATION_MAINTENANCE_FILE=/app/runtime-flags/GENERATION_MAINTENANCE` 读取生成维护标记。维护式脚本会先写远端 `runtime/cloud-test/GENERATION_MAINTENANCE`，因此重建后的新容器仍会保持维护状态，直到脚本最后解除。

专项情况下，也可以从本地主服务器同步代码后，在云端只执行控制面重建子步骤：

```bash
ssh allbot-do-sgp1-test-control
cd /home/deploy/APP/All_bot
./scripts/safe_deploy_cloud_test.sh
```

`safe_deploy_cloud_test.sh` 执行顺序：

1. 校验 `CLOUD_TEST_DATABASE_URL`、`CLOUD_TEST_REDIS_URL`、`CLOUD_TEST_WORKER_REDIS_URL` 与同机 Postgres/Redis 密码。
2. 启动并等待 `postgres-test`、`redis-test` 健康。
3. 构建 Central API、Web API、Dashboard Backend、Dashboard Frontend、QQCC Config Backend、QQCC Config Frontend 镜像。
4. 检查 Alembic 只有一个 head。
5. 初始化或迁移云测试数据库。
6. 重启控制面服务、Dashboard Frontend、QQCC Config Frontend 与 imgproxy。
7. 校验 Central API、Web API、Dashboard API、Dashboard Frontend、QQCC Config API 与 QQCC Config Frontend 健康检查。

启动测试 Bot：

```bash
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot up -d bot-test
```

若历史本地测试栈仍在本地主服务器运行，切换云测试前先停止并保留数据：

```bash
./scripts/stop_local_test_preserve.sh
```

随后启动本地 cloud-worker 测试栈：

```bash
./scripts/start_cloud_worker_test.sh
```

公网测试 Web 入口继续使用边缘 VPS 的 `web-test.aivison.it.com`，不直接暴露云端 Vite 端口。当前形态是：

```text
web-test.aivison.it.com
  -> Tailscale 内的 web VPS 100.88.57.122
  -> /root/dist-test 静态前端
  -> /api/ 反代到云端测试 Web API
```

当前 `/api/` upstream 为云测试 Tailscale Web API `http://100.82.124.91:8001`。
测试静态站的 `index.html` 和 SPA fallback 必须设置重新校验缓存头，避免浏览器继续使用旧入口 HTML；哈希化的 `assets/*` 文件可按文件名缓存。

发布静态前端：

```bash
cd frontend
npm run deploy:edge-test
```

VPS Nginx 配置文件为 `/etc/nginx/sites-available/web-test.aivison.it.com`，修改后必须执行 `nginx -t && nginx -s reload`。仓库模板为根目录 `all_bot_nginx_web_test.conf`。

## 4. 数据库初始化策略

当前历史 `initial_baseline` Alembic 迁移不是完整的空库建表迁移，它依赖一批历史表已经存在。因此云端全新测试库不能直接先跑 `alembic upgrade head`。

`safe_deploy_cloud_test.sh` 的云测试策略是：

- 若云测试库没有 `users` 表：使用当前 ORM `Base.metadata.create_all()` 初始化当前测试 schema，然后 `alembic stamp head`，再同步基础种子数据。
- 若云测试库已经存在 schema：执行 `alembic upgrade head`，再同步基础种子数据。

该策略只用于云测试控制面，不改变生产发布脚本的迁移口径。

### 4.1 同机测试 PostgreSQL

2026-06-09 新建独立测试 Droplet 后，云测试数据库改回同机容器 `postgres-test`，避免为短期测试环境单独承担托管 PostgreSQL 成本，也避免误连正式托管库。

当前事实：

- 容器名：`cloud-postgres-test`
- 镜像：`postgres:15`
- 数据卷：`cloud-postgres-test-data`
- 数据库：`bot_db_test`
- 应用连接：`CLOUD_TEST_DATABASE_URL=postgresql+asyncpg://postgres:<password>@postgres-test:5432/bot_db_test`

密码和完整连接串只允许写入 `.env.cloud.test`、云端受控 secret/env 文件或本地密码管理器，不得写入仓库文档。若未来重新使用托管 PostgreSQL，必须单独更新本文档和运维 Skill，并确认 Trusted sources、SSL 与迁移演练。

## 5. 服务与端口

所有入口服务端口绑定到云测试 Tailscale IP `100.82.124.91`，不直接暴露公网。若临时设置 `CLOUD_TEST_BIND_IP=0.0.0.0`，必须同时配置源 IP 白名单，只允许边缘 VPS 和本地主服务器访问测试 API 端口。

| 服务 | 容器名 | 本机端口 | 用途 |
| :--- | :--- | :--- | :--- |
| Central API | `cloud-central-api-test` | `8004` | 任务控制面 API，本地 cloud-worker 访问 |
| Web API | `cloud-web-api-test` | `8001` | Web BFF / 主 API |
| QQCC Config Backend | `cloud-qqcc-config-backend-test` | `8045` | 专属测试懒人 Bot 配置 API |
| QQCC Config Frontend | `cloud-qqcc-config-frontend-test` | `8088` | 专属测试懒人 Bot 配置 Web |
| QQCC Private Bot Worker | `cloud-qqcc-private-bot-worker-test` | 无 | `qqcc-private-bots` profile；消费 Telegram webhook stream，默认不启动 |
| imgproxy | `cloud-imgproxy-test` | `8084` | 图片代理 |

Dashboard 不属于云测试服务清单。QQCC Config 的测试 Host/8045/8088 进入配置门禁、preflight 和验收；测试机 firewall 继续保护这些端口。
`https://qqcc-admin-test.aivison.it.com` 由测试 Tunnel 回源 `100.82.124.91:8088`，未登录请求由 Cloudflare Access 拦截。该入口由 main bundle 的云测试发布管理；入口可达之外还必须核对目标 digest/revision 与业务页面。QQCC Config 自身登录仍是第二层认证，测试 private Bot gate 关闭，`private-bot-test.aivison.it.com` 未创建。

云测试缓存与队列使用同机容器 `redis-test`，不复用正式 Valkey/Redis：

```text
Container: cloud-redis-test
Image: redis:7-alpine
Volume: cloud-redis-test-data
REDIS_URL: DB 3
WORKER_REDIS_URL: DB 4
Auth: CLOUD_TEST_REDIS_PASSWORD
```

Tailscale 主链路验证：

```bash
curl -fsS http://<CLOUD_TEST_CONTROL_HOST>:8004/health
./scripts/start_cloud_worker_test.sh
```

VS Code Remote 或本地 SSH 仍可通过端口转发作为应急访问：

```bash
ssh -N \
  -L 8001:100.82.124.91:8001 \
  -L 8004:100.82.124.91:8004 \
  allbot-do-sgp1-test-control
```

## 6. 验证命令

```bash
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps
curl -fsS http://100.82.124.91:8004/health
curl -fsS http://100.82.124.91:8001/api/health
docker stats --no-stream
df -h /
```

QQCC 私有 Bot 联调属于跨 Web API、QQCC Config、官方 QQCC、Redis stream、Alembic 与 private worker 的整栈变更。未启用时 safe deploy 以 validator `--allow-disabled` 接受 gate 缺失/`false`，不要求 inactive profile 的 activation secrets；准备联调时必须显式设置 `PRIVATE_QQCC_BOT_ENABLED=true`，配置独立测试 keyring/JWT/fingerprint、测试 HTTPS webhook base、owner Host/URL 和 `QQCC_BOT_TOKEN_TEST`，再经严格 validator、显式 migration 后按变更面重建服务。private worker 只通过精确 profile 启动；它读取测试官方 token 仅用于频道会员查询，不启动 polling：

```bash
docker compose --env-file .env.cloud.test \
  -f deploy/docker-compose-cloud-test.yml \
  --profile qqcc-private-bots build qqcc-private-bot-worker-test
docker compose --env-file .env.cloud.test \
  -f deploy/docker-compose-cloud-test.yml \
  --profile qqcc-private-bots up -d --no-deps qqcc-private-bot-worker-test
```

执行前还必须确认测试 webhook hostname 已实际路由到 `web-api-test`、owner public Host 只暴露 owner API、worker startup PEL catch-up/有界背压与 admin metrics 可观测，以及 `QQCC_BOT_TOKEN_TEST` 没有第二个 polling 实例。本文只记录契约，不代表本轮已部署云测试。

2026-06-09 独立测试 Droplet 首次部署验证结果：

- Central API、Web API、Dashboard API 健康检查通过。
- 同机 Postgres/Redis 均为 healthy，Postgres/Redis 端口未发布到公网。
- 启动 `bot-test` 前已确认本地测试 Bot 停止，避免测试 token 双实例 polling。
- Droplet 根分区约 48GB，首次构建后已用约 9.2GB。

2026-06-13 RunPod `wan22_video_v2` 云测试 Web 端验收口径：

- 验收必须通过测试 Web API `http://100.82.124.91:8001/api/tasks/generate` 提交 `wan22_video_v2` preview/5s 任务，不能只做 worker 直测。
- 合格结果应同时满足：RunPod worker 接单、Central `task_type=wan22_video_v2`、终态 `done`、Web result `success`、MP4 与 `extra_outputs.last_frame` 均可下载。
- 验收结束后必须恢复临时禁用的云测试 worker，删除 RunPod Pod，并确认 `list-pods` / `reconcile-managed-pods` 的 managed count 为 0。

2026-06-14 RunPod `i2i_pro` 云测试 Web 端验收口径：

- `i2i_pro` 是 RunPod runtime profile，可同时支持执行面 `i2i_pro`、`t2i-pornmaster-turbo` 与 `face_swap_v2`；旧 `face_swap` V1 不进入该 profile。
- 验收必须通过测试 Web API `http://100.82.124.91:8001/api/tasks/generate` 串行提交 `i2i_pro`、Web `txt2img`、`face_swap_v2` 三单，不能只做 worker 直测。
- RunPod env 需渲染为 `RUNPOD_TASK_TYPE=i2i_pro`、`SUPPORTED_TASK_TYPES=i2i_pro,t2i-pornmaster-turbo,face_swap_v2`、`POOL_RUNTIME_PROFILE=i2i_pro`、`AGENT_ID` 前缀 `runpod_test_i2i_pro`，并带 `TASK_TYPE_WORKFLOW_OVERRIDES={"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json","face_swap_v2":"face_swap_v2.json"}`。
- 模型 manifest 使用 `allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json`，六个模型文件总计约 `36.11 GiB`；首次 canary 使用 `RUNPOD_CONTAINER_DISK_GB=120`，GPU 只请求 `NVIDIA GeForce RTX 4090`。
- 镜像基线使用与现有图生图 / Wan22 RunPod 一致的 `yanwk/comfyui-boot:cu128-slim`；不得使用 `cu130`，若真实 canary 仍遇驱动不兼容，再降级到 `cu124`。
- 合格结果应同时满足：RunPod worker heartbeat 出现为 `runpod_test_i2i_pro_*`、三单 Central `task_type` 分别为 `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap_v2`、每单 `pop_evidence.agent_id` 均匹配 RunPod worker、终态 `done`、Web result `success`、图片可下载；该 heartbeat 不得声明 `face_swap`。
- 若当前保留了云正式手动备用 RunPod Pod，执行 `i2i_pro` cloud-test canary 时必须显式开启 `--allow-existing-prod-managed-pods` 或 `RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS=true`；该开关只忽略 `allbot-runpod-prod-*-manual-` 已知正式手动备用名称前缀，任何 cloud-test 残留 managed Pod 仍会阻止执行。
- 失败排障时可用 `--no-cleanup` 保留本次新建的 `i2i_pro` Pod；复跑 Web 任务使用 `--reuse-pod-id i2i_pro=<pod_id>`，不得重复创建诊断 Pod。
- 验收结束后必须恢复临时禁用的非 RunPod cloud-test `i2i_pro/t2i-pornmaster-turbo/face_swap_v2` worker，删除本次新建的 RunPod Pod，并确认 `list-pods` / `reconcile-managed-pods` 的非忽略 managed count 为 0；既有 prod 手动备用 Pod 必须保持运行。

2026-06-17 RunPod `scail2` 云测试 Web 端验收口径：

- 本能力只做 cloud-test RunPod，不接云正式，不复用 `gpu-002/8190`。LAN AIO SCAIL-2 runtime 可继续给测试环境手工/worker 使用；RunPod canary 执行时会短暂 disable 支持 SCAIL-2 的非 RunPod cloud-test worker，通常是 `cloud_worker_test_08`，结束必须恢复。
- 模型权重转存到模型缓存桶 `allbot-model-cache/scail2/2026-06-17-test`，不能放进 `user-data-test`。入口为 `scripts/prepare_scail2_model_r2_bundle.py --env-file .env.cloud.test` dry-run，确认 6 个 HuggingFace direct URL、LoRA 路径 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors` 和 manifest key 后，才加 `--execute` 写入 R2。
- 镜像由 `.github/workflows/runpod_scail2_profile_image.yml` 构建并推送 `ghcr.io/giraffu/allbot-comfy-runpod-scail2:<tag>`。镜像必须包含 ComfyUI SCAIL-2 core 节点、VideoHelperSuite、KJNodes、rgthree、Frame-Interpolation、Fill-Nodes、ffmpeg、sshd/bootstrap，不得 baked 任何 `.safetensors` 权重。RunPod env 使用 `RUNPOD_IMAGE_NAME_SCAIL2=<GHCR ref>`、`RUNPOD_USE_TEMPLATE_SCAIL2=false`、`RUNPOD_MODEL_PREFIX_SCAIL2=scail2/2026-06-17-test`、`RUNPOD_MODEL_MANIFEST_KEY_SCAIL2=scail2/2026-06-17-test/manifest.json`。
- RunPod env 需渲染为 `RUNPOD_TASK_TYPE=scail2`、`SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_video_replacement`、`POOL_RUNTIME_PROFILE=scail2`、`AGENT_ID` 前缀 `runpod_test_scail2`，`MINIO_RESULT_BUCKET=user-data-test`，`RUNPOD_MODEL_BUCKET=allbot-model-cache`，`containerDiskInGb=120`，GPU 优先 `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090`，并带 `dockerStartCmd=["bash","-lc","exec bash /opt/allbot/runpod_bootstrap_from_git.sh"]`。
- `runpod canary --task-type scail2` 会上传/复用 Nomadoor 样例参考图与 motion video，串行提交 `scail2_action_transfer 5s` 与 `scail2_video_replacement 5s` 两个 Web 任务。合格结果应同时满足：RunPod worker heartbeat 出现为 `runpod_test_scail2_*`、两个 Central `task_type` 分别正确、每单 `pop_evidence.agent_id` 均匹配 RunPod worker、终态 `done`、Web result `success`、MP4 可下载/播放。
- 失败排障可用 `--no-cleanup` 保留本次 SCAIL-2 Pod；复跑使用 `--reuse-pod-id scail2=<pod_id>`，不得重复创建诊断 Pod。验收结束后必须恢复 `cloud_worker_test_08` 原 control 状态，删除本次 RunPod Pod，并确认 managed cloud-test Pod 清理正常。

2026-06-21 LTX 高级图生视频扩展云测试验收口径：

- LTX 用户侧仍通过 Web/Bot 的高级图生视频入口提交并写历史为 `ltx_video`；当前用户入口只开放单首帧与首尾帧，执行面分别分流为 `ltx_video`、`ltx_video_flf2v`。目标 LTX worker 仍建议声明 `SUPPORTED_TASK_TYPES=ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`，并加载三份 LTX workflow，以兼容历史/队列中的 V2V Audio 任务。
- 常规验收应通过测试 Web 或测试 Bot 分别提交单首帧、首尾帧两单，不能只做 worker 直测。合格结果应同时满足：Central 中两单执行类型分别正确、目标 LTX worker 接单、终态 `done`、Web result/history 成功、输出 MP4 可下载。
- 首尾帧模式必须检查 `extra_outputs.last_frame` 可下载，并从结果页或历史详情触发“扩展生成”后能把该尾帧预填为下一段 LTX 起始帧。
- 如需回归 `ltx_video_v2v_audio` 兼容执行面，应使用受控直测或临时入口单独验证；除 MP4 可播放外，还必须用实际播放器或 `ffprobe` 检查输出存在音频流。
- 现有 `ltx_video` 单首帧路径应保持旧 workflow 与结果表现不变；若只改了新工作流，仍要至少提交一单旧 I2V 做回归。

2026-06-22 LTX 10Eros v1.2 云测试 canary：

- `cloud-comfy-agent-test-3` / `cloud_worker_test_03` 是当前测试 LTX AIO worker，指向 `http://192.168.1.177:8191`。本次只通过 `.env.cloud.test` 的 `CLOUD_TEST_WORKER_03_TASK_TYPE_WORKFLOW_OVERRIDES` 覆盖测试 worker3，默认 `TASK_TYPE_WORKFLOW_FILENAMES` 不变。
- 三个 canary workflow 为 `LTX 2.3 10Eros v1.2 I2V 6.1.json`、`LTX 2.3 10Eros v1.2 FLF2V 6.1.json`、`LTX 2.3 10Eros v1.2 V2V Audio 6.1.json`，分别覆盖 `ltx_video`、`ltx_video_flf2v`、`ltx_video_v2v_audio`；旧 `LTX 2.3 *.json` 只作为历史默认 workflow 资产保留，不作为新 RunPod 的回退路径，不得覆盖。FLF2V canary 必须验证时空 VAE `last_frame_fix=true`，并抽样对比上传终止帧、VAE 尾帧与 MP4 解码尾帧。
- 10Eros v1.2 主模型文件名为 `models/diffusion_models/LTX 2.3/10Eros_v1.2_fp8mixed_learned.safetensors`。LAN AIO LTX 镜像不 baked 权重，测试前必须确认该文件在 AIO `/workspace/ComfyUI/models` 持久化挂载下可见；云端 R2 `allbot-model-cache/ltx_video/2026-06-10/manifest.json` 当前为 v1.2-only，旧 v1 不再作为 RunPod 回退，不要依赖手工容器层文件。
- RunPod `ltx_video` profile 的镜像由 `.github/workflows/runpod_ltx_video_profile_image.yml` 发布到仓库 Actions 可写的 `ghcr.io/giraffu/allbot-comfy-runpod-ltx-video-v2:<tag>`；旧无 `-v2` 包只作为历史回滚来源，不得承接新 SHA。Dockerfile 默认从公网 GHCR Wan22 镜像复制节点，不依赖 LAN registry。RunPod env 需渲染为 `RUNPOD_TASK_TYPE=ltx_video`、`SUPPORTED_TASK_TYPES=ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`、`POOL_RUNTIME_PROFILE=ltx_video`、`RUNPOD_MODEL_MANIFEST_KEY_LTX_VIDEO=ltx_video/2026-06-10/manifest.json`、`containerDiskInGb>=180`、GPU 优先 `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090`，并带三份 v1.2 `TASK_TYPE_WORKFLOW_OVERRIDES` 和标准 `dockerStartCmd`。

2026-06-06 R2 切换验证结果：

- 本地测试 MinIO 历史对象已镜像到 R2 `user-data-test` 桶根路径：`bot-data-test` 约 1.10GiB，`comfyui-temp-test` 约 749.91MiB，`bot-template-test` 为空。
- 历史样本 key `242/output_images/01c4cd38-e7e9-4587-90e2-f5d15c7a1147.mp4` 在 R2 S3 API 中 HEAD 成功。
- 云端 Web API 容器实际生效：`MINIO_ENDPOINT=<R2 endpoint host>`、`MINIO_BUCKET=user-data-test`、`MINIO_SECURE=true`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`。
- 云端 Web API 使用 R2 预签名 URL 读写烟测通过，预签名 host 为 R2 S3 endpoint，读取状态 200。
- `https://r2-test.aivison.it.com` 已验证可读取新写入 Web 视频结果，例如 `history/<task_id>/original.mp4` 返回 200；云测试 Web owner 视频结果依赖该公网域名完成 `/api/tasks/{task_id}/result` 成功态返回。
- R2 `user-data-test` 已配置 Web 直传 CORS。2026-07-14 为不可变 Pages 测试站补齐 `https://web-cf-test.aivison.it.com` 与 `https://allbot-web-cf-test.pages.dev`，并继续保留 `https://web-test.aivison.it.com`、`https://web.aivison.it.com`；四个 Origin 的 `OPTIONS` 预检均返回 204。以 `https://web-cf-test.aivison.it.com` Origin 执行的真实预签名 `PUT` 与后续 `HEAD` 均返回 200、响应回显精确 `Access-Control-Allow-Origin`，烟测对象随后已删除。更新桶策略时必须保留这四个 Origin 及 `GET/PUT/HEAD`、`AllowedHeaders=["*"]`、`ExposeHeaders=["ETag"]`、`MaxAgeSeconds=3600`，避免前端再次出现 `Network error during upload`。

2026-06-09 边缘测试 Web 切换结果：

- VPS Nginx `web-test.aivison.it.com` 只影响测试静态站和测试 `/api/`，不得修改正式 `web.aivison.it.com`。
- `/api/` upstream 已切到云测试 Tailscale Web API `http://100.82.124.91:8001`。
- 公网 eth0 测试端口已由 `allbot-cloud-test-firewall.service` drop。

2026-06-09 云端测试容器口径：

- 云端核心容器：Postgres、Redis、Central API、Web API、QQCC Config 前后端、imgproxy 和按配置启用的核心 Bot。云端不运行 Dashboard 或 Web 前端 dev 容器；公共测试 Web 由边缘静态站提供，QQCC Config 使用不可变 Nginx 镜像。

## 7. Tailscale 接入边界

- 本地主服务器已安装 Tailscale；云服务器需安装 Tailscale 并加入同一 tailnet。
- 云测试机当前 Tailscale IPv4 为 `100.82.124.91`。
- 推荐给云服务器使用 `tag:allbot-cloud-test`，并用 ACL 只放行本地主服务器与 Web 边缘访问云测试端口。
- 当前不使用 subnet router，不把武汉家庭内网 `192.168.1.0/24` 暴露给云端。
- 云端 PostgreSQL 与 Redis 均为同机 Docker 容器，不发布公网端口。
- 若 Tailscale 不可用，可临时回退 SSH `-L` 转发，或短期使用公网 IP + 源 IP 白名单；后者只允许测试 API 端口，不得开放数据库/缓存端口，恢复后必须收回公网白名单。

## 8. Bot Profile

`bot-test` profile 默认禁止启动。只有确认本地主服务器上的 `tg-bot-test` 已停止，且测试 token 不会双实例冲突时，才允许手动启动：

```bash
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot up -d bot-test
```

云测试 `bot-test` 默认设置 `TON_PAYMENT_POLLING_ENABLED=false`，避免空云测试库启动后回扫真实 TON 商户地址的历史交易并污染测试订单/用户数据。只有需要专门联调 TON 支付履约时，才在 `.env.cloud.test` 中显式设置 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`，并同时提供经确认、通过 TON 地址库校验的 `VITE_MERCHANT_ADDRESS`；缺失或非法地址会在逐服务投影/运行时双层 fail closed。测试环境保持真实链轮询关闭时，可通过 fake upstream 验证 plans、下单 503 和有效地址订单契约。

GPU worker 不在云服务器运行；本地 `workers/docker-compose-cloud-worker-test.yml` 经 `CLOUD_TEST_CONTROL_HOST` 连接云端 Central API，并通过 R2 S3 endpoint 直接读写 `user-data-test`。agent 先把 ComfyUI 结果写入共享 spool，再由不可变发布的本地 relay 上传 R2；两侧默认必须共同挂载宿主机 `/var/lib/allbot/test-worker/spool`，仅在 relay 与全部 agent 同时迁移时才可统一覆盖 `CLOUD_TEST_WORKER_SPOOL_HOST_DIR`。若日志出现 `Upload sidecar returned HTTP 502`，先核对 agent/relay 的 `/app/spool` mount source 是否一致；relay 会以 `upload_asset_attempt_failed` 记录真实异常类型，`FileNotFoundError: spool file not found` 表示共享挂载契约被破坏，而不是 R2 或 ComfyUI 生成失败。

云测试日常可以复用正式可用的 LAN AIO ComfyUI runtime，但 worker 仍注册到云测试 Central，输入/结果仍写测试桶。图片换脸拆分候选中，test-1 指向 `gpu-252` GPU1 的 `8191` `i2i_pro`，承接 `face_swap_v2`、`i2i_pro`、`i2i_draw`、`t2i-pornmaster-turbo`，不得承接 V1；`gpu-252:8192` 当前是 GPU0 `image_to_video`，不能作为 i2i 验收端点。迁移器会把已知旧 `gpu-252` GPU0/8192 test-1 组合原子归一到 GPU1/8191，同时保留其它非已知组合的显式覆盖。发布前实时心跳若仍是旧 `face_swap`，只能作为待排空旧运行态，不能据此改回候选。test-2 指向 `gpu-177:8190` 的 `wan22_video_v2`；test-3 指向 `gpu-177:8191` 的 LTX；test-6 指向 `gpu-226:8188` 的 `img2img_lora` 兼容 runtime；test-7 指向 `gpu-002:8191` 的 `image_to_video`；test-8 指向 `gpu-002:8190` 的 SCAIL-2。共享 AIO worker 默认 `PREFETCH_ENABLED=false`、`PIPELINE_ENABLED=false`、`PIPELINE_MAX_RUNNING_TASKS=1`，避免测试任务并发抢占正式生成容量。test-8 可通过 `.env.cloud.test` 的 `CLOUD_TEST_WORKER_08_TASK_TYPES` 与 `CLOUD_TEST_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES` 做测试专用能力覆盖；当前可把动作迁移 5/8s、动作迁移 10/15/20s 隐藏执行、视频换人、视频换脸 v10 two-stage 分别指向 `SCAIL-2_Animation_multi-char_audio.api.json`、`SCAIL-2_Animation_WAN-Context-Windows.api.json`、`SCAIL-2_Replacement_audio.api.json`、`SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json`。Bot/Web 用户侧只显示一个“动作迁移”，业务提交和历史类型仍是 `scail2_action_transfer`，dispatcher 才按时长把 10/15/20s 送到 `scail2_action_transfer_long`。v10 视频换脸还通过 `CLOUD_TEST_WORKER_08_FACE_SWAP_V10_*` 打开 worker8 预处理：先调用配置的 V2 Comfy API 执行 `face_swap_v2.json` 对驱动视频第一帧做图片换脸，再提交 SCAIL-2 视频换人式 workflow。这只是测试 worker 能力，正式 SCAIL-2 worker 仍按正式发布计划单独变更。

2026-06-18 03:06 只读快照：云测试 Central `queue_size=0`，`active_workers=8`，`healthy_workers=5`，`error_workers=3`，`quarantined_workers=0`。该状态是瞬时运行态；执行测试验收前必须重新查 `/system/workers` 并按目标任务类型确认 worker 健康。

### 8.1 Shared LAN AIO cloud-test worker

`cloud-comfy-agent-test-2..7` 是共享正式 LAN AIO runtime 的云测试 worker，默认不常驻：

| Worker | Profile | 默认 ComfyUI | 任务类型 | 口径 |
| :--- | :--- | :--- | :--- | :--- |
| `cloud_worker_test_02` | `shared-aio-canary` | `192.168.1.177:8190` | `wan22_video_v2` | gpu-177 GPU0 AIO |
| `cloud_worker_test_03` | `shared-aio-canary` | `192.168.1.177:8191` | `ltx_video,*` | gpu-177 GPU1 LTX AIO |
| `cloud_worker_test_04` | `shared-aio-canary` | 默认 `127.0.0.1:9` 占位 | `pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit` | 仅保留旧本地 AIO canary 入口；常规测试不启动 |
| `cloud_worker_test_05` | `wan22-canary` | 无健康默认入口 | `wan22_video_v2` | 默认指向 `127.0.0.1:9` 占位，必须先换成有效 RunPod/LAN endpoint |
| `cloud_worker_test_06` | `shared-aio-canary` | `192.168.1.226:8188` | `img2img,img2img_lora` | 备用 img2img shared runtime |
| `cloud_worker_test_07` | `shared-aio-canary` | `192.168.1.2:8191` | `image_to_video,video_insert,video_edit` | gpu-002 slot1 image_to_video AIO |

启动共享 AIO canary 前，先确认正式队列压力可接受，且目标端口 `/system_stats` 返回 200。真实启动只针对目标服务，不要 `up` 整个 compose：

```bash
COMPOSE_PROFILES=shared-aio-canary docker-compose \
  --env-file .env.cloud.test \
  -f workers/docker-compose-cloud-worker-test.yml \
  up -d --no-deps cloud-comfy-agent-test-2 cloud-comfy-agent-test-3
```

主 Bot 的旧“自由P图 v2”按钮已升级为自由P图 v3：单图先提交 `pornmaster_flux2_edit_bf16`，再以原图为人脸来源提交内部 `face_swap_v2`；整个用户操作统一扣 5 灵石，换脸续接任务不得二次扣费。云测试 Web 发布不负责保证 BF16 或全部 Worker 在线，也不为日常页面验收启动本地 PornMaster LAN AIO；需要专项验证真实生成时，可另行启动云测试 RunPod worker：

```bash
RUNPOD_DRY_RUN=false RUNPOD_AUTOSCALER_ENABLED=true \
python scripts/gpu_pool_controller.py runpod workers scale \
  --profile pornmaster_flux2_edit_bf16 \
  --desired 1 \
  --env cloud-test \
  --env-file .env.cloud.test \
  --execute
```

专项生成验收时，预期云测试 Central `/system/workers` 出现 `runpod_test_pornmaster_flux2_edit_bf16_*`，`runtime_profile=pornmaster_flux2_edit`，types 为 `pornmaster_flux2_edit_bf16`，control 为 `enabled`，且另有健康的 `face_swap` worker；这不是测试 Web 发布门禁。旧 `cloud_worker_test_04` / 本地 LAN AIO canary 只作为专项回归入口；若明确要走本地 AIO，需要覆盖 `cloud_worker_test_04` 并确认不会和当前 `i2i_pro` / 正式任务抢占同一 GPU：

```bash
ENABLE_FREE_EDIT_V2=true
CLOUD_TEST_WORKER_04_RUNTIME_PROFILE=pornmaster_flux2_edit
CLOUD_TEST_WORKER_04_TASK_TYPES=pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit
CLOUD_TEST_WORKER_04_COMFY_API_URL=http://192.168.1.252:8192
CLOUD_TEST_WORKER_04_COMFY_WS_URL=ws://192.168.1.252:8192/ws
```

对应本地 AIO 由 `scripts/lan_pornmaster_flux2_edit_aio_test.sh start --execute` 启动，初始保持测试 agent disabled；确认 `8192` 健康后启用 AIO 自带的 cloud-test agent，不再额外启动 `cloud-comfy-agent-test-4`，避免两个 agent 同时轮询同一个 ComfyUI：

```bash
scripts/lan_pornmaster_flux2_edit_aio_test.sh enable-test-agent --execute
```

结束窗口后立即恢复，避免云测试任务长期占用正式 AIO：

```bash
scripts/lan_pornmaster_flux2_edit_aio_test.sh restore --execute
```

`cloud-comfy-agent-test-5` 不随 `shared-aio-canary` 启动；`wan22_video_v2` 当前默认应走 RunPod canary 或先显式设置 `CLOUD_TEST_WORKER_05_COMFY_API_URL` / `CLOUD_TEST_WORKER_05_COMFY_WS_URL` 到健康 endpoint。

### 8.2 Worker 6/7 GPU pool 控制测试

`cloud-comfy-agent-test-6` 与 `cloud-comfy-agent-test-7` 用于 GPU pool 小范围验证时，可以临时覆盖任务类型、runtime profile 和 Comfy URL；默认配置写在 `.env.cloud.test`，临时命令行覆盖仍可用于一次性 canary：

在改动测试 worker 前，先从 Controller 生成备用端口 canary plan / compose 供审阅；该步骤只渲染 dry-run 输出，不启动或重启任何 ComfyUI 容器：

```bash
python scripts/gpu_pool_controller.py runtime-plan \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic \
  --host-port 8190
python scripts/gpu_pool_controller.py runtime-render \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic \
  --host-port 8190
```

```bash
set -a
source .env.cloud.test
set +a

CENTRAL="http://${CLOUD_TEST_CONTROL_HOST}:8004"
AUTH_HEADER="Authorization: Bearer ${AGENT_SECRET_TOKEN}"

curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"disabled","reason":"gpu-pool canary","ttl_seconds":900}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_06"
curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"draining","reason":"gpu-pool canary","ttl_seconds":900}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_07"

docker ps -aq --filter name=cloud-comfy-agent-test-6 --filter name=cloud-comfy-agent-test-7 \
  | xargs -r docker rm -f

# 该片段是历史 video_basic canary 兼容入口；新视频验证优先使用 canonical image_to_video / wan22_video_v2 split profile。
CLOUD_TEST_WORKER_06_TASK_TYPES='video_insert,image_to_video' \
CLOUD_TEST_WORKER_06_RUNTIME_PROFILE='video_basic_canary' \
CLOUD_TEST_WORKER_06_COMFY_API_URL='http://192.168.1.2:8190' \
CLOUD_TEST_WORKER_06_COMFY_WS_URL='ws://192.168.1.2:8190/ws' \
CLOUD_TEST_WORKER_07_TASK_TYPES='img2img,img2img_lora' \
CLOUD_TEST_WORKER_07_RUNTIME_PROFILE='img2img_lora_canary' \
CLOUD_TEST_WORKER_07_COMFY_API_URL='http://192.168.1.2:8191' \
CLOUD_TEST_WORKER_07_COMFY_WS_URL='ws://192.168.1.2:8191/ws' \
docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml \
  up -d --no-deps cloud-comfy-agent-test-6 cloud-comfy-agent-test-7
```

验证点：

- `/system/workers` 能看到 `cloud_worker_test_06/07` 的 `types`、`node_id=gpu-002`、`gpu_index`、`runtime_profile` 与 `pool_managed=true` 随容器环境更新。
- 备用端口 canary 时，`cloud_worker_test_06/07` 的 `COMFY_API_URL` / `COMFY_WS_URL` 指向当次显式设置的 AIO runtime 端口；如果复用正式 AIO，必须控制任务窗口和并发。
- `disabled/draining` 状态下，带 `agent_id` 的 `/api/agent/task/pop` 返回空任务，不影响其它 worker。
- 本地主服务器旧版 `docker-compose 1.29.2` 可能在 `--force-recreate` 时报 `KeyError: 'ContainerConfig'`；只删除目标 6/7 容器再 `up -d --no-deps`，不要 `--remove-orphans`。

恢复默认状态。当前默认不是重新启动 6/7，而是停止共享 AIO 测试 worker：

```bash
docker ps -aq --filter name=cloud-comfy-agent-test-6 --filter name=cloud-comfy-agent-test-7 \
  | xargs -r docker stop

curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"disabled","reason":"restore shared-aio cloud-test default stopped"}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_06"
curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"disabled","reason":"restore shared-aio cloud-test default stopped"}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_07"
```

## 9. 停止与退役

云测试控制面是当前唯一受支持的测试环境，不再维护“回滚到本地主服务器旧测试栈”的标准方案。需要暂停云测试时，先停测试 Bot，再停本地 cloud-worker 测试栈；云端控制面是否停止取决于当次维护目标。

```bash
docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml stop
ssh allbot-do-sgp1-test-control 'cd /home/deploy/APP/All_bot && docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml --profile bot stop bot-test && docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml --profile qqcc-bot stop qqcc-bot-test'
```

旧本地测试 compose 和 `safe_deploy_test.sh` 仅作为历史迁移/人工取证材料保留。若必须短时启动，应另起临时排障计划，确认不会抢占测试 token、GPU、Redis 队列、对象桶或边缘 `web-test` 入口，结束后立即停止并保留数据。
