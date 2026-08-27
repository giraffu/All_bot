# 子模块：MiniMax H3 视频服务

## 能力与边界

`minimax_h3` 是独立 GPU profile，不是 LTX alias。执行面支持四个任务：
`minimax_h3_t2v`、`minimax_h3_i2v`、`minimax_h3_flf2v` 和
`minimax_h3_ref2v`。测试 Web 与主 Bot 在同一“高级图生视频pro”工作台切换四种模式。
终端用户只选择模式、时长、清晰度和适用模式的比例，不再选择主模型、附加模型或
强度。Dashboard“入口控制”的独立“Pro 模型预设”子页按四种模式维护主模型与最多
十三个附加模型，并逐项保存 `0.1..2.0` 强度；Web 与主 Bot 子页只维护入口/菜单开关。
Web 和主 Bot 的新提交都由服务端读取并覆盖客户端模型字段，精确使用后台保存的附加
模型强度。其中十六项支持全部模式，原生 REF2VA Motion v0.2 只允许 REF2V，
VBVR H3 v1 只允许 T2V/I2V。
QQCC 配置 Web 同样从这一领域目录下发 18 项及其模式范围，场景保存最多 13 个有序 `lora_items`；官方懒人
Bot、私有懒人 Bot、场景续链与示例生成都把相同稳定 ID 和强度提交到 I2V/FLF2V。
REF2V 只接受有序参考图片，不接受参考视频或参考音频。测试 Web/主 Bot 限制 1–4 张；
官方 QQCC 固定 1 张用户主体图加 1–4 张管理员参考图；Worker 防御上限为 5 张。私有
QQCC Bot 过滤 REF2V 场景并拒绝已失效 callback。

Bot/Web 的终端用户界面只展示“效果增强”和用途标签，不展示 MiniMax H3、基础链、
checkpoint、LoRA 术语、作者资产名或物理文件名。Web 不渲染基础链说明；Bot 设置
摘要只显示启用数量。下文模型名、目录 ID、强度和文件路径均是内部运行契约，不是
用户文案；展示脱敏不得改变提交 payload 或 Worker 注入顺序。

Web 能力由发布配置 `enable_minimax_h3` 控制；普通导航由 Dashboard 的 Web
`minimax_h3` 入口开关控制，修仙市集类型筛选另由 Gallery `minimax_h3` 入口开关
独立控制。Web 启动时从公开只读接口 `/api/app/entry-visibility` 加载这些安全布尔值，
Dashboard 通过认证接口 `/api/entry-visibility` 写入
`feature_entry_visibility_config:v1`，同一配置还保存四种 Pro 模式的系统模型预设，无需
重新发布代码；公开接口只返回安全布尔开关，不下发内部模型配置。入口读取失败时沿用
Pages 发布配置，模型预设读取失败则服务端拒绝新 Pro 会话或提交，不能回退客户端选择。
REF2V 子能力由 `enable_minimax_h3_ref2v` 控制。后端分别由
`MINIMAX_H3_BACKEND_ENABLED` 和
`MINIMAX_H3_REF2V_ENABLED` 控制。入口隐藏不删除已有投稿，也不阻止作品详情、
模板深链或 `/advanced_video_pro` 命令测试。
REF2V 的“从人物库选择”还同时要求人物能力 `enable_character_assets` 与 Dashboard
Web“人物角色图”入口开关 `character_assets` 均开启；管理员关闭人物角色图入口后，
Web 刷新并读取最新公开开关时不再渲染人物图库选择器，临时上传参考图仍可使用。
提示词优化另由 `MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED` 控制。测试与正式 Dashboard
可分别维护共享场景配置 `minimax_h3`。该开关只控制 Web H3 优化能力；主 Bot
新 Pro 会话不展示优化或生成确认入口，接收提示词后直接生成。

## 请求契约

