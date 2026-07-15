---
name: allbot-concurrent-workspaces
description: "管理 AllBot 多 AI 并发开发 worktree、A-D 固定槽位、任务分支交接、受保护 test-train 合入和唯一云测试站串行发布。创建/分配/停放并发工作区、让多个 AI 同时开发、合并任务到 codex/test-train、部署或验收 test-candidate、处理 train blocked/forward-fix 时必须使用。"
---

# AllBot 并发工作区与 Test Train

## 1. 先读什么

- 操作 A-D 槽位前读 `docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`。
- 部署 test-candidate 时同时加载 `allbot-ops-deployment`，只通过 `scripts/test_train_release.py`。
- 修改管理脚本或发布门禁时同时加载 `allbot-tdd`；修改规则后加载 `allbot-kb-auto-updater`。

## 2. 固定职责

- 把 `/home/hfy/APP/All_bot` 作为集成控制工作区，不在其中执行普通功能开发。
- 只在 `/home/hfy/APP/All_bot-workspaces/A` 至 `D` 开发并行任务；每个槽位只能承载一个任务分支。
- 让功能 AI 只修改当前 worktree、运行本地测试、推送分支并向 `codex/test-train` 提交 PR。禁止功能 AI 部署共享 test、操作 prod、Cloudflare 或 GPU runtime。
- 让集成 AI 独占 test-train 合入、candidate bundle、云测试切换、accept/block 与恢复。

## 3. 稳定入口

```bash
python scripts/manage_ai_workspaces.py status
python scripts/manage_ai_workspaces.py init
python scripts/manage_ai_workspaces.py assign --slot A --task <slug>
python scripts/manage_ai_workspaces.py park --slot A
python scripts/manage_ai_workspaces.py refresh --slot A

python scripts/test_train_release.py status
python scripts/test_train_release.py plan --sha <40位SHA>
python scripts/test_train_release.py deploy --sha <40位SHA> --pr <PR> --slot A --execute
python scripts/test_train_release.py accept --sha <40位SHA> --evidence <json>
python scripts/test_train_release.py block --sha <40位SHA> --reason <原因>
```

## 4. 红线

- 不在 dirty、未完成 merge/rebase、未推送或落后 train 的槽位上重新分配任务。
- 不删除 park 后的任务分支；只 detach 到最新 `origin/codex/test-train`。
- 不把 env、SSH key、Pages/GHCR token、runtime 或数据库副本放入 A-D。
- 只允许精确 `refs/heads/codex/test-train` 的可信 CI bundle 标记为 `test-candidate`。candidate 只能部署 test，禁止 `verify-test`、prod、fast-track 或正式晋级。
- 不让独立功能分支横向覆盖测试站。任务必须先合入 train，后一个任务在前一个 accepted candidate 上继续累积。
- GPU 基线无可用 artifact 时只接受 `availability: unavailable` 的读取计划；不得把它当作 GPU 验收或自动 mutation，涉及 GPU 的任务仍必须交给对应 canary/operator。
- 部署事务失败时逆序恢复已完成 track；部署成功但业务失败时 block train、保留现场并从原槽位做 forward-fix，不自动改写 Git 历史。

## 5. 交付门禁

- PR 写明 slot、train base SHA、head SHA、v2 tracks/modules、测试、migration、风险和云测试步骤。
- 只有当前 candidate accepted 后才合入下一个无关任务。
- train 全部通过后合入 main；对新的 main SHA 重新构建、部署和完整验收。candidate evidence 不能替代正式 24 小时/短观察授权与 `verify-test`。
