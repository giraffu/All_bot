# 子模块：MiniMax H3 视频服务

## 能力与边界

`minimax_h3` 是独立 GPU profile，不是 LTX alias。用户态和 Central 保留四个任务身份：
`minimax_h3_t2v`、`minimax_h3_i2v`、`minimax_h3_flf2v`、`minimax_h3_ref2v`。
测试 Web 使用一个工作台切换四种子模式；Bot、QQCC、Gallery、生产 RunPod 和
autoscaler 默认不接入。Web 由 `enable_minimax_h3` 控制，后端由
`MINIMAX_H3_BACKEND_ENABLED` 控制，两个开关默认关闭。

## 请求契约

- 公共字段：非空 `prompt`、`duration=5|10|15`、
  `resolution_preset=preview|standard|hd`、常用 `aspect_ratio` 和可选 `seed`。
- T2V 不接受图片；I2V 恰好 1 张；FLF2V 恰好 2 张有序首尾帧；REF2V 接受
  1–4 张有序角色参考图和可选的等长角色说明。
- 服务端 `src/domain_config/minimax_h3.py` 是尺寸、帧数、费用和输入数量事实源。
  Worker 再次拒绝模型、LoRA、采样器、timeline、本地路径和参考音视频覆盖。
- 输出为带音轨 MP4，并通过 `SaveImage` 产生 `extra_outputs.last_frame` 所需尾帧。
- ComfyUI history 同时出现 VHS `gifs/videos` 与 `SaveImage.images` 时，四个 H3
  task type 必须优先把 MP4 物化为主结果；文件名含 `last_frame` 的 PNG 只进入
  `extra_outputs.last_frame`，不得覆盖主视频。

## Workflow 与模型

四份 API workflow 的事实源位于 `workers/comfy_agent/workflows/`，由
`scripts/build_minimax_h3_api_workflows.py` 确定性生成并同步进 baked RunPod runtime。
生成器校验 DaSiWa Civitai UI 源文件 SHA256 后才接受源资产；API 图固定 25 steps、
`res_multistep`、`simple`、video/audio shift `11/4`，并启用 KJNodes 的 H3
memory-efficient SageAttention patch。

REF2V 的原生 `MiniMaxH3ReferenceToVideo` 节点使用 ComfyUI V3 Autogrow 输入。
API JSON 必须以 `ref_images.ref_image_0` 至 `ref_images.ref_image_3` 连接 1–4 张
有序参考图；不得使用扁平 `ref_image_1` 等字段，否则节点执行阶段会收到非预期
关键字。业务提示词中的 `<Picture 1>` 仍保持 1-based，两种编号只属于不同层次。

模型包为 `minimax_h3_runtime/2026-08-04-dasiwa-cmmh3-v1`，来自固定 revision 的
`Comfy-Org/MiniMax-H3` 官方量化转换，包含 FL2VA、REF2VA、Qwen3-VL text encoder
及 video/audio VAE；没有 DaSiWa 微调 checkpoint 或 LoRA。模型只进入内容寻址仓库、
R2 model cache 和目标模型卷，不进入 Git 或 OCI 镜像。

## 发布与 LAN 验收

镜像模块为 `minimax_h3`，Dockerfile 固定 ComfyUI、DaSiWa Nodes、KJNodes、VHS
以及官方 SageAttention 源码 revision。H3 不得使用 PyPI
`sageattention==1.0.6`：KJNodes H3 patch 依赖 2.x `sageattention.core` 和 RTX 5090
SM120 kernel。构建阶段使用 digest-pinned CUDA 12.8 devel toolkit，只编译
`TORCH_CUDA_ARCH_LIST=12.0`，最终镜像只复制 wheel，不携带 devel toolkit。先从完整
Git SHA 构建 canonical digest，再保 digest 复制到 LAN registry；
未获得精确 digest 前不得把候选写入 LAN catalog。

H3 的 ComfyUI 代码和 custom nodes 必须从镜像内 `/opt/ComfyUI` 启动，不能回落到
网络卷或 LAN workspace 中可能存在的 `/workspace/ComfyUI`。模型仍保存在外部模型卷：
LAN 将精确模型 workspace 挂载到 `/opt/ComfyUI/models`；RunPod 由 baked entrypoint
把 `/opt/ComfyUI/models` 安全链接到 `/workspace/ComfyUI/models`。构建后 smoke 必须
真实启动 CPU ComfyUI 并从 `/object_info` 校验六个 H3 必需节点，仅检查源码文件存在
不构成节点注册证据。CPU `/object_info` 也不证明 SageAttention kernel 可用；H3
容器在 GPU 上启动时还必须校验 `get_cuda_arch_versions()` 包含 `sm120`，否则不得
注册 Worker。

GPU1 验收只走 `scripts/lan_aio_fleet_prod_ops.py`：重新读取 XDG ledger 和 live queue，
等待 LTX 自然空闲，warm-cache 后事务性 takeover，串行执行四个 5 秒 preview，稳定后
补一个 10 秒 standard，最后显式 recover 原 LTX slot。任一 OOM、Xid、队列、音轨、
尾帧或 Central 心跳失败立即回滚；运行态结果只写 XDG history/evidence，不回写本文。
H3 profile 必须启用 `reset_comfy_memory_before_task`，让每个串行请求提交前通过 Comfy
`/free` 卸载上一个驻留模型和 allocator 缓存，避免共享宿主 RAM 上跨任务累积。
LAN RTX 5090 profile 同时固定 `--fast-disk --disable-pinned-memory`：模型 workspace
位于 NVMe，优先使用磁盘后备动态加载并禁止大块 pinned host-memory 池，避免与同机
其它 GPU Worker 争用约 60 GiB 宿主 RAM；保持 DynamicVRAM 开启，不使用 lowvram。

静态候选为 `gpu-177-gpu1-minimax_h3`，独占 H3 workspace、模型 workspace、容器名和
agent ID，但与当前 `gpu-177-gpu1-ltx_unified` 共享 `gpu-177:gpu1`/8191 物理槽。
catalog v2 会把非 blocked 条目规范化为 operator-eligible `catalog_ready`；这只允许显式
fleet 操作，不等同于开启公共 H3 feature flag 或自动接流。四任务 workflow override
必须随 compose 一起渲染，禁止让 I2V、FLF2V 或 REF2V 回落到 T2V 图。
接管后的串行矩阵由 `scripts/minimax_h3_prod_smoke.py` 提交；脚本绑定预期 agent，
逐单校验 Central task type、结果 MP4、24fps、原生音轨和 `extra_outputs.last_frame`，
并把一次性 evidence 写入 XDG state，而不是 Git。生产 Web API 默认入口是
`https://api.aivison.it.com/api`；canary JWT 必须来自当前 Web API secret 且绑定实际
存在的内部测试用户/password_version，禁止用本地陈旧 secret 猜测 token。

## 最小验证

```bash
python -m pytest -q tests/config/test_minimax_h3.py \
  tests/workers/test_minimax_h3_workflows.py \
  tests/ops/test_runpod_minimax_h3_profile.py \
  tests/scripts/test_prepare_minimax_h3_model_bundle.py
cd frontend && npm test -- --run src/composables/lab-workbench/useLabSubmitPayload.test.ts
```
