# 子模块: GPU 算力资源池控制器 (GPU Pool Controller)

## 1. 目标与范围
本模块记录 AllBot 第一阶段 GPU 算力资源池方案。当前不是 K8s/K3s，也不是自动生产弹性伸缩系统；它是一个以声明式配置、dry-run 计划、canary 和受控 RunPod provider 为主的运维控制器。

当前实现入口：
- 控制器包：`ops/gpu_pool_controller/`
- CLI：`scripts/gpu_pool_controller.py`
- 默认配置：`ops/gpu_pool_controller/config/`
- 本地镜像仓库：`deploy/docker-compose-local-registry.yml`、`scripts/manage_local_registry.sh`
- LAN 模型缓存：`deploy/docker-compose-model-cache-lan.yml`、`scripts/manage_lan_model_cache.sh`
- LAN RunPod 化一体容器云测试 canary：`scripts/lan_runpod_aio_canary.sh`
- LAN RunPod 化一体容器生产灰度：`scripts/lan_runpod_aio_prod_canary.sh`
- gpu-002 LAN AIO 正式日常入口：`scripts/lan_aio_prod_ops.sh`
- gpu-002 SCAIL-2 LAN AIO 正式 slot0 入口：`scripts/lan_scail2_aio_prod.sh`
- LAN AIO fleet 泛化配置：`ops/gpu_pool_controller/config/lan_aio_prod_slots.yml`
- LAN AIO fleet 泛化入口：`scripts/lan_aio_fleet_prod_ops.py`
- RunPod public provider facade：`ops/gpu_pool_controller/providers/runpod.py`
- RunPod profile/catalog 事实源：`ops/gpu_pool_controller/runpod_profile_catalog.py`
- RunPod create pod request 渲染 seam：`ops/gpu_pool_controller/runpod_pod_request.py`
- RunPod 通用 HTTP seam：`ops/gpu_pool_controller/runpod_http.py`
- RunPod 通用 auth/control seam：`ops/gpu_pool_controller/runpod_control.py`
- RunPod 云测试 canary lifecycle coordinator：`ops/gpu_pool_controller/runpod_canary.py`、`ops/gpu_pool_controller/runpod_split_video_canary.py`
- RunPod 云测试 canary case/executor seam：`ops/gpu_pool_controller/runpod_cloud_test_canary.py`
- RunPod 云测试 worker scale：`ops/gpu_pool_controller/runpod_workers.py`
- RunPod 手动正式备用 worker coordinator：`ops/gpu_pool_controller/runpod_prod_worker.py`
- RunPod 手动正式备用 worker 计划 seam：`ops/gpu_pool_controller/runpod_prod_worker_planner.py`
- RunPod 手动正式备用 worker HTTP seam：`ops/gpu_pool_controller/runpod_prod_worker_http.py`
- RunPod 手动正式备用 worker auth/control seam：`ops/gpu_pool_controller/runpod_prod_worker_control.py`
- RunPod 手动正式备用 worker canary case/executor seam：`ops/gpu_pool_controller/runpod_prod_worker_canary.py`
- RunPod 手动正式备用池日常入口：`scripts/runpod_prod_ops.sh`
- RunPod split video manifest：`ops/gpu_pool_controller/runpod_video_manifests.py`
- RunPod bootstrap/model sync：`remote_workers/scripts/runpod_bootstrap_from_git.sh`、`remote_workers/scripts/runpod_sync_models_from_r2.py`

默认边界：
- 本地 GPU 资源池只纳入可 SSH 管理的局域网 GPU 节点。
- RunPod 不属于局域网 SSH 资源池，不会出现在 `LanSshProvider.inventory_from_config()` 中。
- Controller v1 默认只做盘点、计划、渲染和 canary；不自动重启 GPU 节点、不自动替换 ComfyUI、不自动按生产队列扩容。
- 所有真实 RunPod create/start/stop/delete/scale 都必须同时满足门禁环境变量和 `--execute`。

## 2. 当前资源池口径
可 SSH 管理的局域网 GPU 节点：

| 节点 | Host alias / IP | GPU | ComfyUI 口径 |
| :--- | :--- | :--- | :--- |
| `gpu-226` | `allbot-gpu-226` / `192.168.1.226` | 1 x RTX 5090 | 宿主机 ComfyUI `8188` |
| `gpu-177` | `allbot-gpu-177` / `192.168.1.177` | 2 x RTX 5090 | 正式 LAN AIO `8190/8191` only；旧 `comfy0/comfy1` 与本地主 agent 2/3 已退役删除 |
| `gpu-252` | `allbot-gpu-252` / `192.168.1.252` | 1 x RTX 4090 48G active | 正式 LAN AIO GPU0 `8190` 承载 `img2img/img2img_lora`；故障 RTX 4090 已拆除，GPU1 `wan22_video_v2` 本地 AIO 当前 maintenance disabled，RunPod 兜底；旧 `comfy0/comfy1` stopped rollback |
| `gpu-002` | `allbot-gpu-002` / `192.168.1.2` | 2 x RTX 4090 48G | 正式 LAN AIO slot0 SCAIL-2 `8190` + slot1 image_to_video `8191`；旧 `comfy0/comfy1` stopped rollback |

必须分清两层运行态：

| 层级 | 当前事实 | Controller v1 边界 |
| :--- | :--- | :--- |
| Worker Agent 层 | 本地主服务器上的 `cloud-prod-comfy-agent-*` / `cloud-comfy-agent-test-*` 容器，负责 `pop/status/complete/heartbeat`、workflow patch、上传回报 | 可通过 agent control 置为 `enabled/draining/disabled`；可重建 agent 容器；可上报 GPU pool metadata |
| ComfyUI Runtime 层 | 局域网 GPU 节点上的真实 ComfyUI。`gpu-226:8188` 是宿主机进程，其它双卡节点是 `comfy0/comfy1` Docker 容器 | 第一阶段只盘点、canary、渲染计划；不默认接管、不默认重启、不把宿主机进程当 Docker 容器 |

`POOL_IMAGE_REF` 只是期望 profile/镜像声明，不能当作底层 ComfyUI runtime 的实际镜像事实。

## 3. 声明式配置与本地命令
主要配置文件：
- `nodes.yml`：节点、GPU、Comfy 实例、模型目录、worker 对应关系
- `task_profiles.yml`：任务类型、模型 bundle、workflow、custom node、最低显存、镜像引用
- `assignments.yml`：worker/节点支持哪些任务
- `model_bundles.yml`：模型 bundle manifest 计划与版本

常用只读 / dry-run 命令：

```bash
python scripts/gpu_pool_controller.py inventory
python scripts/gpu_pool_controller.py plan
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py image-plan \
  --source-image workers_cloud-prod-comfy-agent-1:latest \
  --repository allbot/worker-agent \
  --tag "$(git rev-parse --short HEAD)"
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06
```

模型导入器以 `workers/comfy_agent/workflows` 为事实源生成
`/srv/allbot/model-registry/bundles/<bundle>/<version>/manifest.yml`。若目标
worker 通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 替换实际执行 workflow，
`BundleImportSpec.workflow_overrides` 必须同步写入同一映射；否则
`model-import-plan` 会按 legacy 默认 workflow 拉取已经不接单的旧模型。
当前 `face_swap` 使用 `face_swap_v2.json`，`t2i-pornmaster-turbo` 使用
`txt2img_from_i2i_pro.json`，二者与 `i2i_pro.json` 共享
`i2i_pro_baseline` 的六个 Flux2/Z-Image 模型。

Runtime dry-run 说明：
- `runtime-plan` 输出 runtime/image/model/worker-env diff，不连接远端、不修改 worker。
- `runtime-render` 渲染标准 ComfyUI runtime compose；只适用于 `docker_container`。
- `runtime-plan` / `runtime-render` 支持 `--host-port`、`--container-name`、`--api-url`、`--ws-url` 做备用端口 canary 覆盖。
- `runtime-plan` / `runtime-render` 支持显式 `--runtime-shape runpod_all_in_one`，用于渲染 LAN RunPod 化一体容器；默认仍是 `standard_comfy_runtime`，不会改既有 ComfyUI compose。
- all-in-one 模式支持 `--environment cloud-test|cloud-prod`；默认 `cloud-test`，生产灰度必须显式使用 `cloud-prod`，并验收 `RUNPOD_ENVIRONMENT=cloud-prod`、`CENTRAL_API_URL=https://worker-central.aivison.it.com`、`MINIO_*_BUCKET=user-data-prod`。
- `runtime-apply`、`switch-profile`、`rollback-profile --execute` 当前会明确拒绝真实执行。
- `gpu-226` 是 `host_service`，不得生成 Docker pull/up/restart 操作。

### 3.1 LAN RunPod 化一体容器 canary

第一轮只允许 `gpu-002` slot0 / `img2img_lora`，临时 agent 固定为 `lan_aio_test_gpu002_gpu0_img2img_lora_01`，canary host port 固定为 `8190`。该路径服务于云测试闭环，不接管旧生产 agent，不修改用户侧 task type，不创建 RunPod Pod。

运行态形态：
- `runtime_shape=runpod_all_in_one`
- runtime root：`/srv/allbot/runpod-runtime`
- workspace mount：`/workspace`
- 容器内 relay：`http://127.0.0.1:8013`
- 容器内 ComfyUI：`http://127.0.0.1:8188`
- Central：`https://worker-central-test.aivison.it.com`
- LAN 模型缓存：`http://192.168.1.115:9010`，bucket 固定 `allbot-model-cache`
- LAN registry：`192.168.1.115:5000`

模型缓存和镜像入口：

```bash
scripts/manage_lan_model_cache.sh --dry-run
python scripts/upload_all_task_models_to_lan_cache.py --env-file .env.lan.model-cache
```

LAN registry 缓存已验证 GHCR RunPod 镜像，也保存 SCAIL-2 这类本地构建的测试 profile 镜像；不要把未验证的一次性本地构建 tag 当作长期事实源。当前 LAN AIO 镜像关系：
- `ghcr.io/giraffu/allbot-comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946` -> `192.168.1.115:5000/allbot/comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`
- `ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh` -> `192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh`
- `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` -> `192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`
- `remote_workers/docker/runpod_profiles/scail2/Dockerfile` -> `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260617-scail2-cu128-a492b2b-proddeps1`

注意：旧 `20260613-wan22aio-lanbase-ab9b7ea` Wan22 镜像不能被假定已 baked `rife49.pth`，只应作为回滚/热缓存场景。当前稳定新 tag `20260619-wan22aio-rife-bcf3ebd` 已 baked `rife49.pth`、`runpod_bootstrap_from_git.sh`，并通过构建 smoke 检查 `ComfyUI_Fill-Nodes` 与 `ComfyUI-Frame-Interpolation` 两处缓存路径。

GPU 节点 Docker daemon 必须信任 HTTP registry `192.168.1.115:5000` 后才能直接 `docker pull 192.168.1.115:5000/...`；未配置 insecure registry 时会被 Docker 强制按 HTTPS 访问并报 `HTTP response to HTTPS client`。修改 `/etc/docker/daemon.json` 并 restart Docker 会影响节点容器运行态，只能放在明确的节点维护窗口执行。若目标 SSH 用户没有免密 sudo，短期可在本地主服务器执行 `docker save <lan-registry-image> | ssh <gpu-host> docker load` 预置镜像；fleet `preflight` 会接受“registry 已配置”或“目标镜像已存在”任一条件。

