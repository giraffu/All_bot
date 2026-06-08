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

worker 写入 R2 `user-data-prod`，不得配置 legacy MinIO 写路径。启用 sidecar 时，worker 先把 ComfyUI 结果写入 `/app/spool`，由 `cloud-prod-worker-relay` 上传 R2；只有 sidecar 确认 put 成功后，worker 才调用 Central `/complete`。

### 2.3 边缘入口
- `web.aivison.it.com`：静态前端由边缘 VPS 承接，`/api/` 反代到云 Web API。
- `rmb.aivison.it.com`：优先通过 Cloudflare Tunnel 回源到云 Payment API。
- `assets.aivison.it.com`：保留到本地 legacy MinIO 的只读代理，用于历史媒体 fallback。

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

### 4.3 本地云正式 worker 更新
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
- `https://web.aivison.it.com/api/health`
- `https://rmb.aivison.it.com/pay/result`
- Dashboard 登录后系统状态、worker 卡片与大盘统计能刷新。

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
