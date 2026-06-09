# 子模块: 本地正式灾备切换 (Local Prod Fallback)

## 1. 目标与触发条件
本文档是本地主服务器保留的唯一“临时替代正式服务”方案。它只在云正式控制面整体不可用、且短时间无法恢复 `allbot-do-sgp1-control`、Cloudflare Tunnel 或托管数据库/Valkey 时使用。

正常研发、联调、缺陷修复和配置验证不得使用本文档；默认目标仍是云测试控制面。正常生产热修也不得使用本地旧 `safe_deploy.sh`，应走云正式 compose 或 `scripts/safe_deploy_cloud_prod.sh`。

触发前必须确认：
- 云正式 Web API、Central API、Payment API 或 Bot 已经无法满足生产入口。
- 已决定接受本地灾备的 RPO/RTO 风险：本地 PostgreSQL/Redis 不是云正式库的实时同步副本。
- 有权限切换 Cloudflare Tunnel、Pages/DNS 或边缘 Nginx。
- 可以保证生产 Telegram Bot token 全网只有一个 polling 实例。

## 2. 当前生产与灾备边界

| 层级 | 当前正式 | 本地灾备 |
| :--- | :--- | :--- |
| Bot/Web/Payment/Central/Dashboard | 云 Droplet `allbot-do-sgp1-control` | 本地主服务器旧正式 compose |
| 数据库/缓存 | 云正式 PostgreSQL/Valkey | 本地 `.env` 指向的 PostgreSQL/Redis；必要时先从云备份恢复 |
| 新对象存储 | R2 `user-data-prod` | 仍优先保持 R2；本地 MinIO 只做 legacy fallback |
| GPU worker | 本地 `cloud-prod-comfy-agent-*` 接云 Central | 本地旧 `comfy-agent-*` 接本地 Central |
| Web 静态站 | Cloudflare Pages `web.aivison.it.com` | 优先保留 Pages；把 API base/origin 切到本地 Web API，或临时回滚到边缘 VPS `/root/dist` |
| Web API 入口 | `api.aivison.it.com` Tunnel -> 云 Web API | Tunnel/边缘回源 -> 本地 `127.0.0.1:8000` 或本地主机 Tailscale IP |
| RMB 支付入口 | `rmb.aivison.it.com` Tunnel -> 云 Payment API | `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute` -> 本地 `127.0.0.1:8021` |

本地灾备不是第二套长期生产。它用于让服务临时恢复可用，云端恢复后应尽快回切云正式并做数据对账。

## 3. 切换前检查

### 3.1 确认云端故障范围
```bash
ssh allbot-do-sgp1-control 'hostname && docker ps --format "{{.Names}}\t{{.Status}}"'
curl -fsS --max-time 8 https://api.aivison.it.com/api/health
curl -fsS --max-time 8 https://rmb.aivison.it.com/pay/result
curl -fsS --max-time 8 http://100.107.220.127:8003/health
```

若云端仍可登录，先停止云正式 Bot，避免同 token 双实例：

```bash
ssh allbot-do-sgp1-control '
  cd /home/deploy/APP/All_bot &&
  docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml --profile bot stop bot-prod
'
```

若云端不可登录，切本地 Bot 前必须通过 Telegram 侧症状、云端健康检查和容器状态残缺程度共同确认云 Bot 已不可用或需要被替代。

### 3.2 数据口径确认
本地 `.env` 必须是生产口径，且不得把测试库、测试 Redis 或测试桶混进本地正式栈。

```bash
set -a
source /home/hfy/APP/All_bot/.env
export BOT_TYPE=PROD
set +a
```

旧本地正式 compose 仍保留若干历史硬编码默认值和占位值，尤其是 `backend/docker-compose.yml`、`dashboard/docker-compose.yml` 与 `workers/docker-compose.yml`。因此灾备切换前不能只看 `.env` 文件是否正确，还必须本机核对 compose 渲染和容器内实际环境变量，确认 Central API、Dashboard、worker 的 `AUTH_TOKEN`/`AGENT_SECRET_TOKEN`、数据库、Redis、对象存储桶和 `BOT_TYPE=PROD` 均为正式口径。`docker compose config` 和 `docker exec <container> env` 输出可能包含密钥，只能在本机查看，不得贴到聊天、日志或文档。

计划内切换时，优先从云正式 PostgreSQL 做最终 dump 并恢复到本地 `bot_db`，再启动本地写入口。云端完全不可用时，只能使用本地现有数据快照，后续必须对订单、余额、任务历史和用户写入做人工对账。

### 3.3 停止会抢资源的本地 cloud worker
若本地旧正式 worker 将接管本地 Central，先停云正式 worker，释放 GPU 容量：

```bash
docker-compose --env-file .env.cloud.prod -f workers/docker-compose-cloud-prod-worker.yml stop \
  cloud-prod-worker-relay \
  cloud-prod-comfy-agent-1 cloud-prod-comfy-agent-2 cloud-prod-comfy-agent-3 \
  cloud-prod-comfy-agent-4 cloud-prod-comfy-agent-5 cloud-prod-comfy-agent-6 \
  cloud-prod-comfy-agent-7
```

测试 worker 如仍运行，也应停掉：

```bash
docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml stop
```

## 4. 启动本地正式服务

推荐按服务边界启动，先不启动 Bot，等 API 和外部入口切好后再启动 Bot。

