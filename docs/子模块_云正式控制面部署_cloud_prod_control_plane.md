# 子模块: 云正式控制面部署 (Cloud Prod Control Plane)

## 1. 当前生产架构事实
截至 2026-06-18，正式生产已经切到“云控制面 + 托管 PostgreSQL/Valkey + R2 + 本地 GPU worker / 手动 RunPod 备用池”的运行口径。

当前长期事实：
- 云控制面 Droplet：`allbot-do-sgp1-control`，运行目录 `/home/deploy/APP/All_bot`。
- 云控制面规格：DigitalOcean SGP1 Basic Regular `$96/mo`，8 vCPU / 16GB RAM / 320GB SSD。
- 云端 compose：`deploy/docker-compose-cloud-prod.yml`。
- 本地 GPU worker compose：`workers/docker-compose-cloud-prod-worker.yml`。
- 正式对象存储事实源：Cloudflare R2 `user-data-prod`。
- 本地 MinIO：只作为 legacy 迁移补齐、人工回滚、旧外链排障和本地热数据保留，不再是新生成结果或正式 Web/Dashboard 运行时读路径的公开事实源。
- 本地 GPU/ComfyUI：仍在武汉内网运行，worker 默认通过本机 `cloud-prod-worker-relay` 访问云 Central API；relay 再经 Tailscale 访问云端。
- 公共 Web API 与 RMB 支付入口已经由云端控制面承接；`assets.aivison.it.com` 继续保留到 legacy MinIO 的只读代理，但正式应用不再生成该域名 URL。
- Cloudflare Pages/API Tunnel 已成为正式入口：`web.aivison.it.com` 由 Pages 项目 `allbot-web-prod` 承接，`api.aivison.it.com` 通过云机上的 Cloudflare Tunnel 回源云 Web API `100.107.220.127:8000`。历史 `web-cf-test`/`api-cf-test` 仅作为 canary/归档语义，不再是迁移待办。
- 当前容量判断口径：本地 compose 声明 `cloud-prod-comfy-agent-1..7`，但实际线上 worker 还可能包含 LAN AIO、`remote_workers` 与手动 RunPod。2026-06-18 03:06 快照为 `active_workers=13`、`healthy_workers=13`、`error_workers=0`、`quarantined_workers=0`；该数字只代表当时运行态，不写成固定长期容量。

## 2. 服务分布

### 2.1 云端控制面
云端 `deploy/docker-compose-cloud-prod.yml` 承载：

| 服务 | 容器 | 端口口径 | 说明 |
| :--- | :--- | :--- | :--- |
| Central API | `cloud-central-api-prod` | `100.107.220.127:8003` | 执行面、队列、worker heartbeat、状态观测 |
| Web API | `cloud-web-api-prod` | `100.107.220.127:8000` | Web/BFF、任务提交、历史、广场、用户中心 |
| Payment API | `cloud-payment-api-prod` | `100.107.220.127:8021` | RMB 回调与支付结果页 |
| Dashboard Backend | `cloud-dashboard-backend-prod` | `100.107.220.127:8043` | 管理后台 API |
| Dashboard Frontend | `cloud-dashboard-frontend-prod` | `100.107.220.127:8086` | 管理后台云端 Nginx 前端，同源反代 Dashboard Backend |
| imgproxy | `cloud-imgproxy-prod` | compose 内部端口 | 图片缩略与代理 |
| Bot | `cloud-tg-bot-prod` | `bot` profile | 正式 Bot polling；必须保证全网单实例 |

云端不长期自托管正式 PostgreSQL、Valkey 或 MinIO；正式库与运行态 Redis/Valkey 使用托管服务或外部服务。

正式核心 R2 / RunPod 变量口径：

```bash
MINIO_ENDPOINT=c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com
MINIO_BUCKET=user-data-prod
MINIO_INPUT_BUCKET=user-data-prod
MINIO_RESULT_BUCKET=user-data-prod
MINIO_TEMPLATE_BUCKET=user-data-prod
MINIO_SECURE=true
MINIO_PUBLIC_URL=
R2_BUCKET=user-data-prod
R2_PUBLIC_DOMAIN=https://r2.aivison.it.com
RUNPOD_PROD_GPU_TYPE_IDS=NVIDIA GeForce RTX 4090
RUNPOD_MODEL_BUCKET=allbot-model-cache
RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10
RUNPOD_MODEL_MANIFEST_KEY=img2img_lora/2026-06-10/manifest.json
```

正式变量分层：

| 变量 | 当前值或来源 | 作用 |
| :--- | :--- | :--- |
| `MINIO_*` / `R2_*` | `user-data-prod` + `https://r2.aivison.it.com` | 正式新生成对象、Web 媒体、历史/Gallery 读取与 worker 结果上传事实源 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `.env.cloud.prod` 真实值；RunPod Pod 内使用 `allbot_cloud_prod_r2_access_key` / `allbot_cloud_prod_r2_secret_key` secret | 只读写 `user-data-prod`，不得用于模型缓存 |
| `MEMBERSHIP_SETTLEMENT_V2_ENABLED` / `AFFILIATE_MEMBERSHIP_REDEEM_ENABLED` | `true` | 正式 Web 与 Bot 的 affiliate 返佣兑身份硬开关；缺失或为 false 会让用户看到“返佣兑换身份功能未开启”，正式 preflight 必须阻断 |
| `RUNPOD_PROD_AGENT_SECRET_TOKEN_REF` | `{{ RUNPOD_SECRET_allbot_cloud_prod_agent_secret_token }}` | 正式 RunPod Pod 访问 Central agent API 的 token 引用 |
| `RUNPOD_PROD_R2_ACCESS_KEY_REF` / `RUNPOD_PROD_R2_SECRET_KEY_REF` | `{{ RUNPOD_SECRET_allbot_cloud_prod_r2_access_key }}` / `{{ RUNPOD_SECRET_allbot_cloud_prod_r2_secret_key }}` | 正式 RunPod Pod 读写 `user-data-prod` 的 secret 引用 |
| `RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO` / `RUNPOD_USE_TEMPLATE_IMAGE_TO_VIDEO` | `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` / `false` | 正式 `image_to_video` split profile 的 RunPod 镜像；不得继承旧 `WAN22_AIO` template/image |
| `RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2` / `RUNPOD_USE_TEMPLATE_WAN22_VIDEO_V2` | `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` / `false` | 正式 `wan22_video_v2` split profile 的 RunPod 镜像；不得继承旧 `WAN22_AIO` template/image |
| `RUNPOD_MODEL_BUCKET` / `RUNPOD_MODEL_PREFIX` / `RUNPOD_MODEL_MANIFEST_KEY` | `allbot-model-cache` + profile-specific manifest | 手动正式 RunPod `img2img` 使用 `img2img_lora/2026-06-10/manifest.json`；`image_to_video` 使用 `image_to_video/2026-06-13-test/manifest.json`；`wan22_video_v2` 使用 `wan22_video_v2/2026-06-13-test/manifest.json`；`i2i_pro` 使用 `i2i_pro/2026-06-14-test/manifest.json`；`scail2` 使用 `scail2/2026-06-17-test/manifest.json` |
| `RUNPOD_MODEL_ACCESS_KEY_REF` / `RUNPOD_MODEL_SECRET_KEY_REF` | `{{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}` / `{{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}` | RunPod Pod 同步 `allbot-model-cache` 的 secret 引用，可与云测试共用模型缓存 secret |
| `GITHUB_TOKEN` / `GHCR_TOKEN` / `all-github-token` | `.env.cloud.prod` 可保存真实值作为人工密钥来源 | 只用于本机 `docker login ghcr.io`、GHCR push 或 GitHub package 管理；不属于云正式服务容器运行时变量，不进入 RunPod Pod env |

