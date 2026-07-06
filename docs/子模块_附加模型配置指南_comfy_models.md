# 子模块: 附加模型部署与配置指南 (ComfyUI Add-on Models)

本指南汇总了在现有分层解耦架构（Bot 交互 -> Backend 队列 -> Comfy Agent 调度）下，新增各种附加模型（如 LoRA、ControlNet 等）的实施方案。

整个过程主要是一个**配置驱动**的过程，无需重构核心逻辑。下面分别介绍“图生图”与“图生视频”附加模型的具体配置路径。

---

## 0. workflow 资产事实源红线

- `workers/comfy_agent/workflows` 是唯一 workflow 资产事实源；`backend/workflows` 已退出，Central API 不再挂载、COPY 或启动校验 workflow 目录。
- 新增或修改 workflow JSON、`mappings.json`、`workflow_patcher.py`、`workflow_task_patchers.py` 时，只更新 Worker 目录，并确认目标 Worker 的 `SUPPORTED_TASK_TYPES` 覆盖该 task type。
- Worker 启动时会基于 `workers/comfy_agent/workflows/mappings.json` 校验映射节点与输入名；Central API 只负责参数网关和队列入队，不再用 workflow 文件做启动门禁。
- 重导 workflow 后必须复核硬编码节点 ID、`mappings.json` 节点输入名、`TASK_TYPE_WORKFLOW_FILENAMES` 绑定和 Worker `SUPPORTED_TASK_TYPES`，避免 Worker 校验通过但执行面读到旧文件。
- 共享 workflow 的 alias 必须同轮维护：`image_to_video`、`video_insert`、`video_edit` 都绑定 `Wan22AioV82.json`，并必须同时存在于 `mappings.json` 与 `TASK_SPECIFIC_PATCHERS`，且复用 `patch_image_to_video_workflow`。生产 worker 的 workflow/mapping 目录可能是 bind mount，而 patcher 可能随镜像烘焙；只更新挂载目录不重建对应 agent，会造成半更新并触发 ComfyUI 400。
- LAN AIO / RunPod profile 镜像不得 baked `.safetensors` 业务模型；新增大模型 workflow 时先落 API workflow、`mappings.json`、`TASK_TYPE_WORKFLOW_FILENAMES`、`remote_workers/` 同步和 model registry / 云端转存脚本。云端正式 RunPod 模型优先用临时 RunPod transfer Pod 从授权下载链接流式写入 `allbot-model-cache/<profile>/<version>/models/...`，再 HEAD 校验并发布 manifest；不要从本地上传大模型。

---

## 一-A、PornMaster Flux2 图片编辑自动工作流

2026-06-27 新增两份 API-format workflow：

| task type | API workflow | 输入映射 |
| :--- | :--- | :--- |
| `pornmaster_flux2_single_edit` | `PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json` | `image -> LoadImage 15.image`、`prompt -> CLIPTextEncode 185.text`、`seed -> RandomNoise 28.noise_seed` |
| `pornmaster_flux2_multi_edit` | `PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_V1_2026_05_27.api.json` | `image -> LoadImage 17.image`、`image2 -> LoadImage 29.image`、`prompt -> CLIPTextEncode 8.text`、`seed -> RandomNoise 43.noise_seed` |

这两份 workflow 已移除空的 `Lora Loader (LoraManager)` 节点，运行依赖收敛为 ComfyUI Flux2 core 节点：`UNETLoader`、`CLIPLoader`、`VAELoader`、`ReferenceLatent`、`EmptyFlux2LatentImage`、`Flux2Scheduler`、`SamplerCustomAdvanced` 等。对应文件必须同时存在于 `workers/comfy_agent/workflows/` 与 `remote_workers/comfy_agent/workflows/`，并同步 `src/workflow_mapping_validation.py` 与 `remote_workers/src/workflow_mapping_validation.py`。

模型 bundle 口径为 `pornmaster_flux2_edit_baseline/2026-06-27`，LAN cache prefix 为 `pornmaster_flux2_edit/2026-06-27`。需要的模型相对路径为：
- `diffusion_models/flux2/PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors`
- `text_encoders/flux2/qwen_3_8b_fp8mixed.safetensors`
- `vae/flux2/full_encoder_small_decoder.safetensors`

Qwen text encoder 复用 `i2i_pro_baseline/2026-06-14-test` 的本地 registry blob；VAE 与 PornMaster 9B fp8 UNET 已导入 `/srv/allbot/model-registry/bundles/pornmaster_flux2_edit_baseline/2026-06-27/manifest.yml` 并记录 sha256。LAN cache 复核或更新入口是 `scripts/import_pornmaster_flux2_edit_models.py --execute`，默认读取 ignored `.env.local` 中的 `CIVITAI_API_TOKEN`；真实 token 只能放 ignored env 文件，不得写入文档、代码或 git。缺少 UNET 时脚本必须返回阻断状态并拒绝写半截 manifest。完整导入后可执行 `scripts/upload_pornmaster_flux2_edit_models_to_lan_cache.sh --execute` 维护 LAN model cache。

