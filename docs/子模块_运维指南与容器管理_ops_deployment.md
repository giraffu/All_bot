# 子模块: 运维指南与容器管理 (Ops & Deployment)

## 1. 目标与范围
本模块记录当前仓库真实生效的部署顺序、迁移策略与常见故障恢复方式。最重要的事实更新有两点：
- 旧本地正式脚本的数据库迁移由 `safe_deploy.sh` 在宿主机上主动执行，不再依赖“容器下次启动自动迁移”；云正式/云测试分别以 cloud deploy 脚本和目标环境 Alembic 口径为准。
- `web-api` 等服务若未挂载源码卷，代码变更后必须 `--build` 重建镜像才会生效。

## 2. 当前推荐部署路径
- 功能研发、联调、修复、配置调整：首选云测试控制面 `scripts/safe_deploy_cloud_test.sh`；旧本地隔离测试栈脚本/compose 仅作历史保留和必要人工取证材料，不再作为受支持的测试或回滚环境
- 当前云正式生产热修：按云正式文档使用 `scripts/safe_deploy_cloud_prod.sh` 或目标 cloud-prod compose 单服务重建
- 本地正式灾备：仅在云正式整体不可用时按 `docs/子模块_本地正式灾备切换_local_prod_fallback.md` 切回本地主服务器
- 本地正式灾备整栈启动/重建：仅在云正式整体故障、需要本地主服务器临时接管时才执行 `bash safe_deploy.sh`
- 原因：脚本已经把以下步骤串成标准顺序：
  - 进入维护模式
  - 等待活跃任务清空
  - 清理僵尸任务与 Redis 锁
  - 检查 Alembic 多 head
  - 生产脚本基于 `.env` 并显式 `BOT_TYPE=PROD`，宿主机执行 `alembic upgrade head`
  - 重建 workers
  - 重建 central api
  - 重建主服务群
  - 重建 dashboard
  - 发布生产 Web 静态站到边缘 VPS
- `safe_deploy.sh` 到此结束，不会顺带重建测试环境；它不代表当前云正式控制面的发布入口。
- `safe_deploy_test.sh` 不再作为推荐入口。若历史排障必须短时恢复旧本地隔离测试栈，应另起临时计划，先确认它不会抢占测试 Bot token、GPU、Redis 队列、对象桶或边缘测试站；完成后立即停止并保留数据。

## 2.1 当前默认发布策略
- AI 在功能研发期间默认只能更新隔离测试环境，不得主动执行生产部署。
- “帮我改功能”“帮我修 Bug”“帮我联调”“帮我验证配置”这类请求，默认理解为测试环境操作。
- 只有在用户明确表达“上线”“发布”“部署正式环境”“交付生产”后，才允许切换到云正式脚本或生产 compose；`safe_deploy.sh` 只用于云正式整体故障时的本地正式灾备。
- 在用户完成测试验收前，不得把测试环境变更直接同步到正式 Bot、正式 Web、正式 Payment、正式 Central API 或正式 Dashboard。

