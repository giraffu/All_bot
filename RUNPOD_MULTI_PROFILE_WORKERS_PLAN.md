# RunPod 多 Profile Worker 拆分与 N 副本调度计划

日期：2026-06-13

## Implementation Status

已落地代码前置：

- Web/Core 已允许字面量 `image_to_video` 进入视频任务集合；`StrategyFactory.get_strategy("image_to_video")` 走 Wan22 legacy image-to-video 策略，Web `/api/tasks/generate` 提交后 Central task type 不应再回退成 `img2img`。
- RunPod Provider 已新增 `image_to_video` 与 `wan22_video_v2` profile；两者 cloud-test 默认复用 template `77gi0wqo8x` 和 Wan22 GHCR image，但分别渲染独立 `SUPPORTED_TASK_TYPES`、`POOL_RUNTIME_PROFILE`、`AGENT_ID_PREFIX` 与模型 manifest。
- 已新增 `runpod workers render-scale|scale`、`runpod split-video-manifests` 与 `runpod split-video-canary`。
- 已新增 split manifest helper：从 `wan22_aio_video/2026-06-12-test/manifest.json` 生成 `image_to_video/2026-06-13-test/manifest.json` 与 `wan22_video_v2/2026-06-13-test/manifest.json`，复用原始 R2 `key`，上传前 HEAD 校验，不复制 safetensors 大对象。
- `.env.cloud.test` 已补齐 split profile 的非敏感默认值；真实 mutation 门禁仍保持默认 dry-run。

待执行真机阶段：

- 先执行 `runpod split-video-manifests --execute` 上传两个小 manifest。
- 临时设置 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`RUNPOD_MAX_PODS_TOTAL=2`、`RUNPOD_MAX_PODS_PER_TYPE=1`，执行 `runpod split-video-canary --execute`。
- canary 会同时启动 2 个视频 Pod，GPU 调度按 `RTX 5090` 优先、`RTX 4090` 回退，模拟 Web 用户提交 3 条任务，并把结果下载到 `runpod_video_test_results/`，结束后删除两个 Pod。

## Summary

结论：可以把现在的 `wan22_aio_video` 拆成两个独立的图生视频 RunPod 类。`image_to_video` 和 `wan22_video_v2` 可以继续使用同一个 Wan22 容器镜像/基础 template，但必须拆分运行时 profile、`SUPPORTED_TASK_TYPES`、agent 前缀、模型 manifest 和扩缩容 slot。

拆分后系统面向 RunPod 的 worker 类先固定为三类：

| RunPod profile | 接取任务类型 | 容器/模板 | 模型集合 |
| --- | --- | --- | --- |
| `img2img_lora` | `img2img,img2img_lora` | 现有图生图镜像/template | 图生图 baseline |
| `image_to_video` | `image_to_video` | Wan22 视频镜像/template | 旧图生视频/单图生成所需模型 |
| `wan22_video_v2` | `wan22_video_v2` | Wan22 视频镜像/template | Wan22 v2 所需模型 |

目标能力：

- 每类 RunPod 都可以按参数启动 N 个，例如 `image_to_video=1`、`wan22_video_v2=2`、`img2img_lora=3`。
- 多次执行扩缩容命令时，只调整目标 profile，不误删其它 profile 的 Pod。
- Central 仍按 worker heartbeat 里的 `SUPPORTED_TASK_TYPES` 分发任务；拆分后每类 worker 只暴露自己的任务类型。
- 云测试先落地，正式环境等 cloud-test canary 通过后另开确认，不读取或修改 `.env.cloud.prod`。

## 当前事实

- `img2img_lora` 是已验证过的 RunPod 成功路径，支持 `img2img,img2img_lora`。
- `wan22_aio_video` 目前是临时 AIO profile，支持 `image_to_video,wan22_video_v2`，cloud-test template id 为 `77gi0wqo8x`。
- 使用 template 后，Wan22 Pod 已能越过容器冷拉并进入模型同步；模型同步和 worker heartbeat 路径可用。
- 最近一次真实 canary 的主要阻塞不在 RunPod 容器，而是 cloud-test Web/Core 到 Central 的派发链路：`image_to_video` 任务进入 Central 后被记录/执行成了 `img2img`，导致输出 PNG 且没有 `extra_outputs.last_frame`。
- 因此拆分 profile 前，必须把 `image_to_video` 的任务类型派发 bug 修掉并纳入回归测试。

