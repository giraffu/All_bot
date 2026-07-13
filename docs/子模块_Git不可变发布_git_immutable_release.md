# Git + 不可变镜像发布

## 1. 状态与边界

截至 2026-07-13，仓库侧发布契约已经建立；本轮没有执行生产部署、Cloudflare Pages mutation、Git push/tag、deploy key 或 GHCR token 创建。首次云测试/生产切换必须另行授权，并先运行 bootstrap dry-run。

旧 `update_cloud_*` 脚本已经 fail closed。它们不再包含 rsync 或 build 能力。旧 compose、云端混合源码和容器 image ID 只用于首次切换归档与一次性 legacy 回滚，不是可信 release 基线。

## 2. 事实源

| 事实 | 文件/位置 |
| :--- | :--- |
| CI 构建 | `.github/workflows/control-plane-release.yml` |
| 影响分析 | `deploy/release-policy.yml` |
| 配置契约 | `deploy/env.schema.yml` |
| 公共控制面 | `deploy/docker-compose-cloud-base.yml` + test/prod overlay |
| 公共 Worker | `deploy/docker-compose-worker-base.yml` |
| 发布接口 | `scripts/release.py` |
| 主机首次准备 | `scripts/bootstrap_release_host.sh` |
| 状态 | `/var/lib/allbot/deployments/<env>/current.json` 与 `history/` |
| 私密配置 | `/etc/allbot/test.env`、`/etc/allbot/prod.env`，`600 deploy:deploy` |

## 3. 构建契约

受保护 `main` 的 CI 构建 `allbot-app`、`allbot-central-api`、Dashboard backend/frontend、Worker 和 Web tar。所有自有镜像以完整 SHA 为 tag并写 OCI revision/source；release bundle 也以完整 SHA 发布。workflow 在推送前检查同 SHA tag 不存在，避免正常流水线覆盖。

`release.json` 同时记录自有镜像 digest、imgproxy/Postgres/Redis digest、Web SHA256 和 CI run。部署器拒绝短 SHA、`latest`/普通 tag、缺少 digest、manifest SHA 不一致和未推送/不可从 `origin/main` 到达的提交。

## 4. 配置

代码发布不修改真实 env。Compose 依次读取版本化 `deploy/env.defaults`、`/etc/allbot/<env>.env` 和该 release 的非敏感 `release.env`，后者优先级最高且只包含 release SHA、config revision 与镜像 digest。

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

错误只输出变量名，不输出值。Worker 槽位由 `ALLBOT_WORKER_SERVICES=worker-01,...` allowlist 决定；发布器只重建该列表，未启用 canary 不会被顺带启动。每个选中槽位必须提供对应 `ALLBOT_WORKER_XX_*` 契约。

首次 env 迁移必须人工完成：在目标机本地备份、写临时文件、校验、`chmod 600`/`chown deploy:deploy`、原子 rename，并记录新 config revision。不要通过 Git、CI、rsync 或命令输出传输秘密。

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

## 6. Web、Worker 与回滚

- 测试 Web 校验 tar SHA256，上传到 SHA 版本目录后原子切换 `/root/dist-test` symlink，不覆盖现有目录。
- 正式 Web 用 `deploy` 账号下的独立最小权限 token（默认 `/home/deploy/.config/allbot/cloudflare-pages.token`）通过 Wrangler 上传同一 tar；仓库 CI 不保存 Cloudflare 管理凭据。首次切换前须人工关闭 Pages 自动生产构建。
- 普通 Worker 使用 release 中同一 Worker digest；源码、workflow、relay、`src` 全在镜像内。发布器只处理本地常规 Worker；RunPod/LAN AIO 仍走专用 operator。
- 回滚命令读取旧 release manifest/Web tar，不重建。部署状态 history 长期保留；运行主机不得全局 `docker system prune`。数据库 migration 只向前兼容，应用回滚不自动 Alembic downgrade。

```bash
scripts/release.py rollback --env test --to <old-sha> --manifest <old-release.json> --web-artifact <old-web.tgz> --execute
scripts/release.py rollback --env prod --to <old-sha> --manifest <old-release.json> --web-artifact <old-web.tgz> --execute --confirm-prod
```

## 7. 首次切换

`scripts/bootstrap_release_host.sh` 默认 dry-run。`--execute` 必须由 `deploy` 账号运行，并只在已有只读 deploy key、Docker Compose v2、受限 GHCR read 凭据和明确授权时使用；发布 CLI 也以该账号读取 `600 deploy:deploy` env。脚本不会创建密钥或复制 env。它建立干净 release checkout、禁用 origin push，并归档 legacy compose、容器 image ID 和排除 env/日志/runtime 的混合源码。

归档 `origin/main`/`origin/deploy` tag、stabilization PR、GHCR 权限、主机 bootstrap、env 原子迁移、测试回滚演练、Pages 自动构建关闭和首次生产切换均是外部 mutation，必须分别确认。仓库代码完成不等于这些运行态动作已经发生。
