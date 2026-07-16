# Git + 不可变镜像发布

## 1. 状态与边界

截至 2026-07-15，发布 schema 已升级为 v2，拆分为共享控制面、测试执行面和 GPU 执行面三条链。仓库实现不等于运行态已晋级：本阶段只允许部署云测试并等待人工验收，生产部署、正式 GPU mutation、legacy Relay/Worker 下线与正式 Cloudflare Pages mutation均未获授权。原有全量只读 preflight、跨系统事务、逆序恢复和 Dashboard fast-track 安全门禁继续保留。

旧 `update_cloud_*` 脚本已经 fail closed。它们不再包含 rsync 或 build 能力。旧 compose、云端混合源码和容器 image ID 只用于首次切换归档与一次性 legacy 回滚，不是可信 release 基线。

## 2. 事实源

| 事实 | 文件/位置 |
| :--- | :--- |
| CI 构建 | `.github/workflows/control-plane-release.yml` |
| 影响分析 | `deploy/release-policy.yml` |
| 配置契约 | `deploy/env.schema.yml` |
| Web 公开运行时配置 | `frontend/runtime-config.yml` |
| 公共控制面 | `deploy/docker-compose-cloud-base.yml` + test/prod overlay |
| 公共 Worker | `deploy/docker-compose-worker-base.yml` |
| 发布接口 | `scripts/release.py` |
| 主机首次准备 | `scripts/bootstrap_release_host.sh` |
| 状态 | v2 为 `/var/lib/allbot/deployments/<env>/<track>/current.json` 与 `history/`；事务仍记录在 `transactions/<sha>.json` |
| 私密配置 | `/etc/allbot/test.env`、`/etc/allbot/prod.env`，`600 deploy:deploy` |

## 3. 构建契约

并发开发增加独立 `test-candidate` channel。`main` bundle 位于 `ghcr.io/giraffu/allbot-release-v2:<sha>`；精确 `codex/test-train` bundle 位于 `ghcr.io/giraffu/allbot-release-v2-test-candidate:<sha>`。v2 index 显式写 `release_channel` 和 `source_ref`，旧 index 只兼容为 main。Candidate 只能部署 test，禁止 `verify-test`、prod、Dashboard fast-track 与正式晋级；最终合入 main 后必须重新构建并重新测试新的 main SHA。

受保护 `main` 的 CI 先构建不含业务源码的 `allbot-python-runtime-base`。测试 Agent 使用派生的 `allbot-python-worker-base`；Relay 直接继承 runtime base，不携带 workflow、ComfyUI 或 GPU 依赖。Central、Web、Payment、各 Bot、Dashboard Backend、QQCC Config Backend、Agent 和 Relay 都是独立 target/镜像。Dashboard 与 QQCC Config 分别产出 Nginx 镜像，private-bot owner SPA 归 QQCC Config Frontend；Public Web 只构建一份环境无关 `public-web-dist.tgz`。所有自有镜像以完整 SHA 为 tag 并写 OCI revision/source，workflow 禁止覆盖同 SHA tag。

GPU 首次聚合按六个实际 runtime 构建、八个发布 profile 记录：`image_to_video` 与
`wan22_video_v2` 复用同一 Wan22 镜像，`pornmaster_flux2_edit` 与
`pornmaster_flux2_edit_bf16` 复用同一 PornMaster 镜像，但各自必须使用独立模型
manifest 和独立 canary 证据。`img2img` 的同 SHA GHCR 构建入口为
`.github/workflows/runpod_img2img_profile_image.yml`；其它 runtime 使用对应的
`runpod_*_profile_image.yml`。v2 catalog 的 `task_types` 必须等于运行时真实声明，不能
用 Dashboard profile 名替代 Central task type。

