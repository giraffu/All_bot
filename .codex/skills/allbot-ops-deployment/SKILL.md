---
name: "allbot-ops-deployment"
description: "处理 Docker Compose 编排、按模块风险分级发布、云正式/云测试控制面、本地正式灾备、Alembic 迁移、RunPod/LAN AIO、Dashboard autoscaler、cloud-prod shadow 同步、R2/legacy 媒体恢复和故障恢复。核心用户链路默认先发测试；正式发布或生产 mutation 必须用户明确确认。"
---

# AllBot 运维指南与容器管理

本技能是运维任务的轻量入口，只保留稳定路由、高压红线和最小验证要求。具体 SOP 以对应 `docs/子模块_*.md`、脚本 `--help`、当前 compose/env 和运行态快照为准。

## 1. 先读什么

按任务场景只读必要资料，避免一次性把所有运维细节塞进上下文：

| 场景 | 必读资料 |
| :--- | :--- |
| 云测试部署、联调、修复 | `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` |
| 并发 AI worktree、单批次 main PR、按需共享测试站切换 | `allbot-concurrent-workspaces`、`docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md` |
| 云正式发布、单服务热修、维护窗口 | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`docs/子模块_运维指南与容器管理_ops_deployment.md` |
| 云正式整体不可用、本地接管 | `docs/子模块_本地正式灾备切换_local_prod_fallback.md` |
| RunPod、GPU worker、autoscaler | `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`、`references/runpod-lan-runtime.md` |
| LAN AIO 当前态、缓存态、候选切换、单卡 takeover/recover/restart | `allbot-lan-aio-operator`、`${XDG_STATE_HOME:-~/.local/state}/allbot/lan-aio/current.yml`、`ops/gpu_pool_controller/config/lan_aio_prod_slots.yml` |
| 局域网 GPU 登录、节点资源、ComfyUI | `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`、`docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` |
| cloud-prod shadow 同步、R2 shadow、完整合并桶 | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`docs/子模块_系统资源与容量画像_resource_inventory.md` |
| R2 可见热集审计、legacy 媒体补齐 | `docs/子模块_社区与存储_gallery_storage.md`、对应 `scripts/*r2* --help` |
| QQCC 单服务更新 | `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`、`allbot-qqcc-lazy-bot` |
| 付费群审核 Bot | `docs/子模块_付费群审核Bot_paid_group_guard_bot.md`、`allbot-tg-fsm` |
| 网络、Cloudflare、边缘节点 | `allbot-cloudflare-ops`、`docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md`、`docs/子模块_网络暴露与代理穿透_network_proxy.md`、`docs/子模块_边缘节点运维指南_edge_node_ops.md` |

若用户报告失败、慢、卡住或线上异常，叠加 `allbot-diagnosing-bugs`。若改运维脚本、preflight、helper 或回归门禁，叠加 `allbot-tdd`。若改知识库事实，叠加 `allbot-kb-auto-updater`。

## 2. 当前稳定入口