`wan22_aio_video`、`image_to_video`、`wan22_video_v2` 三个 LAN AIO profile 共用同一个 Wan22 AIO 镜像；差异只在 runtime profile、`SUPPORTED_TASK_TYPES` 与模型 manifest。LAN AIO 的 `image_to_video` / `wan22_video_v2` split profile 由 runtime-render 自动在 `COMFY_EXTRA_ARGS` 追加 `--disable-dynamic-vram`，用于规避 cu128 ComfyUI DynamicVRAM 在 32G 5090 上的概率性 OOM。Wan22 V82 的 `FL_RIFE` 后处理还需要 `rife49.pth`，它不是大模型 manifest 的主权重；新镜像要 baked，旧镜像要用热缓存/启动 helper 补齐，不能依赖任务运行时访问 HuggingFace。

all-in-one compose 渲染：

```bash
python scripts/gpu_pool_controller.py runtime-render \
  --assignment lan-002-8188-worker-06 \
  --profile img2img_lora \
  --host-port 8190 \
  --runtime-shape runpod_all_in_one \
  --agent-id lan_aio_test_gpu002_gpu0_img2img_lora_01
```

验收时必须看到：
- `x-allbot-runtime.production_port_unchanged=true`
- `host_port=8190`、`container_port=8188`
- `runtime_shape=runpod_all_in_one`
- `model_target_dir=/workspace/ComfyUI/models`
- `model_write_scope` 只包含 `/workspace/ComfyUI/models`
- `CENTRAL_API_URL=https://worker-central-test.aivison.it.com`
- `MASTER_API_URL=http://127.0.0.1:8013`
- `PIPELINE_MAX_RUNNING_TASKS=1`
- `NO_PROXY=*`

受控 canary helper：

```bash
scripts/lan_runpod_aio_canary.sh --action preflight --dry-run
scripts/lan_runpod_aio_canary.sh --action start-heartbeat --dry-run
scripts/lan_runpod_aio_canary.sh --action enable-canary --dry-run
scripts/lan_runpod_aio_canary.sh --action restore --dry-run
```

`start-heartbeat --execute` 会先把临时 agent control 设为 `disabled`，再把 compose/env 推到 `allbot-gpu-002` 并启动 canary 容器；不会放开接单。`enable-canary --execute` 只允许在真实 Web canary 窗口内临时 disable `cloud_worker_test_06` 并 enable 临时 agent；结束后必须执行 `restore --execute`，恢复旧 worker 并停止 canary 容器。失败现场需要保留容器和日志时，`restore --execute --keep-container` 只恢复 control，不停止容器。

gpu-002 早期 AIO 正式日常入口是 `scripts/lan_aio_prod_ops.sh`。它只管理原固定生产接管范围：slot0 `img2img/img2img_lora` 与 slot1 `image_to_video/video_insert/video_edit`，默认 dry-run，真实动作必须显式加 `--execute`。2026-06-18 后 slot0/`8190` 已由 `scripts/lan_scail2_aio_prod.sh` 接管为正式 SCAIL-2 AIO，旧 `lan_aio_prod_ops.sh` 不再能代表 gpu-002 全局现状；slot0 当前状态以 SCAIL-2 helper 为准，slot1 `image_to_video` 仍可用旧 helper 观测。底层 `scripts/lan_runpod_aio_prod_canary.sh` 仍保留给旧 img2img_lora slot 的渲染、registry 配置、heartbeat-only、回滚和专项排障。

| 日常动作 | 命令 | 语义 |
| :--- | :--- | :--- |
| 状态汇总 | `scripts/lan_aio_prod_ops.sh status` | 汇总 AIO agent control/status、8190/8191 health、旧 worker 06/07、旧 `comfy0/comfy1` 与旧 agent 6/7 状态 |
| AIO 接新单 | `scripts/lan_aio_prod_ops.sh enable-aio --execute` | 校验 AIO healthy，drain/wait idle 旧 worker，再 disable legacy 并 enable 两个 AIO agent |
| AIO 停接 | `scripts/lan_aio_prod_ops.sh disable-aio --execute` | drain 两个 AIO agent，等待当前 AIO 任务完成，再保持 AIO disabled |
| 回滚旧链路 | `scripts/lan_aio_prod_ops.sh rollback --execute` | 启动旧 `comfy0/comfy1`，验证 8188/8189，启动旧 agent 6/7，restore legacy worker 并 disable AIO |
| 停旧容器 | `scripts/lan_aio_prod_ops.sh stop-old --execute` | 仅在 AIO healthy 且 legacy worker disabled 时停止旧 ComfyUI/agent 容器；不删除 |

生产灰度 helper：

```bash
scripts/lan_runpod_aio_prod_canary.sh --action preflight --slot both --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action drain --slot both --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action configure-registry --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action start-heartbeat --slot slot0 --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action enable-canary --slot slot0 --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action drain-temp --slot slot0 --dry-run
scripts/lan_runpod_aio_prod_canary.sh --action restore --slot slot0 --dry-run
```

生产灰度只允许 `gpu-002` 两个固定映射：slot0 `cloud_prod_worker_06 -> lan_aio_prod_gpu002_gpu0_img2img_lora_01`，端口 `8190`，profile `img2img_lora`；slot1 `cloud_prod_worker_07 -> lan_aio_prod_gpu002_gpu1_image_to_video_01`，端口 `8191`，profile `image_to_video`。生产执行必须先将目标 legacy worker 置为 `draining` 并等待当前任务自然完成；不要用强制重启代替 drain。生产 helper 会拒绝 test Central URL，并在启动前校验 compose 不含 `cloud-test` / `user-data-test`。slot1 `start-heartbeat --execute` 会从 gpu-002 宿主机旧 `inst1` 缓存预置 `rife49.pth` 到 AIO 内两个 RIFE 查找路径；缺失该热缓存时应停止放量，不让 FL_RIFE 后处理回退到 HuggingFace。

`start-heartbeat --execute` 必须在 Central 看到临时 agent 的 disabled heartbeat 后才算成功：临时 agent 不得是 `running`，不得有 `current_task_type`，heartbeat 必须携带 `node_id=gpu-002`、`provider=lan_ssh`、对应 `runtime_profile` 与 `pool_managed=true`。如果镜像内 remote_workers bundle 过旧，`/pop` 未携带 `agent_id` 或 heartbeat 缺少这些 GPU pool 元数据，Central agent control 无法可靠阻止临时 agent 接单；此时必须停止灰度，重建或挂载新版 remote_workers 后再试。

生产 helper 会把当前 repo 的 `remote_workers/` 同步到 gpu-002 并挂载为 `/workspace/allbot/remote_workers`，同时设置 `PYTHONPATH` 与 `PYTHONDONTWRITEBYTECODE=1`，避免继续使用镜像内旧 bundle。all-in-one 入口必须先安装 `remote_workers/requirements.txt`，再执行 `runpod_sync_models_from_r2.py` 把 LAN cache manifest 同步到 `/workspace/ComfyUI/models`，最后把 baked ComfyUI 的 `models` 链接到该目录，确保 ComfyUI `/object_info` 能枚举到 manifest 模型。小窗口灰度达到目标接单数后，先执行 `drain-temp --execute` 阻止临时 agent 继续 pop，等已接任务终态后再 `restore --execute`。

Central 可能在 worker 已回到 `idle` 后保留上一单的 `current_task_id`。生产 helper 的等待空闲逻辑以 `status == running` 或存在 `current_task_type` 作为忙碌信号；单独的陈旧 `current_task_id` 不应阻断 drain/restore 后续步骤。

gpu-002 进入 AIO 接管时仍使用同一 helper：先 `drain --slot both --execute`，再 `wait-idle --slot both --execute`，确认 legacy worker 与原 `8188/8189` 队列自然清空后，分别对 slot0/slot1 执行 `enable-canary --execute`。这会把 `cloud_prod_worker_06/07` 置为 disabled，并 enable `lan_aio_prod_gpu002_gpu0_img2img_lora_01` / `lan_aio_prod_gpu002_gpu1_image_to_video_01` 接新单。原 gpu-002 `comfy0/comfy1` 和本地主服务器 `cloud-prod-comfy-agent-6/7` 默认继续运行作为热回滚基线，不删除、不重建；AIO 稳定并完成验收后，如需释放资源只执行 `docker stop comfy0 comfy1` 与 `docker stop cloud-prod-comfy-agent-6 cloud-prod-comfy-agent-7`。回滚时先 `docker start comfy0 comfy1`，再启动 `cloud-prod-comfy-agent-6/7`，最后执行 `restore --slot slot0|slot1 --execute` 恢复 legacy worker。

gpu-002 首次生产灰度前还必须在维护窗口配置 Docker daemon `insecure-registries=["192.168.1.115:5000"]`；这会短暂重启 Docker 并影响 `comfy0/comfy1`，因此必须先 drain `cloud_prod_worker_06/07` 并确认 `8188/8189` 队列为空。配置完成后只拉取 LAN mirror 镜像，不创建 RunPod Pod，不修改生产 Web task type。
如当前 SSH 用户无免密 sudo，可只在当次命令环境传入 `LAN_AIO_GPU_SUDO_PASSWORD`；该变量不得写入 `.env`、compose、日志或文档。

### 3.2 LAN AIO fleet 泛化接管

gpu-002 专用 helper 已证明 all-in-one runtime 可以在正式 Central 下以 `disabled heartbeat -> 小窗口 enable -> drain/restore` 的方式安全接管。`gpu-177` 已用 fleet 入口整机接管，后续把 `gpu-252` 纳入 AIO 时继续使用同一套 fleet 配置和统一入口，不再复制 gpu-002 专用脚本：

- 配置事实源：`ops/gpu_pool_controller/config/lan_aio_prod_slots.yml`
- 编排入口：`scripts/lan_aio_fleet_prod_ops.py`
- 渲染事实源仍是 `python scripts/gpu_pool_controller.py runtime-render --runtime-shape runpod_all_in_one --environment cloud-prod`
- 真实密钥仍只从 `.env.cloud.prod`、`.env.lan.model-cache`、`.env.lan-aio-prod` 的 allowlist 读取；不得打印 env、compose config 展开值或 presigned URL

首批可灰度 slot：

| Slot | Legacy worker | AIO agent | Profile | Host port | 阶段 |
| :--- | :--- | :--- | :--- | ---: | :--- |
| `gpu-177-gpu0-image_to_video` | `cloud_prod_worker_02` | `lan_aio_prod_gpu177_gpu0_image_to_video_01` | `wan22_video_v2` | 8190 | `prod_enabled` |
| `gpu-177-gpu1-ltx_video` | `cloud_prod_worker_03` | `lan_aio_prod_gpu177_gpu1_ltx_video_01` | `ltx_video` | 8191 | `prod_enabled` |
| `gpu-252-gpu0-img2img_lora` | `cloud_prod_worker_04` | `lan_aio_prod_gpu252_gpu0_img2img_lora_01` | `img2img/img2img_lora` | 8190 | `prod_enabled` |
| `gpu-252-gpu1-wan22_video_v2` | `cloud_prod_worker_05` | `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` | `wan22_video_v2` | 8191 | `maintenance_disabled` |

暂缓 slot：
- `gpu-226-gpu0-face_i2i_t2i`：当前是宿主机 ComfyUI，不是 Docker `comfy0`；需要单独的 host-service 到容器化迁移方案。

