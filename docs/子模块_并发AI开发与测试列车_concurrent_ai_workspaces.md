# 子模块：并发 AI 开发工作区与测试列车

## 1. 目标与边界

AllBot 使用八个固定 Git worktree 并行开发，只保留一套共享云测试站。A-H 功能 AI 不持有发布职责；根工作区的集成 AI 把任务逐个合入 `codex/test-train`，使用 schema v2 增量 bundle 串行切换测试站。生产发布仍只接受 `main` bundle。

目录和职责固定如下：

| 目录 | 用途 |
| :--- | :--- |
| `/home/hfy/APP/All_bot` | 集成控制、train 合入、candidate 部署和最终 main 发布 |
| `/home/hfy/APP/All_bot-workspaces/A` | 并行功能槽位 A |
| `/home/hfy/APP/All_bot-workspaces/B` | 并行功能槽位 B |
| `/home/hfy/APP/All_bot-workspaces/C` | 并行功能槽位 C |
| `/home/hfy/APP/All_bot-workspaces/D` | 并行功能槽位 D |
| `/home/hfy/APP/All_bot-workspaces/E` | 并行功能槽位 E |
| `/home/hfy/APP/All_bot-workspaces/F` | 并行功能槽位 F |
| `/home/hfy/APP/All_bot-workspaces/G` | 并行功能槽位 G |
| `/home/hfy/APP/All_bot-workspaces/H` | 并行功能槽位 H |

Git worktree 只隔离工作目录和 index；它们仍共享对象库与 refs。Python `.venv`、前端 `node_modules`、临时目录和其它可写缓存应留在各自槽位，避免并发写入污染。

### 1.1 能力边界不是安全沙箱

A-H 使用同一受信任 OS 用户，目标是隔离代码/index/依赖写入，不是限制 AI 了解真实系统。功能 AI 可以读取 worktree 或主机已有的真实 env、配置、SSH/API 凭据、日志、数据库连接信息和远端运行态，并可使用这些凭据完成只读诊断、本地测试和部署计划。已有配置或凭据出现在槽位中不构成分配失败，也不要求自动删除。

高访问能力与操作授权必须分开：秘密原文不得进入对话、测试输出、日志、diff、commit 或 PR；功能任务未明确要求时不得改写、轮换或另存凭据。凭据可见也不授权功能 AI 部署共享 test、修改 prod、Cloudflare、RunPod/GPU、执行数据库 migration 或改变发布状态，这些 mutation 仍由集成 AI 和对应运维 Skill 控制。

依赖目录属于并发污染面，不属于凭据访问面。新任务应优先使用槽位自己的 `.venv`、`node_modules` 与缓存；若只读审计发现运行中的任务沿用历史共享目录或符号链接，记录风险即可，不得为了修复隔离而中断任务或自动删除依赖。待任务交付、PR 稳定或槽位维护时再收口。

## 2. 槽位生命周期

```bash
python scripts/manage_ai_workspaces.py init
python scripts/manage_ai_workspaces.py status
python scripts/manage_ai_workspaces.py claim --task billing-ledger
python scripts/manage_ai_workspaces.py assign --slot A --task billing-ledger
python scripts/manage_ai_workspaces.py park --slot A
python scripts/manage_ai_workspaces.py refresh --slot A
```

- `init` 幂等创建 A-H；空闲槽位 detached 在最新 `origin/codex/test-train`。
- `claim` 是新 AI 窗口的默认入口：它用 `~/.local/state/allbot/ai-workspaces.lock` 原子选择第一个空闲槽位，自动刷新过期的 clean detached 槽位，创建任务分支并返回路径。并发窗口不会获得同一槽位。
- `assign` 创建 `codex/<slot>-<task>`，在 dirty、Git 操作未结束、槽位未 park 或 base 过期时拒绝。
- `park` 要求工作区 clean 且 HEAD 已由同名远端分支包含；只 detach，不删除分支。
- `refresh` 只更新已经 park 的 detached 槽位。
- 清理旧元数据先运行 `git worktree prune --dry-run`，只对明确 prunable 的失效登记执行 prune；不得删除仍存在的旧 worktree 或用户分支。

功能 AI 的 PR base 固定为 `codex/test-train`。提交前更新 train、解决冲突并重新跑 CI。PR 描述至少包含 slot、base/head SHA、影响 track/module、测试结果、migration、风险和代表性测试步骤。

功能 AI 交付后保持槽位在任务分支上，不自动 `park`。集成 AI 只有在该 PR 已合入 train、精确 train SHA 的 candidate 已完成对应运行时部署并执行 `accept` 后，才确定本轮不需要 forward-fix，并必须立即 `park` PR 记录的槽位，再推进下一个无关 PR。机器计划明确为 non-runtime 的 control-plane 不伪造容器部署：包装器把精确 SHA 记录为 `ready-for-acceptance` / `deployment_mode=non-runtime`，以 bundle、CI 与 plan 证据 `accept` 后按同一规则释放。槽位释放不等待其它任务完成、train 合入 main 或正式发布；candidate 只完成部署或 non-runtime 计划但尚未 `accept`、被 `block` 或仍需 forward-fix 时继续保留原槽位。面向用户的最简使用方式见 `docs/并发AI自动接单使用指南_auto_workspace_claim.md`。

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

