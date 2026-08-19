# 子模块：MiniMax H3 视频服务

## 能力与边界

`minimax_h3` 是独立 GPU profile，不是 LTX alias。用户只开放三个任务：
`minimax_h3_t2v`、`minimax_h3_i2v`、`minimax_h3_flf2v`。Web 使用一个“高级图生
视频pro”工作台切换三种模式，主 Bot 使用同一组模式。两端均可从
十三个本地 LoRA 中多选；默认全部关闭，Web 可逐项设置强度，Bot 使用目录默认强度。
QQCC 配置 Web 同样从这一领域目录下发 13 项，场景保存有序 `lora_items`；官方懒人
Bot、私有懒人 Bot、场景续链与示例生成都把相同稳定 ID 和强度提交到 I2V/FLF2V。
历史 `minimax_h3_ref2v` 类型与 workflow 仅用于读取旧任务和代码兼容，不进入 H3
Worker pool、RunPod/LAN 支持任务列表或新建入口。

Bot/Web 的终端用户界面只展示“效果增强”和用途标签，不展示 MiniMax H3、基础链、
checkpoint、LoRA 术语、作者资产名或物理文件名。Web 不渲染基础链说明；Bot 设置
摘要只显示启用数量。下文模型名、目录 ID、强度和文件路径均是内部运行契约，不是
用户文案；展示脱敏不得改变提交 payload 或 Worker 注入顺序。

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
- `src/domain_config/minimax_h3.py` 是时长、尺寸、帧数、费用、输入数量和公开 LoRA
  目录的事实源。新请求使用最多 13 个有序 `lora_items[{name,strength}]`，强度限定
  `0.1..2.0`且不得重复；空列表表示不加载附件。旧 `addon_models` 和
  `lora_name/lora_strength` 仅作有限兼容，不得与 `lora_items` 混用。客户端不能覆盖
  主模型、采样器、steps、timeline、本地路径或参考音视频。
- 输出为带音轨 MP4，并由 `SaveImage` 产生 `extra_outputs.last_frame`。
- ComfyUI history 同时包含视频和尾帧时，MP4 是主结果，名称含 `last_frame` 的 PNG
  只能进入 `extra_outputs.last_frame`。

## Gallery 与模板应用

- 只有 `minimax_h3_i2v` 与 `minimax_h3_flf2v` 可投稿；T2V、历史 REF2V 和
  QQCC 自生成结果不开放投稿。Web 与主 Bot 新生成的 I2V/FLF2V 都写入
  `allow_contribute=true`，模板派生结果固定为 `false`。
- 两种可投稿类型在 Gallery 统一显示为“高级图生视频pro”，筛选值
  `minimax_h3` 同时查询两类 History。点赞、点踩、收藏、评论、举报、关注、排行和
  提示词解锁继续复用 Gallery 通用能力。
- Web finalizer 与主 Bot 完成链路把模式、时长、`resolution_preset`、
  `aspect_ratio` 和有序 `lora_items` 写入版本 1 的 `_minimax_h3_context`。
  不迁移旧记录；缺少完整上下文的历史投稿仍可互动，但
  `template_apply_disabled_reason=minimax_h3_context_missing`。
- 一键应用不返回或复用原始 `input_file/input_files`。I2V 要求重新上传 1 张首帧，
  FLF2V 要求重新上传有序的 2 张首尾帧并在提交前校验比例差不超过 1%。原提示词、
  时长、档位、`source` 比例和有序附加模型全部锁定；成功提交携带
  `is_template=true` 与 `source_post_id` 后立即关闭模板会话。

## 提示词优化契约

新 Prompt Optimizer 任务使用三个 `profile@5` 与
`minimax_h3_10eros_naughtytimes@4`。输出不是旧的 200–270 词单段 caption，而是
MiniMax 官方 Base 顺序：`integrated_multimodal_description` →
`overall_soundscape` → `non_diegetic_music`。T2V 无对齐首行；I2V 必须先写官方
`<Picture 1>` 0.00 秒对齐句；FLF2V 必须先写 Picture 1/2、动态结束时间和正文实际
最终 Shot 编号的对齐句。第一镜头不得带时间，后续镜头必须按顺序编号且时间戳严格
早于视频时长。