- 公共字段为非空 `prompt`、`duration=5|10|15`、
  `resolution_preset=preview|small|standard|hd` 和可选 `seed`。普通模式按
  `5/10/15` 秒分别使用完整四档价格矩阵：`10/11/15/17`、
  `14/17/27/33`、`19/27/42/59`；该公开矩阵由上一版价格统一乘以
  `1.1` 后向上取整，不再用 5 秒基础价线性倍乘。
  主 Bot 的当前设置摘要、时长按钮和画质按钮通过
  `get_minimax_h3_cost` 展示选中组合的预计灵石消耗，但扣费仍由 Task Core 以服务端
  价格为准。
- `main_model` 通用值为 `10eros|official`，REF2V 额外允许
  `official_ref2v_turbo`（用户文案“官方 REF2V 极速”），缺失时为 `10eros`。
  `official_ref2v_turbo` 用于其它模式时在领域层和 Worker 层都 fail closed；未知值
  同样拒绝。
- T2V 不接受图片；I2V 恰好一张首帧；FLF2V 恰好两张有序首尾帧。
- REF2V 使用固定画幅。`<Picture N>` 永远按图片数组顺序编号，Worker 不重排。
  REF2V 按 `5/10/15` 秒分别使用完整四档价格矩阵：`11/13/17/22`、
  `17/24/37/50`、`26/38/64/91`。上一版矩阵来自 5 秒 GPU/灵石基准的整数价格，
  普通模式应用 `1.05`、REF2V 应用 `1.15` 系数后向上取整；当前公开价格再统一
  应用 `1.1` 系数并向上取整。
- Web REF2V 使用有序 `reference_refs`。当前用户从私人人物中逐张选择 ready 子图，
  同一人物可选择多个不同视图，也可与临时上传混排：

  ```json
  [
    {"source":"private_character_view","character_id":"...","view_type":"face_front"},
    {"source":"upload","object_key":"..."}
  ]
  ```

  `reference_refs` 只允许 1–4 项且与旧 `images` 互斥；旧纯上传 `images` 继续兼容。
  I2V/FLF2V 不接受人物素材引用。服务端在扣费前按顺序解析 owner、moderation、
  人物和子图状态、对象存在性/20 MB 上限及重复项，并生成最终
  `images` 与 `reference_descriptions`。客户端不得提交人物 object key 或人物描述。
  `character-asset-mosaic-v1` 只用于人物库完整资产与预览，不能作为 H3 输入；这是为了
  避免模型把接触表复刻成分屏、网格或重复人物。
  对人物子图，服务端还会按 `character_id` 分组并注入强制 Picture-to-target 绑定：同一
  人物的多个 `<Picture N>` 只描述目标视频中的同一个实例，参考图本身、比较视图、接触
  表、分屏和重复身体不得进入输出。用户无需在提示词中手写内部 Picture 编号；Prompt
  Optimizer 使用同一绑定。
  Prompt Optimizer 复用相同解析器，因此优化和生成的 `<Picture N>` 顺序一致；最终
  生成会再次解析，优化后被停用或失效的人物在扣费前拒绝。
- I2V/FLF2V 固定 `aspect_ratio=source`，按首帧像素预算与 Div32 计算尺寸。FLF2V
  首尾帧比例差异超过 1% 时由入口和 Worker 双重拒绝。
- `src/domain_config/minimax_h3.py` 是时长、尺寸、帧数、费用、输入数量和内部附加模型
  目录的事实源。服务端预设生成最多 13 个有序 `lora_items[{name,strength}]`，强度限定
  `0.1..2.0`且不得重复；空列表表示不加载附件。旧 `addon_models` 和
  `lora_name/lora_strength` 仅作有限兼容，不得与 `lora_items` 混用。客户端不能覆盖
  管理端预设的主模型、附加模型、采样器、steps、timeline、本地路径或参考音视频。
