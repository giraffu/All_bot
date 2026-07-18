---
name: allbot-concurrent-workspaces
description: "管理 AllBot 多 AI 并发开发的 A-H 固定 worktree、主目录自动接单、高访问能力与外部 mutation 授权分离、任务分支交接、受保护 test-train 和唯一测试站发布。用户在 /home/hfy/APP/All_bot 直接提出开发、修复、重构或文档修改需求，要求槽位读取真实配置/凭据，或需要分配/停放工作区、合并到 codex/test-train、部署/验收 test-candidate、处理 blocked/forward-fix 时必须使用。"
---

# AllBot 并发工作区与 Test Train

## 1. 主目录需求自动接单

当用户在 `/home/hfy/APP/All_bot` 提出任何需要写入仓库的需求时：

1. 从需求生成 2-6 个英文小写词的 kebab-case slug；不询问用户选哪个槽位。
2. 在主目录立即执行 `python scripts/manage_ai_workspaces.py claim --task <slug>`。
3. 从 JSON 记住 `slot`、`path`、`branch`、`base_sha`，立即告知用户已接单的槽位。
4. 后续所有搜索、读取、编辑、测试和 Git 命令都以返回的 `path` 为工作目录；不在主目录修改功能代码。
5. 在槽位中读 `AGENTS.md`、本 Skill 及需求对应的业务 Skill，然后实现需求。

`claim` 在跨进程锁下自动刷新过期空槽并选择 A-H 中第一个安全槽位。若无槽位，在任何编辑前停止并向用户报告；不回退到主目录开发。

以下任务不自动 `claim`：纯解释/审查/状态查询、集成 AI 合并 PR、test-train 发布和用户明确指定已分配槽位。

## 2. 固定职责

- 把 `/home/hfy/APP/All_bot` 作为集成控制工作区，不在其中执行普通功能开发。
- 只在 `/home/hfy/APP/All_bot-workspaces/A` 至 `H` 开发并行任务；每个槽位只能承载一个任务分支。
- 让功能 AI 只修改当前 worktree、运行本地测试、推送分支并向 `codex/test-train` 提交 PR。禁止功能 AI 部署共享 test、操作 prod、Cloudflare 或 GPU runtime。
- 让集成 AI 独占 test-train 合入、candidate bundle、云测试切换、accept/block 与恢复。
- 功能 AI 完成后运行测试、提交、推送并创建 base 为 `codex/test-train` 的 PR；保持槽位在任务分支上，**不执行 `park`**。这会让后来窗口自动选择其他槽位。
- 集成 AI 在该 PR 已合入 train、精确 train SHA 的 candidate 已完成对应运行时部署并执行 `accept` 后，若没有 blocked/forward-fix，必须立即 `park` 对应槽位，再推进下一个无关 PR；不等全部 train 任务完成、合入 main 或正式发布后才释放。机器计划明确为 non-runtime 的 control-plane 不伪造容器部署：包装器记录 `ready-for-acceptance` / `deployment_mode=non-runtime`，以精确 bundle、CI 与 plan 证据 `accept` 后同样释放。

### 集成批次范围冻结

- 集成 AI 在第一次 train 合入、candidate 部署或其它共享 mutation 前，必须做一次只读盘点并冻结本批次成员。每个成员以 `slot + task branch + PR + handoff head SHA` 共同标识；只记槽位字母不构成稳定身份。
- 批次冻结后，新认领的任务、新提交的无关 PR，以及未列入批次的既有开发现场都属于后续批次。它们可以继续独立开发，不自动加入当前批次，也不因 dirty、落后 train、草稿 PR 或尚未交接而阻塞当前批次。
- 当前批次不得对非成员执行 merge/rebase、切分支、stash/clean、依赖清理、`park`、`refresh` 或其它写操作；只允许为判断冲突与容量做只读状态查询。即使某个批次槽位已释放后被新任务复用，后来的任务也不是原批次成员，收尾时不得按槽位字母再次操作。
- 同一任务为解决 train 冲突、CI 门禁、blocked candidate 或 forward-fix 产生的新 head/修复 PR，可作为原成员的可追溯修订继续留在批次；必须记录从原交接到新 head/PR 的关系。无关功能不得借 forward-fix 扩大批次。
- 批次按冻结顺序串行完成成员的 train 合入、candidate `accept` 与对应槽位释放，再冻结/批准最终候选、完成 train→main promotion 和 main→train 血缘同步。main 不重新构建或部署测试站。批次关闭后重新盘点，后续工作只能进入新的批次。

