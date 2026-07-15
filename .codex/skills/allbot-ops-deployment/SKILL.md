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
| 并发 AI worktree、test-train 候选、共享测试站排他切换 | `allbot-concurrent-workspaces`、`docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md` |
| 云正式发布、单服务热修、维护窗口 | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`docs/子模块_运维指南与容器管理_ops_deployment.md` |
| 云正式整体不可用、本地接管 | `docs/子模块_本地正式灾备切换_local_prod_fallback.md` |
| RunPod、GPU worker、autoscaler | `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`、`references/runpod-lan-runtime.md` |
| LAN AIO 当前态、缓存态、候选切换、单卡 takeover/recover/restart | `allbot-lan-aio-operator`、`ops/gpu_pool_controller/config/lan_aio_fleet_state.yml`、`ops/gpu_pool_controller/config/lan_aio_prod_slots.yml` |
| 局域网 GPU 登录、节点资源、ComfyUI | `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`、`docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` |
| cloud-prod shadow 同步、R2 shadow、完整合并桶 | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`docs/子模块_系统资源与容量画像_resource_inventory.md` |
| R2 可见热集审计、legacy 媒体补齐 | `docs/子模块_社区与存储_gallery_storage.md`、对应 `scripts/*r2* --help` |
| QQCC 单服务更新 | `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`、`allbot-qqcc-lazy-bot` |
| 付费群审核 Bot | `docs/子模块_付费群审核Bot_paid_group_guard_bot.md`、`allbot-tg-fsm` |
| 网络、Cloudflare、边缘节点 | `allbot-cloudflare-ops`、`docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md`、`docs/子模块_网络暴露与代理穿透_network_proxy.md`、`docs/子模块_边缘节点运维指南_edge_node_ops.md` |

若用户报告失败、慢、卡住或线上异常，叠加 `allbot-diagnosing-bugs`。若改运维脚本、preflight、helper 或回归门禁，叠加 `allbot-tdd`。若改知识库事实，叠加 `allbot-kb-auto-updater`。

## 2. 当前稳定入口

