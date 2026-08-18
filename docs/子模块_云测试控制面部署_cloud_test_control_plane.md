# 子模块：云测试控制面部署

本文只记录云测试环境的当前稳定拓扑与单模块发布契约。旧源码同步、目标机
build、维护式整栈脚本和 legacy Compose SOP 已退役，历史原因见
[云测试旧发布流程退役说明](archive/cloud-test-legacy-sop-retirement.md)。

## 1. 事实源与边界

| 事实 | 唯一来源 |
| --- | --- |
| 可构建/部署模块、adapter、环境支持 | `deploy/module-catalog.json` |
| 云控制面 Compose 拓扑 | `deploy/docker-compose-cloud-base.yml`、`deploy/docker-compose-cloud-test.overlay.yml` |
| 服务配置契约 | `deploy/service-env-contract.yml`、`scripts/runtime_env_contract.py` |
| 构建、部署、回滚和状态 | `scripts/release.py` |
| 当前配置 | 测试主机 `/etc/allbot/test.env` 与 active config revision |
| 当前模块 identity | remote state 与目标容器/Pages 的当次只读检查 |
| GPU/LAN current | provider、Central worker 快照与 LAN XDG ledger |

代码发布不修改 `/etc/allbot/test.env`，也不自动发布其它模块、执行数据库迁移、
切换 GPU/LAN 或触发人工验收。A–H handoff 协调器只合并 main，不构建或部署。

矩阵状态保持 `runtime-verification-required`：仓库只能证明发布契约，不能证明
测试站此刻的容器、配置 revision、DNS、数据库、队列或 Worker 健康。

## 2. 当前拓扑

测试控制面由 base Compose 与 test overlay 组合。业务模块按 catalog 独立替换；
PostgreSQL、Redis、配置、Compose 契约和 migration 也都是显式模块，不能由普通
业务模块隐式创建或修复。

主要模块分为：

- 控制面：`central-api`、`web-api`、`main-bot`、`qqcc-bot`、
  `private-bot-worker`、`worker-relay`。通用 `worker-agent` 只构建不可变镜像，
  由 RunPod/LAN/专用 agent operator 消费，不伪装成云 Compose service。
- 管理面：`dashboard-backend`、`dashboard-frontend`、
  `qqcc-config-backend`、`qqcc-config-frontend`。
- 公网与媒体：`public-web`、`imgproxy`。
- 基础设施契约：`postgres`、`redis`、`config-contract`、
  `compose-contract`、`database-migration`。
- GPU profile：catalog 中声明 test 支持的 GPU 模块；实际运行仍由明确的
  RunPod/LAN operator 和 exact slot 管理，不随控制面部署联动。

模块清单会变化，不在本文复制完整 catalog。执行前以
`python3 scripts/release.py --help`、catalog 和目标模块条目为准。

## 3. 不可变发布流程

### 3.1 构建

只从受保护 main 的完整 SHA 构建明确模块：

```bash
python3 scripts/release.py build \
  --module <module> --sha <40位main-sha>
```

构建返回精确 `repository@sha256:digest`。artifact 身份不可用 mutable tag、
本地目录或目标机源码替代。需要 config/compose 契约变更时，先分别构建并部署
对应 contract，再逐个重建受影响模块。

控制面 image 默认优先使用 SGP1 专用云 BuildKit，并显式传入操作者当次验证过的
远端 builder；Pages/contract 仍由本地打包。Worker artifact 要保留在本地 registry
时，按不可变发布文档的“云构建写入本地 registry”流程使用仅绑定 loopback 的 SSH
transport，把同一 repository path 的精确 digest 从云 builder 写入本地 registry，
并在部署窗口供测试主机拉取。该 transport 不授权公网暴露 registry、云测试运行主机
源码构建或长期修改 Docker daemon。

### 3.2 部署

```bash
python3 scripts/release.py deploy \
  --env test --module <module> \
  --artifact <repository@sha256:digest>
```

一次只部署一个模块。Compose adapter 只替换目标 service，并在写状态前等待健康
检查；Pages adapter 注入 test runtime config 后从 canonical 域名回读验证。
失败只恢复目标模块的 previous identity。migration 失败保留现场，不自动
downgrade 或恢复备份。

目标主机默认读取 active
`/var/lib/allbot/module-contracts/test/compose-contract/current`；缺失或不完整
时 fail closed。只有故障处置才显式使用 `--remote-root`，恢复后应回到 active
contract。

### 3.3 状态与回滚

```bash
python3 scripts/release.py status --env test --module <module>
python3 scripts/release.py rollback --env test --module <module>
```

持久 Runner 使用 remote state；本地 CLI 默认使用 XDG state。状态文件只是发布器
账本，验收还必须核对目标 adapter 的 live identity、健康检查和必要业务行为。

## 4. 配置、数据库与服务顺序

- `config-contract` 从受控 test env 生成逐服务投影；秘密不得进入 artifact、
  Git、发布状态或普通日志。
- `compose-contract` 固定 base/overlay、端口、profile、volume 和 service
  接线。接线变化先激活 contract，再显式重部署消费者。
- 数据库 schema 只通过 `database-migration` 模块执行。先备份、确认单
  Alembic head 和目标 migration 内容；普通 Web/Central 部署不得顺带迁移。
- 带 Worker 新协议时，先部署向后兼容的 Central/Web，再部署 Worker，最后激活
  前端；回滚按相反顺序。
- Bot 模块部署前确认同一 token 没有其它 polling 实例。private Bot 继续使用
  webhook，不切成 polling。
- test env 不设置 prod 资格。人工验收结果由操作者判断，不写入发布器门禁。

## 5. GPU 与 Worker 验收

控制面部署不会推断或修改 GPU 当前态。测试生成链路验收前，当次核对：

1. Central 队列与目标 task type 的 enabled/healthy Worker。
2. Worker 的 supported task types、profile、artifact digest 与 heartbeat。
3. ComfyUI health、queue、workflow/model contract。
4. 输入上传、结果物化、R2 URL、History/Gallery 与 `/complete` 终态。

RunPod mutation 使用受控 provider；LAN mutation 必须加载
`allbot-lan-aio-operator` 并通过
`scripts/lan_aio_fleet_prod_ops.py` 操作单一 exact slot。构建 GPU artifact
不授权 rollout。

## 6. 最小验证

```bash
.venv/bin/python -m pytest -q tests/ops/test_release_cli.py \
  tests/ops/test_runtime_env_contract.py \
  tests/ops/test_immutable_compose.py
python3 scripts/doc_quality_checker.py
```

部署后的 focused smoke 按目标模块选择：

- API：目标 health、鉴权边界和一条公开 API 行为。
- Bot：容器/日志、single polling 或 webhook 隔离和一条无副作用交互。
- Pages：canonical test 域名回读的 SHA、runtime revision、API base 与 Bot 用户名。
- migration：目标 head、关键 schema 与非目标数据不变。
- GPU：disabled canary、任务成功/失败收口和非目标 slot 不变。

交付时明确区分“代码与本地测试通过”“test artifact 已部署”“测试环境人工验收
通过”。未执行的运行态检查不能写成已验证。