## 设计原则

1. **同镜像，不同运行类**
   `image_to_video` 和 `wan22_video_v2` 共用同一个 GHCR 镜像和同一套 ComfyUI custom nodes；差异由 env、manifest 和 worker 支持任务类型决定。

2. **同 template 可用，推荐分 template**
   cloud-test 可以暂时让两个视频 profile 复用 `77gi0wqo8x`，通过 create pod env override 区分任务类型与模型 manifest。长期推荐在 RunPod UI 中建两个 template：
   - `allbot-image-to-video-cloud-test`
   - `allbot-wan22-video-v2-cloud-test`

   这样 UI 侧环境变量、排障日志和手工重建路径更直观。

3. **模型从业务 profile 拆分**
   不再让 `wan22_aio_video` 同步两个视频任务的全集模型。每个 profile 只同步自己需要的模型集合，减少启动耗时、网络流量和磁盘占用。

4. **扩缩容必须 profile-aware**
   `scale image_to_video --desired 2` 只能影响 `image_to_video` Pod；不能清理 `img2img_lora` 或 `wan22_video_v2` Pod。

5. **默认 dry-run**
   所有 RunPod mutation 继续默认 dry-run。真实创建/删除仍必须显式设置：
   - `RUNPOD_DRY_RUN=false`
   - `RUNPOD_AUTOSCALER_ENABLED=true`
   - 对应 Pod 数上限
   - CLI `--execute`

## Profile 配置目标

新增或调整 `ops/gpu_pool_controller/config/task_profiles.yml`：

```yaml
profiles:
  img2img_lora:
    runtime_profile: img2img_lora
    task_types:
      - img2img
      - img2img_lora
    model_bundles:
      - img2img_lora_baseline

  image_to_video:
    runtime_profile: image_to_video
    task_types:
      - image_to_video
    model_bundles:
      - image_to_video_baseline
    workflow: workers/comfy_agent/workflows/Wan22AioV82.json
    min_vram_gb: 48

  wan22_video_v2:
    runtime_profile: wan22_video_v2
    task_types:
      - wan22_video_v2
    model_bundles:
      - wan22_video_v2_baseline
    workflow: workers/comfy_agent/workflows/Wan22AioV82.json
    min_vram_gb: 48
```

`wan22_aio_video` 暂时保留为兼容/回滚 profile，但新能力以 `image_to_video` 和 `wan22_video_v2` 为主；拆分 canary 全部通过后再标记废弃。

## 模型 Manifest 拆分

建议拆成两个视频 manifest：

```text
allbot-model-cache/image_to_video/2026-06-13-test/manifest.json
allbot-model-cache/wan22_video_v2/2026-06-13-test/manifest.json
```

`image_to_video` manifest：

- 旧图生视频入口所需 high/low 模型。
- 单起始帧和首尾帧生成所需模型。
- `Wan22AioV82.json` 运行所需 VAE、text encoder、RIFE/video helper 相关模型。
- 只包含 `image_to_video` 路径实际会加载的 LoRA/UNet。

`wan22_video_v2` manifest：

- Wan22 v2 Dasiwa high/low 模型。
- v2 所需 VAE、text encoder、RIFE/video helper 相关模型。
- 不包含旧 `image_to_video` 专属 LoRA，除非 workflow 或 patcher 明确会加载。

共享模型处理策略：

- R2 `allbot-model-cache` 继续作为源头事实。
- 第一阶段允许两个 manifest 各自引用所需对象，先保证可用和清晰。
- 后续再增强 manifest 格式，支持 `relative_path` 与 `object_key` 解耦，让两个 profile 复用同一个 R2 大对象，避免重复存储。
- 如果启用 RunPod Network Volume，优先按 data center 预热共享模型目录，启动时只同步缺失文件。

## 新增环境变量约定

保留现有 `RUNPOD_*_WAN22_AIO_VIDEO` 作为兼容变量，新拆分 profile 增加：

