# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全局路由指引。
当前项目以 **VS Code + Codex** 为主要 AI 编程入口，`.codex/skills/` 是 Codex 的项目级技能主目录。
为了避免全局上下文过载并保持规范的实时更新，**详细的架构规范与业务红线已全部下沉至独立的 Skills（技能）和 `/docs` 目录中**。

## 1. 核心开发原则 (Core Principles)

- **技能优先 (Skills First)**：遇到具体业务开发时，**必须第一时间加载对应 Skill**，以获取该模块最新的架构红线、接口契约和容灾规范。若当前 Codex 会话未自动暴露该项目 Skill，请手动读取 `.codex/skills/<skill-name>/SKILL.md`。
- **查阅文档 (Read Docs)**：在进行系统级重构、了解历史背景或不确定业务逻辑时，请主动读取 `/docs` 目录下的相关说明。
- **核心层隔离 (Core Isolation)**：`/src/core/` 下的代码**绝对禁止**引入任何与 Telegram `Update` 或 Web `Request` 相关的特定平台对象，必须使用内部统一的 `internal_user_id` 流转。
- **主目录自动接单 (Auto Claim)**：用户在 `/home/hfy/APP/All_bot` 提出需要写入仓库的开发、修复、重构或文档任务时，必须先加载 `allbot-concurrent-workspaces` 并执行 `python scripts/manage_ai_workspaces.py claim --task <slug>`，后续只在返回的 A-H 槽位中工作。纯查询/审查和集成发布任务不抢占槽位；无空闲槽位时必须在编辑前停止，不得回退到主目录开发。
- **能力与授权分离 (Capability vs. Authority)**：A-H 可以读取真实 env、配置、凭据、日志和远端状态，用于只读核对、本地测试与计划；不得泄露秘密原文。凭据可见不代表获准部署或修改共享 test、prod、Cloudflare、RunPod/GPU、数据库或发布状态。槽位依赖应独立，但发现运行中任务使用历史共享依赖时只记录风险，不得自动中断或清理。
- **按风险分级、不可变发布 (Risk-based Immutable Release)**：正式发布只接受受保护 `main` 可达的完整 Git SHA、成功 CI 构建任务生成的 release index 和 digest-pinned 产物；云端禁止代码/env rsync、现场 build、源码 bind mount和 `latest`。统一入口为 `scripts/release.py plan|preflight|deploy|rollback|recover`，策略为 `auto|standard|direct|emergency`：核心用户链路默认 `standard`，Dashboard/QQCC 管理面和 GPU 执行面默认 `direct`，公共 Web 默认 `standard` 但可显式 `direct`；核心紧急直发必须用 `emergency`。migration、部署/Compose 共享契约和未知路径永久 `standard`，不得旁路。`direct/emergency` 只豁免明确记录的测试门禁，不得跳过 main 血缘、CI 产物构建、digest/checksum/OCI revision、生产配置、目标健康、事务回滚、非目标服务不重建和每次真实正式执行的 `--confirm-prod`。`build-only` 只能由 CI 生成并记录 `tests=skipped`，发布时必须显式 `--skip-gate ci-tests --reason --approved-by`，禁止用 `--skip-ci-checks` 执行。唯一测试例外是精确受保护 `codex/test-train` 的可信 `test-candidate` bundle，它只能部署 test；共享 test-train 只由集成 AI 操作。Dashboard/QQCC 管理面不部署测试环境，测试 Worker 仅用 `--with-test-execution` 按需启用；验收证据按 track/artifact/digest 隔离。正式执行仍须用户明确确认。本地主服务器仅保留云正式整体故障时的临时灾备。

## 2. Codex 工作区知识布局 (Workspace Knowledge Layout)

