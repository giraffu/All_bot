---
name: "allbot-comfy-models"
description: "处理图生图/图生视频附加模型、ComfyUI workflow、Bot/Web 参数透传与 Worker 动态注入。新增或修改生成模型时必须调用。"
---

# AllBot ComfyUI 模型与工作流

本 Skill 是模型与 workflow 的 context packet。用户可见 task type、具体模型清单、
节点 ID、LoRA 数量、当前 canary/profile 状态会变化，只从代码、workflow JSON、
manifest 和专项文档读取，不在此维护快照。

涉及任务生命周期叠加 `allbot-task-engine`；修改价格叠加
`allbot-billing-auth`；修改 Bot FSM 叠加 `allbot-tg-fsm`；发布 GPU artifact
叠加 `allbot-ops-deployment` 与相应 operator。

## 1. 按需阅读

| 场景 | 先读 |
| --- | --- |
| task type、workflow 映射、LoRA/ControlNet 注入 | `docs/子模块_附加模型配置指南_comfy_models.md` |
| LTX 文生视频/人物一致性 | `docs/子模块_LTX文生视频与人物一致性_ltx_t2v_characters.md` |
| 本地多模态 LLM 提示词优化、task profile | `docs/子模块_本地多模态LLM提示词优化_prompt_optimizer.md` |
| 用户提交到 Worker 结果回流 | `docs/子模块_生成任务全链路_task_full_chain.md` |
| GPU profile、artifact、RunPod/LAN | `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` |
| QQCC 场景/选项 | `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md` |
| 不可变发布 | `docs/子模块_Git不可变发布_git_immutable_release.md` |

只读命中场景。修改节点前必须重新打开当前 workflow JSON；文档中的节点 ID 仅是
导航提示。

## 2. 稳定事实源

- 用户能力和参数：task registry/domain config、Bot/Web schema 与 presenter。
- task type → workflow/profile：Worker registry、workflow resolver、release
  artifact catalog 和 focused tests。
- 节点、输入名和默认值：`workers/comfy_agent/workflows/*.json` 及对应
  patcher；禁止凭记忆编辑。
- 模型是否可运行：目标 profile 的模型 manifest、镜像内 workflow checksum、
  运行时只读探测和 canary evidence。控制面出现选项不等于 GPU 已可加载。
- 价格、History 类型、扣费退款：billing/task 领域事实源；workflow override
  不能改变业务类型或价格。
- 提示词优化器只是可选预处理 seam，输出必须按 task profile 重新校验；它不得
  选择或改写业务 task type、workflow、模型/LoRA、时长、分辨率和计费字段。
- 本地 LLM 是否已加载、视觉能力、并发与显存占用属于运行态，必须实时探测；
  Skill 不保存绝对模型路径、进程状态或一次性容量结论。

## 3. 分层与复用

- 优先复用现有用户 task type、执行 profile、workflow 和 patch seam。只有
  用户语义、资源隔离或发布生命周期确实不同才新增类型/profile。
- Bot/Web 只收集和校验参数；domain config 规范化；Worker patcher 把参数写入
  workflow；ComfyUI 只执行 JSON。不要在多个入口复制节点逻辑。
- 用户可见逻辑类型可以 alias 到内部执行类型；alias 不得改写 History、价格、
  refund identity 或 Gallery 分类。
- 多阶段任务只有一个根业务身份和一次扣费。预处理/换脸/续接阶段使用内部执行
  ID 与 continuation checkpoint，不对用户暴露，也不二次扣费。
- 多个 task type 共享 workflow 时，在 patcher 按类型注入差异，不复制 JSON。
- 主 Bot、QQCC 和管理后台可有不同选项 catalog；私有选项不得泄漏到公开
  catalog，兼容字段只读解析，不作为新入口。
- `workers/comfy_agent/` 与 `workers/runpod_runtime/` 的
  workflow/mapping/checksum 必须保持发布契约要求的一致；不要只改测试执行
  Worker 或正式 GPU runtime。

## 4. 修改流程

1. 明确用户语义、输入/输出、价格归属、执行 profile 和资源要求。
2. 搜索 registry、schema、presenter、submission、Worker mapping、patcher、
   workflow、manifest、History/Gallery 和 tests 的所有调用点。
3. 先补参数拒绝、默认值、patch 结果、错误收口和 alias 身份的行为测试。
4. 修改 workflow 前保存结构化 diff；逐个核对 node class、input key、模型
   相对路径和输出节点，禁止按显示标题猜 node ID。
5. 同步 Bot/Web/QQCC schema 与 i18n；服务端必须再次校验，不依赖前端菜单。
6. 若模型或 workflow 进入 artifact，更新 checksum/manifest/profile，走同
   SHA 构建和 canary；代码合入本身不代表模型已在运行节点生效。

## 5. 高压红线