`.env.cloud.prod` 不应保存 Cloudflare `cfat_...` API token，也不应把真实 R2 key、GitHub/GHCR token 写入知识库、日志或 `docker compose config` 输出。当前环境文件中出现的 `all-github-token` 带中划线，不能被 `source .env.cloud.prod` 导出为 shell 变量；需要推 GHCR 时应临时映射到 `GHCR_TOKEN` 或 `GITHUB_TOKEN` 后执行 `docker login ghcr.io`，并在 push 后用空 `DOCKER_CONFIG` 匿名验证 package public。正式 RunPod `prod-worker` 代码入口已支持 `--profile img2img`、`--profile image_to_video`、`--profile wan22_video_v2`、`--profile i2i_pro` 与 `--profile scail2` 五条手动备用路径；真实创建、启用或 canary 生产任务仍必须由用户明确确认并满足 RunPod 门禁。

`prod-worker --profile i2i_pro` 使用 `runpod_prod_i2i_pro_manual_NN` agent 和 `allbot-runpod-prod-i2i-pro-manual-NN` Pod 名称，固定请求 `NVIDIA GeForce RTX 4090`，生产 Pod 不开启 SSH。该 profile 的 `SUPPORTED_TASK_TYPES` 为 `i2i_pro,t2i-pornmaster-turbo,face_swap`，并通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 将 `t2i-pornmaster-turbo` 指向 `txt2img_from_i2i_pro.json`、`face_swap` 指向 `face_swap_v2.json`。`prod-worker` heartbeat 等待默认 `3600s`，覆盖 i2i_pro 首次同步约 36GiB 模型的启动窗口；生产 canary 会串行提交 `i2i_pro`、Web `txt2img` 与 `face_swap` 三单，全部由 `runpod_prod_i2i_pro_manual_NN` 接单并出图后才可启用接正式队列。

`prod-worker --profile scail2` 使用 `runpod_prod_scail2_manual_NN` agent 和 `allbot-runpod-prod-scail2-manual-NN` Pod 名称，固定请求 `NVIDIA GeForce RTX 4090`，生产 Pod 不开启长期 SSH。该 profile 的 `SUPPORTED_TASK_TYPES` 为 `scail2_action_transfer,scail2_video_replacement`，模型从 `allbot-model-cache/scail2/2026-06-17-test/manifest.json` 同步，用户输入和结果只写 `user-data-prod`。生产 canary 会串行提交 `scail2_action_transfer 5s` 与 `scail2_video_replacement 5s` 两单，全部由 `runpod_prod_scail2_manual_NN` 接单并返回可播放 MP4 后，才可与 LAN SCAIL-2 并行 enable。当前长期口径是：`scail2` RunPod 已具备代码、镜像、模型 manifest 与 Dashboard 管理入口，但不是必须常驻的正式容量；没有 heartbeat 或已删除的 `manual_NN` 不能当作可用 worker。SCAIL-2 正式主路径仍以 gpu-002 slot0 LAN runtime 为准，RunPod 只作为手动备用/临时扩容。

RunPod 正式手动 worker 的“启动”和“接单”是两层：`prod-worker up --execute`
只创建/启动 Pod 并等待 disabled heartbeat；`prod-worker enable --execute` 才把
Central agent control 切到 `enabled` 并允许接正式队列。`disable --execute`
只停接新单不关 Pod，适合保留现场；`down --execute` 会删除 Pod，必须确认目标
worker 没有 `current_task_id`。旧 Pod 原地重启可能复用
`/workspace/allbot/repo` 中已有的 `remote_workers` bundle；修复 workflow/override 后，
新建 Pod 会拉最新 `deploy`，已有旧 Pod 则先 disable 再更新远端 repo 或重建。

正式手动 RunPod 池的容量和 profile 组合按当次运维目标决定，不记录为固定长期事实；
某次实操的 Pod 数量、创建日期和 profile 组合只应进入运维日志或工单。
日常新增容量统一使用 `scripts/runpod_prod_ops.sh add --profile <profile> --count <N> --execute`；
它只创建空闲 `manual_NN` slot，不删除、缩容或重建已有 slot。`scale --desired N` 是高级精确目标数入口，
会删除超出 desired 的 slot，Dashboard 禁止使用。真实 mutation 必须显式设置
`RUNPOD_DRY_RUN=false` 与 `RUNPOD_AUTOSCALER_ENABLED=true`；`RUNPOD_MAX_PODS_TOTAL`、
`RUNPOD_MAX_PODS_PER_TYPE`、`RUNPOD_MAX_HOURLY_COST_USD` 不再作为 provider/Dashboard 的容量门禁。
若目标 slot 超过默认手动 slot 上限，只在本次命令环境中临时设置
`RUNPOD_PROD_MAX_MANUAL_SLOTS=<slot上限>`。如果 RunPod 返回
`There are no instances currently available`，优先对同一个 profile/count 使用
`scripts/runpod_prod_ops.sh add --retry-unavailable --max-attempts N --retry-interval SEC --execute`
做有界重试；不要并发启动多条相同 profile/count 的创建循环。底层 prod-worker 会按 profile
持有文件锁，并在每个 slot create 前重新读取 RunPod 列表；发现目标 `manual_NN` 已被占用会在写
Central control 和创建 Pod 前中止。最终验收以 `reconcile.managed_count` 按目标变化、
`orphans=[]`、每个目标 worker heartbeat 存在且 control state 符合预期为准。详细启动、
停接、删除和缩容命令见 `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` 的
“手动云正式备用 worker”。