schema v2 的远端事务和发布合约都按 track 隔离：journal/staged state 使用 `transactions/<track>/<sha>`，云 Compose 的非敏感合约使用 `/var/lib/allbot/releases/<track>/<sha>/release.env`，Worker host 使用 `release-env/<track>/<sha>/release.env`。Worker preflight 从同一 track-scoped 路径读取上一版本回滚材料；若该轨没有任何 cloud service，则跳过 cloud preflight，不要求不会生成的云端合约。同一 candidate 先后部署 control-plane 与 test-execution 时，后一轨不得覆盖前一轨的镜像变量或回滚输入。

测试 Worker 的 GPU/ComfyUI 类型与目标业务窗口不匹配时，用户或集成 AI 可以明确把它留到后续独立窗口：在同一命令追加 `--skip-test-execution`。该参数只从本轮 mutation 中移除 `test-execution`，不改变默认顺序，也不把 Worker 标记为已部署；test-train 状态、验收 evidence 和手工测试结论都只能列出实际完成的 `control-plane`。后续需要 Worker 时必须对当时最新的可信 candidate 重新 plan，并在匹配 GPU runtime 的窗口单独部署/验收，禁止用这次控制面结果冒充 Worker 通过。

若 control-plane 计划同时满足 `level=none`、无 artifacts 且无 services，包装器不会为了推进状态机而调用空的 preflight/deploy。它记录 `ready-for-acceptance`、`deployment_mode=non-runtime` 和精确 SHA；若 `--skip-test-execution` 延后了 Worker，还会记录 `deferred_tracks=["test-execution"]`。验收 JSON 的 tracks 仍写 `control-plane`，modules 可为空，smoke 只证明 candidate bundle 已发布、可信 CI 成功、control-plane 为 non-runtime，以及 Worker 是否明确延后；不得写任何容器、Pages 或 Worker 已更新。

若后一个 track 部署失败，包装器按相反顺序回滚本轮已成功 track；单 track 内部继续使用 `release.py` 事务补偿。若部署成功但业务 smoke 失败：

1. 执行 `block` 并暂停其它无关 PR 合入。
2. 保留失败 candidate 供诊断；需要恢复可用性时由集成 AI 显式回滚最后 accepted candidate。
3. 原槽位从失败 train 创建 `codex/<slot>-<task>-fix-N`，提交新 PR 到 train。
4. 新 SHA CI 成功后重新 plan/deploy；不自动 revert、force-push 或改写 train 历史。

若本轮 candidate 的实际部署与 smoke 均通过，或 non-runtime candidate 的精确 bundle/CI/plan 证据均通过，集成 AI 先执行 `accept`，随后立即运行 `python scripts/manage_ai_workspaces.py park --slot <PR记录的槽位>` 并用 `status` 确认该槽位已经 detached/空闲。完成这一步后才能合入下一个无关 PR；不得把已经测试通过的槽位一直占用到整列 train 或正式发布结束。

Migration 只允许向前兼容。失败后不得自动 Alembic downgrade；通过 forward-fix 或显式恢复发布前测试库备份收口，期间 train 保持 blocked。

## 5. 验收与最终晋级

Candidate evidence 使用 `deploy/test-train-acceptance.example.json`，只记录本轮 PR/slot、受影响模块、smoke 和真实时间，不要求每个子任务观察 24 小时，也不能生成正式 verified 状态。

全部任务 accepted 后：

1. 创建 `codex/test-train` 到 `main` 的唯一集成 PR。
2. 等待 main CI 生成新的 main v2 bundle。
3. 把最终 main SHA 重新部署云测试，完成组合回归、回滚演练和人工验收。
4. 默认观察 24 小时；用户明确授权时才使用现有短观察 evidence/CLI 双重确认。
5. 执行 `verify-test`，再由用户明确确认正式发布同 SHA/digest。

main 合并会产生一个新的 merge commit。下一轮新的槽位 PR 合入 train 前，集成 AI 必须再通过 PR 把该 main 血缘同步回 `codex/test-train`，确保下一次 train→main PR 满足 strict up-to-date 保护；这不延迟已经 accepted 的槽位立即释放，也不得为此直接 push 或 force-push train。

## 6. GitHub 保护规则

`main` 与 `codex/test-train` 都禁止 direct push、force-push 和删除，要求 PR、现有 CI checks 全绿且 head 最新。当前单人维护形态不要求 review approval；集成 AI 只能通过 PR merge 推进 train/main。
