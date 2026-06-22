---
name: "allbot-comfy-models"
description: "处理图生图/图生视频的附加模型(LoRA/ControlNet)配置、Bot 菜单参数透传与 ComfyUI 工作流动态注入。当新增或修改 AI 生成模型时，必须调用本技能。"
---

# AllBot ComfyUI 附加模型配置指南

本指南汇总了在现有分层解耦架构（Bot 交互 -> Backend 队列 -> Comfy Agent 调度）下，新增各种附加模型（如 LoRA、ControlNet 等）的实施方案。

整个过程主要是一个**配置驱动**的过程，无需重构核心逻辑。下面分别介绍“图生图”与“图生视频”附加模型的具体配置路径。

新增模型、workflow 或运行时 profile 时，叠加 `allbot-tdd` 做最小映射/patcher/worker focused tests；遇到 ComfyUI 400、模型缺失、RunPod/LAN runtime 不一致或结果物化异常时，叠加 `allbot-diagnosing-bugs` 先建立可复现反馈环。

低频且易过期的 RunPod/LAN/runtime 细节优先沉淀到 [references/runtime-profiles.md](references/runtime-profiles.md)，主技能只保留事实源红线、配置入口和验证要求。

---

## 0. workflow 资产事实源红线

- `workers/comfy_agent/workflows` 是唯一 workflow 资产事实源；`backend/workflows` 已退出，Central API 不再挂载、COPY 或启动校验 workflow 目录。
- 新增或修改 workflow JSON、`mappings.json`、`workflow_patcher.py`、`workflow_task_patchers.py` 时，只更新 Worker 目录，并确认目标 Worker 的 `SUPPORTED_TASK_TYPES` 覆盖该 task type。
- RunPod 镜像运行的是 `remote_workers/` bundle；新增 workflow override 或远端可接任务时，必须同步 `remote_workers/src/workflow_mapping_validation.py` 与 `remote_workers/comfy_agent/workflows/`，不能只改本地主服务器的 `workers/` / `src/` 副本。
- RunPod bootstrap 只在 `/workspace/allbot/repo/remote_workers` 不存在时 clone `deploy`；旧 Pod 原地重启可能复用已有 bundle。修复 workflow/override 后，新建 Pod 会自然拉到最新代码；已有旧 Pod 要先 `disable`，再 SSH/diagnostic 更新远端 repo 或重建 Pod。
- Worker 启动时会基于 `workers/comfy_agent/workflows/mappings.json` 校验映射节点与输入名；Central API 只负责参数网关和队列入队，不再用 workflow 文件做启动门禁。
- 重导 workflow 后必须复核硬编码节点 ID、`mappings.json` 节点输入名、`TASK_TYPE_WORKFLOW_FILENAMES` 绑定和 Worker `SUPPORTED_TASK_TYPES`，避免 Worker 校验通过但执行面读到旧文件。
- 共享 workflow 的 alias 必须同轮维护：`image_to_video`、`video_insert`、`video_edit` 都绑定 `Wan22AioV82.json`，并必须同时存在于 `mappings.json` 与 `TASK_SPECIFIC_PATCHERS`，且复用 `patch_image_to_video_workflow`。生产 worker 的 workflow/mapping 目录可能是 bind mount，而 patcher 可能随镜像烘焙；只更新挂载目录不重建对应 agent，会造成半更新并触发 ComfyUI 400。
- `face_swap_v2.json` 是从 `i2i_pro` Flux2/edit 链路拆出的图片换脸替代模板；业务 task type 仍保持 `face_swap`，通过 Worker `TASK_TYPE_WORKFLOW_OVERRIDES` 指向 v2，不新增 Backend/Bot 任务类型，也不需要 Python 专属 patcher。`mappings.json` 必须保持 `face_image -> 2`、`body_image -> 3`；未设置 override 时默认绑定仍回到旧 `face_swap.json`。
- 本地主模型 registry 的 `model-import-plan` / `model-import-execute` 也必须按实际 runtime override 抽取模型：当前 `face_swap -> face_swap_v2.json`、`t2i-pornmaster-turbo -> txt2img_from_i2i_pro.json`，并与 `i2i_pro.json` 共享 `i2i_pro_baseline` 六个 Flux2/Z-Image 模型。不要再把 legacy Pornmaster/t2i 或旧 `face_swap.json` 专属模型纳入 `i2i_pro_baseline`。
- 局域网 GPU 节点的模型目录、`comfy0/comfy1` 容器挂载和 `inst0/inst1` 隔离关系见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。新增或移动模型前必须确认目标 ComfyUI 的共享模型目录，避免误改另一张卡正在使用的模型集。
- Worker Agent 与 ComfyUI Runtime 是两层：`cloud-prod-comfy-agent-*` 更新 workflow/patcher/上传逻辑，目标 GPU 节点上的 ComfyUI 负责实际模型加载。`gpu-226:8188` 是宿主机 ComfyUI，不是 Docker `comfy0`；`POOL_IMAGE_REF` 只是期望 profile/镜像声明，不能当作模型已随镜像部署的证据。
- GPU Pool Controller 首阶段模型同步只写目标共享 `models` 目录；不要碰 `input/output/temp/custom_nodes/workflows`，也不要为了修路径创建大模型重复别名文件。模型路径应按 Comfy `/object_info` 和 workflow 实际引用修正。

