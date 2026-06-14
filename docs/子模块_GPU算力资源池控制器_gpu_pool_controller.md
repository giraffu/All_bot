# 子模块: GPU 算力资源池控制器 (GPU Pool Controller)

## 1. 目标与范围
本模块记录 AllBot 第一阶段 GPU 算力资源池方案。当前不是 K8s/K3s，也不是自动生产弹性伸缩系统；它是一个以声明式配置、dry-run 计划、canary 和受控 RunPod provider 为主的运维控制器。

当前实现入口：
- 控制器包：`ops/gpu_pool_controller/`
- CLI：`scripts/gpu_pool_controller.py`
- 默认配置：`ops/gpu_pool_controller/config/`
- 本地镜像仓库：`deploy/docker-compose-local-registry.yml`、`scripts/manage_local_registry.sh`
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

Runtime dry-run 说明：
- `runtime-plan` 输出 runtime/image/model/worker-env diff，不连接远端、不修改 worker。
- `runtime-render` 渲染标准 ComfyUI runtime compose；只适用于 `docker_container`。
- `runtime-plan` / `runtime-render` 支持 `--host-port`、`--container-name`、`--api-url`、`--ws-url` 做备用端口 canary 覆盖。
- `runtime-apply`、`switch-profile`、`rollback-profile --execute` 当前会明确拒绝真实执行。
- `gpu-226` 是 `host_service`，不得生成 Docker pull/up/restart 操作。

## 4. RunPod Provider v0
RunPod provider 当前覆盖四类路径：

| 路径 | 用途 | 当前状态 |
| :--- | :--- | :--- |
| 云测试图生图 canary | `img2img` / `img2img_lora` 真实 Web 闭环 | 已通过真实 canary；作为 RunPod 基础链路回归入口 |
| 云测试 split video canary | `image_to_video` 与 `wan22_video_v2` 分 profile 验证 | `wan22_video_v2` 已完成 Web 端真实闭环；后续以 `split-video-canary` 复验 |
| 云测试图生图 Pro canary | 现有业务类型 `i2i_pro` 的专用 RunPod runtime profile | 已有 render/create/workers/canary 入口；仅 cloud-test，等待真实 Web canary |
| 手动云正式备用 worker | `img2img`、`image_to_video`、`wan22_video_v2` | 代码已支持；默认创建后先 `disabled`，不开启生产自动扩容 |

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
| `i2i_pro` | `i2i_pro` | `i2i_pro` | `runpod_test_i2i_pro` | `i2i_pro/2026-06-14-test/manifest.json` |
| `wan22_aio_video` | `image_to_video,wan22_video_v2` | `wan22_aio_video` | `runpod_test_wan22_aio_video` | `wan22_aio_video/2026-06-12-test/manifest.json` |

`wan22_aio_video` 只保留为兼容/回滚 profile；新测试、新扩容和正式接入都应优先使用 split profile。
`i2i_pro` 是现有业务任务类型的 cloud-test RunPod profile，不新增业务 task type；正式 `prod-worker --profile i2i_pro` 仍未开放。

手动正式 profile：

| `prod-worker --profile` | Agent id | `SUPPORTED_TASK_TYPES` | 模型 manifest | GPU |
| :--- | :--- | :--- | :--- | :--- |
| `img2img` | `runpod_prod_img2img_manual_NN` | `img2img,img2img_lora` | `img2img_lora/2026-06-10/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `image_to_video` | `runpod_prod_image_to_video_manual_NN` | `image_to_video` | `image_to_video/2026-06-13-test/manifest.json` | `NVIDIA GeForce RTX 4090` |
| `wan22_video_v2` | `runpod_prod_wan22_video_v2_manual_NN` | `wan22_video_v2` | `wan22_video_v2/2026-06-13-test/manifest.json` | `NVIDIA GeForce RTX 4090` |

正式 video profile 镜像必须以 `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:` 开头；`img2img` 使用已验证 public GHCR 图生图镜像。

## 6. 真实执行门禁
任意真实 RunPod mutation 都必须显式满足：

```dotenv
RUNPOD_DRY_RUN=false
RUNPOD_AUTOSCALER_ENABLED=true
RUNPOD_MAX_PODS_TOTAL=<目标总数>
RUNPOD_MAX_PODS_PER_TYPE=<目标单类型数>
```

并带对应 CLI 的 `--execute`。

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

`i2i_pro` cloud-test canary 必须通过 Web API 创建真实任务，而不是只做 worker 直测。验收口径：
- RunPod worker heartbeat 出现为 `runpod_test_i2i_pro_*`。
- Central 任务类型保持 `i2i_pro`，`pop_evidence.agent_id` 匹配该 RunPod worker。
- Web result 为 `success`，最终状态为 `done`，图片结果可下载。
- 验收结束后恢复临时禁用的非 RunPod cloud-test `i2i_pro` worker，删除 Pod，并确认 managed RunPod count 回到 0。

当测试服 canary 需要与现有云正式手动备用 Pod 共存时，必须显式传
`--allow-existing-prod-managed-pods` 或设置
`RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS=true`。该开关只忽略名称前缀为
`allbot-runpod-prod-img2img-manual-`、`allbot-runpod-prod-image-to-video-manual-`、
`allbot-runpod-prod-wan22-video-v2-manual-` 的既有 managed Pod；任何 cloud-test
残留 Pod 仍会阻止 `canary --execute`。开启后 `RUNPOD_MAX_PODS_TOTAL=1`
表示“本次 cloud-test canary 只允许创建 1 个非忽略 Pod”，cleanup 验收也按
非忽略 managed Pod 数量回到 0 计算。失败现场用 `--no-cleanup` 保留的新
`i2i_pro` Pod 可通过 `--reuse-pod-id i2i_pro=<pod_id>` 复跑 Web 任务，避免重复创建 Pod。

cloud-test 诊断 Pod 如需 SSH，`.env.cloud.test` 可设置
`RUNPOD_PUBLIC_KEY_FILE=~/.ssh/allbot_runpod_debug_20260613_ed25519.pub` 或
`RUNPOD_PUBLIC_KEY=<ssh public key>`。provider 会把它渲染为 Pod env `PUBLIC_KEY`，
bootstrap 启动 sshd 时写入 `/root/.ssh/authorized_keys`；不要写入私钥，也不要把该
能力扩展为生产 Pod 的长期 SSH 入口。

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
```