云端正式 RunPod 的模型准备不要走本地上传。使用 `scripts/create_runpod_model_transfer_pod.py --pornmaster-flux2-edit` 渲染三文件 batch，确认 dry-run 中 bucket、prefix、key、sha256、size 正确且 source URL 已脱敏；execute 还必须显式传入 `--confirm-model-transfer`，临时 RunPod 以 `python:3.11-slim` 从 Civitai/HuggingFace 链接流式 multipart 上传到 `allbot-model-cache/pornmaster_flux2_edit/2026-06-27/models/...`，完成后默认退出。Civitai 权限通过 RunPod secret `allbot_civitai_api_token` 或一次性下载 URL 提供，不能写入 batch 明文。转存完成后运行 `scripts/publish_pornmaster_flux2_model_manifest.py`，它会 HEAD 三个对象并要求 `ContentLength` 与 metadata `sha256` 匹配，再写 `pornmaster_flux2_edit/2026-06-27/manifest.json`。

当前默认运行模型固定为 `V4_turbo_fp8`，因为两份 workflow 与 RunningHub 资源名都指向 `PornMaster_flux2_klein_9b_turbo_fp8_V4.safetensors`，且 fp8 更适合标准 24GB RTX 4090 的稳定推理。Civitai 同页还有 `V4_turbo_bf16`，发布时间晚于 fp8、权重约 17.7GB，理论上量化损失更少，但会显著增加显存和加载压力；只有在 48GB 4090 或明确接受 CPU/offload 降速时，才建议另建 bf16 canary profile 测画质，不直接替换当前 fp8 默认 profile。

LAN AIO 镜像入口为 `remote_workers/docker/runpod_profiles/pornmaster_flux2_edit/Dockerfile`，专用构建 wrapper 为 `scripts/build_pornmaster_flux2_edit_lan_aio_image.sh --push`。该镜像基于 i2i_pro LAN AIO 镜像，只 smoke ComfyUI core 节点、FLUX.2 small-decoder VAE 兼容补丁与基础诊断依赖，模型仍由启动时的 LAN model cache manifest 同步，不得 baked 到镜像层。

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

旧图生视频的用户侧能力仍保留 `custom_video` / `video_lora` 两种历史类型；Telegram 懒人动图保留 `perfect_video_insert` / `doggy_style` / `blowjob` / `undress_tongue` / `closeup_blowjob` 等历史 mode 与内置提示词。但这些旧入口的执行面已经统一为 `image_to_video`，并与 `wan22_video_v2` 共用 `workers/comfy_agent/workflows/Wan22AioV82.json`。两者通过 `src.domain_config.wan22_aio_video` 中的 profile 注入不同主模型：旧入口使用 `legacy_image_to_video`，v2 使用 `wan22_video_v2`。旧 `src.services.wan22_video_v2_config` 与 `src.services.wan22_video_v2_context` 兼容 re-export 已删除，新增逻辑必须直接引用 domain_config 入口。

目前系统主要支持 LTX-2.3 和 Wan2.2/Wan2.1 视频生成工作流。关于 LTX-2.3 工作流的具体 LoRA 使用与提示词规范，请参考项目根目录的 `LTX_LoRA_Guide.md`。

