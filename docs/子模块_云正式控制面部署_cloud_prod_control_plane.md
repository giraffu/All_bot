# 子模块: 云正式控制面部署 (Cloud Prod Control Plane)

## 1. 当前生产架构事实
截至 2026-06-07 晚间，正式生产已经切到“云控制面 + 托管 PostgreSQL/Valkey + R2 + 本地 GPU worker”的运行口径。

当前长期事实：
- 云控制面 Droplet：`allbot-do-sgp1-control`，运行目录 `/home/deploy/APP/All_bot`。
- 云端 compose：`deploy/docker-compose-cloud-prod.yml`。
- 本地 GPU worker compose：`workers/docker-compose-cloud-prod-worker.yml`。
- 正式对象存储事实源：Cloudflare R2 `user-data-prod`。
- 本地 MinIO：只作为 legacy 历史媒体只读 fallback 和本地热数据保留，不再是新生成结果的公开事实源。
- 本地 GPU/ComfyUI：仍在武汉内网运行，worker 默认通过本机 `cloud-prod-worker-relay` 访问云 Central API；relay 再经 Tailscale 访问云端。
- 公共 Web API 与 RMB 支付入口已经由云端控制面承接；`assets.aivison.it.com` 继续保留 legacy MinIO 只读回源。
- Cloudflare Pages/API Tunnel 测试入口正在按 canary 口径推进：目标是 `web-cf-test.aivison.it.com` 由 Cloudflare Pages 承接，`api-cf-test.aivison.it.com` 通过云机上的 Cloudflare Tunnel 回源云 Web API `100.107.220.127:8000`。Cloudflare 控制台完成前，这两个入口不得视为已上线。

## 2. 服务分布

### 2.1 云端控制面
云端 `deploy/docker-compose-cloud-prod.yml` 承载：

| 服务 | 容器 | 端口口径 | 说明 |
| :--- | :--- | :--- | :--- |
| Central API | `cloud-central-api-prod` | `100.107.220.127:8003` | 执行面、队列、worker heartbeat、状态观测 |
| Web API | `cloud-web-api-prod` | `100.107.220.127:8000` | Web/BFF、任务提交、历史、广场、用户中心 |
| Payment API | `cloud-payment-api-prod` | `100.107.220.127:8021` | RMB 回调与支付结果页 |
| Dashboard Backend | `cloud-dashboard-backend-prod` | `100.107.220.127:8043` | 管理后台 API |
| imgproxy | `cloud-imgproxy-prod` | compose 内部端口 | 图片缩略与代理 |
| Bot | `cloud-tg-bot-prod` | `bot` profile | 正式 Bot polling；必须保证全网单实例 |

云端不长期自托管正式 PostgreSQL、Valkey 或 MinIO；正式库与运行态 Redis/Valkey 使用托管服务或外部服务。

### 2.2 本地执行面
本地主服务器运行云正式 GPU worker 和一个本地 worker relay/上传 sidecar：

| 容器 | 说明 |
| :--- | :--- |
| `cloud-prod-worker-relay` | 本地 worker 网关与上传 sidecar，默认监听 `127.0.0.1:8013`，向云 Central `:8003` 转发 agent API |

| 容器 | AGENT_ID | ComfyUI |
| :--- | :--- | :--- |
| `cloud-prod-comfy-agent-1` | `cloud_prod_worker_01` | `192.168.1.226:8188` |
| `cloud-prod-comfy-agent-2` | `cloud_prod_worker_02` | `192.168.1.177:8188` |
| `cloud-prod-comfy-agent-3` | `cloud_prod_worker_03` | `192.168.1.177:8189` |
| `cloud-prod-comfy-agent-4` | `cloud_prod_worker_04` | `192.168.1.252:8188` |
| `cloud-prod-comfy-agent-5` | `cloud_prod_worker_05` | `192.168.1.252:8189` |
| `cloud-prod-comfy-agent-6` | `cloud_prod_worker_06` | `192.168.1.2:8188` |
| `cloud-prod-comfy-agent-7` | `cloud_prod_worker_07` | `192.168.1.2:8189` |

`cloud-prod-comfy-agent-3` 当前支持 `ltx_video,image_to_video`。该节点对应 `192.168.1.177:8189` / `comfy1`；2026-06-08 已在 ComfyUI 侧补齐 `socksio` 并重启，使 `FL_RIFE` 正常暴露，compose 不再需要 `WAN22_RIFE_NODE_CLASS`。