```bash
# image_to_video
RUNPOD_GPU_TYPE_IDS_IMAGE_TO_VIDEO=NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090
RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:<tag>
RUNPOD_USE_TEMPLATE_IMAGE_TO_VIDEO=true
RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO=<template_id>
RUNPOD_MODEL_PREFIX_IMAGE_TO_VIDEO=image_to_video/2026-06-13-test
RUNPOD_MODEL_MANIFEST_KEY_IMAGE_TO_VIDEO=image_to_video/2026-06-13-test/manifest.json
RUNPOD_PROJECTED_COST_PER_HR_IMAGE_TO_VIDEO=<cost>
RUNPOD_MAX_PODS_IMAGE_TO_VIDEO=<n>

# wan22_video_v2
RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2=NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090
RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2=ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:<tag>
RUNPOD_USE_TEMPLATE_WAN22_VIDEO_V2=true
RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2=<template_id>
RUNPOD_MODEL_PREFIX_WAN22_VIDEO_V2=wan22_video_v2/2026-06-13-test
RUNPOD_MODEL_MANIFEST_KEY_WAN22_VIDEO_V2=wan22_video_v2/2026-06-13-test/manifest.json
RUNPOD_PROJECTED_COST_PER_HR_WAN22_VIDEO_V2=<cost>
RUNPOD_MAX_PODS_WAN22_VIDEO_V2=<n>
```

可选 Network Volume 变量：

```bash
RUNPOD_NETWORK_VOLUME_ID_IMAGE_TO_VIDEO=<volume_id>
RUNPOD_ALLOWED_DATACENTERS_IMAGE_TO_VIDEO=EUR-NO-1
RUNPOD_VOLUME_MOUNT_PATH_IMAGE_TO_VIDEO=/workspace

RUNPOD_NETWORK_VOLUME_ID_WAN22_VIDEO_V2=<volume_id>
RUNPOD_ALLOWED_DATACENTERS_WAN22_VIDEO_V2=EUR-NO-1
RUNPOD_VOLUME_MOUNT_PATH_WAN22_VIDEO_V2=/workspace
```

## 扩缩容 CLI 目标

新增一个通用 worker/profile 命令组，替代只面向正式图生图 slot 的特殊入口：

```bash
# 渲染将要创建/删除哪些 Pod，不真实执行
python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile image_to_video \
  --desired 2 \
  --env cloud-test

# 真实扩到 2 个 image_to_video worker
python scripts/gpu_pool_controller.py runpod workers scale \
  --profile image_to_video \
  --desired 2 \
  --env-file .env.cloud.test \
  --execute

# 另一次调用只调整 wan22_video_v2，不影响 image_to_video
python scripts/gpu_pool_controller.py runpod workers scale \
  --profile wan22_video_v2 \
  --desired 1 \
  --env-file .env.cloud.test \
  --execute

# 缩到 0，按 drain -> delete 清理
python scripts/gpu_pool_controller.py runpod workers scale \
  --profile image_to_video \
  --desired 0 \
  --env-file .env.cloud.test \
  --execute
```

slot 命名建议：

```text
Pod name: allbot-runpod-test-<profile>-<slot>
Agent id: runpod_test_<profile>_<slot>
```

示例：

```text
allbot-runpod-test-image-to-video-01
runpod_test_image_to_video_01

allbot-runpod-test-wan22-video-v2-01
runpod_test_wan22_video_v2_01
```

缩容规则：

- 只缩目标 profile。
- 从最高 slot 往低 slot 删除。
- 删除前先把 worker control 置为 `disabled/draining`。
- 如果目标 worker 有 `current_task_id`，默认失败并提示等待；不强杀运行中任务。
- 删除 Pod 后必须核验 RunPod managed pod 与 Central worker control 状态。

## Provider 改造目标

将当前硬编码的 `RUNPOD_TASK_PROFILES` 扩展成通用 profile spec：

```python
RunPodProfileSpec(
    profile_id="image_to_video",
    runtime_profile="image_to_video",
    supported_task_types=("image_to_video",),
    agent_id_prefix="runpod_test_image_to_video",
    pod_name_prefix="allbot-runpod-test-image-to-video",
    image_env_key="RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO",
    template_id_env_key="RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO",
    model_prefix_env_key="RUNPOD_MODEL_PREFIX_IMAGE_TO_VIDEO",
    manifest_key_env_key="RUNPOD_MODEL_MANIFEST_KEY_IMAGE_TO_VIDEO",
    max_pods_env_key="RUNPOD_MAX_PODS_IMAGE_TO_VIDEO",
)
```

需要支持：

