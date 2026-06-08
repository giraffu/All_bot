---
name: "allbot-ops-deployment"
description: "处理 Docker Compose 编排、safe_deploy/safe_deploy_test、Alembic 迁移和故障恢复。研发默认先发测试环境，正式发布需用户明确确认。"
---

# AllBot 运维指南与容器管理 (Ops & Deployment)

本技能用于规范 AllBot 的部署、迁移与系统级排障，必须以当前 `safe_deploy.sh` 与 `safe_deploy_test.sh` 的真实流程为准。

## 1. 模块功能描述
- **测试优先部署**：功能研发、联调、修复与配置调整默认先更新隔离测试栈，优先使用根目录 `safe_deploy_test.sh`；只有在用户明确要求正式发布或交付验收通过后，才允许使用 `safe_deploy.sh` 更新生产环境。
- **标准部署入口**：测试环境优先使用 `safe_deploy_test.sh`，生产环境使用 `safe_deploy.sh`，避免手工拼接多个目录的容器命令。
- **云测试控制面入口**：DigitalOcean SGP1 云端测试控制面使用 `scripts/safe_deploy_cloud_test.sh` 与 `deploy/docker-compose-cloud-test.yml`。云端运行 Central API、Web API、Dashboard Backend、imgproxy、测试 Bot，并通过 `CLOUD_TEST_DATABASE_URL` 连接 DigitalOcean 托管 PostgreSQL，通过 `CLOUD_TEST_REDIS_URL`/`CLOUD_TEST_WORKER_REDIS_URL` 连接 DigitalOcean 托管 Valkey；GPU worker 仍在本地主服务器以 `workers/docker-compose-cloud-worker-test.yml` 运行，并经 Tailscale 访问云端 Central API；对象存储事实源为 R2。
- **云正式切换前准备入口**：正式控制面迁云准备使用 `.env.cloud.prod`、`deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`、`scripts/safe_deploy_cloud_prod.sh`、`scripts/start_cloud_prod_worker.sh` 与 `scripts/stop_local_prod_entry_preserve.sh`。这些文件只用于维护窗口前门禁、预启动和保留式停止，不代表正式切流授权；`cloud-tg-bot-prod` 使用 `bot` profile，默认不得启动。云正式 Web API 必须配置非占位 `JWT_SECRET_KEY`，preflight 应在启动前拦截缺失或默认值。
- **云正式当前生产入口**：2026-06-07 晚间正式生产已切到 DigitalOcean 云控制面。云端运行 `cloud-central-api-prod`、`cloud-web-api-prod`、`cloud-payment-api-prod`、`cloud-dashboard-backend-prod`、`cloud-imgproxy-prod` 与 `cloud-tg-bot-prod`；本地运行 `cloud-prod-worker-relay` 与 `cloud-prod-comfy-agent-1..7`，worker 默认先连本机 relay，再由 relay 访问云 Central。云正式长期 SOP 见 `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`。生产热修优先用 `scripts/safe_deploy_cloud_prod.sh` 或 cloud-prod compose 单服务重建，不再默认走旧本地 `safe_deploy.sh`。
- **云正式负载/卡顿排障基线**：2026-06-08 17:10 巡检确认，云控制面本身通常不是第一瓶颈；云内 Web/Central/Dashboard 健康接口可在毫秒级返回，而边缘到云约 0.5s、外部公网访问可到 1.6-2.8s。用户反馈 Web 卡顿时，先做延迟分段、Central Redis pending/running/heartbeat、GPU 利用率、Web R2 result timeout、`assets.aivison.it.com` legacy 回源与边缘 Nginx 499/磁盘检查，再决定是否重建服务或扩容。
- **Cloudflare Pages/API Tunnel 正式入口**：canary 入口为 `web-cf-test.aivison.it.com`/`api-cf-test.aivison.it.com`；正式入口已切为 `web.aivison.it.com` -> Cloudflare Pages 项目 `allbot-web-prod`，`api.aivison.it.com` -> 云机 `allbot-do-sgp1-control` 上的 Cloudflare Tunnel -> `100.107.220.127:8000`。Tunnel connector 必须跑在云机，不能复用本地主服务器的 RMB tunnel；Pages canary 构建用 `frontend npm run build:cf-test`，正式 Pages 构建用 `frontend npm run build:cf-prod` 并指向 `https://api.aivison.it.com/api`。Cloudflare 控制台创建 tunnel、Pages Git 集成和 custom domain 需要人工操作，token 不得贴日志或文档。
- **局域网 GPU SSH 与资源管理**：本地主服务器到 4 台 GPU 节点使用 key-based SSH，Host 别名为 `allbot-gpu-226`、`allbot-gpu-177`、`allbot-gpu-252`、`allbot-gpu-002`；SSH 详情见 `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`，硬件、ComfyUI 容器、模型挂载和单容器运维边界见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。不得把 GPU 节点密码写入 Git、docs、compose 或 `.env.cloud.prod`，需要 root 级远端操作时必须人工确认维护窗口。
- **局域网 GPU ComfyUI 素材清理**：清理 GPU 节点磁盘时优先使用 `scripts/cleanup_lan_comfy_artifacts.sh`，默认 dry-run，必须显式 `--execute` 才删除；当前策略是 `output/temp` 清 60 分钟以前文件，`input` 只清 24 小时以前文件。不要把“只保留最近 1 小时”直接套到 `input`，因为已进入 ComfyUI 队列的 prompt 可能仍引用输入文件。不得清理 `models/custom_nodes/workflows`。
- **云正式旧媒体策略**：新数据写入 R2 `user-data-prod`；旧 `bot-data` 不再要求切换前全量强搬，改用 `scripts/backfill_history_r2_objects.py --visible-scope user-visible --source-storage legacy` 预热用户可见集合，并通过 `LEGACY_MINIO_*` 在 Web API / Dashboard 读路径启用本地 MinIO 只读 fallback。Worker 写路径不得配置 legacy MinIO。预热顺序推荐为原文件 `--media-only`、legacy 缩略图 copy-only、再用 `--source-storage current --generate-missing-thumbnails` 从已预热 R2 原文件生成缺失缩略图；历史详情/Gallery/Wan22 预览必须做返回 URL 可读验收，不能只验 S3 HEAD。
- **云正式边缘入口模板**：`web.aivison.it.com` 正式静态站已切到 Cloudflare Pages，正式 API 健康检查使用 `https://api.aivison.it.com/api/health`；`web.aivison.it.com/api/health` 会返回 Pages SPA HTML，不再是 API 入口。`all_bot_nginx_cloud_prod.conf` 仍必须保留 `assets.aivison.it.com` 到本地 MinIO 的 legacy 代理和 `/root/dist` 回滚副本。RMB 正式入口首选继续使用 Cloudflare Tunnel，当前回源为云 Payment API；如需紧急回滚，用 `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute` 切回本地 Payment API。切换/回滚脚本默认 dry-run，真实执行必须显式 `--execute`。
- **边缘 VPS 资源与运维**：当前边缘层包含 Web/Nginx VPS (`100.88.57.122`/`154.17.30.113`) 与 Telegram Local API VPS (`69.63.220.115`)。Web 节点用 `frontend/ssh_key/id_rsa.pem` 登录，根盘可用空间极低，Nginx cache/log 变更前必须先查 `df -h`；Telegram 节点当前主服务器未配置可用 SSH key，完整排障前需补齐 SSH。详见 `docs/子模块_边缘节点运维指南_edge_node_ops.md`。
- **云测试退役入口**：当云服务器后续只作为正式控制面使用时，使用 `scripts/cleanup_cloud_test_for_prod.sh` 退役云测试。脚本默认 dry-run，真实清理必须 `--execute`；只清云测试容器、本地 `cloud-comfy-agent-test-*`、托管 PostgreSQL `bot_db_test` 与 Valkey DB3/DB4，不删除 R2 `user-data-test`，不改 `web-test.aivison.it.com` 静态站。
- **迁移保护**：部署前检查 Alembic multiple heads；发现多 head 立即中止。
- **宿主机迁移执行**：通过后直接在宿主机执行 `alembic upgrade head`，不依赖容器启动时自动迁移；生产脚本加载 `.env` 后显式导出 `BOT_TYPE=PROD`。
- **分阶段重建**：按 workers -> central api -> 主服务群 -> dashboard -> 生产 Web 边缘静态站的顺序重建/发布。
- **生产单服务重建**：当用户明确要求只重建某个正式服务时，使用目标 compose 目录内的单 service 流程；必须避免全量 `safe_deploy.sh`、避免 `--remove-orphans`、避免旧版 `docker-compose` 直接 `--force-recreate` 触发 `ContainerConfig` 兼容错误。
- **故障恢复**：处理 MinIO 503、Nginx 404/502、容器代码未更新、环境变量未生效等典型问题。
- **测试 worker 变量陷阱**：`workers/docker-compose-test.yml` 内的 `${...}` 插值不会读取 `env_file: ../.env.test`；当前测试 compose 已使用测试桶默认值并让 `AGENT_SECRET_TOKEN` 来自 `env_file`，重建后仍必须核对容器内实际生效变量，避免 401 或读写错误桶。
- **workflow 资产事实源**：`workers/comfy_agent/workflows` 是唯一 workflow 目录。Central API 不再挂载、COPY 或启动校验 workflow；修改 workflow 时默认只更新 Worker 目录，并重建/重启对应 Worker。

