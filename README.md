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
- [Compat / Seam 退出表](./docs/compat_seam_exit_table.md)
- [AllBot Knowledge Base Audit Matrix](./docs/knowledge_base_audit_matrix.md)
- [修仙主题 AI 创作工作台 - 系统架构与业务分析报告](./docs/system_architecture_report.md)
- [双入口职责矩阵](./docs/入口职责矩阵_entry_responsibility_matrix.md)
- [双入口重复能力 Inventory](./docs/双入口重复能力_inventory.md)
- [GitHub 分支保护与热点回归门禁](./docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md)
- [子模块: Telegram 本地 API 与文件代理 (TG Local API)](./docs/子模块_Telegram本地API与文件代理_tg_local_api.md)
- [子模块: 中控 API 与节点通信 (Central API & Worker Communication)](./docs/子模块_中控API与节点通信_central_api.md)
- [子模块: 云控制面 SSH 密钥管理 (Cloud SSH Access)](./docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md)
- [子模块: 云正式控制面部署 (Cloud Prod Control Plane)](./docs/子模块_云正式控制面部署_cloud_prod_control_plane.md)
- [子模块: 云测试控制面部署 (Cloud Test Control Plane)](./docs/子模块_云测试控制面部署_cloud_test_control_plane.md)
- [子模块: 本地正式灾备切换 (Local Prod Fallback)](./docs/子模块_本地正式灾备切换_local_prod_fallback.md)
- [子模块: 交互状态机与回调路由 (FSM & Callback Handlers)](./docs/子模块_交互状态机_fsm_handlers.md)
- [子模块: 代码静态分析与质量评估规范 (Code Quality & Static Analysis)](./docs/子模块_代码静态分析与质量评估规范_code_quality.md)
- [子模块: 任务调度 (Task Scheduler)](./docs/子模块_任务调度_task_scheduler.md)
- [任务黄金路径回归清单](./docs/子模块_任务黄金路径回归清单_task_golden_path.md)
- [子模块: 前端浏览器预览截图](./docs/子模块_前端浏览器预览截图_frontend_browser_preview.md)
- [子模块: 后台监控与清理 (Dashboard & Monitoring)](./docs/子模块_后台监控与清理_dashboard_monitoring.md)
- [子模块: 容灾与持久化 (Database & Recovery)](./docs/子模块_容灾与持久化_database_recovery.md)
- [子模块: 局域网 GPU 节点 SSH 管理](./docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md)
- [子模块: 局域网 GPU 节点资源与运维](./docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md)
- [热点文件门禁与回归触发规则](./docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md)
- [子模块: 生成任务全链路](./docs/子模块_生成任务全链路_task_full_chain.md)
- [子模块: 用户认证与权限管理 (User Auth & Permission)](./docs/子模块_用户认证与权限_user_auth_permission.md)
- [子模块: 社区广场与分级存储 (Gallery & Storage)](./docs/子模块_社区与存储_gallery_storage.md)
- [子模块: 系统资源与容量画像](./docs/子模块_系统资源与容量画像_resource_inventory.md)
- [子模块: 网络暴露与代理穿透 (Network & Proxy)](./docs/子模块_网络暴露与代理穿透_network_proxy.md)
- [子模块: 计费与支付核心 (Billing & Payment)](./docs/子模块_计费与支付_billing_payment.md)
- [子模块: 边缘节点运维与网络代理 (Edge Node Ops)](./docs/子模块_边缘节点运维指南_edge_node_ops.md)
- [子模块: 运维指南与容器管理 (Ops & Deployment)](./docs/子模块_运维指南与容器管理_ops_deployment.md)
- [子模块: 附加模型部署与配置指南 (ComfyUI Add-on Models)](./docs/子模块_附加模型配置指南_comfy_models.md)
- [All_Bot 本地旧部署脚本说明 (`safe_deploy.sh` / `safe_deploy_test.sh`)](./docs/SAFE_DEPLOY_GUIDE.md)
- [测试与入口命名约定](./docs/测试与入口命名约定.md)
<!-- DOCS_INDEX_END -->

历史迁云、一次性变更说明和问题复盘已归档到 [`docs/archive/2026-06-cloud-migration/`](./docs/archive/2026-06-cloud-migration/README.md) 与 [`docs/archive/2026-06-runtime-canaries/`](./docs/archive/2026-06-runtime-canaries/README.md)。归档材料不作为当前部署 SOP，排障报告默认保留在 `logs/`。

## 持续集成与部署

- 本项目通过 GitHub Actions 实现对 Markdown 文档的自动校验（`markdownlint`）和自动目录更新。
- 当前研发验证首选云测试控制面，日常维护式更新入口为 `scripts/update_cloud_test_with_maintenance.sh --execute`；正式热修走云正式 compose / cloud deploy 脚本；本地 `safe_deploy.sh` 只保留为云正式整体故障时的临时本地正式灾备入口。