- profile-specific image/template/model env。
- profile-specific `SUPPORTED_TASK_TYPES`。
- N slot 渲染。
- list/status 时按 profile 过滤。
- guard 同时检查全局上限、profile 上限、总小时成本和 profile 小时成本。
- redaction 不泄露 RunPod/R2/agent token。

## Canary 调整

拆分后不再用 `wan22_aio_video` 一次跑两条视频任务，而是两条 profile-aware canary：

```bash
python scripts/gpu_pool_controller.py runpod canary \
  --task-type image_to_video \
  --env-file .env.cloud.test \
  --execute

python scripts/gpu_pool_controller.py runpod canary \
  --task-type wan22_video_v2 \
  --env-file .env.cloud.test \
  --execute
```

验收标准：

- `image_to_video` worker heartbeat 只声明 `image_to_video`。
- `wan22_video_v2` worker heartbeat 只声明 `wan22_video_v2`。
- Central `task_type` 与提交任务类型一致，不能再被写成 `img2img`。
- 两类视频 canary 都生成可读 MP4。
- `extract_last_frame=true` 时必须产出可读 `extra_outputs.last_frame`。
- canary 结束恢复被临时禁用的测试 worker，删除 Pod，并确认无 orphan。

## 分阶段实施

### Phase 1：修复 cloud-test 视频派发 bug

- 核对 Web/Core 提交 `image_to_video` 的 route、Pydantic model 和 Central enqueue task type。
- 增加回归测试：提交 `image_to_video` 后 Central 记录必须仍是 `image_to_video`，不能回退成 `img2img`。
- 重新跑 cloud-test canary 的 dry-run，确保 canary 任务参数中有 `extract_last_frame=true`。

### Phase 2：配置拆分

- 在 `task_profiles.yml` 增加 `image_to_video` profile。
- 把当前 `wan22_video_v2` profile 的 task type 收窄为 `wan22_video_v2`。
- 保留 `wan22_aio_video` 兼容 profile，但文档标记为临时 AIO canary profile。
- 增加 `image_to_video_baseline` model bundle。

### Phase 3：Provider 通用化

- 把 RunPod provider 从少量硬编码 profile 改成 profile registry。
- 支持 `RUNPOD_*_<PROFILE>` 变量读取。
- 支持按 profile 渲染单 Pod 和 N slot scale plan。
- 支持重复调用不同 profile 的 scale，不互相清理。

### Phase 4：模型 manifest 拆分和预热

- 生成 `image_to_video` manifest dry-run。
- 生成 `wan22_video_v2` manifest dry-run。
- 对两个 manifest 做 R2 HEAD 校验。
- 如果启用 Network Volume，先在同 data center 预热模型目录。
- 确认两个 manifest 不包含对方专属大模型。

### Phase 5：template 与启动参数

- cloud-test 先复用现有 Wan22 template 验证 env override。
- 如果 RunPod UI/日志中容易混淆，再创建两个 profile 专属 template。
- 确认 template 不保存明文密钥，只使用 RunPod Secret refs。
- 确认 image/template 下的 `dockerStartCmd` 仍能执行 bootstrap、模型同步和 worker 启动。

### Phase 6：单 profile canary

- 启动 1 个 `image_to_video` worker，跑 preview/5s 单起始帧 canary。
- 清理后启动 1 个 `wan22_video_v2` worker，跑 preview/5s 单起始帧 canary。
- 两条都通过后，再做并发 canary：两个 profile 同时各 1 个 Pod，提交两种任务，验证 Central 分发到正确 agent 前缀。

### Phase 7：N 副本扩缩容

- dry-run 验证 `img2img_lora=2`、`image_to_video=1`、`wan22_video_v2=1`。
- 真实 cloud-test 验证不同 profile 多次 scale：
  - 先 `image_to_video -> 1`
  - 再 `wan22_video_v2 -> 1`
  - 再 `image_to_video -> 2`
  - 再分别缩容到 0
- 每次只影响目标 profile，最后 `list-pods` 和 `reconcile-managed-pods` 均无 orphan。

### Phase 8：正式准备，另行确认

- cloud-test 全部通过后，再制定正式 profile 数量、成本上限、template id、模型 prefix 和 Network Volume 策略。
- 正式执行前必须单独确认，不把 cloud-test 的 `--execute` 口径带入生产。

