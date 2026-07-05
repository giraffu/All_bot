---
name: "allbot-ops-deployment"
description: "处理 Docker Compose 编排、云正式/云测试控制面、本地正式灾备、Alembic 迁移、RunPod/LAN AIO、Dashboard autoscaler、cloud-prod shadow 同步、R2/legacy 媒体恢复和故障恢复。研发默认先发测试环境，正式发布或生产 mutation 必须用户明确确认。"
---

# AllBot 运维指南与容器管理

本技能是运维任务的轻量入口，只保留稳定路由、高压红线和最小验证要求。具体 SOP 以对应 `docs/子模块_*.md`、脚本 `--help`、当前 compose/env 和运行态快照为准。

## 1. 先读什么

按任务场景只读必要资料，避免一次性把所有运维细节塞进上下文：

| 场景 | 必读资料 |
| :--- | :--- |
| 云测试部署、联调、修复 | `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` |
| 云正式发布、单服务热修、维护窗口 | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`docs/子模块_运维指南与容器管理_ops_deployment.md` |
| 云正式整体不可用、本地接管 | `docs/子模块_本地正式灾备切换_local_prod_fallback.md` |
| RunPod、GPU worker、autoscaler | `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`、`references/runpod-lan-runtime.md` |
| LAN AIO 当前态、缓存态、候选切换、单卡 takeover/recover/restart | `allbot-lan-aio-operator`、`ops/gpu_pool_controller/config/lan_aio_fleet_state.yml`、`ops/gpu_pool_controller/config/lan_aio_prod_slots.yml` |
| 局域网 GPU 登录、节点资源、ComfyUI | `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`、`docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` |
| cloud-prod shadow 同步、R2 shadow、完整合并桶 | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`docs/子模块_系统资源与容量画像_resource_inventory.md` |
| R2 可见热集审计、legacy 媒体补齐 | `docs/子模块_社区与存储_gallery_storage.md`、对应 `scripts/*r2* --help` |
| QQCC 单服务更新 | `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`、`allbot-qqcc-lazy-bot` |
| 付费群审核 Bot | `docs/子模块_付费群审核Bot_paid_group_guard_bot.md`、`allbot-tg-fsm` |
| 网络、Cloudflare、边缘节点 | `docs/子模块_网络暴露与代理穿透_network_proxy.md`、`docs/子模块_边缘节点运维指南_edge_node_ops.md` |

若用户报告失败、慢、卡住或线上异常，叠加 `allbot-diagnosing-bugs`。若改运维脚本、preflight、helper 或回归门禁，叠加 `allbot-tdd`。若改知识库事实，叠加 `allbot-kb-auto-updater`。

## 2. 当前稳定入口

- 云测试日常更新：快速为主，按变更影响只同步必要代码并重建对应 compose service / profile，不默认进入生成维护、不默认等待 Central pending/running 排空。典型命令是在云测试机 `docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml [--profile bot|qqcc-bot] build <service>` 后 `up -d --no-deps <service>`。
- 云测试整栈/维护式更新：只有涉及迁移、跨服务契约、控制面多服务联动、边缘 Web 发布、需要排空队列，或用户明确要求维护窗口时，才使用 `scripts/update_cloud_test_with_maintenance.sh --execute`；`scripts/safe_deploy_cloud_test.sh` 仅作为远端控制面重建子步骤。
- 云正式完整控制面更新：`scripts/update_cloud_prod_with_maintenance.sh`，默认 dry-run；真实执行必须 `--execute --confirm-prod`。
- 云正式远端控制面重建子步骤：`scripts/safe_deploy_cloud_prod.sh`。
- 本地正式灾备：`safe_deploy.sh` 只用于云正式整体故障时的临时接管，不是日常部署入口。
- QQCC 正式单服务更新：`scripts/update_cloud_prod_qqcc_bot.sh --execute --confirm-prod --confirm-single-polling`。用户明确要求 QQCC 单服务更新时，可视为当次正式与单 polling 操作确认；若目标容器、token、env、实例数量或脚本路径异常，必须停下追问。
- Dashboard/服务窄更新：优先用 `scripts/update_cloud_prod_with_maintenance.sh --scope services --services "..."`，只重建目标服务。
- 云测试/云正式/QQCC 这三条整仓 rsync 更新入口必须排除 `local_analytics_platform/`、`backups/`、`logs/`、前端构建产物和密钥文件；本地分析平台数据不属于远端运行代码包。
- cloud-prod shadow 同步：`scripts/sync_cloud_prod_to_local_shadow.py` 默认 dry-run，真实执行必须 `--execute`。
- RunPod 正式手动池：日常入口优先 `scripts/runpod_prod_ops.sh status|up|add|enable|disable|restart|down|scale|canary|rollback`。
- GPU/LAN AIO fleet：具体状态查看、缓存预热、候选切换、单卡 takeover/recover/restart 优先加载 `allbot-lan-aio-operator`，并通过 `scripts/lan_aio_fleet_prod_ops.py`、`lan_aio_prod_slots.yml` 与 `lan_aio_fleet_state.yml` 操作；gpu-002 SCAIL-2 正式 slot0 也必须先声明在 fleet 配置里让 operator 可见，`scripts/lan_scail2_aio_prod.sh` 仅作为 SCAIL-2 低层启动/重建/回滚工具。