- 输出为带音轨 MP4，并由 `SaveImage` 产生 `extra_outputs.last_frame`。
- ComfyUI history 同时包含视频和尾帧时，MP4 是主结果，名称含 `last_frame` 的 PNG
  只能进入 `extra_outputs.last_frame`。

## Gallery 与模板应用

- 只有 `minimax_h3_i2v` 与 `minimax_h3_flf2v` 可投稿；T2V、REF2V 和
  QQCC 自生成结果不开放投稿。Web 与主 Bot 新生成的 I2V/FLF2V 都写入
  `allow_contribute=true`，模板派生结果固定为 `false`。
- 两种可投稿类型在 Gallery 统一显示为“高级图生视频pro”，筛选值
  `minimax_h3` 同时查询两类 History。点赞、点踩、收藏、评论、举报、关注、排行和
  提示词解锁继续复用 Gallery 通用能力。
- Web finalizer 与主 Bot 完成链路把模式、时长、`resolution_preset`、
  `aspect_ratio` 和有序 `lora_items` 写入版本 1 的 `_minimax_h3_context`。
  不迁移旧记录；缺少完整上下文的历史投稿仍可互动，但
  `template_apply_disabled_reason=minimax_h3_context_missing`。
- Dashboard 历史生成筛选把 H3 归为两个入口：普通链的 T2V/I2V/FLF2V 合并为
  “高级图生视频pro · 图生视频”，REF2V 独立为“高级图生视频pro · 参考图生视频”；
  列表行仍按四个真实 `History.type` 显示具体子模式，筛选不得改写持久类型。
- 一键应用不返回或复用原始 `input_file/input_files`。I2V 要求重新上传 1 张首帧，
  FLF2V 要求重新上传有序的 2 张首尾帧并在提交前校验比例差不超过 1%。原提示词、
  时长、档位和 `source` 比例继续锁定；历史上下文中的附加模型只用于记录与展示兼容，
  新模板任务同样使用当前 Dashboard 系统模型预设。成功提交携带
  `is_template=true` 与 `source_post_id` 后立即关闭模板会话。

## 提示词优化契约

新 Prompt Optimizer 任务使用三个 `profile@5` 与
`minimax_h3_10eros_naughtytimes@5`。输出不是旧的 200–270 词单段 caption，而是
MiniMax 官方 Base 顺序：`integrated_multimodal_description` →
`overall_soundscape` → `non_diegetic_music`。T2V 无对齐首行；I2V 必须先写官方
`<Picture 1>` 0.00 秒对齐句；FLF2V 必须先写 Picture 1/2、动态结束时间和正文实际
最终 Shot 编号的对齐句。第一镜头不得带时间，后续镜头必须按顺序编号且时间戳严格
早于视频时长。

Web 从 capability 选择 template v5；Web 提交时把管理端当前配置、原台词及
服务端检测的台词语言渲染成不可变 snapshot。检测以台词自身为准，不受中文或英文场景
叙述影响；Worker 要求输出保留匹配的 `<d>[Language] 原文</d>`，翻译、改写或漏写时
受控重试。保存过的旧单段 H3 scene config、没有对白语言占位符的旧官方配置，
以及仍声称 NaughtyTimes 固定加载的配置，对新任务自动回落到 built-in 默认值，
但历史任务继续读取自己原有的 snapshot 与旧 profile。Worker 在任何文本增量对用户
可见前复验结构、对齐和时长。本地 Optimizer 生成的是兼容官方 Base 的提示词，不调用
未开源的托管 H3-Context-IR，因此不宣称复现官方 Context-IR 的完整推理质量。
主 Bot 新 Pro 会话不调用这些 profile/template；历史已提交的 Bot draft 仍可用自身冻结
snapshot 完成续接。

REF2V 使用 `minimax_h3_ref2v_prompt@1..4` 与 `minimax_h3_ref2v@1`。媒体角色严格为
`reference_image_1..4`，按 `<Picture N>` 和六段式参考描述组织完整提示词；QQCC
管理员固定场景提示词不经过用户侧优化。