worker 写入 R2 `user-data-prod`，不得配置 legacy MinIO 写路径。启用 sidecar 时，worker 先把 ComfyUI 结果写入 `/app/spool`，由 `cloud-prod-worker-relay` 上传 R2；只有 sidecar 确认 put 成功后，worker 才调用 Central `/complete`。

GPU 节点上的 ComfyUI 服务不在本 compose 内。`cloud-prod-comfy-agent-*` 只替换本地主服务器上的 worker 容器，不会自动重启 GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI。GPU 节点硬件、容器、模型挂载和单容器运维边界见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。

### 2.3 边缘入口
- `web.aivison.it.com`：静态前端由边缘 VPS 承接，`/api/` 反代到云 Web API。
- `rmb.aivison.it.com`：优先通过 Cloudflare Tunnel 回源到云 Payment API。
- `assets.aivison.it.com`：保留到本地 legacy MinIO 的只读代理，用于历史媒体 fallback。
- `web-cf-test.aivison.it.com`：Cloudflare Pages canary 静态站，构建模式为 `frontend npm run build:cf-test`；只用于小范围人工验收，不切正式用户。
- `api-cf-test.aivison.it.com`：Cloudflare Tunnel canary API 入口，connector 必须运行在 `allbot-do-sgp1-control` 云机，回源 `http://100.107.220.127:8000`；不要复用本地主服务器上的 RMB tunnel。

## 3. 运行态与性能口径

### 3.1 Central 状态观测
- Central 真实任务分发、worker `pop`、状态上报、完成回流仍走实时 Redis/HTTP。
- `/system/status` 与 `/system/workers` 是高频观测接口，不是强一致调度入口。
- Central 在应用生命周期内复用共享 Redis 客户端，避免每个请求新建连接。
- 状态观测快照默认约 10 秒 TTL，最长约 120 秒 stale-while-revalidate；缓存失效刷新中会先返回短时旧快照，避免 Bot/Web/Dashboard 并发轮询拖慢控制面。
- Dashboard worker 监控应以 `healthy_workers`、`error_workers`、`quarantined_workers` 与 `workers_by_status` 判断容量，不要只看 `active_workers`。

### 3.2 Dashboard 统计
- Dashboard 大盘 stats 是重查询路径，后端使用进程内短缓存与 single-flight，避免多人刷新时重复扫大表。
- 前端对 stats 类接口不得强制加 `_t` 缓存击穿参数。
- 队列/worker 轮询保持秒级即可，当前前端监控默认约 2 秒轮询，不应再改成更高频刷新。

### 3.3 Worker 状态回报
- 本地 `cloud-prod-worker-relay` 透明代理 worker 的 `pop/check/peek/complete/heartbeat/task_heartbeat` 到云 Central。非终态 `running` status 可在本地快速 ACK 并合并转发，终态 `complete/failed/cancelled` 必须同步转发成功。
- Worker `complete` 回报是任务成功收口硬依赖，必须保留有限重试；全部失败后进入失败路径。
- Worker 运行态 `status` 上报也有轻量重试，用于减少云网络瞬断导致的监控漏报；status 上报失败不会直接判定生成任务失败。
- Worker 可在当前图生图/换脸类任务执行期间通过 relay 调 Central 只读 `/api/agent/task/peek` 预取同类型下一单输入。`peek` 不会把任务标记 running，真实执行仍以后续 `/pop` 命中的 `task_id` 为准。
- 本地 GPU “停几秒再继续”通常是 ComfyUI/worker 执行链路现象，例如模型/LoRA 加载、WebSocket 终态未及时返回、worker 转 `/history/{prompt_id}` 轮询收口，不应直接归因到 Central `/system/status` 慢。

### 3.4 Web 卡顿与负载判读

2026-06-08 17:10 巡检确认，云正式 Web 卡顿不应直接等同于云 Droplet 负载打满。排查时先拆成五段：

1. 云机内部：`http://100.107.220.127:8000/api/health`、`http://100.107.220.127:8003/system/status`、`http://100.107.220.127:8043/api/health`
2. Web 边缘到云 Web API：在 `100.88.57.122` 上 curl `http://100.107.220.127:8000/api/health`
3. 公网域名：从本地主服务器或用户侧 curl `https://api.aivison.it.com/api/health`，并验证 `https://web.aivison.it.com` Pages 静态站 200
4. 结果/媒体依赖：统计 `cloud-web-api-prod` 的 `Timed out resolving web result R2 URL` 与 `Unexpected object_exists failure`
5. 生成队列：统计 Central Redis pending/running、pending 最老等待时间、`queue_by_type` 与 heartbeat TTL