## 2.2 云端测试控制面
- DigitalOcean SGP1 Droplet 上的云测试控制面入口为 `scripts/safe_deploy_cloud_test.sh`，compose 文件为 `deploy/docker-compose-cloud-test.yml`。
- 云测试控制面默认部署同机 Postgres、同机 Redis、Central API、Web API、Dashboard Backend、Dashboard Frontend 与 imgproxy；`bot-test` 只通过 `bot` profile 手动启动，本地主服务器另行启动 GPU worker。当前对象存储事实源是 Cloudflare R2，云测试 compose 当前不包含 MinIO、Payment API 或 Web 前端 dev 容器。
- 云测试 `.env.cloud.test` 已被 `.gitignore` 忽略，不能提交到仓库。
- 云端服务端口绑定到云测试 Tailscale IP `100.82.124.91`，不直接开放公网。若临时使用 `CLOUD_TEST_BIND_IP=0.0.0.0`，必须配合源 IP 白名单，只允许边缘 VPS 与本地主服务器访问测试 API 端口，恢复后必须收回公网白名单。
- 云测试全链路 worker 使用 `workers/docker-compose-cloud-worker-test.yml`，容器名为 `cloud-comfy-agent-test-*`，从本地主服务器经 `CLOUD_TEST_CONTROL_HOST=100.82.124.91` 访问云端 `8004` Central API，并直接访问 R2 S3 endpoint 读写 `user-data-test`。当前 compose 声明 `cloud-comfy-agent-test-1..8`，其中 `cloud_worker_test_08` 是 SCAIL-2 测试 worker。
- 若历史本地测试栈仍在运行，切云测试前用 `scripts/stop_local_test_preserve.sh` 停止并保留数据；云测试 GPU 执行面使用 `scripts/start_cloud_worker_test.sh` 启动本地 cloud-worker 测试栈。
- 云测试 `bot-test` 默认通过 `TON_PAYMENT_POLLING_ENABLED=false` 禁用 TON 链上轮询，避免空云测试库回扫真实商户地址历史交易；仅在专门支付联调时显式开启 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`。
- 云测试库若为空，脚本使用当前 ORM schema 初始化并 `alembic stamp head`；若已有 schema，脚本执行 `alembic upgrade head`。这是云测试控制面的特殊兼容策略，不改变生产脚本的迁移口径。
- 云测试 `.env.cloud.test` 中 `MINIO_*` 是项目兼容变量名；R2 直连时应保持 `MINIO_SECURE=true`、`MINIO_BUCKET/MINIO_INPUT_BUCKET/MINIO_RESULT_BUCKET/MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`。Web owner 视频结果接口依赖 R2 公网 URL，公开域名缺失会导致视频停在 99% / `pending_result`。
- 云测试公网 Web 使用 `web-test.aivison.it.com` 的边缘 VPS 静态站，`/api/` 反代到云端测试 Web API `http://100.82.124.91:8001`；云端不运行 Web 前端 dev 容器。Dashboard 测试前端由 `cloud-dashboard-frontend-test` 提供，默认 `http://100.82.124.91:8087/`，仅限 Tailscale/受控来源访问。
- 详细说明见 `/docs/子模块_云测试控制面部署_cloud_test_control_plane.md`。