Web 的人物库选择器只在 REF2V 显示。每个人物只提供一张完整合成素材图，可与上传
混用，统一托盘最多四张并支持拖动排序。合成图包含同一人物的全部 ready 子图，
Optimizer 和最终生成都把它作为一个 `<Picture N>`，描述明确要求只提取身份、身体、
服装、局部、配饰和物件证据，不复现拼贴构图。私人人物入口由独立人物开关控制，
显式局部子图另有 kill switch；生产两项默认关闭。

## 可选主模型、固定基础链与作者资产

`main_model=10eros` 保留现有默认链。`main_model=official` 与
`main_model=official_ref2v_turbo` 在 Worker patcher 中同时切换 checkpoint 和
模式专属执行 profile，不能只替换 `UNETLoader`。官方
checkpoint 使用 Comfy-Org 推荐的裁剪 INT8 ConvRot 版本：

- T2V/I2V/FLF2V：`diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors`，
  20,970,379,616 bytes，SHA256
  `e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a`；
- REF2V：`diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors`，
  20,970,379,616 bytes，SHA256
  `9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779`。

两份文件均固定 Comfy-Org/MiniMax-H3 revision
`4cc1d817b6184899b41293954329f576cb5ae86b`。官方 FL2VA 使用
LightX2V + Euler/simple/8-step；官方 REF2VA 高保真使用 `ref_image_size=max`、
sigma shift `12/3`、`res_multistep` 与 `BasicScheduler(simple, 20 steps)`。`max` 保留最多 2048px
短边的参考图 token 以提高身份保真，但会增加速度与显存成本。用户不能覆盖
checkpoint、采样器、scheduler、sigma、steps 或参考图缩放策略。

四种模式的 `10eros` 默认基础链统一使用一个作者原始资产：

- 10Eros-Max TURBO hybrid Beta3
  `10Eros_Max_h3_TURBO-hybrid_beta3.safetensors`，revision
  `47be06381f1a558f5fbd96e94d808d61fb164006`，40,228,492,688 bytes，SHA256
  `ea0df6670a84dfe594fe12c1202dfd82a497dbf2a75d6f06279a6b6993ab64b2`；
- LightX2V FL2VA 8-step v1.0 `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`
  仍保留给 `official` FL2VA，
  1,956,193,000 bytes，SHA256
  `2339acdf19bfe123f46b971ea35d367a84adb85de43627e1eceafa5a5b2b111e`；
- LightX2V Ref2VA 4-step v0.1
  `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` 只供
  `official_ref2v_turbo`，revision `ec01fa4c86263832faa0bd1d6d8f36a281eaabb2`，
  1,956,193,000 bytes，SHA256
  `5b9ab5ade15d0775676d01a907268a69a1468dc6033b3b0d3ded5502f3ebb84c`；
- Comfy-Org 官方 Qwen3-VL NVFP4 AWQ encoder、FP16 video VAE 与 FP32 audio VAE。

