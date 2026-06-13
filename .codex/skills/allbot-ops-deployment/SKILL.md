---
name: "allbot-ops-deployment"
description: "处理 Docker Compose 编排、云正式/云测试控制面、本地正式灾备、Alembic 迁移和故障恢复。研发默认先发测试环境，正式发布需用户明确确认。"
---

# AllBot 运维指南与容器管理 (Ops & Deployment)

本技能用于规范 AllBot 的部署、迁移与系统级排障，必须以当前云正式、云测试和本地灾备的真实运行口径为准。

## 1. 模块功能描述
- **测试优先部署**：功能研发、联调、修复与配置调整默认先更新云测试控制面，优先使用 `scripts/safe_deploy_cloud_test.sh`；旧本地测试栈脚本/compose 仅作为历史保留和必要人工取证材料，不再作为受支持的测试或回滚环境。只有在用户明确要求正式发布或交付验收通过后，才允许更新正式环境。
- **标准部署入口**：云测试使用 `scripts/safe_deploy_cloud_test.sh`；云正式使用 `scripts/safe_deploy_cloud_prod.sh` 或 cloud-prod compose 单服务重建；本地 `safe_deploy.sh` 只用于云正式整体故障时的本地正式灾备。
- **云测试控制面入口**：DigitalOcean SGP1 独立测试 Droplet `allbot-do-sgp1-test-control` 使用 `scripts/safe_deploy_cloud_test.sh` 与 `deploy/docker-compose-cloud-test.yml`。云端运行 Postgres、Redis、Central API、Web API、Dashboard Backend、Dashboard Frontend、imgproxy 与测试 Bot；数据库和缓存只服务云测试栈，不复用正式托管库/缓存。GPU worker 仍在本地主服务器以 `workers/docker-compose-cloud-worker-test.yml` 运行，通过云测试 Tailscale IP `100.82.124.91` 访问云端 Central API；对象存储事实源为 R2 `user-data-test`。
- **云正式控制面入口**：正式生产运行在 `allbot-do-sgp1-control`，使用 `.env.cloud.prod`、`deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`、`scripts/safe_deploy_cloud_prod.sh` 与 `scripts/start_cloud_prod_worker.sh`。生产热修优先 cloud-prod 单服务重建；`cloud-tg-bot-prod` 重建前必须确认全网只有一个生产 Telegram polling 实例。云正式 Web API 必须配置非占位 `JWT_SECRET_KEY`，preflight 应在启动前拦截缺失或默认值。
- **云正式当前生产入口**：2026-06-07 晚间正式生产已切到 DigitalOcean 云控制面。云端运行 `cloud-central-api-prod`、`cloud-web-api-prod`、`cloud-payment-api-prod`、`cloud-dashboard-backend-prod`、`cloud-dashboard-frontend-prod`、`cloud-imgproxy-prod` 与 `cloud-tg-bot-prod`；本地运行 `cloud-prod-worker-relay` 与 `cloud-prod-comfy-agent-1..7`，worker 默认先连本机 relay，再由 relay 访问云 Central。无法接入 Tailscale 的远程 Windows GPU 节点使用 `remote_workers/` 独立 venv 包，内含 bundled `comfy_agent`、`remote_relay` 和最小 `src` 兼容模块，并通过 worker 专用 Cloudflare Tunnel 域名访问云 Central `:8003`。云正式长期 SOP 见 `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`。生产热修优先用 `scripts/safe_deploy_cloud_prod.sh` 或 cloud-prod compose 单服务重建，不再默认走旧本地 `safe_deploy.sh`。
- **云正式负载/卡顿排障基线**：2026-06-08 17:10 巡检确认，云控制面本身通常不是第一瓶颈；云内 Web/Central/Dashboard 健康接口可在毫秒级返回，公网 API 需以 `https://api.aivison.it.com/api/health` 分段验证。用户反馈 Web 卡顿时，先做延迟分段、Central Redis pending/running/heartbeat、GPU 利用率、Web R2 result timeout、`assets.aivison.it.com` legacy 回源与前端串行请求检查，再决定是否重建服务或扩容。
- **本地 Dashboard 网关入口**：管理员局域网入口固定为 `http://192.168.1.115:8086/`，由本地主服务器 `dashboard/docker-compose-local-gateway.yml` 的 Nginx 生产网关承接静态资源，并通过 Tailscale 反代云端 Dashboard Backend `100.107.220.127:8043`。上线/切换先用 `dashboard-local-gateway-8085` canary 验证，再停止旧 `8086` Vite dev，启动 `dashboard-local-gateway-8086`；该流程不得重建云正式 Dashboard Backend。旧 `0.0.0.0:8043` SSH 转发只作为临时兼容入口，长期应移除或收紧到 `127.0.0.1`。
- **云端 Dashboard 前端入口**：`cloud-dashboard-frontend-test` 默认绑定云测试 Tailscale `100.82.124.91:8087`；`cloud-dashboard-frontend-prod` 默认绑定云正式 Tailscale `100.107.220.127:8086`，`/api/` 在 Docker 内网反代 Dashboard Backend。公网管理域名只能通过 Cloudflare Tunnel + Access 或等价身份层保护，禁止裸开 `8086`/`8043`。
- **Cloudflare Pages/API Tunnel 正式入口**：正式入口为 `web.aivison.it.com` -> Cloudflare Pages 项目 `allbot-web-prod`，`api.aivison.it.com` -> 云机 `allbot-do-sgp1-control` 上的 Cloudflare Tunnel -> `100.107.220.127:8000`。Tunnel connector 必须跑在云机，不能复用本地主服务器的 RMB tunnel；正式 Pages 构建用 `frontend npm run build:cf-prod` 并指向 `https://api.aivison.it.com/api`。历史 canary 材料已归档到 `docs/archive/2026-06-cloud-migration/`；Cloudflare 控制台创建 tunnel、Pages Git 集成和 custom domain 需要人工操作，token 不得贴日志或文档。
- **局域网 GPU SSH 与资源管理**：本地主服务器到 4 台 GPU 节点使用 key-based SSH，Host 别名为 `allbot-gpu-226`、`allbot-gpu-177`、`allbot-gpu-252`、`allbot-gpu-002`；SSH 详情见 `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`，硬件、ComfyUI 容器、模型挂载和单容器运维边界见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。不得把 GPU 节点密码写入 Git、docs、compose 或 `.env.cloud.prod`，需要 root 级远端操作时必须人工确认维护窗口。
- **GPU Pool Controller v1 / RunPod Provider v0**：本地 GPU 资源池第一阶段入口为 `ops/gpu_pool_controller/`、`scripts/gpu_pool_controller.py`、`deploy/docker-compose-local-registry.yml` 与 `scripts/manage_local_registry.sh`。默认 dry-run/canary，不自动重启生产 worker、ComfyUI 或 GPU 节点；`runtime-plan` 只输出 runtime/image/model/worker-env diff，`runtime-render` 只渲染标准 Comfy runtime compose，二者已支持 `--host-port`/`--container-name`/`--api-url`/`--ws-url` 备用端口 canary 覆盖；`runtime-apply`/`switch-profile`/`rollback-profile --execute` 当前会拒绝真实执行。`gpu-226` 是 `host_service`，Controller 不得为它生成 Docker 操作；`gpu-002` 是 Phase 1 试点。RunPod v0 位于 `ops/gpu_pool_controller/providers/runpod.py`，CLI 为 `python scripts/gpu_pool_controller.py runpod ...`，当前允许云测试 `img2img,img2img_lora` canary、云测试 `wan22_aio_video` dry-run/render 预检，以及手动正式 `runpod_prod_img2img_manual_01..NN` 图生图备用 worker；正式 slot 默认最多 2 个，可通过 `RUNPOD_PROD_MAX_MANUAL_SLOTS=N`、单 slot 命令 `--slot NN` 和 `prod-worker scale --desired N` 扩展，但真实扩到更多仍必须同步打开 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL>=N`、`RUNPOD_MAX_PODS_PER_TYPE>=N` 且不超过 `RUNPOD_PROD_MAX_MANUAL_SLOTS`。`wan22_aio_video` 仅限 cloud-test，视频 GPU 默认 `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090`（5090 优先、4090 回退）、`SUPPORTED_TASK_TYPES=image_to_video,wan22_video_v2`、`RUNPOD_MODEL_PREFIX=wan22_aio_video/2026-06-12-test`，当前 cloud-test template id 为 `77gi0wqo8x`，Provider 已支持 `RUNPOD_DOCKER_START_SCRIPT_FILE_WAN22_AIO_VIDEO` 和 Wan22 template-aware canary validation；未验证真实 canary 前不得接正式。真实 transfer/build/canary 仍只允许 cloud-test 且完成即删 Pod。正式手动 worker 默认 4090-only 且支持 `img2img,img2img_lora`；真实 create/start/stop/delete/scale 必须同时显式设置 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、对应 Pod 上限和 `--execute`。推荐使用 `python scripts/gpu_pool_controller.py runpod canary --env-file .env.cloud.test` 作为默认 dry-run 一键预检；真实执行仍需四重门禁和 `--execute`，命令会自动串起单 Pod 创建、readiness、RunPod worker heartbeat、临时禁用测试 worker、上传测试 PNG、任务闭环、恢复 worker、删除 Pod 和 orphan 核验，且不得输出 JWT、agent token、RunPod/R2 key、presigned URL 或完整 create/env payload。正式手动入口为 `python scripts/gpu_pool_controller.py runpod prod-worker render|status|up|enable|disable|down|canary|scale`；`up --execute` 必须先写目标 agent 的 Central control `disabled` 再创建 Pod，`scale --execute` 扩容按 `disabled -> create -> readiness -> heartbeat -> enabled`，缩容从最高 slot 往下 `disabled -> drain -> delete`，忙碌 worker 有 `current_task_id` 时必须失败而非强杀；`down --execute` 必须确认目标 worker 无 `current_task_id` 才删除，`canary --execute` 不禁用现有正式 worker，完成后恢复目标 RunPod worker 为 `disabled`。RunPod 已验证两条云测试路径：公网基础镜像 + bootstrap + R2 模型同步，以及 GHCR public baked profile 镜像 `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946` + R2 模型同步；二者都不等同于本地正式 GPU ComfyUI runtime 镜像。RunPod R2 manifest 同步入口 `remote_workers/scripts/runpod_sync_models_from_r2.py` 已支持 `.partial` 断点续传、有限重试和后续新 Pod 的进度日志；已经创建的 Pod 不会热更新 `dockerStartCmd`，需删除重建才会拿到新 bootstrap。`img2img_lora` workflow 所需的 `ComfyUI-KJNodes` 可由 `remote_workers/scripts/runpod_bootstrap_from_git.sh` 在启动 ComfyUI 前默认安装，也可 baked 进 profile 镜像后设置 `RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false`、`RUNPOD_COMFY_KJNODES_ENABLED=false`。RunPod SSH 只用于云测试/失败现场短时诊断，需人工从 RunPod UI 提供当次 proxy SSH 信息；生产路径不依赖 SSH，也不得要求生产 Pod 暴露永久 SSH。详细口径见 `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`。
- **RunPod split video profile 口径**：2026-06-13 起 cloud-test RunPod 视频主路径拆成 `image_to_video` 与 `wan22_video_v2` 两个 profile，暂时复用 Wan22 template `77gi0wqo8x` 和同一个 GHCR image，但分别渲染 `SUPPORTED_TASK_TYPES`、`POOL_RUNTIME_PROFILE`、`AGENT_ID_PREFIX` 与 profile-specific manifest；`wan22_aio_video` 只保留为兼容/回滚 canary profile。视频 profile 的 GPU 调度口径为 `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090`，5090 优先，库存不足时允许 4090 回退。新增 CLI：`runpod workers render-scale|scale --profile image_to_video|wan22_video_v2`、`runpod split-video-manifests`、`runpod split-video-canary`。真实 split canary 只允许 cloud-test；默认双 profile 需临时设置 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=2`、`RUNPOD_MAX_PODS_PER_TYPE=1` 和 `--execute`，完成或失败后都要恢复 worker control、删除两个 Pod 并核验 managed count 为 0；分阶段验证时可传 `--profile wan22_video_v2` 或 `--profile image_to_video`，此时只创建 1 个 Pod，必须把 `RUNPOD_MAX_PODS_TOTAL` 收窄为 `1`，并只禁用支持该 profile 任务类型的非 RunPod worker。若第二个 Pod 创建失败，必须立即删除第一个已创建 Pod，避免计费残留。
- **RunPod / R2 变量分层**：`MINIO_*` / `R2_*` 始终表示用户数据桶，云测试为 `user-data-test` + `https://r2-test.aivison.it.com`，云正式为 `user-data-prod` + `https://r2.aivison.it.com`；`RUNPOD_MODEL_*` 始终表示模型缓存桶 `allbot-model-cache`，`img2img_lora` 默认 `img2img_lora/2026-06-10`，`wan22_aio_video` 为 `wan22_aio_video/2026-06-12-test`，split 视频为 `image_to_video/2026-06-13-test` 与 `wan22_video_v2/2026-06-13-test`。`RUNPOD_MODEL_ACCESS_KEY` / `RUNPOD_MODEL_SECRET_KEY` 是模型桶真实 S3 凭据名，`RUNPOD_MODEL_ACCESS_KEY_REF` / `RUNPOD_MODEL_SECRET_KEY_REF` 只是 RunPod Secret reference 字符串；RunPod 用户数据桶 secret 分测试 `allbot_cloud_test_*` 和正式 `allbot_cloud_prod_*` 两套。Cloudflare `cfat_...` API token 不用于 S3 客户端，不写入 `.env.cloud.*`、日志或知识库；完整变量字典见 `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`。
- **RunPod model-transfer Pod 并发口径**：`scripts/create_runpod_model_transfer_pod.py` 默认仍只允许 1 个临时 transfer Pod；只有用户明确要求并发同步不同批次大对象时，才可在 cloud-test 临时设置 `RUNPOD_MAX_PODS_TOTAL=2`，且必须同时满足 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true` 和 `--execute`。完成后逐个删除 Pod，核验 RunPod managed transfer Pod 为 0、R2 active multipart 为 0；不得把该 2 Pod 口径带入生产或正式 worker。
- **GitHub/GHCR token 口径**：Wan22 RunPod profile 镜像优先通过 GitHub Actions `.github/workflows/runpod_wan22_profile_image.yml` 手动构建/推送，workflow 使用仓库 `GITHUB_TOKEN` 登录 GHCR 并做匿名 manifest 检查；本机 `scripts/build_runpod_profile_image.sh --profile wan22_aio_video` 只作为调试/兜底。GitHub token 只用于 `docker login ghcr.io`、GHCR push 或 GitHub package 管理，不是 `RUNPOD_API_KEY`、R2 S3 key、agent token，也不进入 RunPod Pod env。`.env.cloud.test` / `.env.cloud.prod` 可保存真实值但不得提交或输出；当前 `all-github-token` 带中划线，不能通过 `source` 直接导出，本机推镜像前需手工映射到合法 shell 变量 `GHCR_TOKEN` / `GITHUB_TOKEN`。GHCR push 后必须用空 `DOCKER_CONFIG` 匿名 pull/inspect 验证 package public。
- **Wan22 RunPod 冷拉状态**：2026-06-13 旧 `wan22_aio_video` GHCR 镜像为 28 层、压缩约 6.59 GiB，不包含业务大模型；两次 5090 cloud-test 真实 canary 均卡在 RunPod `Downloading your container...` 冷拉阶段并中止，未进入模型同步或任务执行，Pod 已清理。第一轮启动优化切到 RunPod 官方 PyTorch/CUDA base `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` 后，GitHub Actions 成功发布 `20260613-wan22aio-runpodbase-89eca6c`，但 manifest 为 36 层、压缩约 11.94 GiB、最大单层约 4.0 GiB；真实 canary Pod `cqghk2kaa1x5dq` 约 10 分钟仍停在 `runtime=false` / `pod_readiness`，已中断并清理到 managed Pod=0。回退 `yanwk/comfyui-boot:cu128-slim` 清理版后，`20260613-wan22aio-yanwkclean-108c7ea` 为 28 层、压缩约 7.01 GiB，但单 Pod 仍约 8 分钟卡在 cold pull 并清理到 managed Pod=0。随后使用 cloud-test template `77gi0wqo8x` 创建 Pod `jt7o48kip6ohq2`，成功越过容器冷拉并完成模型同步、注册 `runpod_test_wan22_aio_video_jt7o48kip6ohq2`；第一条 `image_to_video` canary 任务 `23a54cc8-5b88-404b-8b45-170ef14c0bd4` 落库但 Central task_type 变成 `img2img`、输出为 PNG、`extra_outputs` 为空，canary 失败在缺少 `last_frame`，Pod 与 worker control 已清理到 0。图生图更快主要因为镜像约 6.35-6.40 GiB、custom nodes 少、direct image 成功路径更早被验证且可能命中缓存；Wan22 下一阻塞点是云测试 Web/Core 到 Central 的 `image_to_video` 派发链路，不再是 RunPod template/模型同步。DaSiWa installer 可参考 custom node/依赖清单，但当前官方 Linux installer 仍是 wizard/self-updating 口径，不适合直接放进每次 RunPod cold-start 的 `dockerStartCmd`。Wan22 后续启动优化优先评估 RunPod Network Volume/High-performance storage 预热 `/workspace/ComfyUI/models`，避免每次从 R2 重拉几十 GiB。
- **局域网 GPU ComfyUI 素材清理**：清理 GPU 节点磁盘时优先使用 `scripts/cleanup_lan_comfy_artifacts.sh`，默认 dry-run，必须显式 `--execute` 才删除；当前策略是 `output/temp` 清 60 分钟以前文件，`input` 只清 24 小时以前文件。不要把“只保留最近 1 小时”直接套到 `input`，因为已进入 ComfyUI 队列的 prompt 可能仍引用输入文件。不得清理 `models/custom_nodes/workflows`。
- **云正式旧媒体策略**：新数据写入 R2 `user-data-prod`；旧 `bot-data` 不再要求切换前全量强搬，改用 `scripts/backfill_history_r2_objects.py --visible-scope user-visible --source-storage legacy` 预热用户可见集合，并通过 `LEGACY_MINIO_*` 在 Web API / Dashboard 读路径启用本地 MinIO 只读 fallback。Worker 写路径不得配置 legacy MinIO。预热顺序推荐为原文件 `--media-only`、legacy 缩略图 copy-only、再用 `--source-storage current --generate-missing-thumbnails` 从已预热 R2 原文件生成缺失缩略图；历史详情/Gallery/Wan22 预览必须做返回 URL 可读验收，不能只验 S3 HEAD。
- **云正式边缘入口模板**：`web.aivison.it.com` 正式静态站已切到 Cloudflare Pages，正式 API 健康检查使用 `https://api.aivison.it.com/api/health`；`web.aivison.it.com/api/health` 会返回 Pages SPA HTML，不再是 API 入口。`all_bot_nginx_cloud_prod.conf` 仍必须保留 `assets.aivison.it.com` 到本地 MinIO 的 legacy 代理和 `/root/dist` 回滚副本。RMB 正式入口首选继续使用 Cloudflare Tunnel，当前回源为云 Payment API；如需紧急回滚，用 `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute` 切回本地 Payment API。切换/回滚脚本默认 dry-run，真实执行必须显式 `--execute`。
- **边缘 VPS 资源与运维**：当前边缘层包含 Web/Nginx VPS (`100.88.57.122`/`154.17.30.113`) 与 Telegram Local API VPS (`69.63.220.115`)。Web 节点用 `frontend/ssh_key/id_rsa.pem` 登录，根盘可用空间极低，Nginx cache/log 变更前必须先查 `df -h`；Telegram 节点当前主服务器未配置可用 SSH key，完整排障前需补齐 SSH。详见 `docs/子模块_边缘节点运维指南_edge_node_ops.md`。
- **本地正式灾备入口**：本地主服务器只保留云正式整体故障时临时接管正式服务的一套方案，操作手册为 `docs/子模块_本地正式灾备切换_local_prod_fallback.md`。切换前必须停云 Bot 或确认云 Bot 不可用，避免生产 token 双实例；本地 `.env` 必须是生产口径，并且旧本地 compose 的历史硬编码默认值/占位值必须通过 compose 渲染和容器内实际 env 核对；RMB 可用 `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute` 切回本地 Payment API。`safe_deploy.sh` 只允许在该灾备语境中使用；`safe_deploy_test.sh` 不再是受支持回滚方案。
- **云测试退役入口**：如未来需要退役云测试，使用 `scripts/cleanup_cloud_test_for_prod.sh`。脚本默认 dry-run，真实清理必须 `--execute`；不得删除 R2 `user-data-test`，不得误改正式服务或 `web.aivison.it.com`。
- **迁移保护**：部署前检查 Alembic multiple heads；发现多 head 立即中止。
- **宿主机迁移执行**：通过后直接在宿主机执行 `alembic upgrade head`，不依赖容器启动时自动迁移；生产脚本加载 `.env` 后显式导出 `BOT_TYPE=PROD`。
- **本地灾备分阶段重建**：只有本地正式灾备接管时，才按 workers -> central api -> 主服务群 -> dashboard -> 旧边缘静态站的顺序启动或重建；云正式不走该路径。
- **生产单服务重建**：当用户明确要求只重建某个正式服务时，使用目标 compose 目录内的单 service 流程；必须避免全量 `safe_deploy.sh`、避免 `--remove-orphans`、避免旧版 `docker-compose` 直接 `--force-recreate` 触发 `ContainerConfig` 兼容错误。
- **故障恢复**：处理 MinIO 503、Nginx 404/502、容器代码未更新、环境变量未生效等典型问题。
- **旧本地测试 worker 变量陷阱**：`workers/docker-compose-test.yml` 内的 `${...}` 插值不会读取 `env_file: ../.env.test`；若因人工取证短时启动旧本地测试 worker，仍必须核对容器内实际生效变量，避免 401 或读写错误桶。
- **workflow 资产事实源**：`workers/comfy_agent/workflows` 是唯一 workflow 目录。Central API 不再挂载、COPY 或启动校验 workflow；修改 workflow 时默认只更新 Worker 目录，并重建/重启对应 Worker。

