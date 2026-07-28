# AllBot Knowledge Base Audit Matrix

本矩阵只登记活跃知识入口和 canonical 事实源，一份资料一行。责任域由分节
标题确定；本轮静态核对日期为 `2026-07-27`。状态只使用 `current`、
`needs-review`、`runtime-verification-required`、`superseded`。

逐日变化、已删除 seam、部署结果、事故和一次性运行态不登记为矩阵行，统一
进入
[`docs/archive/knowledge-base-changelog/`](archive/knowledge-base-changelog/)
或 `docs/release_evidence/`。

## 总览、治理与业务文档

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/knowledge_base_audit_matrix.md` | 活跃知识索引 | 本矩阵、质量检查器的登记/体积门禁 | current | 仅全量知识校准 |
| `docs/system_architecture_report.md` | 稳定系统拓扑与边界 | 入口、core、Central、Worker、发布契约 | current | 跨模块设计 |
| `docs/SAFE_DEPLOY_GUIDE.md` | 发布快速入口 | `scripts/release.py`、不可变发布文档 | current | 只需发布入口 |
| `docs/domain/CONTEXT.md` | 共享领域词汇 | 代码模型与领域文档 | current | 术语歧义 |
| `docs/skills/README.md` | Skill 索引、context packet 与预算 | `.codex/skills`、`AGENTS.md`、质量检查器 | current | 选择/维护 Skill |
| `docs/入口职责矩阵_entry_responsibility_matrix.md` | Web/Central 入口归属与重叠 | 应用入口、router、provider 注册 | current | 新接口或职责移动 |
| `docs/compat_seam_exit_table.md` | 尚存兼容层和退出条件 | 静态调用、数据/运行态观测 | runtime-verification-required | 删除兼容层 |
| `docs/测试与入口命名约定.md` | 测试与入口命名 | tests、公开 facade | current | 新测试/入口 |
| `docs/business/00_INDEX_业务板块分类与规范总览.md` | 业务文档索引 | business 文档 | current | 业务视角导航 |
| `docs/business/00_DICT_全局业务数据字典.md` | 业务数据字典 | schema、API、领域模型 | current | 字段/口径变更 |
| `docs/business/01_BIZ_AI创作与生成板块.md` | 生成业务能力 | task registry、入口、History | current | 产品生成能力 |
| `docs/business/02_BIZ_商业化与会员资产板块.md` | 商业化与资产 | billing/auth/payment | current | 计费与会员 |
| `docs/business/03_BIZ_社区广场与社交互动板块.md` | 社区业务 | Gallery API/service | current | 社区产品 |
| `docs/business/04_BIZ_用户修为与身份权限体系.md` | 用户身份与权限 | user/auth/quota | current | 身份权限 |
| `docs/business/image_to_image_flow.md` | 图生图业务流 | task registry、FSM/Web、worker patcher | current | 图生图改动 |
| `docs/business/image_to_video_flow.md` | 图生视频业务流 | registry、FSM/Web、Wan22/LTX worker | current | 视频生成改动 |

## 任务、Bot、Web 与社区

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/子模块_任务调度_task_scheduler.md` | task facade、队列与清理 | `src/core/task_core*`、QueueManager | current | 任务生命周期 |
| `docs/子模块_生成任务全链路_task_full_chain.md` | 入口到结果的完整链路 | Web/Bot、Central、Worker、History | current | 跨层任务改动 |
| `docs/子模块_中控API与节点通信_central_api.md` | Central/Agent 协议 | `backend/app`、API client、Worker | current | 队列或 worker 协议 |
| `docs/子模块_任务黄金路径回归清单_task_golden_path.md` | 端到端行为清单 | public facade/API/FSM/provider tests | current | 高风险回归 |
| `docs/子模块_交互状态机_fsm_handlers.md` | Telegram FSM/callback/file | handlers、runtime bootstrap、FSM services | current | Bot 交互 |
| `docs/子模块_Telegram本地API与文件代理_tg_local_api.md` | Bot API/file endpoint | runtime bootstrap、Bot env | current | Telegram 文件/代理 |
| `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md` | 官方 QQCC 与 Config | QQCC code、config service、focused tests | current | QQCC 功能 |
| `docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md` | 私有 Bot webhook/租户 | schema、credentials、worker、owner/admin API | current | 私有 QQCC |
| `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` | 独立审核 Bot | paid group code/config | current | 入群审核 |
| `docs/子模块_客服Bot_support_bot.md` | 客服工单 Bot | support bot、Dashboard、schema | current | 客服能力 |
| `docs/子模块_用户认证与权限_user_auth_permission.md` | JWT/密码/权限 | auth core、Web security | current | 鉴权 |
| `docs/子模块_计费与支付_billing_payment.md` | 账本、支付、affiliate | billing core、payment services、RMB reconciliation jobs | current | 金钱与会员 |
| `docs/子模块_社区与存储_gallery_storage.md` | Gallery、R2、apply-context | Gallery core/services、storage、R2 scripts | current | 社区/媒体 |
| `docs/子模块_后台监控与清理_dashboard_monitoring.md` | Dashboard 监控治理 | Dashboard backend/frontend | current | 管理后台 |
| `docs/子模块_本地数据分析平台_local_analytics_platform.md` | LAN 分析平台 | local analytics code、shadow pipeline | runtime-verification-required | 本地分析 |
| `docs/子模块_本地数据分析平台提示词词义分析_prompt_semantics.md` | 提示词词元治理 | prompt rule/materialization code | current | 词元治理 |