## 2.3 云正式控制面
- 2026-06-07 晚间正式生产已切到云控制面。当前长期运维入口为 `deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`、`scripts/safe_deploy_cloud_prod.sh`、`all_bot_nginx_cloud_prod.conf` 和 `all_bot_nginx_cloud_prod_rmb.conf`。
- `.env.cloud.prod` 是本机私有文件，已被 `.gitignore` 忽略；`.env.cloud.prod.example` 只提供变量契约和占位值。`.dockerignore` 必须忽略 `.env.*`，避免 root Docker build 把真实云正式变量 COPY 进镜像。
- 云正式 Web API 需要 `JWT_SECRET_KEY`，且不能使用默认占位值；该 key 已纳入 `.env.cloud.prod.example` 和 `scripts/safe_deploy_cloud_prod.sh` preflight 必填检查。
- 云测试环境退役入口为 `scripts/cleanup_cloud_test_for_prod.sh`。脚本默认 dry-run，真实清理必须传 `--execute`；它不得删除 R2 `user-data-test`，不得误改正式服务或 `web.aivison.it.com`。
- 云正式控制面包含 Central API、Web API、Payment API、Dashboard Backend、Dashboard Frontend、imgproxy 和正式 Bot；`cloud-tg-bot-prod` 使用 `bot` profile，重建前必须确认全网只有一个生产 polling 实例。
- 云正式本地 worker compose 声明 `cloud-prod-worker-relay` 与 `cloud-prod-comfy-agent-1..7`；线上实际容量还可能包含 LAN AIO agent、`remote_workers` 与手动 RunPod worker。启动或重建后必须在云 Central `/system/workers` 验证当次目标 worker 集合的 heartbeat、control state 与任务类型，状态不能是 `error` 或 `quarantined`；不要把固定 7 个 heartbeat 当成所有场景的唯一验收标准。
- 云正式 R2 在线口径为 `user-data-prod` 单桶，`MINIO_*` 兼容变量和 `R2_*` 都指向正式 R2；`MINIO_PUBLIC_URL` 保持空，结果公开读取依赖 `R2_PUBLIC_DOMAIN=https://r2.aivison.it.com`。
- 正式 Web API / Dashboard 运行时不再通过 `LEGACY_MINIO_*` 回源本地 MinIO；云正式 compose 对 Web/Dashboard 应设置 `LEGACY_MINIO_READ_FALLBACK_ENABLED=false` 并清空 legacy endpoint/key/public URL。R2 miss 后只允许当前 R2/S3 短签、空值或 `pending_result`，worker 仍只写 R2，不得把 legacy MinIO 配进 worker 写路径。
- legacy 退出前的用户可见热集补齐使用 `scripts/backfill_history_r2_objects.py --env-file .env.cloud.prod --hotset-profile web-visible-retire-legacy --source-storage legacy --include-input-files --batch-size 500`，默认 dry-run，真实复制必须显式 `--apply`。默认补齐范围包括每用户最近 8 条可见历史、Gallery 投稿/收藏/应用/解锁、History 收藏；若本轮只迁移社区强可见集合，追加 `--skip-per-user-recent-history`，范围收窄为所有 Gallery 投稿、History 收藏、Gallery like/apply 互动关联 active posts 与 prompt unlock 关联 active posts，并使用独立 cursor。先从 legacy 或 current 源复制原文件/已有缩略图/输入文件，再用 `--source-storage current --generate-missing-thumbnails` 从已补齐到 R2 的原文件生成缺失缩略图。
- 云正式历史详情、Gallery/Wan22 预览等读路径需要验收“返回 URL 可读”，不能只验 R2 S3 `HEAD`。若 `R2_PUBLIC_DOMAIN` 对部分 key 返回 404，但 R2 S3 `HEAD` 命中，Gallery 列表应直接返回 R2 S3 短签 URL，历史详情读路径可返回 R2 S3 短签 URL 兜底；Web owner `/result` 视频仍应按真实结果接口单独验收，不要用历史详情 fallback 代替。
- 云正式 Web 已由 Cloudflare Pages 项目 `allbot-web-prod` 承接，正式 Web API 独立使用 `api.aivison.it.com` Cloudflare Tunnel 回源云 Web API；`web.aivison.it.com/api/health` 会返回 Pages SPA HTML，不再作为健康检查。Web/Nginx VPS 继续保留 `assets.aivison.it.com` 到本地 MinIO 的 legacy 代理和 `/root/dist` 回滚副本，但正式应用不应再生成 `assets` URL。RMB 支付入口继续使用 Cloudflare Tunnel 回源云 Payment API。如需紧急回滚 RMB 回源，用 `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute` 切回本地 Payment API。切换/回滚脚本默认 dry-run，真实执行必须显式 `--execute`。
- 云正式 Dashboard Frontend 由 `cloud-dashboard-frontend-prod` 提供，默认绑定 `100.107.220.127:8086`，`/api/` 在 Docker 内网反代 `dashboard-backend-prod:8043`。该入口用于减少本地主服务器前端与本地网关链路；若需要公网管理域名，必须通过 Cloudflare Tunnel + Access 或等价身份层保护，禁止裸开 `8086`/`8043`。
- 边缘 VPS 当前至少包含 Web/Nginx 节点 `100.88.57.122`/`154.17.30.113` 与 Telegram Local API 节点 `69.63.220.115`。2026-06-18 快照显示 Web 节点根盘约 6.2G 可用、使用率约 84%，`nginx`/`tailscaled` active 且未安装 `docker`；发布静态资源、调整 Nginx cache 或开启详细日志前仍必须先查 `df -h`。Telegram 节点当前主服务器未配置可用 SSH key，只能做 8081/8082 公网端口探测，完整容器/磁盘排障需先补 SSH。详情见 `docs/子模块_边缘节点运维指南_edge_node_ops.md`。
- 真实 `docker compose config` 会展开密钥，输出只能本地查看，不得贴到日志、文档或聊天中。
- 云正式 Central 高频观测接口已加入短缓存和 stale-while-revalidate；Dashboard stats 也有短缓存与 single-flight。不要通过前端 `_t` 或脚本高频击穿缓存。
- 云正式最新长期 SOP 见 `/docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`；本地正式灾备 SOP 见 `/docs/子模块_本地正式灾备切换_local_prod_fallback.md`；历史迁云证据已归档到 `/docs/archive/2026-06-cloud-migration/`。