2026-06-18 阶段能力口径：

| 层级 | 已覆盖/候选能力 | 当前口径 |
| :--- | :--- | :--- |
| LAN AIO 正式接单 | `img2img`、`img2img_lora`、`image_to_video`（兼容 `video_insert` / `video_edit` alias）、`wan22_video_v2`、`ltx_video`、`scail2_action_transfer`、`scail2_video_replacement` | `gpu-177` GPU0 渲染为 `wan22_video_v2`、GPU1 为 LTX；`gpu-252` GPU0 已恢复 AIO；SCAIL-2 由 `gpu-002` slot0 正式 AIO 承载，legacy `image_to_video` 主要由 gpu-002 slot1/外部容量承接 |
| LAN AIO canary-ready | 暂无固定常驻候选 | 后续新增 slot 仍必须逐 slot 验收，不跨节点批量 enable |
| 有镜像但未作为 LAN AIO 正式容量 | `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap` | 当前主要是 RunPod profile / legacy worker 口径，LAN AIO 接管需单独 slot 规划 |
| 暂缓 | `face_i2i_t2i` / `gpu-226` 综合能力 | 仍是 host-service runtime，需先迁成容器化 ComfyUI |

常用 dry-run / 只读命令：

```bash
scripts/lan_aio_fleet_prod_ops.py list
scripts/lan_aio_fleet_prod_ops.py status --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py render --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py preflight
scripts/lan_aio_fleet_prod_ops.py configure-registry --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py pull-image --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py start-disabled --slot gpu-252-gpu0-img2img_lora
scripts/lan_aio_fleet_prod_ops.py restart-aio --slot gpu-177-gpu0-image_to_video
```

真实接管顺序必须逐 slot 执行，不得一次替换整台或多台 GPU：

1. `preflight --execute` 只读确认正式 Central/Web、LAN registry、LAN model cache、目标旧 ComfyUI `/system_stats`/`/queue`、磁盘，以及目标节点已配置 Docker insecure registry 或已预置目标镜像。
2. 在维护窗口内执行 `configure-registry --slot ... --execute`；该动作会重启目标 GPU 节点 Docker daemon，必须先确保目标 legacy worker drain 且队列为空。若目标用户无免密 sudo，可改用 `docker save ... | ssh ... docker load` 预置镜像，跳过 daemon restart。
3. `pull-image --slot ... --execute` 预拉 LAN mirror 镜像。
4. `start-disabled --slot ... --execute` 启动 AIO 容器，只等待 disabled heartbeat，不允许接单。
5. 验收 compose 不含 `cloud-test` / `user-data-test`，Central heartbeat 必须带 `node_id`、`provider=lan_ssh`、`runtime_profile`、`pool_managed=true`；`image_to_video` / `wan22_video_v2` slot 的 `COMFY_EXTRA_ARGS` 必须包含 `--disable-dynamic-vram`。
6. `enable-aio --slot ... --execute` 会先把 legacy worker 置为 disabled，并拒绝在 legacy 仍 running、AIO disabled heartbeat 不可见或旧 runtime 容器仍占 GPU 显存时放开 AIO，避免同卡双 ComfyUI 抢单。
7. 灰度期可保留旧 runtime 作为热回滚；全量接管时允许在 AIO enable 前后用 `stop-old --slot ... --execute` 停旧 ComfyUI 和本地主旧 agent，但不删除容器。若用户明确放弃本地旧链路，可在确认 AIO 健康后删除旧容器、旧模型目录和旧 agent，并同步把 legacy control 固定为 `disabled`；此后该节点不得再使用 `rollback --slot ... --execute`。

LAN AIO compose 固定带 `restart: unless-stopped`。AIO bootstrap/entrypoint 会同时监管 ComfyUI、relay 与 agent；任一关键进程退出都会退出容器，由 Docker restart policy 重建干净 runtime，避免 ComfyUI 子进程 OOM 后只剩 agent 心跳继续存活。手动恢复某个已接管 AIO worker 时使用 `restart-aio --slot ... --execute` 或 Dashboard worker 卡片 `重启`：它先将目标 AIO agent control 置为 `disabled`，只对该 slot 的 all-in-one compose 执行原地 `restart`，等待容器健康和 disabled heartbeat，再把目标 agent 置回 `enabled`。该动作不重启整机 Docker daemon、不触碰旧 runtime、不跨 slot 操作；若当前 worker 正在执行任务，原地重启会中断该 worker 的当前任务，后续仍需按任务终态/僵尸清理链路收口。

`start-disabled` 支持在 slot 配置中声明 `legacy_hot_cache_copies`，用于把旧 ComfyUI 容器或 GPU 节点宿主机上由 custom node 运行期下载的热缓存文件预置进 AIO 容器。`gpu-177` 的旧 `comfy0` 来源已在 2026-06-20 退役删除，后续重建应使用带 RIFE 缓存的 `20260619-wan22aio-rife-bcf3ebd` 或模型缓存补齐，不得再从旧容器复制；`gpu-252-gpu1-wan22_video_v2` 仍声明从宿主机旧 `inst1` 路径复制同一文件。它们都是 `FL_RIFE` 后处理的运行依赖，不能依赖 AIO 容器运行时访问 HuggingFace；RunPod split video 也遵循同一红线，旧 Pod 需要 helper/模型目录补齐，新 Pod 应使用 baked RIFE 的新镜像 tag。

2026-06-18 `gpu-177` 进入整机 LAN AIO 接管：GPU0 最初由 `lan_aio_prod_gpu177_gpu0_image_to_video_01` 提供 `image_to_video`，GPU1 由 `lan_aio_prod_gpu177_gpu1_ltx_video_01` 提供 `ltx_video`。2026-06-20 已按用户确认退役本地旧链路：旧 `cloud_prod_worker_02/03` control 为 `disabled`，本地主 `cloud-prod-comfy-agent-2/3`、GPU 节点 `comfy0/comfy1`、旧 `/data/comfy` 和旧镜像已删除；gpu-177 不再提供本地旧链路回滚，恢复入口改为 AIO restart/recreate 或外部容量兜底。2026-06-23 起，fleet 配置保留 GPU0 的历史 slot/agent/container 名称以避免 8190 端口 orphan，但 `target_profile_id` 改为 `wan22_video_v2`，并用 `target_task_types=[wan22_video_v2]` 避免误接 legacy alias。

2026-06-18 `gpu-252-gpu1-wan22_video_v2` 已替换 `cloud_prod_worker_05`：AIO agent `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` 连接正式 Central，host `8191`，只声明 `SUPPORTED_TASK_TYPES=wan22_video_v2`，不承接普通 `image_to_video` 或 `video_edit`。旧 `comfy1` 与 `cloud-prod-comfy-agent-5` 已停止保留为回滚基线。2026-06-19 重启后该 slot 配置改回 `gpu_index: 1`；实测第二个生产 wan22 任务仍让 GPU1/ComfyUI 进入 unhealthy 且 Docker 无法 stop/kill 的状态，当前 control 必须保持 `disabled`，RunPod `wan22_video_v2` 继续作为正式兜底容量。

2026-06-19 `gpu-252-gpu0-img2img_lora` 从 canary-ready 转入正式 LAN AIO 接流：AIO agent `lan_aio_prod_gpu252_gpu0_img2img_lora_01` 连接正式 Central，host `8190`，按 `img2img_lora` profile 承接 `img2img` 与 `img2img_lora`。旧 `comfy0` 与 `cloud-prod-comfy-agent-4` 保留为 stopped rollback baseline，不应与 AIO 同时 enabled 或同卡占用显存。

后续优化方向：
- 配置阶段应区分 `prod_enabled`、`canary_ready`、`blocked_host_service_runtime`，避免已正式接管的 slot 仍被误读为 canary。
- `wan22_video_v2` 在 `gpu-177` GPU0 与 `gpu-252` GPU1 slot 都通过 slot-level `target_task_types` 收窄为只接 `wan22_video_v2`；后续新增共享镜像 slot 时也应优先显式声明目标 task type，避免 profile 默认 alias 误接单。
- `preflight` / `start-disabled` 需要继续强化 workflow 文件、remote_workers 挂载、模型 manifest、对象桶和 image digest 检查，减少“容器健康但工作流资产缺失”的误启用。
- LAN registry 仍依赖 GPU 节点 Docker insecure registry；配置会重启整机 Docker daemon，后续优先评估 TLS registry 或免 daemon 重启的镜像分发路径。
- Dashboard 需要把 AIO agent 的 `node_id`、`gpu_index`、`runtime_profile`、image tag/digest、旧 runtime 状态和最近失败原因展示出来，作为正式排障入口。

SCAIL-2 LAN AIO runtime 已用于 Web/Bot 的视频生视频能力：正式 LAN slot0 包含 `scail2_action_transfer`（动作迁移）、`scail2_video_replacement`（视频换人）和 `scail2_face_swap_v2`（视频换脸 v10 two-stage）。它有测试 runtime、云测试 RunPod profile、云正式 slot0 runtime 与云正式手动 RunPod profile 四条边界，不能混用测试/正式桶或 worker；正式 RunPod `scail2` profile 仍只声明动作迁移/视频换人两任务。

测试 LAN runtime 是独立于 Central 接单层的 ComfyUI runtime，不使用 `runtime-render`，入口为 `scripts/lan_scail2_aio_test.sh`。它在 gpu-002 GPU0 上临时替换原 slot0 AIO 的 `8190:8188`，容器名固定为 `allbot-lan-aio-gpu-002-gpu0-scail2-test`，workspace 为 `/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles/scail2/workspace`。`start --execute` 会先把 `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 置为 `draining`，等待当前 `img2img_lora` 任务和 8190 queue 自然空闲，再设为 `disabled` 并停止旧 `allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary`；`cloud_prod_worker_06` 保持 `disabled`，slot1 `image_to_video` AIO 不动。测试容器不设置 `AGENT_ID`、`CENTRAL_API_URL` 或 `SUPPORTED_TASK_TYPES`，只启动 ComfyUI UI、LAN model sync、Nomadoor UI workflow、业务 API workflow 和样例素材。

云正式 slot0 runtime 使用 `scripts/lan_scail2_aio_prod.sh`，同样占用 gpu-002 GPU0/`8190:8188`，但会注册正式 agent `lan_aio_prod_gpu002_gpu0_scail2_01`，容器名为 `allbot-lan-aio-gpu-002-gpu0-scail2-prod`，并由 runtime-render 的 `scail2` profile 生成 cloud-prod all-in-one compose 后在 helper 内覆盖为三任务正式 LAN 配置。该 helper 只触达旧 slot0 AIO agent `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 与旧 slot0 容器 `allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary`，不会重建 `cloud-prod-comfy-agent-1..7`，不会创建/启停 RunPod，不会操作 slot1/`8191`。`start-disabled --execute` 会 drain 旧 slot0 AIO 并等待自然空闲，停止旧 slot0 容器后启动 SCAIL-2 disabled heartbeat；验收 `/system_stats`、`/object_info` 必需节点、模型枚举、`RUNPOD_ENVIRONMENT=cloud-prod`、正式 Central、`user-data-prod`、三任务 `SUPPORTED_TASK_TYPES`、audio/v10 workflow override 与 `SCAIL2_FACE_SWAP_V10_*` 后，才执行 `enable --execute`。

