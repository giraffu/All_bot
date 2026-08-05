# 子模块：本地正式灾备切换

## 1. 适用范围

本地主服务器只在云正式控制面整体不可用且短时间无法恢复时临时接管生产。日常研发、测试、热修和发布不得使用本方案。

切换前必须接受 shadow 数据的 RPO，确认生产 Telegram Bot 全网只有一个 polling 实例，并取得本次生产变更的明确授权。

## 2. 当前边界

| 层级 | 云正式 | 本地灾备 |
| :--- | :--- | :--- |
| Bot/Web/Payment/Central/Dashboard | `allbot-do-sgp1-control` | 本地主服务器正式 compose |
| 数据库/缓存 | 云 PostgreSQL/Valkey | 最近一次 `bot_db_prod_shadow`；缓存运行态不恢复 |
| 对象存储 | R2 `user-data-prod` | 继续使用 R2；`user-data-prod-shadow` 只用于离线校验 |
| Web 静态站 | Cloudflare Pages | 保持 Pages，不切换静态站 |
| Web/Payment 公网入口 | Cloudflare Tunnel 回源云端 | 修改 Tunnel 回源到本地主服务器 |
| GPU worker | 本地 worker 接云 Central | 本地 worker 接本地 Central |

本地灾备不是第二套长期生产。云端恢复后应尽快回切并对账。

## 3. 切换前检查

```bash
ssh allbot-do-sgp1-control 'hostname && docker ps --format "{{.Names}}\t{{.Status}}"'
curl -fsS --max-time 8 https://api.aivison.it.com/api/health
curl -fsS --max-time 8 https://rmb.aivison.it.com/healthz
curl -fsS --max-time 8 http://100.107.220.127:8003/health
```

若云端仍可登录，先停止云正式 Bot，避免同 token 双实例。随后停止 `allbot-cloud-prod-shadow-sync.timer`，核对最近一次 `backups/cloud-prod-shadow/<timestamp>/manifest.json`、数据库版本、关键表行数和 R2 shadow 抽样对象。

若云端仍可读且时间允许，可先执行一次最终同步：

```bash
cd /home/hfy/APP/All_bot
scripts/sync_cloud_prod_to_local_shadow.py
scripts/sync_cloud_prod_to_local_shadow.py --execute
```

脚本默认 dry-run。`R2_BUCKET_SYNC_ENABLED=true` 时仅把 R2 同步到本地 shadow；本地对象桶不作为应用运行时回源。

灾备启用写入前必须备份现有本地数据库，再由人工明确把 `bot_db_prod_shadow` 提升为本地写库。订单、余额、任务历史和用户写入必须在回切时对账。

## 4. 启动本地服务

按服务边界启动，先不启动 Bot；API、外部入口和 worker 验证完成后再启动 Bot。

```bash
cd /home/hfy/APP/All_bot
set -a
source .env
export BOT_TYPE=PROD
set +a

docker-compose -f backend/docker-compose.yml up -d --build api
docker-compose -f deploy/docker-compose.yml up -d --build web-api payment-api imgproxy
docker-compose -f dashboard/docker-compose.yml up -d --build dashboard-backend dashboard-frontend
docker-compose -f workers/docker-compose.yml up -d --build \
  comfy-agent-1 comfy-agent-2 comfy-agent-3 comfy-agent-4 \
  comfy-agent-5 comfy-agent-6 comfy-agent-7
```

确认本地 Central 能看到 worker 后，再启动 Bot：

```bash
curl -fsS http://127.0.0.1:8003/system/status
docker-compose -f deploy/docker-compose.yml up -d --build bot
```

旧 `safe_deploy.sh` 只允许在已授权的本地灾备窗口使用，不是云正式发布入口。

## 5. 切换公网入口

保持 `web.aivison.it.com` 在 Cloudflare Pages。仅在 Cloudflare Zero Trust 中将 `api.aivison.it.com` 的 public hostname 回源改到本地主服务器可达的 Web API。

RMB 使用专用回滚脚本：

```bash
scripts/rollback_rmb_tunnel_to_local_prod.sh --dry-run
scripts/rollback_rmb_tunnel_to_local_prod.sh --execute
```

切换后验证：

```bash
curl -fsS https://api.aivison.it.com/api/health
curl -fsS https://web.aivison.it.com
curl -fsS https://rmb.aivison.it.com/healthz
```

所有媒体仍必须通过 R2 公网域名或 R2/S3 短签访问。

## 6. 回切

1. 使用 `scripts/release.py status` 逐模块核对云端 live identity，并验证
   Web/Central/Payment/Dashboard；旧 full-stack preflight 已退役。
2. 冻结本地新增写入，导出灾备期间订单、用户资产和任务历史。
3. 停止本地 Bot，恢复 Web/Payment Tunnel 云端回源。
4. 启动云正式 Bot 与本地 cloud worker。
5. 停止本地灾备入口但保留数据：

```bash
scripts/stop_local_prod_entry_preserve.sh --execute --include-workers
```

6. 完成数据对账后恢复 shadow timer。

## 7. 禁止事项

- 禁止同时运行本地与云端生产 Bot。
- 禁止把测试数据库、Redis、桶或 token 混入灾备栈。
- 禁止把本地 shadow 桶配置成正式应用回源。
- 禁止清理 R2、MinIO、数据库或备份来“腾空间”。
- 禁止把本地灾备长期运行成第二套生产。
