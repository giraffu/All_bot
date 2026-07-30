# 独立模块不可变发布

## 原则

发布资格由操作者的实际测试结果决定，系统不设置发布门禁。系统只保证：

1. 从操作者指定的完整 Git SHA 构建明确模块；
2. 部署精确 digest 到明确环境和目标；
3. 检查目标模块的执行结果；
4. 失败时只恢复该目标的上一 identity（migration 除外）。

发布器不读取 CI、Git diff、main ancestry、test evidence、approval、bundle、
其它模块状态或 GPU baseline。并发写入协调、focused tests、test 人工验收都
不是发布门禁。

## 模块目录与构建

事实源为 `deploy/module-catalog.json`。每项记录 adapter、build target、必要
base、repository、部署目标、环境支持和结果检查。模块独立构建、部署，不生成
全局 release index，也不因 changed paths 扩大集合。

```bash
python scripts/release.py build \
  --module payment-api \
  --sha <40位main-sha>
```

`--module` 可重复。发布器创建临时干净 worktree，用本机 buildx/GHCR 构建并
push，仅递归必要 base。已有同 SHA 产物时复用并返回精确 digest；外部镜像只
解析 digest。完整 SHA 是构建输入标识，不是 ancestry 门禁。
`build-only` base 不再跟随应用 SHA：其 tag 为
`input-<canonical-sha256>`，身份只覆盖模块名、target、Dockerfile、catalog
声明的 `build_inputs` 和上游 base 的精确 digest。requirements、Dockerfile
或 base digest 变化才重建；最终业务镜像仍用完整 Git SHA tag，并返回
`repository@sha256:digest`。

SGP1 repository-level self-hosted Runner 只承接受保护 `main` 的手动模块构建：

```bash
python scripts/release.py build \
  --module main-bot \
  --sha <40位main-sha> \
  --builder allbot-sgp1 \
  --registry-cache-prefix ghcr.io/giraffu/allbot-build-cache \
  --build-progress plain
```

registry cache ref 是唯一允许 mutable 的构建缓存；运行 artifact 始终精确
digest。构建器在真正 build 前验证 Buildx、registry namespace 和代理。
`127.0.0.1`、`localhost`、`::1` 代理对 docker-container builder 不可达，会
立即失败；需改为容器可达网桥地址或在云 Runner 直连。构建 stderr 实时显示
阶段与耗时，stdout 继续只输出模块到 digest 的 JSON。
若操作者环境存在标准 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` 或小写同名
变量，发布器只把变量名作为 BuildKit 预定义 build arg 转发，不把代理值拼进
命令或镜像历史；未设置时不新增 build arg。

## 部署

```bash
python scripts/release.py deploy \
  --env test --module payment-api \
  --artifact ghcr.io/example/payment-api@sha256:<digest>
```

```bash
python scripts/release.py deploy \
  --env prod --module payment-api \
  --artifact ghcr.io/example/payment-api@sha256:<digest> --confirm-prod
```

一次只部署一个模块。prod 唯一资格确认是 `--confirm-prod`。test 不支持某模块
时只返回目标不可用，不产生 prod blocker。
Compose image adapter 使用 `up --no-deps --wait --wait-timeout 120`，只替换
目标服务并等待其健康检查完成；不得在 `up -d` 返回后立即读取健康状态，以免
把正常启动窗口误判为失败并触发无效回滚。

GPU 还需 `--operator runpod|lan --slot <exact-slot>`。config/compose contract
只切换目标契约，消费者由操作者随后显式部署。migration 只运行指定 artifact。
Migration 镜像闭包必须包含 `src/`、Alembic 配置和 migrations；
Alembic 只通过 `src.runtime_environment.require_env("DATABASE_URL")` 读取唯一
所需配置，不导入完整业务 `config.py`，避免被 R2、Bot 或 Web 的无关必填项
阻断。测试数据库主机位于 Compose 网络内，因此 `database-migration` 在
`test` 自动加入 `--network allbot-test_default`；正式数据库使用外部连接，
`prod` 不附加 Compose 网络。

`public-web` 的 test/prod 使用同一份环境中立 tar。Pages adapter 从 artifact
annotation 读取完整 Git SHA，在上传前按目标环境读取
`frontend/runtime-config.yml`，覆盖 tar 中的空占位
`allbot-runtime-config.js`，并向 Wrangler 传递 `--commit-hash`。上传后必须从
目标 canonical 域名回读 runtime script，确认完整 SHA、runtime revision、
API 域名和 Bot 用户名均与目标环境一致；未切换时部署失败并进入目标模块回滚。
测试与正式配置由 focused tests 固定为独立 mapping，禁止把 test API/Bot
注入正式 Pages，也禁止测试 Pages 回退到同源 `/api`。

## 状态与恢复

```bash
python scripts/release.py status --env prod --module payment-api
python scripts/release.py rollback \
  --env prod --module payment-api --confirm-prod
```

状态按环境和模块保存 current、previous、最近动作和结果。首次部署从 live
adapter 建立基线。部署失败自动尝试恢复 previous；migration 失败只报告并保留
现场，不自动 downgrade 或恢复备份。
本地 CLI 默认继续使用 XDG state；GitHub deploy workflow 显式使用 remote
state backend，把状态原子写入目标主机
`/var/lib/allbot/module-release-state/<env>/<module>/current.json`，因此 Runner
重建不会丢失 rollback identity。

`.github/workflows/module-build.yml` 与 `module-deploy.yml` 只有
`workflow_dispatch`，self-hosted job 不接收 PR/fork。build workflow 要求输入
SHA 等于当前 `origin/main` 并拒绝 GPU kind；GPU/ComfyUI 仍由本地发布路径构建。
deploy workflow 绑定 `test`/`production` GitHub Environment，校验精确 digest；
production mutation 还需 Environment 人工批准、布尔确认和
`--confirm-prod`。Environment 凭据只解码到 `/dev/shm` 并在 job 结束清理。

旧 bundle、transaction、acceptance、failed batch 和 evidence 只作历史取证，
不能作为当前命令输入或阻断模块。
