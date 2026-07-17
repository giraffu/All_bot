---
name: "allbot-comfy-models"
description: "处理图生图/图生视频的附加模型(LoRA/ControlNet)配置、Bot 菜单参数透传与 ComfyUI 工作流动态注入。当新增或修改 AI 生成模型时，必须调用本技能。"
---

# AllBot ComfyUI 模型与工作流配置

本技能是模型、工作流和参数透传的轻量入口。正文只保留当前真实入口、不可越过的边界和验收要求；节点级细节按需读取文档或 reference，避免技能触发时正文被截断。

## 1. 先读什么

| 场景 | 必读材料 |
| :--- | :--- |
| 图生图 LoRA / ControlNet / img2img 参数透传 | `docs/子模块_附加模型配置指南_comfy_models.md`、`src/handlers/fsm/edit_image_fsm.py`、`workers/comfy_agent/workflow_patcher.py` |
| Wan22 / 旧 `image_to_video` / `video_insert` / `video_edit` | `docs/子模块_附加模型配置指南_comfy_models.md`、`.codex/skills/allbot-comfy-models/references/runtime-profiles.md` |
| LTX 系列 LoRA 多选 | `docs/子模块_附加模型配置指南_comfy_models.md`、`src/lora_catalog.py`、`src/qqcc_ltx_lora_catalog.py`、`src/handlers/fsm/ltx_video_fsm.py`、`frontend/src/features/generation/buildGenerationTaskPayload.ts` |
| SCAIL-2 视频生视频 | `docs/子模块_附加模型配置指南_comfy_models.md`、`docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`、`src/domain_config/task_type_registry.py` |
| RunPod / LAN AIO profile、远端 workflow 同步 | 本技能 + `allbot-ops-deployment` + `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` |
| 任务生命周期、队列、扣费、前端交互 | 分别叠加 `allbot-task-engine`、`allbot-billing-auth`、`vue-best-practices` |

## 2. 稳定事实源

- Comfy workflow 事实源只在 `workers/comfy_agent/workflows/`。旧 `backend/workflows/` 已退出，不要新增或回填。
- RunPod 镜像同步用 `remote_workers/comfy_agent/...`；新增/修改远端 workflow、entrypoint、requirements 或环境变量时，同时检查远端模板和镜像构建路径。
- Central 不挂载、不复制、不校验 workflow JSON。Central 只分发任务；workflow 存在性由 Worker Agent 启动映射和运行时 patcher 负责兜底。
- Worker Agent 和 ComfyUI Runtime 是两层：Agent 选 workflow、下载素材、调用 ComfyUI API、回传结果；Runtime 只加载模型并执行 JSON 图。
- 模型同步只能写运行时配置约定的 `ComfyUI/models/...` 子目录。不要把模型塞进 `custom_nodes`、workflow 目录或代码目录。
- 同一个用户可见入口可能共享一个执行 workflow。修改 UI 文案或 task type 前，先核对 `src/domain_config/task_type_registry.py`、worker mapping 和 patcher。
- `free_edit_v2_5` 是用户可见/History 逻辑类型：单图 alias 到既有 `pornmaster_flux2_edit_bf16`，双图 alias 到内部 `pornmaster_flux2_multi_edit_bf16`。双图执行复用 multiple-images workflow 的节点 `17.image` / `29.image` 并把节点 `9.unet_name` 切到现有 BF16 权重；两种内部类型与自由P图 v3 共用模型和 RunPod/LAN profile。v2.5 单阶段直出，v3 才续接图片换脸，禁止复制 workflow、模型或 GPU profile。
- `image_to_video`、`video_insert`、`video_edit` 当前共享 `Wan22AioV82.json`，依赖 `patch_image_to_video_workflow()` 按 task type 注入差异；不要为三者复制分叉 workflow。
- 图片换脸有两套独立执行契约：V1 `face_swap` 使用旧 `face_swap.json`，正式启用容量保留在 `worker_remote_02`；V2 `face_swap_v2` 通过 per-task override 指向 `face_swap_v2.json`，归属 `i2i_pro` profile。i2i_pro Worker 不得继续声明 `face_swap`，也不得修改 remote02 的旧 workflow、模型或环境。
- 自由P图 v3 的第二阶段和 QQCC `original_face_swap_enabled` 内部原脸恢复使用 `face_swap_v2`；快速/随机换脸仍使用 `face_swap`。SCAIL-2 视频换脸 v10 的首帧预处理也使用 V2 workflow，但作为视频组合任务内部阶段不额外计费。
- `model-import-plan` 必须跟随 runtime override。不要只改本地 `ComfyUI/models`，却遗漏 RunPod / LAN profile 的模型路径和启动映射。