### 2.2 本地执行面
本地主服务器保留云正式本地 worker compose 和一个本地 worker relay/上传 sidecar。compose 声明 `cloud-prod-comfy-agent-1..7`，但线上实际启停可以按任务容量、LAN AIO 接管、`remote_workers` 和手动 RunPod 状态调整；容量验收应以 `/system/workers` 的目标 worker 集合为准。

| 容器 | 说明 |
| :--- | :--- |
| `cloud-prod-worker-relay` | 本地 worker 网关与上传 sidecar，默认监听 `127.0.0.1:8013`，向云 Central `:8003` 转发 agent API |

| 容器 | AGENT_ID | ComfyUI |
| :--- | :--- | :--- |
| `cloud-prod-comfy-agent-1` | `cloud_prod_worker_01` | `192.168.1.226:8188` |
| `cloud-prod-comfy-agent-2` | `cloud_prod_worker_02` | 已退役；原 `192.168.1.177:8188` 已由 `lan_aio_prod_gpu177_gpu0_image_to_video_01` / AIO `8190` 替换 |
| `cloud-prod-comfy-agent-3` | `cloud_prod_worker_03` | 已退役；原 `192.168.1.177:8189` 已由 `lan_aio_prod_gpu177_gpu1_ltx_video_01` / AIO `8191` 替换 |
| `cloud-prod-comfy-agent-4` | `cloud_prod_worker_04` | `192.168.1.252:8188` |
| `cloud-prod-comfy-agent-5` | `cloud_prod_worker_05` | 原 `192.168.1.252:8189`，现为 stopped rollback baseline；正式 `wan22_video_v2` 由 `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` 接管 |
| `cloud-prod-comfy-agent-6` | `cloud_prod_worker_06` | `192.168.1.2:8188` |
| `cloud-prod-comfy-agent-7` | `cloud_prod_worker_07` | `192.168.1.2:8189` |

2026-06-18 03:06 本地主服务器 Docker 快照中，`cloud-prod-worker-relay` 以及 `cloud-prod-comfy-agent-1/2/3/5` 处于运行状态，`cloud-prod-comfy-agent-4/6/7` 已退出或由其它接入形态承担容量。不要仅凭本地 compose 表判断线上可用 worker 数；先查 Central `/system/workers`。

运行态分层口径：

| AGENT_ID | Worker Agent 管理 | ComfyUI Runtime | Runtime 纳管口径 |
| :--- | :--- | :--- | :--- |
| `cloud_prod_worker_01` | 本地主服务器 `cloud-prod-comfy-agent-1` 容器 | `gpu-226:8188` 宿主机进程，cwd `/home/ubantu/comfyui` | `comfy_runtime_kind=host_service`，不要执行 `docker restart comfy0` |
| `cloud_prod_worker_02/03` | 已退役，本地主 `cloud-prod-comfy-agent-2/3` 容器已删除 | `gpu-177` 的旧 `comfy0/comfy1` 与 `/data/comfy` 已删除 | control 固定 `disabled`；gpu-177 恢复走 AIO restart/recreate 或外部容量兜底 |
| `cloud_prod_worker_04` | 本地主服务器 agent 容器 | `gpu-252` 的 `comfy0` Docker 容器 | 只在维护窗口按目标容器操作 |
| `cloud_prod_worker_05` | 本地主服务器 agent 容器，当前 stopped rollback | `gpu-252` 的旧 `comfy1` Docker 容器，当前 stopped rollback | 正式 `wan22_video_v2` 已由 `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` / AIO `8191` 接管；回滚前不要重新 enabled |
| `cloud_prod_worker_06/07` | 本地主服务器 agent 容器 | `gpu-002` 的 `comfy0/comfy1` Docker 容器 | 保留为 compose/热回滚口径；gpu-002 slot0/slot1 也可能被 LAN AIO 或 SCAIL-2 runtime 接管，操作前先查当前 Central agent 与本机容器状态 |

`POOL_IMAGE_REF`、`runtime_profile`、`node_id` 等 heartbeat/compose 字段是 GPU pool 观测与期望配置声明，不等于底层 ComfyUI runtime 已经被替换成该镜像。确认某个 ComfyUI 的真实运行方式时，以 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`、SSH 盘点和 Comfy `/system_stats` 为准。

历史 `cloud-prod-comfy-agent-3` / `192.168.1.177:8189` 曾用于 `ltx_video,image_to_video`，并在 2026-06-08 补齐过 `socksio` / `FL_RIFE` 环境。2026-06-20 后该旧链路已退役删除；当前 gpu-177 的 LTX 正式入口是 `lan_aio_prod_gpu177_gpu1_ltx_video_01` / AIO `8191`。

worker 写入 R2 `user-data-prod`，不得配置 legacy MinIO 写路径。启用 sidecar 时，worker 先把 ComfyUI 结果写入 `/app/spool`，由 `cloud-prod-worker-relay` 上传 R2；只有 sidecar 确认 put 成功后，worker 才调用 Central `/complete`。

无法接入 Tailscale 的旧远程 GPU 服务器可使用根目录 `remote_workers/` 的独立 venv 包接入：远程主机只需 sparse-checkout 该目录，即可启动本机 `remote_relay` 与 bundled `comfy_agent`；如仍保留旧 agent，则把旧 agent 的 `MASTER_API_URL` 指向 `127.0.0.1:8013`。该路径要求使用独立 Cloudflare Tunnel worker 专用域名回源云 Central `:8003`，不得复用 `api.aivison.it.com`，并需继续使用 R2 `user-data-prod` 写路径。2026-06-12 正式云机已新增独立 `cloudflared-runpod-prod.service`，使用 root-only token file，回源 `http://100.107.220.127:8003`，作为 RunPod production worker Central connector；已有 `cloudflared-worker-central.service` 仍保持运行，`https://worker-central.aivison.it.com/health` 当前可直接访问正式 Central。

