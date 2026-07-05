# AllBot Knowledge Base Audit Matrix

本矩阵记录 2026-06-27 对 AllBot 实时知识库的逐项核对结果，并承接后续 2026-07-03 QQCC 绘图后处理链等局部知识库同步。事实源优先级为当前代码、compose、脚本、Alembic、`pytest --collect-only`、`ruff check` 与文档结构检查；本轮不做远端 SSH、线上 curl 或 Docker 运行态探测。

## 1. 本轮校准基线

| 项目 | 当前事实 |
| :--- | :--- |
| Git 分支 / 提交 | `deploy` / `2bd2866` |
| Alembic | 单 head：`7f3a9c1d2e4b` |
| 测试收集 | `pytest --collect-only -q` 收集 `1778` 个测试，用时约 118 秒 |
| Ruff | `ruff check --statistics` 剩余 `7` 个可自动修复问题：1 个 `F541`、6 个 `F401`，集中在 `local_analytics_platform/`、`ops/gpu_pool_controller/runpod_pod_request.py`、`scripts/import_minio_bucket_normalized.py` 与测试文件 |
| 文档结构 | `python scripts/doc_quality_checker.py` 通过 |
| Core Isolation | `rg` 轻量扫描 `src/core` 未发现 Telegram `Update` 或 FastAPI `Request/APIRouter` 等平台对象 import |
| 云测试入口 | 日常更新以快速重建对应模块容器为主，不默认维护或排空队列；`scripts/update_cloud_test_with_maintenance.sh --execute` 仅用于整栈联动、迁移、排空验证或用户明确要求维护窗口；远端控制面重建子步骤为 `scripts/safe_deploy_cloud_test.sh`；整仓同步排除并清理远端旧 `local_analytics_platform/` |
| 云正式入口 | 正式发布需明确确认；控制面入口为 `scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod` 或 `scripts/safe_deploy_cloud_prod.sh` 子步骤；QQCC 正式 Bot 单独更新入口为 `scripts/update_cloud_prod_qqcc_bot.sh --execute --confirm-prod --confirm-single-polling`，用户明确要求 QQCC 单服务更新即可作为当次单 polling 操作确认；正式整仓 rsync 脚本排除 `local_analytics_platform/` |
| 本地云正式 shadow 同步 | `scripts/sync_cloud_prod_to_local_shadow.py` 默认 dry-run，`--execute` 才把云正式 PostgreSQL 恢复为本地 `bot_db_prod_shadow`；数据库获取主路径为 `CLOUD_PROD_DB_DUMP_MODE=remote_r2`，由 `allbot-do-sgp1-control` 在云机 dump 后临时上传 R2 `user-data-prod/__shadow-transfer/<timestamp>`，本地经 HTTPS/rclone 下载校验后 restore，避免依赖家宽/VPN 出口 IP 作为托管 DB trusted source；恢复 `_next` 后、切换 shadow 前默认用 `LOCAL_ANALYTICS_PRESERVE_ON_SHADOW_SYNC=true` 保留旧 shadow 中用户画像快照、Prompt Mart、提示词瘦身和 embedding/state 基础表，prompt 表使用显式白名单避免旧派生表被恢复；`R2_BUCKET_SYNC_ENABLED=true` 时才把 R2 `user-data-prod` 增量同步到 MinIO `user-data-prod-shadow` 并用 quarantine 保留云端覆盖/删除的旧对象；`COMPLETE_MEDIA_SYNC_ENABLED=true` 时每日从本地 R2 shadow 非破坏式 copy 到 `user-data-complete-shadow`；legacy `bot-data`/`comfyui-temp` 只在手动 `--include-legacy-media-import` 首次/补漏时导入；脚本持有 `.shadow-sync.lock` 防并发；本地分析刷新入口为 `scripts/run_local_analytics_shadow_pipeline.py` 与 `allbot-local-analytics-refresh.timer`，默认每日 Asia/Shanghai 05:45；刷新链会先 upsert `analytics_user_profile_daily_snapshots`，即使 `.refresh_prompt_vectors.lock` 显示上一轮向量刷新仍在运行也保留当天画像快照，随后才可能跳过 Prompt Mart/embedding 链；无向量锁时按 affected `prompt_hash` 增量刷新 Mart、瘦身和缺失 embedding，不再生成语义场景、相似边、近重复族或图谱；05:00 切库断线后向量阶段重连并断点续跑 |
| 旧本地脚本 | `safe_deploy.sh` 只用于云正式整体故障时的本地正式灾备；`safe_deploy_test.sh` 只作历史取证 |
| 归档材料 | `docs/archive/` 与 `logs/` 只作历史证据或排障报告，不作为当前 SOP |

