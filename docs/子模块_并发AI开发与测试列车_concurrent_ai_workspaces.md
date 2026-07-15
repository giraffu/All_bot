# 子模块：并发 AI 开发工作区与测试列车

## 1. 目标与边界

AllBot 使用四个固定 Git worktree 并行开发，只保留一套共享云测试站。A-D 功能 AI 不持有发布职责；根工作区的集成 AI 把任务逐个合入 `codex/test-train`，使用 schema v2 增量 bundle 串行切换测试站。生产发布仍只接受 `main` bundle。

目录和职责固定如下：

| 目录 | 用途 |
| :--- | :--- |
| `/home/hfy/APP/All_bot` | 集成控制、train 合入、candidate 部署和最终 main 发布 |
| `/home/hfy/APP/All_bot-workspaces/A` | 并行功能槽位 A |
| `/home/hfy/APP/All_bot-workspaces/B` | 并行功能槽位 B |
| `/home/hfy/APP/All_bot-workspaces/C` | 并行功能槽位 C |
| `/home/hfy/APP/All_bot-workspaces/D` | 并行功能槽位 D |

Git worktree 只隔离工作目录和 index；它们仍共享对象库与 refs。Python `.venv`、前端 `node_modules`、临时目录必须留在各自槽位，env、发布凭据、runtime 和数据库副本不得复制进去。

## 2. 槽位生命周期

```bash
python scripts/manage_ai_workspaces.py init
python scripts/manage_ai_workspaces.py status
python scripts/manage_ai_workspaces.py claim --task billing-ledger
python scripts/manage_ai_workspaces.py assign --slot A --task billing-ledger
python scripts/manage_ai_workspaces.py park --slot A
python scripts/manage_ai_workspaces.py refresh --slot A
```

- `init` 幂等创建 A-D；空闲槽位 detached 在最新 `origin/codex/test-train`。
- `claim` 是新 AI 窗口的默认入口：它用 `~/.local/state/allbot/ai-workspaces.lock` 原子选择第一个空闲槽位，自动刷新过期的 clean detached 槽位，创建任务分支并返回路径。并发窗口不会获得同一槽位。
- `assign` 创建 `codex/<slot>-<task>`，在 dirty、Git 操作未结束、槽位未 park 或 base 过期时拒绝。
- `park` 要求工作区 clean 且 HEAD 已由同名远端分支包含；只 detach，不删除分支。
- `refresh` 只更新已经 park 的 detached 槽位。
- 清理旧元数据先运行 `git worktree prune --dry-run`，只对明确 prunable 的失效登记执行 prune；不得删除仍存在的旧 worktree 或用户分支。

功能 AI 的 PR base 固定为 `codex/test-train`。提交前更新 train、解决冲突并重新跑 CI。PR 描述至少包含 slot、base/head SHA、影响 track/module、测试结果、migration、风险和代表性测试步骤。

功能 AI 交付后保持槽位在任务分支上，不自动 `park`。只有集成 AI 在 PR 合入且确定不需要 forward-fix 后释放槽位。面向用户的最简使用方式见 `docs/并发AI自动接单使用指南_auto_workspace_claim.md`。

## 3. Candidate bundle 契约

`main` bundle 继续发布到 `ghcr.io/giraffu/allbot-release-v2:<sha>`。train bundle 发布到 `ghcr.io/giraffu/allbot-release-v2-test-candidate:<sha>`，index 显式记录：

```json
{
  "release_channel": "test-candidate",
  "source_ref": "refs/heads/codex/test-train"
}
```

旧 v2 index 缺少这两个字段时只兼容解释为 `main`。candidate 必须同时满足完整 SHA、远端 train ancestry、可信成功 CI 和 digest-pinned artifact；只能部署 `env=test`，不能执行 `verify-test`、prod、Dashboard fast-track 或晋级。

Candidate CI 沿 train first-parent 复用最近候选 bundle；首次没有候选时复用 main v2 bundle。main CI 永远不从 candidate 仓库复用，确保正式候选重新从 main 历史构建。v2 发布只响应受保护 main/train 的 `push` CI 成功事件；PR CI 只做门禁，不发布 bundle，避免 main→train 血缘回灌 PR 重复写入同一不可变 tag。

## 4. 唯一测试站操作

只有集成 AI 执行：

```bash
python scripts/test_train_release.py plan --sha <train-sha>
python scripts/test_train_release.py deploy \
  --sha <train-sha> --pr <number> --slot A --execute
```

包装器在本地主服务器使用 `~/.local/state/allbot/test-train.lock` 排他锁，先计划三个 track，再按 `control-plane`、`test-execution` 顺序部署受影响模块。`gpu-execution` 只报告计划；真实 GPU profile 仍走对应 canary/operator。当基线还没有任何可用 GPU artifact 时，`plan` 以 `availability: unavailable` 显式报告该 track，不影响纯控制面/测试执行面候选；该状态不会被解释为可执行 GPU mutation。

若后一个 track 部署失败，包装器按相反顺序回滚本轮已成功 track；单 track 内部继续使用 `release.py` 事务补偿。若部署成功但业务 smoke 失败：

1. 执行 `block` 并暂停其它无关 PR 合入。
2. 保留失败 candidate 供诊断；需要恢复可用性时由集成 AI 显式回滚最后 accepted candidate。
3. 原槽位从失败 train 创建 `codex/<slot>-<task>-fix-N`，提交新 PR 到 train。
4. 新 SHA CI 成功后重新 plan/deploy；不自动 revert、force-push 或改写 train 历史。

Migration 只允许向前兼容。失败后不得自动 Alembic downgrade；通过 forward-fix 或显式恢复发布前测试库备份收口，期间 train 保持 blocked。

## 5. 验收与最终晋级

Candidate evidence 使用 `deploy/test-train-acceptance.example.json`，只记录本轮 PR/slot、受影响模块、smoke 和真实时间，不要求每个子任务观察 24 小时，也不能生成正式 verified 状态。

全部任务 accepted 后：

1. 创建 `codex/test-train` 到 `main` 的唯一集成 PR。
2. 等待 main CI 生成新的 main v2 bundle。
3. 把最终 main SHA 重新部署云测试，完成组合回归、回滚演练和人工验收。
4. 默认观察 24 小时；用户明确授权时才使用现有短观察 evidence/CLI 双重确认。
5. 执行 `verify-test`，再由用户明确确认正式发布同 SHA/digest。

main 合并会产生一个新的 merge commit。重新开放槽位前，集成 AI 必须再通过 PR 把该 main 血缘同步回 `codex/test-train`，确保下一次 train→main PR 满足 strict up-to-date 保护；不得为此直接 push 或 force-push train。

## 6. GitHub 保护规则

`main` 与 `codex/test-train` 都禁止 direct push、force-push 和删除，要求 PR、现有 CI checks 全绿且 head 最新。当前单人维护形态不要求 review approval；集成 AI 只能通过 PR merge 推进 train/main。