## 3. 高压红线

- 未经用户明确要求，不进入正式发布、生产 compose 重建、生产 RunPod mutation、生产 GPU 节点维护或本地正式灾备接管。
- 功能研发、联调、缺陷修复与配置调整默认先上云测试控制面。
- 生产 Bot、QQCC Bot、付费群审核 Bot 必须使用各自独立 token。重建或启动 polling 服务前必须确认没有第二个同 token polling 实例。
- 不输出 `.env.cloud.prod`、`.env.cloud.test`、RunPod API key、Bot token、agent token、JWT secret、R2 key、presigned URL、`docker compose config` 敏感展开或真实数据库 URL。
- 不把 `docker restart` 当代码发布方式；COPY 型服务必须 build/up 目标 service。
- 单服务生产重建禁止 `--remove-orphans`、无 service 名 compose 命令、全组 `docker rm` 过滤器；只清目标 service 容器和同 service label 残留。
- `env_file` 只传给容器，不参与 compose 文件 `${...}` 插值；涉及默认值时必须渲染并核对容器内实际 env。
- Alembic multiple heads 必须先中止处理；迁移通过后显式执行 `alembic upgrade head`，不要写“容器下次启动会自动应用迁移”。
- workflow 运行时事实源是 `workers/comfy_agent/workflows`；Central API 不挂载、不 COPY、不启动校验 workflow。改 workflow/mappings/patcher 后重建或重启目标 worker。
- 新生成对象写 R2 `user-data-prod`。正式 Web/Dashboard 不再生成 legacy MinIO URL；legacy MinIO 只用于迁移补齐、人工回滚、旧外链排障。
- 容量判断以 Central `/system/workers` 当次快照和运维目标为准，不写死“7 个本地 worker”或某次 RunPod 数量。
- GPU 节点操作只碰目标容器/slot；禁止因单容器异常整机 reboot、批量 compose down/up、误停另一张卡的 ComfyUI。
- RunPod 真实 create/start/stop/restart/delete/add/scale 必须同时满足 `RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`、`--execute` 和生产确认。

## 4. 场景要点

### 云测试
- 使用独立测试 Droplet、测试 Postgres/Redis/Central/Web/Dashboard/imgproxy/Bot。
- 日常研发验证默认直接重建目标模块容器；例如 Bot 展示/FSM 改动只重建 `bot-test`，Web API 改动只重建 `web-api-test`，Central 改动只重建 `central-api-test`，Dashboard/QQCC Config 改动只重建对应前后端 service。不要为了普通测试更新写维护标记或排空队列。
- 若启动或重建 `bot-test` / `qqcc-bot-test`，先确认没有第二个同测试 token polling 实例；用 `--profile bot` / `--profile qqcc-bot` 限定目标 service。
- cloud-test worker 由本地主服务器经 Tailscale 接入测试 Central；默认常驻只保留 test-1 与 test-8，其它测试 worker 只在 smoke/canary 窗口启用。
- 对象存储为 R2 `user-data-test`，不得误改正式入口。

### 云正式
- 生产控制面在 `allbot-do-sgp1-control`，服务由 `deploy/docker-compose-cloud-prod.yml`、`.env.cloud.prod` 和维护脚本管理。
- `web.aivison.it.com` 是 Cloudflare Pages 静态站；正式 API 健康检查是 `https://api.aivison.it.com/api/health`，RMB 入口是 `https://rmb.aivison.it.com/pay/result`。
- Dashboard 默认走 Tailscale/受控入口；公网管理域名必须有 Cloudflare Access 或等价身份层保护。

### cloud-prod shadow
- 默认数据库路径是云机 `pg_dump` 后临时上传 R2 `user-data-prod/__shadow-transfer/<timestamp>`，本地校验后恢复到 `bot_db_prod_shadow`。
- `R2_BUCKET_SYNC_ENABLED=true` 才镜像 R2 `user-data-prod` 到 MinIO `user-data-prod-shadow`，覆盖/删除进入 quarantine。
- `COMPLETE_MEDIA_SYNC_ENABLED=true` 才从本地 shadow 非破坏式 copy 到 `user-data-complete-shadow`。
- 启用本地正式灾备写入口前必须停 shadow timer、核对 manifest/RPO，并明确服务不会自动切到 shadow 库。

