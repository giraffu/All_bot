# AllBot AI 编程辅助技能库 (AI Skill Library)

本目录与 `.codex/skills/` 同步，记录当前仓库内可用的系统级技能与适用边界。技能描述应反映代码“现状入口”，而不是历史实现路径；若技能说明与代码主入口冲突，应先更新 `.codex/skills` 与 `docs/`，再继续开发。

## 1. 技能清单
当前工作区包含以下核心技能：

| 技能名称 | 核心边界 | 触发场景 |
| :--- | :--- | :--- |
| `allbot-task-engine` | task core facade、provider/capability、双 ID 语义、提交 Saga、Web side-effect monitor、僵尸任务/强制终止 | 修改任务调度、队列、并发控制、任务生命周期、恢复/取消逻辑时 |
| `allbot-billing-auth` | Web 鉴权、JWT claim、password_version、支付履约、affiliate 账本、affiliate 兑换灵石/会员、membership settlement | 修改充值、登录、身份、流水、返佣、支付回调时 |
| `allbot-gallery-storage` | MinIO/R2、广场投稿、评论、收藏、apply-context、对象存储生命周期 | 修改社区分享、互动、防刷、模板应用上下文、媒体 URL 策略时 |
| `allbot-tg-fsm` | Telegram FSM、全局菜单黑盒退出、callback 注册路由、临时文件下载清理、语言切换同步 | 修改 Telegram 对话流、菜单跳转、文件交互时 |
| `allbot-ops-deployment` | Docker Compose、Alembic、云测试控制面、云正式控制面、本地正式灾备、Dashboard 单服务热修、RunPod/LAN AIO 运维、部署排障与恢复 | 调整部署、迁移、容器、环境变量、云正式热修、测试环境、灾备切换、workflow 资产或恢复脚本时 |
| `allbot-comfy-models` | LoRA / ControlNet / ComfyUI 工作流参数透传、动态注入、Worker/remote_workers workflow 映射校验、SCAIL-2 视频生视频模型与 workflow | 修改附加模型、工作流映射、Bot 菜单参数或 RunPod/LAN Comfy profile 时 |
| `allbot-code-analyzer` | 全局静态分析、死代码检测、架构审查、质量评估 | 进行全盘质量分析或架构体检时 |
| `allbot-kb-auto-updater` | 评估代码现状对知识库的影响并同步更新 docs/skills/memory | 代码新增功能、重构、接口变更后 |
| `ops-log-monitor` | 多环境日志采集、异常归因、报告生成 | 需要排查线上日志或监控异常时 |
| `backend-code-review` | Python/FastAPI 后端代码审查 | 审查后端文件或后端改动时 |
| `vue-best-practices` | Vue 3 组合式 API、TypeScript、Pinia、Router 规范 | 修改前端 Vue 代码时 |
| `frontend-browser-preview` | 本服务器浏览器预览、Playwright Chromium 截图、桌面/移动视觉验收 | 前端任务需要预览效果、对照参考图或检查响应式布局时 |

## 2. Codex 技能维护约定
- Codex 项目级技能主入口为 `.codex/skills/<skill>/SKILL.md`。当会话没有自动暴露项目 Skill 时，AI 助手必须按需手动读取该文件。
- `AGENTS.md` 只维护全局路由和高压红线，不承载长篇模块细节；业务规则、接口契约和排障策略放到对应 Skill 与 `/docs`。
- 技能描述必须模型无关，不写死某个历史模型版本；重点描述触发场景、当前真实入口和不能越过的边界。

## 3. 使用建议
- 一个需求常常同时命中多个技能边界，例如“Web 端发起高级视频并扣费入队”通常需要同时加载：
  - `allbot-billing-auth`
  - `allbot-task-engine`
- 当需求本质是“同步知识库”，优先加载 `allbot-kb-auto-updater`，再根据触达的业务面补充其他技能。
- 当前端改动需要视觉确认时，加载 `frontend-browser-preview`；若同时修改 Vue 代码，也加载 `vue-best-practices`。
- 当变更涉及核心门面、运行时依赖、状态流、接口 I/O、超时值、异常类型、双 ID 语义时，优先同步对应 `SKILL.md`。
- 当测试已经迁移到 provider/dependencies seam，后续知识描述也应同步强调“显式依赖注入优先”，避免继续鼓励旧的模块级 patch 方式。

## 4. 维护原则
- `docs/skills/README.md` 只维护技能目录与高层边界，不重复拷贝各 `SKILL.md` 的全部细节。
- `SKILL.md` 只沉淀触发边界、当前真实入口、不可越过的红线和最小验证要求；不要记录一次性 Pod ID、任务 ID、失败尝试流水账或长篇现场日志。这类材料应进入 `/docs/archive/` 或 `logs/`。
- 若新增技能，必须同时同步：
  - `.codex/skills/<skill>/SKILL.md`
  - `AGENTS.md` 路由表
  - 本 README 的技能清单
- 若技能文档中的主入口文件、超时值、关键对象名或异常类型已失真，应视为知识库过期，需要优先修复。