## 2.4 本地正式灾备
- 本地主服务器只保留一套临时本地正式接管方案，不再保留日常正式入口。
- 触发条件是云正式控制面、Tunnel 或云侧数据面整体不可用，且短时间无法恢复。
- 切换前必须确认 `cloud-tg-bot-prod` 已停止或不可用，避免生产 Bot token 双实例 polling。
- 本地 `.env` 必须是生产口径；如果能从云端导出最新数据库，应先恢复到本地 PostgreSQL 再开放写入口。云端完全不可用时，要接受本地快照导致的对账成本。
- 旧本地 compose 仍有历史硬编码默认值和占位值；本地灾备前必须核对 Central API、Dashboard 与 worker 的 compose 渲染和容器内实际环境变量，不能只依赖 `source .env` 判断配置已生效。渲染输出和 `env` 输出可能包含密钥，只能本机查看。
- 切换 Web/API/RMB 入口前，优先只选一条网络路径，不要同时改 Pages、Tunnel、Nginx 和 DNS。
- 回切云端时必须先冻结本地新增写入并导出灾备期间的订单、用户资产、任务历史和必要日志，再恢复云端入口。

## 3. 旧本地脚本迁移口径
- 旧本地正式脚本的迁移入口在 `safe_deploy.sh` 第 4 步。
- 脚本会先寻找可用的 Alembic 可执行文件，再检查 `heads` 数量。
- 一旦发现多个 head，脚本会直接中止，要求先合并 migration，而不是带病部署。
- 通过多 head 检查后，脚本会立即执行 `alembic upgrade head`。
- 生产脚本在加载 `.env` 后显式导出 `BOT_TYPE=PROD`，避免 `config.py` 的默认 TEST 语义影响生产迁移环境选择。

这意味着知识库里以下旧说法都应删除：
- “等容器启动时自动迁移”
- “部署完新容器后再手动进容器跑 upgrade head 才是标准流程”

## 4. 服务重建注意事项
- `web-api`、`payment-api`、Dashboard 等通过镜像 `COPY` 代码的服务，修改代码后都要重建镜像，单纯 `restart` 不会拿到新代码。
- 只更新管理后台时，操作范围应收窄到 `dashboard-backend-prod` / `dashboard-frontend-prod`：同步相关文件后只 build/up 这两个 service 或其中一个，不重启 Central/Web/Bot/Payment/imgproxy/worker/RunPod。云正式 Dashboard 健康检查优先用 `http://100.107.220.127:8043/api/health` 与 `http://100.107.220.127:8086/api/health`；确认其它正式服务容器启动时间未变化。
- `workers` 更新环境变量时，应使用 `docker-compose up -d` 触发重新创建，而不是只做 `restart`。
- 当前受支持的测试环境是云测试控制面；旧本地测试脚本仍可能留在仓库内作为历史迁移/取证材料，但不应被当成回滚目标。
- 若人工取证确需短时启动旧本地隔离测试栈，应使用独立的 `.env.test`、`backend/docker-compose-test.yml` 与 `workers/docker-compose-test.yml`，并让测试入口服务指向独立的 Central API 端口与独立 Redis 队列；否则可能与正式或云测试环境共用任务调度面。
- `workers/docker-compose-test.yml` 中的 `${...}` 插值不会读取 `env_file: ../.env.test` 的值。短时启动旧本地测试 worker 后仍要用 `docker exec <worker> env` 核对实际生效值，避免 401 或读写错误桶；取证完成后立即停止旧本地测试栈。
- 云正式本地 worker 使用 `workers/docker-compose-cloud-prod-worker.yml`。本地主服务器仍可能是 `docker-compose 1.29.2`，目标 worker `up` 触发 `KeyError: 'ContainerConfig'` 时，只删除目标正式 worker 容器和同 service label 残留，再 `up -d --no-deps`；不得使用 `--remove-orphans`，不得清理测试 worker 或旧本地 worker。
- 常规云正式 worker/relay 更新优先进入维护或等价门禁，阻止新生成任务进入，等待 pending/running 或至少目标 worker 当前任务归零后再重建；worker 正在处理任务时重建会中断该 worker 当前单任务。紧急抢修可按目标 worker 直接处理，但必须明确接受该 worker 当前任务可能中断。