---

## 一、 新增图生图附加模型（LoRA/ControlNet）实施方案

### 1. 模型文件部署 (Deployment)
- 将新模型的 `.safetensors` 或 `.pt` 文件放置到 ComfyUI 宿主机映射的对应模型目录中（例如 `models/loras/` 或 `models/controlnet/`）。
- 确保文件名拼写正确且全系统唯一，因为后续的路由完全依赖此文件路径。

### 2. Bot 层：更新用户交互菜单 (UI & FSM)
- **文件定位**：`src/handlers/fsm/edit_image_fsm.py`（或相关的状态机配置）。
- **实施步骤**：
  - 找到存储模型映射的常量字典（如 `LORA_MODELS`）。
  - 在字典中追加新模型配置：将**模型实际相对路径**（如 `"qwen/illustration_v2.safetensors"`）作为键，映射到用户可见的**中文按钮标签**（如 `"插画风"`）。**注意路径必须严格包含在宿主机目录下的相对路径前缀**。
  - **权重配置（重要）**：若新模型需要特定的默认权重（非 `1.0`），必须在同文件下的 `get_lora_default_strength` 函数中增加对应的条件分支。
  - 若引入的是全新类别（如增加 ControlNet 专属选单），需在状态机流转中插入一个新的等待节点（State）以收集该参数。

### 3. Backend 层：参数网关透传 (API Routing)
- **文件定位**：`backend/app/models.py` 和 `backend/app/main.py`。
- **实施步骤**：
  - 检查用于验证图生图请求的 Pydantic 模型（如 `Img2ImgLoraRequest`）。
  - 如果新模型复用现有的 `lora_name` 或 `lora_strength` 参数，则本层**无需任何修改**。
  - 如果新增了独立维度的参数（如 `controlnet_image` 或 `controlnet_weight`），需在对应模型中声明这些可选字段，确保后端 API 能将参数安全写入 Redis 队列。

### 4. Worker 层：工作流映射与动态注入 (Workflow Patcher)
- **文件定位**：`workers/comfy_agent/workflows/mappings.json`、`workers/comfy_agent/workflows/Qwen-Rapid-AIO.json` 及 `workers/comfy_agent/workflow_patcher.py`。
- **实施步骤**：
  - **更新模板**：在 ComfyUI 本地调试好包含新节点的工作流，导出 API 格式的 JSON（非 UI 格式）覆盖现有模板。记录新附加模型节点（如 `Load LoRA`）的节点 ID。
  - **配置映射**：在 `mappings.json` 中，声明 Backend 参数键与 ComfyUI 节点 ID 的对应关系，若需要特定输入名可通过 `{key}_input` 指定（例如：`"lora_name_2": "45", "lora_name_2_input": "lora_name"`）。
  - **启动期校验**：Worker 会在启动时校验 `mappings.json`，至少检查“映射节点 ID 是否存在”“映射输入名是否真实存在于节点 `inputs` 中”。若校验失败，Worker 会 fail fast，避免把错误工作流带到线上运行阶段。
  - **编写动态补丁**：若该模型为**用户可选**（非全局强制加载），需在 `workflow_patcher.py` 中补充防爆逻辑：当检测到任务参数未携带该模型时，通过脚本动态**删除该节点**并**重新缝合**工作流上下文连线（如将 Checkpoint 的连线绕过该节点直接连向下游）。
    > ⚠️ **节点硬编码警告**：由于当前 `workflow_patcher.py` 中的节点剪枝和重连高度依赖硬编码的节点 ID（例如图生图逻辑中写死了 ID 为 `32` 的节点为 LoRA 节点，ID 为 `2` 的节点为 KSampler），如果在更新模板时节点 ID 发生变化，务必同步修改代码中的防爆硬编码逻辑，否则会导致连线断裂！
    > 💡 **格式排障**：如果在导出 JSON 时误导出了 UI 格式（包含 `"nodes"` 数组），Agent 的日志会输出 `Workflow xxx.json seems to be in UI format` 警告。请确保使用 ComfyUI 的 `Save (API Format)` 按钮导出。

### 5. 验证与发布 (Testing & Restart)
- 遵循部署规范，通过 `docker-compose up -d comfy-agent-1` 等指令平滑重载对应的 Agent 容器以读取新 JSON，并重启 Bot 进程。
- 在 Telegram 中唤起图生图菜单，验证新按钮渲染、参数透传是否成功，并在后台观察 ComfyUI 是否成功加载该 `.safetensors` 文件。

---

## 二、 旧图生视频附加模型（LoRA）实施方案