### 能力开放与操作授权

- A-H 功能 AI 可以读取真实 env、配置文件、SSH/API 凭据、日志、数据库连接信息和远端运行态；允许使用现有凭据进行只读核对、本地测试和生成操作计划。不要因槽位中存在这些文件而阻断任务或主动清理。
- 读取到的秘密不得原文写入对话、测试输出、日志、diff、commit 或 PR；除任务明确要求修改配置外，不改写、轮换或另存凭据。
- 凭据可见不等于获得外部 mutation 授权。共享 test 部署、prod、Cloudflare、RunPod/GPU、数据库 migration 和发布状态变更仍按本 Skill 与对应运维 Skill 的职责执行。
- Python `.venv`、前端 `node_modules` 和可写缓存以槽位独立为目标，避免并发污染。审计发现运行中任务沿用共享依赖或历史符号链接时，只告警并记录，不中断任务、不自动删除或替换；在任务交付后由集成维护流程收口。

## 3. 稳定入口

```bash
python scripts/manage_ai_workspaces.py status
python scripts/manage_ai_workspaces.py init
python scripts/manage_ai_workspaces.py claim --task <slug>
python scripts/manage_ai_workspaces.py assign --slot A --task <slug>
python scripts/manage_ai_workspaces.py park --slot A
python scripts/manage_ai_workspaces.py refresh --slot A

python scripts/test_train_release.py status
python scripts/test_train_release.py plan --sha <40位SHA>
python scripts/test_train_release.py deploy --sha <40位SHA> --pr <PR> --slot A --execute
python scripts/test_train_release.py deploy --sha <40位SHA> --pr <PR> --slot A --execute --with-test-execution
python scripts/test_train_release.py accept --sha <40位SHA> --evidence <json>
python scripts/test_train_release.py block --sha <40位SHA> --reason <原因>
python scripts/test_train_release.py freeze --sha <40位SHA>
python scripts/test_train_release.py approve-release --sha <40位SHA> --evidence <json> --approved-by <人> --execute
python scripts/test_train_release.py abort-freeze
```

## 4. 红线