### 0. 当前支持概览
- **普通图生视频 / 自定义图生视频 / 懒人动图**：上游类型仍可保留 `custom_video` / `video_lora` / Web 字面量 `image_to_video` / 懒人动图 mode，执行面统一入队 `TaskType.IMAGE_TO_VIDEO`，底层 workflow 为 `Wan22AioV82.json`。
- **Wan22 AIO profile 口径**：旧图生视频 `custom_video` / `video_lora` / 懒人动图 mode / legacy `video_insert`、`video_edit` -> execution `image_to_video` -> `legacy_image_to_video` profile；图生视频 v2 `wan22_video_v2` -> execution `wan22_video_v2` -> `wan22_video_v2` profile。两者共享 worker workflow，但不是同一个用户功能。
- **旧 LoRA 图生视频 (`video_lora`)**：继续接收 `lora_name` 前缀，由 `workflow_task_patchers.py` 按高噪/低噪双节点动态补入。`custom_video` 不带 LoRA 时会清空 LoRA 槽；`wan22_video_v2` 始终清空额外 LoRA 槽。
- **规格口径**：旧图生视频支持 `5s/8s/10s`，对应 `81/129/161` 帧，分辨率和计费基数与 v2 对齐为 `preview=6`、`small=12`、`standard=20`、`hd=30`，时长倍率为 `1x/2x/3x`；旧投稿 `512p/720p/1024p` 分别映射为 `preview/standard/hd`，`0.36 MP - Small` 映射为 `small`。
- **高级图生视频 (`ltx_video`)**：现已升级为 `lora_items` 多选协议。Bot FSM、Web 单图视频页、模板应用面板都会提交最多 3 个 LoRA 项，每项独立携带 `name + strength`；旧 `lora_name / lora_strength` 仍保留兼容入口，但不再是主文档口径。
- **LTX 执行面分支**：用户侧历史/Gallery 仍归类为 `ltx_video`，当前 Bot/Web 入口只开放 `ltx_video`（旧单首帧 I2V）与 `ltx_video_flf2v`（首帧 + 终止帧）。底层 `ltx_video_v2v_audio`（输入视频 + 文本生成带音频视频）仍保留为历史/队列兼容执行面；三者共用现有 LTX 主模型、LoRA 选单和计费倍率，不新增模型选择体系。
- **LTX 扩展上下文**：Web/Bot “扩展生成”都会把 `extra_outputs.last_frame` 作为下一段起始帧，续段提交携带 `ltx_prev_task_id` / `ltx_chain_task_ids`，并持久化为历史 `extra_outputs._ltx_context` 供结果详情和拼接 API 识别。Bot 扩展入口会先展示直接续写/添加终止帧设置面板，但不展示确认按钮；用户直接发送提示词代表直接续写，直接发送图片代表添加终止帧并写入新的 `end_image_path`，起始帧仍使用上一段尾帧。Bot 扩展 seed 与完成拼接链路恢复的事实源是 `src/services/ltx_video_extension_service.py`，handler 只保留 Telegram 回复和结果发送。
- **Wan22 AIO 链路扩展上下文**：旧图生视频 `custom_video` / `video_lora` 与图生视频 v2 的 Bot “扩展生成”都使用上一段 `extra_outputs.last_frame` 作为新段起始帧；“重新生成当前段落”会复用上一段尾帧，并在首尾帧模式下复用当前段第二张输入图。续段/重生成提交继续携带 `wan22_prev_task_id` / `wan22_chain_task_ids` 并持久化到历史 `extra_outputs._wan22_context`。Bot 扩展、重生成 seed 与完成拼接链路恢复的事实源是 `src/services/wan22_video_v2_extension_service.py`，handler/callback 只保留 Telegram 回复、任务启动和结果发送；该收口不改变 `Wan22AioV82.json`、worker mapping、RunPod profile 或模型目录。
- **Bot 提交计划事实源**：主 Bot 高级视频 FSM 的提交 payload 已收口到 `src/services/advanced_video_submission_service.py`。`image_to_video_fsm.py`、`wan22_video_v2_fsm.py`、`ltx_video_fsm.py` 只负责 Telegram 状态、素材接收、额度检查、回复和清理；service 负责旧图生视频/Wan22 v2/LTX 的分辨率/时长归一、首尾帧 images、LTX LoRA 多选与扩展链字段透传。该收口不改变 `Wan22AioV82.json`、LTX workflow、worker mapping、RunPod profile 或模型目录。
- **Bot 设置面板事实源**：主 Bot 高级视频的同屏设置 view-model/keyboards 已收口到 `src/services/advanced_video_settings_view_service.py`。该 service 只生成旧图生视频/Wan22 v2/LTX 的 Telegram 按钮、费用展示与 LTX 扩展提示文案；不改变 task type、workflow、RunPod profile 或模型目录。

### 1. 模型文件部署 (Deployment)
- **文件命名规范**：根据现有的探针逻辑，图生视频的 LoRA 模型在生成阶段分为高噪和低噪两个环节。新模型**必须**包含两个文件，并严格按照以下格式命名：
  - `{lora_name}_high_noise.safetensors`
  - `{lora_name}_low_noise.safetensors`
  - *(例如：如果你的模型代号叫 `Dance`，则需要提供 `Dance_high_noise.safetensors` 和 `Dance_low_noise.safetensors`)*
- 将上述两个文件放置到 ComfyUI 宿主机映射的对应 LoRA 模型目录中（如 `models/loras/`）。

### 2. Bot 层：更新用户交互菜单 (UI & FSM)
- **文件定位**：`src/handlers/fsm/image_to_video_fsm.py`
- **实施步骤**：
  - 找到存储模型映射的常量字典 `VIDEO_LORA_MODELS`（定义在 `src/lora_catalog.py`，由 `image_to_video_fsm.py` 渲染）。
  - 在字典中追加新模型配置：将**模型前缀名**（即上述的 `{lora_name}`，如 `"Dance"`）作为键，映射到用户可见的**中文按钮标签**（如 `"跳舞"`）。
  - 保存后，Telegram 机器人中的【图生视频】入口会在启动时展示同屏设置面板：第一组为附加模型按钮，第二组为“单图生成/添加终止帧”，第三组为 `preview/small/standard/hd` 分辨率档位，第四组为 `5s/8s/10s` 时长；普通入口不再展示确认按钮。
  - 用户直接上传起始图即确认当前设置：单图模式收 1 张起始图，首尾帧模式依次收起始图和终止图，然后发送提示词提交。
  - 旧入口提供 `5s/8s/10s` 三档时长；菜单与 Web 投稿应用都应展示 v2 四档分辨率和三档时长。`/custom_video` 兼容入口应保持无 LoRA，避免把带 LoRA 的任务写成 `custom_video` 历史类型。