GPU 节点上的 ComfyUI 服务不在本 compose 内。`cloud-prod-comfy-agent-*` 只替换本地主服务器上的 worker 容器，不会自动重启 GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI。GPU 节点硬件、容器、模型挂载和单容器运维边界见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。

### 2.3 边缘入口
- `web.aivison.it.com`：静态前端由 Cloudflare Pages 项目 `allbot-web-prod` 承接，生产前端调用 `https://api.aivison.it.com/api`。
- `api.aivison.it.com`：Cloudflare Tunnel 连接器运行在 `allbot-do-sgp1-control`，回源 `http://100.107.220.127:8000`。
- `worker-central.aivison.it.com`：远程 worker / RunPod worker 专用 Central 入口，回源 `http://100.107.220.127:8003`；不得用于 Web API，也不得启用会拦截 worker 请求的 Cloudflare Access 登录页。RunPod-Prod 独立 tunnel 若使用新 hostname，需在 Cloudflare Public Hostname 中绑定到 `cloudflared-runpod-prod.service` 对应 tunnel。
- `rmb.aivison.it.com`：Cloudflare Tunnel 回源到云 Payment API `http://100.107.220.127:8021`；紧急切回本地 Payment API 使用 `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute`。
- `assets.aivison.it.com`：保留到本地 legacy MinIO 的只读代理，仅用于人工回滚、旧外链和迁移补齐排障；正式 Web/Dashboard 运行时不应生成该域名 URL。
- 管理后台云端前端：默认仅通过 Tailscale/受控来源访问 `http://100.107.220.127:8086/`。若需要公网域名，必须通过 Cloudflare Tunnel 回源该地址，并启用 Cloudflare Access 身份校验、管理员 allowlist/MFA；禁止把 `8086` 或 `8043` 直接暴露到公网。
- `web-test.aivison.it.com`：独立云测试环境的公网 Web 入口，由 Web/Nginx VPS 提供静态站并反代云测试 Web API `100.82.124.91:8001`。
- `web-cf-test.aivison.it.com` / `api-cf-test.aivison.it.com`：历史 canary 入口；若保留，仍不得复用本地主服务器 RMB tunnel。

## 3. 运行态与性能口径

### 3.1 Central 状态观测
- Central 真实任务分发、worker `pop`、状态上报、完成回流仍走实时 Redis/HTTP。
- `/system/status` 与 `/system/workers` 是高频观测接口，不是强一致调度入口。
- Central 在应用生命周期内复用共享 Redis 客户端，避免每个请求新建连接。
- 状态观测快照默认约 10 秒 TTL，最长约 120 秒 stale-while-revalidate；缓存失效刷新中会先返回短时旧快照，避免 Bot/Web/Dashboard 并发轮询拖慢控制面。
- Dashboard worker 监控应以 `healthy_workers`、`error_workers`、`quarantined_workers` 与 `workers_by_status` 判断容量，不要只看 `active_workers`。

### 3.1.1 PostgreSQL / Valkey 容量与连接池口径
- 托管 PostgreSQL 当前按 `max_connections=100`、`superuser_reserved_connections=3` 估算，可用业务连接约 `97`。
- 2026-06-16 云控制面扩到 8C16G 后，生产连接池采用“增强但不贴顶”的预算，目标峰值约 `73/97`：Web API `4 * (6+6) = 48`，Dashboard Backend `6+4 = 10`，Payment API `4+3 = 7`，Bot `4+4 = 8`。
- 本轮只提升 DB 连接池，不同时提高 `uvicorn --workers` 或 Dashboard `gunicorn -w`，避免进程数和连接池同时放大。
- Bot 必须显式设置 `DB_POOL_SIZE=4`、`DB_MAX_OVERFLOW=4`，避免继续继承 `.env.cloud.prod` 的较小默认值。
- 托管 Valkey 当前近期观测约 73MB/2GB、connected_clients 约 53，且无 blocked/rejected/evicted；本轮不提升 Valkey 规格或客户端池参数。
- 若后续确认 PostgreSQL CPU、IO、锁等待和 idle-in-transaction 长期很轻，可单独评估把峰值预算升至 `80-85`，不要和 Web worker 数调整混在同一个短维护窗口。

### 3.2 Dashboard 统计
- Dashboard 大盘 stats 是重查询路径，后端使用进程内短缓存与 single-flight，避免多人刷新时重复扫大表。
- 前端对 stats 类接口不得强制加 `_t` 缓存击穿参数。
- 队列/worker 轮询保持秒级即可，当前前端监控默认约 2 秒轮询，不应再改成更高频刷新。
- 单独重建 `cloud-dashboard-backend-prod` 后，`cloud-dashboard-frontend-prod` 的 Nginx 可能仍持有旧 backend 容器 IP，表现为 `/api/*` 502 且日志里 upstream 指向旧 `172.*` 地址；优先执行 `docker exec cloud-dashboard-frontend-prod nginx -s reload`，再复查 `http://100.107.220.127:8086/api/health`。

### 3.3 Worker 状态回报
- 本地 `cloud-prod-worker-relay` 透明代理 worker 的 `pop/check/peek/complete/heartbeat/task_heartbeat` 到云 Central。非终态 `running` status 可在本地快速 ACK 并合并转发，终态 `complete/failed/cancelled` 必须同步转发成功。
- Worker `complete` 回报是任务成功收口硬依赖，必须保留有限重试；全部失败后进入失败路径。
- Worker 运行态 `status` 上报也有轻量重试，用于减少云网络瞬断导致的监控漏报；status 上报失败不会直接判定生成任务失败。
- 2026-06-10 巡检发现 Central Redis 写连接偶发 `ConnectionResetError: Connection lost`，可导致 `/status/{task_id}` 或 worker heartbeat/status 短暂 500；这不是队列停摆证据，但应作为 P1 后续修复，在 Central Redis 关键读写路径增加有限 retry/reconnect，并覆盖 `/status/{task_id}`、`task_heartbeat`、`status` focused tests。
- Worker 可在当前图生图/换脸类任务执行期间通过 relay 调 Central 只读 `/api/agent/task/peek` 预取同类型下一单输入。`peek` 不会把任务标记 running，真实执行仍以后续 `/pop` 命中的 `task_id` 为准。
- 本地 GPU “停几秒再继续”通常是 ComfyUI/worker 执行链路现象，例如模型/LoRA 加载、WebSocket 终态未及时返回、worker 转 `/history/{prompt_id}` 轮询收口，不应直接归因到 Central `/system/status` 慢。