```bash
cd /home/hfy/APP/All_bot
set -a
source .env
export BOT_TYPE=PROD
set +a

docker-compose -f backend/docker-compose.yml up -d --build api
curl -fsS http://127.0.0.1:8003/health

docker-compose -f deploy/docker-compose.yml up -d --build web-api payment-api imgproxy
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8021/pay/result
curl -fsS http://127.0.0.1:8084/health

docker-compose -f dashboard/docker-compose.yml up -d --build dashboard-backend dashboard-frontend
curl -fsS http://127.0.0.1:8043/api/health

docker-compose -f workers/docker-compose.yml up -d --build \
  comfy-agent-1 comfy-agent-2 comfy-agent-3 comfy-agent-4 \
  comfy-agent-5 comfy-agent-6 comfy-agent-7
```

确认本地 Central 能看到 worker 后，再启动 Bot：

```bash
curl -fsS http://127.0.0.1:8003/system/status
docker-compose -f deploy/docker-compose.yml up -d --build bot
```

`safe_deploy.sh` 只允许在本地正式灾备或旧本地正式维护窗口中使用。该脚本会重建本地 worker、Central、Bot/Web/Payment、Dashboard，并发布旧边缘静态站；它不是当前云正式生产的发布入口。

## 5. 切换公网入口

### 5.1 Web API
当前正式前端 `web.aivison.it.com` 是 Cloudflare Pages，生产包默认调用 `https://api.aivison.it.com/api`。灾备时有两种方式，优先选一种执行，不要同时改多处。

方式 A：在 Cloudflare Zero Trust 将 `api.aivison.it.com` public hostname 回源改到本地主服务器可达地址，例如本机 cloudflared 或 Tailscale/边缘可达的本地 Web API。适合本地主服务器仍有可用 Tunnel 的场景。

方式 B：临时回滚到 Web/Nginx 边缘 VPS `/root/dist`，让 `web.aivison.it.com /api/` 通过 Tailscale 回源本地 `100.99.254.53:8000` 或实际本地主机 Tailscale IP。执行前必须备份 `/etc/nginx/sites-enabled/all_bot` 并 `nginx -t`。

无论哪种方式，健康检查都使用：

```bash
curl -fsS https://api.aivison.it.com/api/health
curl -fsS https://web.aivison.it.com
```

### 5.2 RMB 支付入口
本地主服务器已有 RMB Tunnel 回滚脚本，默认 dry-run，真实切换必须显式 `--execute`：

```bash
cd /home/hfy/APP/All_bot
scripts/rollback_rmb_tunnel_to_local_prod.sh --dry-run
scripts/rollback_rmb_tunnel_to_local_prod.sh --execute
curl -fsS https://rmb.aivison.it.com/pay/result
```

### 5.3 assets 与历史媒体
`assets.aivison.it.com` 继续走 Web/Nginx VPS 到本地 MinIO 的 legacy fallback。不要在灾备切换时清理 MinIO、Nginx cache 或 R2 对象。历史媒体验收必须测试真实 object URL，不能只看 `assets` 根路径 403/200。

## 6. 验证 Checklist

本地：
```bash
docker ps --format '{{.Names}}\t{{.Status}}' | rg '^(api|web-api|payment-api|tg-bot|dashboard-|comfy-agent-)'
curl -fsS http://127.0.0.1:8003/health
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8021/pay/result
curl -fsS http://127.0.0.1:8043/api/health
curl -fsS http://127.0.0.1:8003/system/workers
```

公网：
```bash
curl -fsS https://api.aivison.it.com/api/health
curl -fsS https://web.aivison.it.com
curl -fsS https://rmb.aivison.it.com/pay/result
```

业务：
- Telegram Bot 能响应 `/start` 或核心菜单。
- Web 登录、历史页、提交小图任务、结果页可走通。
- RMB 支付结果页可打开，回调日志无高频失败。
- Dashboard 能登录并刷新系统状态。
- `tg-bot` 与 `cloud-tg-bot-prod` 不得同时运行。

## 7. 回切云正式

云端恢复后不要直接“把流量切回去就结束”。先冻结本地新增写入或进入维护模式，导出本地灾备期间的订单、用户资产、任务历史和必要日志，评估是否需要补数据到云正式库。

回切顺序：
1. 云端 `scripts/safe_deploy_cloud_prod.sh --preflight-only`。
2. 云端 Web/Central/Payment/Dashboard 健康检查。
3. 停止本地 `tg-bot`，确认全网无第二个生产 Bot polling。
4. 将 `api.aivison.it.com` 与 `rmb.aivison.it.com` 回源恢复到云端。
5. 启动或重建 `cloud-tg-bot-prod`。
6. 启动本地 `workers/docker-compose-cloud-prod-worker.yml` 的 cloud worker。
7. 停止本地旧正式 compose 入口，但保留数据：

```bash
scripts/stop_local_prod_entry_preserve.sh --execute --include-workers
```

回切后验证清单以 `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` 为准。

## 8. 禁止事项
- 禁止把本地灾备当成日常测试环境。
- 禁止本地 Bot 与云 Bot 同时使用同一个生产 token polling。
- 禁止在未确认数据口径时启动本地写入口。
- 禁止在灾备窗口清理本地 PostgreSQL、Redis、MinIO、R2 或 Nginx cache。
- 禁止用 `safe_deploy.sh` 更新当前云正式生产。
- 禁止把 `.env`、`.env.cloud.prod`、Tunnel token、Bot token 或 R2 密钥写入文档、日志或聊天。