- schema v2 将不可变产物拆为 `control-plane`、`test-execution`、`gpu-execution` 三条环境无关发布链；`release-index.json` 引用三份 manifest，test/prod 只选择模块并注入配置。`--modules` 与 control-plane alias `--services` 只能扩大影响集合，状态与历史按 track 隔离。
- 并发研发使用精确受保护 `codex/test-train` 的独立 `test-candidate` bundle 仓库；candidate 只能由集成 AI通过 `scripts/test_train_release.py` 部署 test，禁止 `verify-test`、prod、fast-track 和正式晋级。最终 main SHA 必须重新构建、部署和验收。
- 云测试分别部署 control-plane 与 test-execution；v2 bundle 可在不创建 RunPod 的情况下发布，缺少同 SHA canary 的 GPU profile 必须从可用 artifacts 中移除并以 `completeness=incomplete` / `missing_artifacts` 明示。未选择 GPU profile 时，不完整 GPU manifest 不得阻断 control-plane/test-execution 的 plan、部署或晋级；一旦选择 GPU profile，缺失 artifact 仍必须 fail closed，并要求逐 profile 构建、canary 和证据。正式逐模块只晋级测试 verified 的同 digest，共享协议或 migration 可强制扩大原子集合。
- 唯一代码发布入口是 `scripts/release.py plan|preflight|deploy|rollback|recover`。目标必须是可从 `origin/main` 到达的完整 40 位 SHA，并使用 CI 生成的 `release.json`、Web checksum 和 digest-pinned 镜像；云端不 build、不挂载源码、不接收代码/env rsync。`preflight` 与 `deploy` 不自动拉 bundle，所有材料必须预先可读。
- 云测试：先执行 `scripts/release.py plan --env test --sha <sha>`，再以同一 SHA 执行 `deploy --env test --sha <sha> --execute`。影响集合由 `deploy/release-policy.yml` 计算，`--services` 只能扩大，不能缩小。
- 本地主服务器兼任测试 Worker host 时，使用受限的本地测试配置（当前标准路径 `/home/hfy/.config/allbot/test.env`，`600`）并显式传 `--env-file`；发布器必须把 Worker compose 的 `ALLBOT_ENV_FILE` 绑定到这个实参，不能复用云主机 `/etc/allbot/test.env` 的路径字符串。云端事实源与本地副本内容/revision 必须一致，生产 env 不得复制到测试 Worker host。
- 首次测试 immutable 切换必须使用 `--confirm-legacy-cutover`，并把 Postgres/Redis 纳入初始依赖闭包；test overlay 必须复用已确认的 `deploy_cloud-postgres-test-data`/`deploy_cloud-redis-test-data`，保留 `postgres-test`/`redis-test` 网络别名。全部 digest pull/OCI 校验和 legacy Central 队列排空完成后才能停止本轮实际运行的 legacy 控制面容器；新项目失败必须先移除目标容器再重启记录中的旧容器，禁止把普通 `compose up` 当作首次交接。
- Frontend 镜像 smoke 必须真实执行 `/docker-entrypoint.d/05-select-dashboard-spa.sh`，分别验证 dashboard 和 QQCC 模式生成 `/etc/nginx/templates/default.conf.template`；只检查 SPA 文件存在不足以通过发布门禁。
- Dashboard Backend 镜像 smoke 必须真实 import `dashboard.backend.main` 和 `dashboard.backend.qqcc_config_main`；镜像依赖闭包至少包含根 `config.py`、`src`、`shared`、`paid_group_guard_bot` 和 Dashboard 运维路由依赖的 `ops`，禁止用单个文件存在检查代替导入闭包。
- Compose `environment` 必须胜过旧 env 中的入口别名：`BOT_TYPE=TEST` 时 `config._get_env_value()` 优先读取 `API_BASE_TEST`，因此 test overlay 必须同时钉死 `API_BASE`/`API_BASE_TEST=http://central-api:8003`；prod overlay 必须为所有 Python 消费者钉死 `API_BASE`。发布成功前必须在目标容器 import `config` 校验解析后的值，只检查原始 env 或 HTTP health 不足以通过。
- 通过 `ssh ... bash -s` 执行远端发布脚本时，脚本内所有 `docker compose exec/run` 都必须显式使用 `</dev/null`；仅 `-T` 仍可能读取并吞掉后续脚本。远端脚本必须最后输出绑定目标 SHA 的完成标记，发布器还要逐服务核对容器 `.Config.Image` digest 与自有镜像 OCI revision，三者全部通过后才能写 `current.json`。
- 测试与正式 Web 必须校验同一 Web tar 后走统一 Wrangler Pages 发布器；环境差异只能来自版本化公开 runtime config。干净 release checkout 不假定存在 `node_modules`，发布器必须交叉校验 `frontend/package.json` 与 lockfile 中的精确 Wrangler 版本，再由 `npx --yes --package=wrangler@<exact>` 获取该版本。发布成功必须同时满足 production deployment branch/SHA/stage、`canonical_deployment.id` 和 custom domain runtime `release_sha`/revision；不能以 `pages.dev` URL 代替 canonical 验证。`--skip-web` 只允许恢复控制面/Worker，必须记录 `health.web=skipped`，且不得晋级正式。
- `deploy` 在任何 mutation 前强制复用全量只读 preflight。云测试事务顺序为云控制面 → 测试 Worker → Pages → staged state/current-history commit，schema v2 的 staged state 必须原子提交到对应 track 路径；失败按 Pages → 测试 Worker → 云控制面逆序恢复。正式事务只包含云控制面 → Pages → 状态提交，生产 GPU Worker 由各 GPU host 的专用 operator 独立发布，prod preflight/deploy/recover 不检查 heartbeat/relay，也不停止、重建或恢复 Worker。恢复验证只覆盖本事务实际尝试过的阶段；不完整时保持维护并写 `rollback_failed`。`recover --transaction ... --execute` 只能逆向恢复，禁止续跑失败阶段。
- 本地主机默认 release checkout/env/Pages token 为 `~/APP/All_bot-release`、`~/.config/allbot/<env>.env`、`~/.config/allbot/cloudflare-pages.token`；云控制面保持 `/home/deploy/APP/All_bot-release` 与 `/etc/allbot/<env>.env`。bootstrap 必须显式选择 `cloud-control` 或 `local-worker-host` 角色。
- 影响 planner 的全栈集合不代表开启未配置的可选 Bot。`release.py plan` 必须基于已校验 env 输出 `cloud_services`/`disabled_cloud_services`；仅允许按 QQCC token、`PRIVATE_QQCC_BOT_ENABLED`、付费群 Bot token 过滤对应三个可选 runtime，禁止用配置过滤核心 API、Postgres/Redis、主 Bot 或其它自动依赖。
- `--skip-env-checks` 仅供无运行态秘密的 release CI 执行非 mutation `plan` 自检；`deploy`/`rollback` 必须拒绝。实际 test/prod plan 与执行仍须校验对应受限 env，禁止把 CI 的 `config_validation=skipped` 当作部署配置通过。
- 测试验收：图片、视频、Bot、并发锁、locale、Web、Worker heartbeat、回滚演练及默认至少 24 小时观察写入验收 JSON，再执行 `scripts/release.py verify-test ... --execute`；缺少 verified 状态不能晋级。用户明确确认测试服务无问题并授权提前晋级时，可在 evidence 中写 `short_observation_override=true`、非空 `override_reason` 与 `approved_by`，并显式执行 `verify-test --confirm-short-observation`；该例外只跳过固定时长，不放宽任何 smoke、时间顺序、SHA/digest、Web 或 Worker 运行态检查，审计字段必须写入 current/history/acceptance 状态。
- 云正式默认只能把已验收测试环境中的相同 SHA、控制面镜像 digest、第三方镜像 digest 和 Web checksum 晋级，命令必须带 `--execute --confirm-prod`。明确授权的 Dashboard 快速更新可用 `--dashboard-fast-track`。另一条严格例外 `--control-plane-repair-fast-track` 只处理“测试禁用但生产启用的 private worker 薄镜像闭包修复”：必须复用 verified main-channel 测试状态，`tested SHA → target SHA` 只能包含 control-plane Dockerfile、v2 catalog 和 release/docs/tests/skills 元数据；除 private worker 外，每个 digest 变化 artifact 的 catalog inputs 与 Docker target 必须和已测 SHA 等价，private digest 必须在无网络容器中真实导入 `qqcc_bot.main` / `qqcc_private_bot.worker`。migration、业务代码、Compose、GPU、未知路径、显式 modules/services/from-SHA 或其它 fast-track 均 fail closed；main/CI/digest、生产确认、全量 preflight、事务回滚和非目标容器不变仍不可跳过。
- 每次正式发布必须单独确定生成维护模式，不能沿用上次选择：用户当次未指示时默认开启维护；只有用户对该次发布明确要求“不进入维护”时才可请求关闭。关闭只适用于 planner 判定可无维护的 rolling/none 变更；migration、首次/legacy 切换、队列 drain、未知影响或其它强制 maintenance 不能被人工关闭。`plan` 与 `preflight` 必须显示并一致确认请求模式、实际 maintenance level 和门禁；当前发布器若无法表达或证明所选模式，必须在 mutation 前停下修发布契约，禁止手工改 marker、静默采用另一模式或把“默认开启”写成未实际生效。
- 本地正式灾备：`safe_deploy.sh` 只用于云正式整体故障时的临时接管，不是日常部署入口。
- 普通窄更新仍通过影响 planner 和必要的 `--services` 扩大集合表达；两个 fast-track 均禁止同时传 `--services`，也禁止退回单文件同步、rsync 或现场 `--build`。
- QQCC 私有 Bot worker：test/prod service 分别为 `qqcc-private-bot-worker-test/prod`，profile `qqcc-private-bots`，入口 `python -m qqcc_private_bot.worker`。它涉及 Alembic、shared secret、Web API webhook、QQCC Config、官方 QQCC membership checker 与公网 Host，不属于 QQCC 三服务快速更新；当前生产 `PRIVATE_QQCC_BOT_ENABLED=true` 且 webhook/profile/owner Host 已启用，测试环境仍禁用该 worker。
- `scripts/update_cloud_test_with_maintenance.sh`、`scripts/update_cloud_prod_with_maintenance.sh`、`scripts/update_cloud_prod_qqcc_bot.sh` 已是 fail-closed 兼容壳，任何参数都不会再同步或构建。
- cloud-prod shadow 同步：`scripts/sync_cloud_prod_to_local_shadow.py` 默认 dry-run，真实执行必须 `--execute`。
- RunPod 正式手动池：日常入口优先 `scripts/runpod_prod_ops.sh status|up|add|enable|disable|restart|down|scale|canary|rollback`。
- GPU/LAN AIO fleet：具体状态查看、缓存预热、候选切换、单卡 takeover/recover/restart 优先加载 `allbot-lan-aio-operator`，并通过 `scripts/lan_aio_fleet_prod_ops.py`、`lan_aio_prod_slots.yml` 与 `lan_aio_fleet_state.yml` 操作；gpu-002 SCAIL-2 正式 slot0 也必须先声明在 fleet 配置里让 operator 可见，`scripts/lan_scail2_aio_prod.sh` 仅作为 SCAIL-2 低层启动/重建/回滚工具。