发布 v2 release bundle 本身不创建 RunPod，也不要求八个 profile 同时完成 canary。
如果某个 GPU profile 的输入相对上一份可用 bundle 已变化、但没有同 SHA canary manifest，
聚合器不得复用旧 digest，而是在 `gpu-execution-manifest.json` 中移除该 profile，并记录
`completeness=incomplete` 与 `missing_artifacts`。这不会阻断 control-plane 和
test-execution 的产物发布、部署或晋级；各 track 只校验本次选择的 artifacts。后续选择、
部署或晋级缺失 GPU profile 必须 fail closed。CI 会沿
main first-parent 历史寻找最近成功的 v2 bundle 作为增量基线，失败或跳过发布的中间提交
不会导致下一次无条件全量重建。

`release.json` 同时记录自有镜像 digest、imgproxy/Postgres/Redis digest、Web SHA256 和 CI run。部署器拒绝短 SHA、`latest`/普通 tag、缺少 digest、manifest SHA 不一致和未推送/不可从 `origin/main` 到达的提交。

## 4. 配置

代码发布不修改真实 env。Compose 依次读取版本化 `deploy/env.defaults`、`/etc/allbot/<env>.env` 和该 release 的非敏感 `release.env`，后者优先级最高且只包含 release SHA、config revision 与镜像 digest。

Compose 合并后的 service `environment` 必须覆盖旧 env 别名。特别是 `BOT_TYPE=TEST` 时 `config._get_env_value("API_BASE")` 会优先读取 `API_BASE_TEST`，test overlay 因此同时钉死 `API_BASE` 和 `API_BASE_TEST` 为 Compose 内部 `central-api` alias；prod overlay 为所有 Python 消费者钉死 `API_BASE`。发布器在 compose health 通过后还会进入实际容器 import `config`，解析值不是 `http://central-api:8003` 则 fail closed，不写成功状态。

远端发布脚本通过 SSH stdin 交给 `bash -s`。Compose v2 的 `exec -T` 只关闭伪终端，并不保证关闭 stdin；如果不重定向，队列检查可能把后续 pull/up/校验脚本全部读走并以 0 返回。发布器因此要求脚本内所有 `docker compose exec/run` 使用 `</dev/null`，脚本末尾输出绑定 SHA 的完成标记，并在标记前逐服务核对容器 `.Config.Image` 与 manifest digest、自有镜像 OCI revision。缺标记、digest 或 revision 任一不一致都不得写部署状态，也不得作为生产晋级依据。

配置校验：

```bash
python scripts/release.py validate-env --env test --env-file /etc/allbot/test.env
python scripts/release.py validate-env --env prod --env-file /etc/allbot/prod.env
```

独立配置变更先 dry-run，再原子替换并仅 recreate 消费者；生产仍需明确确认：

```bash
python scripts/update_deploy_config.py --env test --source /secure/new-test.env
python scripts/update_deploy_config.py --env test --source /secure/new-test.env --execute
python scripts/update_deploy_config.py --env prod --source /secure/new-prod.env --execute --confirm-prod
```

影响映射在 `deploy/config-impact.yml`。脚本备份旧 env、通过 SSH stdin 写 `600 deploy:deploy` 临时文件、原子 rename，并在 compose 校验或 recreate 失败时恢复旧 env；输出只含变更变量名、revision 和服务名。

错误只输出变量名，不输出值。Worker 槽位由 `ALLBOT_WORKER_SERVICES=worker-01,...` allowlist 决定；当前支持 `worker-01` 至 `worker-08`，发布器只重建该列表，未启用 canary 不会被顺带启动。每个选中槽位必须提供对应 `ALLBOT_WORKER_XX_*` 的 endpoint、任务类型、node/GPU/runtime profile 与 prefetch/pipeline 契约；08 号槽位另外保留 SCAIL-2 workflow/face-swap 配置。

控制面影响分析只允许扩大依赖集合，但可选 Bot 的运行态还必须服从已校验配置：没有对应环境的 `QQCC_BOT_TOKEN*` 时不启动 `qqcc-bot`，`PRIVATE_QQCC_BOT_ENABLED` 未明确开启时不启动私有 Bot worker，没有 `PAID_GROUP_BOT_TOKEN` 时不启动付费群 Bot。`plan` 同时输出 `cloud_services` 与 `disabled_cloud_services`；该过滤白名单只覆盖这三个可选 runtime，不能借配置缩小 API、数据库、Redis、主 Bot 等核心依赖闭包。

