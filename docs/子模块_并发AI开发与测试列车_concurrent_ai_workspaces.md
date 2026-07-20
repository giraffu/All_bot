# 子模块：并发 AI 工作区与单批次 main 集成

## 1. 目标

AllBot 保留 A-H 八个固定 Git worktree 并行开发，但退出“每个功能 PR 串行进入 test-train、逐个构建 candidate、逐个部署验收”的日常流程。新的稳定链路是：

```text
A-H 并行开发
→ 推送并冻结不可变 handoff head
→ 一次组合为 release batch
→ 一个 PR 合入 main
→ main CI 一次构建不可变 bundle
→ 用户需要时部署云测试并验收
→ 用户另行确认后发布正式模块
```

代码集成和昂贵的容器构建以“批次”为单位，不再以“槽位成员”为单位。生产仍只消费受保护 main bundle，正式 mutation 仍需用户当次明确确认。

纯非运行时仓库治理变更不进入上述发布链。`scripts/classify_ci_change.py` 以窄白名单识别 docs、Skills、tests、AGENTS/README、CI workflow/release policy 元数据、测试验收样例及精确仓库治理/门禁脚本（含 `scripts/release.py`）；全部路径均为轻量时，可用单独 PR 直接合入受保护 main 或兼容分支，不加入 release batch/test-train candidate，不跑全量模块测试，不创建 release bundle，也不部署或验收环境。任一运行时、migration、Compose、配置、白名单外发布执行器或未知路径都会恢复完整链路。

GPU controller/RunPod/LAN helper 另有 `operator` 聚焦 scope：只有全部非轻量路径均命中明确 operator allowlist 时，PR/main 才只跑 `tests/ops tests/scripts`；main 后继 modular workflow 仍创建不可变 bundle，并由 artifact planner 决定零模块（LAN 宿主 helper）或仅 `dashboard-backend`（镜像内置 controller/rollout）。它不构建 GPU artifact、不自动部署环境；`remote_workers/**`、`deploy/release-artifacts-v2.json` 中的 GPU release artifact/profile、Dockerfile/模型基础依赖或混合业务变更仍按 `runtime` 走完整链路。

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
- `handoff` 要求远端分支 head 与本地完全一致，返回 `slot/branch/head/base_sha`，随后立即释放槽位。
- 交接身份是远端 branch + 完整 head，不是槽位字母。槽位释放后即使被新任务复用，也不会进入旧批次。
- 任务分支不删除、不 force-push；修订使用新 head 并保留可追溯关系。

## 4. 批次冻结与唯一 main PR

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

main bundle 构建成功后，只有用户要求部署测试时才启动缓慢的拉取、preflight 和共享测试站切换：

```bash
python scripts/release.py plan --env test --track control-plane --sha <main-sha>
python scripts/release.py preflight --env test --track control-plane --sha <main-sha>
python scripts/release.py deploy --env test --track control-plane --sha <main-sha> --execute
```

默认只部署实际受影响的 control-plane/公共 Web。测试 Worker 专项诊断才选择 `test-execution`；GPU profile 不由共享测试站自动 mutation。

通过 smoke、组合回归、回滚演练和观察后，standard artifact 使用 `verify-test` 把精确 digest 写入 main-channel verified history。Dashboard 等 direct artifact 按策略记录 waived/attested，不能伪装为 tested。

测试失败时保留 main SHA 和事务证据，通过新 handoff/new batch 做 forward-fix；不 revert 其它并行成果、不改写 main 历史、不做自动 Alembic downgrade。

## 7. 正式发布与回滚

生产发布只接受 main 可达完整 SHA 和 main-channel bundle。`deploy-module` 可以锁定一个模块组；standard 模块在 preflight 中按 artifact 名称 + 精确 digest 查找云测试 verified 证据，direct 模块按策略显式授权。所有执行仍要求 `--execute --confirm-prod`。

非目标服务不重建。失败按事务已完成阶段逆序恢复；回滚读取历史不可变 manifest/digest，不现场 build。migration 只向前兼容，应用回滚不自动 downgrade。

## 8. GitHub 保护

`main` 禁止 direct push、force-push 和删除。业务运行时改动要求批次 PR 与完整检查；operator 改动仍经 PR/批次集成，但使用聚焦 operator gate；轻量改动可用单独 PR 和 change-scope/aggregate gate 合入。`codex/test-train` 退出日常运行时集成路径，可保留为历史兼容 ref；若仍需同步轻量治理改动，可直接合入且不得触发 candidate、容器构建或测试部署。
