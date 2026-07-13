# 首次可信 Release 准备记录

## 1. 当前结论

仓库侧 stabilization 已按“完整 Git SHA + CI 不可变产物 + 同 digest 晋级”合入主线，并成功产出过一组可独立核验的候选 bundle；首次测试切换预检随后发现 Worker 08/运行时参数闭包、legacy 同 Agent 停机顺序和跨控制面/Worker 维护窗口仍需收口。候选提交必须以这些修正最终合入 `main` 后的 `git rev-parse HEAD` 为准；旧 bundle 只作验证证据，不作为首次切换目标。

用户已授权仅测试环境首次切换；生产部署和正式 Pages mutation 仍未授权。当前代码仍处于切换闭包修正/CI 阶段，在新的 SHA bundle 通过门禁并完成主机预检前不得执行测试切换。

## 2. 已完成的仓库门禁

- stabilization 基线 Python：`2563 passed`；后续 release CI 已改为 Python 3.10 分片门禁并成功完成。
- stabilization 基线 Ops 子集：`379 passed`；LAN AIO 专项 `46 passed`。本次 Worker 切换闭包聚焦回归：`29 passed`；本地完整 Ops 的其它失败若来自未归属的 fleet state 工作区改动，不并入本次 release commit。
- Web：`294 passed`，`npm run build` 通过。
- Dashboard：`93 passed`，类型检查与 `npm run build` 通过。
- Alembic：单 head `3e9c7a1b5d24`。
- test/prod/worker immutable Compose：使用 dummy env 执行 `config -q` 通过，未输出展开配置。
- `python scripts/doc_quality_checker.py` 通过。
- 旧 test/prod/QQCC 同步入口均以退出码 `2` fail closed。
- `git diff --check` 通过；未发现未跟踪 env、私钥、token 或 credential 文件。

验证仅证明仓库候选满足对应门禁，不替代最终合入 SHA 的 GitHub Actions、镜像 smoke、云测试真实任务、24 小时观察或生产晋级门禁。

## 3. Git 血缘整理

- stabilization 与后续 Python 3.10、依赖、分片 CI 修正已通过 PR 纳入 `main`，发布器只接受 `origin/main` 可达的最终完整 SHA。
- Python 镜像基座统一钉死为 Python 3.10.20 的 Bookworm digest；本机宿主 Python 3.13 不参与 release 运行时判定。
- `origin/deploy` 只创建首次切换前归档 tag，随后冻结，不再作为生产代码来源。
- 本地 `debug-main-bot-lag.md` 是未完成排障草稿，不进入 stabilization commit。

## 4. 送审与首次发布待办

1. 将 Worker 切换闭包 PR 合入受保护 `main`，以合并后的完整 40 位 SHA 触发新的 release workflow；旧候选 bundle 不部署。
2. 核对新 CI 成功、OCI revision、所有镜像 digest、Web SHA256 与不可覆盖的 release bundle。
3. 用云测试当前 env 作为控制面事实源、本机旧 env 作为 Worker 参数源，经 test-only 迁移器生成 `/etc/allbot/test.env` 候选并完成 schema/cloud/worker Compose dry-run，任何输出不得含秘密值；未选 dormant 槽位只允许使用 disabled 安全默认值，allowlist 内槽位仍必须显式满足 schema。
4. 在目标机完成只读 deploy key、GHCR `read:packages` 凭据和 release host bootstrap；密钥不进入仓库、源码 checkout 或 CI。
5. 使用 test-only env 迁移器生成候选并校验 `/etc/allbot/test.env`，原子安装为 `600 deploy:deploy`；先部署云测试与测试 Web，再在同一维护窗口停止 allowlist 对应 legacy Worker、启动同 digest 本地测试 Worker，健康后才解除维护。
6. 完成 health、Bot、任务提交、Redis 锁、locale、Web、Worker heartbeat、图片/视频代表任务和回滚演练，并观察至少 24 小时。
7. 写入 verified 验收记录后，才允许以同一 SHA/digest 申请生产确认。
8. 首次生产切换前归档 legacy compose、容器 image ID、混合源码与 env；生产部署和 Pages 变更仍需明确确认。
