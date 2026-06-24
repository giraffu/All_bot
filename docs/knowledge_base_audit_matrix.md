# AllBot Knowledge Base Audit Matrix

本矩阵记录 2026-06-24 对 AllBot 实时知识库的逐项核对结果。事实源优先级为当前代码、compose、脚本、Alembic、`pytest --collect-only` 与 `ruff check`；本轮不做远端 SSH、线上 curl 或 Docker 运行态探测。

## 1. 本轮校准基线

| 项目 | 当前事实 |
| :--- | :--- |
| Git 分支 / 提交 | `deploy` / `9a91388` |
| Alembic | 单 head：`7f3a9c1d2e4b` |
| 测试收集 | `pytest --collect-only -q` 收集 `1678` 个测试，用时约 74 秒 |
| Ruff | `ruff check --statistics` 剩余 `2` 个 `F401`，均在 `ops/gpu_pool_controller/runpod_pod_request.py` |
| 云测试入口 | 日常维护式更新首选 `scripts/update_cloud_test_with_maintenance.sh --execute`；远端控制面重建子步骤为 `scripts/safe_deploy_cloud_test.sh` |
| 云正式入口 | 正式发布需明确确认；控制面入口为 `scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod` 或 `scripts/safe_deploy_cloud_prod.sh` 子步骤 |
| 旧本地脚本 | `safe_deploy.sh` 只用于云正式整体故障时的本地正式灾备；`safe_deploy_test.sh` 只作历史取证 |
| 归档材料 | `docs/archive/` 与 `logs/` 只作历史证据或排障报告，不作为当前 SOP |

## 2. 总览与索引文档

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `README.md` | `docs/` 清单、`.github/workflows/docs_ci.yml`、部署脚本 | 已修正 | 增加知识库矩阵入口；同步云测试维护式更新口径 |
| `AGENTS.md` | `.codex/skills/*/SKILL.md`、运维脚本 | 已修正 | 测试优先部署改为维护式更新脚本优先，补充矩阵导览 |
| `docs/knowledge_base_audit_matrix.md` | 本轮只读扫描与校验命令 | 新增 | 作为后续知识库校准台账 |
| `docs/system_architecture_report.md` | compose、RunPod/Dashboard 服务、测试收集、ruff | 已修正 | 更新 2026-06-24 轻量复核、autoscaler、云测试 worker 口径 |
| `docs/skills/README.md` | `.codex/skills` 清单 | 已修正 | 增加矩阵维护约定，避免 Skill 与 docs 漂移 |
| `docs/domain/CONTEXT.md` | 领域文档与运维脚本 | 已修正 | 补充实时知识库、归档材料、运行态快照、维护式更新等术语 |
| `docs/adr/0000-template.md` | ADR 模板 | 已核对 | 模板有效，无需新增 ADR |