十八个可选 LoRA 由同一目录管理：NaughtyTimes v2 R256（1.0）、HMNSFW AIO v2.5
（0.5）、H3 Motion Booster v2（0.7，触发词 `dynv2`）、原生 REF2VA Motion v0.2
（0.7，触发词 `dynv2`，仅 REF2V）、VBVR H3 v1（1.0，仅 T2V/I2V）、
Mystic XXX v4（1.0，无触发词）、Breast Play & Jiggle v1（0.75）、HMInnie v1（0.8，触发词
`inniepussy`）、Deepthroat v0.2（0.75）、POV Missionary v0.7（0.7）、Footjobs
Type B v1（0.5，触发词 `fj.`）、HMBreasts（1.0）、VagAssist（1.0）、HMPussy v6
（0.35）、HMPenis v2.0（1.0，触发词 `HMPenis`）、HMCumshot v0.5（0.9，触发词
`hmcumshot3`）、HMPussy V1 Stills（0.35，触发词 `pussy`）与 Better Titfuck v0.5
（0.75，触发词 `titjob`）。括号为后台首次选择时的目录初始强度；Dashboard 可在
`0.1..2.0` 内逐项覆盖，保存后 Web 与主 Bot 统一使用该值。
Motion Booster 链接的 V0.2（modelVersion `3228867`）与既有正式资产 SHA256 完全一致，
因此保留稳定 ID 和原文件，不重复注册；HMPenis 稳定 ID 原位升级到 modelVersion
`3247473`，旧场景无需迁移。
VBVR H3 v1 使用 modelVersion `3220766`、file `3102749`，文件
`VBVR_H3_attn_only.safetensors` 为 32,826,752 bytes，SHA256
`372597997f646301dea204bf00e899b0f470254d7b9ac345e7b7417cc2140b34`。
作者将其定位为提示词遵循、时序一致性与动作精度辅助，并明确以 `1.0` 使用；H3
版本只声明训练 T2V/I2V，因此系统只在这两种模式下发，不把未验证的 FLF2V/REF2V
当作兼容模式。它没有触发词，且不替代 Prompt Optimizer。
HMNSFW AIO 保留稳定 ID `sex_pose`，原位升级到 v2.5 modelVersion `3268303`、
file `3152083`；文件 `HMNSFW-AIO-V2.5.safetensors` 为 86,040,232 bytes，SHA256
`a07732a84fd733085eb5d910f602f918fa7a3658117116927e4329f5951a9d2d`。作者建议
`0.5..0.9`，目录继续以 `0.5` 作为新选择初始值；v2.5 未声明旧版 `hmmotion`
触发词，因此不再自动注入，已有场景显式保存的强度保持不变。
Mystic XXX 保留稳定 ID `mystic_xxx`，原位升级到 v4 modelVersion `3266628`、
file `3150341`；文件 `MysticXXX_MMH3-V4.safetensors` 为 155,095,800 bytes，
SHA256 `fc3e856d14c6c19557c888f48662d591e4794e281233ec0d987be5003068afba`。
作者将 `1.0` 作为推荐起点，因此新选择默认改为 `1.0`，已有场景显式保存的强度不变。
原生 REF2VA Motion v0.2 使用 modelVersion `3246346`、file `3129119`，文件
`ref2VA_Motion_v2.safetensors` 为 155,110,288 bytes，SHA256
`b48cf96ebb14985789528449fe61985babf786feb658740a82a88ac685167fd9`。作者将它定位为
独立的 Ref2VA 人物一致性变体而不是普通 V2 的替代品，并提示画质与稳定性存在取舍；因此
保留原 `motion_booster`，新增 `motion_booster_ref2va` 且只允许 REF2V。公开强度未给出，
`0.7` 是与普通 V2 对齐的保守系统初始值，技术 canary 前不得标记为已验证。
Breast Play 作者明确建议 `0.7..0.8`，Footjobs Type B 明确建议 `0.4..0.7` 且通常
从 `0.5` 开始；HMInnie、Deepthroat H3 v0.2 与 POV Missionary 未公开 LoRA strength
区间，因此其目录值是保守的系统初始值，必须由后续 GPU A/B 校准，不能称为作者推荐。
HMPussy V1 Stills 使用 modelVersion `3252213`、file `3135252`，是同模型页的从头重建
静帧候选，不替换既有仍覆盖 motion 的 HMPussy v6。Better Titfuck v0.5 使用
modelVersion `3252313`、file `3135351`；作者说明可用于 T2V/REF2V，但没有训练音频，
并已知在乳房间没有目标物时可能产生胸沟变色或形变，REF2V 可缓解但不能视为系统
canary 结论。两项都没有公开 LoRA strength 建议，`0.35/0.75` 只是保守系统初始值，
实机 A/B 前不得标记为已验证。目录一项只映射一个物理
文件，避免同一 LoRA 以别名被重复加载。