- 不把绝对模型路径、凭据、一次性 Pod/agent ID、GPU 数量
  或 canary 结果写入 Skill/Git。
- 模型不入 Git；manifest 只记来源、相对路径、checksum 和 profile 元数据。
- 不用 mutable tag、现场 build、rsync 源码或 bind mount 覆盖正式镜像代码。
- 未经明确授权，不创建/启用 RunPod，不切换 LAN slot，不修改生产 profile 或
  feature flag。
- `ltx_t2v` 的测试 Web/后端可在 cloud-test 显式开启并连接专用测试 worker；
  Dashboard 只登记独立手动 profile。prod Web、正式 Pod 与 autoscaler 默认关闭，
  不得因测试开关或后台可见性自动晋级。测试环境的 `ltx_t2v` / `ltx_t2v_ic`
  只能由该专用 worker 声明；legacy LTX worker 和通用 `all` worker 默认不得消费，
  避免同一 Central 类型被旧 patcher 或不匹配 profile 随机领取。
- 节点缺失、模型路径不匹配、目标 profile 不支持或 manifest 不完整时 fail
  closed；不要静默忽略用户参数或回退到另一模型。
- 参数数量、强度、分辨率、时长与输入张数必须由服务端/domain config 校验；
  Worker 仍防御校验。H3 基础链固定，LoRA 目录/数量/强度/节点链由 domain
  config 和 patcher fail closed；未知选项不得忽略。
- workflow 执行成功但上传/回报失败不能写成业务成功；结果物化遵守 task engine
  的终态与退款语义。
- 人物参考表与场景背景属于 conditioning，不是交付首尾帧。当前测试
  `ltx_t2v_ic` 固定恰好两个有序人物面板和一张环境图；角色可混用用户私有与
  published 官方角色，环境可选 published 官方单图或当前用户临时上传单图，采用 Runexx 的
  两阶段 guide/crop/sampler 拓扑，模型链固定为 10Eros v1.4 DMD →
  `LTX2.3-Licon-MSR-test_version.safetensors`。10Eros 提供成人生成能力，Licon
  只维持身份；不叠加 distilled、Sulphur 或其它 NSFW LoRA。
- `ltx_t2v_ic` 的两张人物面板和背景图都必须先由 Worker 从对象存储下载并上传到
  目标 ComfyUI input，再把本地文件名注入 `LoadImage`；远端 object key 不得直接
  进入 workflow，也不得把无媒体输出的 Comfy success 当成任务成功。
- 浏览器提交 typed `character_refs` 与 `environment_ref`；旧 ID/upload key 只作
  过渡兼容。服务端校验 owner/published/moderation，解析完整四视图面板、人物描述
  与环境描述；Worker 按选择顺序追加稳定描述。两阶段都必须
  使用 `LTXAddVideoICLoRAGuide`、`LTXVAddGuideMulti` 与 `LTXVCropGuides`，最终裁除
  guide latent。少/多角色、缺背景、客户端面板路径或强度字段全部 fail closed。
- Ingredients 正向提示必须使用官方可执行 workflow 的
  `### Reference Sheet Description` / `### Target Description` 两段标题；人物段内部还必须由 Worker 规范化为
  `Left Panel (Character Face)` / `Right Panel (Character Turnaround)` 两个训练子标题，并从身份文字中移除
  background/panel/参考图等布局句，准确
  描述一个人物 ingredient 和目标动作；基线负向只使用官方质量词
  `worst quality, inconsistent motion, blurry, jittery, distorted`。布局排除词必须
  单独 A/B 验证后才能加入，不能默认与参考表训练语义对冲。
  人物素材必须合成为一张左侧大幅正脸、右侧全身正/侧/背的单一人物面板，禁止
  把六张同角色素材作为六个等权 scene panel。
  单张正面半身照可作为人物构建输入；人物面板固定使用正脸、全身正面、全身
  侧面和全身背面四个槽位，生成与直接上传可混用，保存前必须人工检查视角和景别。

## 6. 最小验证

- Registry/schema：新旧 payload、默认值、非法数量/强度/分辨率/时长拒绝。
- Patcher：使用真实 workflow fixture，断言目标节点、模型路径、输入顺序、
  清空旧槽和非目标节点不变。
- Identity：alias/multi-stage 保持业务 task type、History、价格和根退款键。
- Worker：本地与 remote mapping/checksum 一致，缺 workflow/model fail
  closed，上传与 complete 顺序正确。
- UI/Bot：菜单、i18n、schema、服务端复验和跨入口隔离。
- Artifact：完整 SHA、digest/checksum、OCI revision、目标 manifest 和
  disabled canary；只有实际执行最小任务后才能声明目标 profile 可用。
- 交付列出修改的 registry/workflow/profile/docs/tests，并区分“代码已就绪”
  “artifact 已构建”“测试已 canary”“生产已启用”。
