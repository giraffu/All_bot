# AllBot 本地资源管理平台

## 1. 定位

`lan_resource_manager/` 是仅绑定本地主服务器 LAN 地址的 FastAPI + Vue 3
控制面。它有两个独立界面：

- LAN AIO：读取 catalog、XDG ledger 与 live snapshot，写操作只调用既有单槽
  operator。
- 模块构建部署：扫描 A–H 和 handoff 队列，选择性集成/对齐，并调用独立模块
  发布 CLI。

平台是受限 adapter，不实现第二套 workspace coordinator、release engine 或
GPU fleet。人工选择决定合入和发布目标；系统记录执行结果。

## 2. 当前 API

只读：

- `GET /api/v1/fleet`
- `GET /api/v1/deployments/catalog`
- `GET /api/v1/workspaces/scan`
- `GET /api/v1/modules/{environment}/{module}/status`
- `GET /api/v1/operations/{id}` 与 `/events`

写操作：

- `POST /api/v1/fleet/refresh`
- `POST /api/v1/physical-slots/{node}/{gpu}/switches`
- `POST /api/v1/workspaces/integrate`
- `POST /api/v1/workspaces/align`
- `POST /api/v1/modules/build`
- `POST /api/v1/modules/deploy`

已删除的 API 包括 release candidate/build-status、deployment plan/token、
maintenance、failed-batch retry、全量 test deploy、GPU manifest preparation、
test config sync 和 rollback-material repair。

## 3. 槽位扫描、选择性集成与对齐

`workspaces/scan` 合并：

- `manage_ai_workspaces.py status` 的 A–H clean/branch/head/base；
- XDG integration queue 的
  `pending/integrating/needs-rebase/completed`；
- 当前远端 main SHA。

用户可多选槽位：

- 合入要求每个所选槽位存在当前 pending handoff。runner 将这些 exact head 作为
  重复 `--head` 传给
  `auto_integrate_handoffs.py integrate-all --execute`。协调器仍持有唯一写锁，
  冲突单独进入 needs-rebase。
- 对齐将重复 `--slot` 传给
  `manage_ai_workspaces.py align-merged`。只有 clean 且已经被 main 包含的任务分支
  或 detached 槽位会被刷新；其它槽位原样保留。

选择器没有“直接合并槽位分支”的旁路。未 push/handoff 的开发内容不能从 UI 写入
main。

## 4. 模块构建与部署

模块事实源为 `deploy/module-catalog.json`。runner 从可写的真实 main 挂载执行
`scripts/release.py`：

```text
build --module <selected>... --sha <current-main-sha>
deploy --env <test|prod> --module <one> --artifact <exact-digest>
status --env <test|prod> --module <one>
```

构建允许多选，只递归各模块必要 base，返回所选模块的精确 digest。部署按模块逐个
执行，不形成全局 bundle：

- test 每次选择 1–2 个 catalog 支持 test 的模块；
- prod 可在后台多选，确认短语后每个调用都附加 `--confirm-prod`；
- GPU 必须单独选择并指定 `operator + exact slot`；
- 单个模块失败时停止后续模块，已完成模块和失败结果保存在 operation 中；
- 发布器负责目标健康检查与该模块回滚，migration 保留现场。

平台不查询 CI、Git diff、test evidence、bundle、其它模块或 GPU baseline。

## 5. 安全边界

- Uvicorn 仅绑定配置的 LAN IP；中间件继续校验 CIDR、Host、Origin、JSON、CSRF
  与 mutation rate。
- Web 和 runner 都是非 root、只读 rootfs、drop capabilities、
  `no-new-privileges`。
- Web 只接 Unix socket，不挂主仓库写路径、A–H、Docker/Git/云凭据。
- runner 只接受固定 JSON action；写挂载限真实 main、A–H 与 XDG queue/state。
- runner 不挂 Docker Socket。本机构建使用专用 SSH Docker endpoint 与专用 key；
  GHCR、云 SSH 和 Pages token 均按需只读挂载。
- 页面启动和扫描只读，不自动合入、对齐、构建或部署。
- prod、GPU、数据库、Cloudflare mutation 仍需操作者显式选择和确认。

## 6. 运行与恢复

operation 持久化到平台 data volume。容器重启后未完成 mutation 标为
`interrupted`，不会自动续跑。真实状态分别以 Git/main/queue、模块 release state、
远端 live target 和 LAN operator ledger 为准。

最小验证：

```bash
.venv/bin/python -m pytest -q lan_resource_manager/tests
.venv/bin/python -m pytest -q tests/ops/test_manage_ai_workspaces.py \
  tests/ops/test_auto_integrate_handoffs.py tests/ops/test_release_cli.py
cd lan_resource_manager/frontend && npm test && npm run build
docker compose --env-file lan_resource_manager/.env.example \
  -f lan_resource_manager/compose.yml config
python3 scripts/doc_quality_checker.py
```
