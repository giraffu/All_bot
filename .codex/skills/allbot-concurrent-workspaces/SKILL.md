---
name: allbot-concurrent-workspaces
description: "管理 AllBot A-H 固定 worktree、main 基线、不可变 handoff、单批次 main PR 与按需测试发布。用户在主目录提出写仓库需求、需要分配/释放工作区、冻结并行交接或组装发布批次时必须使用。"
---

# AllBot 并发工作区与单批次集成

## 1. 主目录自动接单

用户在 `/home/hfy/APP/All_bot` 提出需要写入仓库的开发、修复、重构或文档任务时：

1. 生成 2-6 个英文小写 kebab-case slug。
2. 在主目录执行 `python scripts/manage_ai_workspaces.py claim --task <slug>`。
3. 记住返回的 `slot/path/branch/base_sha` 并告知用户。
4. 后续读取、编辑、测试和 Git 命令只在返回的 A-H 路径执行。
5. 槽位基线固定为最新 `origin/main`；不再以 `codex/test-train` 为开发基线。

纯解释、审查、状态查询和集成发布不抢占槽位。没有安全空槽时，在编辑前停止，不回退到主目录开发。

## 2. 功能槽位交接

- 功能 AI 只在自己的 worktree 开发、运行 focused tests、提交并推送任务分支。
- 功能槽位不创建逐任务 test-train PR，不构建 release bundle，不部署共享 test，也不操作 prod、Cloudflare 或 GPU runtime。
- 代码推送完成后执行 `python scripts/manage_ai_workspaces.py handoff --slot <A-H>`。该命令验证工作区 clean、远端分支精确包含本地 head，返回 `slot + branch + head + base_sha` 的不可变交接身份，并立即把槽位停放到最新 `origin/main`。
- handoff 完成即允许槽位接新任务；后续集成按不可变 branch/head 找代码，不能再按槽位字母推断成员。
- handoff 后任务分支不得改写或 force-push。需要修改时产生新的 head，并作为新交接或当前批次的可追溯修订。

## 3. 一次性发布批次

集成 AI 在开始批次前冻结本轮 handoff：

```bash
python scripts/manage_ai_workspaces.py batch-plan \
  --batch <slug> \
  --output <release-batch.json> \
  --member A:codex/a-task@<40位SHA> \
  --member B:codex/b-task@<40位SHA>
```

`batch-plan` 只读核对每个远端 head 未漂移、记录各自 main base，并以独占创建方式写入不可覆盖的批次 JSON，同时输出唯一 `codex/release-batch-<slug>` 和 `pr_base=main`。随后：

1. 从冻结的 `origin/main` 创建批次分支。
2. 一次性组合所有精确 handoff head，解决跨任务冲突并运行批次级测试。
3. 只创建一个 `release-batch -> main` PR；成员任务不再各自进入 test train。
4. 批次冻结后出现的新 handoff 自动属于下一批，不动态插入当前 PR。

合并 main 前的 PR CI 可以运行代码门禁，但不会构建或发布容器。只有 main 合并后的 push CI 成功，才触发一次模块化 GitHub Actions 构建并生成 main-channel 不可变 bundle。

纯非运行时变更是批次流程的例外。`scripts/classify_ci_change.py` 仅对白名单中的 docs、`.codex/**`、tests、AGENTS/README、`.github/**`、`deploy/release-policy.yml`、`deploy/test-acceptance.example.json` 与精确列出的仓库治理/门禁脚本（含 `scripts/release.py`）返回 `lightweight`：

- 可创建单独 PR 直接合入受保护 main，或直接合入仍需维护的兼容分支，不必等待 release batch，也不生成 test-train candidate；
- PR/main workflow 只运行 change-scope/aggregate gate，跳过全量 Python、PostgreSQL、Web、Dashboard 测试；main push 不创建 release bundle，不部署 test/prod；
- 任一业务代码、migration、Compose、运行配置、白名单外发布执行器或未知路径都会 fail closed 为 `runtime`，恢复完整 CI、main bundle 与按需测试链路；
- 轻量路径仍要求本任务运行与改动相称的 focused tests 或文档检查，且不放宽 main 禁止 direct push/force-push。

