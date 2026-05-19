# AllBot AI 编程辅助技能库 (AI Skill Library)

本目录与 `.trae/skills/` 同步，记录当前仓库内可用的系统级技能与适用边界。

## 1. 技能清单

当前工作区包含以下核心技能：

| 技能名称 | 核心边界 | 触发场景 |
| :--- | :--- | :--- |
| `allbot-task-engine` | Redis 队列调度、单用户并发锁、任务状态同步、僵尸任务清理 | 修改任务调度、队列、并发控制、Comfy 节点通信时 |
| `allbot-billing-auth` | Web 鉴权、JWT、密码登录、支付履约、返佣账本、返佣兑换灵石 | 修改充值、登录、身份、流水、返佣、支付回调时 |
| `allbot-gallery-storage` | MinIO/R2、广场投稿、评论、收藏、apply-context、对象存储生命周期 | 修改社区分享、互动、防刷、模板应用上下文、媒体 URL 策略时 |
| `allbot-tg-fsm` | Telegram FSM、多级菜单互斥、防死锁、大文件交互补丁 | 修改 Telegram 对话流、菜单跳转、文件交互时 |
| `allbot-llm-ops` | CS Bot、LangGraph、LM Studio、本地工具化问答、群聊意图识别 | 修改 AI 客服、本地大模型接入、技能工具绑定时 |
| `allbot-ops-deployment` | Docker Compose、Alembic、safe_deploy、部署排障与恢复 | 调整部署、迁移、容器、环境变量或恢复脚本时 |
| `allbot-comfy-models` | LoRA / ControlNet / ComfyUI 工作流参数透传与动态注入 | 修改附加模型、工作流映射、Bot 菜单参数时 |
| `allbot-code-analyzer` | 全局静态分析、死代码检测、架构审查、质量评估 | 进行全盘质量分析或架构体检时 |
| `allbot-kb-auto-updater` | 评估代码变更对知识库的影响并同步更新 docs/skills | 代码新增功能、重构、接口变更后 |
| `ops-log-monitor` | 多环境日志采集、异常归因、报告生成 | 需要排查线上日志或监控异常时 |
| `backend-code-review` | Python/FastAPI 后端代码审查 | 审查后端文件或后端改动时 |
| `vue-best-practices` | Vue 3 组合式 API、TypeScript、Pinia、Router 规范 | 修改前端 Vue 代码时 |

## 2. 使用建议
- 一个需求常常同时命中多个技能边界，例如“Web 端发起高级视频并扣费入队”通常需要同时加载：
  - `allbot-billing-auth`
  - `allbot-task-engine`
- 当需求本质是“同步知识库”，优先加载 `allbot-kb-auto-updater`，再根据触达的业务面补充其他技能。
- 当实际代码已经明显偏离技能说明时，应先更新技能与 `docs/`，再继续编码，避免旧约束误导后续改动。

## 3. 维护原则
- `docs/skills/README.md` 只维护技能目录与高层边界，不重复拷贝各 `SKILL.md` 的全部细节。
- 若新增技能，必须同时同步：
  - `.trae/skills/<skill>/SKILL.md`
  - `AGENTS.md` 路由表
  - 本 README 的技能清单
