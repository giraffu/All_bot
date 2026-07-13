# 首次可信 Release 准备记录

## 1. 当前结论

仓库侧 stabilization 已按“完整 Git SHA + CI 不可变产物 + 同 digest 晋级”合入主线。`a2a44beba88055fcb72291ca39953a7b41868985` 的分片 Python、PostgreSQL、Web、Dashboard 与 release workflow 全绿，Web SHA256、五个自有镜像 digest/tag/OCI revision 已独立核验。2026-07-14 首次测试执行在新项目绑定旧 Dashboard 端口时 fail closed，暴露 legacy 控制面尚未进入首次交接闭包；该 SHA 未写部署成功状态，也未切 Web/Worker，失败尝试产生的新项目容器已清理，旧测试控制面恢复单实例运行。

进一步核对发现旧测试 Postgres/Redis 数据卷属于 `deploy_cloud-*-data`，而新项目默认会使用另一组空卷；旧服务名还承担 `postgres-test`/`redis-test` DNS，旧 env 只提供 `CLOUD_TEST_POSTGRES_*`。修正后的首次交接会显式复用旧卷和网络别名、补运行时变量映射，把 Postgres/Redis 纳入初始服务集合，并在停旧容器前完成 pull/digest 校验和 legacy Central 队列排空；失败会移除新目标容器并重启本轮记录的旧容器。执行前运行态核对还确认测试 env 未启用 QQCC/私有 QQCC Bot，因此发布器必须从实际 cloud 启动集合中过滤这两个明确禁用的可选 runtime，并在 plan 中显示 `disabled_cloud_services`，不能把整栈依赖分析误解为强制开启未配置 Bot。候选必须以这些修正合入 `main` 后的新完整 SHA/bundle 为准，`a2a44...` 和中间候选只保留为演练证据。

用户已授权仅测试环境首次切换；生产部署和正式 Pages mutation 仍未授权。2026-07-14 对 `587d6651688a1f979afa31d9ee5ae19866a61749` 的首次切换在 Dashboard Frontend 启动门禁 fail closed：镜像未创建 `/etc/nginx/templates`，入口脚本无法安装 Nginx 模板。EXIT trap 已清理新项目并恢复 legacy 控制面，未切 Web/Worker，未写成功状态。修正后的 CI 必须真实执行 dashboard/QQCC 两种 frontend 入口模式，而不只检查静态文件存在。`074109e719f00a7484414979f93d9236f703bea6` 重试进一步暴露 Dashboard Backend 镜像漏了根 `config.py`、`paid_group_guard_bot` 和 `ops` 导入闭包，健康门禁再次触发自动回滚。后续 CI 必须真实 import Dashboard 与 QQCC 两个 ASGI app；只能用修正合入后的新 SHA/digest 重试。

`92fcdd34d91d3f9c827ca9c8740fe0e030aacd13` 的云测试控制面与本地测试 Worker 已完成首次不可变切换，所有自有容器的 digest、OCI revision 和 Python 3.10.20 一致，原问题链路中的并发锁参数与 locale 文件也已在镜像内核对。测试 Web 边缘机在切换时已离线 18 小时，因此该次以 `--skip-web` 恢复控制面和 Worker，运行状态必须记录 `health.web=skipped`。在同一 bundle 完成 Web 原子切换、代表性图片/视频/Bot 任务、回滚演练和 24 小时观察前，不得写入 verified 验收或晋级生产。

03:06 和 03:15 两次 Bot 图片任务均在派发前失败，账本 Saga 均完成全额退款。根因不是 Docker DNS 随机抖动，而是 legacy `/etc/allbot/test.env` 中的 `API_BASE_TEST=central-api-test` 被 `BOT_TYPE=TEST` 优先读取，绕过了 overlay 的新 `API_BASE=central-api`。修正 release 必须同时钉死两个变量并在容器内校验解析后的 `config.API_BASE`；重新部署、成功代表任务与新 24 小时窗口完成前，`92fcdd...` 不是可晋级的可信验收版本。