### 3.4 Web 卡顿与负载判读

2026-06-08 17:10 巡检确认，云正式 Web 卡顿不应直接等同于云 Droplet 负载打满。排查时先拆成五段：

1. 云机内部：`http://100.107.220.127:8000/api/health`、`http://100.107.220.127:8003/system/status`、`http://100.107.220.127:8043/api/health`
2. Web 边缘到云 Web API：在 `100.88.57.122` 上 curl `http://100.107.220.127:8000/api/health`
3. 公网域名：从本地主服务器或用户侧 curl `https://api.aivison.it.com/api/health`，并验证 `https://web.aivison.it.com` Pages 静态站 200；管理后台若已配置受保护域名，还要验证 Access 登录后可访问 Dashboard Frontend
4. 结果/媒体依赖：统计 `cloud-web-api-prod` 的 `Timed out resolving web result R2 URL` 与 `Unexpected object_exists failure`
5. 生成队列：统计 Central Redis pending/running、pending 最老等待时间、`queue_by_type` 与 heartbeat TTL

参考基线：云内通常 5-40ms，Cloudflare Tunnel API 公网约 0.3-0.7s；管理后台云端前端可省掉本地主服务器静态资源和本地网关到云端的额外链路。若云内正常但公网慢，优先查 Cloudflare Tunnel/Access、运营商链路、前端串行请求和 R2 公开域名/短签，而不是先重建 Web API。历史边缘 VPS 到云约 0.5s 的基线只适用于回滚或 `web-test`/`assets` 排障。

常见日志信号：
- `cloud-web-api-prod` 高频 `Timed out resolving web result R2 URL`：结果页或历史详情可能卡在 R2 URL 探测，应优先做短超时、缓存或 `pending_result` 快速返回。
- Web 边缘 499 高频集中在 `/api/tasks/{id}/result`、`/api/gallery/posts`、`/api/gallery/my-favorites`、`/api/users/history`：通常是用户端等待过久主动断开。
- `assets.aivison.it.com` 出现 `upstream prematurely closed connection` / `upstream timed out`：只影响人工回滚、旧外链或迁移排障链路；优先查边缘 cache/log 磁盘、Tailscale 到本地 MinIO、真实 object URL，同时确认正式 Web/Dashboard 响应没有返回 `assets` URL。
- `cloud-dashboard-backend-prod` 高频 `Circuit Breaker is OPEN`：管理后台观测或外部余额接口降级，不代表 Central 任务调度一定失败。

## 4. 部署 SOP

### 4.1 云控制面安全部署
首选从本地主服务器执行更保守的维护式更新脚本，默认 dry-run，真实 mutation 必须同时传 `--execute --confirm-prod`：

```bash
cd /home/hfy/APP/All_bot
scripts/update_cloud_prod_with_maintenance.sh
scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod --with-db-upgrade
```

该脚本默认流程：
1. 在远端写 `runtime/cloud-prod/GENERATION_MAINTENANCE`，并在正在运行的 `cloud-web-api-prod` / `cloud-tg-bot-prod` 内写 `/app/GENERATION_MAINTENANCE`，只阻止新生成任务提交。
2. 等待 Central `comfy:queue:pending` 与 `comfy:queue:running` 同时清空；不取消任务、不退款、不清 Redis。
3. `rsync` 同步本地代码到 `allbot-do-sgp1-control:/home/deploy/APP/All_bot`，默认不使用 `--delete`，并排除 `.env*`、`logs/`、`runtime/`、`backups/`、`node_modules/`、`bin/cloudflared`、临时素材等本地数据目录。
4. 默认不更新 `.env.cloud.prod`；只有显式传 `--sync-env --env-file FILE` 时才会先备份远端 env、同步并做 checksum 校验。
5. 远端先执行 `scripts/safe_deploy_cloud_prod.sh --preflight-only`，再按 scope 执行控制面发布或单服务热修。
6. 默认不启动/重建正式 Bot；如需 Bot，必须显式传 `--bot-mode auto|start|stop`，且执行前确认全网没有第二个生产 Telegram polling 实例。
7. 默认不发布 Cloudflare Pages、不中断本地 worker、不操作 RunPod、不改 DNS/Tunnel；这些能力仍按独立 SOP 处理。
8. 验证云内健康检查、公网正式入口、本地 worker relay、Central queue/status/workers、目标容器 restart count 与最近错误日志，成功后解除生成维护；失败时维护保持开启。

常用参数：
- `--scope control-plane`：默认，使用 `scripts/safe_deploy_cloud_prod.sh --start-control-plane` 更新 Central/Web/Payment/Dashboard/imgproxy。
- `--scope services --services "web-api-prod dashboard-backend-prod"`：只重建指定云端服务；禁止把 `bot-prod` 放入 `--services`。
- `--with-db-upgrade`：随 `--scope control-plane` 显式执行 Alembic upgrade head；有迁移时必须走控制面发布并传该参数。
- `--sync-env --env-file FILE`：显式同步正式 env；默认不动远端 `.env.cloud.prod`。
  同步前本地 env 必须包含 `MEMBERSHIP_SETTLEMENT_V2_ENABLED=true` 与 `AFFILIATE_MEMBERSHIP_REDEEM_ENABLED=true`，否则脚本会在本地中止，避免覆盖掉正式 affiliate 返佣兑身份入口。
- `--keep-maintenance`：成功后仍保留生成维护，便于人工验收后再解除。
- `--delete`：给 rsync 增加 `--delete`，默认关闭，避免生产远端误删未纳入同步的人工文件。

远端控制面子步骤仍可手工执行：

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
- `cloud-web-api-prod` 与 `cloud-tg-bot-prod` 挂载 `../runtime/cloud-prod:/app/runtime-flags`，并通过 `GENERATION_MAINTENANCE_FILE=/app/runtime-flags/GENERATION_MAINTENANCE` 读取持久生成维护标记；这保证控制面重建后新容器仍保持维护，直到脚本最后解除。

### 4.2 云端单服务热修
只改云端某个 COPY 型服务代码时，可以只重建目标服务：