- `AGENTS.md`：全局路由与高压红线，只保留入口级规则，避免塞入长篇业务细节。
- `.codex/skills/<skill-name>/SKILL.md`：Codex 项目级技能主入口，按需加载；修改业务边界时优先更新这里。
- `docs/skills/README.md`：技能目录清单与维护约定。
- `docs/knowledge_base_audit_matrix.md`：实时知识库逐项核对台账；记录每篇文档/Skill 的事实源、状态和本轮处理结果。
- `docs/domain/CONTEXT.md`：项目共享领域词汇表，只记录术语含义，不写实现细节。
- `docs/adr/`：架构决策记录；仅在决策难逆、非显然且存在真实取舍时新增。
- `/docs`：系统设计、业务规范、排障手册与历史背景；系统级重构或不确定业务逻辑时主动查阅。

## 3. AI 技能路由索引 (Skills Router)

在执行不同模块的修改时，请主动触发以下技能（Skill）：

| 领域 / 业务场景 | 对应 Skill 名称 | 核心管控边界 |
| :--- | :--- | :--- |
| **并发、排队与任务调度** | `allbot-task-engine` | Redis 队列调度、并发锁防刷、中控分发、僵尸任务双向剔除 |
| **计费、鉴权与会员体系** | `allbot-billing-auth` | 灵石账本 (credits)、JWT 无状态鉴权、支付回调幂等、身份折算 |
| **对象存储与画廊社区** | `allbot-gallery-storage` | MinIO 直传/容灾、R2 边缘分发、社区防并发点赞、一键克隆限制 |
| **Telegram 交互与文件** | `allbot-tg-fsm` | PTB 状态机、多语言(i18n)精准路由、菜单互斥防死锁、大文件 Monkey Patch |
| **QQCC 懒人 Bot / 用户私有 Bot** | `allbot-qqcc-lazy-bot` | 官方 QQCC polling、私有 Bot 申请 FSM/webhook worker、租户配置、`client_type` 恢复隔离和 token 红线 |
| **部署、容器与容灾排障** | `allbot-ops-deployment` | Docker Compose 编排、Alembic 迁移、测试优先发布、云正式/云测试控制面、本地正式灾备切换、MinIO/网络故障恢复 |
| **并发 AI 工作区与测试列车** | `allbot-concurrent-workspaces` | 主目录自动接单、A-H 高访问能力、凭据保密、代码/依赖隔离、操作授权分离、test-train 排他发布和 blocked/forward-fix |
| **Cloudflare 公网入口** | `allbot-cloudflare-ops` | Cloudflare API Token、DNS、Tunnel、Access、Pages/R2、公网管理域名和本地分析平台公网访问 |
| **本地分析提示词词义治理** | `allbot-local-analytics-prompt-semantics` | 提示词词元分类、指定词元、同义映射、删除表、tokens-only 物化、模板候选槽位口径 |
| **局域网 LAN AIO 管理** | `allbot-lan-aio-operator` | 读取 fleet state 与 slot catalog，按单卡 helper 流程管理 LAN AIO 当前态、缓存、候选切换、takeover/recover/restart |
| **文档维护与知识库同步** | `allbot-kb-auto-updater` | 智能监控代码变更影响，自动维护 AGENTS.md、`.codex/skills` 和 /docs/ 的逻辑一致性 |
| **Bug 诊断闭环** | `allbot-diagnosing-bugs` | 建立可复现反馈环、排序假设、精准插桩、修复回归与收尾清理 |
| **测试驱动研发** | `allbot-tdd` | 通过 public facade / API / FSM / provider dependencies seam 做行为测试，一次一个 vertical slice |
| **代码库架构设计** | `allbot-codebase-design` | 使用 module/interface/seam/adapter/depth/leverage/locality 词汇审查模块深度、职责移动与可测试性 |
| **后端代码审查与规范** | `backend-code-review` | 针对 FastAPI/Python 后端接口及核心层代码的架构规则审查、依赖注入和数据库模式检查 |
| **附加模型与工作流配置** | `allbot-comfy-models` | 处理图生图/图生视频的附加模型(LoRA/ControlNet)配置、参数透传与工作流注入 |
| **前端代码审查与规范** | `vue-best-practices` | 针对 Vue3 / SPA 前端（如 Dashboard 或 Web 工作台）的开发规范，推荐 Composition API 与 TypeScript |
| **前端预览与截图验收** | `frontend-browser-preview` | 使用 Playwright Chromium 在本服务器生成桌面/移动端截图，规避系统 Chrome headless 本地 HTTP 卡住问题 |
| **系统日志监控与排障** | `ops-log-monitor` | 自动采集多环境日志，进行链路追踪与异常分析，并生成排障报告，期间保持静默与无痕清理 |
| **全局代码静态分析** | `allbot-code-analyzer` | 执行全盘死代码检测、质量评估、架构审查及注释清理，静默输出无痕分析报告 |