## 模型、GPU 与运行环境

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/子模块_附加模型配置指南_comfy_models.md` | workflow/LoRA/模型注入 | workflow JSON、mapping、patcher | current | 模型/workflow |
| `docs/子模块_LTX文生视频与人物一致性_ltx_t2v_characters.md` | LTX T2V/人物一致性 | domain config、workflow、profile、`shared/image_aspect.py`、结果物化、RunPod canary | current | LTX 专项；人物参考表与 QQCC AI 动图共用智能比例适配器；IC guide 在交付区间外并 fail-closed 裁除；单张正面半身照的六视图需重复门禁与人工语义检查；test Web/后端和 cloud-test 人工 RunPod 已支持，prod 与 autoscaler 关闭 |
| `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` | GPU/RunPod/LAN 稳定边界 | release manifest、provider、catalog、ledger、LAN-only `all` profile | runtime-verification-required | GPU 设计/运维；`all` 只允许 LAN AIO exact-digest takeover |
| `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` | LAN GPU 主机与 ComfyUI | live 节点、受控 helper | runtime-verification-required | LAN 节点 |
| `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md` | LAN SSH 契约 | SSH config/key metadata | runtime-verification-required | LAN 登录 |
| `docs/子模块_LAN_AIO本地资源管理平台_lan_resource_manager.md` | LAN 管理、A–H 集成/对齐与发布 UI/runner | `lan_resource_manager`、fleet/integration/release helper | current | 本地资源平台 |
| `docs/子模块_系统资源与容量画像_resource_inventory.md` | 资源和容量快照 | 当次只读探测 | runtime-verification-required | 容量规划 |
| `docs/子模块_容灾与持久化_database_recovery.md` | 数据库/Redis 恢复 | schema、backup/restore scripts | current | 数据恢复 |

## 发布、网络与仓库治理

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/子模块_Git不可变发布_git_immutable_release.md` | artifact、测试、晋级、回滚 | release.py 兼容门面、release contracts/planning、catalog、policy、tests | current | 发布变更/执行 |
| `docs/子模块_运维指南与容器管理_ops_deployment.md` | Compose 与一般运维 | deploy compose、release scripts | current | 容器运维 |
| `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` | test 拓扑与 SOP | test overlay/env contract、release state | runtime-verification-required | 测试环境 |
| `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` | prod 拓扑与 SOP | prod overlay/env contract、release state | runtime-verification-required | 正式环境 |
| `docs/子模块_本地正式灾备切换_local_prod_fallback.md` | 云故障本地接管 | fallback scripts、DNS/数据门禁 | current | 灾备 |
| `docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md` | 云 SSH 密钥边界 | key metadata、host config | runtime-verification-required | 云登录 |
| `docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md` | DNS/Tunnel/Access/Pages/R2 | Cloudflare 配置与只读探测 | runtime-verification-required | 公网入口 |
| `docs/子模块_网络暴露与代理穿透_network_proxy.md` | 网络与代理边界 | compose/network/Cloudflare config | current | 网络改动 |
| `docs/子模块_边缘节点运维指南_edge_node_ops.md` | 边缘节点运维 | edge config/scripts | runtime-verification-required | 边缘节点 |
| `docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md` | main 保护与 CI 门禁 | GitHub workflow/ruleset | runtime-verification-required | CI/保护规则 |
| `docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md` | 热点路径回归 | classifier、workflow、tests | current | CI 路由 |
| `docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md` | A–H/handoff/main 批次 | workspace scripts、integration queue | current | 并发开发 |
| `docs/并发AI自动接单使用指南_auto_workspace_claim.md` | 用户接单指南 | manage_ai_workspaces.py | current | 主目录写任务 |
| `docs/子模块_前端浏览器预览截图_frontend_browser_preview.md` | Playwright 截图 | preview skill/scripts | current | UI 验收 |
| `docs/子模块_代码静态分析与质量评估规范_code_quality.md` | 静态分析报告规范 | analyzer skill/tooling | current | 全盘审查 |

