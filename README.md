# 修仙主题 AI 创作工作台 (All_Bot)

本项目是一个跨平台 (Telegram / Web / TON) 的多节点分布式 AI 图像与视频生成工作台。具备完备的用户等级（凡人至真传弟子）、单轨制计费（灵石）、防死锁任务调度阵列（ComfyUI），以及支持大文件预签名直传和 R2 边缘加速的画廊社区系统。

## 系统核心架构

系统采用 BFF 架构和多服务编排：

- **Web API**: FastAPI 提供用户 REST/SSE、JWT 鉴权、历史与社区工作台接口
- **Central API**: FastAPI 承接执行面任务队列、worker heartbeat、状态/result 与系统视图
- **TG Bot / QQCC Bot / Paid Group Bot**: 多个独立 Telegram polling 入口，各自使用独立 token 与职责边界
- **Payment API**: 独立回调服务保障支付履约、会员与 affiliate 资产一致性
- **Worker Node**: 本地 worker、LAN AIO 与 RunPod worker 通过 Central/Redis/HTTP 协议驱动 ComfyUI runtime

## 业务板块与产品规范

为帮助产品经理、运营和研发团队快速了解系统的商业逻辑与操作流程，所有业务文档收敛于 `docs/business/` 目录：

- [00_INDEX_业务板块分类与规范总览](./docs/business/00_INDEX_业务板块分类与规范总览.md)
- [00_DICT_全局业务数据字典](./docs/business/00_DICT_全局业务数据字典.md)
- [01_BIZ_AI创作与生成板块](./docs/business/01_BIZ_AI创作与生成板块.md)
- [02_BIZ_商业化与会员资产板块](./docs/business/02_BIZ_商业化与会员资产板块.md)
- [03_BIZ_社区广场与社交互动板块](./docs/business/03_BIZ_社区广场与社交互动板块.md)
- [04_BIZ_用户修为与身份权限体系](./docs/business/04_BIZ_用户修为与身份权限体系.md)

## 核心与次要子模块技术索引

<!-- DOCS_INDEX_START -->
## 系统子模块架构文档索引

