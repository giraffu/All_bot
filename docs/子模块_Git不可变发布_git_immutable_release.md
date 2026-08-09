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
GPU profile 若需在中国区域拉取 PyPI 大依赖，应在 Dockerfile 内显式固定项目已验证的公共镜像站；不依赖操作者现场 `PIP_INDEX_URL`，也不得把带认证的 index URL 写入 build arg 或镜像历史。
RunPod 消费的 GPU module 必须在 catalog 声明 `runpod_single_manifest=true`；
发布器据此显式构建 `linux/amd64` 并关闭 BuildKit provenance，使运行 digest
直接指向单一 Docker image manifest，而不是带 attestation 的 OCI index。
LAN-only GPU module 不受此标记影响。

### 本地代理预检

Buildx 的构建步骤运行在容器网络中，因此宿主 shell 中可用的
`http://127.0.0.1:<port>` 对 Buildx 不可达。发布时必须在真正 build 前完成预检，
不能先启动构建再用超时判断网络：

1. 只核对 proxy 变量是否存在以及 URL 的 host/port，不输出凭据或完整 URL。
2. 若 host 是 loopback，用 `ss -ltn` 确认代理端口监听 `0.0.0.0`、`*` 或 Docker
   网桥可达地址；若只监听回环则停止。
3. 使用 `docker network inspect bridge` 动态读取 gateway，把原 URL 的 scheme/port
   临时映射到该 gateway，并仅对当前 `release.py build` 进程覆盖大小写
   `HTTP_PROXY`/`HTTPS_PROXY`。保留原有 `NO_PROXY`，不修改用户全局 shell、env
   文件、Compose 或 Git。
4. 构建完成后临时环境随进程退出，不把真实代理端点写入发布状态或日志。

例如本机代理已确认监听非回环端口时，可使用任务局部变量：

```bash
release_proxy_port=7890
release_docker_gateway="$(docker network inspect bridge \
  --format '{{(index .IPAM.Config 0).Gateway}}')"
release_proxy_url="http://${release_docker_gateway}:${release_proxy_port}"
HTTP_PROXY="$release_proxy_url" HTTPS_PROXY="$release_proxy_url" \
http_proxy="$release_proxy_url" https_proxy="$release_proxy_url" \
python scripts/release.py build --module <module> --sha <40位main-sha>
```

这里的端口只是调用时参数，不是稳定配置；应从当前 loopback proxy URL 解析，不应
复制到 Skill、catalog 或 Compose 作为固定运行态。

### 增量构建与“热更新”边界

- 同一 build-only 输入身份已经存在于 registry 时，发布器直接复用，不执行 build。
- 业务代码变化会产生新的完整 SHA tag 和 digest，但 BuildKit 应复用本地 layer；传入
  `--registry-cache-prefix` 时还可跨 builder/Runner 复用 registry cache。改变代理地址
  本身不会把代理值写入镜像历史，也不应作为业务层内容身份。
- `COPY src` 等宽目录层只要目录内任一文件变化就会重建该层及其后继层，这是增量镜像
  构建，不是从操作系统开始的完整冷构建。应通过缩小模块 `build_inputs`、稳定精确 base
  和合理拆分 Dockerfile 层降低耗时，而不是在共享环境绕开镜像构建。
- 本地开发可以使用独立开发 Compose 的 bind mount/hot reload；共享 test/prod 必须
  可以按 digest 审计和回滚，所以禁止容器内热改、`docker cp`、rsync 源码或 mutable
  tag。只切换到已经存在的 exact digest 时直接 deploy，不需要重新 build。

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
Compose image adapter 使用
`up --no-deps --force-recreate --wait --wait-timeout 120`，只替换目标服务并等待
其健康检查完成。即使镜像 digest 未变化，配置 revision 切换也必须创建新容器；
不得在 `up -d` 返回后立即读取健康状态，以免把正常启动窗口误判为失败并触发
无效回滚。
目标机的 `/etc/allbot/<env>.env` 必须保持 `root:root 600`。远端 operator 使用
`sudo -n docker compose` 读取该文件；deploy 用户仍只负责 runtime candidate，
禁止用 chmod/chgrp 放宽 env 权限来绕过发布失败。

Compose image adapter 默认从目标环境当前激活的
`/var/lib/allbot/module-contracts/<env>/compose-contract/current` 读取 base 与
overlay。部署前会校验两个 Compose 文件存在；未先激活契约时直接失败，不会回退
到 `/home/deploy/APP/All_bot-release/repo` 的旧副本。`--remote-root` 只作为显式
故障处置覆盖入口。更新端口、profile、volume 或服务接线时，先部署精确 digest 的
`compose-contract`，再逐个重新部署受影响业务模块，使新容器消费同一个 active
contract。

`config-contract` 对 Dashboard 与 QQCC 管理员密码哈希执行 bcrypt 结构校验，
无效值在 projection 激活前 fail closed。bcrypt 在宿主 Compose `--env-file` 中应
写成单引号包裹的标准 `$2b$...`；单引号由配置解析层移除，但会阻止 Compose 把
`$` 当变量插值。旧式 `$$2b$$...` 只适用于 YAML 字符串插值，不能进入独立
service env 文件。

`config-contract` artifact 切换与逐服务环境投影是同一个发布动作：发布器在切换
`current` 后立即以受保护的宿主 env 执行 `runtime_env_contract.py activate`。
投影校验或写入失败会令该模块发布失败，禁止只切换契约而让消费者继续读取旧投影。
激活历史按完整状态与前序 revision 唯一标识；环境从 A 切到 B 后再次回到 A 时必须
生成新的不可变转换记录，不能与首次激活 A 的历史文件冲突。

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
`allbot-runtime-config.js`，把 `index.html` 的引用改为带完整 release SHA 的
查询串，并为 runtime script 写入 `no-store` Pages 响应头，再向 Wrangler 传递
`--commit-hash`。上传后必须从
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
SHA 等于当前 `origin/main` 并拒绝 GPU kind。GPU/ComfyUI 由 operator 直接调用
`release.py build`，可通过 `--builder allbot-sgp1` 使用云端 BuildKit，但构建本身
不授权或触发 RunPod/LAN rollout。deploy workflow 绑定 `test`/`production`
GitHub Environment，校验精确 digest；
production mutation 还需 Environment 人工批准、布尔确认和
`--confirm-prod`。Environment 凭据只解码到 `/dev/shm` 并在 job 结束清理。

旧 bundle、transaction、acceptance、failed batch 和 evidence 只作历史取证，
不能作为当前命令输入或阻断模块。