## 2. 总览与索引文档

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `README.md` | `docs/` 清单、`.github/workflows/docs_ci.yml`、部署脚本 | 已修正 | 按 `docs/*.md` 当前清单补齐活跃索引，恢复 GPU Pool、QQCC、付费群审核、本地数据分析平台等入口；同步云测试快速单模块更新为日常默认 |
| `AGENTS.md` | `.codex/skills/*/SKILL.md`、运维脚本 | 已修正 | 测试优先部署改为云测试快速单模块更新优先，维护式脚本退为整栈/迁移/排空/明确维护窗口入口 |
| `docs/knowledge_base_audit_matrix.md` | 本轮只读扫描与校验命令 | 已修正 | 更新 2026-06-27 基线、ruff/pytest/doc checker/Core Isolation 结果和本轮知识库处理结果 |
| `docs/system_architecture_report.md` | compose、RunPod/Dashboard/QQCC Config/本地分析服务、测试收集、ruff、Bot 菜单/FSM | 已修正 | 更新 2026-06-27 轻量复核、autoscaler 预计非低信任用户清空时间模型、云测试 worker 口径，并补充 `local_analytics_platform` 独立只读 shadow 分析入口；2026-07-03 补充 QQCC Config Backend/Frontend 从主 Dashboard 剥离后的云正式与云测试控制面组成；2026-07-05 同步主 Bot 旧修仙市集改为 `懒人bot` 跳转、QQCC 独立入口开放快速换脸/AI绘图/AI动图/轻量市集 |
| `docs/skills/README.md` | `.codex/skills` 清单与本轮 Skill 体积审计 | 已修正 | 增加矩阵维护约定和 Skill 正文体积维护规则；记录 `allbot-ops-deployment`、`allbot-comfy-models` 与 `allbot-task-engine` 已瘦身，`allbot-gallery-storage` 已折叠超长行 |
| `docs/domain/CONTEXT.md` | 领域文档、运维脚本、本地分析平台代码与文档 | 已修正 | 补充实时知识库、归档材料、运行态快照、维护式更新、云测试快速更新、本地数据分析平台、shadow 数据库、Prompt Mart、提示词瘦身与提示词向量化等术语 |
| `docs/adr/0000-template.md` | ADR 模板 | 已核对 | 模板有效，无需新增 ADR |

