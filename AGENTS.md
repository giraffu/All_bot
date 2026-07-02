# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全局路由指引。
当前项目以 **VS Code + Codex** 为主要 AI 编程入口，`.codex/skills/` 是 Codex 的项目级技能主目录。
为了避免全局上下文过载并保持规范的实时更新，**详细的架构规范与业务红线已全部下沉至独立的 Skills（技能）和 `/docs` 目录中**。

## 1. 核心开发原则 (Core Principles)

- **技能优先 (Skills First)**：遇到具体业务开发时，**必须第一时间加载对应 Skill**，以获取该模块最新的架构红线、接口契约和容灾规范。若当前 Codex 会话未自动暴露该项目 Skill，请手动读取 `.codex/skills/<skill-name>/SKILL.md`。
- **查阅文档 (Read Docs)**：在进行系统级重构、了解历史背景或不确定业务逻辑时，请主动读取 `/docs` 目录下的相关说明。
- **核心层隔离 (Core Isolation)**：`/src/core/` 下的代码**绝对禁止**引入任何与 Telegram `Update` 或 Web `Request` 相关的特定平台对象，必须使用内部统一的 `internal_user_id` 流转。
- **测试优先部署 (Test First Deploy)**：功能研发、联调、缺陷修复与配置调整，默认先更新云测试控制面；日常维护式更新首选 `scripts/update_cloud_test_with_maintenance.sh --execute`，`scripts/safe_deploy_cloud_test.sh` 只是远端控制面重建子步骤。旧本地测试栈脚本仅作历史保留/人工取证，不再作为受支持的测试或回滚环境；本地主服务器只保留云正式整体故障时的临时正式灾备方案。只有在用户明确要求进入交付验证/正式发布时，才允许执行生产部署或更新正式服务。

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
| **QQCC 懒人 Bot** | `allbot-qqcc-lazy-bot` | 独立 QQCC polling 服务、简化菜单、quick image/video FSM、`bot:qqcc` 任务来源和双 polling 红线 |
| **部署、容器与容灾排障** | `allbot-ops-deployment` | Docker Compose 编排、Alembic 迁移、测试优先发布、云正式/云测试控制面、本地正式灾备切换、MinIO/网络故障恢复 |
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
- **QQCC 懒人 Bot**：`/docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`（独立简化 Telegram Bot、部署、token 与任务恢复归属）
- **本地正式灾备切换**：`/docs/子模块_本地正式灾备切换_local_prod_fallback.md`（云正式整体故障时临时切回本地主服务器的操作、验证与回切）
- **生成任务全链路**：`/docs/子模块_生成任务全链路_task_full_chain.md`（前端提交、task core、执行面、worker、结果回流、扩展与排障）
- **前端预览截图**：`/docs/子模块_前端浏览器预览截图_frontend_browser_preview.md`
- **业务领域设计**：`/docs/business/`（包含生成、商业化、社区、用户体系的深度文档）
- **技术子模块规范**：`/docs/子模块_*.md`（针对网络穿透、FSM、任务调度等的专项说明）

👨‍💻 **To AI Assistant**: 
本文件已极简改造。你不再需要从这里读取繁杂的业务红线。**在接下来的所有对话中，请严格遵循“按需加载 `.codex/skills` Skill，再按需查阅 `/docs`”的原则开展工作。**
