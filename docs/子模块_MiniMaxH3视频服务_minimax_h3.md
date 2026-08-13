# 子模块：MiniMax H3 视频服务

## 能力与边界

`minimax_h3` 是独立 GPU profile，不是 LTX alias。Central/Worker 为历史恢复保留四个执行身份：
`minimax_h3_t2v`、`minimax_h3_i2v`、`minimax_h3_flf2v`、`minimax_h3_ref2v`。
测试 Web 使用一个工作台切换 T2V/I2V/FLF2V 三种子模式；REF2V 角色参考视频已从
Bot/Web 新建入口关闭，只保留内部兼容执行身份。面向用户统一展示为“高级图生视频pro”，
不暴露模型或 workflow 供应方名称；QQCC AI 视频
按有无尾帧链自动提交 I2V/FLF2V。Gallery、生产 RunPod 和 autoscaler 默认不接入。
Web 由 `enable_minimax_h3` 控制，后端由
`MINIMAX_H3_BACKEND_ENABLED` 控制，两个开关默认关闭。
提示词优化另由 `MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED` 独立控制；测试开启、正式关闭，
不影响 H3 视频生成。测试与正式 Dashboard 都可独立维护共享场景配置
`minimax_h3`，但正式 Web/Bot 在开关关闭时不展示或调用优化入口。
测试 Web 的 runtime config 当前只展示 MiniMax H3 工作台，并隐藏
`ltx_video`、`ltx_video_v2` 与 `ltx_t2v` 三个 LTX 工作台；生产映射保持独立，
不随测试可见性切换。

## 请求契约

- 公共字段：非空 `prompt`、`duration=5|10|15`（Bot/QQCC 可接收兼容的
  `"5s"` 标签，但进入任务请求、计费和 History 前必须归一为整数秒）、
  `resolution_preset=preview|small|standard|hd` 和可选 `seed`。四档像素预算依次为
  0.26/0.36/0.52/0.65 MP；普通模式每 5 秒为 10/15/20/30 点，角色参考模式为
  12/18/24/36 点。
  未指定 `seed` 时由 MiniMax H3 专用生成器在 Central 请求契约的
  `1..2^50` 范围内生成，不能复用上限更大的通用生成 seed。
- T2V 不接受图片；I2V 恰好 1 张；FLF2V 恰好 2 张有序首尾帧；REF2V 接受
  1–4 张有序角色参考图和可选的等长角色说明。
- I2V/FLF2V 固定使用 `aspect_ratio=source`，首帧通过分辨率计算节点按像素预算
  和 Div32 生成实际宽高，不映射到近似比例。FLF2V 首尾帧比例相对差异超过 1%
  时在入口和 Worker 双重拒绝；T2V/REF2V 继续使用固定 `aspect_ratio`。
- 服务端 `src/domain_config/minimax_h3.py` 是尺寸、帧数、费用、输入数量、用户附加
  模型 ID、默认强度和强度范围的事实源。Worker 再次拒绝未知模型、非法强度、采样器、
  timeline、本地路径和参考音视频覆盖。
- 输出为带音轨 MP4，并通过 `SaveImage` 产生 `extra_outputs.last_frame` 所需尾帧。
- 主 Bot 入口使用 `advanced_video_pro_fsm.py`，规范化提交由
  `advanced_video_pro_submission_service.py` 承接；菜单继续使用历史
  `menu.ltx_video` 配置键以兼容显隐与排序，但新提交只产生 T2V/I2V/FLF2V。
- QQCC 读取旧配置时将 `ltx_video` engine 迁移为内部 H3 engine 并清空旧 LTX
  LoRA；配置 API 保留空的版本化 `ai_video_addon_models` seam，当前不得提交覆盖。
- ComfyUI history 同时出现 VHS `gifs/videos` 与 `SaveImage.images` 时，四个 H3
  task type 必须优先把 MP4 物化为主结果；文件名含 `last_frame` 的 PNG 只进入
  `extra_outputs.last_frame`，不得覆盖主视频。

## Workflow 与模型

四份 API workflow 的事实源位于 `workers/comfy_agent/workflows/`，由
`scripts/build_minimax_h3_api_workflows.py` 确定性生成并同步进 baked RunPod runtime。
生成器校验 DaSiWa Civitai UI 源文件 SHA256 后才接受源资产。FL2VA 的
T2V/I2V/FLF2V 默认不加载用户附加模型。用户可同时选择最多 5 个互不重复的
`breasts`、`anus`、`vagina`、`sex_pose`、`penis`；Bot 提供逐项切换、全选和清空并
使用 catalog 默认强度，Web 提供多选、全选和清空，且每项强度可独立设为 `0.1..2.0`。
主协议为有序 `lora_items: [{name, strength}]`，旧 `lora_name/lora_strength` 仅保留
单模型兼容；Worker 按数组顺序串联全部用户 LoRA，再连接内置加速 LoRA。
`anus` 与 `vagina` 都加载 HMPussy 的 `vagassist` 与 `hmpussy` 双文件并保持
`1.0:0.35` 相对强度，并同时前置训练词 `Vagina, hmpussy`；`anus` 额外追加
`anus` 以区分语义。两份文件和两个训练触发词不可拆开。`penis` 使用
modelVersion `3218160` 的 `HMPenis_v2_e35.safetensors`，默认 `1.0`，按作者说明把
`HMPenis` 放在提示词开头。T2V/I2V 始终在可选附加模型之后串联官方
Lightx2v FL2VA 8-step v1.0 ComfyUI BF16 LoRA，强度 `0.75`，使用固定 revision 的
`MiniMaxH3TurboSampler`、8 steps、`simple` 与 video/audio shift `12/3`，让
加速采样按作者的混合比例 544p 训练 schedule 适配当前四档像素预算。固定
`1344x768`、video shift `6` 的 4-step 768p v1.0 不用于当前支持横竖屏和首帧比例的
公共 workflow。只有用户明确选择附加模型时，
Worker 才把 catalog 触发词放在提示词开头；未选择时不注入附加语义。HMBreasts
作者未发布硬性强度，当前 `1.0` 是与同作者静态结构 LoRA 对齐的候选基线，GPU
canary 必须覆盖叠加质量。FLF2V/REF2V 保持 25 steps、`res_multistep` 与 shift
`11/4` 基线；FLF2V 不加载 Lightx2v。REF2V 使用
不同的 REF2VA 底模，作者资产只声明 FL2VA，因此 fail closed，不加载这组 LoRA。
四模式都启用 KJNodes H3
memory-efficient SageAttention patch。

