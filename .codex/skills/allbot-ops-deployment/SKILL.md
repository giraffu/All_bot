---
name: "allbot-ops-deployment"
description: "处理不可变发布、Docker Compose、迁移、云测试/正式控制面、本地灾备与 GPU/RunPod/LAN 运维；生产 mutation 必须用户明确确认。"
---

# AllBot 运维与发布

本技能只保留场景路由、授权边界和高压红线。命令参数、环境拓扑和恢复步骤
必须从对应专项文档、脚本 `--help`、版本化配置与当次运行态读取，禁止把
一次性现场状态沉淀回本 Skill。

## 1. 按需阅读

| 场景 | 必读资料 |
| --- | --- |
| 不可变 bundle、风险策略、晋级、回滚 | `docs/子模块_Git不可变发布_git_immutable_release.md` |
| 云测试控制面 | `docs/子模块_云测试控制面部署_cloud_test_control_plane.md` |
| 云正式控制面 | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md` |
| Compose 与一般恢复 | `docs/子模块_运维指南与容器管理_ops_deployment.md` |
| 并发 handoff、main 批次和共享测试站 | `allbot-concurrent-workspaces` |
| 本地正式灾备 | `docs/子模块_本地正式灾备切换_local_prod_fallback.md` |
| GPU Pool、RunPod、autoscaler | `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md`；SSH 接入与 runtime 细节见 `references/runpod-lan-runtime.md` |
| LAN AIO current/cache/takeover/recover | `allbot-lan-aio-operator` |
| 本地资源管理平台 | `allbot-lan-resource-manager` |
| R2/legacy 媒体 | `allbot-gallery-storage` |
| QQCC / 私有 Bot | `allbot-qqcc-lazy-bot` |
| Cloudflare、DNS、Tunnel、Pages、Access | `allbot-cloudflare-ops` |

线上失败、慢或卡住时叠加 `allbot-diagnosing-bugs` 和 `ops-log-monitor`；
修改脚本或门禁时叠加 `allbot-tdd`；修改知识事实时叠加
`allbot-kb-auto-updater`。

## 2. 发布模型

- `deploy/release-artifacts-v2.json` 和受保护 main 的 release index/manifest
  是不可变产物事实源。test/prod 选择模块并注入各自配置，不在目标主机
  build、rsync 源码、使用 mutable tag 或 bind mount 仓库。
- schema v2 按 `control-plane`、`test-execution`、`gpu-execution` 分轨。
  控制面变化不能隐式重建 GPU；GPU profile 或 baked worker 输入变化必须
  走同 SHA manifest、attestation 和专用 operator/canary。
- main-first 工作流由不可变 handoff 组成单个 main PR。PR 不构建发布镜像；
  main CI 成功后才产生一次 main-channel bundle。自动协调器最多部署共享
  test，不包含 prod 接口。
- `lightweight` 只覆盖 docs、Skills、tests 和仓库治理；`release-tooling`
  只覆盖明确发布工具；`operator` 只覆盖 GPU/LAN operator allowlist；其它
  或混合路径 fail closed 为 runtime。任何 scope 都不授权 direct push main。
- planner 根据 bundle exact digest、目标 track state、环境拓扑和 policy
  选择 artifact；不能仅用 `source_sha == target_sha`，也不能用 `--services`
  缩小自动影响集合。
- 发布器自动选择 `streamlined|strict`。已知、无漂移、完整验证的普通模块
  可 streamlined；migration、Compose/env、首次切换、未知影响、GPU、
  test-execution 或 strict artifact 使整个事务进入 strict。
- `plan_token` 只能复用短时间内相同 SHA/参数/输入 checksum 的只读证据；
  execute 前仍重新核对目标配置 revision 和健康。
- `scripts/release.py` 是兼容 CLI 门面；不可变命令/计划与显式 I/O seam 在
  `scripts/release_contracts.py`，schema-v2 纯请求策略在
  `scripts/release_planning.py`。新增 planning/target/recovery 测试优先注入
  `ReleaseDependencies`，不要继续把 `_run`、`_remote_shell`、`_read_json`
  等私有函数固化为测试接口。

## 3. 配置与秘密

- test/prod 配置唯一事实源分别为目标主机 `/etc/allbot/test.env` 和
  `/etc/allbot/prod.env`。发布器只生成权限 `600` 的逐服务投影；
  `release.env` 不保存秘密。
- test/prod 共用不可变镜像，环境身份、数据库、Redis、token、bucket、
  域名和开关只能来自宿主 env、overlay 或公开 runtime config。
- `config-plan/config-apply` 是配置收敛入口。模块级 apply 只能改变目标投影，
  必须证明所有非目标 active 投影的 revision 和字节不变；代码发布不能隐式
  修改宿主 env。
- 不输出 env、数据库 URL、Bot/agent/JWT/R2/RunPod token、预签 URL或完整
  `docker compose config`。Compose 校验使用安全 dummy env 与 `config -q`。
- `env_file` 只传给容器，不参与 `${...}` 插值；需要默认值时必须验证容器
  内实际配置。`.dockerignore` 要递归排除 `.env*` 和密钥文件。
- 私有 Bot 密钥、Host 与 gate 继续遵循 `allbot-qqcc-lazy-bot`；GPU token
  轮换继续走专用 operator。

## 4. 授权与生产红线

- 本地实现、测试、文档、CI 修复或读取到真实凭据都不授权共享 test/prod、
  Cloudflare、数据库、RunPod 或 GPU mutation。
- 功能链路默认先验证测试环境；正式发布、生产 Compose 重建、Alembic、
  RunPod mutation、GPU 维护和本地灾备接管必须由用户明确要求。
- 日常正式入口是 `python scripts/release.py promote` 的无 mutation 预览；
  只有同一候选、无 blocker 后增加 `--confirm-prod` 才执行。
- `--no-maintenance` 只表达用户对显式模块本次 forward rollout 的决定，
  不能豁免 migration、首次切换、共享契约、未知路径、配置漂移、健康或
  rollback 门禁。
- `--skip-gate` 仅能按 policy 跳过明确可跳门禁并记录 reason；main 血缘、
  digest/checksum、OCI revision、配置、健康、事务、回滚和非目标证明永久
  保留。execute 禁止 `--skip-ci-checks`。
- 禁止 `docker restart` 代替发布、现场 `compose build`、无目标 service 的
  Compose mutation、`--remove-orphans`、全组容器过滤删除和手工续跑失败事务。
- 生产 polling Bot 必须使用各自独立 token；启动或重建前确认没有相同
  token 的第二个 polling 实例。
- Alembic multiple heads 必须中止；迁移需备份、单 head、显式
  `alembic upgrade head` 和事务恢复，不能假设应用启动会自动迁移。
- 失败事务只允许按 journal 逆向 `recover`，不能从中间阶段继续。自动恢复
  不完整时保持维护并返回 transaction ID。

## 5. 环境与运行态边界

- 共享云测试站只有一个写入者。A–H 功能槽位不部署；自动协调器在可信 main
  bundle 后串行更新适用 test track。专项 test-execution 与 control-plane
  不能并行切换。
- 云正式控制面发布不操作生产 GPU worker。GPU/LAN/RunPod 使用各自
  exact-digest operator；单卡异常不得整机 reboot 或批量 down/up。
- RunPod create/start/stop/restart/delete/scale 必须同时满足真实运行开关、
  `--execute` 和生产确认。Dashboard autoscaler 也必须消费当前 release
  index 的完整 profile digest pin，不能使用 mutable tag。
- 测试 Web 人工验收使用 cloud-test operator 与 `runpod_test_*` agent；Dashboard
  不部署到测试站，后台手动 profile 不能作为创建测试 Pod 的旁路。测试开关必须
  通过 service env/public runtime config 契约投射，prod 值保持关闭。
- LAN AIO 的 current profile、cache marker、验证时间和实时映射属于 XDG
  ledger/运行态，不写 Git。任何 mutation 先由 live + ledger + catalog
  仲裁，精确到一个 physical slot。
- workflow 事实源是 `workers/comfy_agent/workflows`。Central 不挂载、
  COPY 或启动校验 workflow；修改 workflow/mapping/patcher 后只更新目标
  worker artifact/runtime。
- 正式对象读写使用当前 R2；运行时代码不能恢复 legacy MinIO URL。shadow
  同步、R2 backfill 和媒体恢复默认 dry-run，执行前单独确认目标和方向。
- 容量判断读取 Central `/system/workers` 和 provider 当次快照，不把某次
  worker/Pod 数量写成长期事实。
- `safe_deploy.sh` 仅用于云正式整体故障时的受控本地灾备，不是日常入口。

## 6. 日常流程

1. 明确目标环境、授权范围、候选完整 SHA、模块和是否允许维护。
2. 只读运行 `release.py promote` 或对应 `plan`，核对 artifact 旧→新 digest、
   strategy/assurance、execution profile、migration、配置和 blocker。
3. 对 standard artifact 核对同名 exact-digest test evidence；direct 仍核对
   full main validation、目标健康和回滚。不得伪造测试 state。
4. blocker 存在时停止；配置问题只有用户另行要求才进入
   `config-plan/config-apply`，migration/未知契约使用对应 strict 高级入口。
5. 获得明确生产授权后，在同一候选命令增加一次 `--confirm-prod`。
6. 验证目标健康、digest/OCI/config revision、专属 smoke、single polling
   和非目标容器身份；失败按 journal 回滚。

## 7. 最小验证与交付

- 文档治理：`python scripts/doc_quality_checker.py`。
- 脚本：`bash -n <script>`、`--help`、dry-run/preflight 和对应 focused tests。
- migration：`python -m alembic heads`，获授权的隔离环境再验证 upgrade。
- control-plane：目标容器健康、解析后的内部 API、外部健康端点、目标 digest
  和 config revision。
- Worker/GPU：ComfyUI health、Central heartbeat、workflow mapping、R2
  上传后 `/complete`；同时证明非目标 slot 未受影响。
- 交付必须区分“代码支持”“本地/测试验证”“正式已发布”。正式 mutation
  总结还要记录用户确认、维护模式、实际服务、迁移、验证和回滚入口。
- 修改发布入口、Compose、artifact、workflow、GPU profile、媒体策略或
  agent control 后，同步相关专项文档和知识库矩阵。