## 4. 测试环境与正式发布

- 当用户需要部署测试环境时，使用已构建的完整 main SHA：`release.py plan -> preflight -> deploy --env test`。
- 测试控制面只从目标主机 `/etc/allbot/test.env` 生成权限为 `600` 的逐服务投影；不得把整份 env 注入所有容器，也不得把测试投影复制给正式环境。
- 测试按 main bundle 中的精确 digest/checksum 验收；standard artifact 通过 `verify-test` 写入 main-channel verified history。
- `verify-test` 仍要求精确 SHA/digest、全部适用 smoke、真实开始/完成时间和批准人，但不再要求固定 24 小时观察，也没有短观察 override/CLI 确认。
- 测试失败不回退或改写 main 历史。修复走新的功能 handoff 和新的单批次 main PR，再为新 main SHA 构建一次。
- 正式环境只接受受保护 main 可达完整 SHA、成功 main CI bundle 和对应策略证据；日常入口为 `python scripts/release.py promote --confirm-prod`，由它自动锁定候选和实际变化模块。每次生产 mutation 仍需用户明确调用并确认；高风险情形继续走发布器高级入口。
- 正式控制面独立从 `/etc/allbot/prod.env` 生成逐服务投影；配置漂移先走全量 `config-plan`/`config-apply`，或对一个具有容器 env 契约的独立模块使用同名 `--module` 局部暂存。局部暂存可替换/追加目标投影，但必须保证所有非目标 active 投影继续存在且 revision/字节不变；它不调用 Compose 或重启容器，代码发布不能隐式修改宿主 env 或复用测试配置。
- Dashboard 等 direct artifact 可按策略豁免测试验收，但不能绕过 main、CI、digest、配置、健康、事务回滚与生产确认。
- 测试 Worker 仅在专项诊断时显式部署；GPU/LAN AIO/RunPod 继续走专用 operator/canary。

## 5. 能力与授权边界

- A-H 可读取真实 env、配置、凭据、日志、数据库连接和远端状态，用于只读核对、本地测试与计划；秘密不得进入对话、输出、diff、commit 或 PR。
- 凭据可见不代表获准修改共享 test、prod、Cloudflare、RunPod/GPU、数据库或发布状态。
- `.venv`、`node_modules` 和可写缓存以槽位独立为目标。发现历史共享依赖只记录风险，不自动中断或清理运行中任务。

## 6. 红线与最小验证

- 禁止逐功能分支自动触发容器构建；`modular-release-v2.yml` 的 full 自动入口只能来自 main 上游 CI 的成功 `push`，或在 push 事件丢失后对当前 main 精确 head 手动重跑同一上游 workflow。恢复重跑必须再次通过完整预期 test jobs、workflow 元数据和当前 main head 验证；Modular workflow 自身的 `workflow_dispatch` 永远只产生 `build-only`。
- 禁止 direct push/force-push main；批次只能通过一个受保护 PR 合并。
- 禁止把旧 `test-candidate` channel 当作新批次入口。历史 candidate/promotion 工具只作既有记录兼容，不再生成新候选。
- 批次 PR 必须记录全部 handoff 身份、测试结果、影响 track/module、migration 和风险。
- 修改工作区或发布流程时运行：

```bash
python -m pytest -q tests/ops/test_manage_ai_workspaces.py
python -m pytest -q tests/ops/test_release_promotion_v2.py tests/ops/test_release_cli.py
python scripts/doc_quality_checker.py
```

规则变化继续加载 `allbot-tdd`、`allbot-ops-deployment` 与 `allbot-kb-auto-updater`。
