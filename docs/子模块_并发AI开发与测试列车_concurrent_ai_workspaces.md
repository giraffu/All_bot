# 子模块：并发 AI 工作区与单批次 main 集成

## 1. 目标

AllBot 保留 A-H 八个固定 Git worktree 并行开发，但退出“每个功能 PR 串行进入 test-train、逐个构建 candidate、逐个部署验收”的日常流程。新的稳定链路是：

```text
A-H 并行开发
→ 推送并冻结不可变 handoff head
→ 本机单写者自动冻结等待项为 release batch
→ 一个 PR 合入 main
→ main CI 一次构建不可变 bundle
→ 自动串行以 streamlined/strict 分类部署云测试
→ 普通 smoke 自动写 exact-digest verified evidence
→ 用户另行确认后以同一分类发布正式模块
```

代码集成和昂贵的容器构建以“批次”为单位，不再以“槽位成员”为单位。生产仍只消费受保护 main bundle，正式 mutation 仍需用户当次明确确认。

`streamlined` 只适用于已知 schema-v2 main control-plane 影响且目标服务配置投影无漂移；测试和正式均只替换 planner 选中的服务，失败使用目标主机已有旧 ref 回切。任一 migration、Compose/env、首次切换、未知影响或专用执行轨会使整个混合发布进入 `strict`，继续使用完整门禁。该分类不改变自动 handoff 队列、A-H release batch、main CI 构建或生产确认边界，也不授权槽位直接部署共享环境。

纯非运行时与发布工具变更不进入上述运行时发布链。classifier 将 docs/Skills/tests/治理元数据归为 `lightweight`，将 `release.py`、配置契约、CI run 校验、classifier 和自动集成协调器归为 `release-tooling`；后者只运行发布专项回归。两者均可用单独受保护 main PR，不创建 release bundle，也不部署环境。任一运行时、migration、Compose、运行配置、白名单外执行器或未知路径都会恢复完整链路。

GPU controller/RunPod/LAN helper 另有 `operator` 聚焦 scope：只有全部非轻量路径均命中明确 operator allowlist 时，PR/main 才只跑 `tests/ops tests/scripts`；main 后继 modular workflow 仍创建不可变 bundle，并由 artifact planner 决定零模块（LAN 宿主 helper）或仅 `dashboard-backend`（镜像内置 controller/rollout）。它不构建 GPU artifact、不自动部署环境；`workers/runpod_runtime/**`、`workers/runpod_profiles/**`、`deploy/release-artifacts-v2.json` 中的 GPU release artifact/profile、Dockerfile/模型基础依赖或混合业务变更仍按 `runtime` 走完整链路。

## 2. 固定目录和职责

| 目录 | 职责 |
| :--- | :--- |
| `/home/hfy/APP/All_bot` | 只读盘点、批次集成、main PR、测试/正式发布控制 |
| `/home/hfy/APP/All_bot-workspaces/A-H` | 独立功能开发、focused tests、提交、推送和 handoff |

Worktree 隔离源码、index 与可写依赖，不是凭据沙箱。A-H 可以读取真实配置和远端状态做诊断，但不得泄露秘密或把读取能力解释为共享环境 mutation 授权。

## 3. 槽位生命周期

```bash
python scripts/manage_ai_workspaces.py init
python scripts/manage_ai_workspaces.py claim --task billing-ledger
python scripts/manage_ai_workspaces.py handoff --slot A
python scripts/manage_ai_workspaces.py status
```

- 空闲槽位 detached 在最新 `origin/main`。
- `claim` 原子选择第一个 clean、detached、main 基线最新的槽位，创建 `codex/<slot>-<task>`。
- 功能 AI 完成后先测试、提交并推送，再执行 `handoff`。
- `handoff` 要求远端分支 head 与本地完全一致，先将 `slot/branch/head/base_sha` 幂等写入本机 XDG 自动集成队列，成功后立即释放槽位。明确不自动集成时才使用 `--no-enqueue`。
- 交接身份是远端 branch + 完整 head，不是槽位字母。槽位释放后即使被新任务复用，也不会进入旧批次。
- 任务分支不删除、不 force-push；修订使用新 head 并保留可追溯关系。