## 4.1 workflow 资产事实源
- `workers/comfy_agent/workflows` 是唯一 workflow 运行时事实源；`backend/workflows` 已退出，Central API 不再挂载、COPY 或启动校验 workflow 目录。
- 修改 workflow JSON、`mappings.json` 或 workflow patcher 时，只更新 Worker 目录，并重建或重启会执行该 task type 的 Worker。
- Worker 初始化 `WorkflowPatcher` 时仍会校验 `workers/comfy_agent/workflows/mappings.json`，确保映射节点和输入名存在；Central API 只负责请求参数与队列，不再以 workflow 文件作为启动门禁。
- 若只重建 Central API 而未重建 Worker，workflow 变更不会生效；新增 task type 还必须同步 `TASK_TYPE_WORKFLOW_FILENAMES`、`mappings.json` 和目标 Worker 的 `SUPPORTED_TASK_TYPES`。

## 4.2 局域网 GPU 节点操作边界
- 局域网 GPU 节点的 SSH、硬件、ComfyUI 容器、模型挂载和安全操作边界分别见：
  - `/docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`
  - `/docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`
- `cloud-prod-comfy-agent-*` 是本地主服务器上的 worker 容器；GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI 是另一层。替换 worker 不会自动重启 ComfyUI，重启 ComfyUI 也不会更新 worker 代码。
- 双卡 GPU 节点上，`comfy0` 与 `comfy1` 绑定不同 GPU 和不同 `inst0/inst1` 输入输出目录，但共享模型目录和宿主机资源。单个任务类型或单个 worker 异常时，只操作目标 worker 和目标 Comfy 容器。
- 禁止因为一个 Comfy 容器异常而整机 reboot、无 service 名 `docker compose down/up`、批量删除所有 Comfy 容器或清理整个共享模型目录。
- `allbot-gpu-226` 的 ComfyUI 是宿主机进程，cwd 为 `/home/ubantu/comfyui`，不是 Docker Comfy 容器；不要对它执行 `docker restart comfy0`。
- GPU 节点 ComfyUI 素材清理优先使用 `scripts/cleanup_lan_comfy_artifacts.sh`；脚本默认 dry-run，必须显式 `--execute` 才删除。当前保守策略是 `output/temp` 清 60 分钟以前文件，`input` 只清 24 小时以前文件。不要把“只保留 1 小时”直接套到 `input`，也不要清理 `models/custom_nodes/workflows`。
- 2026-06-08 已清理一次旧素材，但 `input/output/temp` 会持续增长；模型下载、Docker pull/build 或大视频输出前必须重新检查 `df -hT`。

## 5. 常见问题与恢复约束
- MinIO 503 / 上传假死
  - 现象：Web 请求超时，甚至非上传接口也被拖慢。
  - 根因：Region 探测阻塞事件循环。
  - 处理：重启 MinIO，并保持 `_region_map` 离线映射策略。
- Nginx 404 / 502
  - `404` 常见于 `proxy_pass` 带错误路径
  - `502` 常见于后端服务或 Tailscale 链路不可达