SCAIL-2 镜像入口是 `remote_workers/docker/runpod_profiles/scail2/Dockerfile`，正式 AIO 当前固定 LAN tag 为 `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260617-scail2-cu128-a492b2b-proddeps1`。该镜像基于 `yanwk/comfyui-boot:cu128-slim`，使用包含 ComfyUI PR `Comfy-Org/ComfyUI#14373` 后的版本，并 baked `remote_workers/requirements.txt` 中的 FastAPI/MinIO/uvicorn/websockets 等 worker 运行依赖。它必须在 `/object_info` 暴露 `WanSCAILToVideo`、`SCAIL2ColoredMask`、`SAM3_VideoTrack`、`WanContextWindowsManual`、`VHS_LoadVideo`、`VHS_VideoCombine`。模型从 `allbot-model-cache/scail2/2026-06-17-test/manifest.json` 同步到 `/workspace/ComfyUI/models`；runtime-render 会把 baked ComfyUI 的 `models` 目录链接到该同步目录，验收还要确认主模型、SAM、CLIP Vision、Wan VAE、UMT5 和 LightX2V LoRA 都在 `/object_info` 枚举中。LoRA 路径必须是 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`，否则 Nomadoor workflow 的 LoRA dropdown 无法解析。

Web/Bot 测试业务接入不把测试 ComfyUI 容器本身注册成 worker：测试容器仍不设置 `AGENT_ID` / `CENTRAL_API_URL` / `SUPPORTED_TASK_TYPES`。接单层在本地主 `workers/docker-compose-cloud-worker-test.yml` 中新增 `cloud-comfy-agent-test-8` / `cloud_worker_test_08`，指向 `http://192.168.1.2:8190`，当前测试可声明 `SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_video_replacement,scail2_face_swap_v2` 与 GPU pool 元数据 `node_id=gpu-002`、`gpu_index=0`、`runtime_profile=scail2`，并用 audio workflow 做测试覆盖；其中视频换脸当前指向 `SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json`，并通过 `CLOUD_TEST_WORKER_08_FACE_SWAP_V10_*` 先跨 runtime 调用 `face_swap_v2.json` 生成换脸首帧。云正式 LAN 业务接单层是 `lan_aio_prod_gpu002_gpu0_scail2_01`，同样三任务写正式 Central 与 `user-data-prod`；手动正式 RunPod `runpod_prod_scail2_manual_NN` 仍只作为动作迁移/视频换人的两任务备用容量，不承接 `scail2_face_swap_v2`，不得复用 `cloud_worker_test_08` 或 `user-data-test`。

SCAIL-2 也支持独立 RunPod profile，不复用 `gpu-002/8190`。`RUNPOD_TASK_PROFILES["scail2"]` 渲染为 `SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_video_replacement`、`POOL_RUNTIME_PROFILE=scail2`、`containerDiskInGb=120`，模型桶固定 `allbot-model-cache`。cloud-test agent prefix 是 `runpod_test_scail2`，用户输入/结果桶是 `user-data-test`；cloud-prod 手动池 agent 是 `runpod_prod_scail2_manual_NN`，Pod 名称是 `allbot-runpod-prod-scail2-manual-NN`，用户输入/结果桶必须是 `user-data-prod`。镜像由 `.github/workflows/runpod_scail2_profile_image.yml` 构建 `ghcr.io/giraffu/allbot-comfy-runpod-scail2:<tag>`，Dockerfile 保留 LAN entrypoint 作为默认 CMD，但 RunPod create JSON 通过 `dockerStartCmd=["bash","-lc","exec bash /opt/allbot/runpod_bootstrap_from_git.sh"]` 启动 bootstrap。模型转存入口是 `scripts/prepare_scail2_model_r2_bundle.py --env-file .env.cloud.test --execute`，默认 dry-run，只写 `allbot-model-cache/scail2/2026-06-17-test/models/...` 与 manifest，不写 `user-data-test` 或 `user-data-prod`。

`runpod canary --task-type scail2` 是 SCAIL-2 cloud-test RunPod 验收入口。dry-run 会校验 GHCR image prefix、`allbot-model-cache`、`scail2/2026-06-17-test/manifest.json`、custom node env 关闭、bootstrap command 与 GPU 类型；真实执行会上传/复用 Nomadoor 样例参考图和 motion video，临时 disable 支持 SCAIL-2 的非 RunPod cloud-test worker（通常是 `cloud_worker_test_08`），串行提交 `scail2_action_transfer 5s` 与 `scail2_video_replacement 5s` 两个 Web 任务，要求 Central 接单 worker 为 `runpod_test_scail2_*`，结束后恢复 worker control 并删除本次 Pod。正式 RunPod 验收使用 `prod-worker canary --profile scail2` 或 `scripts/runpod_prod_ops.sh canary --profile scail2`，串行提交同样两类 5s 正式内部任务，要求 `pop_evidence.agent_id=runpod_prod_scail2_manual_NN`，结果写 `user-data-prod`，canary 结束后目标 RunPod 默认恢复 `disabled`；通过后可与 LAN slot0 `lan_aio_prod_gpu002_gpu0_scail2_01` 并行 enabled 接单。

常用命令：

```bash
scripts/lan_scail2_aio_test.sh preflight
scripts/lan_scail2_aio_test.sh build-image
scripts/lan_scail2_aio_test.sh push-image
scripts/lan_scail2_aio_test.sh start --execute
scripts/lan_scail2_aio_test.sh verify
scripts/lan_scail2_aio_test.sh run-sample
scripts/lan_scail2_aio_test.sh restore --execute
scripts/lan_scail2_aio_prod.sh preflight --execute
scripts/lan_scail2_aio_prod.sh start-disabled --execute
scripts/lan_scail2_aio_prod.sh verify --execute
scripts/lan_scail2_aio_prod.sh enable --execute
scripts/lan_scail2_aio_prod.sh rollback --execute
```

`run-sample` 只自动提交 `SCAIL-2_Animation.json`，使用 Nomadoor reference image 和 motion video；另外三个 workflow 只做 `/object_info` 节点、模型枚举与 API prompt 转换 dry-run。生成后的最新 `SCAIL-2*.mp4` 复制到 `gpu-002:/root/scail2-test-results/<timestamp>/`。测试容器默认保留运行，方便继续在 `http://192.168.1.2:8190/` 手工切换 workflow；恢复图生图 slot0 时执行 `restore --execute`，它会停测试容器、启动原 slot0 AIO 并将 `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 恢复为 `enabled`。

密钥边界：
- 真实密钥只放在 ignored env 文件，例如 `.env.lan.model-cache`、`.env.lan-aio-test` 和 `.env.lan-aio-prod`；生产 helper 也可用 allowlist 从 `.env.cloud.prod` 与 `.env.lan.model-cache` 读取必要变量，不直接 `source`。
- compose 模板只允许出现 `${LAN_AIO_*:?}` / `${LAN_MODEL_CACHE_*:?}` 占位符。
- 不要直接 `source .env.cloud.test`；RunPod dry-run 继续只使用 controller 的 `--env-file` loader。
- LAN 模型缓存 bucket 固定为 `allbot-model-cache`；截至 2026-06-22，`192.168.1.115:9010` 已缓存 `img2img_lora/2026-06-10/manifest.json`、`i2i_pro/2026-06-14-test/manifest.json`、`scail2/2026-06-17-test/manifest.json` 与 `ltx_video/2026-06-10/manifest.json`。LTX manifest 同时保留旧 v1 主模型和 10Eros v1.2 主模型。
- 全任务 LAN cache 入口为 `scripts/upload_all_task_models_to_lan_cache.py --env-file .env.lan.model-cache`，默认 dry-run；真实上传必须另行显式加 `--execute`。helper 复用共享对象池 `models/by-sha256/<sha[:2]>/<sha>`，并会复用已存在且 size/sha256 metadata 匹配的旧对象 key。
- canonical manifest 目标为 `img2img_lora/2026-06-10/manifest.json`、`i2i_pro/2026-06-14-test/manifest.json`、`image_to_video/2026-06-13-test/manifest.json`、`wan22_video_v2/2026-06-13-test/manifest.json`、`wan22_aio_video/2026-06-12-test/manifest.json`、`ltx_video/2026-06-10/manifest.json`、`face_i2i_t2i/2026-06-10/manifest.json`、`scail2/2026-06-17-test/manifest.json`。`video_basic/2026-06-10` 不作为主 manifest；legacy `video_insert` / `video_edit` 只作为兼容任务类型归入 `image_to_video`。
- 单 bundle 通用入口仍为 `scripts/upload_model_bundle_to_r2.py`，通过 `.env.lan.model-cache` 映射 `LAN_MODEL_CACHE_*` 到 `RUNPOD_MODEL_*` 后写入 LAN cache；脚本按对象 size 与 sha256 metadata 跳过已有对象，metadata key 需大小写不敏感处理以兼容 MinIO。

## 4. RunPod Provider v0
RunPod provider 当前覆盖五类路径：

| 路径 | 用途 | 当前状态 |
| :--- | :--- | :--- |
| 云测试图生图 canary | `img2img` / `img2img_lora` 真实 Web 闭环 | 已通过真实 canary；作为 RunPod 基础链路回归入口 |
| 云测试 split video canary | `image_to_video` 与 `wan22_video_v2` 分 profile 验证 | `wan22_video_v2` 已完成 Web 端真实闭环；后续以 `split-video-canary` 复验 |
| 云测试图生图 Pro canary | `i2i_pro` RunPod runtime profile，串行验证 `i2i_pro`、Web `txt2img`、`face_swap` | 已通过单任务 cloud-test Web canary；三任务 canary 由 `runpod canary --task-type i2i_pro` 承担 |
| 云测试 SCAIL-2 canary | `scail2` RunPod runtime profile，串行验证动作迁移和视频换人 | 用于 cloud-test；会临时 disable 同环境非 RunPod SCAIL-2 worker |
| 手动云正式备用 worker | `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro`、`scail2` | 代码已支持；默认创建后先 `disabled`，不开启生产自动扩容 |

RunPod 只读 / dry-run 命令：

```bash
python scripts/gpu_pool_controller.py runpod validate-key
python scripts/gpu_pool_controller.py runpod list-pods
python scripts/gpu_pool_controller.py runpod reconcile-managed-pods
python scripts/gpu_pool_controller.py runpod render-create --task-type img2img_lora --env cloud-test
python scripts/gpu_pool_controller.py runpod render-create --task-type i2i_pro --env cloud-test
python scripts/gpu_pool_controller.py runpod render-create --task-type scail2 --env cloud-test
python scripts/gpu_pool_controller.py runpod create-pod --task-type img2img_lora --env cloud-test
python scripts/gpu_pool_controller.py runpod canary --env-file .env.cloud.test --quiet
python scripts/gpu_pool_controller.py runpod canary --task-type i2i_pro --env-file .env.cloud.test --quiet
python scripts/gpu_pool_controller.py runpod canary --task-type scail2 --env-file .env.cloud.test --quiet
python scripts/gpu_pool_controller.py runpod prod-worker render --profile scail2 --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile scail2 --slot 01
```

`render-create` 不需要 `RUNPOD_API_KEY`；`create-pod` 默认 dry-run。

## 5. RunPod Profile 矩阵
云测试 profile：

| Profile | `SUPPORTED_TASK_TYPES` | `POOL_RUNTIME_PROFILE` | Agent prefix | 模型 manifest |
| :--- | :--- | :--- | :--- | :--- |
| `img2img_lora` / `img2img` | `img2img,img2img_lora` | `img2img_lora` | `runpod_test_img2img_lora` | `img2img_lora/2026-06-10/manifest.json` |
| `image_to_video` | `image_to_video` | `image_to_video` | `runpod_test_image_to_video` | `image_to_video/2026-06-13-test/manifest.json` |
| `wan22_video_v2` | `wan22_video_v2` | `wan22_video_v2` | `runpod_test_wan22_video_v2` | `wan22_video_v2/2026-06-13-test/manifest.json` |
| `i2i_pro` | `i2i_pro,t2i-pornmaster-turbo,face_swap` | `i2i_pro` | `runpod_test_i2i_pro` | `i2i_pro/2026-06-14-test/manifest.json` |
| `scail2` | `scail2_action_transfer,scail2_video_replacement` | `scail2` | `runpod_test_scail2` | `scail2/2026-06-17-test/manifest.json` |
| `wan22_aio_video` | `image_to_video,wan22_video_v2` | `wan22_aio_video` | `runpod_test_wan22_aio_video` | `wan22_aio_video/2026-06-12-test/manifest.json` |

`wan22_aio_video` 只保留为兼容/回滚 profile；新测试、新扩容和正式接入都应优先使用 split profile。
`video_basic` 不再作为独立对外任务或主 manifest 口径；GPU Pool Controller 中新增 canonical `image_to_video` profile，`video_basic` profile 仅保留 legacy 兼容命名，实际 workflow 与模型 manifest 均对齐 `image_to_video`。
`i2i_pro` 是现有 ComfyUI runtime profile，不新增业务 task type；其中 Web 文生图仍提交 `txt2img`，Central 执行面记录为 `t2i-pornmaster-turbo`，worker 通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 读取 `txt2img_from_i2i_pro.json`。图片换脸仍提交 `face_swap`，worker 通过 override 读取 `face_swap_v2.json`。
`wan22_video_v2` RunPod split profile 默认渲染 `COMFY_EXTRA_ARGS=--disable-dynamic-vram`，用于规避 cu128 ComfyUI 0.21.x 的 DynamicVRAM/comfy-aimdo 在 `WanTEModel` 动态加载阶段卡住；如需临时实验其它 Comfy 启动参数，可用 `RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS` 覆盖，并必须重新创建目标 Pod 才会生效。

手动正式 profile：

| `prod-worker --profile` | Agent id | `SUPPORTED_TASK_TYPES` | 模型 manifest | GPU |
| :--- | :--- | :--- | :--- | :--- |
| `img2img` | `runpod_prod_img2img_manual_NN` | `img2img,img2img_lora` | `img2img_lora/2026-06-10/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `image_to_video` | `runpod_prod_image_to_video_manual_NN` | `image_to_video` | `image_to_video/2026-06-13-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `wan22_video_v2` | `runpod_prod_wan22_video_v2_manual_NN` | `wan22_video_v2` | `wan22_video_v2/2026-06-13-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `i2i_pro` | `runpod_prod_i2i_pro_manual_NN` | `i2i_pro,t2i-pornmaster-turbo,face_swap` | `i2i_pro/2026-06-14-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `scail2` | `runpod_prod_scail2_manual_NN` | `scail2_action_transfer,scail2_video_replacement` | `scail2/2026-06-17-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `ltx_video` | `runpod_prod_ltx_video_manual_NN` | `ltx_video,ltx_video_flf2v,ltx_video_v2v_audio` | `ltx_video/2026-06-10/manifest.json` | `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090` |

