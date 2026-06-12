# RunPod 视频 Worker 云测试落地方案

生成时间：2026-06-12

当前口径：先不接正式环境，完整跑通云测试 `cloud-test`。本文件保留原文件名，但本轮目标不是生产发布。

## 1. 结论与修正

根据现有代码和你的四点要求，原“正式图生视频 worker”方案需要调整：

- 视频类 RunPod 首轮指定 `NVIDIA GeForce RTX 5090`，不沿用图生图的 4090-only 口径。
- 默认只走云测试：Central 用 `https://worker-central-test.aivison.it.com`，结果桶用 `user-data-test`，测试通过前不创建/启用正式 Pod。
- 重点前置为两件事：模型进入 `allbot-model-cache`，镜像变成可匿名拉取的最小 baked profile image。
- 参考已跑通的图生图链路，但不能直接套命令：当前 `RunPodProvider v0` 和 `runpod prod-worker` 都硬编码 `img2img_lora/img2img`，需要先做 profile 化改造。

## 2. 当前代码事实

- `image_to_video` 与 `wan22_video_v2` 都使用 `workers/comfy_agent/workflows/Wan22AioV82.json`。
- `image_to_video` 底层使用 `legacy_image_to_video` 模型 profile，允许旧视频 LoRA。
- `wan22_video_v2` 使用 `wan22_video_v2` 模型 profile，默认清空旧 LoRA 槽。
- 关键节点已被 patcher 硬编码依赖：主模型 `2616/2617`，LoRA `26/18`，起始/终止帧 `23/24`，prompt `2368/2371`，分辨率 `2612`，时长 `2578`，RIFE `265`，尾帧 `2607`。
- `task_profiles.yml` 里 `wan22_video_v2` 仍标 `min_vram_gb=48`；RunPod 视频测试 profile 先按用户要求指定 5090，并用真实 preview/5s canary 判断是否 OOM。
- 已跑通的图生图 RunPod 链路包括：public GHCR baked image、R2 manifest 模型同步、RunPod secret reference、云测试 worker 临时禁用、三任务 canary、完成后删除 Pod 和 orphan 核验。

## 3. 目标 Profile

首轮只做一个测试视频 profile：

| 项目 | 值 |
| --- | --- |
| profile | `wan22_aio_video` |
| 环境 | `cloud-test` |
| agent id prefix | `runpod_test_wan22_aio_video` |
| pod name | `allbot-runpod-test-wan22-aio-video` |
| GPU | `NVIDIA GeForce RTX 5090` |
| supported task types | `image_to_video,wan22_video_v2` |
| workflow | `Wan22AioV82.json` |
| runtime profile | `wan22_aio_video` |
| result bucket | `user-data-test` |
| model bucket | `allbot-model-cache` |
| model prefix | `wan22_aio_video/2026-06-12-test` |
| pipeline | `PIPELINE_MAX_RUNNING_TASKS=1` |
| prefetch | `false` |

后续只有在单 Pod union manifest 过大、模型切换成本太高，或两类任务需要单独启停时，再拆成：

- `wan22_image_to_video`
- `wan22_video_v2`

## 4. 模型准备

目标是生成最小 manifest，不搬整包目录。

先由代码列出实际需要的模型：

```bash
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan --bundle video_basic_baseline
python scripts/gpu_pool_controller.py model-import-plan --bundle wan22_video_v2_baseline
```

首轮 manifest 至少覆盖：

- `legacy_image_to_video` high/low UNet：
  - `wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors`
  - `wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors`
- `wan22_video_v2` high/low UNet：
  - `DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors`
  - `DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors`
- workflow 实际引用的 VAE、text encoder、RIFE/插帧模型和辅助模型。
- 旧 `VIDEO_LORA_MODELS` 当前线上可选 LoRA 的 high/low 文件对。

十几 GB、几十 GB 的大模型不要从本地上传。流程改为：

1. 根据 manifest 缺口整理清单：`relative_path`、目标 R2 key、大小、sha256、来源说明。
2. 把缺失的大模型下载链接发给你确认或由你提供。
3. 创建低成本临时 RunPod transfer Pod，从外部 URL 直接 multipart 上传到 `allbot-model-cache`。
4. 上传后 `HEAD` 校验 size/sha256 metadata，再写入 manifest。
5. transfer Pod 完成后立即删除，并跑 `list-pods` / `reconcile-managed-pods`。