- schema v2 将不可变产物拆为 `control-plane`、`test-execution`、`gpu-execution` 三条环境无关发布链；`release-index.json` 引用三份 manifest，test/prod 只选择模块并注入配置。已有增量基线时，普通自动发布只从策略影响集合中选择 bundle 内 `source_sha` 等于目标 SHA 的运行时 artifact；全部 artifact 均复用旧 `source_sha` 时选择集必须为空，风险 level/matched rules 只作为审计元数据，不得触发空重建。`--services` 仍只能扩大影响集合；显式 `--modules dashboard|qqcc-bot|qqcc-config` 是三个受控独立模块边界，一次只能选择一个完整组，并从组内每个 artifact 自己的 `source_sha` 分别计算差异。旧版局部 `current.json` 缺失的 artifact 只从按时间排序的成功 history 在内存恢复，不现场改状态；组内混合版本允许保留各自真实基线。
- `deploy/release-artifacts-v2.json` 是跨 track 的发布契约；已有可信基线时，CI 必须对前后 catalog 做逐 artifact 语义比较，只重建定义变化的 artifact 及其真实 base descendants。控制面、Public Web、文档或发布工具变化不得把 `gpu-execution` 自动卷入构建；main bundle 必须从目标 main 全祖先中最近的完整 main-channel GPU manifest 原样继承未变化 profile 的 digest、source/OCI revision 与模型证据，使 Dashboard 始终获得完整 pin 集，但这不构建、测试或部署 GPU。缺少完整可信祖先时 main bundle fail closed。GPU artifact/profile、`remote_workers/**` 或其真实基础依赖变化才进入 GPU 专用 manifest/canary/operator 链路；本轮变化 profile 不能由历史基线满足，仍必须由 `allbot-gpu-release-manifests:<full-sha>` 提供同 SHA attestation，否则在不可变 main bundle tag 创建前 fail closed。禁止把旧镜像重新标注成新 task type。
- main-first planner 不得只用 artifact `source_sha == target_sha` 判定部署集；还必须把目标 bundle exact digest 与当前 track state 逐 artifact 比较。旧 main 构建、新 bundle 复用的 artifact 只要当前缺失或 digest 不同就必须选入；只有 exact digest 已一致才能空计划/no-change。同时静态排除目标环境不存在的服务，可选 Bot 继续按已验证宿主配置过滤。
- 并发研发以不可变 handoff 冻结多个任务 head，只创建一个 `release-batch -> main` PR。批次 PR 不构建发布容器；main push 的上游 CI 成功后，`modular-release-v2.yml` 才为该 main SHA 构建一次 main-channel bundle。`codex/test-train`、test-candidate 和 approval/promotion workflow 只作历史兼容，不再生成新候选。
- 发布策略是 `--strategy auto|standard|direct|emergency`。核心用户链路与已有专属测试实例的 QQCC Config 默认 standard；Dashboard 与 GPU 执行面默认 direct；公共 Web 默认 standard、可显式 direct；核心只允许带 reason/approved-by 的 emergency。普通混合变更取最高风险。独立模块发布只重建所选服务；migration、未知共享 Compose/env 或未审计跨模块契约仍 fail closed。已审阅并固定内容 SHA256 的 owner-only Compose/env 与向后兼容 schema/config snapshot 可继续独立发布；任一文件内容变化即恢复阻断，不能把 snapshot 当通配 allowlist。
- `--skip-gate` 只允许 `ci-tests|test-deploy|test-acceptance|observation|gpu-business-canary`，并受策略约束。CI `validation_mode=build-only` 仍必须从受保护 main 完整 SHA 构建 digest 产物，发布时显式跳过 `ci-tests` 且记录 reason/approved-by；任何 execute 都禁止 `--skip-ci-checks`。main 血缘、成功构建、digest/checksum/OCI revision、配置、目标健康、事务/回滚和非目标服务不重建永久保留。
- 云测试默认部署 main bundle 中 standard 所需的 control-plane/公共 Web artifact；专属测试 QQCC Config 前后端固定使用测试配置及 8045/8088，Dashboard 仍不进入测试站。test-execution 只在专项诊断时显式选择。验收状态按 track + artifact digest 写入 history；direct/emergency 写 `waived`，GPU direct 写 `attested`，不得覆盖其它核心 artifact 的 tested 证据。
- 唯一发布入口是 `scripts/release.py plan|preflight|deploy|deploy-module|rollback|recover|config-plan|config-apply|credential-isolation-complete`。`deploy-module --module <name>` 默认一次锁定最新受保护 main，可显式传完整 SHA；接受成功 full main CI bundle，standard 模块在生产 preflight 中继续要求 main-channel exact-digest 测试证据，机器依赖集合只能扩大。普通 `preflight/deploy` 不拉材料；快捷入口可在 mutation 前只读拉取 main bundle。云端不 build、不挂载源码、不接收代码/env rsync。
- 云控制面运行配置的唯一事实源是目标主机 `/etc/allbot/test.env` 或 `/etc/allbot/prod.env`。发布器合并版本化非敏感默认值后，只生成权限 `600` 的 `/var/lib/allbot/config/<env>/<revision>/<service>.env` 逐服务投影；`release.env` 不保存秘密。全局 `config-plan/config-apply` 校验完整契约；`deploy-module` 只校验机器定义的目标模块逐服务闭包，但仍校验现有全部投影完整性、全局环境语义与 revision，非目标服务缺少尚未迁移的 canonical key 不得阻断 owner-only rolling。正式机完全没有 active projection、且用户只授权首次 Dashboard rolling 时，唯一局部例外是 `config-plan/config-apply --module dashboard`：只暂存 Dashboard 前后端投影与指针，禁止维护、备份、Compose 和容器重启；可兼容的既有 legacy 宿主键必须是代码内精确清单且不进入 Dashboard 投影，清单外未知键、闭包逃逸或已有 active revision 均拒绝，禁止删除旧宿主键来迁就局部发布；完整计划仍必须把其它未投影服务报告为 drift。配置漂移、目标缺键、未知键或其它首次契约切换仍 fail closed；未知影响和首次正式收敛强制完整维护与备份。
- 公共云 Compose 的逐服务 `env_file` 使用 `required: false` 只允许局部发布解析缺少非目标投影的项目，并必须使用 `format: raw` 保留密码 hash、Token 等值中的字面 `$`；发布器仍须在 pull/up 前严格验证并生成目标服务投影，不能据此启动缺配置目标。非目标服务不得 `up`，容器 ID/digest/revision/启动时间保持不变。该公共 Compose 只在内容 checksum 与 policy 中审阅快照完全一致时允许 owner-only rolling，后续漂移恢复共享契约 blocker。
- 秘密隔离完成前，正式 mutation 额外要求 `--accept-pending-secret-rotation --reason --approved-by`。轮换完成只能通过 `credential-isolation-complete --evidence <json> --approved-by <name> --confirm-prod --execute` 写入状态；证据必须在一小时内、覆盖全部目标键、证明 test/prod 不复用、所有目标健康且旧凭据已撤销。跨环境比较使用随机 challenge HMAC，只输出键名、是否相同和证据摘要；GPU token 切换继续走 LAN AIO/RunPod 专用 operator。
- 云测试：先执行 `scripts/release.py plan --env test --sha <sha>`，再以同一 SHA 执行 `deploy --env test --sha <sha> --execute`。影响集合由 `deploy/release-policy.yml` 计算，`--services` 只能扩大，不能缩小。
- 本地主服务器兼任测试 Worker host 时，使用受限的本地测试配置（当前标准路径 `/home/hfy/.config/allbot/test.env`，`600`）并显式传 `--env-file`；发布器必须把 Worker compose 的 `ALLBOT_ENV_FILE` 绑定到这个实参，不能复用云主机 `/etc/allbot/test.env` 的路径字符串。云端事实源与本地副本内容/revision 必须一致，生产 env 不得复制到测试 Worker host。
- schema v2 的 `test-execution` 尚无 track-scoped `current.json` 时属于首次发布：计划必须标记 `initial-release`，预检用 allowlist 对应的 legacy Agent/Relay 核对端口所有权，切换前把运行中容器快照写到 `release-env/test-execution/<sha>/legacy-worker-running.txt`。失败恢复和后续 immutable 回滚都必须读取同一 track-scoped release-env，禁止错误要求一个尚不存在的新式 Relay 或回落到无 track 的旧目录。
- schema v2 的事务 journal 与 staged state 也必须按 track 隔离到 `transactions/<track>/<sha>.json|.state.json`；远端云 Compose 的非敏感发布合约同步隔离到 `/var/lib/allbot/releases/<track>/<sha>/release.env`，Worker host 合约为 `release-env/<track>/<sha>/release.env`，legacy 云快照沿用对应 track 目录。Worker preflight 必须按 track 读取回滚合约；计划未选择任何 cloud service 时 cloud preflight 直接跳过，不能用不存在的云端 track 合约阻断 Worker-only 发布。云端控制面的历史回滚目标若早于 track 隔离迁移，必须优先找 track-scoped 合约，仅在缺失时兼容同一 SHA 的 `/var/lib/allbot/releases/<sha>/release.env`，且 preflight、失败恢复与恢复验证使用相同选择逻辑；新发布不得写回 legacy 路径。即使目标 SHA 相同，control-plane 与 test-execution 也不得互相覆盖 journal、staged state 或 release contract。test-execution 的 `initial-release` 只表示 legacy Worker 切换，不得把控制面首次发布专属的 Postgres/Redis 闭包带入 Worker-only 事务。`recover --track <track>` 可兼容读取升级前的同 track 无目录 journal，但恢复写回必须进入 track-scoped 路径。
- 测试站不运行 Dashboard，但 Dashboard-only candidate 仍可能以携带全部继承 artifact 的完整 bundle 成为 control-plane 记录基线。若其 rollback checkout/release.env 缺失，`recover --modules dashboard --repair-rollback-materials` 必须从同一完整 bundle 展开实际启用的测试服务，逐项核对 `current.json` digest 和运行容器 image digest 后才物化完整回滚合约；不得寻找不存在的测试 Dashboard 容器，也不得只写 Dashboard 变量或跳过运行服务核验。
- `recover --repair-rollback-materials` 必须能恢复 RunPod profile pin 契约上线前已经部署的 Dashboard 基线：仅该恢复路径可接受旧 bundle 缺少 pin，并继续只物化旧 checkout/release.env；普通 plan/preflight/deploy 的 main Dashboard pin 完整性门禁不得放宽。恢复仍不得 pull/up/stop/restart，旧 Dashboard 本身不消费新的 pin JSON。
- 若 test 已有 control-plane 状态但 immutable PostgreSQL/Redis 容器缺失，普通发布必须继续 fail closed，禁止手工 compose 或跳过 drain。只有先从停止的 legacy Redis 取证 worker DB 的 pending/running 均为 0，才可对可信 main bundle 使用 `--repair-test-data-services --services postgres --services redis --confirm-legacy-cutover --confirm-empty-test-queue` 做一次维护式数据服务修复；该模式仅允许 test/control-plane 且必须成对选择 PostgreSQL/Redis。
- 首次测试 immutable 切换必须使用 `--confirm-legacy-cutover`，并把 Postgres/Redis 纳入初始依赖闭包；test overlay 必须复用已确认的 `deploy_cloud-postgres-test-data`/`deploy_cloud-redis-test-data`，保留 `postgres-test`/`redis-test` 网络别名。全部 digest pull/OCI 校验和 legacy Central 队列排空完成后才能停止本轮实际运行的 legacy 控制面容器；新项目失败必须先移除目标容器再重启记录中的旧容器，禁止把普通 `compose up` 当作首次交接。
- Frontend 镜像 smoke 必须真实执行 `/docker-entrypoint.d/05-select-dashboard-spa.sh`，分别验证 dashboard 和 QQCC 模式生成 `/etc/nginx/templates/default.conf.template`；只检查 SPA 文件存在不足以通过发布门禁。
- Dashboard Backend 镜像 smoke 必须以显式 CI 哨兵投影注入严格运行配置，再真实 import `dashboard.backend.main` 和 `dashboard.backend.qqcc_config_main`；不得为了让 smoke 通过而向镜像或源码恢复秘密默认值。独立 `Dockerfile.dashboard-backend` 与可信 bundle 实际使用的多阶段 `Dockerfile.control-plane` 都必须提供完整依赖闭包，至少包含根 `config.py`、`src`、`shared`、`paid_group_guard_bot`、Dashboard 运维路由依赖的 `ops`，以及 LAN AIO 发布链路需要的 `scripts/gpu_release_rollout.py`、`release_manifest_v2.py`、`release_strategy.py`；禁止只修未被 release builder 使用的 Dockerfile，也禁止用单个文件存在检查代替导入闭包。
- 环境中立门禁对每个可运行 Python service artifact 分别注入 test/prod 哨兵身份并真实导入；`python-runtime-base` 和 `python-worker-base` 不携应用源码，只执行 Config.Env 与文件系统扫描，不得对其执行服务身份启动检查。
- 云测试控制面首次收敛旧 env 时，使用 `scripts/migrate_legacy_test_env.py --control-plane-only`。它只在 canonical key 缺失时复制已知 `_TEST` 别名，仅对已知 Telegram 公网 endpoint 或自建 `:8081`/`:8082` 组合生成 file base，其它组合 fail closed；此模式不得新增、归一或改写任何 Worker 槽位键。
- 控制面配置 revision 明确排除 `ALLBOT_WORKER_*` / `CLOUD_TEST_WORKER_*` / `CLOUD_TEST_SHARED_AIO_*`：这些键原样留在受限宿主 env，但不进入控制面投影、漂移和影响集，任何变更继续走 test-execution/LAN AIO/RunPod 专用链路。Dashboard 自身消费的 `RUNPOD_*` / `LAN_AIO_*` 仍是控制面服务配置；其它未知键仍 fail closed 并扩大为全服务影响。
- `config-apply` 和 migration 的 `pg_dump` 在容器 POSIX `/bin/sh` 中运行；`postgresql+asyncpg:` 转换必须使用 `case` + `${VAR#prefix}`，禁止 Bash-only 替换语法。未知 scheme、空备份或非单 Alembic head 都必须在 projection/容器变更前 fail closed，不得人工跳过。
- GPU profile 镜像在 `COPY remote_workers` 后必须以镜像内 `PYTHONPATH` 真实 import `comfy_agent.workflow_task_patchers`；只校验文件存在或主仓库 `src` 可导入不足以证明 baked worker bundle 闭包完整。导入失败必须在镜像构建阶段阻断，禁止等 LAN/RunPod 启动后再发现。
- Compose 内部调用必须使用当前 project service DNS `http://central-api:8003`。历史 prod env 仍含 `central-api-prod` 时，获准单独滚动 Dashboard 的 prod overlay 必须显式覆盖 Dashboard Backend 的 `API_BASE`，不得为此修改或重启其它正式服务；后续完整配置收敛再统一修正宿主投影。发布成功前必须在目标容器 import `config`，并通过解析后的 `config.API_BASE` 请求 `/health`；禁止把测试或正式别名硬编码进通用 smoke，也不能只检查原始 env。
- 通过 `ssh ... bash -s` 执行远端发布脚本时，脚本内所有 `docker compose exec/run` 都必须显式使用 `</dev/null`；仅 `-T` 仍可能读取并吞掉后续脚本。远端脚本必须最后输出绑定目标 SHA 的完成标记，发布器还要逐服务核对容器 `.Config.Image` digest 与自有镜像 OCI revision，三者全部通过后才能写 `current.json`。
- 测试与正式 Web 必须校验同一 Web tar 后走统一 Wrangler Pages 发布器；环境差异只能来自版本化公开 runtime config。干净 release checkout 不假定存在 `node_modules`，发布器必须交叉校验 `frontend/package.json` 与 lockfile 中的精确 Wrangler 版本，再由 `npx --yes --package=wrangler@<exact>` 获取该版本。发布成功必须同时满足 production deployment branch/SHA/stage、`canonical_deployment.id` 和 custom domain runtime `release_sha`/revision；不能以 `pages.dev` URL 代替 canonical 验证。`--skip-web` 只允许恢复控制面/Worker，必须记录 `health.web=skipped`，且不得晋级正式。
- `deploy` 在任何 mutation 前强制复用全量只读 preflight。云测试事务顺序为云控制面 → 测试 Worker → Pages → staged state/current-history commit，schema v2 的 staged state 必须原子提交到对应 track 路径；失败按 Pages → 测试 Worker → 云控制面逆序恢复。正式事务只包含云控制面 → Pages → 状态提交，生产 GPU Worker 由各 GPU host 的专用 operator 独立发布，prod preflight/deploy/recover 不检查 heartbeat/relay，也不停止、重建或恢复 Worker。恢复验证只覆盖本事务实际尝试过的阶段；不完整时保持维护并写 `rollback_failed`。`recover --transaction ... --execute` 只能逆向恢复，禁止续跑失败阶段。
- 本地主机默认 release checkout/env/Pages token 为 `~/APP/All_bot-release`、`~/.config/allbot/<env>.env`、`~/.config/allbot/cloudflare-pages.token`；云控制面保持 `/home/deploy/APP/All_bot-release` 与 `/etc/allbot/<env>.env`。bootstrap 必须显式选择 `cloud-control` 或 `local-worker-host` 角色。
- 影响 planner 的全栈集合不代表开启未配置的可选 Bot。`release.py plan` 必须基于已校验 env 输出 `cloud_services`/`disabled_cloud_services`；仅允许按 QQCC token、`PRIVATE_QQCC_BOT_ENABLED`、付费群 Bot token 过滤对应三个可选 runtime，禁止用配置过滤核心 API、Postgres/Redis、主 Bot 或其它自动依赖。
- `--skip-env-checks` 仅供无运行态秘密的 release CI 执行非 mutation `plan` 自检；`deploy`/`rollback` 必须拒绝。实际 test/prod plan 与执行仍须校验对应受限 env，禁止把 CI 的 `config_validation=skipped` 当作部署配置通过。
- standard 测试验收只要求本次选择 artifact 对应的检查和精确 digest；公共 Web 校验 tar checksum，核心按选中服务检查，测试 Worker 仅在显式 track 中检查 heartbeat。默认观察至少 24 小时；短观察仍需 evidence 开关、原因、批准人和 `--confirm-short-observation`。
- 正式 standard 晋级从云测试 retained history 按 artifact + exact digest 查找 main-channel verified 证据；direct artifact 只按明确风险策略豁免，不能伪装 tested。每次 execute 仍必须 `--confirm-prod`。
- `central-api`、`web-api`、主 Bot、QQCC Bot、私有 Bot worker 任一被选中时，混合事务整体进入生成维护；Dashboard、QQCC 配置后台、Payment、Paid Group Bot、Public Web 单独发布 rolling 替换。migration、Compose/发布契约、未知影响始终完整维护、备份和单 Alembic head。`no-change` 只有实际容器 RepoDigest、健康和 config revision 全部一致才能报告。
- test/prod 共用 main bundle 镜像；环境身份、DB/Redis、Token、对象存储、bucket、域名、Bot username 和开关只允许来自宿主 env/overlay/Web runtime config。`.dockerignore` 必须同时递归排除根目录与任意子目录的 `.env`/`.env.*`，避免目录级 `COPY` 带入开发示例。main CI 必须执行 `validate_release_environment_neutral.py` 检查 build context、Dockerfile、当前 main SHA 新构建镜像的 Config.Env/文件系统/双环境解析和 Public Web dist，且不得输出秘密值；复用 artifact 保留原构建 SHA 的成功扫描证据，不得用任意 SHA 过滤器绕过当前构建。
- 本地正式灾备：`safe_deploy.sh` 只用于云正式整体故障时的临时接管，不是日常部署入口。
- 普通窄更新仍通过影响 planner 和必要的 `--services` 扩大集合表达；两个 fast-track 均禁止同时传 `--services`，也禁止退回单文件同步、rsync 或现场 `--build`。
- QQCC 私有 Bot worker：test/prod service 分别为 `qqcc-private-bot-worker-test/prod`，profile `qqcc-private-bots`，入口 `python -m qqcc_private_bot.worker`。它涉及 Alembic、shared secret、Web API webhook、QQCC Config、官方 QQCC membership checker 与公网 Host，不属于 QQCC 三服务快速更新；当前生产 `PRIVATE_QQCC_BOT_ENABLED=true` 且 webhook/profile/owner Host 已启用，测试环境仍禁用该 worker。
- `scripts/update_cloud_test_with_maintenance.sh`、`scripts/update_cloud_prod_with_maintenance.sh`、`scripts/update_cloud_prod_qqcc_bot.sh` 已是 fail-closed 兼容壳，任何参数都不会再同步或构建。
- cloud-prod shadow 同步：`scripts/sync_cloud_prod_to_local_shadow.py` 默认 dry-run，真实执行必须 `--execute`。
- RunPod 正式手动池：日常入口优先 `scripts/runpod_prod_ops.sh status|up|add|enable|disable|restart|down|scale|canary|rollback|rollout-release`。release rollout 必须传 release index/full SHA/profile/单 slot，先 disabled 验证 exact digest/heartbeat；失败恢复旧 exact image 并停止。
- GPU/LAN AIO fleet：具体状态查看、缓存预热、候选切换、单卡 takeover/recover/restart 优先加载 `allbot-lan-aio-operator`，并通过 `scripts/lan_aio_fleet_prod_ops.py`、Git catalog 与 XDG 本地 state ledger 操作；普通 profile 切换不写仓库。gpu-002 SCAIL-2 正式 slot0 也必须先声明在 catalog 里让 operator 可见，`scripts/lan_scail2_aio_prod.sh` 仅作为 SCAIL-2 低层启动/重建/回滚工具。

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
- 共享云测试站只有一个写入者。A-H 功能 AI 不得部署；main bundle 构建完成且用户要求测试后，由集成 AI通过 release 事务锁切换确实要求测试的 control-plane/公共 Web；test-execution 仅用于专项诊断，显式启用时按 control-plane → test-execution 顺序切换。
- 日常研发验证也先形成完整 Git SHA 和 CI release；发布器可只 recreate 自动影响到的模块，但代码、shared、locale 与 Worker 依赖始终来自同一 release。
- 若发布器选中 `bot` / `qqcc-bot`，仍须确认没有第二个同测试 token polling 实例。
- cloud-test worker 由本地主服务器经 Tailscale 接入测试 Central；默认常驻只保留 test-1 与 test-8，其它测试 worker 只在 smoke/canary 窗口启用。test-1 的当前 i2i_pro 事实源是 `gpu-252` GPU1/8191；GPU0/8192 当前为 `image_to_video`，不得用于图片换脸验收。
- 对象存储为 R2 `user-data-test`，不得误改正式入口。