参考基线：云内通常 5-40ms，Cloudflare Tunnel API 公网约 0.3-0.7s；若云内正常但公网慢，优先查 Cloudflare Tunnel/运营商链路、前端串行请求和 R2/legacy 回源，而不是先重建 Web API。历史边缘 VPS 到云约 0.5s 的基线只适用于回滚或 `web-test`/`assets` 排障。

常见日志信号：
- `cloud-web-api-prod` 高频 `Timed out resolving web result R2 URL`：结果页或历史详情可能卡在 R2 URL 探测，应优先做短超时、缓存或 `pending_result` 快速返回。
- Web 边缘 499 高频集中在 `/api/tasks/{id}/result`、`/api/gallery/posts`、`/api/gallery/my-favorites`、`/api/users/history`：通常是用户端等待过久主动断开。
- `assets.aivison.it.com` 出现 `upstream prematurely closed connection` / `upstream timed out`：legacy MinIO 回源链路不稳，优先查边缘 cache/log 磁盘、Tailscale 到本地 MinIO、真实 object URL。
- `cloud-dashboard-backend-prod` 高频 `Circuit Breaker is OPEN`：管理后台观测或外部余额接口降级，不代表 Central 任务调度一定失败。

## 4. 部署 SOP

### 4.1 云控制面安全部署
首选脚本：

```bash
ssh allbot-do-sgp1-control
cd /home/deploy/APP/All_bot
scripts/safe_deploy_cloud_prod.sh --preflight-only
scripts/safe_deploy_cloud_prod.sh --start-control-plane --with-db-upgrade
```

要求：
- `.env.cloud.prod` 只在服务器本地保存，不得提交、不贴日志。
- `docker compose config` 输出会展开密钥，只能本机查看。
- 有 Alembic 变更时必须确认单 head，并显式执行 `alembic upgrade head`；不要写“容器启动自动迁移”。
- 正式 Bot 重建前必须确认全网只有一个生产 Telegram polling 实例。

### 4.2 云端单服务热修
只改云端某个 COPY 型服务代码时，可以只重建目标服务：

```bash
ssh allbot-do-sgp1-control
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build central-api-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml up -d --no-deps central-api-prod
```

目标 service 可替换为 `web-api-prod`、`dashboard-backend-prod`、`payment-api-prod` 或 `bot-prod`。生产热修前建议先备份被覆盖文件；当前云端运行目录不应假设一定是完整 Git 工作区。

### 4.3 Cloudflare Pages/API Tunnel canary
测试入口迁移分为两个暂停点：

1. 先由人工在 Cloudflare Zero Trust 创建 `allbot-cloud-web-api-canary` tunnel，并把 public hostname `api-cf-test.aivison.it.com` 指向 `http://100.107.220.127:8000`。connector 安装命令含 token，不得贴到聊天、文档或 Git。
2. `api-cf-test` 健康检查 200 后，只热更云端 `web-api-prod` 使 CORS allowlist 生效；不要重建 Central、Payment、Bot、Dashboard 或 worker。
3. 再由人工在 Cloudflare Pages Git 集成创建 `allbot-web-cf-test`，仓库分支 `deploy`，root directory `frontend`，build command 推荐 `npm ci && npm run build:cf-test`，output directory `dist`，环境变量至少设置 `NODE_VERSION=24`。
4. Pages 自定义域名绑定 `web-cf-test.aivison.it.com` 后，执行 canary 验收脚本：

```bash
bash scripts/check_cloudflare_canary.sh
```

历史 canary 验收通过后，2026-06-08 晚间已将正式 `api.aivison.it.com` 切到云机 Cloudflare Tunnel，并将 `web.aivison.it.com` 绑定到 Cloudflare Pages 项目 `allbot-web-prod`。`assets.aivison.it.com` 继续留在 Web/Nginx VPS，作为 legacy MinIO fallback。

### 4.4 本地云正式 worker 更新
worker 镜像 COPY 代码，修改 `workers/comfy_agent` 后必须重建镜像并重建容器。

