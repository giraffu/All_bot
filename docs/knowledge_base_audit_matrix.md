# AllBot Knowledge Base Audit Matrix

本矩阵记录 2026-06-27 对 AllBot 实时知识库的逐项核对结果。事实源优先级为当前代码、compose、脚本、Alembic、`pytest --collect-only`、`ruff check` 与文档结构检查；本轮不做远端 SSH、线上 curl 或 Docker 运行态探测。

## 1. 本轮校准基线

| 项目 | 当前事实 |
| :--- | :--- |
| Git 分支 / 提交 | `deploy` / `2bd2866` |
| Alembic | 单 head：`7f3a9c1d2e4b` |
| 测试收集 | `pytest --collect-only -q` 收集 `1778` 个测试，用时约 118 秒 |
| Ruff | `ruff check --statistics` 剩余 `7` 个可自动修复问题：1 个 `F541`、6 个 `F401`，集中在 `local_analytics_platform/`、`ops/gpu_pool_controller/runpod_pod_request.py`、`scripts/import_minio_bucket_normalized.py` 与测试文件 |
| 文档结构 | `python scripts/doc_quality_checker.py` 通过 |
| Core Isolation | `rg` 轻量扫描 `src/core` 未发现 Telegram `Update` 或 FastAPI `Request/APIRouter` 等平台对象 import |
| 云测试入口 | 日常维护式更新首选 `scripts/update_cloud_test_with_maintenance.sh --execute`；远端控制面重建子步骤为 `scripts/safe_deploy_cloud_test.sh` |
| 云正式入口 | 正式发布需明确确认；控制面入口为 `scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod` 或 `scripts/safe_deploy_cloud_prod.sh` 子步骤；QQCC 正式 Bot 单独更新入口为 `scripts/update_cloud_prod_qqcc_bot.sh --execute --confirm-prod --confirm-single-polling`，用户明确要求 QQCC 单服务更新即可作为当次单 polling 操作确认 |
| 本地云正式 shadow 同步 | `scripts/sync_cloud_prod_to_local_shadow.py` 默认 dry-run，`--execute` 才把云正式 PostgreSQL 恢复为本地 `bot_db_prod_shadow`；数据库获取主路径为 `CLOUD_PROD_DB_DUMP_MODE=remote_r2`，由 `allbot-do-sgp1-control` 在云机 dump 后临时上传 R2 `user-data-prod/__shadow-transfer/<timestamp>`，本地经 HTTPS/rclone 下载校验后 restore，避免依赖家宽/VPN 出口 IP 作为托管 DB trusted source；恢复 `_next` 后、切换 shadow 前默认用 `LOCAL_ANALYTICS_PRESERVE_ON_SHADOW_SYNC=true` 保留旧 shadow 中 `analytics_prompt_*` 本地分析表；`R2_BUCKET_SYNC_ENABLED=true` 时才把 R2 `user-data-prod` 增量同步到 MinIO `user-data-prod-shadow` 并用 quarantine 保留云端覆盖/删除的旧对象；`COMPLETE_MEDIA_SYNC_ENABLED=true` 时每日从本地 R2 shadow 非破坏式 copy 到 `user-data-complete-shadow`；legacy `bot-data`/`comfyui-temp` 只在手动 `--include-legacy-media-import` 首次/补漏时导入；脚本持有 `.shadow-sync.lock` 防并发；本地分析刷新入口为 `scripts/run_local_analytics_shadow_pipeline.py` 与 `allbot-local-analytics-refresh.timer`，默认每日 Asia/Shanghai 05:45；若 `.refresh_prompt_vectors.lock` 显示上一轮向量刷新仍在运行则整轮跳过，否则按 affected `prompt_hash` 增量刷新 Mart、瘦身、缺失 embedding、语义场景、相似边/近重复族，05:00 切库断线后向量阶段重连并断点续跑；embedding 未完整时语义场景和相似边阶段跳过，LM Studio 不可用但 embedding 已完整时仍允许刷新语义场景 |
| 旧本地脚本 | `safe_deploy.sh` 只用于云正式整体故障时的本地正式灾备；`safe_deploy_test.sh` 只作历史取证 |
| 归档材料 | `docs/archive/` 与 `logs/` 只作历史证据或排障报告，不作为当前 SOP |