## 2. 操作规范
- 修改数据库结构时：
  - 先更新模型
  - 生成 migration
  - 确保只有一个 Alembic head
  - 测试研发阶段先通过 `scripts/safe_deploy_cloud_test.sh` 或测试库宿主机 Alembic 验证升级
  - 只有在用户明确要求正式发布时，才通过云正式脚本/生产库宿主机 Alembic 执行升级
- 修改未挂载源码卷的服务代码时：必须 `--build` 重建镜像，不能只 `restart`。
- 功能研发默认目标环境是云测试控制面：`.env.cloud.test` + `deploy/docker-compose-cloud-test.yml`；旧本地隔离测试栈 `.env.test`、`backend/docker-compose-test.yml`、`workers/docker-compose-test.yml`、`deploy/docker-compose-test.yml` 仅作历史保留/人工取证材料，不再作为知识库推荐的测试或回滚路径。
- 若用户明确要把测试控制面部署到 DigitalOcean Droplet，使用 `scripts/safe_deploy_cloud_test.sh`。该脚本使用 `.env.cloud.test`，要求 `CLOUD_TEST_DATABASE_URL` 指向同机 `postgres-test:5432/bot_db_test`，`CLOUD_TEST_REDIS_URL`/`CLOUD_TEST_WORKER_REDIS_URL` 指向同机 `redis-test` 的测试 DB；云端不使用正式托管 PostgreSQL/Valkey。当前服务端口绑定云测试 Tailscale IP `100.82.124.91`；配置 `CLOUD_TEST_BIND_IP=0.0.0.0` 只能配合主机防火墙或云防火墙白名单临时使用，恢复后必须改回 Tailscale IP。`.env.cloud.test` 不得提交。当前云测试对象存储直连 R2：`MINIO_SECURE=true`，`MINIO_BUCKET/MINIO_INPUT_BUCKET/MINIO_RESULT_BUCKET/MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`；Web owner 视频结果依赖 R2 公网 URL，缺失会停在 99% / `pending_result`。Web 直传依赖 R2 桶 CORS，`user-data-test` 必须允许 `web-test.aivison.it.com`/`web.aivison.it.com` 的 `GET/PUT/HEAD`。
- 云测试公网 Web 入口继续使用 `web-test.aivison.it.com` 的边缘 VPS 静态站；前端静态资源由 `frontend npm run deploy:edge-test` 发布到 `web` VPS `/root/dist-test`，VPS Nginx 的 `/api/` 必须反代到云测试 Web API `http://100.82.124.91:8001`。Dashboard 测试前端由 `cloud-dashboard-frontend-test` 提供，默认 `100.82.124.91:8087`。云测试服务端口绑定到该 Tailscale IP；公网 eth0 上的 `8001/8004/8044/8084/8087` 由 `allbot-cloud-test-firewall.service` drop。
- 云端全链路切换前，先用 `scripts/stop_local_test_preserve.sh` 停止本地主服务器原测试栈但保留数据，再用 `scripts/start_cloud_worker_test.sh` 启动 7 个 `cloud-comfy-agent-test-*` 本地 GPU worker。
- 云测试 `bot-test` 默认禁用 TON 链上支付轮询；若需要支付联调，先确认测试库 checkpoint 与通知目标，再通过 `.env.cloud.test` 显式设置 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`。
- 云正式准备阶段先运行 `scripts/safe_deploy_cloud_prod.sh --preflight-only`、`scripts/start_cloud_prod_worker.sh --preflight-only` 和 `scripts/stop_local_prod_entry_preserve.sh --dry-run`；真正预启动控制面需显式传 `--start-control-plane`，worker 需显式传 `--start`，本地正式入口停止需显式传 `--execute`。
- 云正式当前生产热修阶段，云端控制面代码更新优先在 `allbot-do-sgp1-control:/home/deploy/APP/All_bot` 备份文件后同步，再用 `docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build <service>` 与 `up -d --no-deps <service>` 替换目标服务。真实 `docker compose config` 输出不得贴出。
- Cloudflare Pages/API Tunnel 已是正式入口；若重新启用 canary，只允许为 CORS allowlist 热更 `web-api-prod`，并使用 `bash scripts/check_cloudflare_canary.sh` 验收。不得把历史 canary 文档当成当前待办。
- 云测试退役阶段先运行 `scripts/cleanup_cloud_test_for_prod.sh --dry-run` 核对对象；真实清理时传 `--execute`，不得同时执行正式切流、正式 Bot 启动或边缘 Nginx reload。
- 云正式 `.env.cloud.prod` 不得提交；所有真实密钥只能来自该忽略文件。`.dockerignore` 必须忽略 `.env.*`，避免 root Docker image 把私有云正式变量 COPY 进镜像。
- 云正式迁移期若启用 `LEGACY_MINIO_*`，必须确认 `LEGACY_MINIO_PUBLIC_URL` 是浏览器可读 URL；该配置只用于历史媒体读取 fallback，不是新数据写入目标。
- 云正式 compose 渲染会展开密钥；真实 `docker compose config` 输出不得贴到日志、文档或聊天中。
- 云正式首发 worker 只包含 7 个 `cloud-prod-comfy-agent-*`；`worker_remote_01/02` 未纳入首发时，必须确认没有独占任务类型缺口。
- 云正式支付控制若仅依赖现有 Web `MAINTENANCE`，Bot RMB/Stars callback 仍可能创建订单；本轮正式切换口径已确认接受该低频风险。维护窗口先只开启 Web 维护状态并等待当前队列自然归零，不立即停止本地 Bot 或旧 worker；最终 dump 前再停止本地 Bot/旧入口，并导出 `orders` 中 `PENDING`/`CREATED` 待处理订单最终快照。
- 测试完成前，不得默认重建生产 Bot、生产 Web API、生产 Payment API、生产 Central API 或正式 Dashboard。
- 交付前必须把“测试环境已验证通过、准备正式发布”作为显式阶段切换条件，不得自行跳过用户验收。
- 若因人工取证短时启动旧本地测试 worker，必须额外核对容器内实际生效的 `AGENT_SECRET_TOKEN`、`MINIO_INPUT_BUCKET=bot-data-test`、`MINIO_RESULT_BUCKET=comfyui-temp-test`；不要误以为 compose `${...}` 插值会自动读取 `.env.test` 的 `env_file` 值。若重建云测试 cloud-worker，则核对 `MINIO_ENDPOINT=<R2 endpoint host>`、`MINIO_INPUT_BUCKET=user-data-test`、`MINIO_RESULT_BUCKET=user-data-test`、`MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_SECURE=true`。
- 修改 workflow JSON、`mappings.json` 或 workflow patcher 时，默认以 `workers/comfy_agent/workflows` 为运行时事实源；Central API 不再维护 backend 副本，也不再执行 workflow 启动校验。
- 云正式 Central 高频观测接口使用共享 Redis 客户端与短 TTL/stale 缓存；Dashboard stats 也有短缓存和 single-flight。排查管理后台卡顿时先区分 Central 观测慢、Dashboard stats 慢和本地 GPU/ComfyUI 生成停顿。
- 云正式 Web 卡顿不要只看 `docker stats`。必须同时比较：云机内 `100.107.220.127:8000/8003/8043`、公网 `api.aivison.it.com` Tunnel、Pages 静态站、R2/legacy 媒体与前端串行请求；`web.aivison.it.com/api/health` 不再是 API 健康检查。
- 云正式结果页/历史/Gallery 卡顿要优先查 `cloud-web-api-prod` 的 `Timed out resolving web result R2 URL` 与 `Unexpected object_exists failure`，以及 Web 边缘 `assets.aivison.it.com` 的 `upstream prematurely closed` / `upstream timed out`。这些问题会表现为 `/api/tasks/{id}/result`、Gallery、History 的 499 或用户端等待超时。
- 云正式 Dashboard 卡顿要统计 `cloud-dashboard-backend-prod` 中 `Circuit Breaker is OPEN`，并区分云端/本地 Dashboard 网关、Central 观测接口、外部余额接口和 Dashboard stats 缓存失效；不要把 Dashboard 熔断直接当作任务调度失败。Dashboard Nginx 网关可短缓存 `/api/stats*` 与 `/api/system/status|workers|concurrency_stats`，但登录、退款、封禁、删除和清理类写操作不得缓存。
- 云正式队列压力要看 Central Redis 事实：`comfy:queue:pending`、`comfy:queue:running`、`comfy:task_heartbeat:*` TTL、pending 最老等待时间和 `queue_by_type`。`healthy_workers=7` 且 heartbeat TTL 正常时，pending 增长通常是容量/任务类型分布或视频长尾耗时，不是 worker 离线。
- 云正式 worker compose 包含本地 relay/上传 sidecar。更新 `workers/comfy_agent`、`workers/local_relay`、`worker_requirements.txt`、`remote_workers/` 或 worker compose 时，测试 canary 需额外验证 relay `/health` 与 `/ready`、`relay_forward_failed`/`sidecar_upload_failed` 日志、R2 上传成功后才 `/complete`，以及 Central `/system/workers` 无 error/quarantined。
- GPU worker 自动恢复入口为 `scripts/watch_cloud_worker_recovery.sh --env cloud-test|cloud-prod --mode dry-run|execute`。云测试可用 execute 做故障注入验证；云正式默认只允许 dry-run 观测，真实 execute 必须用户另行明确确认。watchdog 只可精确恢复本地主服务器上的 relay 或单个 `cloud-*-comfy-agent-*` 容器，禁止重启 GPU 节点、ComfyUI 容器、全量 compose 或 `--remove-orphans`。relay `/ready` 返回 404 表示当前运行 relay 仍是旧版本，watchdog 只能记录 `relay_ready_endpoint_missing`，不得把重启当成版本升级手段。
- 远程登录局域网 GPU 节点时默认使用 SSH Host alias，不在命令、日志或文档中输出密码；当前 4 台 GPU 节点均不是免密 sudo，驱动、系统服务、Docker daemon 或 ComfyUI 服务级修改应先确认维护窗口。
- `cloud-prod-comfy-agent-*` 是本地主服务器上的 worker 容器，GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI 是另一层。替换 worker 不会自动重启 ComfyUI；重启 ComfyUI 也不会替换 worker 代码。
- 2026-06-10 云正式更新后口径：Worker Agent 新协议生效只表示 7 个 `cloud-prod-comfy-agent-*` 已携带 `agent_id`、GPU pool heartbeat 元数据并通过 relay `/ready`；不表示底层 ComfyUI runtime 都已容器化或被 Controller 接管。`POOL_IMAGE_REF` 是期望 profile/镜像声明，不能当作实际 ComfyUI 镜像事实。
- GPU Pool Controller 切换任务能力前应先通过 agent control 将目标 worker 置为 `draining`，等待当前任务自然结束，再同步模型或调整 compose；不要用强制重启代替 drain。
- agent control 已在云测试验证：Central API 必须包含 `control/{agent_id}` 与 `pop(agent_id=...)` 控制逻辑，worker 也必须重建到真实 `/pop` 携带 `agent_id` 的版本；正式更新指南见 `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`。同步 Central 文件时不要漏 `backend/app/queue_manager_flow_helpers.py`，否则 heartbeat metadata 会 500。
- 云测试 `cloud-comfy-agent-test-6/7` 已作为 GPU pool 小范围验证入口：可用 `CLOUD_TEST_WORKER_06_TASK_TYPES`、`CLOUD_TEST_WORKER_07_TASK_TYPES`、对应 `*_RUNTIME_PROFILE` 以及 `CLOUD_TEST_WORKER_06/07_COMFY_API_URL`、`CLOUD_TEST_WORKER_06/07_COMFY_WS_URL` 临时覆盖任务类型和 Comfy 备用端口，默认值仍是 6=`img2img,img2img_lora`、7=`video_insert,image_to_video`；旧 `docker-compose 1.29.2` 切换时优先删除目标 6/7 容器再 `up -d --no-deps`，不要 `--force-recreate` 或 `--remove-orphans`。
- 本地 Docker registry 使用 `deploy/docker-compose-local-registry.yml` / `scripts/manage_local_registry.sh` 管理，数据目录为 `/srv/allbot/docker-registry`，同时绑定 `127.0.0.1:5000` 和 `192.168.1.115:5000`。主服务器本机 push/pull 使用 `localhost:5000`，GPU 节点后续 pull 前才需要在维护窗口信任 `192.168.1.115:5000` insecure registry。
- 本地模型仓库事实源为 `/srv/allbot/model-registry`，首轮通过 `workflow-model-check`、`model-import-plan`、`model-import-execute` 导入业务 workflow/LoRA/Wan22 profile 实际引用模型；bundle manifest 引用 sha256 blob，同一模型不得复制多份。
- 双卡 GPU 节点的 `comfy0/comfy1` 绑定不同 GPU 和不同 `inst0/inst1` 输入输出目录，但共享模型目录。排障或更新功能时只能操作目标 worker/目标 Comfy 容器；禁止因为一个容器异常而整机 reboot、无 service 名 `docker compose down/up` 或批量删除所有 Comfy 容器。
- `allbot-gpu-226` 的 ComfyUI 是宿主机进程，cwd 为 `/home/ubantu/comfyui`，不是 Docker Comfy 容器；不要对它执行 `docker restart comfy0`。
- 当前 `gpu-252` 现场要分清：`cloud_prod_worker_04`/`gpu-252:8188` 可视为本地容量缺口；`cloud_prod_worker_05`/`gpu-252:8189` 仍可用，保留 `POOL_GPU_INDEX=0`、`PIPELINE_MAX_RUNNING_TASKS=1` 的临时状态。RunPod canary 不得自动恢复 `comfy0`、不重启 `gpu-252`、不改 `comfy1/worker_05`。
- GPU 节点模型下载、Docker pull/build 或大视频输出前必须重新检查 `df -hT`；2026-06-08 已清理 ComfyUI 旧素材，但 `input/output/temp` 会持续增长。
- ComfyUI 旧素材清理要优先走 `scripts/cleanup_lan_comfy_artifacts.sh` 并先 dry-run；双卡节点通过 `comfy0/comfy1` 容器内路径分别清理，`allbot-gpu-226` 走宿主机 `/home/ubantu/comfyui/{input,output,temp}`。生产环境不建议把 `input` 保留窗口降到 1 小时。
- Dashboard Backend 启动入口必须注册 billing core providers。若管理接口涉及退款、强制终止、资产调整或订单处理，确认 `dashboard/backend/main.py` 已调用 `ensure_billing_core_providers_registered()`；只注册 task core provider 会触发 `Billing core providers 未注册`。
- Central Redis 关键读写路径仍有 P1 后续项：2026-06-10 巡检见到偶发写连接 reset 导致 `/status/{task_id}` 或 worker heartbeat/status 短暂 500。排障时先看是否可重试恢复，后续修复应加有限 retry/reconnect 和 focused tests。

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

若本地灾备 worker 正在处理任务，非紧急情况下应先告知用户会中断该 worker 当前任务，并尽量等待任务完成或确认可以中断；只有本地正式灾备整栈接管才走 `safe_deploy.sh` 的队列门禁流程。

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

本地主服务器旧版 `docker-compose 1.29.2` 可能在 recreate 时触发 `KeyError: 'ContainerConfig'`。恢复时只删除目标 `cloud-prod-comfy-agent-*` 容器和同 service label 残留，再 `up -d --no-deps`；禁止 `--remove-orphans`，禁止清理测试 worker 或旧本地 worker。常规云正式 worker/relay 更新优先开启维护或等价门禁，阻止新生成任务进入，等待 pending/running 或目标 worker 当前任务归零后再重建；紧急抢修才按目标 worker 直接处理，并明确接受该 worker 当前任务可能中断。

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
- 不要把本地灾备脚本当成普通生产发布入口；`safe_deploy.sh` 会操作旧本地正式栈，不会更新云正式 `cloud-*` 容器。
- 不要用云测试退役脚本清 R2 `user-data-test` 或边缘 `web-test.aivison.it.com`；这两个资源若要清理必须另起单独计划。
- 不要把云端 Tailscale 接入做成 subnet router；当前只允许本地主服务器访问云端测试端口，不暴露武汉家庭内网。

## 4. 测试与验证
- 测试研发阶段先验证隔离测试栈健康检查、关键 API 可达、测试库/测试 Redis/测试中控链路正确。
- 只有在测试环境完成功能验证并得到用户确认后，才进入正式环境部署验证。
- 验证 migration 在空库可顺利 `upgrade head`。
- 验证重建后容器确实运行的是新镜像，而不是旧容器旧代码。
- 云测试控制面验证至少包括 `docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps`，以及 `8004/health`、`8001/api/health`、`8044/api/health`、`8087/api/health` 健康检查；全链路还要确认 `/system/workers` 能看到 7 个 `cloud_worker_test_*` heartbeat、本地 relay `127.0.0.1:8014/ready` 返回 200、watchdog dry-run 不误报健康 worker。
- 云正式准备验证至少包括：cloud-prod control compose config、worker compose config、`.env.cloud.prod` 占位值/重复 key/`API_TOKEN == AUTH_TOKEN` 检查、`CLOUD_PROD_BIND_IP != 0.0.0.0`、R2 `user-data-prod` list/head、Telegram Local Bot API reachability，以及 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health`、`8086/api/health` 健康检查。正式 Bot profile 不在准备阶段启动。
- 云正式当前生产验证至少包括：云端 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health`、`8086/api/health`，公共 `https://web.aivison.it.com` Pages 静态站、`https://api.aivison.it.com/api/health` 与 `https://rmb.aivison.it.com/pay/result`，本地 Dashboard 网关 `http://127.0.0.1:8086/api/health`，本机 relay `127.0.0.1:8013/health`，Central `/system/status` 与 `/system/workers`，`cloud-prod-worker-relay` 与 7 个 `cloud-prod-comfy-agent-*` `RestartCount=0`，以及最近日志无高频 `ERROR/Traceback/Exception`。正式 relay 已重建新版后还要要求 `127.0.0.1:8013/ready` 返回 200；未重建时 watchdog dry-run 只应记录 `relay_ready_endpoint_missing` 且不重启。Web/Dashboard 卡顿专项还要记录云内 API、公网 API、Pages 静态站、Dashboard Frontend、R2/legacy 媒体与任务队列等待，统计 Web R2 result timeout、Dashboard circuit breaker 与 `assets` 回源异常。
- 若重新启用 Cloudflare canary，验证至少包括：`https://api-cf-test.aivison.it.com/api/health` 200、从 `Origin: https://web-cf-test.aivison.it.com` 发起的 OPTIONS preflight 2xx、`https://web-cf-test.aivison.it.com` 静态站 200、登录态 Authorization 跨域 API 正常、任务状态流不被缓存、Gallery/History/结果页仍可读 legacy assets。
- 边缘节点验证至少包括：Web VPS `nginx -t`、`systemctl is-active nginx tailscaled`、`df -h /`、`assets.aivison.it.com` 根路径/真实对象回源；正式 Web 静态站验证走 Cloudflare Pages 的 `https://web.aivison.it.com`，正式 API 验证走 `https://api.aivison.it.com/api/health`。Telegram Local API 节点在 SSH 未补齐前只能验证 22/8081/8082 端口可达，不能声称已验证容器日志或磁盘。
- 若测试 worker 涉及认证或对象存储，额外验证实际生效的 `AGENT_SECRET_TOKEN`、输入桶和结果桶与目标环境一致；云测试 R2 直连还要验证 R2 S3 `list/head`、Web API 预签名 URL 读取 200，以及从 `https://web-test.aivison.it.com` Origin 发起的 R2 `PUT` CORS 预检返回 204/200。
- 生产单服务重建后必须验证：目标容器 `Up`、`RestartCount=0`、最近日志无 `ERROR/Traceback/Exception`、关键非敏感环境变量符合正式口径。worker 需额外确认 heartbeat、Central API、ComfyUI WebSocket、MinIO 桶名正常；日志和总结中不要输出密钥值。
- GPU 节点单容器操作后必须验证：目标 ComfyUI `/system_stats`、`/queue`、对应 worker Central heartbeat，以及未操作的另一 ComfyUI 端口仍可用。双卡节点上只重启 `comfy0` 时必须确认 `comfy1` 未受影响，反之亦然。
