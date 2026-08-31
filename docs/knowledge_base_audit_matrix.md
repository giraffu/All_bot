# AllBot Knowledge Base Audit Matrix

本矩阵只登记活跃知识入口和 canonical 事实源，一份资料一行。责任域由分节
标题确定；本轮静态核对日期为 `2026-08-29`。状态只使用 `current`、
`needs-review`、`runtime-verification-required`、`superseded`。

逐日变化、已删除 seam、部署结果、事故和一次性运行态不登记为矩阵行，统一
进入
[`docs/archive/knowledge-base-changelog/`](archive/knowledge-base-changelog/)
或 `docs/release_evidence/`。

## 总览、治理与业务文档

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/knowledge_base_audit_matrix.md` | 活跃知识索引 | 本矩阵、质量检查器的登记/体积门禁 | current | 仅全量知识校准 |
| `docs/system_architecture_report.md` | 稳定系统拓扑、当前兼容缺口与边界 | 入口、core/default runtime、Central、Worker、schema migrations、发布契约 | current | 跨模块设计 |
| `docs/SAFE_DEPLOY_GUIDE.md` | 发布快速入口 | `scripts/release.py`、不可变发布文档 | current | 只需发布入口 |
| `docs/domain/CONTEXT.md` | 共享领域词汇 | 代码模型与领域文档 | current | 术语歧义 |
| `docs/skills/README.md` | Skill 索引、context packet 与预算 | `.codex/skills`、`AGENTS.md`、质量检查器 | current | 选择/维护 Skill |
| `docs/入口职责矩阵_entry_responsibility_matrix.md` | Web/Central 入口归属与重叠 | 应用入口、router、provider 注册 | current | 新接口或职责移动 |
| `config/compat_registry.json` | 兼容层的 owner、埋点、替代入口与退出条件 | `validate_compat_registry.py`、代码埋点、数据/运行态观测 | runtime-verification-required | 新增或删除兼容层 |
| `docs/compat_seam_exit_table.md` | 兼容 registry 的人工导航与运维查询口径 | `config/compat_registry.json` | current | 删除兼容层 |
| `docs/测试与入口命名约定.md` | 测试与入口命名 | tests、公开 facade | current | 新测试/入口 |
| `docs/business/00_INDEX_业务板块分类与规范总览.md` | 业务文档索引 | business 文档 | current | 业务视角导航 |
| `docs/business/00_DICT_全局业务数据字典.md` | 业务数据字典 | schema、API、领域模型 | current | 字段/口径变更 |
| `docs/business/01_BIZ_AI创作与生成板块.md` | 生成业务能力 | task registry、入口、History | current | 产品生成能力 |
| `docs/business/02_BIZ_商业化与会员资产板块.md` | 商业化与资产 | billing/auth/payment | current | 计费与会员 |
| `docs/business/03_BIZ_社区广场与社交互动板块.md` | 社区业务 | Gallery API/service | current | 社区产品 |
| `docs/business/04_BIZ_用户修为与身份权限体系.md` | 用户身份与权限 | user/auth/quota | current | 身份权限 |
| `docs/business/image_to_image_flow.md` | 图生图业务流 | task registry、FSM/Web、worker patcher | current | 图生图改动 |
| `docs/business/image_to_video_flow.md` | 图生视频业务流 | registry、FSM/Web、Wan22/LTX worker | current | 视频生成改动 |
| `docs/company_operations/00_INDEX.md` | 公司运营知识总览与月结闭环 | 专项文档、本机保险库契约、外部平台事实 | current | 公司管理导航 |
| `docs/company_operations/01_主体账户与备案.md` | 主体、门户、账号角色与备案登记簿 | 营业执照、平台账户、主管机关登记 | runtime-verification-required | 主体或账户资料 |
| `docs/company_operations/02_税务申报与合规日历.md` | 税种、期限、申报与回执 | 电子税务局、税法、私密申报台账 | runtime-verification-required | 报税与征期 |
| `docs/company_operations/03_资金银行与支付对账.md` | 银行、支付结算与四方对账 | 银行/渠道流水、产品订单、会计凭证 | runtime-verification-required | 收付款与对账 |
| `docs/company_operations/04_会计账簿与成本凭证.md` | 账簿、成本、报销与档案 | 原始凭证、会计账、税务规则 | current | 记账与成本 |
| `docs/company_operations/05_本机私密资料与证据库.md` | 凭据、证件与证据的本机保管契约 | XDG 私密目录、校验脚本 | runtime-verification-required | 秘密或证件 |
| `docs/company_operations/06_网站与AI服务合规.md` | ICP、隐私、算法/模型与 AI 标识 | 工信部/网信办规则、线上页面 | runtime-verification-required | 网站或 AI 合规 |

## 任务、Bot、Web 与社区

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/子模块_任务调度_task_scheduler.md` | TaskApplication、提交 intent、due finalizer、队列与清理 | `src/core/task_application.py`、`task_core*`、`task_web_finalizer.py`、QueueManager | current | 任务生命周期 |
| `docs/子模块_生成任务全链路_task_full_chain.md` | 入口到结果的完整链路与生成 task type contract | Web/Bot、Central、Worker、History | current | 跨层任务或任务类型改动 |
| `docs/子模块_中控API与节点通信_central_api.md` | Central/Agent 队列、资产完整性、状态协议与任务类型门禁 | `backend/app`、API client、Worker | current | 队列、worker 协议或 task enum |
| `docs/子模块_任务黄金路径回归清单_task_golden_path.md` | 端到端行为清单 | public facade/API/FSM/provider tests | current | 高风险回归 |
| `docs/子模块_交互状态机_fsm_handlers.md` | Telegram FSM/callback/file、返佣兑 USDT | handlers、runtime bootstrap、FSM services | current | Bot 交互 |
| `docs/子模块_Telegram本地API与文件代理_tg_local_api.md` | Bot API/file endpoint | runtime bootstrap、Bot env、当次节点探测 | runtime-verification-required | Telegram 文件/代理 |
| `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md` | 官方 QQCC 与 Config | QQCC code、config service、focused tests | current | QQCC 功能 |
| `docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md` | 私有 Bot webhook/租户 | schema、credentials、worker、owner/admin API | current | 私有 QQCC |
| `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` | 独立审核 Bot | paid group code/config | current | 入群审核 |
| `docs/子模块_独立群管理Bot_standalone_group_manage_bot.md` | 独立群管理 Bot | group manage code/config | current | 消息治理 |
| `docs/子模块_客服Bot_support_bot.md` | 客服工单 Bot | support bot、Dashboard、schema | current | 客服能力 |
| `docs/子模块_Telegram观察与报告Bot_observer_bot.md` | Observer Bot 的通知、队列监控、群采集和 LM Studio 报告 | `observer_bot/`、schema、发布/env 契约 | current | Observer 开发或运维 |
| `docs/子模块_用户认证与权限_user_auth_permission.md` | JWT/密码/权限 | auth core、Web security | current | 鉴权 |
| `docs/子模块_计费与支付_billing_payment.md` | 账本、支付、支付宝直连白名单、affiliate、USDT 人工出款 | billing core、payment providers、RMB reconciliation jobs | current | 金钱与会员 |
| `docs/子模块_社区与存储_gallery_storage.md` | Gallery 一致性、R2、apply-context | Gallery core/services、migration、audit/storage scripts | current | 社区/媒体 |
| `docs/子模块_后台监控与清理_dashboard_monitoring.md` | Dashboard 监控治理、返佣人工出款 | Dashboard backend/frontend | current | 管理后台 |
| `docs/子模块_本地数据分析平台_local_analytics_platform.md` | LAN 分析平台、shadow/派生数据边界与分层新鲜度 | local analytics routes/refreshers、shadow pipeline、Compose/live state | runtime-verification-required | 本地分析开发或运维 |
| `docs/子模块_本地数据分析平台提示词词义分析_prompt_semantics.md` | 提示词词元治理 | prompt rule/materialization code | current | 词元治理 |
| `docs/子模块_本地媒体归档_local_media_archive.md` | History 媒体目录、NAS MinIO、恢复与冷清理 | archive core/outbox/API/Worker/Compose | runtime-verification-required | 全量媒体归档 |