## 3. 高压红线

- 未经用户明确要求，不进入正式发布、生产 compose 重建、生产 RunPod mutation、生产 GPU 节点维护或本地正式灾备接管。
- 功能研发、联调、缺陷修复与配置调整默认先上云测试控制面。
- 生产 Bot、QQCC Bot、付费群审核 Bot 必须使用各自独立 token。重建或启动 polling 服务前必须确认没有第二个同 token polling 实例。
- QQCC 私有 Bot token 只能加密存数据库，不写 compose/env；compose 只保存 AES keyring、active key version、独立 fingerprint key、显式 `PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS`、owner JWT key 和 URL/Host 契约。AES/fingerprint/owner JWT 均必须是分别生成的 32-byte Base64URL key，owner JWT 还不得复用 QQCC/主 JWT/Dashboard secret，发布前用 `scripts/validate_private_qqcc_bot_env.py` 校验。forbidden IDs 必须列全官方/测试/付费群 Bot，不能把官方 token 传给管理后端替代。私有 Bot API/file base 必须为独立 HTTPS，禁止继承公网 HTTP Local API；owner/admin Host 显式区分且 unknown Host 404。owner Host 必须允许 Telegram WebView CSP 且不发送 XFO，admin/unknown 仍须 `DENY`/`frame-ancestors 'none'`。禁止输出完整 `docker compose config`；校验使用安全 dummy env + `config -q`。
- private worker 必须注入环境对应的 `QQCC_BOT_TOKEN` / `QQCC_BOT_TOKEN_TEST`，但只用于官方频道会员查询，不能启动 polling。safe deploy 以 validator `--allow-disabled` 做条件门禁：gate 缺失/`false` 时 inactive profile 的 activation secrets 非必填；gate=`true` 时严格校验全部密钥、R2/HTTPS/Host 契约和对应官方 QQCC token。直接 validator 不加该参数是启用前严格模式；worker 在 gate 非真时拒绝启动。
- 不输出 `.env.cloud.prod`、`.env.cloud.test`、RunPod API key、Bot token、agent token、JWT secret、R2 key、presigned URL、`docker compose config` 敏感展开或真实数据库 URL。
- 不把 `docker restart`、现场 `docker compose build` 或代码 bind mount 当发布方式；只允许拉取 `release.json` 中的 digest 并 recreate 目标 service。
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
- 共享云测试站只有一个写入者。A-D 功能 AI 不得部署；集成 AI 使用 test-train 本地排他锁，按 control-plane → test-execution 顺序切换受影响 track。
- 日常研发验证也先形成完整 Git SHA 和 CI release；发布器可只 recreate 自动影响到的模块，但代码、shared、locale 与 Worker 依赖始终来自同一 release。
- 若发布器选中 `bot` / `qqcc-bot`，仍须确认没有第二个同测试 token polling 实例。
- cloud-test worker 由本地主服务器经 Tailscale 接入测试 Central；默认常驻只保留 test-1 与 test-8，其它测试 worker 只在 smoke/canary 窗口启用。
- 对象存储为 R2 `user-data-test`，不得误改正式入口。