Web 与 Bot 从 capability 选择 template v4；Web 提交时把管理端当前配置、原台词及
服务端检测的台词语言渲染成不可变 snapshot。检测以台词自身为准，不受中文或英文场景
叙述影响；Worker 要求输出保留匹配的 `<d>[Language] 原文</d>`，翻译、改写或漏写时
受控重试。保存过的旧单段 H3 scene config、没有对白语言占位符的旧官方配置，
以及仍声称 NaughtyTimes 固定加载的配置，对新任务自动回落到 built-in 默认值，
但历史任务继续读取自己原有的 snapshot 与旧 profile。Worker 在任何文本增量对用户
可见前复验结构、对齐和时长。本地 Optimizer 生成的是兼容官方 Base 的提示词，不调用
未开源的托管 H3-Context-IR，因此不宣称复现官方 Context-IR 的完整推理质量。

## 固定基础链与可选作者资产

T2V/I2V/FLF2V 的基础链只固定两个作者原始资产：

- 10Eros-Max Beta2 `10Eros_Max_h3_fl2va_beta2_pruned.safetensors`，revision
  `47aa7e38dc2aca9a1e71a5b01b7ffefd462b57b5`，40,222,933,592 bytes，SHA256
  `57da2b2a12b9efc89eeaa6d751e1ef46ef3e406ca227684c31848abc749f1b20`；
- LightX2V FL2VA 8-step v1.0 `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`，
  1,956,193,000 bytes，SHA256
  `2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e`；
- Comfy-Org 官方 Qwen3-VL NVFP4 AWQ encoder、FP16 video VAE 与 FP32 audio VAE。

十三个可选 LoRA 由同一目录管理：NaughtyTimes v2 R256（1.0）、HMNSFW AIO v2
（0.5）、H3 Motion Booster v2（0.7，触发词 `dynv2`）、Mystic XXX v2（0.75，
无触发词）、Breast Play & Jiggle v1（0.75）、HMInnie v1（0.8，触发词
`inniepussy`）、Deepthroat v0.2（0.75）、POV Missionary v0.7（0.7）、Footjobs
Type B v1（0.5，触发词 `fj.`）、HMBreasts（1.0）、VagAssist（1.0）、HMPussy v6
（0.35）与 HMPenis v2（1.0）。括号为 Bot 默认强度；Web 可在 `0.1..2.0` 内覆盖。
Breast Play 作者明确建议 `0.7..0.8`，Footjobs Type B 明确建议 `0.4..0.7` 且通常
从 `0.5` 开始；HMInnie、Deepthroat H3 v0.2 与 POV Missionary 未公开 LoRA strength
区间，因此其目录值是保守的系统初始值，必须由后续 GPU A/B 校准，不能称为作者推荐。
目录一项只映射一个物理
文件，避免同一 LoRA 以别名被重复加载。

HMInnie 的 `inniepussy` 替换提示词中的通用阴道名词，可与 HMPussy 叠加，但叠加不代表
已验证最优；Footjobs 只自动注入短触发词 `fj.`，不自动拼接作者给出的整段示例提示词。
Deepthroat v0.2 按作者说明以 24fps、guidance 4 训练并强调 15 秒连续性；当前系统固定
24fps，但公开 workflow guidance 为 1，因此只视为待 canary 候选。POV Missionary
作者仍标记为早期实验版。五个新模型在实机 canary 完成前均不得标记为已验证。

三个 workflow 使用同一基础顺序：`UNETLoader(10Eros Beta2) →
LoraLoaderModelOnly(LightX2V, 1.0) → [用户选中 LoRA 有序链] →
ModelAttentionBackend(comfy kitchen attention) → MiniMaxH3SigmaShift(12/3) →
ReservedVRAMSetter(2 GiB auto、3 GiB 上限) → MiniMaxH3ImageToVideo →
Euler/simple/8 steps`。LightX2V 同时覆盖 T2V、I2V 和 FLF2V，FLF2V 不再回退到
25 steps。输出继续解码 H3 原生同步音轨。