## 4. 批次冻结与唯一 main PR

日常入口是用户级 `allbot-ai-integration-queue.timer`。每分钟唤醒的 `scripts/auto_integrate_handoffs.py run-once --execute` 先抢非阻塞单写者锁：已有集成/测试发布在运行时本轮不抢占；拿到锁后把当时全部 pending handoff 冻结为一个不可变批次，后到任务留给下一批。协调器依次组合精确 head、创建 main PR、等待 PR checks、合并、等待 main CI 和 modular bundle，最后只执行固定的 `release.py ... --env test`。阶段写入 `running/*.json`，进程中断后从 PR、main CI 或测试部署阶段续跑。

任一 head 漂移、组合冲突、CI、bundle 或测试部署失败都会把批次移入 `failed/` 并阻断后续批次；排除原因后使用 `retry-failed --batch <id>` 将同一批次移回 running，并从已持久化的 PR、main CI 或测试部署阶段续跑。若失败阶段是 `waiting-main-ci` 且已有 pending forward-fix，精确重试会把这些 handoff 按原顺序冻结进同一批次、清除旧 PR/main/scope 元数据并以新分支重走受保护 PR，避免“旧 main 必然构建失败、修复又被 failed 阻塞”的死锁；`deploying-test` 失败不得吸收后到 handoff。`lightweight` 与 `release-tooling` 批次均在 main CI 后完成，不等待不存在的 modular bundle，也不更新环境；从历史 `deploying-test` 阶段恢复时仍应用同一 scope 规则，其中纯 lightweight 批次不写 release-batch JSON。协调器没有 `--env`、prod 或 promote 参数，不能修改正式环境。

首次启用必须等实现进入 main 后从主目录 dry-run 并安装用户 timer：

```bash
scripts/install_ai_integration_queue_timer.sh
scripts/install_ai_integration_queue_timer.sh --execute
python scripts/auto_integrate_handoffs.py status
```

本地主资源管理平台的“模块构建部署”是上述稳定入口的受限 UI：读取 A–H 与 queue
状态，确认 `INTEGRATE <main-sha>` 后执行 `integrate-all --execute`，再以
`ALIGN <main-sha>` 对齐 clean 且已被 main 包含的槽。UI 不实现另一套 merge 逻辑，
也没有 prod 参数。`integrate-all` 会把已包含于 main 的 stale pending 记为
`already-merged`；只有旧 `deploying-test` 失败已被更新 main 超越时才记为
`superseded`，其它失败继续阻断。

未启用 timer、自动协调器故障或需要人工选择成员时，仍可使用下列手工入口。

集成 AI 先选择本轮要交付的 handoff，再执行只读冻结：

```bash
python scripts/manage_ai_workspaces.py batch-plan \
  --batch 2026-07-release \
  --output release-batches/2026-07-release.json \
  --member A:codex/a-billing-ledger@<sha> \
  --member D:codex/d-gallery-search@<sha>
```

计划器会核对：

- 每个 head 是 40 位完整 SHA；
- `origin/<task-branch>` 仍精确指向 handoff head；
- 交接 base 可从当前 main 追溯；
- 同一 handoff 没有重复进入批次。

输出文件以独占创建方式保存成员、冻结 main base、固定目标 `codex/release-batch-<slug>` 和 `pr_base=main`；已存在路径直接拒绝覆盖。集成 AI 将该 JSON 纳入批次 PR，并从冻结 main base 一次性组合全部精确 head，解决组合冲突、运行批次测试，只创建一个面向 main 的 PR。

批次冻结后的新任务或新 handoff 属于下一批。当前批次不得切分支、清理、刷新或重新停放这些非成员工作区。

## 5. CI 与构建触发