## ADR

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/adr/README.md` | ADR 状态索引 | 各 ADR | current | 查架构决策 |
| `docs/adr/0000-template.md` | ADR 模板 | ADR 维护约定 | current | 新建 ADR |
| `docs/adr/0001-postgresql-only-runtime.md` | PostgreSQL-only 决策 | schema/运维工具 | current | 数据库架构 |
| `docs/adr/0002-qqcc-private-bots-use-webhooks.md` | 私有 Bot webhook 决策 | private worker 架构 | current | 私有 Bot 运行时 |
| `docs/adr/0003-git-sha-immutable-image-promotion.md` | 不可变身份决策 | release contract | current | 发布身份 |
| `docs/adr/0004-three-release-tracks-and-thin-images.md` | 三轨与薄镜像 | artifact catalog | current | artifact 架构 |
| `docs/adr/0005-four-ai-worktrees-and-test-train.md` | 旧 test-train 决策 | ADR 0008 | superseded | 历史原因 |
| `docs/adr/0006-risk-based-artifact-release-gates.md` | 风险门禁决策 | release policy | current | assurance 策略 |
| `docs/adr/0007-promote-tested-candidate-artifacts.md` | 旧 candidate 晋级 | ADR 0008 | superseded | 历史原因 |
| `docs/adr/0008-main-first-release-batches.md` | main-first 批次 | integration queue/workspace scripts | current | 当前集成设计 |

## 项目 Skills

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `.codex/skills/allbot-task-engine/SKILL.md` | 任务生命周期路由 | task core/Central/Worker docs | current | 任务改动 |
| `.codex/skills/allbot-billing-auth/SKILL.md` | 计费鉴权红线 | billing/auth code | current | 金钱/身份 |
| `.codex/skills/allbot-gallery-storage/SKILL.md` | Gallery/R2 路由 | Gallery/storage code | current | 社区/存储 |
| `.codex/skills/allbot-tg-fsm/SKILL.md` | Telegram FSM 路由 | handlers/runtime services | current | Bot 交互 |
| `.codex/skills/allbot-qqcc-lazy-bot/SKILL.md` | QQCC 官方/私有 Bot 路由 | QQCC code/docs | current | QQCC |
| `.codex/skills/allbot-ops-deployment/SKILL.md` | 发布运维路由 | release/compose/docs | current | 运维 |
| `.codex/skills/allbot-concurrent-workspaces/SKILL.md` | A–H/handoff 路由 | workspace/integration scripts | current | 仓库写任务 |
| `.codex/skills/allbot-cloudflare-ops/SKILL.md` | Cloudflare 路由 | Cloudflare config/docs | current | 公网入口 |
| `.codex/skills/allbot-comfy-models/SKILL.md` | 模型/workflow 路由 | workflow/mapping/profile | current | AI 模型 |
| `.codex/skills/allbot-lan-aio-operator/SKILL.md` | LAN AIO 操作红线 | catalog/ledger/helper | current | LAN mutation |
| `.codex/skills/allbot-lan-resource-manager/SKILL.md` | 本地资源平台 | platform/helper/docs | current | LAN UI |
| `.codex/skills/allbot-local-analytics-prompt-semantics/SKILL.md` | 词元治理 | analytics code/docs | current | 提示词治理 |
| `.codex/skills/allbot-kb-auto-updater/SKILL.md` | 知识同步 | docs/Skills/matrix | current | 知识变更 |
| `.codex/skills/allbot-diagnosing-bugs/SKILL.md` | Bug 反馈环 | reproduction/tests/logs | current | 故障 |
| `.codex/skills/allbot-tdd/SKILL.md` | TDD 纪律 | public seams/tests | current | 行为改动 |
| `.codex/skills/allbot-codebase-design/SKILL.md` | 架构词汇 | module/interface/seam | current | 设计重构 |
| `.codex/skills/backend-code-review/SKILL.md` | 后端审查 | backend rules | current | Python review |
| `.codex/skills/vue-best-practices/SKILL.md` | Vue 规范 | Vue code/tooling | current | 前端 |
| `.codex/skills/frontend-browser-preview/SKILL.md` | 浏览器预览 | Playwright workflow | current | UI 截图 |
| `.codex/skills/ops-log-monitor/SKILL.md` | 日志监控 | env logs/diagnostics | current | 线上日志 |
| `.codex/skills/allbot-code-analyzer/SKILL.md` | 静态分析 | analyzer workflow | current | 全局审查 |