## 2. 操作规范
- 修改数据库结构时：
  - 先更新模型
  - 生成 migration
  - 确保只有一个 Alembic head
  - 测试研发阶段先通过 `safe_deploy_test.sh` 或测试库宿主机 Alembic 验证升级
  - 只有在用户明确要求正式发布时，才通过 `safe_deploy.sh` 或生产库宿主机 Alembic 执行升级
- 修改未挂载源码卷的服务代码时：必须 `--build` 重建镜像，不能只 `restart`。
- 功能研发默认目标环境是隔离测试栈或云测试控制面：`.env.test`、`backend/docker-compose-test.yml`、`workers/docker-compose-test.yml`、`deploy/docker-compose-test.yml`，或 `.env.cloud.test` + `deploy/docker-compose-cloud-test.yml`。
- 若用户明确要把测试控制面部署到 DigitalOcean Droplet，使用 `scripts/safe_deploy_cloud_test.sh`。该脚本使用 `.env.cloud.test`，要求 `CLOUD_TEST_DATABASE_URL` 指向 DigitalOcean 托管 PostgreSQL，`CLOUD_TEST_REDIS_URL`/`CLOUD_TEST_WORKER_REDIS_URL` 指向 DigitalOcean 托管 Valkey；云端不再启动容器版 Redis。服务端口默认绑定到云主机 `127.0.0.1`，配置 `CLOUD_TEST_BIND_IP` 后绑定到云服务器 Tailscale IP，`.env.cloud.test` 不得提交。当前云测试对象存储直连 R2：`MINIO_SECURE=true`，`MINIO_BUCKET/MINIO_INPUT_BUCKET/MINIO_RESULT_BUCKET/MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`；Web owner 视频结果依赖 R2 公网 URL，缺失会停在 99% / `pending_result`。Web 直传依赖 R2 桶 CORS，`user-data-test` 必须允许 `web-test.aivison.it.com`/`web.aivison.it.com` 的 `GET/PUT/HEAD`。
- 云测试公网 Web 入口继续使用 `web-test.aivison.it.com` 的边缘 VPS 静态站；前端静态资源由 `frontend npm run deploy:edge-test` 发布到 `web` VPS `/root/dist-test`，VPS Nginx 的 `/api/` 必须反代到云端测试 Web API `http://100.107.220.127:8001`。
- 云端全链路切换前，先用 `scripts/stop_local_test_preserve.sh` 停止本地主服务器原测试栈但保留数据，再用 `scripts/start_cloud_worker_test.sh` 启动 7 个 `cloud-comfy-agent-test-*` 本地 GPU worker。
- 云测试 `bot-test` 默认禁用 TON 链上支付轮询；若需要支付联调，先确认测试库 checkpoint 与通知目标，再通过 `.env.cloud.test` 显式设置 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`。
- 云正式准备阶段先运行 `scripts/safe_deploy_cloud_prod.sh --preflight-only`、`scripts/start_cloud_prod_worker.sh --preflight-only` 和 `scripts/stop_local_prod_entry_preserve.sh --dry-run`；真正预启动控制面需显式传 `--start-control-plane`，worker 需显式传 `--start`，本地正式入口停止需显式传 `--execute`。
- 云正式当前生产热修阶段，云端控制面代码更新优先在 `allbot-do-sgp1-control:/home/deploy/APP/All_bot` 备份文件后同步，再用 `docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build <service>` 与 `up -d --no-deps <service>` 替换目标服务。真实 `docker compose config` 输出不得贴出。
- Cloudflare canary 阶段只允许为 CORS allowlist 热更 `web-api-prod`；先确认 `api-cf-test.aivison.it.com/api/health` tunnel 可达，再重建 Web API。验收使用 `bash scripts/check_cloudflare_canary.sh`；未通过前不得切 `web.aivison.it.com` 或正式 `api.aivison.it.com`。
- 云测试退役阶段先运行 `scripts/cleanup_cloud_test_for_prod.sh --dry-run` 核对对象；真实清理时传 `--execute`，不得同时执行正式切流、正式 Bot 启动或边缘 Nginx reload。
- 云正式 `.env.cloud.prod` 不得提交；所有真实密钥只能来自该忽略文件。`.dockerignore` 必须忽略 `.env.*`，避免 root Docker image 把私有云正式变量 COPY 进镜像。
- 云正式迁移期若启用 `LEGACY_MINIO_*`，必须确认 `LEGACY_MINIO_PUBLIC_URL` 是浏览器可读 URL；该配置只用于历史媒体读取 fallback，不是新数据写入目标。
- 云正式 compose 渲染会展开密钥；真实 `docker compose config` 输出不得贴到日志、文档或聊天中。
- 云正式首发 worker 只包含 7 个 `cloud-prod-comfy-agent-*`；`worker_remote_01/02` 未纳入首发时，必须确认没有独占任务类型缺口。
- 云正式支付控制若仅依赖现有 Web `MAINTENANCE`，Bot RMB/Stars callback 仍可能创建订单；本轮正式切换口径已确认接受该低频风险。维护窗口先只开启 Web 维护状态并等待当前队列自然归零，不立即停止本地 Bot 或旧 worker；最终 dump 前再停止本地 Bot/旧入口，并导出 `orders` 中 `PENDING`/`CREATED` 待处理订单最终快照。
- 测试完成前，不得默认重建生产 Bot、生产 Web API、生产 Payment API、生产 Central API 或正式 Dashboard。
- 交付前必须把“测试环境已验证通过、准备正式发布”作为显式阶段切换条件，不得自行跳过用户验收。
- 若重建本地隔离测试 worker，必须额外核对容器内实际生效的 `AGENT_SECRET_TOKEN`、`MINIO_INPUT_BUCKET=bot-data-test`、`MINIO_RESULT_BUCKET=comfyui-temp-test`；不要误以为 compose `${...}` 插值会自动读取 `.env.test` 的 `env_file` 值。若重建云测试 cloud-worker，则核对 `MINIO_ENDPOINT=<R2 endpoint host>`、`MINIO_INPUT_BUCKET=user-data-test`、`MINIO_RESULT_BUCKET=user-data-test`、`MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_SECURE=true`。
- 修改 workflow JSON、`mappings.json` 或 workflow patcher 时，默认以 `workers/comfy_agent/workflows` 为运行时事实源；Central API 不再维护 backend 副本，也不再执行 workflow 启动校验。
- 云正式 Central 高频观测接口使用共享 Redis 客户端与短 TTL/stale 缓存；Dashboard stats 也有短缓存和 single-flight。排查管理后台卡顿时先区分 Central 观测慢、Dashboard stats 慢和本地 GPU/ComfyUI 生成停顿。
- 云正式 Web 卡顿不要只看 `docker stats`。必须同时比较：云机内 `100.107.220.127:8000/8003/8043`、Web 边缘到云 upstream、公网 `web.aivison.it.com` 三段耗时；若云内毫秒级但公网秒级，优先查边缘/Cloudflare/Tailscale/运营商链路和 API 串行请求。
- 云正式结果页/历史/Gallery 卡顿要优先查 `cloud-web-api-prod` 的 `Timed out resolving web result R2 URL` 与 `Unexpected object_exists failure`，以及 Web 边缘 `assets.aivison.it.com` 的 `upstream prematurely closed` / `upstream timed out`。这些问题会表现为 `/api/tasks/{id}/result`、Gallery、History 的 499 或用户端等待超时。
- 云正式 Dashboard 卡顿要统计 `cloud-dashboard-backend-prod` 中 `Circuit Breaker is OPEN`，并区分 Central 观测接口、外部余额接口和 Dashboard stats 缓存失效；不要把 Dashboard 熔断直接当作任务调度失败。
- 云正式队列压力要看 Central Redis 事实：`comfy:queue:pending`、`comfy:queue:running`、`comfy:task_heartbeat:*` TTL、pending 最老等待时间和 `queue_by_type`。`healthy_workers=7` 且 heartbeat TTL 正常时，pending 增长通常是容量/任务类型分布或视频长尾耗时，不是 worker 离线。
- 云正式 worker compose 包含本地 relay/上传 sidecar。更新 `workers/comfy_agent`、`workers/local_relay`、`worker_requirements.txt` 或 worker compose 时，测试 canary 需额外验证 relay `/health`、`relay_forward_failed`/`sidecar_upload_failed` 日志、R2 上传成功后才 `/complete`，以及 Central `/system/workers` 无 error/quarantined。
- 远程登录局域网 GPU 节点时默认使用 SSH Host alias，不在命令、日志或文档中输出密码；当前 4 台 GPU 节点均不是免密 sudo，驱动、系统服务、Docker daemon 或 ComfyUI 服务级修改应先确认维护窗口。
- `cloud-prod-comfy-agent-*` 是本地主服务器上的 worker 容器，GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI 是另一层。替换 worker 不会自动重启 ComfyUI；重启 ComfyUI 也不会替换 worker 代码。
- 双卡 GPU 节点的 `comfy0/comfy1` 绑定不同 GPU 和不同 `inst0/inst1` 输入输出目录，但共享模型目录。排障或更新功能时只能操作目标 worker/目标 Comfy 容器；禁止因为一个容器异常而整机 reboot、无 service 名 `docker compose down/up` 或批量删除所有 Comfy 容器。
- `allbot-gpu-226` 的 ComfyUI 是宿主机进程，cwd 为 `/home/ubantu/comfyui`，不是 Docker Comfy 容器；不要对它执行 `docker restart comfy0`。
- GPU 节点模型下载、Docker pull/build 或大视频输出前必须重新检查 `df -hT`；2026-06-08 已清理 ComfyUI 旧素材，但 `input/output/temp` 会持续增长。
- ComfyUI 旧素材清理要优先走 `scripts/cleanup_lan_comfy_artifacts.sh` 并先 dry-run；双卡节点通过 `comfy0/comfy1` 容器内路径分别清理，`allbot-gpu-226` 走宿主机 `/home/ubantu/comfyui/{input,output,temp}`。生产环境不建议把 `input` 保留窗口降到 1 小时。

### 2.1 生产单服务重建标准流程
用户明确要求“只重建某个正式服务”时，先确认目标 service 存在，再按以下规则处理：

1. **加载生产环境变量再运行 compose**：`env_file` 只传给容器，不参与 compose 文件里的 `${...}` 插值；进入 `workers/`、`backend/`、`dashboard/` 等子目录执行生产 compose 前，必须先 `source /home/hfy/APP/All_bot/.env` 并 `export BOT_TYPE=PROD`。
2. **先 build，后替换目标容器**：先执行 `docker-compose build <service>`；构建成功后，只删除目标 service 的精确容器或 compose label 残留，再执行 `docker-compose up -d --no-deps <service>`。
3. **不要直接 force recreate**：当前宿主机可能使用 `docker-compose 1.29.2`，对新镜像元数据直接执行 `docker-compose up -d --no-deps --build --force-recreate <service>` 可能报 `KeyError: 'ContainerConfig'`。若已经触发该错误，只清理目标 service 的残留容器后重试，不要清理整组服务。
4. **不要清理 orphan**：workers 目录下测试栈容器可能被正式 compose 识别为 orphan。除非用户明确要求清理测试栈，否则不要加 `--remove-orphans`。
5. **避免误伤全组服务**：单服务重建时禁止执行未带 service 名的 `docker-compose rm -fsv`、`docker-compose up -d --build` 或 `docker rm -f $(docker ps -a -q -f name=comfy-agent)`。

生产 `comfy-agent-2` 这类 worker 的推荐流程：

```bash
set -euo pipefail
set -a
source /home/hfy/APP/All_bot/.env
export BOT_TYPE=PROD
set +a

