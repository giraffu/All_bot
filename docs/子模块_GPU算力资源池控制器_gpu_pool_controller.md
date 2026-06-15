# 子模块: GPU 算力资源池控制器 (GPU Pool Controller)

## 1. 目标与范围
本模块记录 AllBot 第一阶段 GPU 算力资源池方案。当前不是 K8s/K3s，也不是自动生产弹性伸缩系统；它是一个以声明式配置、dry-run 计划、canary 和受控 RunPod provider 为主的运维控制器。

当前实现入口：
- 控制器包：`ops/gpu_pool_controller/`
- CLI：`scripts/gpu_pool_controller.py`
- 默认配置：`ops/gpu_pool_controller/config/`
- 本地镜像仓库：`deploy/docker-compose-local-registry.yml`、`scripts/manage_local_registry.sh`
- LAN 模型缓存：`deploy/docker-compose-model-cache-lan.yml`、`scripts/manage_lan_model_cache.sh`
- LAN RunPod 化一体容器 canary：`scripts/lan_runpod_aio_canary.sh`
- RunPod provider：`ops/gpu_pool_controller/providers/runpod.py`
- RunPod 云测试 canary：`ops/gpu_pool_controller/runpod_canary.py`、`ops/gpu_pool_controller/runpod_split_video_canary.py`
- RunPod 云测试 worker scale：`ops/gpu_pool_controller/runpod_workers.py`
- RunPod 手动正式备用 worker：`ops/gpu_pool_controller/runpod_prod_worker.py`
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
| `gpu-177` | `allbot-gpu-177` / `192.168.1.177` | 2 x RTX 5090 | Docker `comfy0/comfy1` -> `8188/8189` |
| `gpu-252` | `allbot-gpu-252` / `192.168.1.252` | 2 x RTX 4090 48G | Docker `comfy0/comfy1` -> `8188/8189` |
| `gpu-002` | `allbot-gpu-002` / `192.168.1.2` | 2 x RTX 4090 48G | Docker `comfy0/comfy1` -> `8188/8189` |

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
scripts/upload_img2img_lora_models_to_lan_cache.sh --dry-run
scripts/build_runpod_profile_image.sh \
  --profile img2img_lora \
  --image-ref 192.168.1.115:5000/allbot/comfy-runpod-img2img-lora:lan-canary \
  --push
```

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

密钥边界：
- 真实密钥只放在 ignored env 文件，例如 `.env.lan.model-cache` 和 `.env.lan-aio-test`。
- compose 模板只允许出现 `${LAN_AIO_*:?}` / `${LAN_MODEL_CACHE_*:?}` 占位符。
- 不要直接 `source .env.cloud.test`；RunPod dry-run 继续只使用 controller 的 `--env-file` loader。
- LAN 模型缓存 bucket 固定为 `allbot-model-cache`；截至 2026-06-15，`192.168.1.115:9010` 已缓存 `img2img_lora/2026-06-10/manifest.json` 与 `i2i_pro/2026-06-14-test/manifest.json`。
- 通用上传入口为 `scripts/upload_model_bundle_to_r2.py`，通过 `.env.lan.model-cache` 映射 `LAN_MODEL_CACHE_*` 到 `RUNPOD_MODEL_*` 后写入 LAN cache；脚本按对象 size 与 sha256 metadata 跳过已有对象，metadata key 需大小写不敏感处理以兼容 MinIO。

## 4. RunPod Provider v0
RunPod provider 当前覆盖四类路径：

| 路径 | 用途 | 当前状态 |
| :--- | :--- | :--- |
| 云测试图生图 canary | `img2img` / `img2img_lora` 真实 Web 闭环 | 已通过真实 canary；作为 RunPod 基础链路回归入口 |
| 云测试 split video canary | `image_to_video` 与 `wan22_video_v2` 分 profile 验证 | `wan22_video_v2` 已完成 Web 端真实闭环；后续以 `split-video-canary` 复验 |
| 云测试图生图 Pro canary | `i2i_pro` RunPod runtime profile，串行验证 `i2i_pro`、Web `txt2img`、`face_swap` | 已通过单任务 cloud-test Web canary；三任务 canary 由 `runpod canary --task-type i2i_pro` 承担 |
| 手动云正式备用 worker | `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro` | 代码已支持；默认创建后先 `disabled`，不开启生产自动扩容 |

RunPod 只读 / dry-run 命令：

```bash
python scripts/gpu_pool_controller.py runpod validate-key
python scripts/gpu_pool_controller.py runpod list-pods
python scripts/gpu_pool_controller.py runpod reconcile-managed-pods
python scripts/gpu_pool_controller.py runpod render-create --task-type img2img_lora --env cloud-test
python scripts/gpu_pool_controller.py runpod render-create --task-type i2i_pro --env cloud-test
python scripts/gpu_pool_controller.py runpod create-pod --task-type img2img_lora --env cloud-test
python scripts/gpu_pool_controller.py runpod canary --env-file .env.cloud.test --quiet
python scripts/gpu_pool_controller.py runpod canary --task-type i2i_pro --env-file .env.cloud.test --quiet
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
| `wan22_aio_video` | `image_to_video,wan22_video_v2` | `wan22_aio_video` | `runpod_test_wan22_aio_video` | `wan22_aio_video/2026-06-12-test/manifest.json` |

