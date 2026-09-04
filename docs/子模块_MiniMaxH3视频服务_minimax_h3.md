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
- REF2V 接收 1–4 张有序参考图，也可各接收一个参考视频和主角参考语音。Web
  上传的参考视频最长 40 秒、最大 40 MB；服务端再次探测时长并拒绝无法读取或超限
  文件。上传后选择 `reference_video_duration=3|5|10|15`，原片时长必须不短于所选
  片段；Worker 只截取视频开头对应秒数作为动作和场景参考，用户可在提示词中使用
  `<Video 1>` 说明其用途。旧请求未携带该字段时兼容为 5 秒。

时长只允许 5/10/15 秒，帧数分别为 124/243/362，固定 24 fps。分辨率档位为
`preview|small|standard|hd`。REF2V 的图片是人物/外观/道具/风格参考，不是首帧；
I2V/FLF2V 的帧归属不能与 REF2V 混用。

### 默认灵石价格

普通 T2V/I2V/FLF2V 共用下表；REF2V 使用独立基础价。参考音频在 REF2V 基础价上
乘 `1.10`。参考视频按实际选择的开头片段长度加价：3 秒 `×1.40`、5 秒
`×1.60`、10 秒 `×2.20`、15 秒 `×2.80`；5 秒仍保持原有价格锚点。音频与视频
同时使用时两个系数连乘，最终统一向上取整。后台显式价格覆盖仍优先于默认价。

| 模式 | 时长 | 极速 | 清晰 | 标准 | 高清 |
| --- | ---: | ---: | ---: | ---: | ---: |
| T2V/I2V/FLF2V | 5 秒 | 10 | 11 | 15 | 17 |
| T2V/I2V/FLF2V | 10 秒 | 14 | 21 | 36 | 47 |
| T2V/I2V/FLF2V | 15 秒 | 23 | 36 | 63 | 89 |
| REF2V 基础价 | 5 秒 | 11 | 13 | 17 | 22 |
| REF2V 基础价 | 10 秒 | 17 | 24 | 37 | 50 |
| REF2V 基础价 | 15 秒 | 26 | 38 | 64 | 91 |

商品目录同时使用 `reference_video=yes|no` 和
`reference_video_duration=none|3|5|10|15` 区分覆盖价；服务端权威 matcher、Web
展示价与领域默认价必须使用同一档位，不能仅在前端估价。

### 扩展生成执行语义

“直接扩展”的用户态任务身份继续保持 `minimax_h3_ref2v`，因此 History 类型、
价格、退款键、Gallery 分类和扩展链关系不变；执行层通过服务端可信字段
`minimax_h3_execution_task_type=minimax_h3_i2v` 选择 I2V workflow，并把父段
`extra_outputs.last_frame.path` 作为唯一首帧输入。I2V 强制使用 `aspect_ratio=source`，
提示词、主模型、LoRA、时长和清晰度档位继续透传。普通 REF2V 生成仍按参考图、
参考视频和参考音频契约执行，不受该条件映射影响。

Web 客户端不得直接提交内部执行类型；扩展服务在校验父记录归属、尾帧存在和链关系
后注入。主 Bot 只下载父段尾帧，不再下载最后五秒视频，也不允许在直接扩展中追加
参考图、参考音频或参考视频。Worker 最终接收 `minimax_h3_i2v`，因此现有 I2V workflow 的
`first_frame` 是生成事实源；公开任务类型仍用于计费和结果持久化。

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
时长、分辨率、比例与 LoRA 外，还必须写入已归一的 `main_model`；使用参考视频的新任务
另写可选 `reference_video_duration` 供审计。本地分析平台用该字段
显示与筛选 H3 主模型；version 1/2 的旧记录没有该字段，必须显示为“未记录”，不得按默认
BF16 回填或推测。

本地分析平台必须把四种公开任务类型全部纳入生成消费白名单，同时保留模式级 History
和趋势；提示词词元/模板候选把四种模式归并为统一的“高级图生视频 Pro”scope，并从
`_minimax_h3_context.lora_items` 读取附加模型筛选，不从提示词正文推测模型。

管理后台历史页不能只读 `History.input_file`：REF2V 参考音频从已校验的
`_minimax_h3_context.reference_audio` 生成 typed `input_media`，扩展段的实际生成图片
输入是父段尾帧。尾帧锚定扩展会在 version 3 上可选记录 `execution_mode=i2v`，后台据此
标记“上一段尾帧”和“父段视频”，同时根据 `prev_task_id` 保留父段视频的链路入口。
父段视频在管理员点击时才通过 Dashboard 历史媒体路由解析，列表不预加载原视频。

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