### 云正式
- 生产控制面在 `allbot-do-sgp1-control`，新发布契约由 `deploy/docker-compose-cloud-base.yml`、prod overlay、`/etc/allbot/prod.env` 和非敏感 `release.env` 管理；旧 compose 仅供首次切换归档/legacy 回滚取证。
- 维护按 artifact 分类由 planner 每次计算；生成入口混合发布一律维护，管理面/Public Web 等无生成集合直接原子替换，locked 变更一律完整维护。最终总结记录 planner level、实际替换服务、no-change 或回滚结果。
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
- 正式 Dashboard RunPod operation 必须消费同一 main release index 的完整 `profile -> image@sha256` pin 集合并覆盖 `/app/.env` 历史 ref；缺 profile、mutable tag 或共用 image env 对应冲突 digest 时一律 fail closed。Dashboard control-plane `release.env` 只记录这组非敏感 pin JSON，不修改真实 prod env，也不重建或替换已经运行的 Pod。未变化 profile 可以来自该 bundle 审计记录的完整祖先 manifest，必须保留原 source/OCI revision，不能伪装成当前 main 的 GPU 构建或 canary。PornMaster FP8/BF16 共用 runtime 镜像与 single/multiple workflow，release index 中二者映射到同一 image env 时必须解析为相同 digest；差异由 task type、模型 manifest、GPU/`--lowvram` 和 UNet 节点替换表达。
- LTX 新 SHA 只允许发布到当前仓库 Actions 可写的 `allbot-comfy-runpod-ltx-video-v2` 包；旧无 `-v2` 包仅可作为 digest-pinned 历史回滚来源，不能登记新的 code/workflow revision。
- Dashboard autoscaler 基于预计清空时间、profile 阈值、Redis leader lease 与 operation store 做 add/down/restart/enable；不直接操作本地 worker，不绕过 RunPod 门禁；RunPod Worker 卡片的 `锁定/解锁` 会让手动删除、autoscaler down 和 add cleanup 跳过该 worker。
- Dashboard 成功删除 RunPod 后，operation store 的同 agent delete 记录必须在 heartbeat 新鲜窗口内充当删除墓碑；Central 残留的 `disabled + idle|running` heartbeat 不得触发自动 enable，未被删除的其它暂停 RunPod 仍可正常恢复。
- LAN AIO 的易变运行事实不写进 Git 或本 skill 正文；当前 profile、缓存 marker、验证时间与审计写入本地主 XDG state ledger，切换前必须用 live + ledger + catalog 三方仲裁，任一 drift 都 fail closed。
- Dashboard 不再提供 LAN AIO profile/slot 列表、候选切换、`takeover`、`recover` 或 `warm-cache` API；当前态和任务显示走 `/api/system/workers`，Worker 卡片只保留 `pause/enable/restart` 基础控制。
- 新增 LAN AIO 候选先走 `scripts/lan_aio_fleet_prod_ops.py candidate-plan --node-id ... --profile ... --replace-slot ...` 生成 YAML patch 和校验摘要，再由 Git/YAML 事实源合入；失败现场恢复入口只允许 `recover --physical-slot <node>:gpuN --slot <slot-id> --prefer old|candidate` 这种单物理 GPU/精确 slot 范围。
- 云正式 Dashboard 若触发 LAN AIO worker `pause/enable/restart`，不可变 prod overlay 必须固定 SSH runner，生产 env 必须提供 runner host 与 key directory，Compose 只读挂载精确私钥；本地主保留 Tailscale SSH 22 端口，已开启 linger 的用户级 systemd OpenSSH listener 默认只在 Tailscale 地址的 2222 端口为 runner 服务。发布 preflight 检查 key 可读性与 `600` 权限，并真实连接 runner 核对 helper/env 契约；任何缺项都 fail closed，禁止回退到云容器内 local helper。slot 管理 mutation 仍只由本地 AI operator/CLI 执行。
- LAN AIO 真实接管按单 slot 执行：preflight -> registry/镜像准备 -> pull-image -> warm-cache -> drain-legacy -> wait-idle -> stop-old -> start-disabled -> 验证 disabled heartbeat -> enable-aio；`stop-old` 保护窗口后失败应自动回滚旧服务，优先恢复产能。
- 低频镜像 tag、RIFE 缓存、SCAIL-2/LTX profile、gpu-177/gpu-252/gpu-002 细节只在需要时读取 `references/runpod-lan-runtime.md` 和 GPU Pool 文档。