- 旧本地测试 worker 短时取证后出现 401 / 读错桶
  - 常见根因：把 `env_file` 当成 compose `${...}` 插值来源，或测试 worker 容器内实际 `AGENT_SECRET_TOKEN`、`MINIO_INPUT_BUCKET`、`MINIO_RESULT_BUCKET` 与 `.env.test` 口径不一致
  - 处理：核对 `workers/docker-compose-test.yml` 默认值是否仍为测试桶，重建后用 `docker exec <worker> env` 验证 `MINIO_INPUT_BUCKET=bot-data-test`、`MINIO_RESULT_BUCKET=comfyui-temp-test`，并确认 token 与旧本地测试 Central API 一致；取证结束后停止该栈
- 云测试 R2 新对象公开域名返回 403
  - 现象：R2 S3 API `head_object` 成功，但 `https://r2-test.aivison.it.com/<new-key>` 返回 403
  - 处理：若只是图片结果，可临时使用 R2 S3 预签名 URL 闭环；若是 Web 视频结果，必须优先修复公开域名或改造 owner result fallback，否则 `/api/tasks/{task_id}/result` 会持续 `pending_result`
- 云正式 `/system/status`、管理后台 worker 监控卡顿
  - 常见根因：Central 状态观测重复扫描 Redis/Valkey、Dashboard stats 重查询、前端高频缓存击穿或 Valkey 连接抖动。
  - 处理：确认 Central 使用共享 Redis 客户端和约 10 秒观测缓存；确认 Dashboard stats 缓存未被 `_t` 参数击穿；确认 `/system/status` 和 `/system/workers` 只是观测接口，不参与任务分发。
- 本地 GPU 生成中“停几秒再继续”
  - 常见根因：ComfyUI 模型/LoRA 加载、显存切换、WebSocket 终态未及时返回、worker 转 `/history/{prompt_id}` 轮询收口。
  - 处理：查对应 `cloud-prod-comfy-agent-*` 日志和 ComfyUI `/system_stats`，不要直接归因为 Central 状态接口慢。
- 双卡 GPU 节点只坏一个 ComfyUI
  - 现象：同一台 GPU 服务器上一个端口异常，另一个端口仍正常。
  - 处理：按 worker 到 Comfy 的映射只重启目标 `comfy0` 或 `comfy1`，并验证未操作端口 `/system_stats` 仍可用。不要整机重启，也不要执行无 service 名 compose 操作。
- SCAIL-2 正式 RunPod 停摆或 OOM
  - 现象：`runpod_prod_scail2_manual_NN` heartbeat 进入 `error` / unhealthy，或 RunPod 日志提示内存限制。
  - 处理：先通过 Central control `disable` 停止接新单，确认 `current_task_id` 为空后用 `scripts/runpod_prod_ops.sh down --profile scail2 --slot NN --execute` 删除 Pod 释放计费资源。不要让 Dashboard 或 CLI 并发创建多条相同 `scail2` add operation；需要恢复时重新 `add --profile scail2 --count 1`，等待 disabled heartbeat、canary 两单 MP4 成功后再决定是否 enable。SCAIL-2 正式主路径仍以 gpu-002 slot0 LAN runtime 为准。

## 6. 文档维护口径
- 涉及本地正式灾备 compose 的文档必须和 `safe_deploy.sh` 的真实顺序保持一致；云正式和云测试文档必须分别以对应 cloud compose / cloud deploy 脚本为准。
- 若云测试流程、旧本地测试栈退役口径、`safe_deploy_cloud_test.sh` 或“测试优先发布”策略发生变化，必须同步更新运维技能、`AGENTS.md` 与本子模块文档。
- 若云正式、本地灾备、Cloudflare Tunnel、Pages 或边缘 upstream 发生变化，必须同步更新云正式、网络、边缘、资源画像和本地灾备文档。
- 任何涉及 Alembic 的说明，都应明确“先检查多 head，再在宿主机执行 upgrade head”。
- 任何涉及容器代码更新的说明，都应先核对卷挂载，再决定是 `restart` 还是 `--build`。
- 任何涉及 workflow 资产的说明，都应明确 Central 校验目录与 Worker 执行目录是否一致。
- 任何涉及 GPU 节点运维的说明，都应明确 worker 容器、ComfyUI 容器、模型目录和 `inst0/inst1` 目录是否共享或隔离。