cd /home/hfy/APP/All_bot/workers
docker-compose config --services | rg '^comfy-agent-2$'
docker-compose build comfy-agent-2
docker rm -f comfy-agent-2 2>/dev/null || true
docker ps -aq \
  --filter "label=com.docker.compose.project=workers" \
  --filter "label=com.docker.compose.service=comfy-agent-2" \
  | xargs -r docker rm -f
docker-compose up -d --no-deps comfy-agent-2
```

若目标 worker 正在处理任务，非紧急情况下应先告知用户会中断该 worker 当前任务，并尽量等待任务完成或确认可以中断；正式全量发布仍走 `safe_deploy.sh` 的队列门禁流程。

云正式 `cloud-prod-comfy-agent-*` 的当前热更新流程：

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

本地主服务器旧版 `docker-compose 1.29.2` 可能在 recreate 时触发 `KeyError: 'ContainerConfig'`。恢复时只删除目标 `cloud-prod-comfy-agent-*` 容器和同 service label 残留，再 `up -d --no-deps`；禁止 `--remove-orphans`，禁止清理测试 worker 或旧本地 worker。用户已确认云正式 worker 热更新可不启用全站维护；这只会中断被重建 worker 当时正在跑的单任务。

## 3. 核心红线
- 不要在普通功能研发过程中默认执行 `safe_deploy.sh`、生产 compose 或任何正式环境重建动作。
- 不要把“帮我改功能/修 Bug/做联调”自动理解为“允许正式部署”；除非用户明确提出上线、交付、发布、同步生产。
- 不要再写“容器下次启动会自动应用 Alembic 变更”，这不是当前标准流程。
- 不要在存在 multiple heads 的情况下继续部署。
- 不要让生产 Alembic 迁移依赖 `config.py` 的默认 `BOT_TYPE`；生产脚本应显式 `BOT_TYPE=PROD`，测试脚本显式 `BOT_TYPE=TEST`。
- 不要忽略卷挂载差异直接判断“代码已生效”。
- 不要把 `docker restart` 当作代码发布手段，特别是 `web-api`、Dashboard、CS Bot 等 COPY 型服务。
- 不要把 `env_file` 与 compose `${...}` 插值混为一谈；测试 worker 的 compose 默认值必须保持测试环境口径，重建后用 `docker exec <worker> env` 核对。
- 不要在单服务生产重建时使用 `--remove-orphans`、无 service 名的 compose 命令或全组 `docker rm` 过滤器；只允许清理目标 service 的容器和同 service label 残留。
- 不要把 workflow 放到 Central API 或 backend 目录后期待 Worker 执行；必须更新 `workers/comfy_agent/workflows` 并确认目标 Worker 支持该 task type。
- 不要默认启动云端 `bot-test` profile；除非已经确认本地主服务器的 `tg-bot-test` 停止，避免同一个测试 Telegram token 双实例冲突。
- 不要默认启动 `cloud-tg-bot-prod`；云正式控制面预启动只包含 Central/Web/Payment/Dashboard/imgproxy，正式 Bot polling 必须留到边缘入口切换和本地 Bot 停止之后。
- 云正式已切流后，重建 `cloud-tg-bot-prod` 前必须确认本地旧正式 Bot 已停止且全网无第二个同 token polling 实例；不要把准备阶段“不得启动 Bot”的规则误用为当前生产必须停 Bot。
- 不要把 cloud-prod 准备脚本当成正式切流授权；`safe_deploy_cloud_prod.sh` 不会 reload 边缘 Nginx，`stop_local_prod_entry_preserve.sh` 默认 dry-run，正式维护窗口仍需用户明确确认。
- 不要用云测试退役脚本清 R2 `user-data-test` 或边缘 `web-test.aivison.it.com`；这两个资源若要清理必须另起单独计划。
- 不要把云端 Tailscale 接入做成 subnet router；当前只允许本地主服务器访问云端测试端口，不暴露武汉家庭内网。

## 4. 测试与验证
- 测试研发阶段先验证隔离测试栈健康检查、关键 API 可达、测试库/测试 Redis/测试中控链路正确。
- 只有在测试环境完成功能验证并得到用户确认后，才进入正式环境部署验证。
- 验证 migration 在空库可顺利 `upgrade head`。
- 验证重建后容器确实运行的是新镜像，而不是旧容器旧代码。
- 云测试控制面验证至少包括 `docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps`，以及 `8004/health`、`8001/api/health`、`8044/api/health` 三个健康检查；全链路还要确认 `/system/workers` 能看到 7 个 `cloud_worker_test_*` heartbeat。
- 云正式准备验证至少包括：cloud-prod control compose config、worker compose config、`.env.cloud.prod` 占位值/重复 key/`API_TOKEN == AUTH_TOKEN` 检查、R2 `user-data-prod` list/head、Telegram Local Bot API reachability，以及 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health` 健康检查。正式 Bot profile 不在准备阶段启动。
- 云正式当前生产验证至少包括：云端 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health`，公共 `https://web.aivison.it.com` Pages 静态站、`https://api.aivison.it.com/api/health` 与 `https://rmb.aivison.it.com/pay/result`，本机 relay `127.0.0.1:8013/health`，Central `/system/status` 与 `/system/workers`，`cloud-prod-worker-relay` 与 7 个 `cloud-prod-comfy-agent-*` `RestartCount=0`，以及最近日志无高频 `ERROR/Traceback/Exception`。Web 卡顿专项还要记录云内 API、公网 API、Pages 静态站、R2/legacy 媒体与任务队列等待，统计 Web R2 result timeout、Dashboard circuit breaker 与 `assets` 回源异常。
- Cloudflare canary 验证至少包括：`https://api-cf-test.aivison.it.com/api/health` 200、从 `Origin: https://web-cf-test.aivison.it.com` 发起的 OPTIONS preflight 2xx、`https://web-cf-test.aivison.it.com` 静态站 200、登录态 Authorization 跨域 API 正常、任务状态流不被缓存、Gallery/History/结果页仍可读 legacy assets。
- 边缘节点验证至少包括：Web VPS `nginx -t`、`systemctl is-active nginx tailscaled`、`df -h /`、`assets.aivison.it.com` 根路径/真实对象回源；正式 Web 静态站验证走 Cloudflare Pages 的 `https://web.aivison.it.com`，正式 API 验证走 `https://api.aivison.it.com/api/health`。Telegram Local API 节点在 SSH 未补齐前只能验证 22/8081/8082 端口可达，不能声称已验证容器日志或磁盘。
- 若测试 worker 涉及认证或对象存储，额外验证实际生效的 `AGENT_SECRET_TOKEN`、输入桶和结果桶与目标环境一致；云测试 R2 直连还要验证 R2 S3 `list/head`、Web API 预签名 URL 读取 200，以及从 `https://web-test.aivison.it.com` Origin 发起的 R2 `PUT` CORS 预检返回 204/200。
- 生产单服务重建后必须验证：目标容器 `Up`、`RestartCount=0`、最近日志无 `ERROR/Traceback/Exception`、关键非敏感环境变量符合正式口径。worker 需额外确认 heartbeat、Central API、ComfyUI WebSocket、MinIO 桶名正常；日志和总结中不要输出密钥值。
- GPU 节点单容器操作后必须验证：目标 ComfyUI `/system_stats`、`/queue`、对应 worker Central heartbeat，以及未操作的另一 ComfyUI 端口仍可用。双卡节点上只重启 `comfy0` 时必须确认 `comfy1` 未受影响，反之亦然。