### 3. Backend 层：参数网关透传 (API Routing)
- **文件定位**：`backend/app/models.py` 和 `backend/app/main_simple_task_routes.py`。
- **实施状态**：**无需修改**。
  - 后端网关已经定义了 `VideoLoraRequest`。
  - 当前主 simple route 是 `/image_to_video`；兼容入口 `/perfect_video_lora` 仍会接收该请求，并统一**转化为 `TaskType.IMAGE_TO_VIDEO`** 推入 Redis 队列，同时将 `lora_name`、`resolution_preset`、`end_image`、`extract_last_frame=True` 等参数携带给下游 Worker。
  - `/perfect_video_insert` 与 `/perfect_video_edit` 只作为旧 endpoint 兼容入口保留，会把旧 width/height/frame length 归一为 Wan22 的 `resolution_preset` 与秒数，并入队 `TaskType.IMAGE_TO_VIDEO`。懒人动图差异只体现在 FSM 内置 prompt 和历史 mode，不再对应独立 workflow。

### 4. Worker 层：工作流动态注入 (Workflow Patcher)
- **文件定位**：`workers/comfy_agent/workflow_task_patchers.py` 和 `workers/comfy_agent/workflows/Wan22AioV82.json`。
- **实施状态**：**通常无需修改**，但需注意**硬编码防爆红线**。
  - `image_to_video`、legacy `video_insert` / `video_edit` 都必须复用 `patch_image_to_video_workflow`，不要再绑定 `perfect_video_insert.json`、`perfect_video_edit.json` 或任务专属模型。
  - 主模型节点固定为 `2616`（high）和 `2617`（low）。patcher 会根据 `wan22_model_profile` 写入对应 high/low UNet 文件。
  - 旧 LoRA 注入节点固定为 `26`（high noise）和 `18`（low noise）：
    - `26.inputs.lora_1.lora = {lora_name}_high_noise.safetensors`
    - `18.inputs.lora_1.lora = {lora_name}_low_noise.safetensors`
  - 无 LoRA 的 `custom_video`、懒人动图 mode 与 `wan22_video_v2` 必须清空 `26` / `18` 的 LoRA slot，避免 workflow 模板残留旧模型。
  - V82 通过 `265`（`FL_RIFE`，`multiplier=4`）对 `2603` 最终帧序列插帧；`_patch_wan22_aio_workflow(...)` 会在检测到 `265` 后让 `28` 视频输出、`2575` 帧数统计和 `2607` 尾帧提取都读取 `["265", 0]`，避免插帧被绕过或时长变慢。三档时长会写入 `2578.inputs.value`，保持 `5s/8s/10s` 对应 `81/129/161` 源帧。所有 `image_to_video` / `wan22_video_v2` / `wan22_aio_video` runtime 都必须把 `rife49.pth` 当作离线运行依赖：LAN AIO 通过 slot 热缓存预置到 `ComfyUI_Fill-Nodes` 与 `ComfyUI-Frame-Interpolation` 两处路径；RunPod Wan22 新镜像要在构建期 baked 并由 `remote_workers/scripts/ensure_wan22_rife_cache.py` 启动前 fail-fast 校验，不能让正式任务后处理临时访问 HuggingFace。
  - 节点 `2612` 当前 DaSiWa 版本要求同时写入旧口径 `precision_presets` 和新口径 `resolution_preset`，并补齐 `swap_aspect_when_not_image=false`、`aspect_preset_when_not_image="9:16 - Social"`、`custom_aspect_width=16`、`custom_aspect_height=9`；否则 RunPod ComfyUI `/prompt` 会因缺必填输入拒绝工作流。节点 `2607` 的 `ImageFromBatch.batch_index` 必须保持 `4095`，不要改回旧模板里的 `16384`。
  - 扩展生成、分段重生成和整链拼接依赖 `extra_outputs.last_frame`。Worker 会优先读取 Comfy `2503` 尾帧输出；若个别 Comfy 实例只返回主 MP4，`agent_result_materialization.py` 会用 worker 镜像内的 `ffmpeg/ffprobe` 从主视频补抽最后一帧，因此 `workers/Dockerfile` 必须保留 ffmpeg 依赖。
  - > ⚠️ **节点硬编码警告**：如果后续重导 `Wan22AioV82.json`，必须复核 `2616`、`2617`、`26`、`18`、`2612`、`23`、`24`、`2368`、`2371`、`2578`、`2603`、`265`、`2575`、`2607` 是否仍满足当前补丁与 mappings 逻辑，否则主模型、LoRA、分辨率、首尾帧输入、时长、RIFE 插帧或尾帧输出会失效。

### 5. 验证与发布 (Testing & Restart)
- 上传好 `.safetensors` 模型文件后，重启 Bot 进程（以重载 `VIDEO_LORA_MODELS` 字典）。
- 在 Telegram 中唤起【图生视频】菜单，确认新添加的动作按钮出现在首个设置区；选择模型、帧模式和分辨率后直接发送起始图。
- 观察 Worker (Agent) 的控制台日志，确认 `workflow_task_patchers.py` 成功将 `{lora_name}_high_noise.safetensors` 和 `{lora_name}_low_noise.safetensors` 注入到了 `26` 和 `18` 节点中，且 ComfyUI 能够正常加载文件并启动推理。
- 同时验证旧投稿一键应用：prompt 恢复、`[模型: xxx]` 能解析为 `lora_name`、`1024p` 映射 `hd`、`5s/8s/10s` 恢复和对应灵石消耗。