`c6d473fb668210bc5b7b1fccb1adbb538208f45a` 的 CI/bundle 全绿，但首次执行时进一步暴露发布器 SSH stdin 缺口：远端队列检查使用 `docker compose exec -T`，它吞掉同一 stdin 中后续 pull/up/校验脚本并返回 0，导致 Worker/状态清单先于云容器变化。测试控制面已用同一 SHA/digest 受控恢复，实际容器、OCI revision 与解析后的 `config.API_BASE` 已对齐，Postgres/Redis 未重启；但 `c6d473...` 自带的发布器仍不允许用于生产。必须等待加入 `</dev/null`、SHA 完成标记和实际容器 digest/revision 门禁的新 main SHA/bundle，再以新发布器重跑测试并重新开始验收窗口。

## 2. 已完成的仓库门禁

- stabilization 基线 Python：`2563 passed`；后续 release CI 已改为 Python 3.10 分片门禁并成功完成。
- stabilization 基线 Ops 子集：`379 passed`；LAN AIO 专项 `46 passed`。本次 Worker 切换闭包聚焦回归：`29 passed`；本地完整 Ops 的其它失败若来自未归属的 fleet state 工作区改动，不并入本次 release commit。
- Web：`294 passed`，`npm run build` 通过。
- Dashboard：`93 passed`，类型检查与 `npm run build` 通过。
- Alembic：单 head `3e9c7a1b5d24`。
- test/prod/worker immutable Compose：使用 dummy env 执行 `config -q` 通过，未输出展开配置。
- `python scripts/doc_quality_checker.py` 通过。
- 旧 test/prod/QQCC 同步入口均以退出码 `2` fail closed。
- `git diff --check` 通过；未发现未跟踪 env、私钥、token 或 credential 文件。

验证仅证明仓库候选满足对应门禁，不替代最终合入 SHA 的 GitHub Actions、镜像 smoke、云测试真实任务、24 小时观察或生产晋级门禁。

## 3. Git 血缘整理

- stabilization 与后续 Python 3.10、依赖、分片 CI 修正已通过 PR 纳入 `main`，发布器只接受 `origin/main` 可达的最终完整 SHA。
- Python 镜像基座统一钉死为 Python 3.10.20 的 Bookworm digest；本机宿主 Python 3.13 不参与 release 运行时判定。
- `origin/deploy` 只创建首次切换前归档 tag，随后冻结，不再作为生产代码来源。
- 本地 `debug-main-bot-lag.md` 是未完成排障草稿，不进入 stabilization commit。

## 4. 送审与首次发布待办

1. 将首次 legacy 控制面/数据卷交接修正 PR 合入受保护 `main`，以合并后的完整 40 位 SHA 触发新的 release workflow；`a2a44...` 旧候选不再部署。
2. 核对新 CI 成功、OCI revision、所有镜像 digest、Web SHA256 与不可覆盖的 release bundle。
3. 用云测试当前 env 作为控制面事实源、本机旧 env 作为 Worker 参数源，经 test-only 迁移器生成 `/etc/allbot/test.env` 候选并完成 schema/cloud/worker Compose dry-run，任何输出不得含秘密值；未选 dormant 槽位只允许使用 disabled 安全默认值，allowlist 内槽位仍必须显式满足 schema。
4. 在目标机完成只读 deploy key、GHCR `read:packages` 凭据和 release host bootstrap；密钥不进入仓库、源码 checkout 或 CI。
5. 使用 test-only env 迁移器生成候选并校验 `/etc/allbot/test.env`，原子安装为 `600 deploy:deploy`；控制面先复用旧 Postgres/Redis 数据卷完成原子 legacy 交接，再切测试 Web，并在同一维护窗口停止 allowlist 对应 legacy Worker、启动同 digest 本地测试 Worker，全部健康后才解除维护。
6. 完成 health、Bot、任务提交、Redis 锁、locale、Web、Worker heartbeat、图片/视频代表任务和回滚演练，并观察至少 24 小时。
7. 写入 verified 验收记录后，才允许以同一 SHA/digest 申请生产确认。
8. 首次生产切换前归档 legacy compose、容器 image ID、混合源码与 env；生产部署和 Pages 变更仍需明确确认。