测试环境首次迁移使用 `scripts/migrate_legacy_test_env.py` 生成候选文件：`--source` 必须是云测试当前 `/etc/allbot/test.env` 的受限本地副本，作为控制面配置事实源；`--worker-source` 可指向本机旧 `.env.cloud.test`，只补 Worker 槽位参数，不能用旧本机配置覆盖云端新增项。脚本默认 dry-run、丢弃 malformed legacy 行、最后一个合法同名变量生效，补齐测试 admin/owner 非敏感 Host，且只输出计数不输出值。候选必须再经 `scripts/release.py validate-env` 和 cloud/worker Compose `config -q`，随后备份旧 env、`chmod 600`/`chown deploy:deploy`、原子 rename，并记录新 config revision。不要通过 Git、CI、rsync 或命令输出传输秘密。该迁移器是 test-only，不能用于生产 env。

## 5. 标准流程

并发任务的 test-train 入口为 `scripts/test_train_release.py`，A-D 功能工作区不得直接运行发布器。详细槽位与 forward-fix SOP 见 `docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`。

包装器默认顺序部署 control-plane 与 test-execution。若用户明确把测试 Worker 留到匹配 GPU/ComfyUI 类型的后续窗口，集成 AI 可在 candidate deploy 上追加 `--skip-test-execution`；这只允许先完成并记录 control-plane，不能把未部署 Worker 写入 acceptance，也不能用于正式 `verify-test` 或生产晋级的 Worker 证据。

`plan` 可从 GHCR 拉 release bundle，需要预先 `docker login ghcr.io` 和 `oras`。`preflight`、`deploy` 不拉取任何材料，必须先把 `release.json` 与 Web tar 放入本地 bundle cache，或显式传本地 `--manifest`/`--web-artifact`，以保证门禁失败前没有 pull、worktree 或远端写入。

正式环境的生成维护模式按每次发布单独决定，默认开启。只有用户对当前 SHA 的本次发布明确要求“不进入维护”时，才可请求无维护发布；该请求不持久化，也不适用于 migration、首次/legacy 切换、队列 drain、未知影响或 planner 要求的其它强制 maintenance。正式 `plan`/`preflight` 必须同时报告用户请求/default、计算出的 maintenance level 和最终实际模式。若当前 CLI/事务实现不能表达或证明所选模式，必须在 mutation 前停止并修复发布契约，不能手工操作维护 marker、回退到 legacy 脚本或静默采用另一模式。

```bash
scripts/release.py plan --env test --track control-plane --sha <40-char-sha>
scripts/release.py preflight --env test --track control-plane --sha <40-char-sha>
scripts/release.py deploy --env test --track control-plane --sha <40-char-sha> --execute

scripts/release.py plan --env test --track test-execution --sha <40-char-sha>
scripts/release.py preflight --env test --track test-execution --sha <40-char-sha>
scripts/release.py deploy --env test --track test-execution --sha <40-char-sha> --execute

scripts/release.py verify-test \
  --sha <40-char-sha> \
  --manifest release.json \
  --evidence test-acceptance.json \
  --execute

# 仅在用户明确批准提前晋级、且全部 smoke 已完成时使用
scripts/release.py verify-test \
  --sha <40-char-sha> \
  --manifest release.json \
  --evidence test-acceptance.json \
  --confirm-short-observation \
  --execute

scripts/release.py plan --env prod --sha <40-char-sha>
scripts/release.py preflight --env prod --sha <40-char-sha>
scripts/release.py deploy --env prod --sha <40-char-sha> --execute --confirm-prod

# 仅限用户明确授权的管理后台免测试快速更新
scripts/release.py plan --env prod --sha <40-char-sha> --dashboard-fast-track
scripts/release.py preflight --env prod --sha <40-char-sha> --dashboard-fast-track
scripts/release.py deploy --env prod --sha <40-char-sha> \
  --dashboard-fast-track --execute --confirm-prod

# 仅限已测控制面后的 private worker 镜像闭包修复
scripts/release.py plan --env prod --track control-plane --sha <40-char-sha> \
  --control-plane-repair-fast-track
scripts/release.py preflight --env prod --track control-plane --sha <40-char-sha> \
  --control-plane-repair-fast-track
scripts/release.py deploy --env prod --track control-plane --sha <40-char-sha> \
  --control-plane-repair-fast-track --execute --confirm-prod

# 默认正式控制面晋级入口
scripts/release.py plan --env prod --track control-plane --sha <40-char-sha> --modules central-api
scripts/release.py deploy --env prod --track control-plane --sha <40-char-sha> --modules central-api --execute --confirm-prod
```