HMInnie 的 `inniepussy` 替换提示词中的通用阴道名词，可与 HMPussy 叠加，但叠加不代表
已验证最优；Footjobs 只自动注入短触发词 `fj.`，不自动拼接作者给出的整段示例提示词。
Deepthroat v0.2 按作者说明以 24fps、guidance 4 训练并强调 15 秒连续性；当前系统固定
24fps，但公开 workflow guidance 为 1，因此只视为待 canary 候选。POV Missionary
作者仍标记为早期实验版。五个新模型在实机 canary 完成前均不得标记为已验证。

T2V/I2V/FLF2V 的 `10eros` v3 基础顺序为：`UNETLoader(TURBO hybrid Beta3) →
[用户选中 LoRA 有序链] → ModelAttentionBackend(comfy kitchen attention) →
MiniMaxH3SigmaShift(12/3) → ReservedVRAMSetter(2 GiB auto、3 GiB 上限) →
MiniMaxH3ImageToVideo → er_sde/ManualSigmas(1.00,0.94,0.83,0.72,0.55,0.30,0.10,0.00)`。
这是作者对 TURBO 模型偏好的 7-step 调度，默认链不得再叠加 LightX2V。
`official` FL2VA 保持 `UNETLoader → LightX2V(1.0) → 可选 LoRA → Euler/simple/8 steps`。
输出继续解码 H3 原生同步音轨。

REF2V 在 `10eros` 下使用同一 TURBO hybrid Beta3，不加载 LightX2V。其链路为
PyTorch attention、video/audio sigma shift `11/4`、
`MiniMaxH3ReferenceToVideo(ref_image_size="match")`、`KSamplerSelect("er_sde") →
ManualSigmas("1.00, 0.94, 0.83, 0.72, 0.55, 0.30, 0.10, 0.00") →
SamplerCustomAdvanced`；禁止 `BasicScheduler`。十八个候选 LoRA 中最多十三个仍按选择顺序注入；
REF2VA Motion v0.2 可进入任一 REF2V profile，并始终追加在所选基础/加速链之后。

`official + REF2V` 是独立执行 profile：同一基础节点在 patch 后切换为官方 INT8
ConvRot Ref2VA、`ref_image_size="max"`、`KSamplerSelect("res_multistep")` 和
`BasicScheduler("simple", 20, 1.0)`；不继承 10Eros 的 ManualSigmas。这里固定
`simple` 是为了与当前 Comfy-Org 官方模板精确对齐；官方说明参考很多时 `beta` 或
`normal` 往往优于 `simple`，后续若要调整必须作为新的受控 profile 单独 canary。

`official_ref2v_turbo + REF2V` 是独立极速 profile：官方 INT8 ConvRot Ref2VA →
专用 Ref2VA Turbo LoRA（1.0）→ 用户选中 LoRA 有序链 → PyTorch attention →
sigma shift `12/3` → `MiniMaxH3ReferenceToVideo(ref_image_size="match")` →
`KSamplerSelect("euler")` → `BasicScheduler("simple", 4, 1.0)`。4 steps、shift、
sampler、缩放策略和专用 LoRA 是同一蒸馏契约，不能替换为 FL2VA 8-step 文件或随意
改成 8 steps。`official` 20-step 高保真 profile 继续保留。

镜像不安装 ContextIR、SageAttention 或旧 `MiniMaxH3TurboSampler`；新模型包包含
10Eros TURBO hybrid Beta3、官方 FL2VA/Ref2VA、两份任务专属加速 LoRA和上述十八个
可选 LoRA，不包含 RedMix。旧 checkpoint、
blob 与 bundle 不删除，供回溯和回滚。10Eros BF16 主模型比 RedMix INT8 更占磁盘与加载
内存；7-step 只减少采样计算量，不消除模型加载和 CPU offload 成本。画质、峰值显存和
实际速度必须通过后续四模式 GPU canary 才能定论。