旧图生视频的用户侧类型仍保留 `custom_video` / `video_lora`，Web 侧也允许字面量 `image_to_video`；Telegram 懒人动图保留 `perfect_video_insert` / `doggy_style` / `blowjob` / `undress_tongue` / `closeup_blowjob` 等历史 mode 与内置提示词。上述旧入口执行面统一为 `image_to_video`，并与 `wan22_video_v2` 共用 `workers/comfy_agent/workflows/Wan22AioV82.json`。两者通过 `src.domain_config.wan22_aio_video` 的 profile 注入不同主模型：旧入口使用 `legacy_image_to_video` profile，v2 使用 `wan22_video_v2` profile。旧 `src.services.wan22_video_v2_config` 与 `src.services.wan22_video_v2_context` 兼容 re-export 已删除，新增逻辑直接引用 domain_config 入口。

目前系统主要支持 LTX-2.3 和 Wan2.2/Wan2.1 视频生成工作流。关于 LTX-2.3 工作流的具体 LoRA 使用与提示词规范，请参考项目根目录的 `LTX_LoRA_Guide.md`。

### 1. 模型文件部署 (Deployment)
- **文件命名规范**：根据现有的探针逻辑，图生视频的 LoRA 模型在生成阶段分为高噪和低噪两个环节。新模型**必须**包含两个文件，并严格按照以下格式命名：
  - `{lora_name}_high_noise.safetensors`
  - `{lora_name}_low_noise.safetensors`
  - *(例如：如果你的模型代号叫 `Dance`，则需要提供 `Dance_high_noise.safetensors` 和 `Dance_low_noise.safetensors`)*
- 将上述两个文件放置到 ComfyUI 宿主机映射的对应 LoRA 模型目录中（如 `models/loras/`）。
- 旧图生视频支持 `5s/8s/10s`，对应 `81/129/161` 帧，分辨率与计费基数和 v2 对齐为 `preview=6`、`small=12`、`standard=20`、`hd=30`，时长倍率为 `1x/2x/3x`；旧投稿 `512p/720p/1024p` 分别映射为 `preview/standard/hd`，`0.36 MP - Small` 映射为 `small`。
- Wan22 AIO 底层映射必须保持：旧图生视频 `custom_video` / `video_lora` / Web 字面量 `image_to_video` / 懒人动图 mode / legacy Central alias `video_insert`、`video_edit` -> execution `image_to_video` -> `legacy_image_to_video` profile；图生视频 v2 `wan22_video_v2` -> execution `wan22_video_v2` -> `wan22_video_v2` profile。两者共享 worker workflow，但不是同一个用户功能，历史/Gallery task type 不能互相改名；Web `/api/tasks/generate` 提交 `image_to_video` 后 Central `task_type` 必须保持 `image_to_video`，懒人动图历史 type 也必须保留原 mode。

### 2. Bot 层：更新用户交互菜单 (UI & FSM)
- **文件定位**：`src/handlers/fsm/image_to_video_fsm.py`
- **实施步骤**：
  - 找到存储模型映射的常量字典 `VIDEO_LORA_MODELS`（定义在 `src/lora_catalog.py`，由 `image_to_video_fsm.py` 渲染）。
  - 在字典中追加新模型配置：将**模型前缀名**（即上述的 `{lora_name}`，如 `"Dance"`）作为键，映射到用户可见的**中文按钮标签**（如 `"跳舞"`）。
  - 保存后，Telegram 机器人中的【图生视频】入口会在启动时展示同屏设置面板：第一组为附加模型按钮，第二组为“单图生成/添加终止帧”，第三组为 `preview/small/standard/hd` 分辨率档位，第四组为 `5s/8s/10s` 时长，第五组为确认。
  - 用户确认后再上传图片：单图模式收 1 张起始图，首尾帧模式依次收起始图和终止图，然后发送提示词提交。
  - 旧入口提供 `5s/8s/10s` 三档时长；菜单与 Web 投稿应用都应展示 v2 四档分辨率和三档时长。`/custom_video` 兼容入口应保持无 LoRA，避免把带 LoRA 的任务写成 `custom_video` 历史类型。

### 3. Backend 层：参数网关透传 (API Routing)
- **文件定位**：`backend/app/models.py` 和 `backend/app/main_simple_task_routes.py`。
- **实施状态**：**无需修改**。
  - 后端网关已经定义了 `VideoLoraRequest`。
  - `/image_to_video` 和兼容入口 `/perfect_video_lora` 会入队到执行面 `TaskType.IMAGE_TO_VIDEO`，同时将 `lora_name`、`resolution_preset`、`end_image`、`extract_last_frame=True` 等参数携带给下游 Worker。
  - `/perfect_video_insert` 与 `/perfect_video_edit` 只作为旧 endpoint 兼容入口保留，会把旧 width/height/frame length 归一为 Wan22 的 `resolution_preset` 与秒数，并入队 `TaskType.IMAGE_TO_VIDEO`。懒人动图的差异应停留在 FSM 内置 prompt 和历史 mode，不再新增或复活独立 worker workflow。