`wan22_aio_video` 只保留为兼容/回滚 profile；新测试、新扩容和正式接入都应优先使用 split profile。
`i2i_pro` 是现有 ComfyUI runtime profile，不新增业务 task type；其中 Web 文生图仍提交 `txt2img`，Central 执行面记录为 `t2i-pornmaster-turbo`，worker 通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 读取 `txt2img_from_i2i_pro.json`。图片换脸仍提交 `face_swap`，worker 通过 override 读取 `face_swap_v2.json`。
`wan22_video_v2` RunPod split profile 默认渲染 `COMFY_EXTRA_ARGS=--disable-dynamic-vram`，用于规避 cu128 ComfyUI 0.21.x 的 DynamicVRAM/comfy-aimdo 在 `WanTEModel` 动态加载阶段卡住；如需临时实验其它 Comfy 启动参数，可用 `RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS` 覆盖，并必须重新创建目标 Pod 才会生效。

手动正式 profile：

| `prod-worker --profile` | Agent id | `SUPPORTED_TASK_TYPES` | 模型 manifest | GPU |
| :--- | :--- | :--- | :--- | :--- |
| `img2img` | `runpod_prod_img2img_manual_NN` | `img2img,img2img_lora` | `img2img_lora/2026-06-10/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `image_to_video` | `runpod_prod_image_to_video_manual_NN` | `image_to_video` | `image_to_video/2026-06-13-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `wan22_video_v2` | `runpod_prod_wan22_video_v2_manual_NN` | `wan22_video_v2` | `wan22_video_v2/2026-06-13-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `i2i_pro` | `runpod_prod_i2i_pro_manual_NN` | `i2i_pro,t2i-pornmaster-turbo,face_swap` | `i2i_pro/2026-06-14-test/manifest.json` | `NVIDIA GeForce RTX 4090` |

正式 video profile 镜像必须以 `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:` 开头；`i2i_pro` 镜像必须以 `ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:` 开头；`img2img` 使用已验证 public GHCR 图生图镜像。

## 6. 真实执行门禁
任意真实 RunPod mutation 都必须显式满足：

```dotenv
RUNPOD_DRY_RUN=false
RUNPOD_AUTOSCALER_ENABLED=true
RUNPOD_MAX_PODS_TOTAL=<目标总数>
RUNPOD_MAX_PODS_PER_TYPE=<目标单类型数>
```

并带对应 CLI 的 `--execute`。

`RUNPOD_MAX_PODS_TOTAL` 是全 managed RunPod 池的显式总上限；`RUNPOD_MAX_PODS_PER_TYPE`
是当前 task/profile 的单类型上限，仍受 `RUNPOD_PROD_MAX_MANUAL_SLOTS` 约束。云正式多
profile 共存时，例如保留前四台并只补一台 `wan22_video_v2`，应使用
`RUNPOD_MAX_PODS_TOTAL=5`、`RUNPOD_MAX_PODS_PER_TYPE=1`，并把
`RUNPOD_MAX_HOURLY_COST_USD` 显式设置到能覆盖现有 Pod 加新 Pod 的成本；不要为了创建第五台
放宽单类型上限。

云测试 split video canary：
- 默认同时测 `image_to_video` 与 `wan22_video_v2`，要求 `RUNPOD_MAX_PODS_TOTAL=2`、`RUNPOD_MAX_PODS_PER_TYPE=1`。
- 传 `--profile image_to_video` 或 `--profile wan22_video_v2` 时只创建 1 个 Pod，门禁必须收窄为 `RUNPOD_MAX_PODS_TOTAL=1`。
- 若只允许 4090，可临时覆盖 `RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2='NVIDIA GeForce RTX 4090'`。
- 失败或中断后必须恢复 worker control、删除 Pod，并用 `list-pods` / `reconcile-managed-pods` 确认 managed count 为 0。

## 7. 云测试 canary
图生图默认 canary：

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

常用命令：

```bash
python scripts/gpu_pool_controller.py runpod prod-worker render
python scripts/gpu_pool_controller.py runpod prod-worker status
python scripts/gpu_pool_controller.py runpod prod-worker up --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker enable --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker disable --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker down --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile img2img
python scripts/gpu_pool_controller.py runpod prod-worker scale --profile img2img --desired 1
python scripts/gpu_pool_controller.py runpod prod-worker render --profile i2i_pro --slot 01
python scripts/gpu_pool_controller.py runpod prod-worker canary --profile i2i_pro --slot 01
```

`prod-worker` 默认先加载 `.env.cloud.test` 中的 RunPod API/profile 默认值，再加载 `.env.cloud.prod` 覆盖正式 Central/Web/R2/JWT 变量；已在 shell 显式设置的 `RUNPOD_*` 门禁不会被 prod env 文件覆盖。

操作语义速查：

| 命令 | 是否触碰 Pod 生命周期 | 是否放开接单 | 主要用途 |
| :--- | :--- | :--- | :--- |
| `render` / `status` | 否 | 否 | 渲染/观测，适合 AI 运维先读状态 |
| `up --execute` | 创建并启动目标 Pod | 否，默认写 `disabled` | 新增手动正式备用 worker，等待模型同步和 heartbeat |
| `enable --execute` | 否 | 是，仅改 Central control | 放开已有 Pod 接正式队列 |
| `disable --execute` | 否 | 否，仅改 Central control | 保留 Pod 现场、停止接新单，用于排障或维护 |
| `canary --execute` | 不创建已存在的 prod Pod | 临时 enable，结束恢复 `disabled` | 提交真实 Web 任务验证目标 worker |
| `down --execute` | 删除目标 prod Pod | 否 | 下线手动备用 Pod，必须确认无 `current_task_id` |
| `scale --desired N --execute` | 按 slot 创建/删除/enable/disable | 取决于计划 | 多手动 slot 运维，仍受总上限和单类型上限约束 |

判断“RunPod 已启动并可接单”不能只看 Pod `RUNNING`：还必须看到 Central worker heartbeat，
且 agent control 为 `enabled`。`up --execute` 后处于 ready 但 `disabled` 是预期行为；需要
`enable --execute` 才会接正式任务。

真实创建示例：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod prod-worker up \
  --profile wan22_video_v2 \
  --execute
```

