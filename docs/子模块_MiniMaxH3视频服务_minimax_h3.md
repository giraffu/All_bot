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
  空的历史 `addon_models`、`lora_items`、`lora_name`、`lora_strength` 占位值继续兼容；
  任一非空值明确拒绝。客户端不能覆盖模型、采样器、steps、timeline、本地路径或参考音视频。
- 输出为带音轨 MP4，并由 `SaveImage` 产生 `extra_outputs.last_frame`。
- ComfyUI history 同时包含视频和尾帧时，MP4 是主结果，名称含 `last_frame` 的 PNG
  只能进入 `extra_outputs.last_frame`。

## 提示词优化契约

新 Prompt Optimizer 任务使用三个 `profile@3` 与
`minimax_h3_10eros_naughtytimes@2`。输出不是旧的 200–270 词单段 caption，而是
MiniMax 官方 Base 顺序：`integrated_multimodal_description` →
`overall_soundscape` → `non_diegetic_music`。T2V 无对齐首行；I2V 必须先写官方
`<Picture 1>` 0.00 秒对齐句；FLF2V 必须先写 Picture 1/2、动态结束时间和正文实际
最终 Shot 编号的对齐句。第一镜头不得带时间，后续镜头必须按顺序编号且时间戳严格
早于视频时长。

Web 与 Bot 从 capability 选择 template v2；Web 提交时把管理端当前配置渲染成不可变
snapshot。保存过的旧单段 H3 scene config 对新任务自动回落到官方 built-in 默认值，
但历史任务继续读取自己原有的 snapshot 与旧 profile。Worker 在任何文本增量对用户
可见前复验结构、对齐和时长。本地 Optimizer 生成的是兼容官方 Base 的提示词，不调用
未开源的托管 H3-Context-IR，因此不宣称复现官方 Context-IR 的完整推理质量。

## 固定作者资产栈

T2V/I2V/FLF2V 使用可分别升级、但对客户端完全固定的作者原始资产：

- 10Eros-Max Beta2 `10Eros_Max_h3_fl2va_beta2_pruned.safetensors`，revision
  `47aa7e38dc2aca9a1e71a5b01b7ffefd462b57b5`，40,222,933,592 bytes，SHA256
  `57da2b2a12b9efc89eeaa6d751e1ef46ef3e406ca227684c31848abc749f1b20`；
- LightX2V FL2VA 8-step v1.0 `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`，
  1,956,193,000 bytes，SHA256
  `2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e`；
- NaughtyTimes v2 pruned R256 `NaughtyTimes_pruned_r256_v2.safetensors`，Civitai
  modelVersion `3212436` / file `3094173`，2,242,444,272 bytes，SHA256
  `947efec5a357505bb93bdc1b050d33786ec150aa1c85f24337f0d59f39aaf31a`；
- Comfy-Org 官方 Qwen3-VL NVFP4 AWQ encoder、FP16 video VAE 与 FP32 audio VAE。

三个 workflow 使用同一固定顺序：`UNETLoader(10Eros Beta2) →
LoraLoaderModelOnly(LightX2V, 1.0) → LoraLoaderModelOnly(NaughtyTimes, 1.0) →
ModelAttentionBackend(comfy kitchen attention) → MiniMaxH3SigmaShift(12/3) →
ReservedVRAMSetter(2 GiB auto、3 GiB 上限) → MiniMaxH3ImageToVideo →
Euler/simple/8 steps`。LightX2V 同时覆盖 T2V、I2V 和 FLF2V，FLF2V 不再回退到
25 steps。输出继续解码 H3 原生同步音轨。

镜像不安装 ContextIR、SageAttention 或旧 `MiniMaxH3TurboSampler`；新模型包也不包含
REF2VA、HMNSFW、HMBreasts、HMPussy、HMPenis、RedMix 或其它历史附件。旧 checkpoint、
blob 与 bundle 不删除，供回溯和回滚。10Eros BF16 主模型比 RedMix INT8 更占磁盘与加载
内存；8-step 只减少采样计算量，不消除模型加载和 CPU offload 成本。画质、峰值显存和
实际速度必须通过后续三模式 GPU canary 才能定论。

三份公开 API JSON 由 `scripts/build_minimax_h3_api_workflows.py` 确定性生成，并同步到
`workers/comfy_agent/workflows/` 与 baked RunPod runtime。历史 REF2V workflow 仅保留
解析能力，不进入新镜像 smoke、capability 或新提交入口。

## 模型包与镜像

`scripts/prepare_minimax_h3_model_bundle.py` 固定版本
`2026-08-16-10eros-beta2-naughtytimes-v2-r256-lightx2v8-v1`、六个文件的字节数与
SHA256，总计 65,921,776,719 bytes（61.39 GiB）。脚本复用已有内容寻址 blob，只把缺失
资产下载到临时文件；尺寸和 SHA256 均通过后才原子落盘。NaughtyTimes 下载需要通过
`CIVITAI_API_TOKEN` 鉴权；Token 只发送给 Civitai API host，不转发到重定向后的对象存储。模型只进入
`/srv/allbot/model-registry`，不得进入 Git 或 OCI 镜像；本次准备不自动上传 LAN、R2 或
任何远端 registry。

作者发布新版本时保持 workflow 拓扑不变，只更新准备脚本与 bundle 中的 repository
revision、filename/modelVersion/fileId、SHA256 和 size。新版本必须使用新 bundle version，
不能覆盖旧 manifest；完整校验、focused tests 与 GPU canary 通过后才可单独更新部署指针。

镜像模块仍为 `minimax_h3`，基础镜像从 LAN registry 的精确 digest 读取，不依赖
GHCR 或构建时访问 Docker Hub；同时固定支持 Comfy Kitchen Attention 的 ComfyUI、
DaSiWa Nodes、KJNodes、VHS 与 `ComfyUI-ReservedVRAM` 源码 revision，不安装
`ComfyUI-MiniMax-ContextIR`、`ComfyUI-MiniMax-H3-Turbo`，也不编译或在启动时依赖
SageAttention。ComfyUI 从镜像内 `/opt/ComfyUI` 启动，模型卷
挂载到 `/opt/ComfyUI/models`；禁止源码 bind mount 或在目标机 build。

## LAN 测试切换

测试候选为 `gpu-177-gpu1-minimax_h3_test`，与
`gpu-177-gpu1-ltx_unified` 共用 `gpu-177:gpu1` 和 8191。只能通过
`scripts/lan_aio_fleet_prod_ops.py` 读取实时 ledger、确认队列空闲、warm-cache 并做
单卡 takeover/recover。候选身份固定为 `cloud-test`，只能连接测试 Central 和
`user-data-test`。测试期间正式 LTX 会在自然 drain 后停止；结束时显式 recover。

验收至少串行提交 T2V、I2V、FLF2V 各一条 5 秒 preview，逐条检查：Central task type、
Worker agent、MP4、24fps、音轨、尾帧、显存/OOM/Xid；还必须对全部视频帧执行亮度/
黑帧检查，不能仅因容器成功、MP4 可探测或存在尾帧就宣布 canary 通过。
`scripts/minimax_h3_prod_smoke.py` 使用 FFmpeg `signalstats` 扫描全部帧；所有帧的
`YAVG <= 20` 且 `YMAX <= 32` 时按全黑失败，缺少亮度元数据同样 fail closed。H3 profile 保持
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