```bash
set -euo pipefail
set -a
source /home/hfy/APP/All_bot/.env.cloud.prod
set +a

cd /home/hfy/APP/All_bot/workers
services="cloud-prod-worker-relay cloud-prod-comfy-agent-1 cloud-prod-comfy-agent-2 cloud-prod-comfy-agent-3 cloud-prod-comfy-agent-4 cloud-prod-comfy-agent-5 cloud-prod-comfy-agent-6 cloud-prod-comfy-agent-7"
docker-compose -f docker-compose-cloud-prod-worker.yml build $services
docker-compose -f docker-compose-cloud-prod-worker.yml up -d --no-deps $services
```

本地主服务器仍使用旧版 `docker-compose 1.29.2` 时，`up` 可能触发 `KeyError: 'ContainerConfig'`。恢复方式只能清理目标正式 worker 容器和同 service label 残留，不得 `--remove-orphans`，不得删除测试 worker 或本地旧栈：

```bash
for svc in $services; do
  docker rm -f "$svc" 2>/dev/null || true
  docker ps -aq \
    --filter "label=com.docker.compose.project=workers" \
    --filter "label=com.docker.compose.service=$svc" \
    | xargs -r docker rm -f
done
docker-compose -f docker-compose-cloud-prod-worker.yml up -d --no-deps $services
```

worker 正在处理任务时重建会中断该 worker 当前单任务；用户已确认可在需要时直接更新，不要求为此开启全站维护。紧急修复之外，仍建议先看 `/system/status` 和 worker 日志，确认影响范围。

## 5. 验证 Checklist

### 5.1 云控制面
```bash
ssh allbot-do-sgp1-control
CENTRAL=http://100.107.220.127:8003
curl -fsS "$CENTRAL/health"
curl -fsS "$CENTRAL/system/status"
curl -fsS "$CENTRAL/system/workers"
docker inspect cloud-central-api-prod --format 'restart={{.RestartCount}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
```

Web、Payment、Dashboard 验证：
- `https://web.aivison.it.com` Pages 静态站 200，且 JS bundle 指向 `https://api.aivison.it.com/api`
- `https://api.aivison.it.com/api/health`
- `https://api-cf-test.aivison.it.com/api/health` 仅在 canary tunnel 已配置时验证；若未配置，不得把 502 当作云 Web API 故障。
- `https://rmb.aivison.it.com/pay/result`
- Dashboard 登录后系统状态、worker 卡片与大盘统计能刷新。
- Web 卡顿专项需额外记录云内、边缘到云、公网三段延迟，并统计边缘 499、Web R2 result timeout、Dashboard circuit breaker 和 `assets` 回源异常。

### 5.2 Worker
```bash
docker ps --format '{{.Names}}\t{{.Status}}' | rg '^cloud-prod-(worker-relay|comfy-agent-)'
curl -fsS http://127.0.0.1:8013/health
docker logs --since 2m --tail 100 cloud-prod-comfy-agent-1
```

云 Central 应看到：
- `active_workers=7`
- `healthy_workers=7`
- `error_workers=0`
- `quarantined_workers=0`
- Central Redis 中 `comfy:queue:pending`、`comfy:queue:running`、`comfy:task_heartbeat:*` TTL 与 `/system/status` 口径一致
- `cloud-prod-worker-relay` 最近日志无 `relay_forward_failed`、`sidecar_upload_failed`

### 5.3 数据与媒体
- Alembic 当前 head 应与仓库 migration head 一致。
- Gallery/History 热路径索引必须存在，尤其是 `ix_gallery_posts_active_created_at_id`、`ix_history_task_id`、`ix_history_user_id_id_desc`、`ix_user_interactions_user_action_post`。
- 新生成对象写入 R2 `user-data-prod`。
- 旧历史媒体可通过 R2 或 `assets.aivison.it.com` legacy fallback 读取。

## 6. 回滚与事故处理
- 只重建 Central/Web/Dashboard 代码后，若服务异常，优先回滚目标容器代码或恢复热修前备份文件，再只重建目标服务。
- worker 更新后如果单节点异常，可只重建对应 `cloud-prod-comfy-agent-N`；不要全量清理 `workers` project。
- 已经启动云 Bot 并产生新写入后，不做简单整站回滚；走数据核对与定向修复。
- `/system/status` 慢或 Dashboard 卡顿时，先检查 Central 状态观测缓存、托管 Valkey 连接、Dashboard stats 缓存和前端轮询频率，不要把 GPU 生成停顿直接当成控制面故障。
- Web 公网慢但云内健康时，不要优先重启 Web API；先检查 Web 边缘磁盘、Nginx 499/5xx、Cloudflare/Tailscale 链路、R2 result timeout 与 legacy assets 回源。
