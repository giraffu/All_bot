# 子模块：云正式控制面部署

本文只记录云正式环境的当前稳定拓扑、授权边界和单模块不可变发布契约。旧
rsync、目标机 build、源码 bind mount、组合批次与自由 Compose 流程已退出活跃
SOP，见[云正式旧发布流程退役说明](archive/cloud-prod-legacy-sop-retirement.md)。

## 1. 授权与事实源

正式环境、数据库、Cloudflare、RunPod 和 LAN 的 mutation 都必须由用户明确
要求。读取本地 env、SSH 配置、目标状态或日志只授权诊断，不授权发布。

| 事实 | 唯一来源 |
| --- | --- |
| 模块、adapter、prod 支持与 build inputs | `deploy/module-catalog.json` |
| Compose 拓扑 | `deploy/docker-compose-cloud-base.yml`、`deploy/docker-compose-cloud-prod.overlay.yml` |
| 服务配置契约 | `deploy/service-env-contract.yml`、`scripts/runtime_env_contract.py` |
| build/deploy/status/rollback | `scripts/release.py` |
| 当前秘密与配置 | 正式主机 `/etc/allbot/prod.env` 与 active config revision |
| 当前模块 identity | remote release state 加目标 adapter 当次只读验证 |
| 公网入口 | Cloudflare 当次只读状态与 Cloudflare 专项文档 |
| GPU current | provider/Central/XDG ledger 当次状态 |

仓库只能证明契约，不能证明线上此刻健康，因此本资料保持
`runtime-verification-required`。不得把旧容器清单、worker 数量、队列或资源
快照写成当前事实。

## 2. 当前拓扑边界

正式控制面使用 base Compose 与 prod overlay。服务、基础设施契约、Pages 与 GPU
都是 catalog 中独立模块：

- API/Bot：Central、Web、Payment、主 Bot、QQCC、private worker、付费群 Bot、
  客服 Bot。
- 管理面：Dashboard 与 QQCC Config 的前后端。
- 公网/媒体：Public Web、imgproxy、Cloudflare adapter。
- 基础设施：PostgreSQL、Redis/Valkey、config contract、compose contract、
  database migration。
- GPU：RunPod 与 LAN profile；只由明确 operator/exact slot 管理。

本文不复制完整模块清单。发布前以 catalog、`release.py --help` 和目标环境
live state 为准。单模块发布不会自动选择相邻模块、迁移数据库、切 DNS 或 rollout
GPU。

## 3. 构建

只从受保护 main 的完整 SHA 构建明确模块：

```bash
python3 scripts/release.py build \
  --module <module> --sha <40位main-sha>
```

构建在本地/受控 builder 完成并返回精确
`repository@sha256:digest`。目标主机只消费 artifact，禁止目标机 build、
源码同步、bind mount、mutable tag 或容器内改代码。

build-only base 可按内容身份复用；业务 artifact 仍绑定完整 Git SHA。GPU artifact
构建不授权 RunPod/LAN rollout。

## 4. 正式部署

只有用户明确确认本次正式 mutation 后执行：

```bash
python3 scripts/release.py deploy \
  --env prod --module <module> \
  --artifact <repository@sha256:digest> --confirm-prod
```

一次只部署一个模块。发布器不读取 CI、测试 evidence、Git diff、bundle、其它
模块或 GPU baseline。操作者负责依据实际测试结果决定模块、顺序和时机。

- Compose adapter 只替换目标 service，等待健康检查并核对 live identity。
- Pages adapter 只更新目标 project，注入 prod runtime config 后从 canonical
  域名回读 SHA、revision、API base 与 Bot 用户名。
- config/compose contract 只切换自身 active identity，消费者必须随后显式重部署。
- migration 只执行指定 artifact；失败保留现场，不自动 downgrade 或恢复备份。
- GPU 需要 `--operator runpod|lan --slot <exact-slot>`，并继续满足对应 operator
  红线。

失败只恢复目标模块 previous identity。任何回滚都不扩大成整栈或非目标模块
mutation。

## 5. 配置与 Compose 契约

- `/etc/allbot/prod.env` 保持 `root:root 600`；不得为 deploy 用户放宽权限。
- config contract 从受控 env 生成逐服务投影。secret 不能进入 Git、artifact、
  state、普通日志或聊天。
- Compose image 默认读取
  `/var/lib/allbot/module-contracts/prod/compose-contract/current`。缺失或文件
  不完整时 fail closed。
- `--remote-root` 只用于显式故障处置；恢复后回到 active contract。
- bcrypt hash、Telegram token、R2、数据库、支付和 private Bot keys 由各自
  contract 校验；不能用占位值或临时关闭 gate 绕过。

端口、profile、volume、network 或 service 接线变化时：

1. 构建并部署 exact-digest `compose-contract`。
2. 必要时部署 `config-contract`。
3. 按依赖顺序逐个重部署受影响模块。
4. 核对非目标模块 identity 与启动时间未变化。

## 6. 数据库与跨模块顺序

数据库 mutation 必须单独授权，并使用 `database-migration` 模块。执行前：

1. 备份并验证可恢复性。
2. 确认单 Alembic head、目标 migration 内容和 downgrade 风险。
3. 核对目标数据库、连接环境与 migration artifact identity。
4. 先部署向后兼容的 API，再迁移，再逐个部署消费者。

带 Worker 新协议时，推荐顺序是兼容 Central/Web → Worker → 前端；回滚反向。
支付、鉴权、账本和 private Bot 还要满足各领域 Skill 的幂等、密钥与租户边界。

## 7. 公网与 Bot 边界

- DNS、Tunnel、Access、Pages、R2 或 WAF 修改必须加载
  `allbot-cloudflare-ops` 并获得明确授权；代码发布不隐式修改 Cloudflare。
- 同一 Telegram token 只能有一个 polling 实例。private Bot 使用 webhook，
  不切成 polling。
- Public Web 的 prod runtime config 不能包含 test API/Bot，也不能回退到同源
  `/api`。
- 正式环境故障切到本地主服务器属于独立灾备操作，必须使用
  `docs/子模块_本地正式灾备切换_local_prod_fallback.md`，不能把普通模块回滚
  扩大成灾备切换。

## 8. 状态、回滚与验收

```bash
python3 scripts/release.py status --env prod --module <module>
python3 scripts/release.py rollback \
  --env prod --module <module> --confirm-prod
```

remote state 是发布器账本，不是 live 健康的替代品。部署后至少核对：

- 目标 artifact digest、OCI revision、config/compose revision。
- 目标 health、必要 API/业务 smoke 与日志中无新增异常。
- Bot single polling/webhook、Pages canonical 回读或 migration head。
- 非目标 service/container/Pages/GPU slot 未变化。
- 失败时 current/previous 与实际运行 identity 一致。

## 9. 最小验证

```bash
.venv/bin/python -m pytest -q tests/ops/test_release_cli.py \
  tests/ops/test_runtime_env_contract.py \
  tests/ops/test_immutable_compose.py
python3 scripts/doc_quality_checker.py
```

再按目标模块运行 focused tests。交付必须区分：

- 代码与本地测试支持。
- artifact 已构建。
- prod 已部署。
- 线上业务验收已完成。

未执行的层级不能写成已完成；本任务若只更新知识库，不执行任何正式 mutation。