## 5. 生产单服务发布

1. 确认用户确实要求正式发布或生产热修。
2. 确认目标 service 存在，并确定是否涉及 Alembic、shared env、worker workflow 或跨服务契约；同时记录本次维护意图：用户未指示则为“开启”，用户当次明确要求时才为“不开启”。
3. 对精确 SHA 运行 `release.py plan --env prod --track control-plane`，再运行只读 `preflight`，检查自动影响集合、维护等级、migration、Pages canonical/自动部署和控制面/Web 回滚材料；prod 报告中的 Worker 检查必须是 `skipped`。planner 判定强制 maintenance 时拒绝关闭；请求开启但发布器无法实际建立/保持维护，或请求关闭但发布器无法证明不会进入维护时，都在 mutation 前停止。
4. 先审阅 plan/preflight 的 `risk_class/strategy/validation_mode/skipped_gates/gates`。单独 Dashboard、QQCC Bot、QQCC Config 分别用 `--modules dashboard|qqcc-bot|qqcc-config`，不得在一次独立事务中混选；standard 只晋级 history 中同 artifact digest 的 tested 证据，QQCC Config auto standard，Dashboard auto direct。公共 Web direct 和核心 emergency 必须显式风险接受。所有正式执行仍带 `--execute --confirm-prod`，并确认计划只重建目标服务。
5. 手工 compose、旧 QQCC 快速脚本、rsync 和现场 build 均不是紧急旁路；无法通过发布器时停下修复发布契约。
6. 结束后核对容器 digest、OCI revision、`current.json` 中目标 artifact 的 `source_sha`、健康检查和未触碰服务启动时间；同一 track 的非目标 artifact 版本必须保留。