`--services` 只扩大自动集合。`src/**`/`shared/**` 会覆盖所有 Python 消费者；Worker 变化为 drain；migration 是 maintenance 且执行需 `--confirm-db-upgrade`；未知路径整栈维护；`remote_workers/**`、GPU profile/model manifest 触发 `gpu-runtime-release-required` blocker。用户选择不开维护不能缩小这些机器计算出的等级或依赖闭包；默认开启也必须由发布事务真实建立维护，不能只记录文字意图。

生产发布器会读取云测试 `current.json`，要求状态为 `verified` 且 SHA、自有/第三方 digest 完全相同。验收模板见 `deploy/test-acceptance.example.json`；默认观察窗口不足 24 小时或任何 smoke 为 false 都不能标记 verified。用户明确确认测试服务无问题并授权提前晋级时，短观察 evidence 必须同时包含 `short_observation_override=true`、非空 `override_reason`、`approved_by` 和真实起止时间，并在 CLI 显式传 `--confirm-short-observation`。该例外不允许时间倒置/未来完成时间，也不放宽任何 smoke、SHA/digest、Web checksum 或测试运行态检查；verified current/history 会记录实际观察秒数、例外原因与批准者，禁止伪造 24 小时时间或直接编辑状态文件。

管理后台是单管理员使用的独立控制面，用户明确授权时可选 `--dashboard-fast-track` 跳过云测试部署和 verified 晋级。该选择不跳过 Git/CI/manifest/env/read-only preflight，也不允许 mutable tag、云端 build、rsync 或维护模式；路径分类器只允许 Dashboard runtime、BF16 Dashboard catalog 和配套 release/docs/tests 元数据，自动选择 Dashboard 后端/前端，拒绝 `--services`、migration、共享 Python runtime、其它 GPU ops、Compose 与未知路径。发布事务只 rolling recreate 选中的 Dashboard 服务，状态写入 `promotion_mode=dashboard-fast-track`，并逐一核对非目标容器启动时间不变。显式快速回滚也必须带同一选项，且目标差异仍须满足相同 allowlist。

`--control-plane-repair-fast-track` 不是通用免测入口，只用于 verified main-channel 控制面之后修复生产启用、测试禁用的 `private-bot-worker` 镜像闭包。发布器以测试状态 SHA 为基线重新计算路径差异；只接受 `Dockerfile.control-plane`、v2 artifact catalog 与配套 release/docs/tests/skills 元数据。对其它 digest 变化模块，catalog inputs 必须无变化且对应 Docker target 文本逐字等价；private worker 必须包含 `qqcc_bot/` 与 `qqcc_private_bot/`，并对目标 digest 执行 `--network none` 导入烟测。业务代码、migration、Compose、GPU/ops、未知路径以及显式 `--modules` / `--services` / `--from-sha` 全部拒绝。通过后状态记录 tested/target SHA、等价 artifact 与实际 smoke artifact；main/CI/env/preflight/生产确认/回滚事务仍保持原门禁。

