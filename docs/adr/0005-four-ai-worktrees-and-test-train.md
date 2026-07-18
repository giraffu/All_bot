# ADR 0005: 固定 AI Worktree 与单测试站 Test Train

日期：2026-07-15

容量修订：2026-07-16 将固定槽位从 A-D 扩展为 A-H；单测试站与职责边界不变。

## Status

Partially superseded by ADR 0007。A-H、单测试站与 forward-fix 决策继续有效；candidate 禁止晋级以及 main 重新构建复测的结论已被取代。

## Context

多个 AI 在同一物理工作目录并发会污染 index、未提交文件、依赖缓存和测试进程。项目只有一套真实云测试站，独立功能分支来回覆盖会让数据库迁移、Redis 队列、Bot polling、Worker 和最终组合状态不可追溯。schema v2 已能按发布 track/module 增量构建和部署，但正式发布必须继续以受保护 main 为事实源。

## Decision

- 固定 A-H 八个开发 worktree，根目录只承担集成职责。
- Worktree 用于隔离源码、index 与可写依赖，不作为权限沙箱；A-H 可读取真实配置、凭据、日志和远端状态，凭据可见与外部 mutation 授权分离。
- 使用受保护 `codex/test-train` 累积功能 PR，由单一集成 AI 串行部署共享测试站。
- 建立独立 `test-candidate` bundle channel；它只接受精确 train ref，只能直接部署 test，不能绕过 main 直接部署 prod。
- 部署成功但验收失败时保留 train 历史并 forward-fix，不自动 revert；最终候选冻结、批准并以原 digest 通过 tree-identical main 晋级。

## Alternatives Considered

- 每个 AI 一套测试站：隔离最强，但域名、数据库、Redis、R2、Bot token、Worker/GPU 和清理成本过高。
- 各功能分支轮流覆盖同一测试站：无需新 channel，但组合从未被测试，迁移和运行态会跨分支泄漏。
- 每个 PR 先合 main 再测试：沿用 main-only 发布契约，但会让未通过真实测试的任务进入正式事实源。

## Consequences

- 源码和依赖目录可并行隔离，共享测试站保持单写者和累积版本语义。
- 同一受信任 OS 用户让功能 AI 具备完整诊断上下文，但也要求秘密输出脱敏和明确的 mutation 职责；发现运行中任务使用历史共享依赖时不会自动中断，改在交付后的槽位维护中收口。
- Candidate channel 增加 CI、manifest、Git ancestry 和状态门禁；任何缺失字段或非精确 branch 都必须 fail closed。
- 单测试站仍是串行瓶颈；v2 增量 bundle 缩短切换时间但不改变排他要求。
- main 不重新构建或复测；不可变 candidate 批准记录就是正式 artifact 验收事实源。

## References

- `docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`
- `.codex/skills/allbot-concurrent-workspaces/SKILL.md`
- `scripts/manage_ai_workspaces.py`
- `scripts/test_train_release.py`
