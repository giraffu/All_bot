# AllBot AI 协作入口

本文件只维护全局路由和不可越过的边界。业务契约先加载对应
`.codex/skills/<skill>/SKILL.md`，再按 Skill 路由读取必要 `docs/`；不要一次性
加载整个知识库。

## 1. 全局规则

- **Skills first**：开发、排障、审查或运维前，先加载命中的项目 Skill。
  Skill 与代码冲突时，以代码和 focused tests 为现状证据，并先修正失真的
  Skill/文档。
- **Core isolation**：`src/core/` 只使用内部类型、协议和显式
  provider/dependencies；禁止 Telegram `Update`、Web `Request/APIRouter`
  和基础设施实现对象。跨入口统一使用 `internal_user_id`。
- **能力不等于授权**：A–H 可只读核对真实 env、凭据、日志和远端状态，但
  不得泄露秘密。读取到凭据不授权修改 test/prod、Cloudflare、数据库、
  RunPod、GPU/LAN 或发布状态。
- **生产 mutation**：正式发布、数据库迁移、Cloudflare、GPU/RunPod/LAN
  和本地灾备必须由用户明确要求。核心用户链路默认先验证测试环境。
- **不可变发布**：云环境只消费受保护 main 的完整 SHA 和 digest-pinned
  artifact；禁止 rsync 源码、现场 build、源码 bind mount、mutable tag、
  direct/force push main。
- **运行态不入 Git**：实时 worker/Pod 数量、LAN current/cache、一次性任务
  与事故现场只属于 provider/XDG/日志/归档，不写成稳定 Skill 或当前 SOP。

## 2. 主目录自动接单

用户在 `/home/hfy/APP/All_bot` 要求写仓库时，必须先加载
`allbot-concurrent-workspaces`，再执行：

```bash
python scripts/manage_ai_workspaces.py claim --task <kebab-case-slug>
```

后续读取、编辑、测试和 Git 只在返回的 A–H worktree。无空槽时在编辑前停止，
不得回退主目录开发。纯查询、审查、规划和集成发布不 claim。

完成后在槽位运行 focused tests，提交并推送任务分支，再执行：

```bash
python scripts/manage_ai_workspaces.py handoff --slot <A-H>
```

handoff 以远端 branch/head/base SHA 写入不可变集成队列并释放槽位。功能槽位
不创建逐任务 test-train PR、不部署共享 test、不操作 prod/Cloudflare/GPU。

## 3. 集成与 CI

- 本机单写者将等待 handoff 冻结为一个 `release-batch -> main` PR；运行中
  到达的 handoff 进入下一批。冲突、CI 或测试部署失败会阻断后续批次。
- `lightweight` 覆盖纯 docs、Skills、tests 和仓库治理；`release-tooling`
  覆盖明确发布工具；`operator` 覆盖 GPU/LAN operator allowlist；其它或混合
  路径 fail closed 为 runtime。
- lightweight/release-tooling 不构建 release bundle、不部署环境，但仍须
  受保护 PR 和相称的 focused tests。
- main runtime/operator bundle 成功后，唯一协调器才可串行更新共享 test；
  协调器没有 prod 参数。正式晋级仍需每次明确 `--confirm-prod`。

## 4. Skill 路由

| 场景 | Skill |
| --- | --- |
| 任务提交、队列、Worker、双 ID、zombie | `allbot-task-engine` |
| 计费、JWT、支付、affiliate、会员 | `allbot-billing-auth` |
| Gallery、评论、举报、R2、apply-context | `allbot-gallery-storage` |
| Telegram FSM、callback、文件、菜单 | `allbot-tg-fsm` |
| QQCC 官方/私有 Bot、webhook、租户归属 | `allbot-qqcc-lazy-bot` |
| Docker、不可变发布、迁移、灾备 | `allbot-ops-deployment` |
| A–H worktree、handoff、main 批次 | `allbot-concurrent-workspaces` |
| Cloudflare DNS/Tunnel/Access/Pages/R2 | `allbot-cloudflare-ops` |
| Comfy workflow、LoRA、ControlNet、profile | `allbot-comfy-models` |
| LAN AIO current/cache/takeover/recover | `allbot-lan-aio-operator` |
| LAN 资源管理平台、可信构建与 runner | `allbot-lan-resource-manager` |
| 本地分析提示词词元治理 | `allbot-local-analytics-prompt-semantics` |
| 知识库、Skill、文档同步 | `allbot-kb-auto-updater` |
| Bug 复现、诊断反馈环 | `allbot-diagnosing-bugs` |
| 行为测试、red-green-refactor | `allbot-tdd` |
| module/interface/seam 架构设计 | `allbot-codebase-design` |
| 后端 Python/FastAPI 审查 | `backend-code-review` |
| Vue 3 开发与审查 | `vue-best-practices` |
| 浏览器预览与响应式截图 | `frontend-browser-preview` |
| 日志采集、异常归因和事故报告 | `ops-log-monitor` |
| 全局静态分析、死代码和质量评估 | `allbot-code-analyzer` |

一个任务可以叠加多个 Skill。常见组合：

- 新功能/修 bug：领域 Skill + `allbot-tdd`；线上异常再加
  `allbot-diagnosing-bugs`。
- 修改职责、facade 或依赖注入：领域 Skill + `allbot-codebase-design`。
- 修改接口、入口、状态流或稳定术语：领域 Skill +
  `allbot-kb-auto-updater`。
- Vue UI 视觉验收：`vue-best-practices` + `frontend-browser-preview`。

## 5. 知识库分层

- `AGENTS.md`：全局路由、授权和工作区规则。
- `.codex/skills/*/SKILL.md`：触发条件、稳定入口、高压红线、按需阅读和最小
  验证；单个 Skill 必须小于 20 KB。
- `docs/子模块_*.md` 与 `docs/business/`：当前架构、业务契约和可执行 SOP。
- `docs/domain/CONTEXT.md`：只记录共享术语，不写实现或事故。
- `docs/adr/`：难逆、非显然且有真实替代方案的架构决策；Superseded ADR
  只作历史证据。
- `docs/knowledge_base_audit_matrix.md`：一份活跃资料一行的当前事实源台账，
  不记录逐日 changelog。
- `docs/archive/`、`docs/release_evidence/`、`logs/`：历史、取证、canary、
  事故和一次性运行态，不作为当前 SOP。

知识变更运行：

```bash
python scripts/doc_quality_checker.py
```

若新增 Skill，同步 Skill 文件、本路由、`docs/skills/README.md` 和审计矩阵。
若入口、异常、超时、ID、provider 或测试 seam 变化，同步对应专项文档。

## 6. 文档入口

- 系统总览：`docs/system_architecture_report.md`
- 知识库矩阵：`docs/knowledge_base_audit_matrix.md`
- 共享词汇：`docs/domain/CONTEXT.md`
- 生成主链：`docs/子模块_生成任务全链路_task_full_chain.md`
- 不可变发布：`docs/子模块_Git不可变发布_git_immutable_release.md`
- 并发工作区：`docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`
- 云测试/正式：`docs/子模块_云测试控制面部署_cloud_test_control_plane.md`、
  `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`
- GPU/LAN：`docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`、
  `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`

其它资料由 Skill 路由按需读取，不在此重复目录清单。