- 不在集成批次进行中动态吸收后来完成的无关任务；不以“全部槽位收尾”为由操作批次冻结后出现的开发现场。
- 不在 dirty、未完成 merge/rebase、未推送或落后 train 的槽位上重新分配任务。
- 不删除 park 后的任务分支；只 detach 到最新 `origin/codex/test-train`。
- 不因 A-H 能读取 env、SSH key、Pages/GHCR token 或 runtime 信息而扩大外部写权限；秘密值不得出现在对话、diff、commit 或 PR。
- 只允许精确 `refs/heads/codex/test-train` 的可信 CI bundle 标记为 `test-candidate`。candidate bundle 只能直接部署 test，禁止 `verify-test`、prod 或 fast-track；只有冻结且逐 artifact 批准后，才可由 tree-identical main promotion CI 原样晋级 digest，不能绕过 main。
- `approve-release --execute` 必须先在集成机重新读取测试站运行态并生成精确批准文件。本机 GH token 缺少 `write:packages` 时，不得改 tag、扩权或绕过批准；使用受保护 `modular-release-v2.yml` 的 `publish_approval=true` dispatch，把该文件的 base64 与 SHA256 原样交给 Actions。该 job 只接受当前 `origin/codex/test-train` 头，复核 candidate descriptor、artifact 集与批准内容后不可覆盖发布，禁止 build 或部署测试站。
- 不让独立功能分支横向覆盖测试站。任务必须先合入 train，后一个任务在前一个 accepted candidate 上继续累积。
- GPU 基线无可用 artifact 时只接受 `availability: unavailable` 的读取计划；不得把它当作 GPU 验收或自动 mutation，涉及 GPU 的任务仍必须交给对应 canary/operator。
- 默认只部署确实要求测试的 `control-plane`/公共 Web artifact；`test-execution` 不再是默认步骤，只有专项 Worker 诊断才显式传 `--with-test-execution`。状态与 acceptance evidence 只能记录实际部署的 track，不得声称未启用的 Worker 已更新或验收。
- 若 `test-execution` 没有 track-scoped 历史状态，发布器必须把它视为受控首次切换并从 legacy Worker 快照迁移；预检不得要求尚未创建的 immutable Relay。control-plane 已完成而 Worker 首次切换预检失败时，原槽位继续负责 forward-fix，未完成两轨一致部署前不得 park 或写 accepted。
- 同一 candidate 的 control-plane 与 test-execution journal/staged state 及非敏感 `release.env` 必须按 track 分目录；云端合约路径为 `/var/lib/allbot/releases/<track>/<sha>/release.env`，Worker host 为 `release-env/<track>/<sha>/release.env`。Worker preflight 必须从同一 track-scoped 路径读取回滚材料；当该轨没有任何 cloud service 时必须跳过 cloud preflight，不得要求不会生成的云端合约。云端控制面若回滚目标早于 track 隔离迁移，预检、失败恢复和恢复验证可在 track-scoped 文件缺失时读取同一 SHA 的 legacy `/var/lib/allbot/releases/<sha>/release.env`，新候选仍必须写入 track-scoped 路径。Worker 首次切换不得覆盖已提交的控制面 journal/合约，也不得重跑 Postgres/Redis 控制面 cutover。发现升级前无 track 的失败 journal 时，只能通过带精确 `--track` 的 `recover` 兼容收口，禁止手工删 journal 或维护标记。
- 当 control-plane 的可信计划没有 artifacts/services 时，`deploy` 命令只把精确 candidate 记录为 `ready-for-acceptance` / `non-runtime`，不调用 release preflight/deploy；即使相对上一个实际部署 SHA 累积到已单独验收的运维路径、使 level 高于 `none`，也以空选择集为准，禁止伪造部署。Dashboard-only 管理面候选记录 `deployment_mode=test-not-required`，不得修改共享测试站。QQCC Config 已有专属测试实例，候选必须按 standard 部署对应前后端并等待业务验收。未显式传入 `--with-test-execution` 时，状态保留 `deferred_tracks=["test-execution"]`。证据必须写 bundle/CI/non-runtime、test-not-required 或实际部署计划和延后事实，不得写未更新的容器或 Worker 已更新。
- 部署事务失败时逆序恢复已完成 track，并在恢复成功后的错误中保留底层 `release.py` 最后一行摘要，便于集成 AI 定位失败轨道而不绕过包装器；部署成功但业务失败时 block train、保留现场并从原槽位做 forward-fix，不自动改写 Git 历史。
- candidate 未 `accept`、处于 blocked 或仍需 forward-fix 时不得释放原槽位；修复 candidate 被 `accept` 后立即释放。

## 5. 交付门禁

- 集成开始前记录批次成员及其交接身份；每次 `park` 前重新读取槽位状态，只有当前分支仍属于该成员且 candidate 已 `accept` 才能释放。身份不匹配时停止操作该槽位，但继续推进其它批次成员。
- PR 写明 slot、train base SHA、head SHA、v2 tracks/modules、测试、migration、风险和云测试步骤。
- 只有当前 candidate accepted 后才合入下一个无关任务。
- 当前 candidate accepted 后，集成 AI 必须先对 PR 记录的 slot 执行 `python scripts/manage_ai_workspaces.py park --slot <slot>` 并确认状态为空闲，再合入下一个无关任务。成功部署或 non-runtime `ready-for-acceptance` 但尚未 `accept` 都不算可释放。
- train 最终组合通过后先 `freeze`，按测试站真实 digest 生成 `verified`/`approved-direct` 批量批准记录，再合入 main。promotion CI 必须证明 ancestry/tree 相同并复用原 digest/checksum，禁止 build、测试站部署或 Web 重打包；任何 tree 差异产生新 candidate。
- main 合并完成后，在下一轮新的槽位 PR 合入 train 前通过 PR 把 main merge commit 血缘同步回 train，使下一次 train→main 满足 strict up-to-date；该血缘同步不延迟已经 accepted 的槽位释放，且禁止直接 push/force-push。

## 6. 按需读取

- 自动接单的用户操作只读 `docs/并发AI自动接单使用指南_auto_workspace_claim.md`。
- 槽位、train 或 blocked 细节读 `docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`。
- 部署 candidate 时加载 `allbot-ops-deployment`，只调用 `scripts/test_train_release.py`。
- 修改管理脚本时加载 `allbot-tdd`；规则变化后加载 `allbot-kb-auto-updater`。