正式 `image_to_video` / `wan22_video_v2` RunPod 镜像必须精确使用 `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`；`i2i_pro` 镜像必须以 `ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:` 开头；`scail2` 镜像必须以 `ghcr.io/giraffu/allbot-comfy-runpod-scail2:` 开头；`ltx_video` 镜像必须以 `ghcr.io/giraffu/allbot-comfy-runpod-ltx-video:` 开头；`img2img` 使用已验证 public GHCR 图生图镜像。所有 cloud-prod 手动 RunPod profile 都必须在 create payload 显式带 `dockerStartCmd=["bash","-lc","exec bash /opt/allbot/runpod_bootstrap_from_git.sh"]`；若 RunPod API 显示目标 Pod 的 `dockerStartCmd=null`，说明它没有走 bootstrap/model sync/最新 remote_workers bundle，不能通过原地 restart 修复，需先 disable 并确认无当前任务后删除重建。

## 6. 真实执行门禁
任意真实 RunPod mutation 都必须显式满足：

```dotenv
RUNPOD_DRY_RUN=false
RUNPOD_AUTOSCALER_ENABLED=true
```

并带对应 CLI 的 `--execute`。

`RUNPOD_MAX_PODS_TOTAL`、`RUNPOD_MAX_PODS_PER_TYPE`、`RUNPOD_MAX_HOURLY_COST_USD`
不再作为 provider/Dashboard 的容量或成本门禁；不要依赖它们阻断创建。云正式手动池的
slot 命名空间由 `RUNPOD_PROD_MAX_MANUAL_SLOTS` 控制，默认 `100`，只用于生成
`manual_01..manual_100` agent/pod 名称。

云测试 split video canary：
- 默认同时测 `image_to_video` 与 `wan22_video_v2`，完成后必须恢复 worker control 并删除 Pod。
- 传 `--profile image_to_video` 或 `--profile wan22_video_v2` 时只创建 1 个 Pod。
- 若只允许 4090，可临时覆盖 `RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2='NVIDIA GeForce RTX 4090'`。
- 失败或中断后必须恢复 worker control、删除 Pod，并用 `list-pods` / `reconcile-managed-pods` 确认 managed count 为 0。

## 7. 云测试 canary
云测试 canary runner 仍有自己的单次测试安全门禁；这不适用于 Dashboard / cloud-prod
`prod-worker add`。图生图默认 canary：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --download-results-dir /tmp/allbot_runpod_canary/results \
  --execute
```

split video manifest 与 canary：

```bash
python scripts/gpu_pool_controller.py runpod split-video-manifests \
  --env-file .env.cloud.test

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=2 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod split-video-canary \
  --env-file .env.cloud.test \
  --execute
```

分 profile scale dry-run：

```bash
python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile image_to_video \
  --desired 1 \
  --env cloud-test
python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile wan22_video_v2 \
  --desired 1 \
  --env cloud-test
python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile i2i_pro \
  --desired 1 \
  --env cloud-test
```

canary 摘要只允许记录脱敏后的 object key、task id、Central/Web 终态、下载后的本地路径和去掉 query string 的 result path；不要输出 JWT、agent token、presigned URL、完整 env 或完整 create payload。

内部代码边界：`runpod_canary.py` 与 `runpod_split_video_canary.py` 继续保留
CLI lifecycle、RunPod Pod 创建/等待/清理和旧私有方法兼容入口；HTTP JSON/raw、
URL 脱敏、Web JWT / bearer token、agent control、`/system/workers` 读取、任务
case payload、Central 终态等待、pop evidence、Web result 等待、R2 fallback 和
MP4/PNG/last-frame 下载校验已收口到 `runpod_http.py`、`runpod_control.py` 与
`runpod_cloud_test_canary.py`。新增 cloud-test canary profile 或调整任务 payload 时，
优先在 `runpod_cloud_test_canary.py` 增加 case/executor focused tests，再通过旧 runner
做集成回归，避免重新把 HTTP/control/下载逻辑写回 runner。

`i2i_pro` cloud-test canary 必须通过 Web API 创建真实任务，而不是只做 worker 直测。当前 canary 会串行提交 `i2i_pro`、Web `txt2img` 和 `face_swap` 三单。验收口径：
- RunPod worker heartbeat 出现为 `runpod_test_i2i_pro_*`。
- Central 任务类型分别为 `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap`，每单 `pop_evidence.agent_id` 都匹配该 RunPod worker。
- 三单 Web result 均为 `success`，最终状态均为 `done`，图片结果可下载。
- 验收结束后恢复临时禁用的非 RunPod cloud-test `i2i_pro/t2i-pornmaster-turbo/face_swap` worker，删除 Pod，并确认 managed RunPod count 回到 0。

当测试服 canary 需要与现有云正式手动备用 Pod 共存时，必须显式传
`--allow-existing-prod-managed-pods` 或设置
`RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS=true`。该开关只忽略名称前缀为
`allbot-runpod-prod-img2img-manual-`、`allbot-runpod-prod-image-to-video-manual-`、
`allbot-runpod-prod-wan22-video-v2-manual-`、`allbot-runpod-prod-i2i-pro-manual-`
的既有 managed Pod；任何 cloud-test
残留 Pod 仍会阻止 `canary --execute`。开启后 `RUNPOD_MAX_PODS_TOTAL=1`
表示“本次 cloud-test canary 只允许创建 1 个非忽略 Pod”，cleanup 验收也按
非忽略 managed Pod 数量回到 0 计算。失败现场用 `--no-cleanup` 保留的新
`i2i_pro` Pod 可通过 `--reuse-pod-id i2i_pro=<pod_id>` 复跑 Web 任务，避免重复创建 Pod。

cloud-test 诊断 Pod 如需 SSH，`.env.cloud.test` 可设置
`RUNPOD_PUBLIC_KEY_FILE=~/.ssh/allbot_runpod_debug_20260613_ed25519.pub` 或
`RUNPOD_PUBLIC_KEY=<ssh public key>`。provider 会把它渲染为 Pod env `PUBLIC_KEY`，
bootstrap 启动 sshd 时写入 `/root/.ssh/authorized_keys`；不要写入私钥，也不要把该
能力扩展为生产 Pod 的长期 SSH 入口。`yanwk/comfyui-boot:cu128-slim` 是
openSUSE Tumbleweed 基线，镜像内必须安装 `openssh`，否则 RunPod proxy SSH 可用但
direct TCP `root@<public-ip> -p <mapped-port>` 会因容器内无 `sshd` 而拒绝连接。

## 8. 手动云正式备用 worker
正式 RunPod worker 只作为手动备用，不自动按生产队列扩容。

日常入口优先使用 `scripts/runpod_prod_ops.sh`。它不改变底层 `prod-worker` 语义，只把正式手动备用池的常见动作收窄成固定 SOP；所有 mutation 默认 dry-run，真实执行必须显式 `--execute`，且必须指定 `--profile`。

| 日常动作 | 命令 | 语义 |
| :--- | :--- | :--- |
| 状态汇总 | `scripts/runpod_prod_ops.sh status` | 按 profile 汇总 managed Pod、Central heartbeat 与 control state |
| 启动备用 Pod | `scripts/runpod_prod_ops.sh up --profile img2img --execute` | 创建/启动 Pod 并等待 disabled heartbeat，不自动接单 |
| 放开接单 | `scripts/runpod_prod_ops.sh enable --profile img2img --slot 01 --execute` | 仅修改 Central control 为 enabled |
| 停止接单 | `scripts/runpod_prod_ops.sh disable --profile img2img --slot 01 --execute` | 保留 Pod，设置 Central control 为 disabled |
| 原地重启 | `scripts/runpod_prod_ops.sh restart --profile img2img --slot 01 --execute` | 调用 RunPod 原生 restart，不使用 stop/start，等待 heartbeat 并恢复 enabled；若等待阶段失败但复查确认 Pod RUNNING、worker idle 且 control 仍是本次 restart disable，会安全补一次 enable |
| 删除 Pod | `scripts/runpod_prod_ops.sh down --profile img2img --slot 01 --execute` | disable 后等待 `current_task_id` 为空，再删除目标 Pod |
| 新增容量 | `scripts/runpod_prod_ops.sh add --profile img2img --count 1 --execute` | 只创建空闲 slot，不触碰已有 RunPod；新 slot ready 后自动 enable |
| 高级精确目标 | `scripts/runpod_prod_ops.sh scale --profile img2img --desired 1 --execute` | 会删除超出 desired 的 slot，Dashboard 禁止使用 |
| 业务 canary | `scripts/runpod_prod_ops.sh canary --profile img2img --slot 01 --execute` | 真实 Web canary，结束后保持目标 worker disabled |
| 回滚 | `scripts/runpod_prod_ops.sh rollback --profile img2img --keep-pod --execute` 或 `--delete-pod` | `--keep-pod` 等价 disable；`--delete-pod` 在指定 slot 时走 down，未指定 slot 时走 `scale --desired 0` |

RunPod 4090 库存不足或 create-pod 返回机器资源/稍后再试类 500 时，`up/add/scale`
可显式使用有界重试，不要开多条并发创建循环。日常新增模板：

```bash
scripts/runpod_prod_ops.sh add \
  --profile img2img \
  --count 2 \
  --retry-unavailable \
  --max-attempts 100 \
  --retry-interval 30 \
  --execute