四份公开 API JSON 由 `scripts/build_minimax_h3_api_workflows.py` 确定性生成，并同步到
`workers/comfy_agent/workflows/` 与 LAN GPU runtime。REF2V 模板预建 5 个稳定图片槽，
patcher 删除未使用节点和连接并保持剩余图片顺序。

## 模型包与镜像

`scripts/prepare_minimax_h3_model_bundle.py` 固定版本
`2026-08-27-10eros-v3-official-int8-h3-turbo-profiles-addon18`、26 个文件的字节数与
SHA256，总计 114,106,812,703 bytes，准备前要求模型卷至少 110 GiB 可用。
脚本复用已有内容寻址 blob，只把缺失
资产下载到临时文件；尺寸和 SHA256 均通过后才原子落盘。Civitai 附件下载需要通过
`CIVITAI_API_TOKEN` 鉴权；Token 只发送给 Civitai API host，不转发到重定向后的对象存储。模型只进入
`/srv/allbot/model-registry`，不得进入 Git 或 OCI 镜像；本次准备不自动上传 LAN、R2 或
任何远端 registry。

作者发布新版本时保持 workflow 拓扑不变，只更新准备脚本与 bundle 中的 repository
revision、filename/modelVersion/fileId、SHA256 和 size。新版本必须使用新 bundle version，
不能覆盖旧 manifest；完整校验、focused tests 与 GPU canary 通过后才可单独更新部署指针。

镜像模块仍为 `minimax_h3`。LAN 与 RunPod artifact 独立发布；RunPod profile 只接受
`ghcr.io/giraffu/allbot-gpu-minimax-h3@sha256:<digest>` 形式的精确镜像引用，并从
`RUNPOD_MINIMAX_H3_MODEL_MANIFEST_KEY` 指向的不可变模型清单同步资产。不得复用 LAN
mutable tag 或源码同步替代 RunPod artifact。ComfyUI revision 固定为
`7fe8a6138504f90ff7be82f3babf416da32876b1`，并保留
DaSiWa Nodes、KJNodes、VHS 与 `ComfyUI-ReservedVRAM` 源码 revision，不安装
`ComfyUI-MiniMax-ContextIR`、`ComfyUI-MiniMax-H3-Turbo`，也不编译或在启动时依赖
SageAttention。ComfyUI 从镜像内 `/opt/ComfyUI` 启动，模型卷
挂载到 `/opt/ComfyUI/models`；禁止源码 bind mount 或在目标机 build。
DaSiWa 的 NVIDIA VFX 构建依赖固定为官方 `0.1.0.1` CPython 3.12 ABI3 wheel，按
`597,321,055` bytes 与 SHA256 `e51d9e6faa68466e45b83be7928321af4b0c561c7c5536a8cb2b7e6aba25f905`
并行分段下载并在安装前合并校验，避免 NVIDIA wheel-stub 的单连接损坏重试；该 wheel
只属于镜像构建依赖，不进入模型 bundle。
当前 RTX 5090 运行态保留 DynamicVRAM，但镜像将 AIMDO cast buffer 的
最大预留从 16 GiB 收紧为 8 GiB，避免 32 GiB 显卡上 PyTorch 只剩
16 GiB 可分配空间。运行参数同时启用 `--cache-none`，以便在图执行期间尽快
释放已不再需要的大型节点输出。不得在当前双 GPU、60 GiB RAM 宿主机
对 H3 使用 `--disable-dynamic-vram`；遗留 loader 会使 H3 匿名内存升至约
30 GiB，与同机 WAN22 runtime 叠加后触发宿主机 OOM。

## 测试 Worker 与正式 GPU 边界

