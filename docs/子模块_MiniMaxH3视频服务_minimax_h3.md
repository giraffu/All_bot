# MiniMax H3 视频服务

## 当前事实源

H3 只有四个公开任务类型：

- `minimax_h3_t2v`：文生视频；
- `minimax_h3_i2v`：首帧图生视频；
- `minimax_h3_flf2v`：首尾帧视频；
- `minimax_h3_ref2v`：参考图生视频。

四种模式共用 `src/domain_config/minimax_h3.py`、四份 API workflow 和
`workers/comfy_agent/workflow_task_patchers.py`。主模型只允许：

- `10eros_bf16`（默认）：
  `MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors`；
- `10eros_int8`：
  `MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors`。

兼容读取时，旧 `10eros` 迁移为 `10eros_bf16`，旧 `official` 和
`official_ref2v_turbo` 迁移为 `10eros_int8`。新请求不得继续写入这些旧值；未知值
fail closed。BF16 与 INT8 在四种模式中都使用相同的 10Eros Beta4 原生执行参数：
Euler、simple、8 steps、`shift_video=12`、`shift_audio=7`。workflow 不含旧官方
checkpoint 分支、LightX2V 加速节点或 `ManualSigmas` H3 依赖。

## 附加模型

唯一目录为 `MINIMAX_H3_ADDON_MODELS`，只保留四项，单次最多四项：

| 稳定 ID | 文件 | 默认强度 | 触发词 |
| --- | --- | ---: | --- |
| `deepthroat` | `MiniMaxH3/deepthroat_v02.safetensors` | 0.75 | 无 |
| `pov_missionary` | `MiniMaxH3/H3_Mis_Insrt_v07.safetensors` | 0.70 | 无 |
| `footjob` | `MiniMaxH3/H3_Footjob_TypeB_v1.safetensors` | 0.50 | `fj.` |
| `cumshot` | `MiniMaxH3/HMCumshot_V2.safetensors` | 0.90 | `hmcumshot3` |

四项均支持 T2V、I2V、FLF2V、REF2V。请求使用有序
`lora_items=[{name,strength}]`，禁止重复、未知 ID、任意物理路径或同时混用旧参数
格式。强度范围为 `0.1..2.0`。Worker 按顺序动态建立 `LoraLoaderModelOnly` 链；未选
LoRA 时不创建加载节点。

## 模型包

当前 bundle：`minimax_h3_runtime@2026-09-02-10eros-beta4-bf16-int8-addon4`。
模型缓存前缀为
`minimax_h3/2026-09-02-10eros-beta4-bf16-int8-addon4`，manifest 共九个文件：

1. 10Eros Beta4 BF16；
2. 10Eros Beta4 INT8 ConvRot；
3. Qwen3-VL 32B NVFP4/AWQ text encoder；
4. MiniMax H3 audio VAE；
5. MiniMax H3 video VAE；
6. Daring Deepthroat v0.2；
7. H3 POV Missionary v0.7；
8. H3 Footjobs Type B v1；
9. HMCumshot v0.5。

总字节数 `84,223,835,375`，准备脚本要求至少 90 GiB 空闲。每个文件都必须以
`size_bytes + sha256` 校验。10Eros 上游固定到 Hugging Face revision
`3c071106f5b62c02b3cb0b7d831083cdb582b289`；BF16 SHA-256 为
`bf34b4c9d2fa973ae84c480a1a5a04d2978958023bb6be7375b3b9e4818965e3`，INT8
SHA-256 为 `54d56b15c65923b54c9ca16b494dae641bfe9455cfcb1c19c49b1008e270bbc1`。

`scripts/prepare_minimax_h3_model_bundle.py` 负责下载、断点续传、校验和 manifest。
旧官方 checkpoints、LightX2V H3 accelerators 和其它 H3 LoRA 只列在
`OBSOLETE_FILES`，新 manifest 不引用它们；只有新 manifest 和 LAN canary 验证后才
允许从缓存清理旧文件。

## 输入和 workflow 契约

- T2V 不接收图片；
- I2V 接收一张首帧，画幅按首帧或显式合法比例归一；
- FLF2V 接收首帧和尾帧；
- REF2V 接收 1–4 张有序参考图，也可按现有契约接收参考视频/主角语音。

时长只允许 5/10/15 秒，帧数分别为 124/243/362，固定 24 fps。分辨率档位为
`preview|small|standard|hd`。REF2V 的图片是人物/外观/道具/风格参考，不是首帧；
I2V/FLF2V 的帧归属不能与 REF2V 混用。

