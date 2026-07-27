# Comfy Runtime Profiles

本文件收纳低频、易过期的 ComfyUI runtime / RunPod / LAN profile 记忆。使用前仍需用代码、compose、Central `/system/workers`、目标 ComfyUI `/object_info` 和当前环境变量复核。

## 使用规则
- 测试执行事实源是 `workers/comfy_agent/`；正式 LAN/RunPod 镜像事实源是 `workers/runpod_runtime/` 与 `workers/runpod_profiles/`。
- 新增或重导 workflow 时，优先验证节点 ID、输入名、`SUPPORTED_TASK_TYPES`、workflow override 和 patcher 绑定。
- LAN/RunPod 镜像运行 `workers/runpod_runtime/` bundle；公共 workflow、mapping 或 patcher 变化必须同轮更新两个运行时并通过 parity test。
- 生产 worker 的 workflow/mapping 可能来自 bind mount，而 patcher 可能来自镜像；只更新一边会造成半更新。

## 当前 profile 口径
- `image_to_video` 与 `wan22_video_v2` 是 Wan22 split video 主 profile；`wan22_aio_video` 只保留兼容/回滚语义。
- `i2i_pro` profile 同时承接 `i2i_pro`、执行面 `t2i-pornmaster-turbo`、`face_swap_v2` 和 legacy `face_swap`；两个 face swap 类型都 override 到 `face_swap_v2.json`。旧远程 V1 执行池已退役，候选 profile 是否已部署仍必须以 Central 实时心跳复核。
- `scail2` LAN 正式可承接 `scail2_action_transfer`、`scail2_video_replacement`、`scail2_face_swap_v2`；正式 RunPod `scail2` 手动备用池默认仍按动作迁移/视频换人口径。
- LTX runtime 必须同时覆盖 `ltx_video`、`ltx_video_flf2v`、`ltx_video_v2v_audio`，并保留尾帧输出或 ffmpeg 兜底抽帧能力。

## 复核 checklist
- 目标 worker 是否声明目标 `SUPPORTED_TASK_TYPES`。
- workflow 文件、mapping、patcher、validation 与 RunPod bundle 是否同轮维护。
- ComfyUI `/object_info` 是否包含 workflow 所需 custom nodes。
- 模型 manifest / LAN cache / RunPod bootstrap 是否只同步模型目录，不误写 input/output/temp/custom_nodes/workflows。
- 视频 runtime 是否具备离线后处理依赖，例如 RIFE 小权重和 ffmpeg/ffprobe。