```

`add --count N --execute` 对 RunPod create 的“半成功”有窄恢复：如果 create 返回失败，但复查目标 slot 的 Pod 已是 `RUNNING`、对应 worker 是 `idle` 且 Central control 仍是本次 create 写入的 `disabled`，控制器会继续等待/确认 disabled heartbeat 并 enable 该新 slot。若目标 Pod 不存在、worker 不健康、control 已被其它操作改动或 task type 不匹配，operation 仍保持失败，等待人工排障。

Dashboard 系统监控页也提供正式手动 RunPod 池的日常 Web 入口：

| Dashboard 动作 | 后端 API | 底层命令语义 |
| :--- | :--- | :--- |
| `RunPod 管理` 提交多 profile 新增数量 | `POST /api/runpod/scale` | 拆成 profile 级 `scripts/runpod_prod_ops.sh add --count N --retry-unavailable --execute` operation |
| Worker 卡片 `暂停/开启` (RunPod) | `POST /api/runpod/workers/{agent_id}/pause` / `POST /api/runpod/workers/{agent_id}/enable` | `disable|enable --slot NN --execute`，只切换 Central control，不创建/删除 Pod |
| Worker 卡片 `暂停/开启` (LAN AIO) | `POST /api/runpod/lan-aio/workers/{agent_id}/pause` / `POST /api/runpod/lan-aio/workers/{agent_id}/enable` | `lan_aio_fleet_prod_ops.py disable-aio|enable-aio --slot ... --execute`，只切换目标 AIO agent 是否接新单；enable 仍执行 AIO gate 校验 |
| Worker 卡片 `重启` (RunPod) | `POST /api/runpod/workers/{agent_id}/restart` | `restart --slot NN --execute`，先 disabled，调用 RunPod 原生 restart，等待 heartbeat 后 enable；若底层等待阶段失败但目标已健康 idle，会安全恢复 enabled；禁止用 stop/start 模拟重启 |
| Worker 卡片 `重启` (LAN AIO) | `POST /api/runpod/lan-aio/workers/{agent_id}/restart` | `lan_aio_fleet_prod_ops.py restart-aio --slot ... --execute`，只重启目标 AIO 容器，等待健康/heartbeat 后 enable |
| Worker 卡片 `删除` | `DELETE /api/runpod/workers/{agent_id}` | `down --slot NN --execute`，先停接并等待当前任务结束，再删除 Pod |
| 最近操作 | `GET /api/runpod/operations` | 只读 Dashboard 后端内存 operation 状态和脱敏日志尾部 |
| 最近操作 `终止` | `POST /api/runpod/operations/{operation_id}/terminate` | 仅用于运行中的 `add` operation；终止 Dashboard 子进程后，按该次新增日志记录到的 slot 逐个执行 `down --slot NN --execute` 释放 Pod |

Dashboard 入口不重写 RunPod provider 逻辑，只异步调用 `scripts/runpod_prod_ops.sh` 或 LAN AIO fleet helper。Worker 卡片看到 `control_state=disabled|draining` 时显示 `暂停中`，接单控制按钮显示 `开启`；其它状态显示 `暂停`。数量字段是新增数量；旧前端若仍发送 `desired_count`，后端也按新增数量解释，不会触发 `scale --desired` 或删除既有 slot。当前 Dashboard profile 列表包含 `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro`、`scail2 / 视频生视频` 与 `ltx_video / 高级图生视频`；`scail2` 对应 `scail2_action_transfer,scail2_video_replacement` 两类正式任务，`ltx_video` 对应 `ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`。系统监控页的活跃 RunPod 详情来自 Dashboard `/api/system/status.runpod_profile_queue_details`，按这 6 个 profile 固定聚合 active/pending 和最长 pending 等待；`i2i_pro` 汇总 `i2i_pro,t2i-pornmaster-turbo,face_swap`，正式 RunPod `scail2` 不统计 `scail2_face_swap_v2`。同一请求里同一 profile 只能出现一次；若同 profile 已有未结束的 `add` operation，Dashboard 后端会返回 409，禁止再次提交，避免并发新增抢到同一个 `manual_NN` slot。后台 operation 默认使用 30 秒间隔、100 次无库存重试，真实执行只打开 `RUNPOD_DRY_RUN=false` 与 `RUNPOD_AUTOSCALER_ENABLED=true`，并把 `RUNPOD_PROD_MAX_MANUAL_SLOTS` 设为 `100` 或请求指定值。运行中的新增 operation 可从最近操作点 `终止`，后端会先向该 operation 的进程组发送 SIGTERM；如果该次 operation 已记录 `runpod_create_pod_NN`，会继续提交对应 slot 的 `down` 清理。未记录到创建 slot 的终止只停止等待/重试进程，不推测删除其它 Pod。云正式 Dashboard 后端默认优先把容器内 `/app/.env` 同时作为 `--runpod-env-file` 与 `--prod-env-file`；该文件由云正式 `.env.cloud.prod` 挂载，必须包含完整、shell-compatible 的 `RUNPOD_*` 手动池配置和可用 `RUNPOD_API_KEY`。不要把本机测试专用 `RUNPOD_PUBLIC_KEY_FILE` 路径带入云正式容器；生产路径默认不依赖 RunPod SSH。必要时仍可通过 `DASHBOARD_RUNPOD_ENV_FILE` / `DASHBOARD_RUNPOD_PROD_ENV_FILE` 覆盖 env 路径；不得在 API 响应、operation 日志或文档中输出任何 env 内容或密钥。

`down` 删除已有 Pod 的 preflight 只做 RunPod key、Pod 列表、reconcile 与 Central health 检查，不渲染 create pod request，因此不会因缺少 `RUNPOD_IMAGE_NAME_I2I_PRO` / `RUNPOD_IMAGE_NAME_SCAIL2` / `RUNPOD_IMAGE_NAME_LTX_VIDEO` 这类创建镜像配置而阻断删除；`up` / `add` / `render` / `canary` 仍必须具备目标 profile 的正式镜像与模型配置。

底层高级命令：

```bash
python scripts/gpu_pool_controller.py runpod prod-worker render
python scripts/gpu_pool_controller.py runpod prod-worker status
python scripts/gpu_pool_controller.py runpod prod-worker up --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker enable --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker disable --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker restart --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker down --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker add --profile img2img --count 1
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker scale --profile img2img --desired 1
python scripts/gpu_pool_controller.py runpod prod-worker render --profile i2i_pro --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile i2i_pro --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker render --profile scail2 --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile scail2 --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker render --profile ltx_video --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile ltx_video --slot 01
```

`prod-worker` 默认先加载 `.env.cloud.test` 中的 RunPod API/profile 默认值，再加载 `.env.cloud.prod` 覆盖正式 Central/Web/R2/JWT 变量；已在 shell 显式设置的 `RUNPOD_*` 执行开关和 slot 命名空间不会被 prod env 文件覆盖。
优先用 `prod-worker status` 查看正式手动 worker，因为它会按上述规则加载 env；裸
`runpod list-pods` / `pod-readiness` 只读取当前 shell env，未显式加载 `RUNPOD_API_KEY`
时会返回 `missing_RUNPOD_API_KEY`。

操作语义速查：

| 命令 | 是否触碰 Pod 生命周期 | 是否放开接单 | 主要用途 |
| :--- | :--- | :--- | :--- |
| `render` / `status` | 否 | 否 | 渲染/观测，适合 AI 运维先读状态 |
| `up --execute` | 创建并启动目标 Pod | 否，默认写 `disabled` | 新增手动正式备用 worker，等待模型同步和 heartbeat |
| `add --count N --execute` | 只创建空闲 slot | 是，新 slot ready 后自动 enable | 日常新增容量，不触碰已有 slot |
| `enable --execute` | 否 | 是，仅改 Central control | 放开已有 Pod 接正式队列 |
| `disable --execute` | 否 | 否，仅改 Central control | 保留 Pod 现场、停止接新单，用于排障或维护 |
| `restart --execute` | 同一个 Pod 原生 restart，不 stop/start | 是，恢复后自动 enable；失败兜底只在 Pod RUNNING、worker idle、control 仍是本次 restart disable 时执行 | OOM/error/disabled 后原地恢复手动 RunPod worker，避免 stop 释放 GPU；没有固定网络卷时尤其禁止用 stop/start |
| `canary --execute` | 不创建已存在的 prod Pod | 临时 enable，结束恢复 `disabled` | 提交真实 Web 任务验证目标 worker |
| `down --execute` | 删除目标 prod Pod | 否 | 下线手动备用 Pod，必须确认无 `current_task_id` |
| `scale --desired N --execute` | 按 slot 创建/删除/enable/disable | 取决于计划 | 高级精确目标数入口，会删除超出 slot |

判断“RunPod 已启动并可接单”不能只看 Pod `RUNNING`：还必须看到 Central worker heartbeat，
且 agent control 为 `enabled`。`up --execute` 后处于 ready 但 `disabled` 是预期行为；需要
`enable --execute` 才会接正式任务。

### 8.1 云正式手动 RunPod 按需新增容量

正式手动 RunPod 池的容量和 profile 组合不是固定事实，应按当次运维目标决定。某次实操的
Pod 数量、创建日期和 profile 组合只应进入运维日志或工单，不作为长期 SOP。当前
`prod-worker` 支持 `--profile img2img|image_to_video|wan22_video_v2|i2i_pro|scail2|ltx_video`；日常扩容只使用“新增容量”语义：
`scripts/runpod_prod_ops.sh add --count N` 只选择该 profile 的最低空闲 manual slot 创建新
Pod，不 enable、disable、drain、delete 或 recreate 任何已存在 slot。

| 参数 | 含义 | 设置口径 |
| :--- | :--- | :--- |
| `PROFILE` | 本轮要操作的 profile | 例如 `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro`、`scail2`、`ltx_video` |
| `COUNT` | 本轮新增 Pod 数 | 必须是正整数；不是目标总数 |
| `MANUAL_SLOT_LIMIT` | manual slot 命名空间 | 默认 `100`，只用于生成 `manual_01..manual_100` agent/pod 名称，不是容量或成本上限 |

新增示例：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${COUNT:?set number of new RunPod Pods to add}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
scripts/runpod_prod_ops.sh add \
  --profile "$PROFILE" \
  --count "$COUNT" \
  --execute
```