### RunPod 与 LAN AIO
- RunPod 不属于局域网 SSH GPU 池；RunPod profile、镜像、manifest、override 事实源在 `ops/gpu_pool_controller/` 与 GPU Pool 文档。
- Dashboard RunPod 管理和 LAN AIO worker 基础控制只调用既有脚本，不重写 provider 逻辑；`desired_count` 兼容字段按“新增数量”解释，不代表目标总数。
- Dashboard autoscaler 基于预计清空时间、profile 阈值、Redis leader lease 与 operation store 做 add/down/restart/enable；不直接操作本地 worker，不绕过 RunPod 门禁；RunPod Worker 卡片的 `锁定/解锁` 会让手动删除、autoscaler down 和 add cleanup 跳过该 worker。
- LAN AIO 的易变运行事实不写进本 skill 正文；当前每张 GPU 运行 profile、可快速切换候选、缓存 marker、阻断原因以 `ops/gpu_pool_controller/config/lan_aio_fleet_state.yml` 为 agent 维护入口，切换前仍必须用 live status 仲裁。
- Dashboard 不再提供 LAN AIO profile/slot 列表、候选切换、`takeover`、`recover` 或 `warm-cache` API；当前态和任务显示走 `/api/system/workers`，Worker 卡片只保留 `pause/enable/restart` 基础控制。
- 新增 LAN AIO 候选先走 `scripts/lan_aio_fleet_prod_ops.py candidate-plan --node-id ... --profile ... --replace-slot ...` 生成 YAML patch 和校验摘要，再由 Git/YAML 事实源合入；失败现场恢复入口只允许 `recover --physical-slot <node>:gpuN --slot <slot-id> --prefer old|candidate` 这种单物理 GPU/精确 slot 范围。
- 云正式 Dashboard 若触发 LAN AIO worker `pause/enable/restart`，可通过 `DASHBOARD_LAN_AIO_EXECUTION_MODE=ssh` 指向本地主服务器 runner 执行受限的 `disable-aio|enable-aio|restart-aio`；slot 管理 mutation 只由本地 AI operator/CLI 执行。
- LAN AIO 真实接管按单 slot 执行：preflight -> registry/镜像准备 -> pull-image -> warm-cache -> drain-legacy -> wait-idle -> stop-old -> start-disabled -> 验证 disabled heartbeat -> enable-aio；`stop-old` 保护窗口后失败应自动回滚旧服务，优先恢复产能。
- 低频镜像 tag、RIFE 缓存、SCAIL-2/LTX profile、gpu-177/gpu-252/gpu-002 细节只在需要时读取 `references/runpod-lan-runtime.md` 和 GPU Pool 文档。

## 5. 生产单服务重建

1. 确认用户确实要求正式发布或生产热修。
2. 确认目标 service 存在，并确定是否涉及 Alembic、shared env、worker workflow 或跨服务契约。
3. 能走维护式脚本时，优先用 `scripts/update_cloud_prod_with_maintenance.sh --scope services --services "..."`。
4. 若目标是 QQCC Bot，优先走 `scripts/update_cloud_prod_qqcc_bot.sh`。
5. 手工 compose 只作为脚本不适用或紧急抢修路径；必须限定 service 名，禁止 orphan 清理。
6. 结束后验证目标容器、日志、健康检查、非敏感 env 和未触碰服务启动时间。

## 6. 验证矩阵

- 基础代码/迁移：`python -m alembic heads`，必要时 `alembic upgrade head`。
- 文档：`python scripts/doc_quality_checker.py`。
- shell 脚本：`bash -n <script>`，再跑对应 dry-run / `--help`。
- 云测试：cloud-test compose `ps`、`8004/health`、`8001/api/health`、`8044/api/health`、`8087/api/health`、Central `/system/workers`、本地 relay `/ready`。
- 云正式：云内 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health`、`8086/api/health`，公网 `https://api.aivison.it.com/api/health`、`https://rmb.aivison.it.com/pay/result`，本机 relay `127.0.0.1:8013/health`，Central `/system/status` 与 `/system/workers`。
- worker 更新：确认 Central heartbeat、ComfyUI WebSocket、R2 上传成功后才 `/complete`，并观察 `relay_forward_failed`、`sidecar_upload_failed`、`error/quarantined`。
- GPU 单容器：确认目标 ComfyUI `/system_stats`、`/queue`、目标 worker heartbeat，以及另一 ComfyUI 端口未受影响。

## 7. 交付要求

- 研发阶段默认只报告云测试验证结果，不声称已发布正式。
- 正式发布总结必须说明：测试环境验证、用户确认、实际更新服务、迁移状态、验证命令结果和回滚入口。
- 若修改部署入口、compose、worker workflow、RunPod profile、R2/legacy 媒体策略、agent control 或运维脚本，同步更新相关 docs/skills，并调用 `allbot-kb-auto-updater`。