```bash
ssh allbot-do-sgp1-control
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build central-api-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml up -d --no-deps central-api-prod
```

目标 service 可替换为 `web-api-prod`、`dashboard-backend-prod`、`dashboard-frontend-prod`、`payment-api-prod` 或 `bot-prod`。生产热修前建议先备份被覆盖文件；当前云端运行目录不应假设一定是完整 Git 工作区。

管理后台单独更新时，只同步 Dashboard 后端/前端相关文件，只重建目标 Dashboard service，不重启 Central/Web/Bot/Payment/imgproxy/worker/RunPod。云正式 Dashboard 健康检查使用 Tailscale 入口：

```bash
ssh allbot-do-sgp1-control
cd /home/deploy/APP/All_bot

docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build \
  dashboard-backend-prod dashboard-frontend-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml up -d --no-deps \
  dashboard-backend-prod dashboard-frontend-prod

curl -fsS http://100.107.220.127:8043/api/health
curl -fsS http://100.107.220.127:8086/api/health
```

若只改 Dashboard 前端，例如 RunPod 管理页面 profile 列表、按钮识别或展示逻辑，只重建
`dashboard-frontend-prod` 即可。验证时确认 `cloud-dashboard-frontend-prod` 与
`cloud-dashboard-backend-prod` healthy，且 `cloud-central-api-prod`、`cloud-web-api-prod`、
`cloud-tg-bot-prod`、`cloud-payment-api-prod`、`cloud-imgproxy-prod` 的启动时间没有变化。
Dashboard RunPod 管理入口当前支持 `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro`
与 `scail2 / 视频生视频`；它只提交正式手动 RunPod 池新增/暂停/删除操作，不直接启停其它正式服务。

### 4.2.1 SCAIL-2 低影响正式发布与 RunPod 扩容

SCAIL-2 的正式上线起始边界是“只更新云正式主控制面 + 正式 Web/Bot 入口 + gpu-002 slot0 SCAIL-2 AIO runtime/agent”。这条低影响路径不重建 `cloud-prod-comfy-agent-1..7`，不执行 `scripts/start_cloud_prod_worker.sh --start`，不修改 gpu-002 slot1/`8191` 或其它 GPU 节点。后续需要增加正式视频生视频容量时，可以使用手动正式 RunPod `scail2` profile 作为并行 worker；它不替代 slot0 LAN runtime，canary 通过后可与 `lan_aio_prod_gpu002_gpu0_scail2_01` 同时 enabled 接单。

正式 task type：
- `scail2_action_transfer`：动作迁移，5s/8s，40/80 灵石
- `scail2_video_replacement`：视频换人，5s/8s，40/80 灵石
- `scail2_face_swap_v2`：视频换脸 v10 two-stage，5s/8s，40/80 灵石；仅由 gpu-002 LAN SCAIL-2 正式 worker 承接，正式 RunPod `scail2` 仍保持动作迁移/视频换人两任务。

发布闸门：

```bash
cd /home/hfy/APP/All_bot
scripts/cloud_prod_generation_release_gate.py enable-maintenance --execute
scripts/cloud_prod_generation_release_gate.py wait-pending --threshold 10 --timeout-seconds 3600
scripts/cloud_prod_generation_release_gate.py refund-pending --threshold 10 --execute
```

`enable-maintenance --execute` 在 `cloud-web-api-prod` 与 `cloud-tg-bot-prod` 内写 `/app/GENERATION_MAINTENANCE`，只阻止新生成进入。不要为这类低影响发布写 `/app/MAINTENANCE`，它会触发 Web API 全局 503 并影响结果轮询、历史等非提交接口。`wait-pending` 与 `refund-pending` 必须在能访问正式 Redis 的 `allbot-do-sgp1-control` 上运行；本地主服务器直连正式 Redis 超时不代表队列闸门不可用。`refund-pending --execute` 只处理仍在 Central pending zset 中的任务，按维护发布退款类型 `refund_prod_maintenance_release` 走统一 finalization，释放并发锁并退款；running 任务不强杀。

slot0 runtime 接管：

```bash
cd /home/hfy/APP/All_bot
scripts/lan_scail2_aio_prod.sh preflight --execute
scripts/lan_scail2_aio_prod.sh start-disabled --execute
scripts/lan_scail2_aio_prod.sh verify --execute
scripts/lan_scail2_aio_prod.sh enable --execute
```

`scripts/lan_scail2_aio_prod.sh` 只操作 gpu-002 slot0/`8190`：
- 新 agent：`lan_aio_prod_gpu002_gpu0_scail2_01`
- 新容器：`allbot-lan-aio-gpu-002-gpu0-scail2-prod`
- 旧 slot0 AIO agent：`lan_aio_prod_gpu002_gpu0_img2img_lora_01`
- 旧 slot0 容器：`allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary`

渲染出的 compose 必须为 `RUNPOD_ENVIRONMENT=cloud-prod`、`CENTRAL_API_URL=https://worker-central.aivison.it.com`、`MINIO_*_BUCKET=user-data-prod`，声明 `SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_video_replacement,scail2_face_swap_v2`，并通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 绑定三份 audio/v10 workflow；`scail2_face_swap_v2` 必须开启 `SCAIL2_FACE_SWAP_V10_*` 预处理，先调用 `face_swap_v2.json` 生成换脸首帧。compose 不得出现 `cloud-test` / `user-data-test`。`start-disabled --execute` 会先 drain 旧 slot0 AIO 并等待其自然空闲，停止旧 slot0 容器后启动 SCAIL-2 disabled heartbeat；只有 `/system_stats`、`/object_info` 必需节点、模型枚举和 disabled heartbeat 全部通过后，才允许 `enable --execute`。

控制面服务发布仍按单服务最小范围处理：

```bash
ssh allbot-do-sgp1-control
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build central-api-prod web-api-prod bot-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml up -d --no-deps central-api-prod web-api-prod bot-prod
```

正式 Web Pages 只发布正式前端项目；不要把测试 Pages 或测试 API 域名带入正式构建。验收通过后执行：

```bash
scripts/cloud_prod_generation_release_gate.py disable-maintenance --execute
```

回滚顺序：

```bash
scripts/cloud_prod_generation_release_gate.py enable-maintenance --execute
scripts/lan_scail2_aio_prod.sh drain-scail2 --execute
scripts/lan_scail2_aio_prod.sh rollback --execute
```