四份 workflow 由 `scripts/build_minimax_h3_api_workflows.py` 生成。修改生成脚本后必须
重建 JSON，并通过 `tests/workers/test_minimax_h3_workflows.py` 验证四种模式、两种
精度、采样参数和 LoRA 链。不得手工维护与生成脚本不一致的 workflow。

## 管理后台与提交链

管理后台的 H3 主模型选项由服务端下发 `10eros_bf16`、`10eros_int8`，四种模式均可
选择。后台和 Web 的 LoRA 选项必须与领域目录完全一致，不能复制第二套物理路径目录。
旧保存值在读取时迁移，新保存值只能是当前两个主模型和四个 LoRA。

Bot、Web、QQCC、Gallery apply-context 和 History 必须持久化归一后的稳定 ID、顺序和
强度。Central 只接收领域参数；Worker 才把稳定 ID 映射为模型路径。Prompt Optimizer
不得输出模型名、LoRA 名、强度、采样器或触发词；触发词由领域/Worker 注入。

H3 成功 History 的 `extra_outputs._minimax_h3_context` 当前为 version 3，除既有模式、
时长、分辨率、比例与 LoRA 外，还必须写入已归一的 `main_model`。本地分析平台用该字段
显示与筛选 H3 主模型；version 1/2 的旧记录没有该字段，必须显示为“未记录”，不得按默认
BF16 回填或推测。

## 不可变发布和运维

H3 发布顺序固定为：

1. 从完整 Git SHA 构建 `minimax_h3` 不可变镜像，得到精确 digest；
2. 准备并上传九文件 manifest；
3. 只通过 `scripts/lan_aio_fleet_prod_ops.py` 对单个 H3 LAN slot 做 preflight、
   warm-cache 和 digest rollout；
4. LAN slot 接取真实正式 H3 任务并成功终态后，才更新正式管理后台/控制面的未来
   RunPod artifact 配置；
5. 现有 RunPod 不因这次 LAN 验证而重建、拉取或切换镜像；新建 H3 RunPod 只允许消费
   新 digest 和新 manifest。

H3 的 LAN AIO 和 RunPod 启动契约必须包含
`COMFY_EXTRA_ARGS=--enable-triton-backend`。镜像继续使用 CUDA 12.8 兼容的
`comfy-kitchen 0.2.31` pure-Python wheel，但 INT8 ConvRot 线性层必须通过 Triton
backend 执行；构建检查 `triton` backend 已注册 `int8_linear`，运行日志检查该 backend
未被 disabled。BF16 不依赖这条 INT8 kernel 路径。已有 H3 RunPod 如需应用该修复，只能
在任务自然空闲后做配置级滚动重启，不切换镜像、不复制源码、不删除 Pod；任一 Pod 验证
失败即停止后续滚动并保留其余实例。
配置级滚动统一走
`scripts/runpod_prod_ops.sh refresh-runtime-env --profile minimax_h3 --slot <NN>`；该命令只
允许更新白名单键 `COMFY_EXTRA_ARGS`，会合并保留 Pod 的全部既有环境变量，并要求更新前后
Pod ID 和镜像引用完全相同。RunPod 配置更新会重启容器并清除 `/workspace` 之外的容器盘
数据，因此模型和结果仍必须位于既有持久卷契约内。Dashboard autoscaler 必须把
`runpod_prod_worker_*` control reason 识别为 operator maintenance hold；自然排空、
配置更新和新 heartbeat 验证完成前不得自动 enable、restart 或 down 该 Pod。

生产 mutation 必须使用完整 SHA、digest-pinned artifact 和精确 manifest key。禁止
mutable tag、目标机 build、源码 bind mount、手工 Compose 或绕过 fleet helper。LAN
rollout 前必须确认 slot 自然空闲；不得中断正在执行的正式任务。

## 最小验证

```bash
python -m pytest -q \
  tests/config/test_minimax_h3.py \
  tests/workers/test_minimax_h3_workflows.py \
  tests/scripts/test_prepare_minimax_h3_model_bundle.py \
  tests/ops/test_runpod_minimax_h3_profile.py \
  tests/ops/test_lan_aio_prod.py
```

管理后台同时运行相关 dashboard Python tests、Vue tests 和 `vue-tsc --noEmit`。文档
变更运行 `python3 scripts/doc_quality_checker.py`。运行态 Pod 数、LAN current/cache、
一次性 canary task ID 和事故证据不写入本文。