可复用现有入口，但需要支持批量清单：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
python scripts/create_runpod_model_transfer_pod.py \
  --env-file .env.cloud.test \
  --bucket allbot-model-cache \
  --key wan22_aio_video/2026-06-12-test/models/<relative_path> \
  --relative-path <relative_path> \
  --sha256 <sha256> \
  --size-bytes <bytes> \
  --source-url '<download-url>' \
  --execute
```

计划问题核对：`scripts/transfer_url_to_r2.py` 在本地执行时会占本地带宽；本轮大模型优先用 `create_runpod_model_transfer_pod.py` 这种“Pod 内下载再传 R2”的方式。

## 5. 镜像准备

目标镜像：

```text
ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:<date>-wan22aio-test
```

镜像内 baked：

- ComfyUI 基础运行时。
- AllBot `remote_workers/` bundle。
- `Wan22AioV82.json`、`mappings.json`、worker patcher 代码。
- `ffmpeg/ffprobe`。
- Wan22 workflow 必需 custom nodes：至少覆盖 `FL_RIFE`、`VHS_VideoCombine`、`UNETLoader`、`Power Lora Loader (rgthree)`，并以 `/object_info` 实测为准补齐。

镜像内禁止 baked：

- Wan22 high/low UNet。
- VAE、text encoder、LoRA 等业务大模型。
- `.env.cloud.*`、R2 key、RunPod key、agent token。

镜像制备顺序：

1. 在 RunPod 5090 测试 Pod 中拉取纯净基础镜像，例如当前图生图已验证的 `yanwk/comfyui-boot:cu128-slim`。
2. 在 Pod 内安装 Wan22 所需 custom nodes 和系统依赖，先用测试 manifest 同步模型。
3. 跑 `image_to_video preview/5s` 和 `wan22_video_v2 preview/5s`，确认能真实生成 MP4 和 `last_frame`。
4. 把安装动作固化为 `remote_workers/docker/runpod_profiles/wan22_aio_video/Dockerfile`，不要把临时手工容器直接当最终镜像来源。
5. 使用 RunPod build Pod 或具备 Docker/BuildKit 的临时 Pod 构建并 push 到 GHCR。
6. push 后用空 `DOCKER_CONFIG` 匿名 inspect，确认 GHCR package public。

需要改造：

- `scripts/build_runpod_profile_image.sh` 支持 `--profile wan22_aio_video`。
- 新增 `remote_workers/docker/runpod_profiles/wan22_aio_video/Dockerfile`。
- smoke test 检查 ComfyUI、Wan22 workflow、custom nodes、ffmpeg 存在。
- smoke test 检查镜像内没有业务大模型。

计划问题核对：不建议把“docker commit 手工 Pod”作为长期镜像；可用于现场取证，但最终镜像必须由 Dockerfile/profile 可重复构建。

## 6. RunPod Provider 改造

当前 provider 只支持图生图。先补 cloud-test 视频 profile，不碰正式 `prod-worker`。

需要新增配置：

```env
RUNPOD_GPU_TYPE_IDS_WAN22_AIO_VIDEO=NVIDIA GeForce RTX 5090
RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:<tag>
RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO=false
RUNPOD_MODEL_BUCKET=allbot-model-cache
RUNPOD_MODEL_PREFIX=wan22_aio_video/2026-06-12-test
RUNPOD_MODEL_MANIFEST_KEY=wan22_aio_video/2026-06-12-test/manifest.json
RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false
RUNPOD_COMFY_KJNODES_ENABLED=false
```

代码改造点：

- `ops/gpu_pool_controller/providers/runpod.py`
  - `RUNPOD_TASK_PROFILES` 增加 `wan22_aio_video`。
  - `RunPodSettings` 增加 5090 GPU type、image、template、成本估算字段。
  - `_gpu_type_ids_for`、`_template_id_for`、`_image_name_for` 支持新 profile。
  - `_pod_name` 输出 `allbot-runpod-test-wan22-aio-video`。
  - cloud-test env 输出 `SUPPORTED_TASK_TYPES=image_to_video,wan22_video_v2`、`POOL_RUNTIME_PROFILE=wan22_aio_video`。
- `ops/gpu_pool_controller/runpod_canary.py`
  - canary payload 增加 `image_to_video` 与 `wan22_video_v2` 两条视频任务。
  - 支持只临时禁用同任务类型测试 worker。
- `ops/gpu_pool_controller/cli.py`
  - 可继续复用 `runpod render-create/create-pod/canary --task-type wan22_aio_video --env cloud-test`。

测试要补：

- provider render 输出 5090、测试 Central、`user-data-test`、测试 secret refs、model manifest。
- mutation guard 仍保持 dry-run 默认。
- render redaction 不输出 key/token/完整 URL query。
- canary 能识别 RunPod agent pop，任务被本地 worker 接走不算通过。

## 7. 云测试 Canary

启动前检查：

```bash
python scripts/gpu_pool_controller.py runpod validate-key
python scripts/gpu_pool_controller.py runpod list-pods
python scripts/gpu_pool_controller.py runpod reconcile-managed-pods
python scripts/gpu_pool_controller.py runpod render-create \
  --task-type wan22_aio_video \
  --env cloud-test