回滚只停 SCAIL-2 slot0 prod container 并恢复旧 slot0 img2img_lora AIO agent/container。不得删除 SCAIL-2 workspace、模型缓存、旧 img2img workspace 或其它 worker/RunPod。

正式 SCAIL-2 RunPod 扩容准备：

```bash
python scripts/prepare_scail2_model_r2_bundle.py --env-file .env.cloud.test
# 确认 dry-run 后再执行，写入的是 allbot-model-cache，不是 user-data-test/prod
python scripts/prepare_scail2_model_r2_bundle.py --env-file .env.cloud.test --execute

RUNPOD_IMAGE_NAME_SCAIL2=ghcr.io/giraffu/allbot-comfy-runpod-scail2:<prod-tag> \
python scripts/gpu_pool_controller.py runpod prod-worker render --profile scail2 --slot 01
```

正式 SCAIL-2 RunPod 创建与验收：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
scripts/runpod_prod_ops.sh add --profile scail2 --count 1 --execute

scripts/runpod_prod_ops.sh canary --profile scail2 --slot 01 --execute
scripts/runpod_prod_ops.sh enable --profile scail2 --slot 01 --execute
```

`prod-worker canary --profile scail2` 会提交 `scail2_action_transfer 5s` 与 `scail2_video_replacement 5s` 两个正式内部任务。若要强制两单命中 RunPod，应先等待 SCAIL-2 pending 清空，临时 disable `lan_aio_prod_gpu002_gpu0_scail2_01`，canary 完成后再恢复 LAN agent；其它正式 worker 与其它 RunPod profile 不在本操作范围内。

### 4.3 Agent control 正式灰度更新指南

2026-06-10 已在云测试环境验证 `draining/disabled` worker 控制链路：`cloud-central-api-test` 暴露 `GET/POST /api/agent/task/control/{agent_id}`，测试 worker 重建后真实 `/pop` 会携带 `agent_id=cloud_worker_test_*`，`disabled` worker 的 `/pop` 返回空任务且不移除 pending。

正式环境后续更新必须同时覆盖两层：

1. 云正式 Central API 代码：让 `cloud-central-api-prod` 具备 control route、control Redis key 读写、`pop(agent_id=...)` 拒绝接单能力。
2. 本地主服务器正式 worker 镜像：让 `cloud-prod-comfy-agent-*` 在真实 `/pop` query 中携带 `agent_id=cloud_prod_worker_*`。如果只更新 Central、不重建 worker，control 接口存在但实际 worker 仍不受 drain 控制。

测试环境踩坑记录：
- 远端 `/home/deploy/APP/All_bot` 不应假设是 Git 工作区；生产热修前先备份文件，再用 `rsync -R` 保留相对路径同步。
- `backend/app/queue_manager.py` 与 `backend/app/queue_manager_flow_helpers.py` 必须一起同步；只同步前者会导致 heartbeat metadata 参数不兼容。
- 云正式 compose 中 `central-api-prod` 挂载 `../backend/app:/app/app:ro`，同步 Python 文件后重启 `central-api-prod` 即可生效；如同时更新依赖或镜像内文件，再执行 build。

正式更新步骤：

```bash
# 1. 本地主服务器先跑后端 focused tests
cd /home/hfy/APP/All_bot
python -m pytest tests/backend/test_agent_router_helpers.py tests/backend/test_queue_manager.py -q

# 2. 备份云正式 Central 文件
ssh allbot-do-sgp1-control '
  set -euo pipefail
  cd /home/deploy/APP/All_bot
  backup_dir="/home/deploy/APP/All_bot/backups/central-agent-control-$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$backup_dir/routers"
  cp backend/app/agent_router_helpers.py backend/app/queue_manager.py backend/app/queue_manager_flow_helpers.py backend/app/models.py "$backup_dir"/
  cp backend/app/routers/agent.py "$backup_dir/routers"/
  echo "$backup_dir"
'

# 3. 同步 Central 相关文件，-R 用于保留 backend/app/... 相对路径
rsync -avhR \
  backend/app/agent_router_helpers.py \
  backend/app/queue_manager.py \
  backend/app/queue_manager_flow_helpers.py \
  backend/app/models.py \
  backend/app/routers/agent.py \
  allbot-do-sgp1-control:/home/deploy/APP/All_bot/

# 4. 只重启云正式 Central API
ssh allbot-do-sgp1-control '
  set -euo pipefail
  cd /home/deploy/APP/All_bot
  docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml restart central-api-prod
  docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml ps central-api-prod
'
```

Central 验证命令：

```bash
ssh allbot-do-sgp1-control '
  set -euo pipefail
  cd /home/deploy/APP/All_bot
  TOKEN="$(sed -n "s/^AGENT_SECRET_TOKEN=//p" .env.cloud.prod | tail -n1)"
  CENTRAL="http://100.107.220.127:8003"
  curl -fsS "$CENTRAL/health"
  curl -fsS -H "Authorization: Bearer $TOKEN" \
    "$CENTRAL/api/agent/task/control/cloud_prod_worker_06"
  curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"state\":\"disabled\",\"reason\":\"prod control route validation\",\"ttl_seconds\":60}" \
    "$CENTRAL/api/agent/task/control/cloud_prod_worker_06"
  curl -fsS -H "Authorization: Bearer $TOKEN" \
    "$CENTRAL/api/agent/task/pop?types=img2img_lora&agent_id=cloud_prod_worker_06&cancel_lock=true"
  curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"state\":\"enabled\",\"reason\":\"\"}" \
    "$CENTRAL/api/agent/task/control/cloud_prod_worker_06"