release workflow 生成 manifest 后会运行一次不接触运行态秘密的自检 plan，并显式使用 `--skip-env-checks`。该参数只允许 `plan`，输出 `config_validation=skipped`，用于 CI 校验 SHA/manifest/影响规则；`deploy`/`rollback` 一律拒绝它。操作者的测试/生产 plan 默认仍读取并校验真实 env，不能用 CI 例外替代部署前配置门禁。

本地主服务器的默认受限配置为 `~/.config/allbot/<env>.env`（`600`），release checkout 默认 `~/APP/All_bot-release`，Pages token 默认 `~/.config/allbot/cloudflare-pages.token`；云控制面仍使用 `/home/deploy/APP/All_bot-release` 与 `/etc/allbot/<env>.env`。云测试 Worker compose 的 `ALLBOT_ENV_FILE` 绑定本地主机测试配置实参，不能误用 env 文件内面向云主机的 `/etc/allbot/test.env` 路径。正式 GPU Worker 由各 GPU host 独立发布，不进入 `release.py --env prod`。

## 6. Web、Worker 与回滚

- 测试与正式 Web 都先校验同一 tar SHA256，再从精确 SHA checkout 读取 `frontend/runtime-config.yml` 的公开环境段，生成 `allbot-runtime-config.js` 和独立 revision，最后调用同一 Wrangler Pages 发布器。测试目标为 `allbot-web-cf-test/test`，正式目标为 `allbot-web-prod/main`。release checkout 可以没有 `frontend/node_modules`；发布器交叉校验 `package.json`、lockfile 根依赖和 lockfile 已解析项中的精确 Wrangler 版本，并用 `npx --yes --package=wrangler@<exact>` 执行，版本漂移或 lockfile 不一致一律阻断。
- Pages Token 默认读取 `~/.config/allbot/cloudflare-pages.token`，必须是 `600` 且具备目标项目 Pages Read/Write；DNS/Tunnel 权限不能替代 Pages 权限。仓库 CI 不保存 Cloudflare 管理凭据。
- Pages preflight 要求目标项目 production branch 与发布 branch 一致、`production_deployments_enabled=false`、`preview_deployment_setting=none`，并存在 active canonical custom domain；不满足只阻断，不自动修 Cloudflare。Wrangler 返回后必须由 Pages API 找到 `environment=production`、branch/SHA 正确、stage success 的 deployment ID，确认 `canonical_deployment.id` 已切换，再从正式 custom domain 以 cache-busting 请求校验 JavaScript 内的 `release_sha` 与 `runtime_config_revision`。
- 状态 schema v2 记录事务 ID、阶段健康、Pages deployment ID/environment/canonical 验证与 runtime config revision，并在事务提交时原子移动到对应 track 的 `current/history`，同时继续兼容读取 v1 的 `git_sha`。`--skip-web` 只用于故障恢复并写 `health.web=skipped`，不能通过测试验收或生产晋级。
- CI 继续生成同 SHA 的 Worker digest；源码、workflow、relay、`src` 全在镜像内。`release.py --env test` 部署并验收测试 Worker；生产 GPU Worker 由 GPU host 专用 operator 独立拉取/切换，`release.py --env prod` 拒绝显式 `--services worker`，不检查 heartbeat/relay，也不停止、重建或恢复 Worker。RunPod/LAN AIO 继续走各自 operator。
- schema v2 中测试 Worker Agent/Relay 使用不同 digest，并作为同一 test-execution 选择集部署；正式控制面 Compose 不要求二者。RunPod/LAN profile 镜像内置 `/opt/allbot/runtime/remote_workers`、baked entrypoint 和 agent/workflow revision labels，不再 clone `deploy` 分支；模型仍由带 key/size/SHA256 的 manifest 固定。
- 云测试维护发布按“云控制面 → 测试 Worker → Pages → 暂存状态 → 原子提交 current/history 并解除维护”执行。正式发布按本次已确认的维护模式执行“云控制面 → Pages → 状态提交”：默认维护模式在 mutation 前建立生成维护并在成功提交后解除；经用户明确选择且 planner 允许的无维护模式全程不写维护 marker。首次正式切换仍强制同时写 `/var/lib/allbot/prod/runtime/GENERATION_MAINTENANCE` 与 legacy `/home/deploy/APP/All_bot/runtime/cloud-prod/GENERATION_MAINTENANCE`，不能关闭，也不操作任何 GPU Worker 容器。
- 无秘密事务 journal 在每阶段通过远端临时文件原子 rename。失败只逆序补偿本事务实际尝试过的阶段，并只验证这些可能被改变的阶段；例如 cloud 阶段失败时，不得因本来 stopped 的测试 Worker 没有 heartbeat 而误报恢复失败。云测试最大补偿顺序为 Pages → Worker → 云控制面，正式为 Pages → 云控制面。验证失败时记录 `rollback_failed` 并保持维护。
- 回滚命令读取旧 release manifest/Web tar，不重建。部署状态 history 长期保留；运行主机不得全局 `docker system prune`。数据库 migration 只向前兼容，应用回滚不自动 Alembic downgrade。

