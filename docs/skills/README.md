# AllBot Skills 索引

项目级 Skill 主入口为 `.codex/skills/<skill>/SKILL.md`。只加载当前任务命中的
Skill，再按其中“按需阅读”路由打开专项文档；不要预加载全部 Skills/docs。

## 技能目录

| Skill | 负责范围 |
| --- | --- |
| `allbot-task-engine` | 任务 facade、队列、Worker、双 ID、终态和清理 |
| `allbot-billing-auth` | JWT、账本、支付履约、affiliate、会员 |
| `allbot-gallery-storage` | Gallery、互动、举报、R2、apply-context |
| `allbot-tg-fsm` | Telegram FSM、callback、菜单、文件和更新并发 |
| `allbot-qqcc-lazy-bot` | QQCC 官方/私有 Bot、配置、webhook 和租户归属 |
| `allbot-ops-deployment` | 不可变发布、Compose、迁移、测试/正式和灾备 |
| `allbot-concurrent-workspaces` | A–H worktree、handoff、批次集成 |
| `allbot-cloudflare-ops` | DNS、Tunnel、Access、Pages、R2 公网入口 |
| `allbot-cloud-ssh` | 云主机 SSH 连接、认证、主机密钥与救援入口 |
| `allbot-comfy-models` | workflow、LoRA、ControlNet、Worker profile |
| `allbot-lan-aio-operator` | LAN AIO current/cache/takeover/recover |
| `allbot-lan-resource-manager` | LAN 资源平台、可信构建、部署与 runner |
| `allbot-local-analytics-prompt-semantics` | 本地分析提示词词元治理 |
| `allbot-kb-auto-updater` | docs/Skills/术语/矩阵一致性 |
| `allbot-diagnosing-bugs` | 可复现反馈环、假设、插桩和回归 |
| `allbot-tdd` | public seam 行为测试和纵切开发 |
| `allbot-codebase-design` | module/interface/seam/depth 架构设计 |
| `backend-code-review` | Python/FastAPI 后端审查 |
| `vue-best-practices` | Vue 3、Composition API、TypeScript |
| `frontend-browser-preview` | Playwright 预览和响应式截图 |
| `ops-log-monitor` | 日志采集、异常归因和事故报告 |
| `allbot-code-analyzer` | 全局静态分析、死代码和质量评估 |

## 分层约定

- `AGENTS.md` 只维护全局路由、授权和工作区规则。
- `SKILL.md` 是 context packet，只维护触发边界、按任务文档路由、稳定入口、
  高压红线和最小验证。
- 专项 `docs/` 维护当前业务契约、架构和 SOP。
- `docs/domain/CONTEXT.md` 只作为 glossary。
- `docs/knowledge_base_audit_matrix.md` 一份活跃资料一行，分节表示责任域，
  顶部记录静态复核日期和归档入口；不登记 archive 行或追加 changelog。
- `docs/compat_seam_exit_table.md` 只登记尚存兼容层和有价值 seam，并写明
  责任域、运行时调用方、退出信号和最近静态复核日期。
- 事故、上线记录、迁移证据、canary、一次性 ID 和运行态进入
  `docs/archive/`、`docs/release_evidence/` 或 `logs/`。

## 维护门禁

- 单个 Skill 小于 16 KB，全部 Skills 合计小于 140 KB；超出时把低频细节
  下沉到专项文档，不通过拆成自动加载的 reference 规避预算。
- 活跃专题文档单篇小于 75 KB、合计小于 1 MB。大文档优先改善 Skill 的按需
  路由；只有职责确实可独立加载时才拆分，避免制造重复索引。
- 避免超过 1000 字符的规则行；拆成可扫描的短条目。
- Skill 中不写 ISO 日期流水、真实秘密、固定 Pod/任务 ID、邮箱/IP allowlist、
  实时 worker 数量、当前部署结果或已被取代的 SOP。
- 领域 Skill 必须至少路由一篇专项文档，并有最小验证/测试清单。运行态先读
  声明式配置和实时 API，不能相信 Skill 中的快照。
- 新增 Skill 时同步 `.codex/skills`、`AGENTS.md`、本索引和审计矩阵。
- 入口、对象名、异常、超时、双 ID、provider/dependencies 或测试 seam
  变化时，同步领域 Skill 和专项文档。
- 运行 `python scripts/doc_quality_checker.py` 验证路由覆盖、矩阵登记、当前/
  历史边界、canonical 路径、内部链接、日期化运行态和体积预算。