```

真实执行仍需四重门禁：

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod canary \
  --task-type wan22_aio_video \
  --env-file .env.cloud.test \
  --execute
```

为确保任务由 RunPod 接走，canary 期间只在云测试临时禁用同类 worker：

- `image_to_video`：按 `/system/workers` 实际能力临时禁用 `cloud_worker_test_01`、`cloud_worker_test_07` 等支持者。
- `wan22_video_v2`：临时禁用 `cloud_worker_test_05`。
- canary 结束必须恢复原 control 状态。

测试任务：

| 任务 | 参数 |
| --- | --- |
| `image_to_video` | 单起始帧、`preview`、`5s`、先无 LoRA |
| `wan22_video_v2` | 单起始帧、`preview`、`5s` |
| 第二阶段 | `wan22_video_v2` 首尾帧、扩展生成、`image_to_video` 带旧视频 LoRA |

验收标准：

- RunPod Pod infrastructure ready。
- 模型同步日志显示 manifest、进度和 `.partial` 断点续传能力。
- ComfyUI `/system_stats`、`/queue`、`/object_info` 可用。
- relay `/health` ready。
- Central `/system/workers` 出现 `runpod_test_wan22_aio_video_*` heartbeat，状态 healthy。
- 两条视频任务都由 RunPod agent pop。
- Central 终态 `done`。
- Web result `success`。
- MP4 可读，`extra_outputs.last_frame` 存在且可读。
- 结果落 `user-data-test`，下载到 `runpod_canary_results/test/video/<YYYYMMDD>/`。
- canary 后删除 Pod，`list-pods` 和 `reconcile-managed-pods` 无 orphan。

## 8. 阶段拆分

1. 补 `wan22_aio_video` RunPod profile 配置和 provider render。
2. 整理模型最小清单，缺失大模型链接向你确认。
3. 用临时 RunPod transfer Pod 把大模型转入 `allbot-model-cache`。
4. 生成并上传 `wan22_aio_video/2026-06-12-test/manifest.json`。
5. 在 RunPod 5090 测试 Pod 内验证 custom nodes + 模型 + 两条 preview/5s 任务。
6. 固化 `wan22_aio_video` Dockerfile，构建最小 public GHCR 镜像。
7. 跑 provider dry-run 与单元测试。
8. 跑云测试真实 canary。
9. 清理 Pod 和临时资源，沉淀测试结果。
10. 只有云测试彻底通过并经你确认后，另开正式环境方案。

## 9. 当前风险

- 5090 是否足够跑 Wan22 AIO 以真实 canary 为准；若 preview/5s OOM，先优化模型/依赖/精度或拆 profile，不切正式。
- 视频模型和 custom nodes 比图生图复杂，不能只靠 `/system_stats` 判断 ready，必须跑真实 MP4 任务。
- R2 manifest 只同步模型，不同步 custom nodes；custom nodes 必须 baked 入镜像或由 bootstrap 安装，本轮目标是 baked。
- GHCR package 必须 public；private package 会导致付费 Pod 启动后卡住。
- RunPod transfer Pod 和 build Pod 都要设置成本和数量门禁，完成即删。
- 不要把测试桶/测试 Central 与正式 secret 混用；本轮不读取 `.env.cloud.prod`。
