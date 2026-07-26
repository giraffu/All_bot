# AllBot AI 编程辅助技能库 (AI Skill Library)

本目录与 `.codex/skills/` 同步，记录当前仓库内可用的系统级技能与适用边界。技能描述应反映代码“现状入口”，而不是历史实现路径；若技能说明与代码主入口冲突，应先更新 `.codex/skills` 与 `docs/`，再继续开发。

## 1. 技能清单

当前工作区包含以下核心技能：

| 技能名称 | 核心边界 | 触发场景 |
| :--- | :--- | :--- |
| `allbot-task-engine` | task core facade、provider/capability、双 ID 语义、提交 Saga、Web side-effect monitor、僵尸任务/强制终止 | 修改任务调度、队列、并发控制、任务生命周期、恢复/取消逻辑时 |
| `allbot-billing-auth` | Web 鉴权、JWT claim、password_version、支付履约、affiliate 账本、affiliate 兑换灵石/会员、membership settlement | 修改充值、登录、身份、流水、返佣、支付回调时 |
| `allbot-gallery-storage` | MinIO/R2、广场投稿、评论、收藏、apply-context、对象存储生命周期 | 修改社区分享、互动、防刷、模板应用上下文、媒体 URL 策略时 |
| `allbot-tg-fsm` | Telegram FSM、全局菜单黑盒退出、callback 注册路由、临时文件下载清理、语言切换同步、独立付费群审核与轻量群管理 Bot 边界 | 修改 Telegram 对话流、菜单跳转、文件交互或付费群审核 Bot 时 |
| `allbot-qqcc-lazy-bot` | 官方 QQCC polling、用户私有 Bot 申请/配置、webhook worker、租户 `client_type` 隔离及 polling/webhook token 红线 | 修改 `qqcc_bot/`、`qqcc_private_bot/`、QQCC 菜单、私有 Bot API/worker、compose、恢复或来源过滤时 |
| `allbot-ops-deployment` | Docker Compose、Alembic、云测试控制面、云正式控制面、本地正式灾备、Dashboard 单服务热修、RunPod/LAN AIO 运维、部署排障与恢复 | 调整部署、迁移、容器、环境变量、云正式热修、测试环境、灾备切换、workflow 资产或恢复脚本时 |
| `allbot-concurrent-workspaces` | 主目录自动原子接单、A-H 高访问能力与凭据保密、main 基线、不可变 handoff、单批次 main PR 和按需共享测试站发布 | 用户在主目录直接提出写入需求、多 AI 并发开发、分配/交接槽位、冻结发布批次、组装单一 main PR 或处理 forward-fix 时 |
| `allbot-cloudflare-ops` | Cloudflare Account API Token、DNS、Tunnel、Access、Pages/R2、公网管理域名、本地分析平台与管理后台公网访问 | 配置或排障 Cloudflare 公网入口、Token 轮换、Access allowlist、Tunnel public hostname、Pages/R2 账号级能力时 |
| `allbot-local-analytics-prompt-semantics` | 本地数据分析平台提示词词义分析、词元分类、指定词元、同义映射、删除表、自由P图拆解、tokens-only 物化与模板候选槽位口径 | 审查/治理提示词词元、处理高频未覆盖词元、合并映射、软删除无效词、年龄人群发现标签、自由P图拆解筛选或模板候选语义槽位时 |
| `allbot-lan-aio-operator` | LAN AIO fleet state、slot catalog、单物理 GPU takeover/recover/restart、镜像拉取、模型热缓存、drift 检查 | 查看或切换局域网 GPU 节点 LAN AIO 当前类型、缓存候选、阻断 profile 或执行受控单卡切换时 |
| `allbot-lan-resource-manager` | `lan_resource_manager/` 的 FastAPI/Vue、LAN bind/CIDR/CSRF、catalog-ledger-live 聚合和稳定候选网页切换 | 开发或排障本地 LAN AIO 资源管理页面、API、Compose 与安全门禁时 |
| `allbot-comfy-models` | LoRA / ControlNet / ComfyUI 工作流参数透传、动态注入、Worker/remote_workers workflow 映射校验、SCAIL-2 视频生视频模型与 workflow | 修改附加模型、工作流映射、Bot 菜单参数或 RunPod/LAN Comfy profile 时 |
| `allbot-code-analyzer` | 全局静态分析、死代码检测、架构审查、质量评估 | 进行全盘质量分析或架构体检时 |
| `allbot-kb-auto-updater` | 评估代码现状对知识库的影响并同步更新 docs/skills/memory | 代码新增功能、重构、接口变更后 |
| `allbot-diagnosing-bugs` | bug 诊断反馈环、假设排序、精准插桩、修复回归和收尾清理 | 用户报告失败、慢、卡住、线上异常、任务不可见或要求 debug/diagnose/troubleshoot 时 |
| `allbot-tdd` | 行为测试、public seam、red-green-refactor、vertical slice | 新功能研发、bug 修复回归、test-first 或需要补 focused tests 时 |
| `allbot-codebase-design` | module/interface/seam/adapter/depth/leverage/locality 架构词汇 | 设计模块接口、移动职责、改善可测试性、审查浅封装或架构重构时 |
| `ops-log-monitor` | 多环境日志采集、异常归因、报告生成 | 需要排查线上日志或监控异常时 |
| `backend-code-review` | Python/FastAPI 后端代码审查 | 审查后端文件或后端改动时 |
| `vue-best-practices` | Vue 3 组合式 API、TypeScript、Pinia、Router 规范 | 修改前端 Vue 代码时 |
| `frontend-browser-preview` | 本服务器浏览器预览、Playwright Chromium 截图、桌面/移动视觉验收 | 前端任务需要预览效果、对照参考图或检查响应式布局时 |

