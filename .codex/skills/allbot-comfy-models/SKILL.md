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
- `workers/` 与 `remote_workers/` 的 workflow/mapping/checksum 必须保持发布
  契约要求的一致；不要只改本地 Worker。

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

- 不把本地绝对模型路径、凭据、下载 URL、一次性 Pod/agent ID、当前 GPU 数量
  或 canary 结果写入 Skill/Git。
- 不把模型文件提交 Git；manifest 只记录可审计来源、相对路径、checksum 和
  目标 profile 所需元数据。
- 不用 mutable tag、现场 build、rsync 源码或 bind mount 覆盖正式镜像代码。
- 未经明确授权，不创建/启用 RunPod，不切换 LAN slot，不修改生产 profile 或
  feature flag。
- 节点缺失、模型路径不匹配、目标 profile 不支持或 manifest 不完整时 fail
  closed；不要静默忽略用户参数或回退到另一模型。
- 参数数量、强度、分辨率、时长与输入张数必须由服务端/domain config 校验；
  Worker 仍做防御性校验。
- workflow 执行成功但上传/回报失败不能写成业务成功；结果物化遵守 task engine
  的终态与退款语义。

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