## 2. 总览与索引文档

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `README.md` | `docs/` 清单、`.github/workflows/docs_ci.yml`、部署脚本 | 已修正 | 按 `docs/*.md` 当前清单补齐活跃索引，恢复 GPU Pool、QQCC、付费群审核、本地数据分析平台等入口；保留知识库矩阵与云测试维护式更新口径 |
| `AGENTS.md` | `.codex/skills/*/SKILL.md`、运维脚本 | 已修正 | 测试优先部署改为维护式更新脚本优先，补充矩阵导览 |
| `docs/knowledge_base_audit_matrix.md` | 本轮只读扫描与校验命令 | 已修正 | 更新 2026-06-27 基线、ruff/pytest/doc checker/Core Isolation 结果和本轮知识库处理结果 |
| `docs/system_architecture_report.md` | compose、RunPod/Dashboard/本地分析服务、测试收集、ruff | 已修正 | 更新 2026-06-27 轻量复核、autoscaler 预计清空时间模型、云测试 worker 口径，并补充 `local_analytics_platform` 独立只读 shadow 分析入口 |
| `docs/skills/README.md` | `.codex/skills` 清单与本轮 Skill 体积审计 | 已修正 | 增加矩阵维护约定和 Skill 正文体积维护规则；记录 `allbot-ops-deployment`、`allbot-comfy-models` 与 `allbot-task-engine` 已瘦身，`allbot-gallery-storage` 已折叠超长行 |
| `docs/domain/CONTEXT.md` | 领域文档、运维脚本、本地分析平台代码与文档 | 已修正 | 补充实时知识库、归档材料、运行态快照、维护式更新、本地数据分析平台、shadow 数据库、Prompt Mart、提示词瘦身与向量相似审核等术语 |
| `docs/adr/0000-template.md` | ADR 模板 | 已核对 | 模板有效，无需新增 ADR |