## 3. 任务、Worker、Comfy 与 RunPod

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_任务调度_task_scheduler.md` | `src/core/task_core*.py`、`src/task_core_process_defaults.py`、部署脚本 | 已修正 | 部署章节同步云测试快速单模块更新入口；2026-07-04 补充取消退款账本幂等：`registry_task_id` 派生 `task_refund:refund_user_cancel:<registry_task_id>`，重复取消/monitor 收口只允许第一次加灵石 |
| `docs/子模块_生成任务全链路_task_full_chain.md` | `src/web_api/services/*task*`、`backend/app`、`workers/comfy_agent` | 已修正 | 主链路仍符合现状；补充自由P图 v2 到 `pornmaster_flux2_single_edit` / `pornmaster_flux2_multi_edit` 的费用、无 LoRA 和 exact worker task type 路由；修正 SCAIL-2 动作迁移合并长时长：用户侧仍为 `scail2_action_transfer`，10/15/20s 隐式路由到 `scail2_action_transfer_long` 执行；同步长动作迁移 Context Windows `freenoise=true` 速度优先口径，并注明动作循环伪影风险可能回归；补充 Web 用户侧 pending 关闭即撤销、active registry `credits_deducted` 退款判断、confirmed cancel 立即 finalizer 退款/释放锁/清理 active registry、running cancel request 不提前清理的口径；补充 `i2i_draw` 局部重绘仅在 Web 提交入口禁用、core/dispatcher/worker 能力保留的口径；2026-07-04 同步 Redis 连接瞬断鲁棒性：`api_client` 按 submit/status/media 隔离 breaker，Central Redis transient 503 进入 busy/补偿路径；2026-07-04 同步取消退款 `credit_idempotency_key` 语义，Web/Bot/恢复重复看到同一 `cancelled` 不重复退款 |
| `docs/子模块_中控API与节点通信_central_api.md` | `backend/app/main.py`、`backend/app/queue_manager.py`、worker relay | 已修正 | Central / worker protocol 口径有效；同步 `/system/status.queue_by_type_details` 作为 Central pending 轻量等待统计，按 `priority <= 0` / `priority > 0` 分免费与付费最长等待，区别于 Dashboard 低信任聚合口径；SCAIL-2 测试与正式 LAN worker 四任务声明、正式 RunPod scail2 两任务口径仍有效；2026-07-04 同步统一 Redis factory、Central transient 503、入队事务 retry 与 `zpopmin` 不盲 retry 口径 |
| `docs/子模块_任务黄金路径回归清单_task_golden_path.md` | `tests/backend`、`tests/core`、`tests/web_api`、worker tests | 已修正 | 回归分组仍可用；补充 `tests/core/test_task_runtime_cleanup.py` 覆盖用户取消 pending 后退款/锁释放/active registry 清理，以及 running cancel request 不提前清理 |
| `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` | `ops/gpu_pool_controller`、LAN AIO helper/state、Dashboard RunPod 服务、RunPod scripts、PornMaster Flux2 edit profile/scripts | 已修正 | 新增 `lan_aio_fleet_state.yml` 作为 LAN AIO 当前态/缓存态/blocked 摘要入口，文档不再维护易过期静态大表；2026-07-02 校准后记录 gpu226 GPU0 当前 `image_to_video` LAN AIO，旧 `cloud_prod_worker_01` 为 stopped/disabled rollback 元数据；gpu177 GPU0 当前 `wan22_video_v2`、GPU1 当前 `ltx_video`，SCAIL-2 是同卡回切候选，GPU1 `image_to_video` 与 `wan22_video_v2` 都因 RTX 5090 32G 上的 ComfyUI status 137 标记 blocked。2026-07-04 同步 gpu-252 UUID 固定绑定与返修卡隔离：8192 i2i_pro/候选 slot 绑定健康 UUID；8191 返修 UUID 的 SCAIL-2 曾通过普通验证但真实 workload 复现 Xid 119/154，现只以 `gpu-252-gpu1-pornmaster_flux2_edit` 承接低负载自由P图 v2，SCAIL-2/Wan22 仍 maintenance-disabled 并由其它 LAN/RunPod 兜底。Dashboard LAN AIO slot/candidate 管理 API 已移除；当前态/任务仍由 Worker 卡片展示，基础 `pause/enable/restart` 保留，candidate-plan、takeover auto_rollback、recover 单物理 GPU、warm-cache marker 只由本地主 AI operator/CLI 执行 |
| `ops/gpu_pool_controller/config/lan_aio_fleet_state.yml` | live `scripts/lan_aio_fleet_prod_ops.py status --include-disabled`、远端 Docker/container/cache marker 检查 | 新增 | Agent 维护的 Git-tracked LAN AIO fleet 状态文件；记录 `node_id + gpu_index` 的 current profile、slot、agent/container、cached profiles、fast switch candidates、blocked profiles、last_verified_at。只存非敏感事实，不存 env/token/presigned URL/task 流水；每次受控 LAN AIO 管理后必须同步更新。2026-07-04 gpu-252 GPU0 当前为 `i2i_pro` LAN AIO，Docker DeviceIDs 固定健康 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666`；GPU1 返修 UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e` 当前为 `pornmaster_flux2_edit` LAN AIO，SCAIL-2/Wan22 仍因真实 workload Xid 119/154 maintenance-disabled |
| `docs/子模块_附加模型配置指南_comfy_models.md` | `workers/comfy_agent/workflows`、`remote_workers`、workflow patcher、PornMaster Flux2 edit workflow/API 映射、`src/lora_catalog.py`、QQCC config service/FSM | 已修正 | workflow 事实源和 SCAIL-2/LTX 口径有效；新增 PornMaster Flux2 single/multiple edit API workflow、cached 模型 bundle、LAN cache、云端 RunPod transfer 转存、manifest HEAD 校验发布、Civitai token 安全入口、fp8 默认与 bf16 canary 口径；修正 SCAIL-2 Context Windows API workflow 为动作迁移 10/15/20s hidden execution，不作为独立用户入口；同步 QQCC 场景 engine/LoRA 配置边界：旧 `image_to_video`/`free_edit` 可选 catalog 附加模型，`wan22_video_v2`/`free_edit_v2` 自动清空 LoRA；新增 QQCC `end_frame_draw_scene_id` 复用 AI绘图场景的完整 `postprocess_draw_scene_id` 链生成最终尾帧后首尾帧提交旧图生视频或 v2，不新增 workflow/profile；继续作为 `allbot-comfy-models` 的节点级细节事实源 |
| `docs/compat_seam_exit_table.md` | compat 文件现状、`rg` 引用 | 已核对 | 作为 compat 清理挂账表保留 |
| `docs/双入口重复能力_inventory.md` | `backend/app`、`src/web_api` | 已核对 | 双入口分层描述有效 |
| `docs/入口职责矩阵_entry_responsibility_matrix.md` | Web/Central/Dashboard/Payment/Bot entrypoints | 已核对 | 入口职责有效 |
| `docs/测试与入口命名约定.md` | 测试目录与入口命名 | 已核对 | 命名约定有效 |
| `docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md` | hotspot docs、tests、compat 状态 | 已核对 | 长文档保留为门禁清单 |
| `docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md` | `.github/workflows`、hotspot guardrails | 已核对 | 分支保护和回归门禁说明有效 |

## 4. Bot 与交互

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_交互状态机_fsm_handlers.md` | `src/handlers`、FSM tests | 已修正 | 主 Bot FSM 边界有效；2026-07-05 同步主 Bot 菜单去重：`懒人bot` 跳转 QQCC、`图片换脸` 只保留快速/随机换脸、旧脱衣/自慰/视频创作文本和主 Bot `qvid_*` callback 只提示未开放，QQCC 动态场景 callback 保持 |
| `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md` | `qqcc_bot/main.py`、`qqcc_bot/gallery_market.py`、`qqcc_bot/keyboards.py`、`qqcc_bot/prompt_handlers.py`、`src/services/qqcc_config_service.py`、`src/services/qqcc_runtime_context.py`、`src/services/qqcc_draw_chain_service.py`、`dashboard/backend/qqcc_config_main.py`、`dashboard/frontend/src/QqccConfigApp.vue`、quick image/video FSM、Gallery/apply-context 服务、cloud compose QQCC profile、`scripts/update_cloud_prod_qqcc_bot.sh` | 已修正 | 2026-07-04 同步 QQCC `scene_preset_version=1`：`快速自慰` / `快速脱衣` 与默认动图场景只在旧配置迁移时一次性种子化，之后和自定义场景一致可编辑/删除；QQCC draw/video 场景运行时只读取场景自身 `prompt`，不再通过 `prompt_key` 或 `prompts.ini` 回退；QQCC Config Web 底部提示词覆盖只展示 `快速换脸`，保存 payload 不带场景 `prompt_key`；动态 `draw_scenes` engine/LoRA、`qdraw_scene:`、后处理链、最终图发送、AI动图尾帧来源、QQCC Config Web 独立部署、市集、`bot:qqcc` 来源和双 polling 红线继续有效；2026-07-05 同步主 Bot 反向跳转 `QQCC_LAZY_BOT_URL` / `QQCC_LAZY_BOT_USERNAME`、旧主 Bot 修仙市集/视频创作/脱衣/自慰入口下线且 QQCC 市集与场景入口不受影响；同步云测试 `qqcc-bot-test` 快速单模块重建口径；本次不新增 workflow、RunPod profile 或数据库表 |
| `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` | `paid_group_guard_bot`、Dashboard paid group router/service、cloud compose | 已核对 | 独立 Bot 与 Dashboard 配置管理边界有效 |
| `docs/子模块_Telegram本地API与文件代理_tg_local_api.md` | Telegram API env、Bot file handling | 已核对 | 文件代理边界有效 |

## 5. Web、商业化、社区与后台

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/子模块_用户认证与权限_user_auth_permission.md` | `src/core/auth_core*`、`src/web_api/core/security.py` | 已核对 | JWT、password_version、权限复核口径有效 |
| `docs/子模块_计费与支付_billing_payment.md` | `src/core/billing_core*`、`src/payment_api_server.py`、`src/web_api/services/user_credit_ledger_service.py`、affiliate migrations | 已修正 | 支付履约与 affiliate 账本口径有效；补充 Web 个人中心 `GET /api/users/me/credits/ledger` 只读查询本人非 0 `user_logs`、分页排序和 `extra_info` 白名单展示边界 |
| `docs/子模块_社区与存储_gallery_storage.md` | `src/core/gallery*`、`src/web_api/services/*gallery*`、`src/services/gallery_browse_service.py`、`qqcc_bot/gallery_market.py`、R2 scripts | 已修正 | R2/legacy MinIO 退出口径有效；补充 Web 好友搜索、QQCC 修仙市集轻量 Bot 浏览与 Telegram file_id 缓存口径；2026-07-04 同步 `gallery_reports` 举报治理：详情页举报、重复举报 `409`、Dashboard 举报筛选/标记处理/联动下架、`GalleryPost.is_active` 与 `History.is_public` 同步；保留 LTX/SCAIL-2/Wan22/i2i_draw apply-context 禁用与回填口径 |
| `docs/子模块_后台监控与清理_dashboard_monitoring.md` | `dashboard/backend`、`dashboard/frontend`、RunPod admin/autoscaler services | 已更新 | Dashboard 监控和清理边界有效；同步 `/api/system/status` 低信任免费层 pending 用户数/任务数、非低信任最长等待、高质量邀请者豁免、RunPod profile `non_low_trust_clear_pending_count*` 前缀统计、`pornmaster_flux2_edit` 正式 RunPod profile 展示、手动新增入口与 Dashboard autoscaler 自动 add/down 纳管口径 |
| `docs/子模块_本地数据分析平台_local_analytics_platform.md` | `local_analytics_platform`、`local_analytics_platform/app/user_profile_analytics.py`、`local_analytics_platform/app/user_profile_snapshots.py`、`local_analytics_platform/app/prompt_vectors.py`、`scripts/run_local_analytics_shadow_pipeline.py`、`scripts/cleanup_local_analytics_prompt_derivatives.py`、`bot_db_prod_shadow`、本地 compose | 已更新 | 记录独立本地分析平台入口、只读 shadow 数据边界、核心四 Tab ECharts 可视化与新增对比 API、用户画像固定看板/人群透视/用户宽表/单用户详情抽屉、`GET /api/user-analytics` 的 `visualizations`、`analytics_user_profile_daily_snapshots` 快照趋势、`GET /api/user-analytics/groups`、`GET /api/user-analytics/users`、`GET /api/user-analytics/users/{user_id}`、用户画像开始/结束日期范围、用户宽表按日期范围收敛画像信号用户池、人群透视继承下钻用户列表的日期/搜索/分层范围且不再独立预筛、旧用户增长/旧分布/排行榜前端退出、低信任免费层含高质量邀请者豁免、豁免低信任用户、低信任用户邀请价值/真实充值率概览/按邀请人平均受邀充值率/邀请转化/受邀充值/affiliate 返佣账本聚合、每日 shadow 后只保留 Prompt Mart、提示词瘦身、embedding/state 与用户画像快照白名单表、05:45 自动链路先刷新用户画像快照再进入 Prompt/向量链、Mart 增量刷新、瘦身与向量断点续跑链路、提示词瘦身、提示词向量化基础状态、近似代表/近似图/语义场景/语义图谱 Tab/API/刷新入口下线、旧派生表 dry-run 默认清理脚本、媒体引用核验与不挂载现有 Dashboard 的运行口径 |
| `docs/business/00_INDEX_业务板块分类与规范总览.md` | business docs | 已核对 | 业务导航有效 |
| `docs/business/00_DICT_全局业务数据字典.md` | models、domain config、business docs | 已修正 | 补充 `GalleryReport` 字典项，记录举报原因枚举、处理状态、快照字段与 `reporter_user_id + post_id` 唯一约束 |
| `docs/business/01_BIZ_AI创作与生成板块.md` | task type registry、FSM、Web task routes | 已核对 | 生成业务描述有效 |
| `docs/business/02_BIZ_商业化与会员资产板块.md` | billing/auth/affiliate code、`src/web_api/services/user_credit_ledger_service.py` | 已修正 | 商业化描述有效；补充 Web 用户侧灵石账本只读本人流水查询 |
| `docs/business/03_BIZ_社区广场与社交互动板块.md` | Gallery models/services | 已修正 | 同步 Gallery 提示词解锁不再按低信任免费层拦截；2026-07-04 补充修仙市集详情举报、原因枚举、重复举报冲突、Dashboard 举报管理与联动软下架同步语义 |
| `docs/business/04_BIZ_用户修为与身份权限体系.md` | User model、auth core、permission service、billing core | 已修正 | 保留低信任免费层实时标记、高质量邀请者豁免、非低信任用户 `+40` 队列加成，并同步 Gallery 提示词解锁限制退出 |
| `docs/business/image_to_image_flow.md` | image FSM/task routes | 已核对 | 图生图流程有效 |
| `docs/business/image_to_video_flow.md` | video FSM/task routes、Wan22/LTX/SCAIL-2 docs | 已核对 | 图生视频流程有效 |

## 6. 运维与环境

| 文档 | 事实源 | 本轮状态 | 处理结果 |
| :--- | :--- | :--- | :--- |
| `docs/SAFE_DEPLOY_GUIDE.md` | deploy scripts、cloud compose | 已修正 | 云测试日常入口改为目标 service 快速重建，维护式更新脚本只在整栈/迁移/排空/明确维护窗口时使用，`safe_deploy_cloud_test.sh` 标为子步骤 |
| `docs/子模块_运维指南与容器管理_ops_deployment.md` | deploy scripts、compose、ops Skill | 已修正 | 补充正式 QQCC Bot 单服务更新入口；同步云测试快速单模块重建为日常默认，维护式脚本仅用于整栈/迁移/排空/明确维护窗口；运维总口径有效 |
| `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` | `deploy/docker-compose-cloud-test.yml`、`scripts/update_cloud_test_with_maintenance.sh`、`workers/docker-compose-cloud-worker-test.yml` | 已修正 | 云测试 SOP 改为日常快速重建目标 service，不默认维护或排空；维护式脚本保留给整栈/迁移/排空/明确维护窗口；补充自由P图 v2 开关、worker4 临时测试覆盖到 gpu252:8192 PornMaster AIO 和单 worker canary 启动口径；修正 worker8 的 SCAIL-2 `scail2_action_transfer_long` 为动作迁移 10/15/20s hidden execution/workflow override，不再由用户入口 feature flag 控制 |
| `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` | `deploy/docker-compose-cloud-prod.yml`、`scripts/update_cloud_prod_with_maintenance.sh`、`scripts/update_cloud_prod_qqcc_bot.sh`、`scripts/sync_cloud_prod_to_local_shadow.py`、`scripts/run_local_analytics_shadow_pipeline.py`、systemd timer、Dashboard autoscaler service、LAN AIO prod helpers、Cloudflare Pages build logs | 已修正 | 补充正式 QQCC Bot 专用窄更新入口；本地 shadow 同步已更新为云机 dump + R2/HTTPS 临时中转 + 本地 restore 主路径，并补充完整合并桶、timer、安全边界、旧 tunnel fallback、本地分析白名单表保留、05:45 自动分析刷新、提示词向量化收口与旧派生分析退出口径；同步 autoscaler 预计非低信任用户清空时间模型、profile 级自动管理暂停、RunPod 故障/暂停自愈和 bootstrap timeout 换机口径；同步自由P图 v2 当前 LAN 由 GPU002 GPU1 与 GPU252 GPU1 并行接单，GPU252 GPU1 只计入 PornMaster 低负载容量，SCAIL-2/Wan22 仍 maintenance-disabled；补充 `pornmaster_flux2_edit` 正式手动 RunPod env/profile/canary/模型转存 SOP 与 SCAIL-2 长动作迁移正式 LAN 四任务发布口径；补充 gpu226 image_to_video LAN AIO 接管后 worker01 stopped rollback 映射；补充 Cloudflare Pages npm 10.9.2 lockfile 发布前验证与 `@emnapi/runtime` 缺失修复口径 |
| `docs/子模块_本地正式灾备切换_local_prod_fallback.md` | `safe_deploy.sh`、cloud prod scripts、shadow sync script | 已修正 | 灾备时优先核对/使用 `bot_db_prod_shadow`、`user-data-prod-shadow` 与 `user-data-complete-shadow`，本地写入前停止 shadow timer |
| `docs/子模块_网络暴露与代理穿透_network_proxy.md` | Cloudflare/Tunnel scripts、network docs | 已核对 | 网络入口和回滚边界有效 |
| `docs/子模块_边缘节点运维指南_edge_node_ops.md` | edge docs、cloud prod preflight、Cloudflare Pages build logs | 已修正 | 边缘节点说明有效；补充 Cloudflare Pages 使用 Node 24 / npm 10.9.2 构建时的 `npm ci` 同版本验证、lockfile 刷新和 `Missing: @emnapi/runtime@1.11.1 from lock file` 排障口径 |
| `docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md` | SSH docs、cloud compose | 已核对 | 不含私钥，作为登录边界文档保留 |
| `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md` | LAN SSH docs、GPU resource docs | 已核对 | 不含私钥，作为节点访问文档保留；2026-07-04 同步 gpu252：8192 固定健康 UUID 接 i2i_pro，8191 固定返修 UUID 只接 PornMaster Flux2 edit，SCAIL-2/Wan22 仍不得直接接正式队列 |
| `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` | LAN AIO scripts、GPU pool config/state、worker compose、PornMaster Flux2 edit profile/image | 已修正 | 长运行态文档保留，容量需按实时探测复核；新增 `lan_aio_fleet_state.yml` 为当前态事实入口并修正 gpu226 为 `image_to_video` AIO 当前态、旧 worker01 stopped rollback；gpu177 容器表：GPU0 当前 `wan22_video_v2`、GPU0 `image_to_video` 为 stopped rollback，GPU1 当前 `ltx_video`，SCAIL-2 为同卡回切候选，GPU1 `image_to_video` 与 `wan22_video_v2` 均为 `blocked_oom_32gb`；gpu252 GPU0 当前 `i2i_pro`，gpu252 GPU1 当前 `pornmaster_flux2_edit` 低负载接单；GPU1 返修卡上的 SCAIL-2/Wan22 因真实 workload 复现 Xid 119/154 继续 maintenance-disabled。文档提醒先读 state 再跑 helper status，避免只按静态表操作 |
| `docs/子模块_系统资源与容量画像_resource_inventory.md` | compose、resource docs、deployment scripts、shadow sync script | 已修正 | 云正式/云测试入口口径更新；补充本地 shadow DB、R2 shadow、完整合并桶与 MinIO bucket 资源事实，并记录 shadow DB 获取路径已切为云机 dump + R2/HTTPS 中转；2026-07-04 同步 gpu252：8192 i2i_pro 固定健康 UUID，8191 返修 UUID 改为 PornMaster Flux2 edit 低负载接单，SCAIL-2/Wan22 因真实 workload Xid 119/154 保持 maintenance-disabled；运行态快照仍需人工探测 |
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
| `.codex/skills/allbot-ops-deployment/SKILL.md` | deploy scripts、compose、shadow sync script、Dashboard autoscaler service、LAN AIO worker 基础控制、Skill 体积审计 | 已修正 | 从约 51KB 瘦身为约 10KB 的路由型入口，保留测试优先、正式确认、密钥红线、部署入口、RunPod/LAN AIO/shadow/验证矩阵；同步 RunPod Worker 锁定会保护手动删除、autoscaler down 与 add cleanup；同步 Dashboard 不再提供 LAN AIO profile/slot 列表、候选切换、`takeover`、`recover` 或 `warm-cache` API，当前态和任务显示走 `/api/system/workers`，Worker 卡片只保留 `pause/enable/restart` 基础控制；候选切换、恢复和缓存预热只由本地主 AI operator/CLI 执行，云正式 Dashboard runner 仅可执行受限 `disable-aio|enable-aio|restart-aio` |
| `.codex/skills/allbot-lan-aio-operator/SKILL.md` | `allbot-ops-deployment`、`lan_aio_prod_slots.yml`、`lan_aio_fleet_state.yml`、`scripts/lan_aio_fleet_prod_ops.py` | 新增 | 新增 LAN AIO operator skill；只记录稳定操作法、红线、状态文件读取规则和 helper 命令，不硬编码 GPU 当前态表格。要求 mutation 前 live 检查、drift 停止、单物理 GPU 操作、禁止自由 compose/镜像/manifest，并在每次管理后同步 fleet state |
| `.codex/skills/allbot-task-engine/SKILL.md` | task core、queue manager、runtime cleanup、Skill 体积审计 | 已修正 | 已从约 23KB 瘦身为约 8.4KB 的任务生命周期路由入口，保留 core/Web/Central/Worker 边界、双 ID 红线、新任务类型清单和验证要求；修正 SCAIL-2 合并长时长后的 public/history/execution 路由口径；补充 `i2i_draw` Web 入口级禁用不等于全局删除能力；2026-07-04 补充 Central Redis transient 503、入队 retry、`zpopmin` 不盲 retry 与 submit/status breaker 隔离排障入口；长链路细节改由任务调度/生成全链路文档按需加载 |
| `.codex/skills/allbot-comfy-models/SKILL.md` | workflow patcher、remote_workers、Skill 体积审计、QQCC config/FSM | 已修正 | 已从约 36KB 瘦身为约 7.4KB 的模型/workflow 路由入口，保留 workflow 事实源、Central/Worker 边界、Wan22/LTX/SCAIL-2 关键提醒和部署验收；修正 `scail2_action_transfer_long` 为动作迁移 10/15/20s hidden execution；补充 QQCC `AI动图` 尾帧来源只复用 AI绘图后处理链和现有首尾帧输入，不新增 workflow/profile；节点级细节改由 Comfy 子模块文档与 runtime reference 按需加载 |
| `.codex/skills/allbot-tg-fsm/SKILL.md` | `src/handlers`、Bot entrypoint | 已核对 | FSM 边界有效 |
| `.codex/skills/allbot-qqcc-lazy-bot/SKILL.md` | `qqcc_bot`、`qqcc_bot/gallery_market.py`、cloud compose、`scripts/update_cloud_prod_qqcc_bot.sh`、`src/services/qqcc_config_service.py`、`src/services/qqcc_runtime_context.py`、`src/services/qqcc_draw_chain_service.py`、quick image/video FSM、`src/lora_catalog.py` | 已修正 | 2026-07-04 同步 QQCC 配置契约：`scene_preset_version=1` 一次性迁移默认 draw/video 预设，迁移后预设和自定义场景统一，提示词必须来自场景自身 `prompt`；独立配置页底部提示词覆盖只展示 `prompts.face_swap`，旧 prompt override 字段仅用于迁移兼容；动态 draw/video 场景、LoRA 清理、后处理链、尾帧来源、费用预检、QQCC 市集、`bot:qqcc` 任务归属和单 polling 红线继续有效；2026-07-05 补充主 Bot `懒人bot` 反向跳转 env、图片换脸菜单收口和主 Bot 旧入口禁用边界；本次不新增 workflow、RunPod profile 或数据库表 |
| `.codex/skills/allbot-billing-auth/SKILL.md` | auth/billing/affiliate code | 已核对 | 计费鉴权边界有效 |
| `.codex/skills/allbot-gallery-storage/SKILL.md` | Gallery/R2 code、`src/services/gallery_browse_service.py`、QQCC 市集代码、Skill 体积审计 | 已修正 | 存储与社区边界有效；补充 Web 好友搜索与 QQCC 修仙市集口径；2026-07-04 同步举报治理入口、`gallery_reports` 去重、Dashboard 筛选/处理/联动下架和 `History.is_public` 同步红线；自由P图 v2、LTX、SCAIL-2、`i2i_draw` 与 apply-context 口径继续有效 |
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