'
```

期望结果：
- `/control/cloud_prod_worker_06` 初始返回 `state=enabled`。
- 设置 `disabled` 后，带 `agent_id=cloud_prod_worker_06` 的 `/pop` 返回 `task: null`，并说明该 worker 不接新任务。
- 验证结束必须恢复 `enabled`。
- Central 最近日志无 `500 Internal Server Error`、`TypeError`、`Traceback`。

正式 worker 更新：

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

首次上正式时注意：旧生产 worker 尚未携带 `agent_id` 前，不能依赖 Central drain 来保护 worker 重建；应选择队列低峰、确认目标 worker 无当前任务，或按单 worker 逐个更新并接受该 worker 当前任务可能中断。完成更新后，从云 Central 日志确认真实 `/pop` URL 已出现 `agent_id=cloud_prod_worker_*`。

最终验收：
- `curl http://100.107.220.127:8003/health` 正常。
- `/system/workers` 看到当次目标 worker 集合的 heartbeat。若本轮只更新本地 compose worker，至少验证目标 `cloud_prod_worker_*`；若本轮包含 LAN AIO、`remote_workers` 或 RunPod，还要验证对应 agent id、任务类型和 control state。
- 目标 worker control 状态符合发布计划；需要接正式队列的 worker 为 `enabled`，备用/未验收 worker 保持 `disabled`。
- 抽选一个低风险 worker 短 TTL 设置 `disabled`，实际 `/pop` 不再接单；随后恢复 `enabled`。
- 本地 relay `127.0.0.1:8013/ready` 正常，worker 日志无 `relay_forward_failed`、`sidecar_upload_failed`。

回滚：
- Central 异常时，恢复备份目录中的 `backend/app/*.py` 与 `backend/app/routers/agent.py`，只重启 `central-api-prod`。
- Worker 异常时，只回滚或重建对应 `cloud-prod-comfy-agent-N`；不得对 `workers` project 使用 `--remove-orphans`，不得清理测试 worker。

### 4.4 Cloudflare Pages/API Tunnel 维护
正式 Web/API 已完成切换。日常维护只需要确认 Pages 项目、Tunnel connector 和 CORS allowlist 仍与正式域名一致。

历史 canary 流程已经归档到 `docs/archive/2026-06-cloud-migration/`；以下原则仍有效：

- Tunnel connector 必须运行在云机 `allbot-do-sgp1-control`，不得复用本地主服务器 RMB tunnel。
- Cloudflare 控制台 token、connector 安装命令和 `.env.cloud.prod` 不得贴到聊天、文档或 Git。
- 若重新启用 canary，可执行：

```bash
bash scripts/check_cloudflare_canary.sh
```

2026-06-08 晚间已将正式 `api.aivison.it.com` 切到云机 Cloudflare Tunnel，并将 `web.aivison.it.com` 绑定到 Cloudflare Pages 项目 `allbot-web-prod`。`assets.aivison.it.com` 继续留在 Web/Nginx VPS，作为人工回滚、旧外链和 legacy 迁移排障入口。

### 4.5 本地云正式 worker 更新
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

worker 正在处理任务时重建会中断该 worker 当前单任务。常规正式 worker/relay 更新应先开启 Web/Bot 维护或等价门禁，阻止新生成任务进入，等待 pending/running 或至少目标 worker 当前任务自然归零，再重建 relay/worker，最后关闭维护并验收。紧急抢修可以按目标 worker 直接处理，但必须明确接受该 worker 当前任务可能中断。

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
- `http://100.107.220.127:8086/api/health` 仅在云正式 Dashboard Frontend 已启动后验证；如果配置了公网管理域名，还必须确认该域名受 Cloudflare Access 或等价身份层保护。
- Dashboard 登录后系统状态、worker 卡片与大盘统计能刷新。
- Dashboard Backend 必须有可用 `REDIS_URL` 或 `DASHBOARD_RUNPOD_OPERATION_REDIS_URL`，用于持久化 RunPod operation store；生产不应依赖进程内 memory store 追踪 operation。
- Dashboard Backend 启动入口必须调用 `ensure_billing_core_providers_registered()`；退款、强制终止和资产类管理接口会进入 billing core，若只注册 task core provider，会出现 `Billing core providers 未注册`。
- Web 卡顿专项需额外记录云内、边缘到云、公网三段延迟，并统计边缘 499、Web R2 result timeout、Dashboard circuit breaker；若响应仍出现 `assets.aivison.it.com`，按 legacy 退出回归缺陷处理。

### 5.2 Worker
```bash
docker ps --format '{{.Names}}\t{{.Status}}' | rg '^cloud-prod-(worker-relay|comfy-agent-)'
curl -fsS http://127.0.0.1:8013/health
docker logs --since 2m --tail 100 cloud-prod-comfy-agent-1
```

云 Central 应看到：
- `active_workers` / `healthy_workers` 与当次预期容量一致；2026-06-18 03:06 快照为 13 个 active/healthy workers，但 LAN AIO、`remote_workers` 与手动 RunPod 数量都是运行态，不是固定长期容量
- `error_workers=0`
- `quarantined_workers=0`
- Central Redis 中 `comfy:queue:pending`、`comfy:queue:running`、`comfy:task_heartbeat:*` TTL 与 `/system/status` 口径一致
- `cloud-prod-worker-relay` 最近日志无 `relay_forward_failed`、`sidecar_upload_failed`

### 5.3 数据与媒体
- Alembic 当前 head 应与仓库 migration head 一致。
- Gallery/History 热路径索引必须存在，尤其是 `ix_gallery_posts_active_created_at_id`、`ix_history_task_id`、`ix_history_user_id_id_desc`、`ix_user_interactions_user_action_post`。
- 新生成对象写入 R2 `user-data-prod`。
- 旧历史媒体的正式应用读路径应通过 R2 或当前 R2/S3 短签读取；`assets.aivison.it.com` 只作为人工回滚、旧外链和迁移补漏排障入口。

## 6. 回滚与事故处理
- 只重建 Central/Web/Dashboard 代码后，若服务异常，优先回滚目标容器代码或恢复热修前备份文件，再只重建目标服务。
- worker 更新后如果单节点异常，可只重建对应 `cloud-prod-comfy-agent-N`；不要全量清理 `workers` project。
- 已经启动云 Bot 并产生新写入后，不做简单整站回滚；走数据核对与定向修复。
- 云正式整体不可用且短时无法恢复时，才执行本地正式灾备切换。具体步骤见 `docs/子模块_本地正式灾备切换_local_prod_fallback.md`；切换前必须保证生产 Bot 单实例，并接受本地数据库非实时同步带来的对账成本。
- `/system/status` 慢或 Dashboard 卡顿时，先检查 Central 状态观测缓存、托管 Valkey 连接、Dashboard stats 缓存和前端轮询频率，不要把 GPU 生成停顿直接当成控制面故障。
- Web 公网慢但云内健康时，不要优先重启 Web API；先检查 Cloudflare/Tailscale 链路、R2 result timeout、R2 公开域名/短签和前端串行请求。若正式响应出现 legacy `assets` URL，再按回归缺陷排查。