---

## 二-A、QQCC 懒人 Bot 场景附加模型边界

QQCC 独立配置 Web 的 `video_scenes` / `draw_scenes` 可以为每个场景选择底层 engine 和附加模型。该配置仍保存在 `runtime_checkpoints.qqcc_lazy_bot_config:v1`，不会新增 workflow、RunPod profile、模型 bundle 或 Alembic 迁移。

- `AI动图` 默认 engine 为旧 `image_to_video`，不选模型时提交 `custom_video`，选择 `VIDEO_LORA_MODELS` 中的模型时提交 `video_lora` 并透传 `lora_name`。底层仍走旧图生视频 profile 与 `Wan22AioV82.json`，由 `workflow_task_patchers.py` 注入高噪/低噪双 LoRA 节点。
- `AI动图` 切到 `wan22_video_v2` 时提交 `wan22_video_v2`，使用场景提示词、后台固定时长和用户画质选择；v2 本轮不支持附加模型，配置归一化与前端弹窗都必须自动清空 `lora_name`。
- `AI动图` 可选 `end_frame_draw_scene_id` 引用当前有效 `AI绘图` 场景生成尾帧。若该绘图场景配置了 `postprocess_draw_scene_id` 后处理链，运行时使用完整链路最终图作为尾帧。用户仍只上传起始图；QQCC Bot 先隐藏提交被引用绘图链，成功后把用户原图和最终尾帧作为两张输入提交视频。旧 `custom_video` / `video_lora` 透传两张图并写 `use_end_frame=true`，`wan22_video_v2` 透传 `images=[start,end]`；不新增 workflow、profile 或模型 bundle。
- `AI绘图` 默认 engine 为自由P图 v2 `free_edit_v2`，提交 `pornmaster_flux2_single_edit`，不支持附加模型。
- `AI绘图` 切到旧 `free_edit` 时，不选模型提交 `edit`，选择 `IMAGE_LORA_MODELS` 中的模型时提交 `img2img_lora`，并透传 catalog 中的默认 strength。
- `AI绘图` 的 `postprocess_draw_scene_id` 只链式复用其它 `draw_scenes` 的既有 engine/LoRA 配置，不新增 task type、workflow、profile 或模型 bundle；链路循环必须在配置归一化时清理。
- 独立 QQCC Config Backend 的 `GET /api/qqcc/config` 必须返回非持久化 `options`，把 engine 选项和 `src/lora_catalog.py` 中的 LoRA catalog 下发给前端；前端不得手写模型清单，避免和运行时 catalog 漂移。

---

## 三、 高级图生视频 (`ltx_video`) 附加模型实施方案

### 1. 模型文件部署 (Deployment)
- 将 LTX-2.3 LoRA 文件直接放到 ComfyUI LoRA 目录，并保持与工作流节点中一致的**相对路径**，例如 `ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors`。
- 与普通图生视频不同，`ltx_video` 当前走的是**单文件直接注入**，不再要求 `{name}_high_noise / {name}_low_noise` 双文件命名。

### 2. Bot / Web 层：模型选单
- **文件定位**：`src/lora_catalog.py`、`src/handlers/fsm/ltx_video_fsm.py`、`frontend/src/views/CustomFeatures.vue`、`frontend/src/components/template-apply/TemplateImageToVideoPanel.vue`
- **实施步骤**：
  - 在 `src/lora_catalog.py` 的 `LTX_VIDEO_LORA_OPTIONS` 中新增模型条目，维护：
    - `path`：ComfyUI 可识别的相对路径
    - `label_zh` / `label_en`：前后端展示名称
    - `default_strength`：未显式传权重时的默认值
  - Telegram 高级图生视频 FSM 会先进入附加模型选择，再进入同屏设置面板合并选择模式、清晰度和时长；当前允许多选，最多 3 个，并支持逐项调强度。普通入口直接发送起始帧图片即确认当前设置，单首帧上传 1 张图片，首尾帧再继续上传终止帧；旧视频配音回调只提示暂未开放。
  - Web 练功房 `custom_video` 与模板应用面板都支持 LTX 单首帧/首尾帧切换；一键应用上传 1 张起始帧时提交 `ltx_mode=i2v`，额外上传终止帧时提交 `ltx_mode=flf2v`、`use_end_frame=true`。练功房 LTX 至少支持上传两张参考图并自动按首尾帧提交，不再展示独立 `ltx_video_audio` 模式。模板应用面板复用同一批 LTX LoRA 选项；提交时主路径统一写入 `inputs.lora_items`，而不是单个 `inputs.lora_name`。
  - LTX 结果返回 `extra_outputs.last_frame` 后，Web 结果区/历史详情和 Bot 结果消息可执行“扩展生成”，把上一段尾帧作为下一段起始帧；Bot 扩展入口可选直接续写或添加终止帧，面板不再展示确认按钮，发送提示词即直接续写，发送图片即作为终止帧。

