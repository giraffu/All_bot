# Git + 不可变镜像发布

## 1. 状态与边界

截至 2026-07-14，仓库侧发布契约已经建立，测试控制面与本地 Worker 已进入不可变发布链路。测试/正式 Web 统一使用 Wrangler Pages 发布；本轮只授权测试 Pages mutation，生产部署与正式 Pages mutation仍未获授权。

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
| 状态 | `/var/lib/allbot/deployments/<env>/current.json` 与 `history/` |
| 私密配置 | `/etc/allbot/test.env`、`/etc/allbot/prod.env`，`600 deploy:deploy` |

## 3. 构建契约

受保护 `main` 的 CI 构建 `allbot-app`、`allbot-central-api`、Dashboard backend/frontend、Worker 和环境无关的 Web tar。Web 使用锁定 Node/npm/Wrangler 版本运行 `build:release`，不把 test/prod URL 烘焙成不同产物。所有自有镜像以完整 SHA 为 tag并写 OCI revision/source；release bundle 也以完整 SHA 发布。workflow 在推送前检查同 SHA tag 不存在，避免正常流水线覆盖。

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

从 GHCR 自动拉 release bundle 需要预先 `docker login ghcr.io` 和 `oras`；也可以显式传本地 `--manifest`/`--web-artifact`。

```bash
scripts/release.py plan --env test --sha <40-char-sha>
scripts/release.py deploy --env test --sha <40-char-sha> --execute

scripts/release.py verify-test \
  --sha <40-char-sha> \
  --manifest release.json \
  --evidence test-acceptance.json \
  --execute

scripts/release.py plan --env prod --sha <40-char-sha>
scripts/release.py deploy --env prod --sha <40-char-sha> --execute --confirm-prod
```

`--services` 只扩大自动集合。`src/**`/`shared/**` 会覆盖所有 Python 消费者；Worker 变化为 drain；migration 是 maintenance 且执行需 `--confirm-db-upgrade`；未知路径整栈维护；`remote_workers/**`、GPU profile/model manifest 触发 `gpu-runtime-release-required` blocker。

生产发布器会读取云测试 `current.json`，要求状态为 `verified` 且 SHA、自有/第三方 digest 完全相同。验收模板见 `deploy/test-acceptance.example.json`，观察窗口不足 24 小时或任何 smoke 为 false 都不能标记 verified。

release workflow 生成 manifest 后会运行一次不接触运行态秘密的自检 plan，并显式使用 `--skip-env-checks`。该参数只允许 `plan`，输出 `config_validation=skipped`，用于 CI 校验 SHA/manifest/影响规则；`deploy`/`rollback` 一律拒绝它。操作者的测试/生产 plan 默认仍读取并校验真实 env，不能用 CI 例外替代部署前配置门禁。

当本地主服务器兼任测试 Worker host 时，测试配置的本地受限副本固定为 `/home/hfy/.config/allbot/test.env`（`600 hfy:hfy`），内容与云测试 `/etc/allbot/test.env` 保持同一 config revision。调用 plan/deploy 时显式传 `--env-file /home/hfy/.config/allbot/test.env`；Worker compose 的 `ALLBOT_ENV_FILE` 由发布器绑定到该实参，不能误用 env 文件内面向云主机的 `/etc/allbot/test.env` 路径。该副本只用于测试 Worker和本机发布前校验，不得包含生产 env。

## 6. Web、Worker 与回滚

- 测试与正式 Web 都先校验同一 tar SHA256，再从精确 SHA checkout 读取 `frontend/runtime-config.yml` 的公开环境段，生成 `allbot-runtime-config.js` 和独立 revision，最后调用同一 Wrangler Pages 发布器。测试目标为 `allbot-web-cf-test/test`，正式目标为 `allbot-web-prod/main`。
- Pages Token 默认读取 `/home/deploy/.config/allbot/cloudflare-pages.token`，必须是 `600` 且具备目标项目 Pages Write；DNS/Tunnel 权限不能替代 Pages 权限。仓库 CI 不保存 Cloudflare 管理凭据。正式项目的 Git 自动生产构建必须在首次正式切换前人工关闭。
- 状态清单同时记录 Web artifact SHA256、Pages project/branch、deployment URL 与 runtime config revision。`--skip-web` 只用于故障恢复并写 `health.web=skipped`，不能通过测试验收或生产晋级。
- 普通 Worker 使用 release 中同一 Worker digest；源码、workflow、relay、`src` 全在镜像内。发布器只处理本地常规 Worker；RunPod/LAN AIO 仍走专用 operator。
- 测试环境维护发布如果同时包含本地 Worker，云控制面的 `GENERATION_MAINTENANCE` 会一直保持到 Worker digest/OCI revision 校验、旧同 Agent ID 容器停止、新 Worker health 通过；任一步失败都保留维护标志并停止写入部署成功状态。首次切换只停止 allowlist 对应的 legacy worker 与 relay，避免旧/新 Agent 并存。
- 回滚命令读取旧 release manifest/Web tar，不重建。部署状态 history 长期保留；运行主机不得全局 `docker system prune`。数据库 migration 只向前兼容，应用回滚不自动 Alembic downgrade。

```bash
scripts/release.py rollback --env test --to <old-sha> --manifest <old-release.json> --web-artifact <old-web.tgz> --execute
scripts/release.py rollback --env prod --to <old-sha> --manifest <old-release.json> --web-artifact <old-web.tgz> --execute --confirm-prod
```

## 7. 首次切换

`scripts/bootstrap_release_host.sh` 默认 dry-run。`--execute` 必须由 `deploy` 账号运行，并只在已有只读 deploy key、Docker Compose v2、受限 GHCR read 凭据和明确授权时使用；发布 CLI 也以该账号读取 `600 deploy:deploy` env。脚本不会创建密钥或复制 env。它建立干净 release checkout、禁用 origin push，并归档 legacy compose、容器 image ID 和排除 env/日志/runtime 的混合源码。

测试控制面首次切换不是普通 rolling recreate。发布器会把 Postgres/Redis 与应用服务一起纳入初始依赖闭包，测试 overlay 通过显式 external volume 名复用 `deploy_cloud-postgres-test-data` 和 `deploy_cloud-redis-test-data`，并保留 `postgres-test`/`redis-test` 网络别名及旧 `CLOUD_TEST_*` 到运行时变量的映射。流程必须先拉取并校验全部 digest，再从 legacy Central 排空队列、记录实际运行的 legacy 容器、停止这些容器并启动新项目；如果新项目健康或非目标启动时间门禁失败，EXIT trap 会移除新目标容器并重启记录中的旧容器。成功后旧容器保持 stopped，作为一次性 legacy 回滚入口，不得删除旧数据卷。

归档 `origin/main`/`origin/deploy` tag、stabilization PR、GHCR 权限、主机 bootstrap、env 原子迁移、测试回滚演练、Pages 自动构建关闭和首次生产切换均是外部 mutation，必须分别确认。测试 Pages 已于 2026-07-14 使用独立最小 Pages token 关闭 production/preview 自动部署；正式 Pages 仍未修改。本机 DNS/Tunnel Account Token 对 Pages API 返回 403，不能冒充 Pages 发布凭据。