## Test Plan

单元测试：

- `test_runpod_provider.py`
  - 三类 profile render。
  - `image_to_video` 与 `wan22_video_v2` 使用同 image/template 但不同 `SUPPORTED_TASK_TYPES`、manifest 和 agent prefix。
  - N slot render，slot 名称稳定。
  - profile-specific guard：总 Pod 数、单 profile Pod 数、小时成本。
  - scale 目标 profile 时不删除其它 profile Pod。

- `test_runpod_canary.py`
  - `image_to_video` canary 只临时禁用支持 `image_to_video` 的非 RunPod 测试 worker。
  - `wan22_video_v2` canary 只临时禁用支持 `wan22_video_v2` 的非 RunPod 测试 worker。
  - 两类视频任务都要求 `extract_last_frame=true`。
  - render validation 接受 template id，同时校验 profile-specific model manifest。

- `test_gpu_pool_controller.py`
  - CLI parse 覆盖 `runpod workers render-scale/scale --profile ... --desired N`。
  - unsupported profile 报错。

- Web/Core/Central 回归测试
  - `/image_to_video` 入队后 Central `task_type` 必须是 `image_to_video`。
  - `/wan22_video_v2` 入队后 Central `task_type` 必须是 `wan22_video_v2`。
  - 不允许视频入口被兼容路由降级为 `img2img`。

本地 dry-run：

```bash
pytest tests/ops/test_runpod_provider.py \
  tests/ops/test_runpod_canary.py \
  tests/ops/test_gpu_pool_controller.py \
  tests/ops/test_runpod_bootstrap.py

python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile image_to_video \
  --desired 1 \
  --env cloud-test

python scripts/gpu_pool_controller.py runpod workers render-scale \
  --profile wan22_video_v2 \
  --desired 1 \
  --env cloud-test
```

cloud-test 验收：

```bash
python scripts/gpu_pool_controller.py runpod workers scale \
  --profile image_to_video \
  --desired 1 \
  --env-file .env.cloud.test \
  --execute

python scripts/gpu_pool_controller.py runpod canary \
  --task-type image_to_video \
  --env-file .env.cloud.test \
  --execute

python scripts/gpu_pool_controller.py runpod workers scale \
  --profile wan22_video_v2 \
  --desired 1 \
  --env-file .env.cloud.test \
  --execute

python scripts/gpu_pool_controller.py runpod canary \
  --task-type wan22_video_v2 \
  --env-file .env.cloud.test \
  --execute
```

清理验收：

```bash
python scripts/gpu_pool_controller.py runpod workers scale \
  --profile image_to_video \
  --desired 0 \
  --env-file .env.cloud.test \
  --execute

python scripts/gpu_pool_controller.py runpod workers scale \
  --profile wan22_video_v2 \
  --desired 0 \
  --env-file .env.cloud.test \
  --execute

python scripts/gpu_pool_controller.py runpod list-pods --env-file .env.cloud.test
python scripts/gpu_pool_controller.py runpod reconcile-managed-pods --env-file .env.cloud.test
```

## 风险与注意事项

- 如果使用 RunPod Network Volume，Pod 必须落在同 data center，否则 volume 加速收益会消失，甚至限制可用 GPU 供给。
- 两个视频 profile 共用镜像时，不能通过镜像判断任务能力，必须看 `SUPPORTED_TASK_TYPES` 和 `POOL_RUNTIME_PROFILE`。
- `image_to_video` 当前派发 bug 是 P0 阻塞；不修复就算拆 profile，任务也可能继续被错误 worker 接走或产出 PNG。
- 扩缩容命令必须先做 profile-aware list/filter，防止误删其它 profile 的 Pod。
- 正式环境的数量、成本和 max pod guard 必须单独配置，不能沿用 cloud-test 的临时值。
- 业务大模型不得 baked 入镜像；镜像只包含 ComfyUI、custom nodes、ffmpeg/ffprobe 和 worker 运行依赖。

## Non-goals

- 本计划不创建真实 RunPod Pod。
- 本计划不上传或删除 R2 对象。
- 本计划不读取或修改 `.env.cloud.prod`。
- 本计划不把视频 worker 接入正式环境。
- 本计划不改变用户侧任务命名：旧图生视频仍是 `image_to_video`，v2 仍是 `wan22_video_v2`。