### 3. Backend 层：参数网关透传
- **文件定位**：`backend/app/models.py`、`backend/app/main_simple_task_routes.py`、`src/core/task_dispatcher.py`
- **实施状态**：当前 `LtxVideoRequest` 已同时支持：
  - `lora_items: list[{name, strength}]`
  - 兼容字段 `lora_name` 与 `lora_strength`
- **说明**：`LtxVideoFlf2VRequest` / `LtxVideoV2VAudioRequest` 对应执行面 `/api/v1/ltx_video_flf2v` 与 `/api/v1/ltx_video_v2v_audio`；当前上游 Web/Bot 用户入口只提交开放的单首帧/首尾帧，public dispatcher 对 `inputs.ltx_mode=v2v_audio` 直接拒绝，底层 simple route/worker 仍保留兼容能力。新增 LTX LoRA 时通常无需新增 task type；重点是保持请求模型、前端提交协议与 worker patcher 的节点约定一致。

### 4. Worker 层：工作流动态注入
- **文件定位**：`workers/comfy_agent/workflow_task_patchers.py`、`workers/comfy_agent/workflows/LTX 2.3 I2V 6.1.json`、`workers/comfy_agent/workflows/LTX 2.3 FLF2V 6.1.json`、`workers/comfy_agent/workflows/LTX 2.3 V2V Audio 6.1.json`
- **当前约定**：
  - 可选 LoRA 注入节点固定为 `256`（`Power Lora Loader (rgthree)`）。
  - 当请求带 `lora_items` 时，patcher 会按顺序写入 `lora_1..n = {on, lora, strength}`，并清理节点上残留的旧 slot。
  - 当前最大注入槽位为 3；超出的项不会继续下沉到工作流。
  - 当请求未带 `lora_items` 时，patcher 会回退兼容读取 `lora_name / lora_strength`；若最终仍无有效 LoRA，则直接裁掉节点 `256`，并把 `8.inputs.model` 回接到 `191`，保持原始无附加模型拓扑可运行。
  - 未显式传 `strength` 时，会回落到 `src/lora_catalog.py` 中登记的默认强度。
  - `ltx_video_flf2v` 通过 `LoadImage 16` 接收终止帧，并在 `26:297` / `26:312` 写入第二帧条件；`SaveImage 902` 保存尾帧。
  - `ltx_video_v2v_audio` 通过 `VHS_LoadVideo 900` 接收输入视频，patcher 固定 `force_rate=24`、`frame_load_cap=duration_seconds*24+1`。
  - 三个 LTX task type 都需要 worker 声明 `SUPPORTED_TASK_TYPES=ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`，并同步 `remote_workers/`。
  - 2026-06-22 新增的 10Eros v1.2 canary workflow 为 `LTX 2.3 10Eros v1.2 I2V 6.1.json`、`LTX 2.3 10Eros v1.2 FLF2V 6.1.json`、`LTX 2.3 10Eros v1.2 V2V Audio 6.1.json`，只通过单 worker 的 `TASK_TYPE_WORKFLOW_OVERRIDES` 测试覆盖；默认三份 `LTX 2.3 *.json` 仍保持旧主模型绑定。
  - 10Eros v1.2 主模型节点应指向 `LTX 2.3/10Eros_v1.2_fp8mixed_learned.safetensors`；云端 R2 `allbot-model-cache/ltx_video/2026-06-10/manifest.json` 当前为 10Eros v1.2-only，旧 v1 不再作为正式 RunPod 回退。新增或切换主模型时，不要直接覆盖旧 workflow 文件名，先复制新 workflow 并用 override canary。
  - Worker 结果物化会优先识别主 MP4，并保存 `extra_outputs.last_frame`；若 Comfy 未返回 `902` 图片，会用 ffmpeg 从主视频兜底抽最后一帧。
- > ⚠️ **节点硬编码警告**：若你重导出了任一 LTX workflow，必须同步检查 `256`、`191`、`189`、`8`、`15`、`16`、`26:297`、`26:312`、`900`、`902` 这些节点 ID 是否仍满足当前补丁逻辑；否则需要同步修改 `workflow_task_patchers.py`。

### 5. 验证建议
- Telegram：进入【高级图生视频】后应先看到附加模型选择，完成后看到同屏设置面板；直接发送起始帧即确认普通入口设置，单首帧继续要求提示词，首尾帧再要求上传终止帧。
- Web：`ltx_video` 页面和模板应用面板都应能提交 `inputs.lora_items`，并正确回显每个模型的当前强度。
- Worker：分别验证“多选 LoRA / 单个兼容字段 / 不选 LoRA”三种场景，确认多项注入成功、旧字段仍兼容、无 LoRA 时节点被裁剪后仍能正常出图出视频。
- LTX 用户入口：验证单首帧仍走旧工作流，首尾帧输出 MP4 + `last_frame`；扩展生成需验证直接续写和添加终止帧两条路径。如需回归历史兼容执行面，再用直测或受控入口验证 `ltx_video_v2v_audio` 输出 MP4 + `last_frame` 与音轨。