镜像不安装 ContextIR、SageAttention 或旧 `MiniMaxH3TurboSampler`；新模型包不包含
REF2VA 或 RedMix，但包含上述十三个可选 LoRA。旧 checkpoint、
blob 与 bundle 不删除，供回溯和回滚。10Eros BF16 主模型比 RedMix INT8 更占磁盘与加载
内存；8-step 只减少采样计算量，不消除模型加载和 CPU offload 成本。画质、峰值显存和
实际速度必须通过后续三模式 GPU canary 才能定论。

三份公开 API JSON 由 `scripts/build_minimax_h3_api_workflows.py` 确定性生成，并同步到
`workers/comfy_agent/workflows/` 与 baked RunPod runtime。历史 REF2V workflow 仅保留
解析能力，不进入新镜像 smoke、capability 或新提交入口。

## 模型包与镜像

`scripts/prepare_minimax_h3_model_bundle.py` 固定版本
`2026-08-19-10eros-beta2-addon13-lightx2v8-mystic-v2`、18 个文件的字节数与
SHA256，总计 69,631,057,639 bytes（64.85 GiB）。脚本复用已有内容寻址 blob，只把缺失
资产下载到临时文件；尺寸和 SHA256 均通过后才原子落盘。Civitai 附件下载需要通过
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
当前 RTX 5090 运行态同时禁用 DynamicVRAM 并启用 `--cache-none`：
前者避免 AIMDO 错误的 16 GiB 进程显存上限，后者在图执行期间尽快
释放已不再需要的大型节点输出，防止 32B 文本编码器与同机其它
GPU runtime 共同压满宿主机 RAM。

## 测试 Worker 与正式 GPU 边界

H3 测试 Worker 是测试云主机上的专用 `worker-agent`，与 `worker-relay` 一起运行，
只连接 test Central 和测试存储，并只声明 T2V/I2V/FLF2V 三种公开类型。普通“启动
H3 测试 Worker”不得选择 LAN `*_test` 候选、接管 LAN slot 或创建 cloud-test
RunPod；LAN/RunPod runtime 在该语境中都保持正式 Worker 身份。测试 agent 可以经
受限私网或测试主机 loopback 传输调用已经运行的 H3 ComfyUI，但不得启停、重启、
切换或重新标记该正式 runtime。

不提交任务的运行验收包括：relay/agent 容器 running、restart count 为 0、OCI
revision 匹配完整 main SHA、ComfyUI `/system_stats` 与 `/queue` 可达，以及 test
Central `/system/workers` 中目标 agent 为 `enabled`、`idle` 且 profile/types 精确。
这只能证明测试 Worker 可接单，不等于 GPU artifact canary 已通过。

验收至少串行提交 T2V、I2V、FLF2V 各一条 5 秒 preview，逐条检查：Central task type、
Worker agent、MP4、24fps、音轨、尾帧、显存/OOM/Xid；还必须对全部视频帧执行亮度/
黑帧检查，不能仅因容器成功、MP4 可探测或存在尾帧就宣布 canary 通过。
`scripts/minimax_h3_prod_smoke.py` 使用 FFmpeg `signalstats` 扫描全部帧；所有帧的
`YAVG <= 20` 且 `YMAX <= 32` 时按全黑失败，缺少亮度元数据同样 fail closed。H3 profile 保持
`reset_comfy_memory_before_task`、`--fast-disk --disable-pinned-memory` 和
`--disable-dynamic-vram`。H3 使用 ComfyUI 标准显存管理；禁止启用会在当前
PyTorch/RTX 5090 组合上设置半卡进程上限的 AIMDO allocator。运行证据写 XDG
history/evidence，不回写本文。

## 最小验证

```bash
.venv/bin/python -m pytest -q tests/config/test_minimax_h3.py \
  tests/services/test_minimax_h3_history_context_service.py \
  tests/web_api/test_gallery_apply_context.py \
  tests/workers/test_minimax_h3_workflows.py \
  tests/ops/test_runpod_minimax_h3_profile.py \
  tests/scripts/test_prepare_minimax_h3_model_bundle.py
cd frontend && npm test -- --run \
  src/composables/lab-workbench/useLabSubmitPayload.test.ts \
  src/composables/lab-workbench/usePromptOptimizer.test.ts \
  src/views/CustomFeatures.test.ts \
  src/components/template-apply/TemplateAdvancedVideoProPanel.test.ts
```
