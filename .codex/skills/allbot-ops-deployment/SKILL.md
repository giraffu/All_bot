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
- **云测试控制面**：`allbot-do-sgp1-test-control` 使用 `deploy/docker-compose-cloud-test.yml`，同机运行测试 Postgres、Redis、Central API、Web API、Dashboard Backend/Frontend、imgproxy 与测试 Bot；本地主服务器运行 7 个 cloud-test worker，经 Tailscale 访问云测试 Central；对象存储为 R2 `user-data-test`。
- **云正式控制面**：正式生产运行在 `allbot-do-sgp1-control`，使用 `.env.cloud.prod`、`deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`、`scripts/safe_deploy_cloud_prod.sh` 与 `scripts/start_cloud_prod_worker.sh`。云端运行 Central/Web/Payment/Dashboard/imgproxy/TG Bot；本地主服务器运行 `cloud-prod-worker-relay` 与 7 个 `cloud-prod-comfy-agent-*`。
- **生产 Bot 安全**：重建或启动 `cloud-tg-bot-prod` 前，必须确认全网没有第二个同 token Telegram polling 实例。
- **Cloudflare 正式入口**：`web.aivison.it.com` 是 Cloudflare Pages 静态站；正式 API 健康检查是 `https://api.aivison.it.com/api/health`，不是 `web.aivison.it.com/api/health`；RMB 入口为 `https://rmb.aivison.it.com/pay/result`。
- **Dashboard**：云端 Dashboard Frontend 默认绑定 Tailscale；本地管理员入口为 `http://192.168.1.115:8086/`，由本地主服务器 Nginx 网关反代云正式 Dashboard Backend。公网管理域名必须有 Cloudflare Access 或等价身份层保护。
- **workflow 事实源**：`workers/comfy_agent/workflows` 是唯一 workflow 运行时事实源。Central API 不挂载、不 COPY、不启动校验 workflow；改 workflow/mappings/patcher 后必须重建或重启目标 Worker。
- **R2 / legacy 媒体策略**：新数据写入 R2 `user-data-prod`；legacy MinIO 只作为历史媒体只读 fallback。Worker 写路径不得配置 legacy MinIO。
- **GPU Worker 层级**：`cloud-prod-comfy-agent-*` 是本地主服务器上的 Worker Agent；GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI 是另一层。替换 worker 不会自动重启 ComfyUI，重启 ComfyUI 也不会替换 worker 代码。
- **RunPod Provider v0**：RunPod 只通过 `ops/gpu_pool_controller/providers/runpod.py` 接入，不属于本地 SSH GPU 池。云测试支持 `img2img/img2img_lora`、split video canary 与 `i2i_pro` 三任务 canary；手动云正式备用 worker 支持 `--profile img2img|image_to_video|wan22_video_v2|i2i_pro`，默认先 `disabled`，不自动按生产队列扩容。`i2i_pro` RunPod profile 同时声明 `i2i_pro,t2i-pornmaster-turbo,face_swap`，通过 workflow override 绑定 `txt2img_from_i2i_pro.json` 与 `face_swap_v2.json`，不新增业务 task type；远端镜像使用 `remote_workers/` bundle，override 解析和 workflow 文件必须同步到该目录；prod-worker heartbeat 默认等待 `3600s`，覆盖首次同步大模型的启动窗口。
- **RunPod 操作语义**：`prod-worker up --execute` 是创建/启动 Pod 并等待 disabled heartbeat，不等于放开接单；`enable/disable --execute` 只改 Central agent control，不创建/删除 Pod；`down --execute` 会删除目标正式 Pod，必须确认无 `current_task_id`；`canary --execute` 会提交真实任务并在结束后恢复目标 worker 为 `disabled`。判断是否接单必须同时看 Pod `RUNNING`、worker heartbeat 和 control `enabled`。
- **RunPod 正式按需容量口径**：正式手动 RunPod 池的容量和 profile 组合按当次运维目标决定，不写死为固定台数、固定日期或固定类型组合；某次实操的 Pod 数量/profile 组合只应进入运维日志或工单，不作为长期 SOP。启动/恢复优先用 `prod-worker scale --profile ... --desired N --execute`；真实执行时显式设置 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=<目标全局managed上限>`、`RUNPOD_MAX_PODS_PER_TYPE=<当前profile上限>`、合适的 `RUNPOD_MAX_HOURLY_COST_USD`，必要时临时设置 `RUNPOD_PROD_MAX_MANUAL_SLOTS=<slot上限>`。RunPod 返回 `There are no instances currently available` 时可按 60-120 秒间隔轮询同一条 scale 命令，但不要并发启动相同 profile/desired 的重复创建循环。
- **RunPod 关闭/缩容口径**：`disable --execute` 只停接新单不释放计费资源；删除前先 `status` 确认目标 `current_task_id` 为空。单 Pod 删除用 `down --execute`，按 profile 缩容用 `scale --desired N --execute`，全量关闭时对当前实际存在的每个 profile 分别 `scale --desired 0 --execute`；每步都复核 `managed_count` 按目标变化且 `orphans=[]`。
- **RunPod bundle 重启口径**：profile 镜像入口是 `runpod_bootstrap_from_git.sh`，首次启动会把 `deploy` 分支 clone 到 `/workspace/allbot/repo`；如果该目录已有 `remote_workers` bundle，bootstrap 会复用现有文件而不是自动 pull。新建/重建 Pod 会拉到最新 `deploy` 修复；旧 Pod 原地重启前若怀疑 bundle 过旧，先用 `disable` 停接单，再通过 SSH/diagnostic 更新 repo 或重建 Pod，避免继续读旧 workflow。
- **LAN RunPod 化一体容器测试**：第一轮只允许云测试 `gpu-002` slot0 / `img2img_lora`，临时 agent 固定 `lan_aio_test_gpu002_gpu0_img2img_lora_01`，canary 端口固定 `8190:8188`，不得替换原 `8188` 的 `comfy0`。渲染入口是 `runtime-render --runtime-shape runpod_all_in_one`，受控操作入口是 `scripts/lan_runpod_aio_canary.sh`，默认 dry-run；`start-heartbeat --execute` 只启动容器并保持临时 agent `disabled`，`enable-canary --execute` 才临时 disable `cloud_worker_test_06` 并放开临时 agent，结束必须 `restore --execute`。
- **LAN AIO 镜像来源**：LAN registry `192.168.1.115:5000` 只作为已验证 GHCR RunPod 镜像缓存；`img2img_lora` 使用 `allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`，`i2i_pro` 使用 `allbot-comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh`，`image_to_video` / `wan22_video_v2` / `wan22_aio_video` 共用 `allbot-comfy-runpod-wan22-aio-video:20260613-wan22aio-lanbase-ab9b7ea`。不要再把本地一次性 `lan-canary` tag 当作长期事实源。GPU 节点 Docker daemon 必须配置 `192.168.1.115:5000` insecure registry 后才能按该 ref 直拉；修改 `/etc/docker/daemon.json` 并 restart Docker 会影响节点容器，只能放进明确维护窗口。
- **LAN 模型缓存**：`allbot-model-cache-lan` 监听 `192.168.1.115:9010`，数据根目录 `/srv/allbot/model-cache-lan`，bucket 固定 `allbot-model-cache`。只用于 RunPod 化一体容器模型同步，不复用 legacy MinIO 或 `user-data-*` 桶。当前已缓存 `img2img_lora/2026-06-10` 与 `i2i_pro/2026-06-14-test`；全任务 dry-run / 上传入口为 `scripts/upload_all_task_models_to_lan_cache.py --env-file .env.lan.model-cache`，默认只读，真实上传必须另加 `--execute`。canonical manifest 目标包括 `image_to_video/2026-06-13-test`、`wan22_video_v2/2026-06-13-test`、`wan22_aio_video/2026-06-12-test`、`ltx_video/2026-06-10`、`face_i2i_t2i/2026-06-10`；`video_basic/2026-06-10` 不作为主 manifest，legacy `video_insert` / `video_edit` 归入 `image_to_video`，新 runtime-render 验证优先用 `--profile image_to_video`。模型对象优先复用已有 size/sha256 匹配 key，新对象写入 `models/by-sha256/<sha[:2]>/<sha>`。真实密钥只放 ignored env。
- **RunPod split video**：当前视频主路径是 `image_to_video` 与 `wan22_video_v2` 两个 profile；`wan22_aio_video` 只保留为兼容/回滚 profile。`wan22_video_v2` Pod env 默认带 `COMFY_EXTRA_ARGS=--disable-dynamic-vram`，避免 cu128 RunPod ComfyUI 0.21.x 的 DynamicVRAM/comfy-aimdo 在 `WanTEModel` 动态加载阶段卡住；同时带 `WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS=600` 与 `WAN22_VIDEO_V2_EXIT_ON_TIMEOUT=true`，任务完成超时会 interrupt ComfyUI、失败上报并退出容器让 RunPod 重启。`split-video-canary` 只允许云测试，完成或失败后必须恢复 worker control、删除 Pod 并核验 managed count 为 0。
- **RunPod canary 与 prod 手动 Pod 共存**：普通 `runpod canary` 默认仍要求 managed count 为 0。只有 cloud-test canary 需要保留既有 prod 手动备用 Pod 时，才允许显式使用 `--allow-existing-prod-managed-pods` / `RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS=true`；该开关只忽略 `allbot-runpod-prod-*-manual-` 已知前缀，任何 cloud-test 残留 Pod 仍必须阻断执行。失败保留的新测试 Pod 复跑任务应使用 `--reuse-pod-id PROFILE=POD_ID`，不要误删或重启现有 prod 手动 Pod。
- **RunPod cloud-test SSH 诊断**：后续新建 cloud-test RunPod Pod 应通过 `.env.cloud.test` 设置 `RUNPOD_PUBLIC_KEY_FILE=~/.ssh/allbot_runpod_debug_20260613_ed25519.pub` 或 `RUNPOD_PUBLIC_KEY=<ssh public key>`，由 provider 渲染为 Pod env `PUBLIC_KEY`，bootstrap 写入 `/root/.ssh/authorized_keys`。cu128 ComfyUI base 是 openSUSE Tumbleweed，镜像内必须安装 `openssh`，否则 RunPod proxy SSH 可能可用但 direct TCP SSH 会因无 `sshd` 监听而拒绝连接。只注入公钥，绝不注入私钥；生产 Pod 不开放长期 SSH。
- **RunPod 门禁**：真实 create/start/stop/delete/scale 必须同时显式设置 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、目标 Pod 上限和 `--execute`。`RUNPOD_MAX_PODS_TOTAL` 是全 managed RunPod 池总上限，按“已有 managed Pod + 本轮目标新增/保留 Pod”动态计算；`RUNPOD_MAX_PODS_PER_TYPE` 是当前 task/profile 单类型上限，只覆盖当前 profile 的 desired；`RUNPOD_MAX_HOURLY_COST_USD` 必须覆盖目标 managed Pod 总成本。生产 RunPod 操作还必须用户明确确认。
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
- Web/Dashboard 卡顿排查不要只看 `docker stats`；必须同时比较云内 API、公网 API、Pages 静态站、R2/legacy 媒体、Central Redis 队列事实、GPU 利用率和前端串行请求。

## 6. 交付要求
- 研发阶段默认报告云测试验证结果，不声称已发布正式。
- 正式发布总结必须说明：测试环境已验证、用户已确认进入正式发布、实际更新的服务、迁移状态、验证命令结果和回滚入口。
- 若修改部署入口、compose、worker workflow、RunPod profile、R2/legacy fallback、agent control 或运维脚本，必须同步更新相关 docs / skills，并调用 `allbot-kb-auto-updater`。