Web 与主 Bot 都按当前选择动态展示附加模型指南，并明确触发词由 Worker 自动添加。
Web 仍允许服务端合法范围 `0.1..2.0` 内的实验值，但用户指南只直接展示推荐值或
默认值，不使用“作者”来源措辞，也不展示 HMPussy 双文件的内部相对强度。
HMPussy 用户指南仅显示推荐 `1.0`；Worker 仍按 catalog 中的
`relative_strengths` 确定性加载两份 LoRA。HMNSFW V2 推荐 `0.5` 或更低，
HMBreasts/HMPenis 默认 `1.0` 并允许按效果调整。
选择 HMNSFW V2 时，Web/Bot 提示优先 I2V，并建议使用约 200–270 个英文单词覆盖
动作、视角、速度、景别、人物、画面位置、运动、表面状态和环境音；其它附加模型
分别提示其可控解剖属性与镜头方向。指南只帮助用户组织 prompt，不改变服务端强度
校验、模型选择或 Worker 的确定性触发词注入。

提示词优化注册 T2V/I2V/FLF2V 三个目标并统一映射到管理配置“高级图生视频pro”。
请求把当前 5/10/15 秒时长、0/1/2 个 owner-fenced 对象键和至多五个附加模型选择交给
服务端；优化器从同一 catalog 生成不含触发词的可信指南，客户端不能传规则正文。
优化结果只是一份 200–270 词英文 `positive_prompt`，不会提交视频；H3 生成 Worker
继续根据 `lora_items` 自动前置训练触发词。选择乳房模型时，提示模板才允许在证据
支持下使用 `nipples/areoles`，拼写 `areolas` 始终禁止。

REF2V 的原生 `MiniMaxH3ReferenceToVideo` 节点使用 ComfyUI V3 Autogrow 输入。
API JSON 必须以 `ref_images.ref_image_0` 至 `ref_images.ref_image_3` 连接 1–4 张
有序参考图；不得使用扁平 `ref_image_1` 等字段，否则节点执行阶段会收到非预期
关键字。业务提示词中的 `<Picture 1>` 仍保持 1-based，两种编号只属于不同层次。

模型包版本以 `scripts/prepare_minimax_h3_model_bundle.py` 为事实源，来自固定 revision 的
`Comfy-Org/MiniMax-H3` 官方转换。T2V/I2V/FLF2V 使用 pruned BF16 FL2VA，
REF2V 暂时保留 pruned INT8 ConvRot REF2VA；包内另含 NVFP4 AWQ Qwen3-VL text encoder
及 video/audio VAE；同一 manifest 还包含 Civitai modelVersion `3206518` 的
HMNSFW V2、`3216751` 的 HMBreasts、`3215304` 的两文件 HMPussy、`3218160` 的
HMPenis，以及 lightx2v 官方固定 revision 的 FL2VA 8-step v1.0 ComfyUI BF16 LoRA。
所有文件固定 SHA256 和字节数。
FL2VA BF16 与现有 FL2VA LoRA 链配套；REF2VA 没有作者兼容声明，继续禁止加载该
LoRA 链。模型只进入内容寻址仓库、
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

测试 Web 的本地执行候选为 `gpu-177-gpu1-minimax_h3_test`。它仍由同一个 fleet
helper 做单卡 takeover/recover，但运行身份固定为 `cloud-test`、测试 Central 和
`user-data-test`；不得让测试 Web 跨环境提交到正式 Central。候选与正式 LTX 共享物理
GPU，因此接入测试期间正式 LTX 会自然 drain 后停止，结束测试时显式 recover LTX。
H3 Worker 在 patch workflow 时把 backend task ID 规范化进视频和尾帧输出前缀，确保
持久化 Comfy workspace 中每次执行都有独立文件名；不能只依赖 VHS 递增 counter，避免
容器重建后旧中间 MP4 与 ffmpeg `-n` 冲突。

## 最小验证

```bash
python -m pytest -q tests/config/test_minimax_h3.py \
  tests/workers/test_minimax_h3_workflows.py \
  tests/ops/test_runpod_minimax_h3_profile.py \
  tests/scripts/test_prepare_minimax_h3_model_bundle.py
cd frontend && npm test -- --run src/composables/lab-workbench/useLabSubmitPayload.test.ts
```