---

## 四、 SCAIL-2 视频生视频工作流

SCAIL-2 当前是正式可用的视频生视频能力。用户侧只展示三个入口：动作迁移、视频换人、视频换脸。
动作迁移的业务/History task type 始终是 `scail2_action_transfer`；dispatcher 按时长决定执行面：
`5s/8s` 走旧动作迁移 workflow，`10s/15s/20s` 走隐藏执行类型 `scail2_action_transfer_long`
和 Context Windows workflow。正式 RunPod `scail2` profile 仍只保持动作迁移/视频换人两任务。
`scail2_face_swap_v2` 使用 SCAIL-2 FaceSwap v10 first-frame image-swap + replacement audio 方案：

| task type | 用户能力 | API workflow | 关键模式 |
| :--- | :--- | :--- | :--- |
| `scail2_action_transfer` | 动作迁移 | `SCAIL-2_Animation_multi-char_audio.api.json` | `replacement_mode=false` |
| `scail2_action_transfer_long` | 隐藏执行路由（动作迁移 10/15/20s） | `SCAIL-2_Animation_WAN-Context-Windows.api.json` | `replacement_mode=false`，不作为用户入口 |
| `scail2_video_replacement` | 视频换人 | `SCAIL-2_Replacement_audio.api.json` | `replacement_mode=true` |
| `scail2_face_swap_v2` | 视频换脸 v10 two-stage | `SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json` | `replacement_mode=true` |

Nomadoor 的四个 UI workflow 仍保存在 `workers/comfy_agent/workflows/` 与
`remote_workers/comfy_agent/workflows/`，用于人工打开 ComfyUI 编辑、对照和 smoke。业务执行必须使用
派生的 API-format workflow，不得直接把 UI JSON 提交给 worker。`SCAIL-2_Animation_WAN-Context-Windows.json`
原始文件是 ComfyUI UI workflow，保存时长为 133 帧、16fps，约 8.3s；已转换为
`SCAIL-2_Animation_WAN-Context-Windows.api.json` 给动作迁移 10/15/20s 隐藏执行路由使用，但该能力
只动态改生成帧数和 `VHS_LoadVideo.frame_load_cap`，不表示支持无限长输入。

### 1. 用户参数与计费
- Web payload 使用 `inputs.images=[reference_image_key, motion_video_key]`，第一个 input 是参考图，第二个 input 是驱动视频。
- Bot 入口位于“视频生视频”二级菜单，默认顺序为“视频换人 / 动作迁移 / 视频换脸 / 返回主菜单”；不再有独立长时长动作迁移入口。Bot 的“视频换脸”入口走 `scail2_face_swap_v2`，旧 `face_video` FSM 仅保留兼容入口。
- Bot 的 SCAIL-2 流程收参考图片、驱动视频、可选正向提示词和时长；Bot 可点击跳过正向提示词，Web 可留空，空值由 `normalize_scail2_positive_prompt(...)` 按 task type 补默认提示词；负面词固定使用 `SCAIL2_DEFAULT_NEGATIVE_PROMPT`。
- 公开 `scail2_action_transfer` 开放 `5s/8s/10s/15s/20s`，计费为 `40/80/120/180/260` 灵石；`scail2_video_replacement` / `scail2_face_swap_v2` 仍只开放 `5s/8s`，计费为 `40/80` 灵石。用户提交 10/15/20s 时，业务记录仍是 `scail2_action_transfer`，执行面才切到 `scail2_action_transfer_long`。
- 驱动视频上传上限仍为 40MB；Web 端按驱动视频实际时长过滤可选时长，但后端仍会按 task type 做最终校验。
- 固定输出规格为 `512x896`。长时间模式的硬上限是 20s，不开放无限长度，也不新增长时间视频换人/换脸。

### 2. Worker patcher 约定
SCAIL-2 workflow 的硬编码节点必须与 `workflow_task_patchers.py` 和测试保持一致：

| 参数 | 节点/输入 |
| :--- | :--- |
| 参考图 | `LoadImage 58` |
| 驱动视频 | `VHS_LoadVideo 113` |
| 正向提示词 | `CLIPTextEncode 6` |
| 负向提示词 | `CLIPTextEncode 7` |
| 生成帧数 | `WanSCAILToVideo 101.length` |
| 读取帧数 | `VHS_LoadVideo.frame_load_cap` |
| 输出前缀 | `VHS_VideoCombine 49.filename_prefix` |