## 4. 文档体系导览 (Documentation Guide)

如果技能提示词不足以覆盖你的需求，请前往 `/docs` 目录查阅详尽的系统设计：

- **系统全景图**：`/docs/system_architecture_report.md`
- **知识库核对矩阵**：`/docs/knowledge_base_audit_matrix.md`（实时 docs / skills 核对台账、事实源和归档边界）
- **系统资源与容量画像**：`/docs/子模块_系统资源与容量画像_resource_inventory.md`（主服务器、本地 GPU、网络、数据存储与运行负载快照）
- **云控制面 SSH 密钥管理**：`/docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md`（DigitalOcean SSH key、登录入口、安全基线与轮换策略）
- **局域网 GPU 节点 SSH 管理**：`/docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`（本地 GPU 节点 SSH key、Host 别名、权限边界与验证命令）
- **局域网 GPU 节点资源与运维**：`/docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`（GPU 节点硬件、ComfyUI 容器、模型挂载与单容器安全操作边界）
- **云测试控制面部署**：`/docs/子模块_云测试控制面部署_cloud_test_control_plane.md`（DigitalOcean 云测试控制面 compose、部署脚本、端口转发与验证命令）
- **Git 不可变发布**：`/docs/子模块_Git不可变发布_git_immutable_release.md`（完整 SHA、GHCR digest、公共 Compose、配置契约、测试验收、生产晋级与回滚）
- **并发 AI 开发与测试列车**：`/docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`（A-H worktree、test-candidate、共享测试站排他合入与最终 main 晋级）
- **并发 AI 自动接单**：`/docs/并发AI自动接单使用指南_auto_workspace_claim.md`（用户只需在主目录说需求，AI 自动抢占空闲槽位）
- **首次可信发布准备**：`/docs/子模块_首次可信发布准备_first_trusted_release.md`（本地 stabilization 验证结果、Git 血缘和外部待办）
- **QQCC 懒人 Bot**：`/docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`（独立简化 Telegram Bot、部署、token 与任务恢复归属）
- **QQCC 用户私有 Bot 平台**：`/docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md`（一人一 Bot、加密凭据、Webhook 多租户 worker、Owner WebApp、管理员治理与发布门禁）
- **本地正式灾备切换**：`/docs/子模块_本地正式灾备切换_local_prod_fallback.md`（云正式整体故障时临时切回本地主服务器的操作、验证与回切）
- **Cloudflare 公网入口与账号管理**：`/docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md`（Cloudflare Token、DNS、Tunnel、Access、公网管理入口与本地分析平台公网访问）
- **生成任务全链路**：`/docs/子模块_生成任务全链路_task_full_chain.md`（前端提交、task core、执行面、worker、结果回流、扩展与排障）
- **前端预览截图**：`/docs/子模块_前端浏览器预览截图_frontend_browser_preview.md`
- **业务领域设计**：`/docs/business/`（包含生成、商业化、社区、用户体系的深度文档）
- **技术子模块规范**：`/docs/子模块_*.md`（针对网络穿透、FSM、任务调度等的专项说明）

👨‍💻 **To AI Assistant**:
本文件已极简改造。你不再需要从这里读取繁杂的业务红线。**在接下来的所有对话中，请严格遵循“按需加载 `.codex/skills` Skill，再按需查阅 `/docs`”的原则开展工作。**