## 模型、GPU 与运行环境

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/子模块_附加模型配置指南_comfy_models.md` | workflow/LoRA/模型注入 | canonical Worker、workflow JSON、mapping、patcher | current | 模型/workflow |
| `docs/子模块_LTX25视频高清化_ltx25_video_upscale.md` | LTX-2.5 IC V2V 2x 视频高清化、模型许可、独立 GPU profile、RunPod/LAN `all` 内 prod/test 双 consumer 与入口门禁 | task registry、workflow/patcher、model manifest、Web/Bot、RunPod/LAN runtime | runtime-verification-required | 视频高清化开发/发布 |
| `docs/子模块_MiniMaxH3视频服务_minimax_h3.md` | MiniMax H3 四个公开模式、10Eros Beta4 TURBO 与官方 INT8 模式专属执行 profile、Web 有序上传/私人人物 typed refs、十八个候选 LoRA（单次最多十三个，含 REF2V-only 与 T2V/I2V-only 变体）、分阶段入口、test/prod Worker 共享 ComfyUI 并存边界、26 文件模型包和 canary | task registry、API workflow、profile、model manifest、人物引用解析器 | runtime-verification-required | MiniMax H3 开发/发布 |
| `docs/子模块_本地多模态LLM提示词优化_prompt_optimizer.md` | 本地 VLM 提示词优化与 task profile | task registry、workflow mapping/patcher、模型专项文档、运行时 canary | runtime-verification-required | 接入图片/原始提示词优化，或维护模型专用 meta-prompt |
| `docs/子模块_Prompt_Optimizer_Worker.md` | 通用优化 Registry/API/Worker/文本结果 | `src/prompt_optimizer/`、Web API、Prompt Worker、Dashboard scene config | current | Registry template 不可变；管理端 current config 通过 revision/hash/rendered snapshot 固定新任务语义 |
| `docs/子模块_3D角色MiniApp_avatar_miniapp.md` | LAN 3D 角色工作室、fixture 与 CPU 渲染 | `src/avatar_miniapp`、Vue、Compose、focused tests | current | 3D Mini App 开发或本地验收 |
| `docs/子模块_LTX文生视频与人物一致性_ltx_t2v_characters.md` | 独立私人人物身份素材与 LTX T2V/人物一致性 | domain config、独立人物/特写开关、人物库自由合成图、H3 独立子图引用、局部模板库、legacy/官方 LTX 面板、官方/上传环境、Runexx 两阶段 workflow、10Eros/Licon manifest、Prompt scene snapshot、LAN canary | current | 新私人人物任意槽至少一图形成 library mosaic，H3 逐张选择 1–4 个 ready 子图；旧/官方四视图 v3 面板才进入 LTX；test-only IC 固定两个 typed 角色引用加一个环境引用 |
| `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` | GPU/RunPod/LAN 稳定边界、test/prod agent 共享 ComfyUI 并存语义 | release manifest、provider、catalog、ledger、LAN-only `all` profile | runtime-verification-required | GPU 设计/运维；`all` 只允许 LAN AIO exact-digest takeover |
| `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` | LAN GPU 主机与 ComfyUI | live 节点、受控 helper | runtime-verification-required | LAN 节点 |
| `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md` | LAN SSH 契约 | SSH config/key metadata | runtime-verification-required | LAN 登录 |
| `docs/子模块_LAN_AIO本地资源管理平台_lan_resource_manager.md` | LAN 管理、A–H 多选集成/对齐与模块多选发布 UI/runner | `lan_resource_manager`、workspace coordinator、`release.py` | current | 本地资源平台 |
| `docs/子模块_局域网备份图库_lan_media_gallery.md` | LAN 只读图片视频浏览与媒体白名单 | `lan_media_gallery/compose.yml`、运行态挂载检查 | runtime-verification-required | 备份图库部署与运维 |
| `docs/子模块_系统资源与容量画像_resource_inventory.md` | 资源和容量快照 | 当次只读探测 | runtime-verification-required | 容量规划 |
| `docs/子模块_容灾与持久化_database_recovery.md` | 数据库/Redis 恢复 | schema、backup/restore scripts | current | 数据恢复 |

## 发布、网络与仓库治理

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `docs/子模块_Git不可变发布_git_immutable_release.md` | 独立模块内容寻址构建、GitHub 手动 workflow、部署、远程状态与回滚 | `scripts/release.py`、`deploy/module-catalog.json`、`.github/workflows/module-*.yml`、focused tests | current | 发布变更/执行 |
| `docs/子模块_独立媒体增强平台_media_enhance_platform.md` | 独立媒体增强产品边界、账本、任务与 Worker 契约 | `media_enhance_platform/`、专项 focused tests | current | 媒体增强平台 |
| `docs/子模块_运维指南与容器管理_ops_deployment.md` | 症状分诊、独立模块发布、服务/config/数据库 mutation 总门禁 | module catalog、release CLI、env/service contracts、目标 live state | current | 一般运维与环境变更 |
| `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` | test 控制面/Worker 拓扑、与正式 Worker 共享 ComfyUI 的长期并存边界、Dashboard 与单模块 exact-digest SOP | test overlay/env contract、Worker Compose、remote module state | runtime-verification-required | 测试环境 |
| `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` | prod 拓扑与单模块 exact-digest SOP | prod overlay/env contract、remote module state | runtime-verification-required | 正式环境 |
| `docs/子模块_本地正式灾备切换_local_prod_fallback.md` | 云故障本地接管 | fallback scripts、DNS/数据门禁 | current | 灾备 |
| `docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md` | 云 SSH 密钥边界、build/root 别名与 SGP1 Runner/Buildx 用户上下文 | key metadata、host config、GitHub Runner API、systemd/Buildx 只读探测 | runtime-verification-required | 云登录/Runner 运维 |
| `docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md` | DNS/Tunnel/Access/Pages/R2 | Cloudflare 配置与只读探测 | runtime-verification-required | 公网入口 |
| `docs/子模块_网络暴露与代理穿透_network_proxy.md` | 网络与代理边界 | compose/network/Cloudflare config | current | 网络改动 |
| `docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md` | 当前 main 最小写保护 | GitHub live ruleset、handoff 协调器边界 | runtime-verification-required | main 写权限或 ruleset 变更 |
| `docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md` | A–H/handoff/轻量 main 协调 | workspace scripts、integration queue | current | 并发开发 |
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
| `docs/adr/0003-git-sha-immutable-image-promotion.md` | 旧晋级身份 | ADR 0009 | superseded | 历史原因 |
| `docs/adr/0004-three-release-tracks-and-thin-images.md` | 旧三轨发布 | ADR 0009 | superseded | 历史原因 |
| `docs/adr/0005-four-ai-worktrees-and-test-train.md` | 旧 test-train 决策 | ADR 0008 | superseded | 历史原因 |
| `docs/adr/0006-risk-based-artifact-release-gates.md` | 旧风险门禁 | ADR 0009 | superseded | 历史原因 |
| `docs/adr/0007-promote-tested-candidate-artifacts.md` | 旧 candidate 晋级 | ADR 0009 | superseded | 历史原因 |
| `docs/adr/0008-main-first-release-batches.md` | 旧 main-first 批次 | ADR 0009 | superseded | 历史原因 |
| `docs/adr/0009-operator-decides-module-release.md` | 人工结果与独立模块发布 | module catalog、release/coordinator scripts | current | 当前发布设计 |
| `docs/adr/0010-observer-bot-isolated-runtime.md` | Observer 独立进程、逻辑数据库与本地 LM Studio 边界 | `observer_bot/`、schema、发布契约 | current | Observer 架构取舍 |

## 项目 Skills

| 路径 | 用途 | 事实源 | 状态 | 何时加载 |
| --- | --- | --- | --- | --- |
| `.codex/skills/allbot-task-engine/SKILL.md` | 任务生命周期路由 | task core/Central/Worker docs | current | 任务改动 |
| `.codex/skills/allbot-billing-auth/SKILL.md` | 计费鉴权红线 | billing/auth code | current | 金钱/身份 |
| `.codex/skills/allbot-gallery-storage/SKILL.md` | Gallery/R2 路由 | Gallery/storage code | current | 社区/存储 |
| `.codex/skills/allbot-tg-fsm/SKILL.md` | Telegram FSM 路由 | handlers/runtime services | current | Bot 交互 |
| `.codex/skills/allbot-observer-bot/SKILL.md` | Observer Bot 路由 | Observer 代码、专项文档与发布契约 | current | 通知、队列告警或群报告 |
| `.codex/skills/allbot-qqcc-lazy-bot/SKILL.md` | QQCC 官方/私有 Bot 路由 | QQCC code/docs | current | QQCC |
| `.codex/skills/allbot-ops-deployment/SKILL.md` | 发布运维路由 | release/compose/docs | current | 运维 |
| `.codex/skills/allbot-concurrent-workspaces/SKILL.md` | A–H/handoff 路由 | workspace/integration scripts | current | 仓库写任务 |
| `.codex/skills/allbot-cloudflare-ops/SKILL.md` | Cloudflare 路由 | Cloudflare config/docs | current | 公网入口 |
| `.codex/skills/allbot-cloud-ssh/SKILL.md` | 云 SSH 诊断与恢复路由 | SSH config、云控制台、访问文档 | current | 云 SSH 故障或配置 |
| `.codex/skills/allbot-comfy-models/SKILL.md` | 模型/workflow 路由 | workflow/mapping/profile | current | AI 模型 |
| `.codex/skills/allbot-prompt-optimizer/SKILL.md` | 通用提示词优化路由 | Registry/API/Prompt Worker | current | 提示词优化 |
| `.codex/skills/allbot-media-enhance-platform/SKILL.md` | 独立媒体增强平台路由 | `media_enhance_platform/`、专项文档 | current | 媒体增强平台 |
| `.codex/skills/allbot-avatar-miniapp/SKILL.md` | 3D Mini App 路由 | Mini App API/Worker/Vue/Compose | current | 3D 角色工作室 |
| `.codex/skills/allbot-lan-aio-operator/SKILL.md` | LAN AIO 操作红线 | catalog/ledger/helper | current | LAN mutation |
| `.codex/skills/allbot-lan-resource-manager/SKILL.md` | 本地资源平台 | platform/helper/docs | current | LAN UI |
| `.codex/skills/allbot-lan-media-gallery/SKILL.md` | LAN 只读备份图库 | Compose、媒体白名单、专项文档 | current | 备份媒体浏览 |
| `.codex/skills/allbot-local-analytics-prompt-semantics/SKILL.md` | 词元治理 | analytics code/docs | current | 提示词治理 |
| `.codex/skills/allbot-local-media-archive/SKILL.md` | 本地媒体归档路由 | archive code、NAS Compose、专项文档 | current | 媒体归档与冷清理 |
| `.codex/skills/allbot-kb-auto-updater/SKILL.md` | 知识同步 | docs/Skills/matrix | current | 知识变更 |
| `.codex/skills/allbot-diagnosing-bugs/SKILL.md` | Bug 反馈环 | reproduction/tests/logs | current | 故障 |
| `.codex/skills/allbot-tdd/SKILL.md` | TDD 纪律 | public seams/tests | current | 行为改动 |
| `.codex/skills/allbot-codebase-design/SKILL.md` | 架构词汇 | module/interface/seam | current | 设计重构 |
| `.codex/skills/backend-code-review/SKILL.md` | 后端审查 | backend rules | current | Python review |
| `.codex/skills/vue-best-practices/SKILL.md` | Vue 规范 | Vue code/tooling | current | 前端 |
| `.codex/skills/frontend-browser-preview/SKILL.md` | 浏览器预览 | Playwright workflow | current | UI 截图 |
| `.codex/skills/ops-log-monitor/SKILL.md` | 日志监控 | env logs/diagnostics | current | 线上日志 |
| `.codex/skills/allbot-code-analyzer/SKILL.md` | 静态分析 | analyzer workflow | current | 全局审查 |
| `.codex/skills/allbot-company-operations/SKILL.md` | 公司运营、财税与私密资料路由 | 公司运营专项文档、XDG 保险库、主管机关 | current | 公司管理、报税、银行/商户或备案 |