## 3. 修改流程

1. 先判断这是“新增用户可见能力”还是“已有能力追加参数/模型”。能复用现有 task type 和执行 profile 时，不要新增 task type。
2. 更新入口层参数：Bot FSM、Web payload builder、前端表单、`src/lora_catalog.py` 或配置文件应传递同一份结构化字段。
3. 后端只做参数归一、校验和透传。不要在 `src/core/` 引入 Telegram `Update`、FastAPI `Request` 或 ComfyUI HTTP 细节。
4. 在 `workers/comfy_agent/workflows/` 放置或更新 JSON，并在 worker mapping / patcher 中声明路由。远端运行态要同步 `remote_workers`。
5. 对 profile、模型、workflow 有影响时，同步 GPU Pool / RunPod / LAN AIO 文档和运维技能。
6. 补 focused tests，至少覆盖 payload 字段、task type 映射、patcher 注入和关键失败分支。

## 4. 图生图附加模型边界

- LoRA、ControlNet 等附加模型参数应作为结构化 payload 从 UI/FSM 一路透传到 worker，不要靠 prompt 拼接表达业务语义。
- Bot 菜单和 Web 表单的可选项要来自同一份 catalog 或可推导的配置；避免两端静态选项漂移。
- workflow patcher 应只负责把已校验参数注入 ComfyUI JSON，不承担扣费、鉴权或用户权限判断。
- 新增 ControlNet/LoRA 时，核对模型文件名、ComfyUI 节点 loader 类型、strength/weight 默认值和空值行为。
- 图生图改动通常需要覆盖：FSM 黑盒退出、Web payload builder、worker patcher、任务提交成功后的结果回流。

## 5. 视频与 AIO profile 边界

