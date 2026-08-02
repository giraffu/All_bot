# 子模块：本地多模态 LLM 提示词优化

本文定义 AllBot 后续接入本地 LM Studio/VLM 时的模型口径、统一输出契约和按
`task_type` 选择的提示词生成策略。它是设计与接入目录，不代表提示词优化服务已
接入提交链路，也不代表候选 ComfyUI 模型已经部署。

## 1. 边界与事实源

- 优化器是生成任务提交前的可选预处理器，只产出提示词字符串；不得改变
  `task_type`、workflow、checkpoint、LoRA、价格、时长、分辨率或扣费身份。
- 图片/视频只作为当前请求的证据。不得凭空增加人物、身份特征或与首尾帧冲突的
  状态；用户明确要求的变化除外。
- 输出仍须经过现有 domain config、API schema 和 Worker patcher 校验。LLM 的
  JSON、负向词和节点参数都不可信，不能直接写入任意 workflow 节点。
- task type 与 workflow 映射以 `src/domain_config/task_type_registry.py`、
  `workers/comfy_agent/workflows/mappings.json`、当前 workflow JSON 和 patcher
  为准。本文不固化易变节点 ID。
- 不接受自由提示词的任务（普通换脸、`face_video` 等）不调用优化器。

建议服务层使用如下结构化结果，避免模型把解释文字混入实际提示词：

```json
{
  "schema_version": "allbot.prompt_optimizer.v1",
  "task_profile": "ltx_i2v",
  "image_facts": ["仅记录输入中可观察的事实"],
  "preserved_constraints": ["必须保持的身份、构图或时序条件"],
  "positive_prompt": "最终正向提示词",
  "negative_prompt": "仅在该任务支持时生成",
  "warnings": []
}
```

## 2. 本地可用 LLM/VLM

当前本机的优先候选是 **Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive
Q4_K_P GGUF + 对应 F16 mmproj**，通过 LM Studio 的 OpenAI-compatible API
加载。建议服务端使用稳定别名 `ltx-prompt-optimizer`，默认基址
`http://127.0.0.1:1234/v1`。该组合用于“图片 + 原始提示词 → 优化提示词”，
不是 ComfyUI 生成模型，也不进入 GPU artifact 或 Git。

推荐运行基线：16K context、并发 4、GPU full offload；请求输出上限从 1024
tokens 起步。并发数、实际显存占用和模型是否已加载属于运行态，调用前必须通过
`GET /v1/models`、一次文本 canary 和一次带图 canary 重新验证，不能从本文推断
服务可用。服务端还应设置排队上限、超时和熔断；提示词优化失败时保留用户原始
提示词，不得让生成任务被无限阻塞。

选择替代模型时必须同时满足：LM Studio 可加载的 GGUF、匹配的视觉投影文件、
能理解图片、遵循 JSON schema、中文输入和英文生成提示词表现稳定。纯文本 GGUF
只能做二次润色，不能承担图片事实提取。

## 3. 通用 system meta-prompt

以下内容应作为自有模板维护，不直接复制模型发布页的长提示词：

```text
你是 AllBot 的生成提示词编译器。根据 task_profile、用户原始提示词及带角色标记
的输入媒体，生成可直接交给对应 workflow 的提示词。图片是事实证据，不得虚构
其中不存在的人物或身份特征；保留用户意图和所有显式约束。严格执行 task_profile
的输入角色、段落结构、时序所有权和禁止项。不要建议模型、LoRA、采样器、价格、
分辨率或工作流设置。只返回指定 JSON；不输出分析、Markdown 或额外说明。
```

请求中必须显式标记媒体角色，例如 `start_image`、`end_image`、
`reference_image_1`、`driving_video`，不能只按附件顺序让模型猜测。

## 4. 视频任务 profile

| task type | profile | 推荐生成规则 |
| --- | --- | --- |
| `ltx_video` | `ltx_i2v` | 起始图是精确首帧。只补充后续动作、表演、镜头、环境变化和音频；按时长形成简单连续的动作弧，避免重复静态外观。 |
| `ltx_video_flf2v` | `ltx_flf2v` | 起始图和结束图都是硬约束。描述两者间自然过渡，将动作分布到时长中，禁止生成与终帧姿态/人物数量冲突的中间事件。 |
| `ltx_video_v2v_audio` | `ltx_v2v_audio` | 输入视频拥有原始时序和构图。描述期望的表演/画面变化及对白、环境声、音效；不得套用“图片是首帧”的指令。 |
| `ltx_t2v` | `ltx_t2v` | 没有参考图，必须完整描述主体、场景、风格、构图、灯光、动作、镜头、时间演化和音频。不可使用 I2V 的省略式写法。 |
| `ltx_t2v_ic` | `ltx_t2v_ic` | 通用 LLM 只生成目标场景/动作/音频，不改写人物参考表。若生成完整 Worker 输入，必须保留 `### Reference Sheet Description` 与 `### Target Description` 两段标题，以及人物段的 Left/Right Panel 契约。负向词只使用该链路规定的最小基线。 |
| `image_to_video`、`wan22_video_v2` | `wan22_i2v` | 依次写场景/可见外观、动作/运动/故事、镜头/构图。参考图提供首帧事实；存在结束帧时明确自然过渡。profile/LoRA 的模型配置不交给 LLM。 |
| SCAIL2 动作迁移（短/长） | `scail2_action_transfer` | driving video 拥有动作、节奏、镜头；参考图拥有人物身份、服装和风格。提示词只写必要的风格或例外约束，不重新发明动作。 |
| SCAIL2 视频替换 | `scail2_video_replacement` | driving video 拥有背景、灯光、镜头和运动；参考图提供替换主体。强调自然融入和需保留项。 |
| SCAIL2 换脸 v2 | `scail2_face_swap_append_only` | 不重写 domain config 的固定换脸契约，只把用户要求压缩成狭窄的 additional guidance。不得从人脸参考图引入身体、服装、姿势或背景。 |