H3 测试 Worker 是独立测试执行面的专用 `worker-agent`，只连接 test Central 和测试
存储，并声明 T2V/I2V/FLF2V/REF2V 四种公开类型。`worker-relay` 协议未变化时不重建。
普通“启动
H3 测试 Worker”不得选择 LAN `*_test` 候选、接管 LAN slot 或创建 cloud-test
RunPod；LAN/RunPod runtime 在该语境中都保持正式 Worker 身份。测试 agent 可以经
受限私网或测试主机 loopback 传输调用已经运行的 H3 ComfyUI，但不得启停、重启、
切换或重新标记该正式 runtime。

显式授权的 RunPod GPU artifact canary 使用
`scripts/gpu_pool_controller.py runpod canary --task-type minimax_h3`，与上述普通测试
Worker 操作语义不同。该入口只允许 `cloud-test`，强制单 Pod 成本门禁、RTX 5090、
精确镜像 digest、H3 不可变模型清单、test Central 与 `user-data-test`，并串行提交
T2V/I2V/FLF2V/REF2V 四条 5 秒 preview 任务。每条任务必须由目标 RunPod agent 接单、
Central 终态为 `done`、Web 结果成功且存在尾帧；无论成功或失败均恢复被临时关闭的
测试 Worker 并删除新建 Pod。该最小 cloud-test canary 不替代下文完整 GPU artifact
验收。

H3 RunPod volume 固定至少 140 GB，用于 `/workspace/ComfyUI/models`；不能沿用通用
100 GB 默认值，因为当前不可变 bundle 为 114,106,812,703 bytes，模型同步还需要目录、
临时文件和运行缓存余量。

不提交任务的运行验收包括：relay/agent 容器 running、restart count 为 0、OCI
revision 匹配完整 main SHA、ComfyUI `/system_stats` 与 `/queue` 可达，以及 test
Central `/system/workers` 中目标 agent 为 `enabled`、`idle` 且 profile/types 精确。
这只能证明测试 Worker 可接单，不等于 GPU artifact canary 已通过。

测试 agent 与正式 Worker 是两个长期并存的 Central consumer：前者只连接 test
Central/测试存储，后者只连接 prod Central/正式存储。二者可以同时保持 enabled 并调用
同一个 H3 ComfyUI；共享 ComfyUI 的 `/queue` 是执行串行化与容量事实源，不得仅因测试
agent 在线或提交测试任务就 drain 正式 Worker，也不得在测试结束后停止测试 agent。
运维检查必须分别核对两个 Central 的 heartbeat、task ownership 和对象存储边界，并同时
观察 ComfyUI queue，不能把 test Central 队列为空误判为 GPU 没有工作。

并存不授权并发修改 GPU runtime。模型 bundle/cache、workflow、镜像、ComfyUI 重启或
LAN slot takeover/rollback 仍需独立维护窗口，并按单槽 operator 的 drain 规则执行；只有
显式独占 benchmark 或已证实共享队列争用影响诊断时，才临时暂停其中一侧 intake。
验收至少串行提交 T2V、I2V、FLF2V 各一条 5 秒 preview，并覆盖 REF2V 1/4/5 图、
单个 addon 和 13 addon 有序组合，逐条检查：Central task type、Worker agent、MP4、
24fps、音轨、尾帧、显存/OOM/Xid；还必须对全部视频帧执行亮度/
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
  tests/scripts/test_prepare_minimax_h3_model_bundle.py
.venv/bin/python -m pytest -q \
  tests/ops/test_runpod_canary.py \
  tests/ops/test_runpod_cloud_test_canary.py
cd frontend && npm test -- --run \
  src/composables/lab-workbench/useLabSubmitPayload.test.ts \
  src/composables/lab-workbench/usePromptOptimizer.test.ts \
  src/views/CustomFeatures.test.ts \
  src/components/template-apply/TemplateAdvancedVideoProPanel.test.ts
```