## 2. Codex 技能维护约定

- Codex 项目级技能主入口为 `.codex/skills/<skill>/SKILL.md`。当会话没有自动暴露项目 Skill 时，AI 助手必须按需手动读取该文件。
- `AGENTS.md` 只维护全局路由和高压红线，不承载长篇模块细节；业务规则、接口契约和排障策略放到对应 Skill 与 `/docs`。
- `docs/knowledge_base_audit_matrix.md` 维护 docs / skills 的逐项核对台账。完成知识库校准时，应同步记录事实源、状态和处理结果。
- 技能描述必须模型无关，不写死某个历史模型版本；重点描述触发场景、当前真实入口和不能越过的边界。

## 3. 使用建议

- 一个需求常常同时命中多个技能边界，例如“Web 端发起高级视频并扣费入队”通常需要同时加载：
  - `allbot-billing-auth`
  - `allbot-task-engine`
- 当需求本质是“同步知识库”，优先加载 `allbot-kb-auto-updater`，再根据触达的业务面补充其他技能。
- 当前端改动需要视觉确认时，加载 `frontend-browser-preview`；若同时修改 Vue 代码，也加载 `vue-best-practices`。
- 当日志分析进入代码修复或根因验证时，叠加 `allbot-diagnosing-bugs`；当改动需要行为锁定时，叠加 `allbot-tdd`。
- 当争论职责边界、模块深浅、依赖注入位置或测试 seam 时，叠加 `allbot-codebase-design`。
- 当变更涉及核心门面、运行时依赖、状态流、接口 I/O、超时值、异常类型、双 ID 语义时，优先同步对应 `SKILL.md`。
- 当测试已经迁移到 provider/dependencies seam，后续知识描述也应同步强调“显式依赖注入优先”，避免继续鼓励旧的模块级 patch 方式。

## 4. 维护原则

- `docs/skills/README.md` 只维护技能目录与高层边界，不重复拷贝各 `SKILL.md` 的全部细节。
- `SKILL.md` 只沉淀触发边界、当前真实入口、不可越过的红线和最小验证要求；不要记录一次性 Pod ID、任务 ID、失败尝试流水账或长篇现场日志。这类材料应进入 `/docs/archive/` 或 `logs/`。
- Skill 正文应优先保持短入口形态：接近 20KB、出现超过 800 字符的超长行、或需要读入大量低频运行态细节时，应拆到 `references/` 或对应 `/docs/子模块_*.md`，并在 `SKILL.md` 中写清“什么时候读哪个文件”。接近 35KB 的 Skill 视为需排期瘦身。
- 项目共享词汇进入 `docs/domain/CONTEXT.md`；架构决策只在难逆、非显然且有真实取舍时进入 `docs/adr/`。
- 若新增技能，必须同时同步：
  - `.codex/skills/<skill>/SKILL.md`
  - `AGENTS.md` 路由表
  - 本 README 的技能清单
  - 必要时同步对应 `docs/子模块_*.md` 专项文档和 `docs/knowledge_base_audit_matrix.md`
- 若技能文档中的主入口文件、超时值、关键对象名或异常类型已失真，应视为知识库过期，需要优先修复。

## 5. 2026-06-27 Skill 体积审计

本轮只量化 `.codex/skills/*/SKILL.md`，不展开远端运行态探测。`allbot-ops-deployment`、`allbot-comfy-models` 与 `allbot-task-engine` 已按“短入口 + 按需文档/reference”形态瘦身；`allbot-gallery-storage` 已折叠超长媒体 URL 策略行。

| Skill | 当前大小 | 结论 |
| :--- | :--- | :--- |
| `allbot-ops-deployment` | 约 10KB，最大单行 256 字符 | 已从约 51KB 瘦身为路由型入口，低频 RunPod/LAN AIO/shadow 细节改由 docs/reference 按需加载 |
| `allbot-comfy-models` | 约 7.4KB，最大单行 167 字符 | 已从约 36KB 瘦身为模型/workflow 路由入口，节点级和运行态细节改由 Comfy 子模块文档与 runtime reference 按需加载 |
| `allbot-task-engine` | 约 8.4KB，最大单行 212 字符 | 已从约 23KB 瘦身为任务生命周期路由入口，长链路、新任务类型 checklist 与排障细节改由任务调度/全链路文档按需加载 |
| `allbot-gallery-storage` | 约 13KB，最大单行 757 字符 | 正文体量可接受；本轮已折叠超长媒体 URL 策略行，暂不需要拆分 |

## 6. 2026-07-11 Skill 体积复核

本轮重新量化所有项目级 Skill。大多数入口仍低于 20KB；以下三项已越过或接近“短入口”维护阈值，应在后续触达对应业务时按“稳定红线留在 Skill、低频流程移到 references/docs”拆分，本轮只更新知识库，不机械改写业务规则。

| Skill | 当前大小 | 结论 |
| :--- | :--- | :--- |
| `allbot-qqcc-lazy-bot` | 约 26.5KB，最大单行约 2151 字符 | 已超过短入口阈值，且单行聚合过多链路语义；下一次 QQCC 业务改动前优先拆分配置、生成链和部署 reference |
| `allbot-gallery-storage` | 约 17.9KB，最大单行约 824 字符 | 接近阈值并重新出现超长行；后续把媒体 URL/迁移细节继续下沉到 Gallery 专项文档 |
| `allbot-tg-fsm` | 约 13.1KB，最大单行约 951 字符 | 总体积尚可，但存在超长规则行；后续按主 Bot FSM、付费群 Bot 与 runtime bootstrap 边界拆行/分 reference |
