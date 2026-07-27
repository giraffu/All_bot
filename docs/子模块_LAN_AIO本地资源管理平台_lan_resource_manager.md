# AllBot 本地资源管理平台

## 1. 定位

`lan_resource_manager/` 是只发布到本地主服务器 LAN 地址的 FastAPI + Vue 3
独立子项目。页面分为 LAN AIO 与模块构建部署两个 Tab；后者覆盖 A–H handoff
集成、安全槽位对齐、可信构建与模块化部署。所有写操作都经精确确认和既有
operator/integration/release facade，不承载第二套运维实现。

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
- `GET /api/v1/integration/status`：合并远端 main、A–H clean/base/branch 和
  pending/running/failed queue 的脱敏状态。
- `POST /api/v1/integration/run`：确认 `INTEGRATE <full-sha>` 后固定执行测试专用
  `integrate-all`；逐批冻结、PR、CI、bundle 和 test deploy，不接受 prod 参数。
- `POST /api/v1/workspaces/align`：确认 `ALIGN <full-sha>` 后只对 clean 且已被
  main 包含的槽执行 detached refresh。
- `POST /api/v1/environments/test/deploy-all`：确认 `TEST ALL <full-sha>` 后逐个
  部署 release policy 中 test 可用的完整独立模块。

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
- main 身份固定由已认证 `gh api` 读取；Actions run 使用兼容旧版 GitHub CLI 的
  run list 后在 runner 内按 `headSha` 精确过滤，不使用匿名 `git ls-remote` 或
  `gh --commit`。catalog、candidate 与环境 SSH 状态在前端独立收敛；单个环境 SSH
  不可达时显示脱敏 blocker，但不清空已成功读取的 main、bundle 和模块目录。
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
镜像从 digest-pinned Node 22 stage 只复制 `node` 与 npm/npx；发布测试 Pages 时仍由
`release.py` 读取前端 lockfile 的精确 Wrangler 版本。这样隔离 runner 不依赖宿主
Node，也不会在运行时 apt 安装工具。`NPM_CONFIG_CACHE` 固定落到 runner 专用的
`/home/app/.cache/allbot/npm`，`XDG_CONFIG_HOME` 固定到同一 volume 的 `config`
子目录；只读 home 不承担 npm cache 或 Wrangler log/config 写入。Pages 命令失败时
只返回最后一条经统一脱敏和长度限制的诊断，不得回显 token 或完整环境。
Pages 阶段在上传前先同时核对 canonical deployment 的 commit SHA、成功状态以及
公开 runtime config revision；三者匹配就复用该不可变部署并记录
`reused_existing`，使“Pages 已成功但本地进程随后中断”的重试不会重复 mutation。
同 SHA 存在多次历史上传时，以项目当前 canonical deployment ID 选定记录，不能取
部署列表中第一条同 SHA 记录后反向猜测 canonical。
runner 的固定 SSH config 对同一 allowlisted 云主机使用 20 秒 connect timeout、
最多 4 次 connection attempts，以及 20 秒 server-alive/3 次失联上限。该重试只吸收
瞬时网络抖动，不改变目标 host、用户、密钥、known_hosts 或环境授权；全部尝试失败仍
让事务 fail closed 并进入原发布器补偿。

integration 复用 release runner 的动作白名单。runner 对 Git common dir、A–H
worktree root 与 XDG integration queue 只有精确 bind mount；Web 不挂载这些写路径。
队列自动收敛只允许两类可证明安全的历史项：head 已在当前 main 的 pending，或
`deploying-test` 失败且其 main SHA 已被更新 main 超越的批次。其它 failed batch
继续阻断。槽位 dirty、未初始化或未合入均只读展示。

失败原因修复后可通过 `POST /api/v1/integration/retry` 和精确短语
`RETRY <batch>` 将指定批次重新排队并继续集成。runner 的集成临时 worktree
固定落在 release cache volume，并使用固定 coordinator 提交身份，不依赖小容量的
容器 `/tmp` 或宿主 Git 全局配置。同一隔离 volume 覆盖 runner 的
`~/.cache/allbot`，供 bundle cache、临时 worktree 与短效 release plan 使用；Web
不挂载该 volume。

测试全模块入口按 catalog 顺序为每个模块重新生成短效 token 并立即执行；失败时停止，
operation result 记录已完成模块，重跑依靠 exact state 幂等继续。该接口固定为 test，
不存在 prod 对称入口。右上角 `/help.html` 是可点击操作手册，随前端 artifact 发布。

`POST /api/v1/releases/gpu-builds` 只接受当前 main 与精确短语
`GPU BUILD <main-sha>`。它通过 `scripts/prepare_gpu_release_v2.py` 并行补齐 8 个实际
GPU 镜像，复用可信基线的模型 checksum/rollback digest，形成同 SHA 的 9-profile
attested manifest，并重放模块 bundle。已经存在的不可变镜像只有在能找到同 SHA 成功
workflow 时才复用。该入口不创建 RunPod/LAN Pod、不部署 prod，也不进入维护。

`POST /api/v1/environments/test/config-sync` 只接受 `TEST CONFIG <main-sha>`，固定从
当前 main checkout 执行 test `config-plan` 后再执行原子 `config-apply --execute`。
该动作只用于收敛发布前已检测到的 test 配置投影漂移，不接受环境参数、不附加
`--confirm-prod`，也不调用手动维护入口。

`POST /api/v1/environments/test/rollback-repair` 只接受
`REPAIR TEST ROLLBACK <current-sha>`。Web 提交前重新读取测试状态并要求 current SHA
完全相同；runner 固定调用 test/control-plane/dashboard 的
`recover --repair-rollback-materials --execute` 兼容入口。该 repair 模式可按精确
SHA 拉取旧不可变 bundle，再由发布器核对完整 bundle、
current artifact 和运行容器 digest，只原子物化 checkout 与非敏感 `release.env` 并
执行 `compose config -q`；不拉镜像、不替换或重启容器、不写维护标记及 deployment
state。runner 在调用前通过固定测试 SSH 再读取一次当前 control-plane state，校验
schema/track/SHA 后以 0600 临时 `--state-file` 绑定本次恢复，完成后删除；不会为
Dashboard 缺失项遍历历史文件。平台不存在正式环境对称入口。