- Wan22 AIO 是当前 `image_to_video`、`video_insert`、`video_edit` 的主执行面。常见关键节点包括 LoRA loader、正负 prompt、首尾图、RIFE、视频保存和尺寸节点；节点 ID 以文档为准，修改前必须重新打开 workflow JSON 核对。
- QQCC 场景负面提示词只走已有 workflow 参数映射：Qwen 自由P图 `img2img`/`img2img_lora` 写 `4.prompt`；PornMaster Flux2 single/multiple edit 写 `254.text` / `49.text`；Wan22 视频写 `2371.value`。空值保持既有空负向或 Wan22 默认负向归一，不新增 task type、profile 或模型目录。
- QQCC `AI动图` 的 `end_frame_draw_scene_id` 只复用当前 AI绘图场景及其 `postprocess_draw_scene_id` 后处理链生成最终尾帧，再把首尾两图传给旧 `image_to_video` / `video_lora` 或 `wan22_video_v2`；视频任务使用视频场景自身 `negative_prompt`，尾帧绘图链使用被引用绘图场景自身 `negative_prompt`，两者不能串用。这不是新 workflow/profile，v2 仍不支持附加 LoRA。
- QQCC `AI滤镜` 使用独立 `filter_scenes`，但 engine、LoRA、`negative_prompt` 与 `original_face_swap_enabled` 规则复用 AI绘图；滤镜场景自身不支持后处理链，只能作为直接单步入口或 `draw_scenes[].postprocess_filter_scene_id` 的终止模板。关闭 `main_buttons.ai_filter` 只隐藏直接入口，不影响有效滤镜模板被 AI绘图引用；不要新增 workflow、RunPod profile、模型 bundle 或数据库表。
- LTX 系列的用户可见 task type 与执行 profile 不完全同名。`ltx_video`、`ltx_video_flf2v`、`ltx_video_v2v_audio` 等映射必须同时核对 registry、payload builder、worker mapping 和模型 catalog。
- LTX 首尾帧 `ltx_video_flf2v` 的默认与 10Eros override workflow 必须开启时空 VAE 的 `last_frame_fix`，让末端 latent 通过临时重复帧获得完整解码上下文；`workers/` 与 `remote_workers/` 两侧必须同步，避免尾帧轻微形变或运行态漂移。
- LTX LoRA 多选使用 `lora_items` 结构，当前限制最多 3 个。legacy `lora_name/lora_strength` 只作兼容，不应作为新入口。
- QQCC `AI视频` 配置保存 `{path,strength}`，提交边界转换为 LTX 既有 `{name,strength}`；强度限制 `0.1..2.0`、步长 `0.05`。LTX I2V/FLF2V/V2V Audio 的非空 `negative_prompt` 映射到节点 `29.text`，但只有独立发布并验收对应 Worker mapping 后才可宣称生效；空白值必须在 Web/Bot/API 边界省略，不能覆盖工作流节点的内置默认文本。单独发布 QQCC 控制面不得为此触碰正式 LTX GPU runtime，主 Bot Telegram 高级 LTX 设置页仍不暴露负面提示词。
- QQCC 管理后台专用 LTX 选项必须写入 `src/qqcc_ltx_lora_catalog.py`，由 `qqcc_config_service` 独占合并、校验和下发；不要写入公开 `LTX_VIDEO_LORA_OPTIONS`。2026-07-17 的专用库包含 32 个已校验 LoRA，其中 26 个不在公开目录。控制面可配置不等于 GPU 可加载：目标 RunPod/LAN AIO manifest 未同步并 smoke 前，不得宣称正式生效。
- LTX Bot 扩展 seed 与完成拼接链路恢复由 `src/services/ltx_video_extension_service.py` 负责；这只影响 Bot 入口层 histories/last_frame/context 准备，不改变 LTX workflow、worker mapping、RunPod profile 或模型目录。
- Wan22 AIO Bot 链路扩展、重生成与完成拼接准备由 `src/services/wan22_video_v2_extension_service.py` 负责，覆盖旧图生视频 `custom_video` / `video_lora` 与图生视频 v2；这只影响 Bot 入口层 histories/last_frame/input/context 准备，不改变 `Wan22AioV82.json`、worker mapping、RunPod profile 或模型目录。
- 主 Bot 高级视频 FSM 的提交 payload 事实源是 `src/services/advanced_video_submission_service.py`：它只做 Bot 入口层提交计划、分辨率/时长归一、首尾帧和 LTX LoRA/链路字段透传，不改变 worker workflow、RunPod profile 或模型目录。
- 主 Bot 高级视频设置面板事实源是 `src/services/advanced_video_settings_view_service.py`：它只生成 Telegram view-model/keyboards 与费用展示，仍不改变 Wan22/LTX workflow、worker mapping、RunPod profile 或模型目录。
- SCAIL-2 是独立视频生视频 profile，用户入口和执行 profile 要保持映射清晰。用户侧只展示 `scail2_action_transfer` 动作迁移，支持 5/8/10/15/20s；dispatcher 会把 10/15/20s 隐式送到内部执行类型 `scail2_action_transfer_long` 和 Context Windows workflow。`scail2_action_transfer_long` 不作为 Bot/Web 入口，也不进入正式 RunPod profile。涉及成本、时长、尺寸或首帧抽取时，同时检查 task registry、billing 配置和 GPU Pool 文档。
- workflow 里的节点 ID 是高风险事实。不要凭记忆改 `node_id`，必须读取当前 JSON；文档中的 ID 只作为导航提示。

## 6. 运行态与部署红线

- 本地开发、云测试、云正式、RunPod 和 LAN AIO 的 workflow/model 资产可能来自不同同步路径。改动任何 workflow 或模型文件后，必须说明哪些运行态已同步、哪些只是本地准备。
- 测试优先：功能研发、联调、缺陷修复和配置调整默认先更新云测试控制面。正式环境发布必须得到用户明确确认。
- RunPod/LAN AIO 镜像或启动脚本调整时，叠加 `allbot-ops-deployment`，并检查 profile 级环境变量、模型挂载、健康检查和 worker 注册。
- 不要把一次性 Pod ID、临时公网 URL、手工任务 ID 写进技能正文；这类材料进入 `logs/` 或 `docs/archive/`。

## 7. 验证清单

- 结构检查：workflow JSON 可解析，worker mapping 指向存在的文件，patcher 找得到目标节点。
- 行为测试：新增或变更参数至少覆盖 Bot/Web payload 到 worker patcher 的一条黄金路径。
- 兼容测试：旧 payload 空字段、legacy LoRA 字段、无附加模型场景仍能提交。
- 运行态检查：涉及 RunPod/LAN AIO 时，确认 `remote_workers`、模型目录、profile 环境变量和启动日志。
- 交付说明：列出触达的 task type、workflow 文件、模型目录、测试命令，以及是否仅更新云测试或已获准正式发布。

## 8. 交付要求

- 修改后同步必要的 `/docs` 和 `docs/knowledge_base_audit_matrix.md`。
- 如果技能体积再次接近 20KB，优先拆到 `references/` 或对应子模块文档，不继续堆正文。
- 最终回复必须说明：改了哪些模型/工作流入口、如何验证、是否需要部署同步，以及是否存在未触达的运行态。