### 4.1 LTX2.3 10Eros v1.4 候选 profile

发布页将 v1.4 描述为与 v1.0/v1.2 差异较大的版本，并建议 I2V 使用朴素的
scene-script，而不是沿用旧版提示词技巧。为此预留 `ltx_eros_v14_i2v`：

1. 明确输入图是精确首帧，不重新描摹整张静态图。
2. 用 4–8 个短句组织：一条整体电影感/镜头句、环境与光线、以
   `Performance:` 开头的表演动作句；需要时再加 `Dialogue:`。
3. 表演使用自然停顿、目光、呼吸、微表情和清晰动词，动作从首帧姿态按简单
   逻辑演进；不无故增加角色或夸张肢体运动。
4. T2V 不使用此 profile；T2V 没有首帧信息，必须完整描述画面。

该发布页同时建议搭配其 DMD LoRA，并称 BF16 比 FP8 更能保留细节。这些是模型
作者的使用建议，不属于提示词优化器参数，也不证明 AllBot 当前已部署 v1.4。
当前启用的 `ltx_video*` workflow、候选 v1.2 workflow 和未来 v1.4 workflow
必须分别从 registry/workflow/manifest 核验，禁止仅因选择此 profile 就切模型。
来源：[LTX2.3 10Eros v1.4 模型页](https://civarchive.com/models/2447875?modelVersionId=3109610)。
页面许可还限制真实人物/名人用途；若引入该 checkpoint，模型准入与产品策略需要
单独审查，不能由 uncensored LLM 绕过。

## 5. 图片任务 profile

| task type | profile | 推荐生成规则 |
| --- | --- | --- |
| `pornmaster_flux2_single_edit` | `flux2_single_edit` | 使用祈使式编辑指令：要改变什么、目标结果、必须保持什么。不要写镜头时间演化；负向词只在现有字段允许时返回。 |
| `pornmaster_flux2_multi_edit` | `flux2_multi_edit` | 明确 `Image 1`、`Image 2` 各自角色，逐项说明从哪张图提取什么、合成到哪里、哪些内容保持不变，避免含糊代词。 |
| `img2img`、`img2img_lora`、`i2i_pro` | `image_edit_general` | 生成简洁的结果规格：主体、编辑差异、保持项、风格、灯光与构图。LoRA 名称和强度不是提示词内容。 |
| `i2i_draw` | `image_edit_pose_locked` | 与通用编辑相同，但姿态/构图保持要求归 Worker 固定契约；LLM 不得移除或反向改写。 |
| `txt2img` | `text_to_image_full_scene` | 无参考图，完整描述主体、动作、环境、构图、镜头、灯光、材质和风格，不使用首帧/保持原图等语言。 |
| `character_reference_build` | `character_reference_slots` | 不做自由创意润色。按视图槽位输出同一身份、同一服装的正面/侧面/背面等严格描述；人物面板的实际拼接与白底契约由服务端完成。 |

人物一致性细则继续以
[`子模块_LTX文生视频与人物一致性_ltx_t2v_characters.md`](子模块_LTX文生视频与人物一致性_ltx_t2v_characters.md)
为准。普通换脸及其它没有 prompt 输入映射的任务标记为
`prompt_optimizer=disabled`。

## 6. 接入与验收清单

1. 在服务端建立显式 `task_type -> task_profile` 白名单；未知类型 fail closed，
   不调用“通用万能提示词”。
2. 为每个 profile 固定输入媒体角色、是否允许负向词、最大输出长度和保留契约。
3. 解析 JSON 后拒绝额外字段、空正向词和超长结果；保留原始提示词用于审计与
   失败回退，但不得记录用户媒体或敏感提示词到普通应用日志。
4. 建立最小回归集：单人、多人、首尾帧冲突、没有人物、中文短提示词、对白、
   多图角色顺序，以及 LLM 返回非 JSON/超时/卸载模型。
5. 对比“原始提示词 vs 优化提示词”的 Comfy 结果时固定 workflow、seed、时长、
   分辨率和 LoRA，避免把模型栈变化误判为提示词收益。
6. 未来接入代码时再为 API、并发限流、超时回退和各严格契约补 focused tests；
   本文档本身不授权修改 test/prod 或 LAN 运行态。