`prod-worker` 默认先加载 `.env.cloud.test` 中的 RunPod API/profile 默认值，再加载 `.env.cloud.prod` 覆盖正式 Central/Web/R2/JWT 变量；已在 shell 显式设置的 `RUNPOD_*` 门禁不会被 prod env 文件覆盖。

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
- `up --execute` 固定为预检 -> 写目标 agent control `disabled` -> 创建 Pod -> 等 readiness -> 等 Central heartbeat；ready 后默认不抢正式订单。
- `enable --execute` 才允许目标 worker 接单。
- `down --execute` 必须确认无 `current_task_id`，忙碌 worker 不提供隐式 force。
- `canary --execute` 不禁用现有正式 worker；完成后恢复目标 RunPod worker 为 `disabled`。
- 生产真实创建、启用、删除或 canary 任务必须由用户明确确认。

## 9. R2 / RunPod 变量分层
| 变量族 | 语义 | cloud-test | cloud-prod |
| :--- | :--- | :--- | :--- |
| `MINIO_*` / `R2_*` | 用户数据桶，包含用户上传、生成结果、历史/Gallery 媒体 | `user-data-test`、`https://r2-test.aivison.it.com` | `user-data-prod`、`https://r2.aivison.it.com` |
| `RUNPOD_MODEL_BUCKET` | RunPod 模型缓存桶 | `allbot-model-cache` | `allbot-model-cache` |
| `RUNPOD_MODEL_PREFIX` / `RUNPOD_MODEL_MANIFEST_KEY` | 默认模型 manifest，主要给 `img2img_lora` | `img2img_lora/2026-06-10` | `img2img_lora/2026-06-10` |
| `RUNPOD_MODEL_PREFIX_IMAGE_TO_VIDEO` / `RUNPOD_MODEL_MANIFEST_KEY_IMAGE_TO_VIDEO` | split `image_to_video` 模型 manifest | `image_to_video/2026-06-13-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_WAN22_VIDEO_V2` / `RUNPOD_MODEL_MANIFEST_KEY_WAN22_VIDEO_V2` | split `wan22_video_v2` 模型 manifest | `wan22_video_v2/2026-06-13-test/manifest.json` | 同 cloud-test manifest |
| `RUNPOD_MODEL_PREFIX_I2I_PRO` / `RUNPOD_MODEL_MANIFEST_KEY_I2I_PRO` | `i2i_pro` cloud-test 专用模型 manifest | `i2i_pro/2026-06-14-test/manifest.json` | 未开放正式主路径 |
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
- `i2i_pro` RunPod 镜像构建入口是 `remote_workers/docker/runpod_profiles/i2i_pro/`，默认 base 为 `yanwk/comfyui-boot:cu124-slim`，ComfyUI pin 到 `16cd8d8a8f5f16ce7e5f929fdba9f783990254ea`。RunPod 4090 宿主机当前暴露 CUDA driver API `12040`，不得使用 `cu130` 基线，否则 ComfyUI 启动时会因 PyTorch CUDA 版本高于宿主机驱动能力而失败。当前 workflow 只要求 ComfyUI/core `nodes` 与 `comfy_extras` 中的 `UNETLoader`、`CLIPLoader`、`VAELoader`、`ReferenceLatent`、`EmptyFlux2LatentImage`、`Flux2Scheduler`、`SamplerCustomAdvanced`，不 baked 自定义节点或业务模型。GitHub Actions smoke 在 CPU runner 上用静态源码检查确认这些节点存在，避免导入 ComfyUI 时触发 CUDA 初始化；GPU import 与真实执行以 cloud-test canary 为准。
- `i2i_pro_baseline` 模型包从 `gpu-226` / `192.168.1.226:8188` 同步到 R2 `allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json`，包含 6 个文件，总计 `38,769,838,190` bytes（约 `36.11 GiB`）。首次 cloud-test canary 使用 `RUNPOD_CONTAINER_DISK_GB=120`，GPU 只请求 `NVIDIA GeForce RTX 4090`，模型同步只写 ComfyUI `models/`，不得写 `input/output/temp/custom_nodes/workflows`。

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