### 云正式
- 生产控制面在 `allbot-do-sgp1-control`，新发布契约由 `deploy/docker-compose-cloud-base.yml`、prod overlay、`/etc/allbot/prod.env` 和非敏感 `release.env` 管理；旧 compose 仅供首次切换归档/legacy 回滚取证。
- 维护选择按单次正式发布生效，默认开启；当次用户明确要求不开维护时，只有只读 plan 证明不存在强制 maintenance 条件才允许关闭。最终发布总结同时记录用户请求/default、planner 实际 level 与实际生效模式。
- `web.aivison.it.com` 是 Cloudflare Pages 静态站；正式 API 健康检查是 `https://api.aivison.it.com/api/health`，RMB 入口是 `https://rmb.aivison.it.com/pay/result`。
- Dashboard 默认走 Tailscale/受控入口；公网管理域名必须有 Cloudflare Access 或等价身份层保护。Cloudflare token、DNS、Tunnel、Access 或 Pages/R2 变更先加载 `allbot-cloudflare-ops`。

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

## 5. 生产单服务发布

1. 确认用户确实要求正式发布或生产热修。
2. 确认目标 service 存在，并确定是否涉及 Alembic、shared env、worker workflow 或跨服务契约；同时记录本次维护意图：用户未指示则为“开启”，用户当次明确要求时才为“不开启”。
3. 对精确 SHA 运行 `release.py plan --env prod --track control-plane`，再运行只读 `preflight`，检查自动影响集合、维护等级、migration、Pages canonical/自动部署和控制面/Web 回滚材料；prod 报告中的 Worker 检查必须是 `skipped`。planner 判定强制 maintenance 时拒绝关闭；请求开启但发布器无法实际建立/保持维护，或请求关闭但发布器无法证明不会进入维护时，都在 mutation 前停止。
4. 默认只有目标模块 digest 已在 test 对应 track 标记 verified 且 preflight 全绿，才运行 `release.py deploy --env prod --track control-plane ... --execute --confirm-prod`；`--modules` 只能扩大自动集合。用户明确授权 Dashboard 免测试快速更新时，仍可改用同一 SHA 的 `plan|preflight|deploy --env prod --dashboard-fast-track`，执行仍须 `--execute --confirm-prod`，并确认计划只有 Dashboard 服务、level 为 rolling、`promotion_mode=dashboard-fast-track`。
5. 手工 compose、旧 QQCC 快速脚本、rsync 和现场 build 均不是紧急旁路；无法通过发布器时停下修复发布契约。
6. 结束后核对容器 digest、OCI revision、current.json、健康检查和未触碰服务启动时间。