多 profile 共存时，对每个目标 profile 分别执行一次 `add`。Dashboard 的
`POST /api/runpod/scale` 也按新增语义执行，即旧字段 `desired_count` 仍会被解释为
新增数量，不会 scale down 既有 Pod。

`add --count N --execute` / `scale --desired N --execute` / `up --execute` / `down --execute`
会在 prod-worker 内按 profile 持有文件锁，默认锁目录为 `/tmp/allbot_runpod_locks`
（可用 `RUNPOD_PROD_OPERATION_LOCK_DIR` 覆盖），防止多个进程同时为同一 profile 规划或
删除 slot。创建路径还会在每个 slot create 前重新读取 RunPod managed Pod 列表；如果
目标 slot 已被其它操作占用，会在写 Central control 和创建 Pod 前中止。`add --count N --execute`
会先把新 slot 的 Central control 写为 `disabled`，创建 Pod，等待 RunPod readiness、模型同步、ComfyUI ready 和 Central
heartbeat；看到 disabled heartbeat 后才 enable 目标 slot。启动过程中如果 Pod 已
`RUNNING` 但 `worker_seen=false`、control 仍是 `disabled`，通常表示 bootstrap 或模型同步
还没完成，不要手动 enable。

4090 库存不足或 RunPod create-pod 临时失败时，RunPod 可能返回
`There are no instances currently available`、`This machine does not have the resources to deploy your pod`
或 `Please try again later`。优先用
`scripts/runpod_prod_ops.sh add --retry-unavailable` 对同一个 profile/count 做有界重试；
不要同时开多条相同 profile/count 的创建循环，避免重复抢同一批空闲 slot。推荐模板：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${COUNT:?set number of new RunPod Pods to add}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
scripts/runpod_prod_ops.sh add \
  --profile "$PROFILE" \
  --count "$COUNT" \
  --retry-unavailable \
  --max-attempts 100 \
  --retry-interval 30 \
  --execute
```

最终验收每个目标 slot：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${SLOT:?set target manual slot, for example 01}"
: "${MANUAL_SLOT_LIMIT:?set manual slot limit if needed}"

RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
python scripts/gpu_pool_controller.py runpod prod-worker status \
  --profile "$PROFILE" \
  --slot "$SLOT"
```

验收口径：`list_pods.count` / `reconcile.managed_count` 比新增前增加 `COUNT`、
`orphans=[]`、每个新增 worker 有 heartbeat，且 `control.state=enabled`。`worker.status=running`
可能表示正在接单，不等于异常；重点看 `types`、`runtime_profile`、`image_ref` 与目标
profile 是否一致。

### 8.2 正式 RunPod 停接、关闭与缩容

保留 Pod 但停止接新单：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${SLOT:?set target manual slot, for example 01}"

python scripts/gpu_pool_controller.py runpod prod-worker disable \
  --profile "$PROFILE" \
  --slot "$SLOT" \
  --execute
```

删除单个 Pod 前，先 `status` 确认目标 `current_task_id` 为空；若正在运行任务，等待自然结束，
不要用 RunPod UI 强删。删除示例：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${SLOT:?set target manual slot, for example 01}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
python scripts/gpu_pool_controller.py runpod prod-worker down \
  --profile "$PROFILE" \
  --slot "$SLOT" \
  --execute
```

按 profile 精确调整目标数属于高级运维入口。`scale --desired N --execute` 会按 slot
计算计划、enable 保留 slot、disable 待删 worker、等待 drain，并删除超出 desired 的 Pod；
Dashboard 禁止使用该语义。把某个 profile 缩到目标数量示例：

```bash
: "${PROFILE:?set target RunPod profile}"
: "${DESIRED:?set desired pod count for this profile}"
: "${MANUAL_SLOT_LIMIT:=100}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_PROD_MAX_MANUAL_SLOTS="$MANUAL_SLOT_LIMIT" \
python scripts/gpu_pool_controller.py runpod prod-worker scale \
  --profile "$PROFILE" \
  --desired "$DESIRED" \
  --execute
```

全量关闭时，对当前实际启用/存在的每个 profile 分别执行 `scale --desired 0 --execute`。
每步结束后复核 `reconcile.managed_count` 按预期下降且 `orphans=[]`。`disable --execute`
不会停止计费；只有 `down --execute` 或 `scale --desired 0 --execute` 删除 Pod 后才释放
RunPod 资源。

SCAIL-2 属于显存/内存压力更高的视频生视频 profile。`scail2` 代码、镜像、模型 manifest 和
Dashboard 管理入口都已具备，但它不代表线上必须常驻一个 `runpod_prod_scail2_manual_NN`。
如果目标 slot unhealthy 或触发 OOM，标准恢复是先 `disable`，确认无当前任务后 `down` 删除
Pod 释放资源；需要再次接单时重新 `add`、等待 disabled heartbeat、跑
`canary --profile scail2` 两个 5s MP4 验收，再显式 `enable`。没有 heartbeat 或已删除的
`manual_NN` 不应计入正式 SCAIL-2 容量。

LTX 正式 RunPod 是 `ltx_video` profile，面向高级图生视频三种执行类型：
`ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`。手动池 agent 前缀为
`runpod_prod_ltx_video_manual_`，Pod 前缀为
`allbot-runpod-prod-ltx-video-manual-`；GPU 优先 `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090`，
`containerDiskInGb` 至少 `180`。它默认使用
`RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_LTX_VIDEO` 指向三份 10Eros v1.2 workflow，
模型从 `allbot-model-cache/ltx_video/2026-06-10/manifest.json` 同步，不把模型 baked
进镜像，也不改 LAN AIO 或老 `LTX 2.3 *.json` workflow。`canary --profile ltx_video`
只提交一单 5s I2V MP4 验收，完成后保持 worker `disabled`；确认产物后再手动
`enable --profile ltx_video --slot NN --execute` 放开接单。

单 profile 创建模板：

```bash
: "${PROFILE:?set target RunPod profile}"

RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
python scripts/gpu_pool_controller.py runpod prod-worker up \
  --profile "$PROFILE" \
  --execute
```

正式流程红线：
- `up --execute` 固定为预检 -> 写目标 agent control `disabled` -> 创建 Pod -> 等 readiness -> 等 Central heartbeat；ready 后默认不抢正式订单。`prod-worker` 的 worker heartbeat 等待默认 `3600s`，用于覆盖 `i2i_pro` / `scail2` 首次同步大模型的启动窗口。
- `enable --execute` 才允许目标 worker 接单。
- `down --execute` 必须确认无 `current_task_id`，忙碌 worker 不提供隐式 force；删除已有 Pod 不渲染 create pod request，也不应因缺少某个 profile 的 `RUNPOD_IMAGE_NAME_*` 创建配置而失败。
- `canary --execute` 不禁用现有正式 worker；完成后恢复目标 RunPod worker 为 `disabled`。
- `prod-worker canary --profile i2i_pro --execute` 会串行提交 `i2i_pro`、Web `txt2img`、`face_swap` 三单，要求三单均由 `runpod_prod_i2i_pro_manual_NN` 接单并产出可下载图片。
- `prod-worker canary --profile scail2 --execute` 会串行提交 `scail2_action_transfer` 与 `scail2_video_replacement` 两个 5s 正式内部任务，要求两单均由 `runpod_prod_scail2_manual_NN` 接单、结果 MP4 写入 `user-data-prod` 且可下载；若需要强制命中 RunPod，应先让 SCAIL-2 pending 清空并临时 disable LAN SCAIL-2 agent。
- `prod-worker canary --profile ltx_video --execute` 会提交一单 `ltx_video` 5s I2V 内部任务，要求由 `runpod_prod_ltx_video_manual_NN` 接单、结果 MP4 写入 `user-data-prod` 且可下载；完成后目标 worker 保持 `disabled`。
- 生产真实创建、启用、删除或 canary 任务必须由用户明确确认。

## 9. R2 / RunPod 变量分层
| 变量族 | 语义 | cloud-test | cloud-prod |
| :--- | :--- | :--- | :--- |
| `MINIO_*` / `R2_*` | 用户数据桶，包含用户上传、生成结果、历史/Gallery 媒体 | `user-data-test`、`https://r2-test.aivison.it.com` | `user-data-prod`、`https://r2.aivison.it.com` |
| `RUNPOD_MODEL_BUCKET` | RunPod 模型缓存桶 | `allbot-model-cache` | `allbot-model-cache` |
| `RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO` / `RUNPOD_USE_TEMPLATE_IMAGE_TO_VIDEO` | split `image_to_video` 镜像与 template 开关 | `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` / `false` | 同 cloud-test；cloud-prod 渲染会拒绝旧 tag |
| `RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2` / `RUNPOD_USE_TEMPLATE_WAN22_VIDEO_V2` | split `wan22_video_v2` 镜像与 template 开关 | `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` / `false` | 同 cloud-test；cloud-prod 渲染会拒绝旧 tag |
| `RUNPOD_IMAGE_NAME_LTX_VIDEO` / `RUNPOD_USE_TEMPLATE_LTX_VIDEO` | `ltx_video` 高级图生视频镜像与 template 开关 | `ghcr.io/giraffu/allbot-comfy-runpod-ltx-video:<tag>` / `false` | 创建/render/canary 前必须显式配置正式 tag；不得使用 LAN registry |
| `RUNPOD_MODEL_PREFIX` / `RUNPOD_MODEL_MANIFEST_KEY` | 默认模型 manifest，主要给 `img2img_lora` | `img2img_lora/2026-06-10` | `img2img_lora/2026-06-10` |
| `RUNPOD_MODEL_PREFIX_IMAGE_TO_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_IMAGE_TO_VIDEO` | split `image_to_video` 模型 manifest | `image_to_video/2026-06-13-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_WAN22_VIDEO_V2` / `RUNPOD_MODEL_MANIFEST_KEY_WAN22_VIDEO_V2` | split `wan22_video_v2` 模型 manifest | `wan22_video_v2/2026-06-13-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_I2I_PRO` / `RUNPOD_MODEL_MANIFEST_KEY_I2I_PRO` | `i2i_pro` 三任务模型 manifest | `i2i_pro/2026-06-14-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_SCAIL2` / `RUNPOD_MODEL_MANIFEST_KEY_SCAIL2` | `scail2` 视频生视频模型 manifest | `scail2/2026-06-17-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_LTX_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_LTX_VIDEO` | `ltx_video` 高级图生视频模型 manifest | `ltx_video/2026-06-10/manifest.json` | 同 cloud-test manifest，manifest 内长期保留 10Eros v1.2 与旧 v1 主模型 |
| `RUNPOD_MODEL_PREFIX_WAN22_AIO_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_WAN22_AIO_VIDEO` | 兼容/回滚全集 manifest | `wan22_aio_video/2026-06-12-test/manifest.json` | 不作为正式主路径 |

RunPod secret reference 固定口径：