### 4. Worker 层：工作流动态注入 (Workflow Patcher)
- **文件定位**：`workers/comfy_agent/workflow_task_patchers.py` 和 `workers/comfy_agent/workflows/Wan22AioV82.json`。
- **实施状态**：**通常无需修改**，但需注意**硬编码防爆红线**。
  - `patch_image_to_video_workflow` 与 `patch_wan22_video_v2_workflow` 只应作为薄入口，真实实现统一落在 `_patch_wan22_aio_workflow(...)`；legacy `video_insert` / `video_edit` worker alias 也必须复用 `patch_image_to_video_workflow`，不要再绑定 `perfect_video_insert.json`、`perfect_video_edit.json` 或任务专属模型。
  - 主模型节点固定为 `2616`（high）和 `2617`（low）。patcher 会根据 `wan22_model_profile` 写入对应 high/low UNet 文件。
  - 旧 LoRA 注入节点固定为 `26`（high noise）和 `18`（low noise）：
    - `26.inputs.lora_1.lora = {lora_name}_high_noise.safetensors`
    - `18.inputs.lora_1.lora = {lora_name}_low_noise.safetensors`
  - 无 LoRA 的 `custom_video`、懒人动图 mode 与 `wan22_video_v2` 必须清空 `26` / `18` 的 LoRA slot，避免 workflow 模板残留旧模型。
  - V82 通过 `265` 对 `2603` 最终帧序列插帧；默认节点类为 `FL_RIFE`（`multiplier=4`）。`_patch_wan22_aio_workflow(...)` 会在检测到 `265` 后让 `28` 视频输出、`2575` 帧数统计和 `2607` 尾帧提取都读取 `["265", 0]`，避免插帧被绕过或时长变慢。三档时长会写入 `2578.inputs.value`，保持 `5s/8s/10s` 对应 `81/129/161` 源帧。V82 还通过节点 `2599` 使用 `LTXVSpatioTemporalTiledVAEDecode` 进行视频 VAE decode。若某个 ComfyUI 未暴露 `FL_RIFE` 或 `LTXVSpatioTemporalTiledVAEDecode`，应修复该 ComfyUI 自定义节点/依赖环境，不应在 worker 侧切换节点类。所有 `image_to_video` / `wan22_video_v2` / `wan22_aio_video` runtime 必须把 `rife49.pth` 作为离线运行依赖：LAN AIO 预置到 `ComfyUI_Fill-Nodes` 和 `ComfyUI-Frame-Interpolation` 的 RIFE 缓存路径；RunPod Wan22 新构建镜像需在构建期 baked 同一小权重，bootstrap/entrypoint 通过 `remote_workers/scripts/ensure_wan22_rife_cache.py` fail-fast 检查。正式任务后处理不应依赖在线访问 HuggingFace。
  - 节点 `2612` 当前 DaSiWa 版本要求同时写入旧口径 `precision_presets` 和新口径 `resolution_preset`，并补齐 `swap_aspect_when_not_image=false`、`aspect_preset_when_not_image="9:16 - Social"`、`custom_aspect_width=16`、`custom_aspect_height=9`；否则 RunPod ComfyUI `/prompt` 会因 `required input is missing` 拒绝工作流。节点 `2607` 的 `ImageFromBatch.batch_index` 必须保持 `4095`，不要改回旧模板里的 `16384`，新节点最大值为 `4095`。
  - 扩展生成、分段重生成和整链拼接依赖 `extra_outputs.last_frame`。Worker 会优先读取 Comfy `2503` 尾帧输出；若个别 Comfy 实例只返回主 MP4，`agent_result_materialization.py` 会用 worker 镜像内的 `ffmpeg/ffprobe` 从主视频补抽最后一帧，因此 `workers/Dockerfile` 必须保留 ffmpeg 依赖。
  - RunPod Wan22 共享镜像构建入口仍为 `remote_workers/docker/runpod_profiles/wan22_aio_video/Dockerfile`，但 cloud-test 运行时主路径已经拆成 `image_to_video` 与 `wan22_video_v2` 两个 profile；不要再把 `wan22_aio_video` 当作新视频 worker/canary 主 profile。共享镜像默认 base 为局域网成功实例 `192.168.1.2:8189` 同款 `yanwk/comfyui-boot:cu128-slim`，新构建 tag 只 baked `Wan22AioV82.json` 所需 custom nodes、`ffmpeg/ffprobe`、`rife49.pth` 小型后处理权重和运行依赖；其中 `FL_RIFE` 来自 `filliptm/ComfyUI_Fill-Nodes`，`LTXVSpatioTemporalTiledVAEDecode` 取自 `Lightricks/ComfyUI-LTXVideo` 的 `tiled_vae_decode.py`。RunPod 镜像只为 LTXVideo 写入最小 `__init__.py` 注册 tiled decode 节点，不加载 Gemma/Q8/PromptEnhancer 等全量 LTXVideo 节点，避免无关依赖失败导致 Wan22 必需节点缺失。不要直接 `docker commit` 局域网 `comfy1` 容器作为发布镜像，因为成功内容主要来自 bind mount / volume。Wan22 high/low UNet、VAE、text encoder 与旧视频 LoRA 不能 baked 入镜像。当前 split profile 默认复用带 RIFE 缓存的 `20260619-wan22aio-rife-bcf3ebd` Wan22 image；旧 `20260613-wan22aio-lanbase-ab9b7ea` 只作为回滚/热缓存场景，使用旧 tag 时必须依赖 slot 热缓存或启动 helper 预置 `rife49.pth`，不要误认为旧 tag 已 baked 该权重。模型分别同步 `allbot-model-cache/image_to_video/2026-06-13-test/manifest.json` 与 `allbot-model-cache/wan22_video_v2/2026-06-13-test/manifest.json`；`wan22_aio_video/2026-06-12-test/manifest.json` 仅作为兼容/回滚全集 manifest，`video_basic/2026-06-10` 不再作为独立主 manifest，legacy `video_insert` / `video_edit` 只归入 `image_to_video`。RunPod `wan22_video_v2` profile 默认带 `COMFY_EXTRA_ARGS=--disable-dynamic-vram`，LAN AIO `image_to_video` / `wan22_video_v2` runtime-render 也必须追加该参数，避免 cu128 ComfyUI 0.21.x 的 DynamicVRAM/comfy-aimdo 在 `WanTEModel` 动态加载阶段卡住或在 32G 5090 上概率性 OOM；同时带 `WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS=600` 与 `WAN22_VIDEO_V2_EXIT_ON_TIMEOUT=true`，timeout 会 interrupt ComfyUI、失败上报并退出容器重启，避免卡住后继续接单。
  - 2026-06-19 后 Wan22 稳定镜像 tag 为 `ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`，LAN mirror 为 `192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`；该 tag 已 baked 两处 `rife49.pth`、`runpod_bootstrap_from_git.sh`，并通过 smoke。旧 `20260613-wan22aio-lanbase-ab9b7ea` 只能作为回滚/热缓存场景，不能作为新 RunPod 事实源；`image_to_video` / `wan22_video_v2` split profile 不再继承 legacy `RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO` 或 `RUNPOD_USE_TEMPLATE_WAN22_AIO_VIDEO`，若 RunPod template 仍指旧镜像，必须关闭 split-video 的 `RUNPOD_USE_TEMPLATE_*`，直接渲染 `imageName`。
  - RunPod `i2i_pro` 是现有 ComfyUI runtime profile，不新增业务 task type；cloud-test 与手动正式 `prod-worker --profile i2i_pro` 都可同时支持 `i2i_pro`、Web 文生图执行类型 `t2i-pornmaster-turbo`、`face_swap`。Pod env 必须声明 `SUPPORTED_TASK_TYPES=i2i_pro,t2i-pornmaster-turbo,face_swap`，并设置 `TASK_TYPE_WORKFLOW_OVERRIDES={"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json","face_swap":"face_swap_v2.json"}`。镜像入口为 `remote_workers/docker/runpod_profiles/i2i_pro/Dockerfile`，默认 `yanwk/comfyui-boot:cu128-slim`，与现有图生图 / Wan22 RunPod 镜像基线一致；ComfyUI pin 到 `16cd8d8a8f5f16ce7e5f929fdba9f783990254ea`，三份 workflow 都只依赖 ComfyUI/core `nodes` 与 `comfy_extras` 的 Flux2/edit 节点。不要使用 `cu130` 基线；`20260614-i2ipro-6b167aa-cu128-min4` 已在 RunPod 4090 cloud-test Web canary 中成功完成模型同步、ComfyUI 启动、worker heartbeat 和 `i2i_pro` 真实任务出图。GitHub Actions smoke 在 CPU runner 上做静态源码检查，真实 GPU import / execution 以 cloud-test canary 为准；cu128 base 是 openSUSE，镜像 smoke 还要检查 `sshd` / `ssh-keygen`，否则 direct TCP SSH 诊断不可用。若 canary 失败后保留诊断 Pod，复跑任务使用 `--reuse-pod-id i2i_pro=<pod_id>`。模型不 baked 入镜像，专用 manifest 为 `allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json`，六个模型文件总计约 `36.11 GiB`；首次 cloud-test canary 使用 `RUNPOD_CONTAINER_DISK_GB=120`，GPU 只请求 `NVIDIA GeForce RTX 4090`，模型同步只能写 ComfyUI `models/`。生产 Pod 不开放长期 SSH，真实创建/启用/canary 必须用户明确确认。
  - SCAIL-2 业务 task type 当前包括 `scail2_action_transfer`（动作迁移，`replacement_mode=false`）、`scail2_video_replacement`（视频换人，`replacement_mode=true`）和 `scail2_face_swap_v2`（视频换脸 v10 two-stage，`replacement_mode=true`）。Bot 入口位于“视频生视频”二级菜单，按“视频换人 / 动作迁移 / 视频换脸”展示；SCAIL-2 入口收参考图、驱动视频、可选正向提示词和 5s/8s 时长，负面词使用 `SCAIL2_DEFAULT_NEGATIVE_PROMPT`，驱动视频上限 40MB。Bot 可点击跳过正向提示词，Web 可留空；空值由 `src.domain_config.scail2_video.normalize_scail2_positive_prompt(...)` 按 task type 补默认提示词，并由 worker patcher 写入 `CLIPTextEncode 6`。业务执行只提交派生 API workflow；新增/重导后必须同步 `.api.json`、`mappings.json`、`workflow_task_patchers.py`、`src/workflow_mapping_validation.py` 与 `remote_workers/`。SCAIL-2 固定 512x896，只开放 5s/8s，成本分别为 40/80 灵石；worker patcher 强制 `VHS_LoadVideo.force_rate=16`、`skip_first_frames=0`，并把 `frame_load_cap` / `WanSCAILToVideo.length` 写为 `81/129`。manifest 前缀为 `scail2/2026-06-17-test`，LoRA 必须落在 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`；镜像入口 `remote_workers/docker/runpod_profiles/scail2/Dockerfile` 必须 baked SCAIL-2 core 节点和视频依赖，但不得 baked 模型权重。
  - `SCAIL-2_FaceSwap_v2.api.json` 是从 `SCAIL-2_Replacement.api.json` 派生的视频换脸 v2 workflow 资产，已同步 `workers/` 与 `remote_workers/`。它复用 SCAIL-2 主模型、LoRA、采样、VAE、`WanSCAILToVideo` 与输出节点，只把 `SAM3_VideoTrack` 条件词从 `human` 收窄为 `face`、`max_objects=1`，并保留 `replacement_mode=true`。`SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json` 是当前视频换脸 v10 候选：worker 先从驱动视频抽第一帧，调用 `face_swap_v2.json` 把用户参考脸换到该首帧，再把换脸后的首帧作为 SCAIL-2 reference image；v10 workflow 本体复用视频换人的 `human` track / replacement 喂法，避免把 Flux2 图片换脸模型混装进 SCAIL-2 runtime。
  - 当前保留并作为代码默认映射的 SCAIL-2 带音频 workflow 是 `SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json`、`SCAIL-2_Replacement_audio.api.json`、`SCAIL-2_Animation_multi-char_audio.api.json`。三者都在输出 `VHS_VideoCombine` 节点接入驱动视频 `VHS_LoadVideo` 的 audio 输出 `["113", 2]`，并保持 `trim_to_audio=false`。原始 `SCAIL-2_Replacement.api.json` 与 `SCAIL-2_Animation_multi-char.api.json` 只作对照/回滚资产，不要用中间试验覆盖；云测试 `cloud_worker_test_08` 当前通过 `CLOUD_TEST_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES` 把动作迁移/视频换人/视频换脸分别指向 `SCAIL-2_Animation_multi-char_audio.api.json`、`SCAIL-2_Replacement_audio.api.json`、`SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json`，并通过 `CLOUD_TEST_WORKER_08_FACE_SWAP_V10_*` 打开两阶段预处理。中间试验 workflow 已删除，不再作为保留资产。
  - SCAIL-2 运行环境分四类：云测试 LAN runtime 是 gpu-002 GPU0/`8190` 的 `allbot-lan-aio-gpu-002-gpu0-scail2-test`，接单层是 `cloud_worker_test_08`，当前可声明 `scail2_action_transfer,scail2_video_replacement,scail2_face_swap_v2`；云测试 RunPod profile `scail2` 仍按两任务 canary 口径运行，除非另行扩展；云正式 LAN runtime 使用 `scripts/lan_scail2_aio_prod.sh` 在 gpu-002 slot0/`8190` 启动 `lan_aio_prod_gpu002_gpu0_scail2_01`，正式 LAN 接单类型为 `scail2_action_transfer,scail2_video_replacement,scail2_face_swap_v2`，其中视频换脸通过 `SCAIL2_FACE_SWAP_V10_*` 先调用 `face_swap_v2.json` 生成换脸首帧；云正式手动 RunPod profile `scail2` 仍保持动作迁移/视频换人两任务声明，用户输入/结果必须写 `user-data-prod`。
  - LAN AIO 生产支持矩阵以 `ops/gpu_pool_controller/config/lan_aio_prod_slots.yml` 为事实源：`gpu-177` 已整机 `prod_enabled`，GPU0 `image_to_video`（兼容 `video_insert` / `video_edit` alias）和 GPU1 `ltx_video` 均由 AIO 承载；2026-06-20 旧 `cloud_prod_worker_02/03`、`cloud-prod-comfy-agent-2/3`、`comfy0/comfy1` 与 `/data/comfy` 已退役删除，gpu-177 不再有本地旧链路回滚。`gpu-002` slot0 AIO 正式承载 SCAIL-2 的 `scail2_action_transfer` / `scail2_video_replacement` / `scail2_face_swap_v2`；`gpu-252-gpu0-img2img_lora` 已 `prod_enabled` 承接 `img2img/img2img_lora`；`gpu-252-gpu1-wan22_video_v2` 当前无本地 GPU1 可用，AIO control 必须保持 `disabled`，由 RunPod 兜底，旧 `comfy1` / `cloud-prod-comfy-agent-5` 仍是 stopped rollback。
  - > ⚠️ **节点硬编码警告**：如果后续重导 `Wan22AioV82.json`，必须复核 `2616`、`2617`、`26`、`18`、`2612`、`23`、`24`、`2368`、`2371`、`2578`、`2603`、`265`、`2575`、`2607` 是否仍满足当前补丁与 mappings 逻辑，否则主模型、LoRA、分辨率、首尾帧输入、时长、RIFE 插帧或尾帧输出会失效。

### 5. 验证与发布 (Testing & Restart)
- 上传好 `.safetensors` 模型文件后，重启 Bot 进程（以重载 `VIDEO_LORA_MODELS` 字典）。
- 在 Telegram 中唤起【图生视频】菜单，确认新添加的动作按钮出现在首个设置区；选择模型、帧模式和分辨率后点击“确定”。
- 观察 Worker (Agent) 的控制台日志，确认 `workflow_task_patchers.py` 成功将 `{lora_name}_high_noise.safetensors` 和 `{lora_name}_low_noise.safetensors` 注入到了 `26` 和 `18` 节点中，且 ComfyUI 能够正常加载文件并启动推理。
- 同时验证旧投稿一键应用：prompt 恢复、`[模型: xxx]` 能解析为 `lora_name`、`1024p` 映射 `hd`、`5s/8s/10s` 恢复和对应灵石消耗。

---

## 三、 高级图生视频 (`ltx_video`) LoRA 多选协议

### 1. 当前主协议
- `ltx_video` 当前主路径已从单个 `lora_name / lora_strength` 升级为 `lora_items`：
  - `lora_items: [{name, strength}, ...]`
  - 最多 3 个 LoRA
- 旧字段 `lora_name / lora_strength` 仍保留兼容，但不再是新增功能的首选协议。
- 用户侧历史/Gallery 仍统一归类为 `ltx_video`；执行面按模式分发为：
  - `ltx_video`：旧单首帧 I2V，工作流 `LTX 2.3 I2V 6.1.json`
  - `ltx_video_flf2v`：首帧 + 终止帧，工作流 `LTX 2.3 FLF2V 6.1.json`
  - `ltx_video_v2v_audio`：输入视频 + 文本生成带音频视频，工作流 `LTX 2.3 V2V Audio 6.1.json`
- 三条 LTX 执行路径共用同一组主模型与 LoRA/附加模型协议，不新增模型选择体系。

### 2. Bot / Web 侧入口
- **文件定位**：`src/lora_catalog.py`、`src/handlers/fsm/ltx_video_fsm.py`、`frontend/src/views/SingleImageToVideo.vue`、`frontend/src/components/template-apply/TemplateImageToVideoPanel.vue`
- **当前事实**：
  - Telegram FSM 允许多选最多 3 个 LoRA，并支持逐项调整强度；LoRA 后会进入同屏设置面板，合并选择 LTX 模式（单首帧、首尾帧、视频配音）、清晰度和时长，确认后再按模式上传 1 张图片、2 张图片或 1 段视频。
  - Web 单图视频页支持 LTX 三模式切换；练功房把 LTX 视频配音拆为独立内部模式 `ltx_video_audio`，但真实提交仍是用户侧 `ltx_video` + `inputs.ltx_mode="v2v_audio"`；练功房高级图生视频只保留单首帧/首尾帧，并可在当前结果区直接用 `extra_outputs.last_frame` 扩展生成。
  - 前端主路径提交 `inputs.lora_items`，而不是只提交单个 `inputs.lora_name`。
  - LTX 结果若存在 `extra_outputs.last_frame`，Web 结果区/历史详情和 Bot 结果消息可进入“扩展生成”，把尾帧作为下一段起始帧。Web/Bot 续段提交会携带 `inputs.ltx_prev_task_id` 与 `inputs.ltx_chain_task_ids`；Web finalizer 和 Bot completion 会把它们持久化到 `extra_outputs._ltx_context`，历史/结果响应转成 `result_meta.ltx_prev_task_id`、`result_meta.ltx_chain_task_ids`、`result_meta.ltx_segment_index`。
  - LTX 续段结果（存在 `result_meta.ltx_prev_task_id`）可在练功房结果区或闪回瓶详情调用 `/users/history/{task_id}/ltx-chain/stitch` 拼接整条链，拼接历史使用 `extra_outputs.ltx_chain_stitch` 标记。首段只有扩展按钮，不显示拼接按钮。

### 3. Backend 层
- **文件定位**：`backend/app/models.py`
- **当前事实**：
  - `LtxVideoRequest` 已同时支持 `lora_items` 与兼容字段 `lora_name / lora_strength`。
  - `LtxVideoFlf2VRequest` 和 `LtxVideoV2VAudioRequest` 分别对应 `/api/v1/ltx_video_flf2v`、`/api/v1/ltx_video_v2v_audio`。
  - 上游 Web/Bot 仍提交用户侧 `ltx_video`；`src/core/task_dispatcher.py` 通过 `inputs.ltx_mode`、`use_end_frame`、`video` 或输入数量分流到上述执行面 simple routes。
  - Web LTX 扩展链路元数据由 `src/core/task_dispatcher.py` 写入 metadata，并由 `src/services/task_web_terminal_finalization.py` 合并到历史 `extra_outputs._ltx_context`；Bot LTX 扩展链路元数据由 `src/handlers/fsm/ltx_video_fsm.py` / `process_ltx_video_task(...)` 传入 result metadata，并由 `src/services/task_service_completion.py` 合并到同一 `_ltx_context`。拼接入口位于 `src/web_api/services/ltx_history_chain_service.py`。
  - 新增 LTX LoRA 时，通常无需新增 task type，重点是保持请求模型与 patcher 协议一致。

### 4. Worker 层
- **文件定位**：`workers/comfy_agent/workflow_task_patchers.py`、`workers/comfy_agent/workflows/LTX 2.3 I2V 6.1.json`、`workers/comfy_agent/workflows/LTX 2.3 FLF2V 6.1.json`、`workers/comfy_agent/workflows/LTX 2.3 V2V Audio 6.1.json`
- **当前约定**：
  - 注入节点固定为 `256`（`Power Lora Loader (rgthree)`）。
  - patcher 会优先消费 `lora_items`，写入 `lora_1..n`。
  - 若 `lora_items` 为空，则兼容回退读取 `lora_name / lora_strength`。
  - 若最终没有有效 LoRA，则裁掉节点 `256`，并把 `8.inputs.model` 回接到 `191`。
  - `ltx_video_flf2v` 的终止帧输入节点为 `16`，尾帧保存节点为 `902`，关键 image-to-video 节点为 `26:297` / `26:312`。
  - `ltx_video_v2v_audio` 的输入视频节点为 `900`，patcher 固定 `force_rate=24`，`frame_load_cap=duration_seconds*24+1`。
  - 三个 LTX task type 都属于视频主输出任务；结果物化会优先识别 MP4，并把 `last_frame` 写入 `extra_outputs.last_frame`。若 Comfy 未返回 `902` 图片，worker 会用 ffmpeg 从主 MP4 兜底抽取尾帧。
  - 目标 LTX worker 的 `SUPPORTED_TASK_TYPES` 必须包含 `ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`，并同步 `remote_workers/`。
- **LTX AIO 镜像**：
  - LAN/RunPod 化最小镜像入口为 `remote_workers/docker/runpod_profiles/ltx_video/Dockerfile`，当前 LAN registry tag 为 `192.168.1.115:5000/allbot/comfy-runpod-ltx-video:20260618-ltx-min-cu128-sageattn1`。
  - 镜像面向 LTX 三工作流：保留 KJNodes、VideoHelperSuite、rgthree、LTXVideo、`sageattention==1.0.6`，并用 `allbot_ltx_min_nodes` shim 覆盖 `ImpactDummyInput`、`TwoWaySwitch`、`easy int`、`mxSlider`、`RAMCleanup`、`VRAMCleanup`、`Float`、`IntToFloat`、`Sigmas Sigmoid`、`MathExpression|pysssss`；workflow 保持 `sage_attention=auto`，不要通过禁用 SageAttention 来绕过依赖缺失。不要把 Easy-Use、Impact-Pack、mxToolkit、Memory_Cleanup、RES4LYF、custom-scripts 等大包作为 LTX 最小镜像依赖重新引入。
  - V2V Audio 使用 VideoHelperSuite 的视频读取节点，并保留现有 LTX workflow 的 audio 输出方向；真实上线前必须用目标 ComfyUI `/object_info` 和一单 smoke 确认 `VHS_LoadVideo`、`VHS_VideoCombine`、`SaveImage 902` 可用且输出 MP4 含音轨。
  - LTX AIO 不 baked 模型权重，模型仍从 `allbot-model-cache/ltx_video/2026-06-10/manifest.json` 同步；新增/重导 workflow 时要用容器 `/object_info` 复核上述 shim 节点和 `LTXV*`/rgthree/VHS 节点。
- **红线**：
  - 若重导出任一 LTX workflow，必须复核 `256`、`191`、`189`、`8`、`15`、`16`、`26:297`、`26:312`、`900`、`902` 这些节点 ID 是否仍满足补丁逻辑。

### 5. 验证建议
- 同时验证“多选 LoRA”“旧字段兼容”“无 LoRA”三种场景。
- 同时验证普通 I2V、首尾帧 FLF2V、V2V Audio 三条路径，至少覆盖无 LoRA 和多 LoRA。
- 首尾帧与 V2V Audio 的验收必须检查主 MP4、`extra_outputs.last_frame`；V2V Audio 还需用 `ffprobe` 或播放器确认音轨存在。
- 若只更新前端但不更新 worker patcher，容易出现 UI 可多选但执行面只吃首项或直接失效的知识错配。