- [AllBot 发布入口](./docs/SAFE_DEPLOY_GUIDE.md)
- [Compat / Seam 当前退出表](./docs/compat_seam_exit_table.md)
- [AllBot Knowledge Base Audit Matrix](./docs/knowledge_base_audit_matrix.md)
- [AllBot 系统架构总览](./docs/system_architecture_report.md)
- [双入口职责矩阵](./docs/入口职责矩阵_entry_responsibility_matrix.md)
- [子模块: Cloudflare 公网入口与账号管理 (Cloudflare Ops)](./docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md)
- [子模块：GPU 算力资源池控制器](./docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md)
- [GitHub 分支保护与热点回归门禁](./docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md)
- [Git + 不可变镜像发布](./docs/子模块_Git不可变发布_git_immutable_release.md)
- [AllBot 本地资源管理平台](./docs/子模块_LAN_AIO本地资源管理平台_lan_resource_manager.md)
- [子模块：LTX 2.3 Sulphur 文生视频与 Ingredients 人物一致性](./docs/子模块_LTX文生视频与人物一致性_ltx_t2v_characters.md)
- [子模块: QQCC 懒人 Bot (QQCC Lazy Bot)](./docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md)
- [子模块: QQCC 用户私有 Bot 平台 (QQCC Private Bot Platform)](./docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md)
- [子模块: Telegram 本地 API 与文件代理 (TG Local API)](./docs/子模块_Telegram本地API与文件代理_tg_local_api.md)
- [子模块: 中控 API 与节点通信 (Central API & Worker Communication)](./docs/子模块_中控API与节点通信_central_api.md)
- [子模块: 云控制面 SSH 密钥管理 (Cloud SSH Access)](./docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md)
- [子模块: 云正式控制面部署 (Cloud Prod Control Plane)](./docs/子模块_云正式控制面部署_cloud_prod_control_plane.md)
- [子模块: 云测试控制面部署 (Cloud Test Control Plane)](./docs/子模块_云测试控制面部署_cloud_test_control_plane.md)
- [子模块: 交互状态机与回调路由 (FSM & Callback Handlers)](./docs/子模块_交互状态机_fsm_handlers.md)
- [子模块: 付费群审核 Bot (Paid Group Guard Bot)](./docs/子模块_付费群审核Bot_paid_group_guard_bot.md)
- [子模块: 代码静态分析与质量评估规范 (Code Quality & Static Analysis)](./docs/子模块_代码静态分析与质量评估规范_code_quality.md)
- [子模块: 任务调度 (Task Scheduler)](./docs/子模块_任务调度_task_scheduler.md)
- [任务黄金路径回归清单](./docs/子模块_任务黄金路径回归清单_task_golden_path.md)
- [子模块：前端浏览器预览与截图](./docs/子模块_前端浏览器预览截图_frontend_browser_preview.md)
- [子模块: 后台监控与清理 (Dashboard & Monitoring)](./docs/子模块_后台监控与清理_dashboard_monitoring.md)
- [独立客服 Bot](./docs/子模块_客服Bot_support_bot.md)
- [子模块: 容灾与持久化 (Database & Recovery)](./docs/子模块_容灾与持久化_database_recovery.md)
- [子模块: 局域网 GPU 节点 SSH 管理 (LAN GPU SSH Access)](./docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md)
- [子模块: 局域网 GPU 节点资源与运维 (LAN GPU Resource Ops)](./docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md)
- [子模块：并发 AI 工作区与不可变 handoff 集成](./docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md)
- [子模块: 本地数据分析平台 (Local Analytics Platform)](./docs/子模块_本地数据分析平台_local_analytics_platform.md)
- [本地数据分析平台提示词词义分析指南](./docs/子模块_本地数据分析平台提示词词义分析_prompt_semantics.md)
- [子模块：本地正式灾备切换](./docs/子模块_本地正式灾备切换_local_prod_fallback.md)
- [子模块: 生成任务全链路 (Task Full Chain)](./docs/子模块_生成任务全链路_task_full_chain.md)
- [子模块: 用户认证与权限管理 (User Auth & Permission)](./docs/子模块_用户认证与权限_user_auth_permission.md)
- [子模块: 社区广场与分级存储 (Gallery & Storage)](./docs/子模块_社区与存储_gallery_storage.md)
- [子模块: 系统资源与容量画像 (Resource Inventory)](./docs/子模块_系统资源与容量画像_resource_inventory.md)
- [子模块：网络暴露与代理穿透](./docs/子模块_网络暴露与代理穿透_network_proxy.md)
- [子模块: 计费与支付核心 (Billing & Payment)](./docs/子模块_计费与支付_billing_payment.md)
- [子模块: 运维指南与容器管理 (Ops & Deployment)](./docs/子模块_运维指南与容器管理_ops_deployment.md)
- [子模块: 附加模型部署与配置指南 (ComfyUI Add-on Models)](./docs/子模块_附加模型配置指南_comfy_models.md)
- [并发 AI 自动接单使用指南](./docs/并发AI自动接单使用指南_auto_workspace_claim.md)
- [测试与入口命名约定](./docs/测试与入口命名约定.md)
<!-- DOCS_INDEX_END -->

历史迁云、一次性变更说明和问题复盘已归档到 [`docs/archive/2026-06-cloud-migration/`](./docs/archive/2026-06-cloud-migration/README.md) 与 [`docs/archive/2026-06-runtime-canaries/`](./docs/archive/2026-06-runtime-canaries/README.md)。归档材料不作为当前部署 SOP，排障报告默认保留在 `logs/`。

## 集成与发布

- A–H 功能槽位提交并推送任务分支后写入不可变 handoff；本机单写者逐项合并并
  推送 main，不创建逐任务 PR，也不把 CI 或共享测试站作为 main 合入门禁。
- 发布由操作者从完整 Git SHA 运行 `scripts/release.py build --module ...`，再把
  精确 digest 部署到明确环境。test 与 prod 各自选择 artifact；不存在“必须先在
  test 晋级同一 digest”这一自动资格链。
- 生产、数据库、Cloudflare、RunPod/GPU/LAN 与灾备 mutation 必须由用户明确
  授权。禁止源码/env rsync、目标机 build、源码 bind mount、mutable tag 和
  force push main。
