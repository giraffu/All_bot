# 修仙主题 AI 创作工作台 (All_Bot)

本项目是一个跨平台 (Telegram / Web / TON) 的多节点分布式 AI 图像与视频生成工作台。具备完备的用户等级（凡人至真传弟子）、单轨制计费（灵石）、防死锁任务调度阵列（ComfyUI），以及支持大文件预签名直传和 R2 边缘加速的画廊社区系统。

## 系统核心架构

系统采用 BFF 架构和多服务编排：
- **Web API**: FastAPI 提供 REST/SSE 和 JWT 鉴权
- **TG Bot**: Python-Telegram-Bot 处理 Telegram Update
- **Payment API**: 独立回调服务保障资产一致性
- **Worker Node**: ComfyUI 阵列与 Redis Pub/Sub 队列通信
- **CS Bot**: LangGraph 驱动，接入宿主机 LM Studio

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
- [All_Bot 安全更新与部署脚本 (`safe_deploy.sh` / `safe_deploy_test.sh`) 使用说明](./docs/SAFE_DEPLOY_GUIDE.md)
- [Compat / Seam 退出表](./docs/compat_seam_exit_table.md)
- [修仙主题 AI 创作工作台 - 系统架构与业务分析报告](./docs/system_architecture_report.md)
- [双入口职责矩阵](./docs/入口职责矩阵_entry_responsibility_matrix.md)
- [双入口重复能力 Inventory](./docs/双入口重复能力_inventory.md)
- [Web 历史原视频 R2 优先链路变更说明](./docs/变更说明_web历史原视频R2优先链路.md)
- [GitHub 分支保护与热点回归门禁](./docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md)
- [子模块: Telegram 本地 API 与文件代理 (TG Local API)](./docs/子模块_Telegram本地API与文件代理_tg_local_api.md)
- [子模块: 中控 API 与节点通信 (Central API & Worker Communication)](./docs/子模块_中控API与节点通信_central_api.md)
- [子模块: 交互状态机与回调路由 (FSM & Callback Handlers)](./docs/子模块_交互状态机_fsm_handlers.md)
- [子模块: 代码静态分析与质量评估规范 (Code Quality & Static Analysis)](./docs/子模块_代码静态分析与质量评估规范_code_quality.md)
- [子模块: 任务调度 (Task Scheduler)](./docs/子模块_任务调度_task_scheduler.md)
- [任务黄金路径回归清单](./docs/子模块_任务黄金路径回归清单_task_golden_path.md)
- [子模块: 后台监控与清理 (Dashboard & Monitoring)](./docs/子模块_后台监控与清理_dashboard_monitoring.md)
- [子模块: 容灾与持久化 (Database & Recovery)](./docs/子模块_容灾与持久化_database_recovery.md)
- [子模块: 提示词优化 (Prompt Optimization)](./docs/子模块_提示词优化_prompt_optimization.md)
- [子模块: 智能客服 (CS Bot Agent)](./docs/子模块_智能客服_cs_bot_agent.md)
- [热点文件门禁与回归触发规则](./docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md)
- [子模块: 用户认证与权限管理 (User Auth & Permission)](./docs/子模块_用户认证与权限_user_auth_permission.md)
- [子模块: 社区广场与分级存储 (Gallery & Storage)](./docs/子模块_社区与存储_gallery_storage.md)
- [子模块: 网络暴露与代理穿透 (Network & Proxy)](./docs/子模块_网络暴露与代理穿透_network_proxy.md)
- [子模块: 计费与支付核心 (Billing & Payment)](./docs/子模块_计费与支付_billing_payment.md)
- [子模块: 边缘节点运维与网络代理 (Edge Node Ops)](./docs/子模块_边缘节点运维指南_edge_node_ops.md)
- [子模块: 运维指南与容器管理 (Ops & Deployment)](./docs/子模块_运维指南与容器管理_ops_deployment.md)
- [子模块: 附加模型部署与配置指南 (ComfyUI Add-on Models)](./docs/子模块_附加模型配置指南_comfy_models.md)
- [测试与入口命名约定](./docs/测试与入口命名约定.md)
- [Web 老任务恢复导致无效状态轮询问题分析与现状收口版](./docs/问题分析_web老任务恢复导致无效状态轮询.md)
<!-- DOCS_INDEX_END -->

## 持续集成与部署

- 本项目通过 GitHub Actions 实现对 Markdown 文档的自动校验（`markdownlint`）和自动目录更新。
- 业务代码支持通过 `docker-compose` 和边缘节点 VPN 隧道进行发布。
