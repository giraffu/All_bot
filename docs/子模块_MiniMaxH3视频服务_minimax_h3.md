# 子模块：MiniMax H3 视频服务

## 能力与边界

`minimax_h3` 是独立 GPU profile，不是 LTX alias。用户只开放三个任务：
`minimax_h3_t2v`、`minimax_h3_i2v`、`minimax_h3_flf2v`。Web 使用一个“高级图生
视频pro”工作台切换三种模式，主 Bot 使用同一组模式；两端都不提供附加模型选择。
历史 `minimax_h3_ref2v` 类型与 workflow 仅用于读取旧任务和代码兼容，不进入 H3
Worker pool、RunPod/LAN 支持任务列表或新建入口。

Web 由 `enable_minimax_h3` 控制，后端由 `MINIMAX_H3_BACKEND_ENABLED` 控制。
提示词优化另由 `MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED` 控制。测试与正式 Dashboard
可分别维护共享场景配置 `minimax_h3`，但开关关闭时 Web/Bot 不展示优化入口。

## 请求契约

- 公共字段为非空 `prompt`、`duration=5|10|15`、
  `resolution_preset=preview|small|standard|hd` 和可选 `seed`。四档普通模式每 5 秒
  分别计 10/15/20/30 点。
- T2V 不接受图片；I2V 恰好一张首帧；FLF2V 恰好两张有序首尾帧。
- I2V/FLF2V 固定 `aspect_ratio=source`，按首帧像素预算与 Div32 计算尺寸。FLF2V
  首尾帧比例差异超过 1% 时由入口和 Worker 双重拒绝。
- `src/domain_config/minimax_h3.py` 是时长、尺寸、帧数、费用和输入数量的事实源。
  `lora_items`、`lora_name` 或 `lora_strength` 只要出现在 H3 请求中就拒绝，包括空值；
  客户端不能覆盖模型、采样器、steps、timeline、本地路径或参考音视频。
- 输出为带音轨 MP4，并由 `SaveImage` 产生 `extra_outputs.last_frame`。
- ComfyUI history 同时包含视频和尾帧时，MP4 是主结果，名称含 `last_frame` 的 PNG
  只能进入 `extra_outputs.last_frame`。

## 固定 RedMix 栈

T2V/I2V/FLF2V 使用 Civitai modelVersion `3226037` 的 RedMix A2A Beta1 固定栈：

- diffusion model：`REDMix-MiniMaxH3-A2A-pruned-int8-convrot-ComfyMCP.safetensors`；
- text encoder：`qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors`；
- video VAE：`minimax_h3_video_vae_int8_convrot.safetensors`；
- audio VAE：Comfy-Org 官方 `minimax_h3_audio_vae_fp32.safetensors`。

RedMix 文件元数据记录的合并配方以 `10Eros_Max_h3_fl2va_beta1_pruned` 为起点，依次
合入 LightX2V MiniMax H3 Turbo 8-step v1.0（`0.75`）、SexGod NaughtyTimes H3
（`0.75`）及作者用于 A2A 的 reference LoRA（`0.5`），然后以官方 H3 INT8 ConvRot
结构量化保存。因此 10Eros 的成人审美/细节/动作、LightX2V 8-step 加速和
NaughtyTimes 成人动作能力已经在 checkpoint 中，不得再次加载同名外部 LoRA，否则会
重复放大融合效果。

三个公开 workflow 固定使用 8 steps、`simple` scheduler、Euler sampler、video/audio
shift `12/3`，并保留 KJNodes H3 memory-efficient SageAttention patch。它们没有
`LoraLoaderModelOnly` 或 TurboSampler 节点，不注入触发词。与旧方案相比，运行模型包
从约 80.6 GiB 降至约 37.7 GiB，并移除 BF16 FL2VA、REF2VA、旧 Qwen encoder、FP16
video VAE、五个用户 LoRA 和独立 Turbo LoRA；INT8 主模型预计降低显存/磁盘压力，但
Beta1 融合会改变整体色彩、人物质感、成人动作偏置和提示词响应，不能期待与旧五 LoRA
组合逐项等价。最终质量仍以三模式 GPU canary 为准。

四份 API JSON 由 `scripts/build_minimax_h3_api_workflows.py` 确定性生成，并同步到
`workers/comfy_agent/workflows/` 与 baked RunPod runtime。公开三模式必须指向同一个
RedMix checkpoint、Heretic encoder 和 INT8 video VAE。

## 模型包与镜像

`scripts/prepare_minimax_h3_model_bundle.py` 固定版本
`2026-08-14-redmix-a2a-beta1-int8`、文件字节数与 SHA256。Civitai 下载要求通过
`CIVITAI_API_TOKEN` 鉴权；Token 只发送给 Civitai API host，不转发到重定向后的对象
存储。模型进入 `/srv/allbot/model-registry` 的内容寻址 blob 与 bundle manifest，随后
上传 LAN model cache；模型文件不得进入 Git 或 OCI 镜像。

镜像模块仍为 `minimax_h3`。Dockerfile 的 ComfyUI、CUDA devel 与 Python builder
基础镜像均从 LAN registry 的精确 digest 读取，不依赖 GHCR 或构建时访问 Docker Hub；
同时固定 DaSiWa Nodes、KJNodes、VHS 和 SageAttention 源码 revision，不再安装
`ComfyUI-MiniMax-H3-Turbo`。RTX 5090 启动时必须
确认 SageAttention wheel 含 `sm120`。ComfyUI 从镜像内 `/opt/ComfyUI` 启动，模型卷
挂载到 `/opt/ComfyUI/models`；禁止源码 bind mount 或在目标机 build。

## LAN 测试切换

测试候选为 `gpu-177-gpu1-minimax_h3_test`，与
`gpu-177-gpu1-ltx_unified` 共用 `gpu-177:gpu1` 和 8191。只能通过
`scripts/lan_aio_fleet_prod_ops.py` 读取实时 ledger、确认队列空闲、warm-cache 并做
单卡 takeover/recover。候选身份固定为 `cloud-test`，只能连接测试 Central 和
`user-data-test`。测试期间正式 LTX 会在自然 drain 后停止；结束时显式 recover。

验收至少串行提交 T2V、I2V、FLF2V 各一条 5 秒 preview，逐条检查：Central task type、
Worker agent、MP4、24fps、音轨、尾帧、显存/OOM/Xid。H3 profile 保持
`reset_comfy_memory_before_task`、`--fast-disk --disable-pinned-memory` 和
DynamicVRAM；运行证据写 XDG history/evidence，不回写本文。

## 最小验证

```bash
python -m pytest -q tests/config/test_minimax_h3.py \
  tests/workers/test_minimax_h3_workflows.py \
  tests/ops/test_runpod_minimax_h3_profile.py \
  tests/scripts/test_prepare_minimax_h3_model_bundle.py
cd frontend && npm test -- --run \
  src/composables/lab-workbench/useLabSubmitPayload.test.ts \
  src/composables/lab-workbench/usePromptOptimizer.test.ts \
  src/views/CustomFeatures.test.ts
```
