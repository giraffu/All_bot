# LAN AIO 本地资源管理平台

## 1. 定位

`lan_resource_manager/` 是只发布到本地主服务器 LAN 地址的 FastAPI + Vue 3
独立子项目。它把 Git catalog、XDG ledger 和低频 live status 汇总为物理 GPU
视图，并把明确确认的稳定候选切换翻译为既有单卡 operator 命令。

它不替代 `scripts/lan_aio_fleet_prod_ops.py`，也不恢复云 Dashboard 已移除的 slot
管理 API。catalog、ledger、live 与 helper history 继续是唯一事实源。

## 2. 状态与接口

- `GET /api/v1/fleet`：快速合并 catalog、ledger 和最近一次持久化 live snapshot。
- `POST /api/v1/fleet/refresh`：后台执行全量 `status --include-disabled`；同一时间只
  存在一个 operation。
- `POST /api/v1/physical-slots/{node_id}/{gpu_index}/switches`：接收目标 slot、
  页面看到的 current 和手工输入的目标 profile。
- `GET /api/v1/operations/{id}` 与 `/events`：读取结构化阶段或通过 SSE 跟踪。

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
