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
- **不可变发布**：操作者从完整 Git SHA 在本机构建明确模块，云环境只消费
  digest-pinned artifact；禁止 rsync 源码、目标机 build、源码 bind mount、
  mutable tag 和 force push main。
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

## 3. 集成与发布

- 本机单写者逐个验证 handoff 的精确远端 head，并直接合并、推送 main。
  内容冲突只把该记录转入 `needs-rebase`，后续 pending 继续集成。
- 冲突修订基于最新 main 产生新 commit 和 handoff，并用 `--supersedes`
  指向旧记录。协调器不创建 PR、不查询或运行 CI、不构建产物、不部署环境。
- focused tests 由任务自行决定，不是 main 合入条件；并发写入协调不是发布门禁。
- 操作者使用 `scripts/release.py build --module ... --sha ...` 独立构建模块，
  再以精确 digest 直接部署 test 或 prod。系统不保存人工测试资格。
- 正式 mutation 仍需明确模块、环境和 `--confirm-prod`，但不查询 CI、
  test evidence、Git diff、bundle、其它模块或 GPU 完整性。

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
| 云主机 SSH、密钥、端口、堡垒机、救援控制台 | `allbot-cloud-ssh` |
| Comfy workflow、LoRA、ControlNet、profile | `allbot-comfy-models` |
| 多模态提示词优化、Profile/模板、Prompt Worker | `allbot-prompt-optimizer` |
| 独立媒体增强平台、账本、Worker 契约与 workflow | `allbot-media-enhance-platform` |
| 3D 角色 Mini App、GLB/VRM、Blender 渲染 | `allbot-avatar-miniapp` |
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
- 云 SSH 失败：`allbot-cloud-ssh`；线上事故再加 `allbot-diagnosing-bugs`，
  需要日志采集再加 `ops-log-monitor`。

## 5. 知识库分层

- **最小上下文协议**：
  1. 只选命中场景的最少 Skill；完整读取这些 Skill。
  2. 先检查 Skill 指向的代码入口、配置和 focused tests。
  3. 只打开“按需阅读”表中命中的文档；跨层改动才组合多篇。
  4. `knowledge_base_audit_matrix.md` 只用于全量校准，archive/evidence 只用于
     追溯，不作为普通开发的预读上下文。
  5. 已足以定位 interface、事实源、红线和验证项时停止扩展上下文。
- `AGENTS.md`：全局路由、授权和工作区规则。
- `.codex/skills/*/SKILL.md`：触发条件、稳定入口、高压红线、按需阅读和最小
  验证；单个 Skill 必须小于 16 KB，且不写日期化运行态。
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

## 6. 治理入口

- 系统总览：`docs/system_architecture_report.md`
- 知识库矩阵：`docs/knowledge_base_audit_matrix.md`
- 共享词汇：`docs/domain/CONTEXT.md`

普通研发和运维不从本清单继续展开；由命中的 Skill 路由专题资料。