## 6. 验证矩阵

- 基础代码/迁移：`python -m alembic heads`，必要时 `alembic upgrade head`。
- 私有 Bot 门禁：未启用基线用 `python scripts/validate_private_qqcc_bot_env.py --env-file <ignored-env> --allow-disabled`；启用前去掉 `--allow-disabled` 做严格校验，并确认生产发布授权后才执行 migration/profile/webhook/Cloudflare mutation。
- 文档：`python scripts/doc_quality_checker.py`。
- shell 脚本：`bash -n <script>`，再跑对应 dry-run / `--help`。
- 云测试：cloud-test compose `ps`、`8004/health`、`8001/api/health`；只有显式启用 test-execution 时才检查 Central `/system/workers` 和本地 relay `/ready`。管理面端口不属于测试验收。
- 云正式发布事务：云内 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health`、`8086/api/health`，公网 `https://api.aivison.it.com/api/health`、`https://rmb.aivison.it.com/pay/result`。本机 relay 与 Central `/system/workers` 只在独立 GPU Worker 运维任务中验证，不作为控制面/Pages 发布提交条件。
- worker 更新：确认 Central heartbeat、ComfyUI WebSocket、R2 上传成功后才 `/complete`，并观察 `relay_forward_failed`、`sidecar_upload_failed`、`error/quarantined`。
- GPU 单容器：确认目标 ComfyUI `/system_stats`、`/queue`、目标 worker heartbeat，以及另一 ComfyUI 端口未受影响。

## 7. 交付要求

- 研发阶段默认只报告云测试验证结果，不声称已发布正式。
- 正式发布总结必须说明：测试环境验证、用户确认、本次维护模式请求/默认值/实际值、实际更新服务、迁移状态、验证命令结果和回滚入口。
- 若修改部署入口、compose、worker workflow、RunPod profile、R2/legacy 媒体策略、agent control 或运维脚本，同步更新相关 docs/skills，并调用 `allbot-kb-auto-updater`。