## 3. 任务、Worker、Comfy 与 RunPod

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_任务调度_task_scheduler.md` | `src/core/task_core*.py`、`src/task_core_process_defaults.py`、部署脚本 | 已修正 | 部署章节同步云测试维护式更新入口 |
| `docs/子模块_生成任务全链路_task_full_chain.md` | `src/web_api/services/*task*`、`backend/app`、`workers/comfy_agent` | 已修正 | 主链路仍符合现状；补充自由P图 v2 到 `pornmaster_flux2_single_edit` / `pornmaster_flux2_multi_edit` 的费用、无 LoRA 和 exact worker task type 路由；修正 SCAIL-2 动作迁移合并长时长：用户侧仍为 `scail2_action_transfer`，10/15/20s 隐式路由到 `scail2_action_transfer_long` 执行；补充 Web 用户侧 pending 关闭即撤销、active registry `credits_deducted` 退款判断、confirmed cancel 立即 finalizer 退款/释放锁/清理 active registry、running cancel request 不提前清理的口径 |
| `docs/子模块_中控API与节点通信_central_api.md` | `backend/app/main.py`、`backend/app/queue_manager.py`、worker relay | 已修正 | Central / worker protocol 口径有效；同步 `/system/status.queue_by_type_details` 作为 Central pending 轻量等待统计，按 `priority <= 0` / `priority > 0` 分免费与付费最长等待，区别于 Dashboard 低信任聚合口径；SCAIL-2 测试与正式 LAN worker 四任务声明、正式 RunPod scail2 两任务口径仍有效 |
| `docs/子模块_任务黄金路径回归清单_task_golden_path.md` | `tests/backend`、`tests/core`、`tests/web_api`、worker tests | 已修正 | 回归分组仍可用；补充 `tests/core/test_task_runtime_cleanup.py` 覆盖用户取消 pending 后退款/锁释放/active registry 清理，以及 running cancel request 不提前清理 |
| `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` | `ops/gpu_pool_controller`、Dashboard RunPod 服务、RunPod scripts、PornMaster Flux2 edit profile/scripts | 已修正 | 已包含 Dashboard autoscaler 预计清空时间模型、profile 级自动管理暂停、RunPod Worker 锁定/解锁保护手动删除、autoscaler down 与 add cleanup、RunPod 故障/暂停自愈、bootstrap timeout 换机清理、RunPod/LAN AIO 当前边界，并记录 `pornmaster_flux2_edit` 镜像、cached 模型 manifest、gpu252:8192 正式 AIO slot、gpu252:gpu1 maintenance disabled 不作为当前容量、gpu177:8190 当前 live runtime 收敛为 `image_to_video`、gpu177:8191 新增 `wan22_video_v2` disabled 同卡/同服务器候选、gpu002:8191 在 2026-06-29 23:17 Asia/Shanghai 后再次由 PornMaster Flux2 edit 接管且 `gpu-002-gpu1-image_to_video` 为同卡回切候选、旧 img2img_lora / ignored token env 与 fp8/bf16 运行口径；补充 Dashboard `LAN AIO 管理` 以 live runtime heartbeat / running container 判定当前 slot、返回 configured/live 双轨字段、runtime drift、`live_state`、`target_container_state`、`switch_readiness`、`switch_blockers`、`recover_readiness`、`recover_blockers`、`recover_prefer`、`recovery_status`，无 live signal 时不再用配置态兜底为当前；候选 `takeover` 可显式选择同服务器替换目标并按 live runtime profile 禁用同类型目标，同卡已有 live current 时 stopped/no-live 配置 slot 作为 warning 可切换目标，默认 `failure_policy=auto_rollback`；legacy `/system_stats`/`/queue` preflight 对刚重启 ComfyUI 有短重试，`warm-cache` 对 retarget 后 root-owned `/srv` workspace 有 Docker helper 兜底，`start-disabled` 会安全清理同名非运行态候选残留容器，`takeover` 在 `stop-old` 保护窗口后失败会自动回滚旧服务；新增候选走 `candidate-plan` 只读生成 YAML patch，失败现场恢复入口限定为单物理 GPU/精确 slot `recover --physical-slot ... --slot ...`，Dashboard 巡检空物理 GPU 后才开放 `恢复此 AIO`；单步 operation 保留为后端/API/CLI 排障入口，保留 profiles/slots/action API、`warm-cache` cache marker、物理 slot operation lock 与无自由镜像/manifest 边界；补充云正式 Dashboard LAN AIO mutation 需经本地主服务器 SSH runner 执行，runner SSH key/env/proxy 与 preflight 失败摘要口径已同步；补充正式 LAN SCAIL-2 可承接 `scail2_action_transfer_long` 且正式 RunPod 不承接 |
| `docs/子模块_附加模型配置指南_comfy_models.md` | `workers/comfy_agent/workflows`、`remote_workers`、workflow patcher、PornMaster Flux2 edit workflow/API 映射 | 已修正 | workflow 事实源和 SCAIL-2/LTX 口径有效；新增 PornMaster Flux2 single/multiple edit API workflow、cached 模型 bundle、LAN cache、Civitai token 安全入口、fp8 默认与 bf16 canary 口径；修正 SCAIL-2 Context Windows API workflow 为动作迁移 10/15/20s hidden execution，不作为独立用户入口；继续作为 `allbot-comfy-models` 的节点级细节事实源 |
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
| `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md` | `qqcc_bot/main.py`、`qqcc_bot/commands.py`、`qqcc_bot/keyboards.py`、`qqcc_bot/prompt_handlers.py`、cloud compose QQCC profile、`scripts/update_cloud_prod_qqcc_bot.sh`、`src/handlers/fsm/quick_image_fsm.py`、`src/handlers/fsm/quick_video_fsm.py` | 已修正 | 补充 QQCC 主菜单 `前往主bot` 非生成入口、正式 QQCC Bot 单服务更新脚本、单 polling 确认口径、独立 token、`bot:qqcc` 来源、快速脱衣主菜单入口与两种处理方式选择；`视频创作` 已在 QQCC 专用显示层改为 `AI动图`，其二级场景改为挂在 Bot 回复下方的 inline 按钮且三项一行；双 polling 红线有效 |
| `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` | `paid_group_guard_bot`、Dashboard paid group router/service、cloud compose | 已核对 | 独立 Bot 与 Dashboard 配置管理边界有效 |
| `docs/子模块_Telegram本地API与文件代理_tg_local_api.md` | Telegram API env、Bot file handling | 已核对 | 文件代理边界有效 |

## 5. Web、商业化、社区与后台

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_用户认证与权限_user_auth_permission.md` | `src/core/auth_core*`、`src/web_api/core/security.py` | 已核对 | JWT、password_version、权限复核口径有效 |
| `docs/子模块_计费与支付_billing_payment.md` | `src/core/billing_core*`、`src/payment_api_server.py`、affiliate migrations | 已核对 | 支付履约与 affiliate 账本口径有效 |
| `docs/子模块_社区与存储_gallery_storage.md` | `src/core/gallery*`、`src/web_api/services/*gallery*`、R2 scripts | 已修正 | R2/legacy MinIO 退出口径有效；补充 LTX 高级图生视频首尾帧 Gallery 标签、apply-context 回填与 `ltx_video_flf2v` alias 口径 |
| `docs/子模块_后台监控与清理_dashboard_monitoring.md` | `dashboard/backend`、`dashboard/frontend`、RunPod admin/autoscaler services | 已更新 | Dashboard 监控和清理边界有效；同步 `/api/system/status` 低信任免费层 pending 用户数/任务数、非低信任最长等待、`pornmaster_flux2_edit` 本地/手动 Worker profile 展示与 `autoscaler_enabled=false` 不进 RunPod autoscaler 的口径 |
| `docs/子模块_本地数据分析平台_local_analytics_platform.md` | `local_analytics_platform`、`local_analytics_platform/app/user_profile_analytics.py`、`scripts/run_local_analytics_shadow_pipeline.py`、`bot_db_prod_shadow`、本地 compose | 已更新 | 记录独立本地分析平台入口、只读 shadow 数据边界、核心四 Tab ECharts 可视化与新增对比 API、用户画像人群透视/用户宽表/单用户详情抽屉、`GET /api/user-analytics/groups`、`GET /api/user-analytics/users`、`GET /api/user-analytics/users/{user_id}`、用户画像开始/结束日期范围、用户宽表按日期范围收敛画像信号用户池、人群透视继承下钻用户列表的日期/搜索/分层范围且不再独立预筛、旧用户增长/漏斗/分布/排行榜前端退出、低信任免费层/低信任用户邀请价值/真实充值率概览/按邀请人平均受邀充值率/邀请转化/受邀充值/affiliate 返佣账本聚合、每日 shadow 后保留 `analytics_prompt_*`、05:45 自动链路的 shadow/vector 双锁、Mart 增量刷新、瘦身与向量断点续跑链路、提示词瘦身、向量相似审核、Prompt 语义场景提炼 v1、Prompt 语义图谱 v2 单任务自然社区派生表/API/前端 Tab、相似族从 duplicate 边传递闭包改为代表点和族内两两阈值守卫、媒体引用核验与不挂载现有 Dashboard 的运行口径 |
| `docs/business/00_INDEX_业务板块分类与规范总览.md` | business docs | 已核对 | 业务导航有效 |
| `docs/business/00_DICT_全局业务数据字典.md` | models、domain config、business docs | 已核对 | 数据字典有效 |
| `docs/business/01_BIZ_AI创作与生成板块.md` | task type registry、FSM、Web task routes | 已核对 | 生成业务描述有效 |
| `docs/business/02_BIZ_商业化与会员资产板块.md` | billing/auth/affiliate code | 已核对 | 商业化描述有效 |
| `docs/business/03_BIZ_社区广场与社交互动板块.md` | Gallery models/services | 已修正 | 补充低信任免费层不能新增提示词解锁转账，但作者自看和已解锁记录不受影响 |
| `docs/business/04_BIZ_用户修为与身份权限体系.md` | User model、auth core、permission service、billing core | 已修正 | 补充身份分级并发上限：外门/默认 3、内门 5、核心 8、真传 12，并保留低信任免费层实时标记、非低信任用户 `+40` 队列加成和 Gallery 提示词解锁限制口径 |
| `docs/business/image_to_image_flow.md` | image FSM/task routes | 已核对 | 图生图流程有效 |
| `docs/business/image_to_video_flow.md` | video FSM/task routes、Wan22/LTX/SCAIL-2 docs | 已核对 | 图生视频流程有效 |

## 6. 运维与环境

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/SAFE_DEPLOY_GUIDE.md` | deploy scripts、cloud compose | 已修正 | 云测试主入口改为维护式更新脚本，`safe_deploy_cloud_test.sh` 标为子步骤 |
| `docs/子模块_运维指南与容器管理_ops_deployment.md` | deploy scripts、compose、ops Skill | 已修正 | 补充正式 QQCC Bot 单服务更新入口；运维总口径有效 |
| `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` | `deploy/docker-compose-cloud-test.yml`、`scripts/update_cloud_test_with_maintenance.sh`、`workers/docker-compose-cloud-worker-test.yml` | 已修正 | 云测试 SOP 以维护式更新为主；补充自由P图 v2 开关、worker4 覆盖到 gpu252:8192 PornMaster AIO 和单 worker canary 启动口径；修正 worker8 的 SCAIL-2 `scail2_action_transfer_long` 为动作迁移 10/15/20s hidden execution/workflow override，不再由用户入口 feature flag 控制 |
| `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` | `deploy/docker-compose-cloud-prod.yml`、`scripts/update_cloud_prod_with_maintenance.sh`、`scripts/update_cloud_prod_qqcc_bot.sh`、`scripts/sync_cloud_prod_to_local_shadow.py`、`scripts/run_local_analytics_shadow_pipeline.py`、systemd timer、Dashboard autoscaler service、LAN AIO prod helpers、Cloudflare Pages build logs | 已修正 | 补充正式 QQCC Bot 专用窄更新入口；本地 shadow 同步已更新为云机 dump + R2/HTTPS 临时中转 + 本地 restore 主路径，并补充完整合并桶、timer、安全边界、旧 tunnel fallback、本地分析表保留、05:45 自动分析刷新、语义场景刷新与验收口径；同步 autoscaler 预计清空时间模型、profile 级自动管理暂停、RunPod 故障/暂停自愈和 bootstrap timeout 换机口径；补充自由P图 v2 正式 GPU252 AIO slot 与 SCAIL-2 长动作迁移正式 LAN 四任务发布口径；补充 Cloudflare Pages npm 10.9.2 lockfile 发布前验证与 `@emnapi/runtime` 缺失修复口径 |
| `docs/子模块_本地正式灾备切换_local_prod_fallback.md` | `safe_deploy.sh`、cloud prod scripts、shadow sync script | 已修正 | 灾备时优先核对/使用 `bot_db_prod_shadow`、`user-data-prod-shadow` 与 `user-data-complete-shadow`，本地写入前停止 shadow timer |
| `docs/子模块_网络暴露与代理穿透_network_proxy.md` | Cloudflare/Tunnel scripts、network docs | 已核对 | 网络入口和回滚边界有效 |
| `docs/子模块_边缘节点运维指南_edge_node_ops.md` | edge docs、cloud prod preflight、Cloudflare Pages build logs | 已修正 | 边缘节点说明有效；补充 Cloudflare Pages 使用 Node 24 / npm 10.9.2 构建时的 `npm ci` 同版本验证、lockfile 刷新和 `Missing: @emnapi/runtime@1.11.1 from lock file` 排障口径 |
| `docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md` | SSH docs、cloud compose | 已核对 | 不含私钥，作为登录边界文档保留 |
| `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md` | LAN SSH docs、GPU resource docs | 已核对 | 不含私钥，作为节点访问文档保留 |
| `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` | LAN AIO scripts、GPU pool config、worker compose、PornMaster Flux2 edit profile/image | 已修正 | 长运行态文档保留，容量需按实时探测复核；gpu177:8190 当前 live runtime 与配置目标均按 `image_to_video`，不能因共用 Wan22 AIO 镜像误判为本地已接 `wan22_video_v2`；`gpu-177-gpu1-wan22_video_v2` 与 `gpu-177-gpu1-scail2` 只作为 disabled 候选；PornMaster Flux2 edit 当前正式 slot 为 `gpu-252-gpu0-pornmaster_flux2_edit` 使用 gpu252:8192，`gpu-252-gpu0-img2img_lora` 是同卡回切候选，gpu252:gpu1 `wan22_video_v2` 保留 maintenance 配置但无本地 GPU live runtime 时显示“停用/无运行态”且不计入当前数量，gpu002:8190 SCAIL-2 已纳入 fleet slot `gpu-002-gpu0-scail2`，且 gpu002:8191 在 2026-06-29 23:17 Asia/Shanghai 后再次由 `gpu-002-gpu1-pornmaster_flux2_edit` 接管；`gpu-002-gpu1-image_to_video` 为同卡回切候选；补充 Dashboard LAN AIO 管理以 live runtime heartbeat / running container 判定当前 slot、当前 slot `一键切换` 禁用、候选 `takeover` 可显式选择同服务器替换目标并按 live runtime profile 禁用同类型目标，同卡已有 live current 时 stopped/no-live 配置 slot 作为 warning 可切换目标，且安全切换默认自动回滚旧服务、legacy preflight 对刚重启 ComfyUI 有短重试、`warm-cache` 可用 Docker helper 兜底创建 root-owned `/srv` retarget workspace、新候选配置先走 `candidate-plan` Git/YAML patch；补充 `巡检本地服务` / `恢复此 AIO` 只在同物理 GPU 无 active runtime 时按 `recover_readiness` 开放，底层走 `recover --physical-slot ... --slot ...` 单卡恢复；SCAIL-2 正式 LAN slot0 四任务含 `scail2_action_transfer_long`，专用脚本仅作为低层启动/重建/回滚入口 |
| `docs/子模块_系统资源与容量画像_resource_inventory.md` | compose、resource docs、deployment scripts、shadow sync script | 已修正 | 云正式/云测试入口口径更新；补充本地 shadow DB、R2 shadow、完整合并桶与 MinIO bucket 资源事实，并记录 shadow DB 获取路径已切为云机 dump + R2/HTTPS 中转；运行态快照仍需人工探测 |
| `docs/子模块_容灾与持久化_database_recovery.md` | migrations、runtime checkpoint code | 已核对 | 恢复主链有效 |
| `docs/子模块_代码静态分析与质量评估规范_code_quality.md` | `pytest --collect-only`、`ruff check`、Alembic、Core Isolation 扫描、doc checker | 已修正 | 保留 2026-06-24 历史快照，新增 2026-06-27 轻量复核结果 |
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
| `.codex/skills/allbot-ops-deployment/SKILL.md` | deploy scripts、compose、shadow sync script、Dashboard autoscaler service、LAN AIO Dashboard 管理、Skill 体积审计 | 已修正 | 从约 51KB 瘦身为约 10KB 的路由型入口，保留测试优先、正式确认、密钥红线、部署入口、RunPod/LAN AIO/shadow/验证矩阵；同步 RunPod Worker 锁定会保护手动删除、autoscaler down 与 add cleanup；同步 LAN AIO Dashboard 页面只暴露受控 `takeover` 一键切换和空物理 GPU 的受控 `recover` 恢复入口，当前态只认 live runtime，默认 `failure_policy=auto_rollback`，新增候选走 `candidate-plan` Git/YAML patch，gpu-002 SCAIL-2 正式 slot0 也需先声明在 fleet 配置，单步 operation 保留为后端/API/CLI 排障入口，保留物理 GPU lock、单物理 GPU/精确 slot `recover` 与云正式 LAN AIO mutation 走本地主服务器 runner 的边界；低频运行态细节改为按需读取 docs/reference，避免触发时正文被截断 |
| `.codex/skills/allbot-task-engine/SKILL.md` | task core、queue manager、runtime cleanup、Skill 体积审计 | 已修正 | 已从约 23KB 瘦身为约 8.4KB 的任务生命周期路由入口，保留 core/Web/Central/Worker 边界、双 ID 红线、新任务类型清单和验证要求；修正 SCAIL-2 合并长时长后的 public/history/execution 路由口径；长链路细节改由任务调度/生成全链路文档按需加载 |
| `.codex/skills/allbot-comfy-models/SKILL.md` | workflow patcher、remote_workers、Skill 体积审计 | 已修正 | 已从约 36KB 瘦身为约 7.4KB 的模型/workflow 路由入口，保留 workflow 事实源、Central/Worker 边界、Wan22/LTX/SCAIL-2 关键提醒和部署验收；修正 `scail2_action_transfer_long` 为动作迁移 10/15/20s hidden execution；节点级细节改由 Comfy 子模块文档与 runtime reference 按需加载 |
| `.codex/skills/allbot-tg-fsm/SKILL.md` | `src/handlers`、Bot entrypoint | 已核对 | FSM 边界有效 |
| `.codex/skills/allbot-qqcc-lazy-bot/SKILL.md` | `qqcc_bot`、cloud compose、`scripts/update_cloud_prod_qqcc_bot.sh`、`src/services/qqcc_config_service.py`、`src/handlers/fsm/quick_image_fsm.py`、`src/handlers/fsm/quick_video_fsm.py` | 已修正 | 补充 QQCC 主菜单 `前往主bot` 非生成入口、正式单独更新脚本、单 polling 确认口径、快速脱衣主菜单入口、`AI动图` 专用文案与 quick video inline 场景按钮契约；修正未配置主 Bot URL/username 时“按钮不展示”的旧口径，改为由 `main_bot_link` 配置控制菜单项，点击时提示入口未配置；QQCC 独立 Bot 边界有效 |
| `.codex/skills/allbot-billing-auth/SKILL.md` | auth/billing/affiliate code | 已核对 | 计费鉴权边界有效 |
| `.codex/skills/allbot-gallery-storage/SKILL.md` | Gallery/R2 code、Skill 体积审计 | 已修正 | 存储与社区边界有效；已补充自由P图 v2 独立 `free_edit_v2_group`、Web 一键应用无 LoRA/重传参考图和 single/multi 提交口径；补充 LTX 首尾帧 tag、apply-context 回填与 `ltx_video_flf2v` alias 口径 |
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