正式流程红线：
- `up --execute` 固定为预检 -> 写目标 agent control `disabled` -> 创建 Pod -> 等 readiness -> 等 Central heartbeat；ready 后默认不抢正式订单。`prod-worker` 的 worker heartbeat 等待默认 `3600s`，用于覆盖 `i2i_pro` 首次同步约 36GiB 模型的启动窗口。
- `enable --execute` 才允许目标 worker 接单。
- `down --execute` 必须确认无 `current_task_id`，忙碌 worker 不提供隐式 force。
- `canary --execute` 不禁用现有正式 worker；完成后恢复目标 RunPod worker 为 `disabled`。
- `prod-worker canary --profile i2i_pro --execute` 会串行提交 `i2i_pro`、Web `txt2img`、`face_swap` 三单，要求三单均由 `runpod_prod_i2i_pro_manual_NN` 接单并产出可下载图片。
- 生产真实创建、启用、删除或 canary 任务必须由用户明确确认。

## 9. R2 / RunPod 变量分层
| 变量族 | 语义 | cloud-test | cloud-prod |
| :--- | :--- | :--- | :--- |
| `MINIO_*` / `R2_*` | 用户数据桶，包含用户上传、生成结果、历史/Gallery 媒体 | `user-data-test`、`https://r2-test.aivison.it.com` | `user-data-prod`、`https://r2.aivison.it.com` |
| `RUNPOD_MODEL_BUCKET` | RunPod 模型缓存桶 | `allbot-model-cache` | `allbot-model-cache` |
| `RUNPOD_MODEL_PREFIX` / `RUNPOD_MODEL_MANIFEST_KEY` | 默认模型 manifest，主要给 `img2img_lora` | `img2img_lora/2026-06-10` | `img2img_lora/2026-06-10` |
| `RUNPOD_MODEL_PREFIX_IMAGE_TO_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_IMAGE_TO_VIDEO` | split `image_to_video` 模型 manifest | `image_to_video/2026-06-13-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_WAN22_VIDEO_V2` / `RUNPOD_MODEL_MANIFEST_KEY_WAN22_VIDEO_V2` | split `wan22_video_v2` 模型 manifest | `wan22_video_v2/2026-06-13-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_I2I_PRO` / `RUNPOD_MODEL_MANIFEST_KEY_I2I_PRO` | `i2i_pro` 三任务模型 manifest | `i2i_pro/2026-06-14-test/manifest.json` | 同 cloud-test manifest |
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
- 当前 split video profile 复用 Wan22 GHCR image/template，但 profile-specific env、agent prefix、`SUPPORTED_TASK_TYPES`、runtime profile 和模型 manifest 必须分开渲染。
- Wan22 镜像只 baked workflow 所需 custom nodes、`ffmpeg/ffprobe` 和运行依赖；Wan22 high/low UNet、VAE、text encoder 与旧视频 LoRA 不 baked 进镜像，启动时从 `allbot-model-cache` 同步。
- `face_swap_v2.json` 使用 `i2i_pro` Flux2/edit 节点与模型替代旧图片换脸工作流，运行面 task type 仍是 `face_swap`。测试 worker1、正式 worker1 与 RunPod `i2i_pro` profile 都通过 `TASK_TYPE_WORKFLOW_OVERRIDES` 将 `face_swap` 指向 v2；这属于 Worker workflow 配置替换，不代表新增业务 task type。
- `i2i_pro` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/i2i_pro/`，默认 base 为 `yanwk/comfyui-boot:cu128-slim`，与现有图生图和 Wan22 RunPod 镜像基线保持一致；ComfyUI pin 到 `16cd8d8a8f5f16ce7e5f929fdba9f783990254ea`。不得使用 `cu130` 基线，否则在当前 RunPod 4090 宿主机上可能因 PyTorch CUDA 版本高于宿主机驱动能力而失败；`20260614-i2ipro-6b167aa-cu128-min4` 已在 `NVIDIA GeForce RTX 4090` cloud-test Web canary 中完成模型同步、ComfyUI CUDA 初始化、worker heartbeat 和 `i2i_pro` 真实任务出图；当前 `.env.cloud.test` 候选镜像为 `20260614-i2ipro-b75c6a9-cu128-min5-ssh`，在 min4 的可用基线上补齐 `openssh` 与 direct TCP SSH smoke。当前 workflow 只要求 ComfyUI/core `nodes` 与 `comfy_extras` 中的 `UNETLoader`、`CLIPLoader`、`VAELoader`、`ReferenceLatent`、`EmptyFlux2LatentImage`、`Flux2Scheduler`、`SamplerCustomAdvanced`，不 baked 自定义节点或业务模型。GitHub Actions smoke 在 CPU runner 上用静态源码检查确认这些节点存在，避免导入 ComfyUI 时触发 CUDA 初始化；GPU import 与真实执行以 cloud-test canary 为准。镜像 smoke 还必须检查 `ffmpeg`、`curl`、`git`、`ssh-keygen` 与 `sshd`，确保 direct TCP SSH 诊断可用。
- RunPod `i2i_pro` 三任务能力依赖 `remote_workers/src/workflow_mapping_validation.py` 支持 `TASK_TYPE_WORKFLOW_OVERRIDES`，并且 `remote_workers/comfy_agent/workflows/` 内存在 `txt2img_from_i2i_pro.json` 与 `face_swap_v2.json`。`runpod_bootstrap_from_git.sh` 只在 `/workspace/allbot/repo/remote_workers` 不存在时 clone `deploy`，若旧 Pod 原地重启且已有旧 bundle，可能继续复用旧文件；新建/重建 Pod 会拉最新 `deploy`。若已运行的旧生产 Pod 因远端 bundle 缺 override 支持而读取旧默认 workflow，可先通过 Central agent control 将目标 worker 置为 `disabled`，再在 Pod 内覆盖默认 `face_swap.json` 与默认 Pornmaster workflow 为对应 v2/i2i_pro 派生模板；`WorkflowPatcher.load_workflow()` 每单重新读 JSON，文件级热修无需删除或重启 Pod，但长期修复仍必须进入 git 与新镜像/新 Pod。
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

- `remote_workers/scripts/runpod_sync_models_from_r2.py` 支持 `.partial` 断点续传、有限重试和进度日志；已经创建的 Pod 不会热更新 `dockerStartCmd`，需删除重建。
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
