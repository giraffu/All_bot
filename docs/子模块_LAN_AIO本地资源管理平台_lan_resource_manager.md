# AllBot 本地资源管理平台

## 1. 定位

`lan_resource_manager/` 是只发布到本地主服务器 LAN 地址的 FastAPI + Vue 3
独立子项目。页面分为 LAN AIO 与模块构建部署两个 Tab；所有写操作都经精确确认和
既有 operator/release facade，不承载第二套运维实现。

它不替代 `scripts/lan_aio_fleet_prod_ops.py`，也不恢复云 Dashboard 已移除的 slot
管理 API。catalog、ledger、live 与 helper history 继续是唯一事实源。

## 2. 状态与接口

- `GET /api/v1/fleet`：快速合并 catalog、ledger 和最近一次持久化 live snapshot。
- `POST /api/v1/fleet/refresh`：后台执行全量 `status --include-disabled`；同一时间只
  存在一个 operation。
- `POST /api/v1/physical-slots/{node_id}/{gpu_index}/switches`：接收目标 slot、
  页面看到的 current 和手工输入的目标 profile。
- `GET /api/v1/operations/{id}` 与 `/events`：读取结构化阶段或通过 SSE 跟踪。
- `GET /api/v1/deployments/catalog`、`/releases/candidate` 与
  `/environments/{env}/status`：读取模块、可信候选、当前部署和维护状态。
- `POST /api/v1/releases/builds`：只触发当前 main 的可信上游构建链，同 SHA 幂等。
- `POST /api/v1/deployment-plans` 与 `/{plan_id}/execute`：服务端保管短效 token 的
  两阶段单模块部署。
- `POST /api/v1/environments/{env}/maintenance`：以预期状态、原因和完整确认文字
  更新平台 owner 的生成维护。

全量 status 可能持续数十秒，因此首屏不等待 live SSH；超过默认 180 秒的 snapshot
标记为 stale 并禁止切换。

## 3. 切换事务

网页只开放 `catalog_ready + enabled + retargetable` 候选。服务收到请求后重新跑目标
卡 status，要求 state `passed`、没有 drift/未完成 helper operation，并再次读取
ledger 核对 current：

- current 存在：执行单卡 `takeover`，固定 `auto_rollback`。
- current 为空且存在 `intentionally_empty`：对用户选择的 slot 执行精确 `recover`。
- current 与页面预期不同、空槽未收口或目标已经 current：fail closed。

helper 的 XDG `mutation.lock` 与平台自己的全局 operation gate 共同保证串行。平台不
提供 state-reconcile、candidate-plan、独立 warm-cache、release-rollout、自由
Docker/SSH 或任务强杀入口。

## 4. 本地部署与安全

Compose 使用 host network 避免 bridge NAT 隐藏真实来源，但 Uvicorn 默认只绑定
`192.168.1.115:8096`，不会监听 `0.0.0.0` 或 Tailscale；应用再次校验
`192.168.1.0/24`、Host、Origin、JSON Content-Type 和 CSRF token。平台没有登录，
所以同网段访问者都视为 operator；若安全边界变化，应先新增应用鉴权再扩大网络范围。

容器以 UID/GID 1000、只读根文件系统、drop all capabilities 和
`no-new-privileges` 运行。AllBot 源码只读、XDG state 读写、正式 env 与 LAN GPU
专用 SSH key 只读挂载；禁止 Docker Socket和云控制面 SSH key。

常驻部署必须由用户明确要求；Compose 镜像内置平台代码，`ALLBOT_ROOT` 只读挂载目标
AllBot 主目录作为 operator 事实源，不挂载 A–H feature worktree。启动与页面刷新均
为只读，不自动修改 GPU。本平台首次授权部署已验证 health passed 且只监听
`192.168.1.115:8096`。

## 5. 验收与恢复

后端测试通过 fake `OperatorPort` 覆盖状态合并、安全门禁、drift、竞争、takeover /
recover 分流和持久化 operation；前端用 Vitest、`vue-tsc`、Vite build 与
Playwright 桌面/移动截图验收。

若容器在 switch 中退出，平台本地 operation 在下次启动标记为 `interrupted`；真实
收口状态以 XDG history/current 和 helper status 为准。不得由平台猜测续跑或自动
recover。

## 6. 可信构建、部署与维护

- runner 查询远端 main、提交变更 scope、上游 CI 与
  `allbot-release-v2:<full-sha>`。缺可信 CI 时 dispatch
  `control-plane-release.yml`；已有同 SHA 成功 CI 时只用固定
  `source_sha/release_channel=main/validation_mode=full/upstream_run_id` 补跑
  modular workflow，禁止 build-only。lightweight 或 release-tooling main 不需要
  新 bundle，部署候选沿 main 历史选择最近不可变 bundle。
- `GET /api/v1/deployments/catalog` 从 release policy 返回完整模块组，并按环境拓扑
  过滤；每次计划只接受一个模块。服务端保存 `release.py plan` 的短效 token，浏览器
  只看到安全预览。
- 执行阶段重新核对候选 SHA，固定调用 `release.py deploy --track control-plane
  --modules <one> --plan-token ... --execute`；正式环境附加 `--confirm-prod`。
- `scripts/release_maintenance.py` 只管理 test/prod 固定 state root 的
  `GENERATION_MAINTENANCE`。平台 owner metadata 与活动 transaction 共同决定是否
  可解除，不写 `/app/MAINTENANCE`。
- CI 构建使用独立并发通道；LAN 切换、部署和维护共享 runtime mutation gate。
  runner/Web 重启不会重放 mutation，GitHub build 仍可从外部 run 状态继续观察。

Web 与 runner 使用同一只读镜像但不同容器。Web 只挂 LAN operator 所需材料和 Unix
socket；runner 才挂云 SSH、GitHub/GHCR/Pages 凭据。两者均非 root、只读根文件系统、
drop all capabilities、`no-new-privileges` 且无 Docker Socket。
