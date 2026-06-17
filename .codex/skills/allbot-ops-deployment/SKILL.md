---
name: "allbot-ops-deployment"
description: "处理 Docker Compose 编排、云正式/云测试控制面、本地正式灾备、Alembic 迁移和故障恢复。研发默认先发测试环境，正式发布需用户明确确认。"
---

# AllBot 运维指南与容器管理 (Ops & Deployment)

本技能用于规范 AllBot 的部署、迁移、容器更新和系统级排障。默认以当前“云正式控制面 + 云测试控制面 + 本地正式灾备 + 本地 GPU worker / RunPod 备用 worker”的真实运行口径为准。

## 0. 使用前先看什么
- 云正式长期 SOP：`docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`
- 云测试 SOP：`docs/子模块_云测试控制面部署_cloud_test_control_plane.md`
- 本地正式灾备：`docs/子模块_本地正式灾备切换_local_prod_fallback.md`
- GPU / RunPod：`docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`
- 局域网 GPU SSH：`docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`
- 局域网 GPU 资源：`docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`
- 边缘节点：`docs/子模块_边缘节点运维指南_edge_node_ops.md`

## 1. 当前运维口径
- **测试优先部署**：功能研发、联调、修复与配置调整默认先更新云测试控制面，优先使用 `scripts/safe_deploy_cloud_test.sh`。只有用户明确要求正式发布、上线或交付验证时，才允许进入云正式部署。
- **标准部署入口**：云测试使用 `scripts/safe_deploy_cloud_test.sh`；云正式使用 `scripts/safe_deploy_cloud_prod.sh` 或 cloud-prod compose 单服务重建；本地 `safe_deploy.sh` 只用于云正式整体故障时的本地正式灾备。
- **云测试控制面**：`allbot-do-sgp1-test-control` 使用 `deploy/docker-compose-cloud-test.yml`，同机运行测试 Postgres、Redis、Central API、Web API、Dashboard Backend/Frontend、imgproxy 与测试 Bot；本地主服务器运行 8 个 cloud-test worker，经 Tailscale 访问云测试 Central；对象存储为 R2 `user-data-test`。
- **云正式控制面**：正式生产运行在 `allbot-do-sgp1-control`，使用 `.env.cloud.prod`、`deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`、`scripts/safe_deploy_cloud_prod.sh` 与 `scripts/start_cloud_prod_worker.sh`。云端运行 Central/Web/Payment/Dashboard/imgproxy/TG Bot；本地主服务器运行 `cloud-prod-worker-relay` 与 7 个 `cloud-prod-comfy-agent-*`。
- **生产 Bot 安全**：重建或启动 `cloud-tg-bot-prod` 前，必须确认全网没有第二个同 token Telegram polling 实例。
- **Cloudflare 正式入口**：`web.aivison.it.com` 是 Cloudflare Pages 静态站；正式 API 健康检查是 `https://api.aivison.it.com/api/health`，不是 `web.aivison.it.com/api/health`；RMB 入口为 `https://rmb.aivison.it.com/pay/result`。
- **Dashboard**：云端 Dashboard Frontend 默认绑定 Tailscale；本地管理员入口为 `http://192.168.1.115:8086/`，由本地主服务器 Nginx 网关反代云正式 Dashboard Backend。公网管理域名必须有 Cloudflare Access 或等价身份层保护。
- **workflow 事实源**：`workers/comfy_agent/workflows` 是唯一 workflow 运行时事实源。Central API 不挂载、不 COPY、不启动校验 workflow；改 workflow/mappings/patcher 后必须重建或重启目标 Worker。
- **R2 / legacy 媒体策略**：新数据写入 R2 `user-data-prod`；正式 Web/Dashboard 运行时不再生成 legacy MinIO URL，R2 miss 后只允许当前 R2/S3 短签、空值或 `pending_result`。`LEGACY_MINIO_READ_FALLBACK_ENABLED` 默认 `false`，云正式 Web/Dashboard compose 应清空 legacy endpoint/key/public URL；legacy MinIO 只保留给 `scripts/backfill_history_r2_objects.py --source-storage legacy`、人工回滚和旧外链排障。Worker 写路径不得配置 legacy MinIO。
- **R2 可见热集只读审计**：核对云正式 Web 可见媒体是否仍缺 R2 对象时，优先用一次性容器运行 `scripts/audit_visible_hotset_r2_objects.py --env-file .env.cloud.prod --recent-limit 8 --report-dir logs`，必要时 bind mount 当前脚本到 `/app/scripts/`。该脚本只读查询 Postgres 与 R2 HEAD，默认包含每用户最近 8 条、Gallery 投稿、History 收藏、Gallery like/apply active posts、prompt unlock active posts，并输出 JSON/Markdown/CSV 缺失附录到 `logs/`。全量审计默认用 `--db-batch-size 1000` 分批读取 History 详情，`--concurrency` 会同时控制 R2 HEAD semaphore 与线程池 worker，`--progress-interval` 可观察进度；不得使用 `docker compose config` 或打印 `.env.cloud.prod`；审计不需要重建或重启正式服务。
- **GPU Worker 层级**：`cloud-prod-comfy-agent-*` 是本地主服务器上的 Worker Agent；GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI 是另一层。替换 worker 不会自动重启 ComfyUI，重启 ComfyUI 也不会替换 worker 代码。
- **RunPod Provider v0**：RunPod 只通过 `ops/gpu_pool_controller/providers/runpod.py` 接入，不属于本地 SSH GPU 池。云测试支持 `img2img/img2img_lora`、split video canary 与 `i2i_pro` 三任务 canary；手动云正式备用 worker 支持 `--profile img2img|image_to_video|wan22_video_v2|i2i_pro`，默认先 `disabled`，不自动按生产队列扩容。`i2i_pro` RunPod profile 同时声明 `i2i_pro,t2i-pornmaster-turbo,face_swap`，通过 workflow override 绑定 `txt2img_from_i2i_pro.json` 与 `face_swap_v2.json`，不新增业务 task type；远端镜像使用 `remote_workers/` bundle，override 解析和 workflow 文件必须同步到该目录；prod-worker heartbeat 默认等待 `3600s`，覆盖首次同步大模型的启动窗口。
- **RunPod 日常入口**：云正式手动备用池日常操作优先用 `scripts/runpod_prod_ops.sh status|up|add|enable|disable|down|scale|canary|rollback`；该 wrapper 默认 dry-run，真实 mutation 必须 `--execute`，且 mutation 必须显式 `--profile`。日常新增容量用 `add --count N`，只创建空闲 slot，不触碰已有 RunPod；`scale --desired N` 是高级精确目标入口，会删除超出 slot，Dashboard 禁止使用。`up/add/scale` 如需抢 RunPod 库存可显式加 `--retry-unavailable --max-attempts N --retry-interval SEC`，只对无库存错误做有界重试。底层 `python scripts/gpu_pool_controller.py runpod prod-worker ...` 保留为高级诊断/专项入口。
- **Dashboard RunPod 管理入口**：系统监控页的 `RunPod 管理`、最近操作 `终止` 与 RunPod worker 卡片 `暂停/删除` 只作为云正式手动池 Web 日常入口，后端位于 `dashboard/backend/routers/runpod.py` / `dashboard/backend/services/runpod_admin_service.py`，仍异步调用 `scripts/runpod_prod_ops.sh`，不重写 provider 逻辑。Web 数量是 profile 新增数量；旧前端若发送 `desired_count`，后端也按新增数量解释，不会调用 `scale --desired` 或删除已有 slot。后台 operation 只保存在当前 Dashboard Backend 进程内存，默认 30 秒间隔、100 次无库存重试；`终止` 仅适用于运行中的 `add` operation，会向该 operation 进程组发 SIGTERM，并只对日志已记录的本次新建 slot 逐个执行 `down --slot NN --execute`，未记录到新建 slot 时不推测删除其它 Pod。Dashboard 后端默认优先使用容器内 `/app/.env` 作为 `--runpod-env-file` 与 `--prod-env-file`，云正式挂载的 `.env.cloud.prod` 必须包含完整且可被 shell/dotenv 解析的 `RUNPOD_*` 手动池配置；不要把本机测试专用 `RUNPOD_PUBLIC_KEY_FILE` 路径带入云正式容器。Dashboard 容器仍可用 `DASHBOARD_RUNPOD_ENV_FILE`、`DASHBOARD_RUNPOD_PROD_ENV_FILE`、`DASHBOARD_RUNPOD_OPS_SCRIPT` 覆盖实际 env/script 路径；API 和 operation log 只能返回脱敏命令、状态与日志尾部，禁止输出 `.env.*`、RunPod API key、agent token、JWT、R2 key 或 presigned URL。
- **RunPod 操作语义**：`prod-worker up --execute` 是创建/启动 Pod 并等待 disabled heartbeat，不等于放开接单；`enable/disable --execute` 只改 Central agent control，不创建/删除 Pod；`down --execute` 会删除目标正式 Pod，必须确认无 `current_task_id`；`canary --execute` 会提交真实任务并在结束后恢复目标 worker 为 `disabled`。判断是否接单必须同时看 Pod `RUNNING`、worker heartbeat 和 control `enabled`。
- **RunPod 正式按需容量口径**：正式手动 RunPod 池的容量和 profile 组合按当次运维目标决定，不写死为固定台数、固定日期或固定类型组合；某次实操的 Pod 数量/profile 组合只应进入运维日志或工单，不作为长期 SOP。启动/恢复优先用 `scripts/runpod_prod_ops.sh add --profile ... --count N --execute`；真实执行时显式设置 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`，必要时设置 `RUNPOD_PROD_MAX_MANUAL_SLOTS=<slot命名空间上限>`，默认建议 `100`。RunPod 返回 `There are no instances currently available` 时可用 wrapper 的 `--retry-unavailable` 做有界轮询；不要并发启动相同 profile/count 的重复创建循环。
- **RunPod 关闭/缩容口径**：`disable --execute` 只停接新单不释放计费资源；删除前先 `status` 确认目标 `current_task_id` 为空。单 Pod 删除用 `down --execute`，按 profile 缩容用 `scale --desired N --execute`，全量关闭时对当前实际存在的每个 profile 分别 `scale --desired 0 --execute`；每步都复核 `managed_count` 按目标变化且 `orphans=[]`。
- **RunPod bundle 重启口径**：profile 镜像入口是 `runpod_bootstrap_from_git.sh`，首次启动会把 `deploy` 分支 clone 到 `/workspace/allbot/repo`；如果该目录已有 `remote_workers` bundle，bootstrap 会复用现有文件而不是自动 pull。新建/重建 Pod 会拉到最新 `deploy` 修复；旧 Pod 原地重启前若怀疑 bundle 过旧，先用 `disable` 停接单，再通过 SSH/diagnostic 更新 repo 或重建 Pod，避免继续读旧 workflow。
- **LAN RunPod 化一体容器测试**：第一轮只允许云测试 `gpu-002` slot0 / `img2img_lora`，临时 agent 固定 `lan_aio_test_gpu002_gpu0_img2img_lora_01`，canary 端口固定 `8190:8188`，不得替换原 `8188` 的 `comfy0`。渲染入口是 `runtime-render --runtime-shape runpod_all_in_one`，受控操作入口是 `scripts/lan_runpod_aio_canary.sh`，默认 dry-run；`start-heartbeat --execute` 只启动容器并保持临时 agent `disabled`，`enable-canary --execute` 才临时 disable `cloud_worker_test_06` 并放开临时 agent，结束必须 `restore --execute`。
- **LAN RunPod 化一体容器生产灰度/接管**：生产 AIO 不得复用云测试 helper；日常入口优先用 `scripts/lan_aio_prod_ops.sh status|enable-aio|disable-aio|rollback|stop-old`，默认 dry-run，真实 mutation 必须 `--execute`。底层高级入口是 `scripts/lan_runpod_aio_prod_canary.sh`，只允许 `gpu-002` 固定映射：slot0 `cloud_prod_worker_06 -> lan_aio_prod_gpu002_gpu0_img2img_lora_01`，端口 `8190`；slot1 `cloud_prod_worker_07 -> lan_aio_prod_gpu002_gpu1_image_to_video_01`，端口 `8191`。`runtime-render --runtime-shape runpod_all_in_one --environment cloud-prod` 必须显示 `RUNPOD_ENVIRONMENT=cloud-prod`、`CENTRAL_API_URL=https://worker-central.aivison.it.com`、`MINIO_*_BUCKET=user-data-prod`，且不得出现 `cloud-test` / `user-data-test`。生产切换先 `draining` legacy worker 并等待当前任务自然结束；首次拉 LAN registry 镜像前配置 gpu-002 Docker insecure registry 会重启 Docker，必须放在维护窗口。`start-heartbeat --execute` 只有在 Central 看到临时 agent 处于 disabled、无 `current_task_type` 且 status 非 `running`，并且 heartbeat 带 `node_id=gpu-002`、`provider=lan_ssh`、`runtime_profile`、`pool_managed=true` 时才算通过；Central 可能保留 idle worker 的旧 `current_task_id`，等待 idle 时以 `current_task_type` / `running` 状态为准。若旧镜像 `/pop` 不携带 `agent_id` 或 heartbeat 缺 GPU pool 元数据，必须停止灰度并更新 remote_workers bundle。生产 helper 会同步并挂载当前 `remote_workers/`，AIO entrypoint 必须先安装 `remote_workers/requirements.txt`，再执行 LAN model cache 同步到 `/workspace/ComfyUI/models`，最后把 baked ComfyUI `models` 链接到该目录；小窗口达到目标接单数后先 `drain-temp --execute`，等已接任务终态后再 `restore --execute`。正式接管时先让 legacy worker `cloud_prod_worker_06/07` 进入 `disabled`，再 enable 两个 AIO agent；gpu-002 原 `comfy0/comfy1` 与本地主服务器 `cloud-prod-comfy-agent-6/7` 默认保留作为热回滚，不删除。AIO 稳定并完成目标任务验收后，如需释放资源，只允许通过日常入口 `stop-old --execute` 停止旧容器，不删除；回滚时优先用 `rollback --execute`，顺序是先启动旧 ComfyUI，再启动旧 agent，最后 restore legacy worker。
- **SCAIL-2 LAN AIO 测试容器**：`scripts/lan_scail2_aio_test.sh` 只用于 gpu-002 GPU0/`8190:8188` 的手工测试窗口，会在 `--execute start` 前 drain/disable `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 并保持 `cloud_prod_worker_06=disabled`，slot1 保持运行。容器 `allbot-lan-aio-gpu-002-gpu0-scail2-test` 不得设置 `AGENT_ID` / `CENTRAL_API_URL` / `SUPPORTED_TASK_TYPES`，只启动 ComfyUI UI 与 LAN model sync；完成 smoke 后视频复制到 `gpu-002:/root/scail2-test-results/<timestamp>/`，恢复 slot0 用同一 helper `restore --execute`。
- **SCAIL-2 Web 测试 worker**：业务测试不修改上述 ComfyUI 手工容器，它仍不接 Central；本地主 `workers/docker-compose-cloud-worker-test.yml` 另有 `cloud-comfy-agent-test-8` / `cloud_worker_test_08` 指向 `http://192.168.1.2:8190`，声明 `SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_video_replacement`、`POOL_RUNTIME_PROFILE=scail2`、`POOL_NODE_ID=gpu-002`、`POOL_GPU_INDEX=0`。`scripts/start_cloud_worker_test.sh` 启动后会把该 agent control 置为 `disabled`，验证 `/object_info`、workflow mapping 和 Web 5s smoke 后才可手动 enable；不得同步到云正式 worker compose。
- **LAN AIO 镜像来源**：LAN registry `192.168.1.115:5000` 只作为已验证 GHCR RunPod 镜像缓存；`img2img_lora` 使用 `allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`，`i2i_pro` 使用 `allbot-comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh`，`image_to_video` / `wan22_video_v2` / `wan22_aio_video` 共用 `allbot-comfy-runpod-wan22-aio-video:20260613-wan22aio-lanbase-ab9b7ea`。不要再把本地一次性 `lan-canary` tag 当作长期事实源。GPU 节点 Docker daemon 必须配置 `192.168.1.115:5000` insecure registry 后才能按该 ref 直拉；修改 `/etc/docker/daemon.json` 并 restart Docker 会影响节点容器，只能放进明确维护窗口。
- **LAN 模型缓存**：`allbot-model-cache-lan` 监听 `192.168.1.115:9010`，数据根目录 `/srv/allbot/model-cache-lan`，bucket 固定 `allbot-model-cache`。只用于 RunPod 化一体容器模型同步，不复用 legacy MinIO 或 `user-data-*` 桶。当前已缓存 `img2img_lora/2026-06-10` 与 `i2i_pro/2026-06-14-test`；全任务 dry-run / 上传入口为 `scripts/upload_all_task_models_to_lan_cache.py --env-file .env.lan.model-cache`，默认只读，真实上传必须另加 `--execute`。canonical manifest 目标包括 `image_to_video/2026-06-13-test`、`wan22_video_v2/2026-06-13-test`、`wan22_aio_video/2026-06-12-test`、`ltx_video/2026-06-10`、`face_i2i_t2i/2026-06-10`；`video_basic/2026-06-10` 不作为主 manifest，legacy `video_insert` / `video_edit` 归入 `image_to_video`，新 runtime-render 验证优先用 `--profile image_to_video`。模型对象优先复用已有 size/sha256 匹配 key，新对象写入 `models/by-sha256/<sha[:2]>/<sha>`。真实密钥只放 ignored env。
- **RunPod split video**：当前视频主路径是 `image_to_video` 与 `wan22_video_v2` 两个 profile；`wan22_aio_video` 只保留为兼容/回滚 profile。`wan22_video_v2` Pod env 默认带 `COMFY_EXTRA_ARGS=--disable-dynamic-vram`，避免 cu128 RunPod ComfyUI 0.21.x 的 DynamicVRAM/comfy-aimdo 在 `WanTEModel` 动态加载阶段卡住；同时带 `WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS=600` 与 `WAN22_VIDEO_V2_EXIT_ON_TIMEOUT=true`，任务完成超时会 interrupt ComfyUI、失败上报并退出容器让 RunPod 重启。`split-video-canary` 只允许云测试，完成或失败后必须恢复 worker control、删除 Pod 并核验 managed count 为 0。
- **RunPod canary 与 prod 手动 Pod 共存**：普通 `runpod canary` 默认仍要求 managed count 为 0。只有 cloud-test canary 需要保留既有 prod 手动备用 Pod 时，才允许显式使用 `--allow-existing-prod-managed-pods` / `RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS=true`；该开关只忽略 `allbot-runpod-prod-*-manual-` 已知前缀，任何 cloud-test 残留 Pod 仍必须阻断执行。失败保留的新测试 Pod 复跑任务应使用 `--reuse-pod-id PROFILE=POD_ID`，不要误删或重启现有 prod 手动 Pod。
- **RunPod cloud-test SSH 诊断**：后续新建 cloud-test RunPod Pod 应通过 `.env.cloud.test` 设置 `RUNPOD_PUBLIC_KEY_FILE=~/.ssh/allbot_runpod_debug_20260613_ed25519.pub` 或 `RUNPOD_PUBLIC_KEY=<ssh public key>`，由 provider 渲染为 Pod env `PUBLIC_KEY`，bootstrap 写入 `/root/.ssh/authorized_keys`。cu128 ComfyUI base 是 openSUSE Tumbleweed，镜像内必须安装 `openssh`，否则 RunPod proxy SSH 可能可用但 direct TCP SSH 会因无 `sshd` 监听而拒绝连接。只注入公钥，绝不注入私钥；生产 Pod 不开放长期 SSH。
- **RunPod 门禁**：真实 create/start/stop/delete/add/scale 必须同时显式设置 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true` 和 `--execute`。`RUNPOD_MAX_PODS_TOTAL`、`RUNPOD_MAX_PODS_PER_TYPE`、`RUNPOD_MAX_HOURLY_COST_USD` 不再作为 Dashboard/API/provider 阻断门禁；`RUNPOD_PROD_MAX_MANUAL_SLOTS` 只控制 manual slot 命名空间，不是容量或成本限制。生产 RunPod 操作还必须用户明确确认。
- **密钥输出红线**：`.env.cloud.prod`、`.env.cloud.test`、`docker compose config`、RunPod create payload、presigned URL、R2 key、GitHub/GHCR token、Bot token、JWT secret 都不得贴进聊天、日志报告或文档。

## 2. 迁移与发布红线
- 部署前必须检查 Alembic multiple heads；发现多 head 立即中止。
- Alembic 迁移通过后在宿主机显式执行 `alembic upgrade head`；不要写“容器下次启动会自动应用迁移”。
- 生产脚本必须显式导出 `BOT_TYPE=PROD`，测试脚本显式使用测试口径；不要依赖 `config.py` 默认值。
- `env_file` 只传给容器，不参与 compose 文件 `${...}` 插值；涉及 compose 默认值时必须渲染并核对容器内实际 env。
- 普通研发不得默认执行 `safe_deploy.sh`、生产 compose 或正式服务重建。
- 不要把“修 Bug/联调/改配置”理解为“允许上线”；进入正式发布前必须有明确用户确认。
- 单服务生产重建禁止 `--remove-orphans`、无 service 名 compose 命令、全组 `docker rm` 过滤器；只清目标 service 容器和同 service label 残留。
- 不要把 `docker restart` 当代码发布方式，尤其是 Web API、Dashboard 等 COPY 型服务。
- 云测试退役脚本 `scripts/cleanup_cloud_test_for_prod.sh` 默认 dry-run；不得删除 R2 `user-data-test` 或误改正式入口。

## 3. 生产单服务重建
用户明确要求只重建某个正式服务时，先确认 service 存在，再按目标服务最小范围处理。

本地主服务器旧版 `docker-compose 1.29.2` 可能在 recreate 时触发 `KeyError: 'ContainerConfig'`。恢复时只删除目标 service 的容器和同 service label 残留，再 `up -d --no-deps`；禁止 `--remove-orphans`。

本地灾备 worker 示例：

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

云正式 worker/relay 热更新示例：

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

常规云正式 worker/relay 更新应先开启维护或等价门禁，等待 pending/running 或目标 worker 当前任务归零；紧急抢修才按目标 worker 直接处理，并明确接受该 worker 当前任务可能中断。

## 4. GPU 与 RunPod 操作红线
- GPU Pool Controller 切换任务能力前，应先通过 agent control 将目标 worker 置为 `draining`，等待当前任务自然结束，再同步模型或调整 compose。
- GPU worker 自动恢复入口为 `scripts/watch_cloud_worker_recovery.sh --env cloud-test|cloud-prod --mode dry-run|execute`。云测试可用 execute 做故障注入；云正式默认只允许 dry-run，真实 execute 必须用户另行确认。
- watchdog 只可精确恢复本地主服务器上的 relay 或单个 worker 容器；禁止重启 GPU 节点、ComfyUI 容器、全量 compose 或 `--remove-orphans`。
- 远程登录局域网 GPU 节点默认使用 SSH Host alias，不在命令、日志或文档中输出密码；驱动、系统服务、Docker daemon 或 ComfyUI 服务级修改应先确认维护窗口。
- `allbot-gpu-226` 的 ComfyUI 是宿主机进程，不是 Docker `comfy0`；不要对它执行 `docker restart comfy0`。
- 双卡 GPU 节点只操作目标 `comfy0` 或 `comfy1`；禁止因为一个容器异常而整机 reboot、无 service 名 `docker compose down/up` 或批量删除所有 Comfy 容器。
- 模型下载、Docker pull/build 或大视频输出前必须重新检查磁盘。
- ComfyUI 素材清理优先用 `scripts/cleanup_lan_comfy_artifacts.sh`，先 dry-run，显式 `--execute` 才删除；不得清理 `models/custom_nodes/workflows`。
- RunPod SSH 只用于云测试或失败现场短时诊断，需人工从 RunPod UI 提供当次 proxy SSH 信息；生产路径不依赖 SSH，也不得要求生产 Pod 暴露永久 SSH。
- LAN 一体容器在 gpu-002 上必须使用 cloud-test Central 域名 `worker-central-test.aivison.it.com`；从 GPU 节点直连 `100.82.124.91:8004` 超时是已知网络事实，不应用作容器内 Central URL。

## 5. 验证要求
- 云测试验证至少包括 cloud-test compose `ps`、`8004/health`、`8001/api/health`、`8044/api/health`、`8087/api/health`、`/system/workers`、本地 relay `/ready` 与 watchdog dry-run。
- 云正式验证至少包括云内 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health`、`8086/api/health`，公共 `https://web.aivison.it.com`、`https://api.aivison.it.com/api/health`、`https://rmb.aivison.it.com/pay/result`，本机 relay `127.0.0.1:8013/health`，Central `/system/status` 与 `/system/workers`。
- 生产单服务重建后必须验证目标容器 `Up`、`RestartCount=0`、最近日志无高频 `ERROR/Traceback/Exception`，关键非敏感 env 符合目标环境。
- worker 更新后还要确认 Central heartbeat、ComfyUI WebSocket、R2 上传成功后才 `/complete`，并观察 `relay_forward_failed`、`sidecar_upload_failed`、`error/quarantined`。
- GPU 节点单容器操作后必须验证目标 ComfyUI `/system_stats`、`/queue`、对应 worker Central heartbeat，以及另一 ComfyUI 端口未受影响。
- Web/Dashboard 卡顿排查不要只看 `docker stats`；必须同时比较云内 API、公网 API、Pages 静态站、R2 公开域名/短签、是否误返回 legacy `assets` URL、Central Redis 队列事实、GPU 利用率和前端串行请求。

## 6. 交付要求
- 研发阶段默认报告云测试验证结果，不声称已发布正式。
- 正式发布总结必须说明：测试环境已验证、用户已确认进入正式发布、实际更新的服务、迁移状态、验证命令结果和回滚入口。
- 若修改部署入口、compose、worker workflow、RunPod profile、R2/legacy 媒体策略、agent control 或运维脚本，必须同步更新相关 docs / skills，并调用 `allbot-kb-auto-updater`。