## 6. 验证矩阵

- 基础代码/迁移：`python -m alembic heads`，必要时 `alembic upgrade head`。
- 私有 Bot 门禁：未启用基线用 `python scripts/validate_private_qqcc_bot_env.py --env-file <ignored-env> --allow-disabled`；启用前去掉 `--allow-disabled` 做严格校验，并确认生产发布授权后才执行 migration/profile/webhook/Cloudflare mutation。
- 文档：`python scripts/doc_quality_checker.py`。
- shell 脚本：`bash -n <script>`，再跑对应 dry-run / `--help`。
- 云测试：cloud-test compose `ps`、`8004/health`、`8001/api/health`、`8044/api/health`、`8087/api/health`、Central `/system/workers`、本地 relay `/ready`。
- 云正式发布事务：云内 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health`、`8086/api/health`，公网 `https://api.aivison.it.com/api/health`、`https://rmb.aivison.it.com/pay/result`。本机 relay 与 Central `/system/workers` 只在独立 GPU Worker 运维任务中验证，不作为控制面/Pages 发布提交条件。
- worker 更新：确认 Central heartbeat、ComfyUI WebSocket、R2 上传成功后才 `/complete`，并观察 `relay_forward_failed`、`sidecar_upload_failed`、`error/quarantined`。
- GPU 单容器：确认目标 ComfyUI `/system_stats`、`/queue`、目标 worker heartbeat，以及另一 ComfyUI 端口未受影响。

## 7. 交付要求

- 研发阶段默认只报告云测试验证结果，不声称已发布正式。
- 正式发布总结必须说明：测试环境验证、用户确认、本次维护模式请求/默认值/实际值、实际更新服务、迁移状态、验证命令结果和回滚入口。
- 若修改部署入口、compose、worker workflow、RunPod profile、R2/legacy 媒体策略、agent control 或运维脚本，同步更新相关 docs/skills，并调用 `allbot-kb-auto-updater`。
