# ADR 0008：并行 handoff、单批次 main 合并与按需测试

日期：2026-07-19（2026-07-22 增补自动集成队列）

## Status

Accepted。取代 ADR 0005 的串行 test-train 决策和 ADR 0007 的 candidate digest promotion 日常流程；A-H worktree、单一共享测试站、不可变产物和正式发布门禁继续有效。

## Context

多个功能槽位可以并行完成代码，但原流程要求每个成员依次创建 test-train PR、等待完整 CI 和 candidate 构建、切换唯一测试站并 accept，随后才允许下一个成员进入。昂贵的 GitHub Actions 容器构建和共享测试站切换按成员重复发生，使批量开发的吞吐受最慢串行阶段限制。

生产环境已经与 Git main 解耦：main 合并不会自动修改生产，正式发布仍由不可变 bundle、精确 digest 证据、preflight、事务回滚和用户确认控制。因此允许代码先以批次进入 main，再按需构建和部署测试，不会自动扩大生产 mutation 权限。

## Decision

- A-H 槽位统一从 `origin/main` 开始开发。
- 功能 AI 完成本地测试、提交和推送后生成不可变 handoff；handoff 绑定 slot、远端 branch、完整 head SHA 和 base SHA，并立即释放槽位。
- 功能任务不创建逐成员 test-train PR，也不触发 release bundle 构建或共享测试站部署。
- 集成 AI 冻结若干 handoff 为一个不可覆盖的 release batch JSON，从冻结 main base 一次组合，运行批次测试，只创建一个 `release-batch -> main` PR。
- 日常由本机用户级 timer 的单写者协调器消费 handoff：锁定时所有 pending 成员进入当前批次，运行中到达的新成员进入下一批；阶段持久化允许进程中断后续跑。失败批次阻断后续工作，避免在未通过的 main/test 基线上继续滚动。
- PR CI 负责代码门禁但不发布容器。main push 的可信 CI 成功后，模块化 workflow 才为该 main SHA 构建一次 main-channel bundle；未变化 artifact 可从既有 main bundle 复用。若托管平台丢失 push workflow 事件，只允许手动重跑当前 main 精确 head 的同一上游 CI，并由模块化 workflow 重新验证完整 test job 集；模块化 workflow 自身的手动入口仍只有 build-only 权限。
- main bundle 的影响判定按 artifact track 隔离：控制面、Public Web、文档和发布工具变化不调度 GPU 构建；GPU artifact/profile 或执行代码变化继续通过独立 manifest、canary 和 operator 链路发布。
- 自动批次的非 lightweight main bundle 成功后，协调器只把该 SHA 串行部署到唯一云测试站。协调器没有生产环境参数；standard artifact 通过 `verify-test` 写入 exact-digest main-channel evidence，direct artifact 按风险策略明确豁免。
- 测试失败通过新的 handoff 和新的 main 批次 forward-fix，不改写 main 历史。
- 生产继续只消费受保护 main bundle。每次 mutation 仍需 main/CI/digest/config/health/rollback 门禁和用户明确 `--confirm-prod`。
- `codex/test-train`、test-candidate 和 promotion 工具只保留历史兼容，不再作为新批次入口。

## Alternatives Considered

- 保留逐成员串行 test-train：测试隔离最细，但重复构建、部署和人工验收成为主要延迟来源。
- 并行部署多个功能分支到同一测试站：会让运行 digest、迁移、Redis 队列和 Bot polling 失去单一可追溯基线。
- 每个槽位直接 PR 到 main：减少 test-train，但仍产生多个合并和多次 main 构建，不能满足单批次目标。
- 由各槽位在 handoff 后各自合并/部署：实现简单，但多个写者会竞争 main 和唯一测试站，无法提供明确的失败阻断与顺序。
- 在 main 合并前构建一个最终 candidate 再 promotion：产物更早得到测试，但仍保留第二条 candidate channel、冻结/批准/promotion 状态机和额外 Git 合并。

## Consequences

- 日常批量开发只有一个远端 main 合并点和一次容器构建，吞吐明显提高。
- main 可能暂时包含尚未部署真实测试站的代码；main 表示代码事实源，不等于生产已发布。正式环境仍由已部署 digest 决定。
- 真实测试失败需要新的 main forward-fix commit，不能隐藏或重写已合并历史。
- 批次规模增大时，组合冲突和回归定位可能更粗；批次必须冻结明确 handoff，并在 main PR 前运行 focused/组合测试。
- 自动合并扩大了协调器权限；因此只允许本机单写者、精确远端 head、受保护 main PR 和必需检查，任何失败均 fail closed。正式发布能力刻意不进入该接口。
- 历史 candidate bundle、approval 和 promotion state 继续可读以支持回滚取证，但不得触发新发布。

## References

- `scripts/manage_ai_workspaces.py`
- `scripts/auto_integrate_handoffs.py`
- `deploy/systemd/allbot-ai-integration-queue.timer`
- `.github/workflows/control-plane-release.yml`
- `.github/workflows/modular-release-v2.yml`
- `scripts/validate_upstream_ci_run.py`
- `scripts/release.py`
- `docs/子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md`
- `.codex/skills/allbot-concurrent-workspaces/SKILL.md`
