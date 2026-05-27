# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全局路由指引。
为了避免全局上下文过载并保持规范的实时更新，**详细的架构规范与业务红线已全部下沉至独立的 Skills（技能）和 `/docs` 目录中**。

## 1. 核心开发原则 (Core Principles)

- **技能优先 (Skills First)**：遇到具体业务开发时，**必须第一时间调用（Invoke）对应的 Skill**，以获取该模块最新的架构红线、接口契约和容灾规范。
- **查阅文档 (Read Docs)**：在进行系统级重构、了解历史背景或不确定业务逻辑时，请主动读取 `/docs` 目录下的相关说明。
- **核心层隔离 (Core Isolation)**：`/src/core/` 下的代码**绝对禁止**引入任何与 Telegram `Update` 或 Web `Request` 相关的特定平台对象，必须使用内部统一的 `internal_user_id` 流转。
- **测试优先部署 (Test First Deploy)**：功能研发、联调、缺陷修复与配置调整，默认只更新隔离测试环境，优先执行 `safe_deploy_test.sh` 或测试栈对应 compose；只有在用户明确要求进入交付验证/正式发布时，才允许执行生产部署或更新正式服务。

## 2. AI 技能路由索引 (Skills Router)

在执行不同模块的修改时，请主动触发以下技能（Skill）：

| 领域 / 业务场景 | 对应 Skill 名称 | 核心管控边界 |
| :--- | :--- | :--- |
| **并发、排队与任务调度** | `allbot-task-engine` | Redis 队列调度、并发锁防刷、中控分发、僵尸任务双向剔除 |
| **计费、鉴权与会员体系** | `allbot-billing-auth` | 灵石账本 (credits)、JWT 无状态鉴权、支付回调幂等、身份折算 |
| **对象存储与画廊社区** | `allbot-gallery-storage` | MinIO 直传/容灾、R2 边缘分发、社区防并发点赞、一键克隆限制 |
| **Telegram 交互与文件** | `allbot-tg-fsm` | PTB 状态机、多语言(i18n)精准路由、菜单互斥防死锁、大文件 Monkey Patch |
| **AI 助理与大模型推理** | `allbot-llm-ops` | LM Studio 限流防 OOM、LangGraph 意图嗅探、群组记忆隔离 |
| **部署、容器与容灾排障** | `allbot-ops-deployment` | Docker Compose 编排、Alembic 迁移、测试优先发布策略、MinIO/网络故障自愈恢复、一键安全部署 (`safe_deploy` / `safe_deploy_test`) |
| **文档维护与知识库同步** | `allbot-kb-auto-updater` | 智能监控代码变更影响，自动维护 AGENTS.md、Skills 和 /docs/ 的逻辑一致性 |
| **后端代码审查与规范** | `backend-code-review` | 针对 FastAPI/Python 后端接口及核心层代码的架构规则审查、依赖注入和数据库模式检查 |
| **附加模型与工作流配置** | `allbot-comfy-models` | 处理图生图/图生视频的附加模型(LoRA/ControlNet)配置、参数透传与工作流注入 |
| **前端代码审查与规范** | `vue-best-practices` | 针对 Vue3 / SPA 前端（如 Dashboard 或 Web 工作台）的开发规范，推荐 Composition API 与 TypeScript |
| **系统日志监控与排障** | `ops-log-monitor` | 自动采集多环境日志，进行链路追踪与异常分析，并生成排障报告，期间保持静默与无痕清理 |
| **全局代码静态分析** | `allbot-code-analyzer` | 执行全盘死代码检测、质量评估、架构审查及注释清理，静默输出无痕分析报告 |

## 3. 文档体系导览 (Documentation Guide)

如果技能提示词不足以覆盖你的需求，请前往 `/docs` 目录查阅详尽的系统设计：
- **系统全景图**：`/docs/system_architecture_report.md`
- **生成任务全链路**：`/docs/子模块_生成任务全链路_task_full_chain.md`（前端提交、task core、执行面、worker、结果回流、扩展与排障）
- **业务领域设计**：`/docs/business/`（包含生成、商业化、社区、用户体系的深度文档）
- **技术子模块规范**：`/docs/子模块_*.md`（针对网络穿透、FSM、任务调度等的专项说明）

👨‍💻 **To AI Assistant**: 
本文件已极简改造。你不再需要从这里读取繁杂的业务红线。**在接下来的所有对话中，请严格遵循“按需加载 Skill”的原则开展工作。**