```bash
scripts/release.py rollback --env test --to <old-sha> --manifest <old-release.json> --web-artifact <old-web.tgz> --execute
scripts/release.py rollback --env prod --to <old-sha> --manifest <old-release.json> --web-artifact <old-web.tgz> --execute --confirm-prod

# 只允许把未完成事务逆向恢复到旧完整栈，不允许续跑失败阶段
scripts/release.py recover --env prod --transaction <failed-target-sha> --execute --confirm-prod

# v2 各 track 独立回滚
scripts/release.py rollback --env test --track control-plane --to <old-sha> --manifest <old-release-index.json> --execute
scripts/release.py rollback --env test --track test-execution --to <old-sha> --manifest <old-release-index.json> --execute
```

## 7. 首次切换

`scripts/bootstrap_release_host.sh` 默认 dry-run，并要求显式角色：云控制面使用 `--role cloud-control`，固定 `/home/deploy/...` 且由 `deploy` 账号执行；云测试 Worker host 使用 `--role local-worker-host`，固定当前用户的 `~/APP/...` 与 `~/.config/allbot/...` 边界。正式 GPU host 的独立发布准备遵循对应 GPU/LAN/RunPod operator，不由 prod release bootstrap 代办。`--execute` 只在已有只读 deploy key、Docker Compose v2、受限 GHCR read 凭据和明确授权时使用。脚本不会创建密钥或复制 env；它建立干净 release checkout、禁用 origin push，并归档 legacy compose、容器 image ID 和排除 env/日志/runtime 的混合源码。

测试控制面首次切换不是普通 rolling recreate。发布器会把 Postgres/Redis 与应用服务一起纳入初始依赖闭包，测试 overlay 通过显式 external volume 名复用 `deploy_cloud-postgres-test-data` 和 `deploy_cloud-redis-test-data`，并保留 `postgres-test`/`redis-test` 网络别名及旧 `CLOUD_TEST_*` 到运行时变量的映射。流程必须先拉取并校验全部 digest，再从 legacy Central 排空队列、记录实际运行的 legacy 容器、停止这些容器并启动新项目；如果新项目健康或非目标启动时间门禁失败，EXIT trap 会移除新目标容器并重启记录中的旧容器。成功后旧容器保持 stopped，作为一次性 legacy 回滚入口，不得删除旧数据卷。

归档 `origin/main`/`origin/deploy` tag、stabilization PR、GHCR 权限、主机 bootstrap、env 原子迁移、测试回滚演练、Pages 自动构建关闭和首次生产切换均是外部 mutation，必须分别确认。测试 Pages 已于 2026-07-14 使用独立最小 Pages token 关闭 production/preview 自动部署；正式 Pages 仍未修改。本机 DNS/Tunnel Account Token 对 Pages API 返回 403，不能冒充 Pages 发布凭据。