短 workflow 时长映射固定为 `5s -> 81`、`8s -> 129`；Context Windows workflow 映射固定为
`10s -> 161`、`15s -> 241`、`20s -> 321`。`VHS_LoadVideo.force_rate=16`，
`skip_first_frames=0`。`scail2_video_replacement` 与 `scail2_face_swap_v2`
必须强制 replacement mode 为 true，`scail2_action_transfer` 与
`scail2_action_transfer_long` 必须强制 false。长时间 workflow 中的
`WanContextWindowsManual` 保持 `context_length=81`、`context_overlap=29`、
`context_schedule=standard_static`、`fuse_method=pyramid`，`freenoise`
固定为 true；该配置优先减少长时长动作迁移生成耗时，但 FreeNoise 仍可能
把前段噪声片段重排复制到后续窗口，带来动作循环伪影。
audio 候选 workflow 的 `VHS_VideoCombine 49.inputs.audio` 应接 `VHS_LoadVideo 113`
的 audio 输出，且 `trim_to_audio=false`。重导 workflow 后要同时更新：
`SCAIL-2_*.api.json`、`mappings.json`、`workflow_task_patchers.py`、
`src/workflow_mapping_validation.py`、`remote_workers/src/workflow_mapping_validation.py` 与
`remote_workers/comfy_agent/workflows/`。
视频换脸 v10 是两阶段方案，不把 Flux2 图片换脸模型混装进 SCAIL-2 runtime：
worker 先从驱动视频抽第一帧，调用 `192.168.1.226:8188` 的 `face_swap_v2.json`
把用户参考脸换到该首帧，再把“换脸后的首帧”作为 `LoadImage 58` 提交给
`SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json`。v10 workflow
本体复用视频换人的 `human` track / replacement 喂法，`101.reference_image` 仍是 `58`，
`101.reference_image_mask` 与 `101.pose_video_mask` 均来自 `SCAIL2ColoredMask 107`。
目标是让参考图只提供脸部身份，让衣服、身体、背景和构图主要来自驱动视频首帧与驱动视频本身。

### 3. 模型与镜像
- 模型 manifest 固定为 `allbot-model-cache/scail2/2026-06-17-test/manifest.json`。
- LoRA 相对路径必须保持 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`，因为 workflow 的 LoRA 枚举引用带 `Wan2.1/` 子目录。
- 镜像入口是 `remote_workers/docker/runpod_profiles/scail2/Dockerfile`。
- 当前 LAN AIO 镜像是 `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260704-sm120-xformers-pr1262`，用于 RTX 5090/Blackwell 节点时保留 xformers 并包含源码编译的 sm_120 attention kernel；不要用 `--disable-xformers` 绕过性能路径。
- 镜像必须包含 ComfyUI SCAIL-2 core 节点、VideoHelperSuite、KJNodes、rgthree、Frame-Interpolation、Fill-Nodes、ffmpeg、bootstrap/sshd 诊断依赖和 `remote_workers/requirements.txt`。
- 镜像不得 baked 任何 `.safetensors` 模型权重；LAN AIO 与 RunPod 都应启动时从 `allbot-model-cache` 同步模型。

### 4. 运行环境边界
SCAIL-2 当前有四类运行环境，桶和 worker 不得混用：

| 环境 | runtime/agent | 用户数据桶 | 用途 |
| :--- | :--- | :--- | :--- |
| 云测试 LAN | `http://192.168.1.2:8190` + `cloud_worker_test_08` | `user-data-test` | Web/Bot 测试 |
| 云测试 RunPod | `runpod_test_scail2_*` | `user-data-test` | cloud-test canary / 临时验证 |
| 云正式 LAN | `lan_aio_prod_gpu002_gpu0_scail2_01` | `user-data-prod` | 当前正式 LAN 接单路径；`gpu-226-gpu0-scail2` 为同卡回切候选 |
| 云正式 RunPod | `runpod_prod_scail2_manual_NN` | `user-data-prod` | 手动备用/临时扩容，不是默认常驻容量 |

正式 RunPod `scail2` profile 可以通过 Dashboard 或 `scripts/runpod_prod_ops.sh` 创建、暂停、
删除和 canary，但没有 heartbeat 或已删除的 `manual_NN` 不能算作可用容量。若出现 unhealthy/OOM，
先 disable，确认无当前任务后 down 删除 Pod；恢复时重新 add、等待 disabled heartbeat、跑两个 5s
canary MP4，再决定是否 enable。正式用户输入和结果只允许写 `user-data-prod`，模型只允许从
`allbot-model-cache` 同步。

正式 RunPod `ltx_video` profile 同样只作为手动备用/临时扩容能力。它使用
`runpod_prod_ltx_video_manual_NN`、`user-data-prod`、`allbot-model-cache/ltx_video/2026-06-10/manifest.json`
和三份 10Eros v1.2 workflow override；不修改 LAN LTX AIO，也不覆盖默认 `LTX 2.3 *.json`
workflow。canary 只提交一单 5s I2V MP4，结束后目标 worker 保持 `disabled`，确认产物后再
手动 enable。

正式 RunPod `pornmaster_flux2_edit` profile 使用 `runpod_prod_pornmaster_flux2_edit_manual_NN`、
`user-data-prod` 和 `allbot-model-cache/pornmaster_flux2_edit/2026-06-27/manifest.json`，只承接
`pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit`。它可通过 Dashboard 或
`scripts/runpod_prod_ops.sh` 手动新增、pause/delete、canary 与 enable，但 `autoscaler_enabled=false`，
不会进入自动扩缩容。canary 必须串行验证 single-edit 与 multi-edit 两单均由目标 RunPod agent 接单并返回 image。