```dotenv
# cloud-test 用户数据桶与 Central token
AGENT_SECRET_TOKEN={{ RUNPOD_SECRET_allbot_cloud_test_agent_secret_token }}
MINIO_ACCESS_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_access_key }}
MINIO_SECRET_KEY={{ RUNPOD_SECRET_allbot_cloud_test_r2_secret_key }}

# cloud-prod 用户数据桶与 Central token
AGENT_SECRET_TOKEN={{ RUNPOD_SECRET_allbot_cloud_prod_agent_secret_token }}
MINIO_ACCESS_KEY={{ RUNPOD_SECRET_allbot_cloud_prod_r2_access_key }}
MINIO_SECRET_KEY={{ RUNPOD_SECRET_allbot_cloud_prod_r2_secret_key }}

# 模型缓存桶
RUNPOD_MODEL_ACCESS_KEY={{ RUNPOD_SECRET_allbot_model_cache_r2_access_key }}
RUNPOD_MODEL_SECRET_KEY={{ RUNPOD_SECRET_allbot_model_cache_r2_secret_key }}
```

`RUNPOD_API_KEY` 只用于 RunPod REST API。GitHub/GHCR token 只用于 Docker CLI login、GHCR push 或 package 管理。Cloudflare `cfat_...` API token 不用于 S3 客户端、RunPod Pod env 或模型同步，不应写入 `.env.cloud.*`、日志或知识库。

## 10. 镜像、模型与 workflow 口径
- `workers/comfy_agent/workflows` 是 workflow 运行时事实源；Central API 不维护 workflow 副本。
- Wan22 共享 RunPod 镜像构建入口仍在 `remote_workers/docker/runpod_profiles/wan22_aio_video/`，这是镜像目录名，不表示运行时继续使用 AIO profile。
- 当前 split video profile 复用 Wan22 GHCR image，但 profile-specific env、agent prefix、`SUPPORTED_TASK_TYPES`、runtime profile 和模型 manifest 必须分开渲染。`image_to_video` / `wan22_video_v2` 不再继承 legacy `RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO` 或 `RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO`；默认直接渲染带 RIFE 的 `imageName`，cloud-prod `prod-worker` 会拒绝旧 tag 或 template。
- Wan22 新镜像只 baked workflow 所需 custom nodes、`ffmpeg/ffprobe`、`rife49.pth` 后处理小权重、`runpod_bootstrap_from_git.sh` 和运行依赖；Wan22 high/low UNet、VAE、text encoder 与旧视频 LoRA 不 baked 进镜像，启动时从 `allbot-model-cache` 同步。`rife49.pth` 由 `FL_RIFE` 运行期读取，不属于可在线下载的普通缓存；RunPod bootstrap/entrypoint 会在启动 ComfyUI 前运行 `remote_workers/scripts/ensure_wan22_rife_cache.py`，缺失时 exit 75。
- `face_swap_v2.json` 使用 `i2i_pro` Flux2/edit 节点与模型替代旧图片换脸工作流，运行面 task type 仍是 `face_swap`。测试 worker1、正式 worker1 与 RunPod `i2i_pro` profile 都通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 将 `face_swap` 指向 v2；这属于 Worker workflow 配置替换，不代表新增业务 task type。
- `i2i_pro` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/i2i_pro/`，默认 base 为 `yanwk/comfyui-boot:cu128-slim`，与现有图生图和 Wan22 RunPod 镜像基线保持一致；ComfyUI pin 到 `16cd8d8a8f5f16ce7e5f929fdba9f783990254ea`。不得使用 `cu130` 基线，否则在当前 RunPod 4090 宿主机上可能因 PyTorch CUDA 版本高于宿主机驱动能力而失败；`20260614-i2ipro-6b167aa-cu128-min4` 已在 `NVIDIA GeForce RTX 4090` cloud-test Web canary 中完成模型同步、ComfyUI CUDA 初始化、worker heartbeat 和 `i2i_pro` 真实任务出图；当前 `.env.cloud.test` 候选镜像为 `20260614-i2ipro-b75c6a9-cu128-min5-ssh`，在 min4 的可用基线上补齐 `openssh` 与 direct TCP SSH smoke。当前 workflow 只要求 ComfyUI/core `nodes` 与 `comfy_extras` 中的 `UNETLoader`、`CLIPLoader`、`VAELoader`、`ReferenceLatent`、`EmptyFlux2LatentImage`、`Flux2Scheduler`、`SamplerCustomAdvanced`，不 baked 自定义节点或业务模型。GitHub Actions smoke 在 CPU runner 上用静态源码检查确认这些节点存在，避免导入 ComfyUI 时触发 CUDA 初始化；GPU import 与真实执行以 cloud-test canary 为准。镜像 smoke 还必须检查 `ffmpeg`、`curl`、`git`、`ssh-keygen` 与 `sshd`，确保 direct TCP SSH 诊断可用。
- RunPod `i2i_pro` 三任务能力依赖 `remote_workers/src/workflow_mapping_validation.py` 支持 `TASK_TYPE_WORKFLOW_OVERRIDES`，并且 `remote_workers/comfy_agent/workflows/` 内存在 `txt2img_from_i2i_pro.json` 与 `face_swap_v2.json`。`runpod_bootstrap_from_git.sh` 只在 `/workspace/allbot/repo/remote_workers` 不存在时 clone `deploy`，若旧 Pod 原地重启且已有旧 bundle，可能继续复用旧文件；新建/重建 Pod 会拉最新 `deploy`。若已运行的旧生产 Pod 因远端 bundle 缺 override 支持而读取旧默认 workflow，可先通过 Central agent control 将目标 worker 置为 `disabled`，再在 Pod 内覆盖默认 `face_swap.json` 与默认 Pornmaster workflow 为对应 v2/i2i_pro 派生模板；`WorkflowPatcher.load_workflow()` 每单重新读 JSON，文件级热修无需删除或重启 Pod，但长期修复仍必须进入 git 与新镜像/新 Pod。
- `scail2` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/scail2/`，GHCR ref 必须为 `ghcr.io/giraffu/allbot-comfy-runpod-scail2:<tag>`。镜像必须包含 ComfyUI SCAIL-2 core 节点、VideoHelperSuite、KJNodes、rgthree、Frame-Interpolation、Fill-Nodes、ffmpeg、bootstrap/sshd 诊断依赖和 `remote_workers/requirements.txt`，不得 baked 任何 `.safetensors` 模型权重。模型 manifest 固定为 `allbot-model-cache/scail2/2026-06-17-test/manifest.json`，LoRA 相对路径必须保持 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`。正式 RunPod `scail2` profile 只接 `scail2_action_transfer,scail2_video_replacement`，结果写 `user-data-prod`；cloud-test RunPod profile 结果写 `user-data-test`。
- `ltx_video` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/ltx_video/`，GHCR ref 必须为 `ghcr.io/giraffu/allbot-comfy-runpod-ltx-video:<tag>`，发布 workflow 为 `.github/workflows/runpod_ltx_video_profile_image.yml`。Dockerfile 默认从可公网拉取的 Wan22 GHCR 节点源复制所需 custom nodes，不依赖 LAN registry；镜像只 baked LTX custom nodes、shim、bootstrap 与运行依赖，不 baked `.safetensors`。模型 manifest 固定为 `allbot-model-cache/ltx_video/2026-06-10/manifest.json`，正式 RunPod profile 默认通过 `RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_LTX_VIDEO` 使用三份 10Eros v1.2 workflow，同时保留老 `LTX 2.3 *.json` 和 LAN AIO 默认行为。
- `i2i_pro_baseline` 模型包从 `gpu-226` / `192.168.1.226:8188` 同步到 R2 `allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json`，包含 6 个文件，总计 `38,769,838,190` bytes（约 `36.11 GiB`）。这 6 个文件同时覆盖 `i2i_pro.json`、`txt2img_from_i2i_pro.json` 与 `face_swap_v2.json`；本地主模型 registry 的 import spec 已按这两个 runtime overrides 生成 manifest，不再把 legacy Pornmaster/t2i 或旧 `face_swap.json` 专属模型纳入 `i2i_pro_baseline`。首次 cloud-test canary 使用 `RUNPOD_CONTAINER_DISK_GB=120`，GPU 只请求 `NVIDIA GeForce RTX 4090`，模型同步只写 ComfyUI `models/`，不得写 `input/output/temp/custom_nodes/workflows`。

`i2i_pro_baseline` 模型清单：

| Relative path | Size bytes |
| :--- | ---: |
| `text_encoders/qwen_3_8b_fp8mixed.safetensors` | `8,664,848,742` |
| `vae/flux2-vae.safetensors` | `336,213,556` |
| `unet/DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors` | `9,078,610,848` |
| `text_encoders/z_image/qwen_3_4b.safetensors` | `8,044,982,048` |
| `vae/z_image/ae.safetensors` | `335,304,388` |
| `unet/DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors` | `12,309,878,608` |

- `remote_workers/scripts/runpod_sync_models_from_r2.py` 支持 `.partial` 断点续传、有限重试和进度日志；已经创建的 Pod 不会热更新 `dockerStartCmd`，需删除重建。Dashboard/CLI 新增 RunPod 前可先用 `prod-worker render` 核对 `docker_start_cmd`，避免创建出 `dockerStartCmd=null` 的旧入口 Pod。
- 不要直接 `docker commit` 局域网成功的 ComfyUI 容器作为发布镜像；成功内容主要来自 volume/bind mount，commit 会漏 custom nodes/models/workflows，且可能混入运行残留。
- `img2img_lora` public GHCR 镜像已经通过真实任务 canary；新 profile 不能继承这个结论，必须单独准备模型 manifest、custom nodes、系统依赖和真实 Web canary。

## 11. Central / Worker 控制协议
新版 worker 在 `/api/agent/task/pop` 携带 `agent_id`。Central 通过 agent control 键控制单个 worker 是否接新单：
- `enabled`：可正常 pop。
- `draining`：不再 pop 新任务，等待当前任务自然结束。
- `disabled`：禁止接新任务。

接口：
- `POST /api/agent/task/control/{agent_id}`
- `GET /api/agent/task/control/{agent_id}`

这些接口使用现有 `AGENT_SECRET_TOKEN` 鉴权。旧 worker 不传 `agent_id` 时保留兼容逻辑。

切换任务能力、同步模型或做单点 canary 前，先把目标 worker 置为 `draining` 或 `disabled`；不要用强制重启代替 drain。

## 12. 运维红线
- Controller v1 不默认重启 worker、ComfyUI 或 GPU 节点。
- RunPod provider 不得触发本地 GPU SSH/Docker 操作。
- RunPod SSH 只用于云测试/失败现场短时诊断，需人工从 RunPod UI 提供当次 proxy SSH 信息；生产路径不依赖 SSH，也不得要求生产 Pod 暴露永久 SSH。
- 对 `host_service` runtime 只能生成观测或人工操作建议，不生成 Docker 操作。
- 模型同步只允许写目标共享 `models` 目录，不碰 `input/output/temp/custom_nodes/workflows`。
- 双卡节点只操作目标实例；不要整机 reboot、无 service 名 `docker compose down/up` 或批量删除容器。
- GPU 节点模型下载、Docker pull/build 或大视频输出前必须重新检查磁盘。
- RunPod model-transfer Pod 默认只允许 1 个；只有用户明确要求并发转存不同批次大对象时，才可在 cloud-test 临时提高到 2，完成后必须删除 Pod 并核验无 orphan、R2 active multipart 为 0。