## 3. 任务、Worker、Comfy 与 RunPod

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_任务调度_task_scheduler.md` | `src/core/task_core*.py`、`src/task_core_process_defaults.py`、部署脚本 | 已修正 | 部署章节同步云测试维护式更新入口 |
| `docs/子模块_生成任务全链路_task_full_chain.md` | `src/web_api/services/*task*`、`backend/app`、`workers/comfy_agent` | 已核对 | 主链路仍符合现状；保留长链路排障细节 |
| `docs/子模块_中控API与节点通信_central_api.md` | `backend/app/main.py`、`backend/app/queue_manager.py`、worker relay | 已核对 | Central / worker protocol 口径有效 |
| `docs/子模块_任务黄金路径回归清单_task_golden_path.md` | `tests/backend`、`tests/core`、`tests/web_api`、worker tests | 已核对 | 回归分组仍可用 |
| `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` | `ops/gpu_pool_controller`、Dashboard RunPod 服务、RunPod scripts | 已核对 | 已包含 Dashboard autoscaler 与 RunPod/LAN AIO 当前边界 |
| `docs/子模块_附加模型配置指南_comfy_models.md` | `workers/comfy_agent/workflows`、`remote_workers`、workflow patcher | 已核对 | workflow 事实源和 SCAIL-2/LTX 口径有效 |
| `docs/compat_seam_exit_table.md` | compat 文件现状、`rg` 引用 | 已核对 | 作为 compat 清理挂账表保留 |
| `docs/双入口重复能力_inventory.md` | `backend/app`、`src/web_api` | 已核对 | 双入口分层描述有效 |
| `docs/入口职责矩阵_entry_responsibility_matrix.md` | Web/Central/Dashboard/Payment/Bot entrypoints | 已核对 | 入口职责有效 |
| `docs/测试与入口命名约定.md` | 测试目录与入口命名 | 已核对 | 命名约定有效 |
| `docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md` | hotspot docs、tests、compat 状态 | 已核对 | 长文档保留为门禁清单 |
| `docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md` | `.github/workflows`、hotspot guardrails | 已核对 | 分支保护和回归门禁说明有效 |

## 4. Bot 与交互

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_交互状态机_fsm_handlers.md` | `src/handlers`、FSM tests | 已核对 | 主 Bot FSM 边界有效 |
| `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md` | `qqcc_bot/main.py`、cloud compose QQCC profile | 已核对 | 独立 token、`bot:qqcc` 来源、双 polling 红线有效 |
| `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` | `paid_group_guard_bot`、Dashboard paid group router/service、cloud compose | 已核对 | 独立 Bot 与 Dashboard 配置管理边界有效 |
| `docs/子模块_Telegram本地API与文件代理_tg_local_api.md` | Telegram API env、Bot file handling | 已核对 | 文件代理边界有效 |

## 5. Web、商业化、社区与后台

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_用户认证与权限_user_auth_permission.md` | `src/core/auth_core*`、`src/web_api/core/security.py` | 已核对 | JWT、password_version、权限复核口径有效 |
| `docs/子模块_计费与支付_billing_payment.md` | `src/core/billing_core*`、`src/payment_api_server.py`、affiliate migrations | 已核对 | 支付履约与 affiliate 账本口径有效 |
| `docs/子模块_社区与存储_gallery_storage.md` | `src/core/gallery*`、`src/web_api/services/*gallery*`、R2 scripts | 已核对 | R2/legacy MinIO 退出口径有效 |
| `docs/子模块_后台监控与清理_dashboard_monitoring.md` | `dashboard/backend`、`dashboard/frontend`、RunPod admin services | 已核对 | Dashboard 监控和清理边界有效 |
| `docs/business/00_INDEX_业务板块分类与规范总览.md` | business docs | 已核对 | 业务导航有效 |
| `docs/business/00_DICT_全局业务数据字典.md` | models、domain config、business docs | 已核对 | 数据字典有效 |
| `docs/business/01_BIZ_AI创作与生成板块.md` | task type registry、FSM、Web task routes | 已核对 | 生成业务描述有效 |
| `docs/business/02_BIZ_商业化与会员资产板块.md` | billing/auth/affiliate code | 已核对 | 商业化描述有效 |
| `docs/business/03_BIZ_社区广场与社交互动板块.md` | Gallery models/services | 已核对 | 社区描述有效 |
| `docs/business/04_BIZ_用户修为与身份权限体系.md` | User model、auth core、permission service | 已核对 | 用户体系描述有效 |
| `docs/business/image_to_image_flow.md` | image FSM/task routes | 已核对 | 图生图流程有效 |
| `docs/business/image_to_video_flow.md` | video FSM/task routes、Wan22/LTX/SCAIL-2 docs | 已核对 | 图生视频流程有效 |

## 6. 运维与环境

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/SAFE_DEPLOY_GUIDE.md` | deploy scripts、cloud compose | 已修正 | 云测试主入口改为维护式更新脚本，`safe_deploy_cloud_test.sh` 标为子步骤 |
| `docs/子模块_运维指南与容器管理_ops_deployment.md` | deploy scripts、compose、ops Skill | 已核对 | 运维总口径有效 |
| `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` | `deploy/docker-compose-cloud-test.yml`、`scripts/update_cloud_test_with_maintenance.sh` | 已核对 | 云测试 SOP 以维护式更新为主，仍有效 |
| `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` | `deploy/docker-compose-cloud-prod.yml`、`scripts/update_cloud_prod_with_maintenance.sh`、Dashboard autoscaler env | 已核对 | 云正式 SOP 有效 |
| `docs/子模块_本地正式灾备切换_local_prod_fallback.md` | `safe_deploy.sh`、cloud prod scripts | 已核对 | 仅灾备使用的边界有效 |
| `docs/子模块_网络暴露与代理穿透_network_proxy.md` | Cloudflare/Tunnel scripts、network docs | 已核对 | 网络入口和回滚边界有效 |
| `docs/子模块_边缘节点运维指南_edge_node_ops.md` | edge docs、cloud prod preflight | 已核对 | 边缘节点说明有效 |
| `docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md` | SSH docs、cloud compose | 已核对 | 不含私钥，作为登录边界文档保留 |
| `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md` | LAN SSH docs、GPU resource docs | 已核对 | 不含私钥，作为节点访问文档保留 |
| `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` | LAN AIO scripts、GPU pool config、worker compose | 已核对 | 长运行态文档保留，容量需按实时探测复核 |
| `docs/子模块_系统资源与容量画像_resource_inventory.md` | compose、resource docs、deployment scripts | 已修正 | 云正式/云测试入口口径更新；运行态快照仍需人工探测 |
| `docs/子模块_容灾与持久化_database_recovery.md` | migrations、runtime checkpoint code | 已核对 | 恢复主链有效 |
| `docs/子模块_代码静态分析与质量评估规范_code_quality.md` | `pytest --collect-only`、`ruff check`、Alembic | 已修正 | 增加 2026-06-24 轻量复核结果 |
| `docs/子模块_前端浏览器预览截图_frontend_browser_preview.md` | Playwright preview skill | 已核对 | 前端截图验收口径有效 |

## 7. 归档材料

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/archive/2026-06-cloud-migration/README.md` | 归档索引 | 归档确认 | 已明确“不作为当前 SOP” |
| `docs/archive/2026-06-cloud-migration/正式云环境切换前准备清单.md` | 历史迁云记录 | 归档确认 | 不重写历史证据 |
| `docs/archive/2026-06-cloud-migration/子模块_Cloudflare_Pages与API_Tunnel测试入口迁移_runbook.md` | 历史 runbook | 归档确认 | 不重写历史证据 |
| `docs/archive/2026-06-cloud-migration/变更说明_web历史原视频R2优先链路.md` | 历史变更说明 | 归档确认 | 不重写历史证据 |
| `docs/archive/2026-06-cloud-migration/问题分析_web老任务恢复导致无效状态轮询.md` | 历史问题分析 | 归档确认 | 不重写历史证据 |
| `docs/archive/2026-06-runtime-canaries/README.md` | 归档索引 | 归档确认 | 已明确“不作为当前 SOP 或容量事实源” |
| `docs/archive/2026-06-runtime-canaries/LAN_AIO_PROD_CANARY_20260616.md` | 一次性 canary | 归档确认 | 不重写历史证据 |
| `docs/archive/2026-06-runtime-canaries/lan_model_cache_upload_2026-06-15.md` | 一次性模型上传记录 | 归档确认 | 不重写历史证据 |

## 8. Skills 与 Skill 附属文件

| 文件 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `.codex/skills/allbot-kb-auto-updater/SKILL.md` | 本矩阵、KB 维护流程 | 已修正 | 补充核对矩阵输出要求 |
| `.codex/skills/allbot-ops-deployment/SKILL.md` | deploy scripts、compose | 已核对 | 已包含云测试维护式更新和云正式 autoscaler 口径 |
| `.codex/skills/allbot-task-engine/SKILL.md` | task core、queue manager、runtime cleanup | 已核对 | 任务生命周期边界有效 |
| `.codex/skills/allbot-comfy-models/SKILL.md` | workflow patcher、remote_workers | 已核对 | workflow/模型边界有效 |
| `.codex/skills/allbot-tg-fsm/SKILL.md` | `src/handlers`、Bot entrypoint | 已核对 | FSM 边界有效 |
| `.codex/skills/allbot-qqcc-lazy-bot/SKILL.md` | `qqcc_bot`、cloud compose | 已核对 | QQCC 独立 Bot 边界有效 |
| `.codex/skills/allbot-billing-auth/SKILL.md` | auth/billing/affiliate code | 已核对 | 计费鉴权边界有效 |
| `.codex/skills/allbot-gallery-storage/SKILL.md` | Gallery/R2 code | 已核对 | 存储与社区边界有效 |
| `.codex/skills/allbot-diagnosing-bugs/SKILL.md` | bug 诊断流程 | 已核对 | 诊断闭环有效 |
| `.codex/skills/allbot-tdd/SKILL.md` | tests、dependencies seam | 已核对 | TDD seam 口径有效 |
| `.codex/skills/allbot-codebase-design/SKILL.md` | 架构词汇 | 已核对 | 设计词汇有效 |
| `.codex/skills/allbot-code-analyzer/SKILL.md` | 静态分析规范 | 已核对 | 只读/报告/清理规范有效 |
| `.codex/skills/backend-code-review/SKILL.md` | backend review references | 已核对 | 审查规范有效 |
| `.codex/skills/vue-best-practices/SKILL.md` | Vue 3 frontend | 已核对 | 前端规范有效 |
| `.codex/skills/frontend-browser-preview/SKILL.md` | Playwright preview workflow | 已核对 | 截图验收规范有效 |
| `.codex/skills/ops-log-monitor/SKILL.md` | log/report workflow | 已核对 | 日志监控边界有效 |
| `.codex/skills/*/references/*.md` | 对应 Skill | 已核对 | reference 文件保持作为按需深读材料 |
| `.codex/skills/*/agents/openai.yaml` | 子代理配置 | 已核对 | 配置文件不作为长期业务知识正文 |