`.github/workflows/control-plane-release.yml` 在批次 PR 上运行代码门禁，在 main push 上再次建立可信 main CI 结果。`.github/workflows/modular-release-v2.yml` 默认消费成功的 main push workflow run；若 GitHub 未投递该 push workflow，可对当前 `main` 精确 head 手动重跑同一上游 workflow，作为受控恢复入口。模块化 workflow 会通过 `scripts/validate_upstream_ci_run.py` 重新读取 run metadata 和 jobs，只有 repository、workflow name/path、`head_branch=main`、`head_sha=origin/main`、completed/success 以及 Web、Dashboard、PostgreSQL 和全部 Python shard 都成功时，才把上游 `workflow_dispatch` 视为 `full`：

- 不监听 `codex/test-train`；
- 不为槽位分支或批次 PR 构建发布容器；
- 每个合入后的 main SHA 最多创建一次不可覆盖 main bundle；
- 只重建影响分析选中的 artifact，未变化 artifact 从最近 main bundle 复用；
- main 涉及 GPU artifact 重建时必须有同 SHA 完整 attestation，否则 bundle 创建失败。

两个 workflow 都先运行 `change-scope`。`lightweight` 跳过全量测试，聚合 `ci-gate` 只核对分类成功，main 后继 modular workflow 也跳过 release job。`operator` 跳过九个 Python 分片、PostgreSQL、Web 和 Dashboard 前端 job，只要求单个 operator test job 成功；main 后继 release job 保留，以便构建真实命中的最小 artifact。`runtime` 运行完整检查。空变更集、未知路径和 operator/runtime 混合均按 `runtime` 处理。

`modular-release-v2.yml` 自身的手动 dispatch 没有测试恢复权限，始终只允许 `validation_mode=build-only`。陈旧 main SHA、缺失或失败的任一预期 test job、错误 workflow/event/branch/repository 都在构建前 fail closed。

旧 `test-candidate`、freeze/approve 和 promotion workflow 不再是新发布入口。历史 bundle 和状态继续由兼容代码读取，但不能用于创建新批次。

## 6. 云测试

自动队列中的 runtime/operator main bundle 构建成功后，协调器串行启动 plan 和共享测试站切换：

```bash
python scripts/release.py plan --env test --track control-plane --sha <main-sha>
# 从上条 JSON 读取 plan_token；自动协调器会完成这一步
python scripts/release.py deploy --env test --track control-plane --sha <main-sha> --plan-token <token> --execute
```

默认只部署实际受影响的 control-plane/公共 Web。测试 Worker 专项诊断才选择 `test-execution`；GPU profile 不由共享测试站自动 mutation。

普通 streamlined 目标 smoke 成功后自动把 exact digest 写入 main-channel verified history；专项 strict/人工验收才补用 `verify-test`。plan token 在 10 分钟内复用候选、CI 和 evidence，但 deploy 仍重新检查目标配置 revision；相同 exact digest/OCI/config/健康直接 no-op。Dashboard 等 direct artifact 按策略记录 waived/attested，不能伪装为 tested。

测试失败时保留 main SHA 和事务证据，通过新 handoff/new batch 做 forward-fix；不 revert 其它并行成果、不改写 main 历史、不做自动 Alembic downgrade。

## 7. 正式发布与回滚

生产发布只接受 main 可达完整 SHA 和 main-channel bundle。`deploy-module` 可以锁定一个模块组；standard 模块在 preflight 中按 artifact 名称 + 精确 digest 查找云测试 verified 证据，direct 模块按策略显式授权。所有执行仍要求 `--execute --confirm-prod`。

非目标服务不重建。失败按事务已完成阶段逆序恢复；回滚读取历史不可变 manifest/digest，不现场 build。migration 只向前兼容，应用回滚不自动 downgrade。

## 8. GitHub 保护

`main` 禁止 direct push、force-push 和删除。业务运行时改动要求批次 PR 与完整检查；operator 改动仍经 PR/批次集成，但使用聚焦 operator gate；轻量改动可用单独 PR 和 change-scope/aggregate gate 合入。`codex/test-train` 退出日常运行时集成路径，可保留为历史兼容 ref；若仍需同步轻量治理改动，可直接合入且不得触发 candidate、容器构建或测试部署。
