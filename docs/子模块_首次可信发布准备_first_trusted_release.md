# 首次可信 Release 准备记录

## 1. 当前结论

仓库侧 stabilization 候选已按“完整 Git SHA + CI 不可变产物 + 同 digest 晋级”整理。候选提交必须以当前分支最终 `git rev-parse HEAD` 为准；本文不硬编码自身提交 SHA，避免文档提交改变候选 SHA。

本轮只整理本地仓库，不执行 Git push/PR、远端 tag、GHCR 发布、云主机 bootstrap、env 迁移、测试/生产部署或 Cloudflare Pages mutation。因而当前状态是“可送审候选”，不是已经可部署的可信 release。

## 2. 已完成的仓库门禁

- Python：`2563 passed`。
- Ops 子集：`379 passed`；LAN AIO 专项 `46 passed`。
- Web：`294 passed`，`npm run build` 通过。
- Dashboard：`93 passed`，类型检查与 `npm run build` 通过。
- Alembic：单 head `3e9c7a1b5d24`。
- test/prod/worker immutable Compose：使用 dummy env 执行 `config -q` 通过，未输出展开配置。
- `python scripts/doc_quality_checker.py` 通过。
- 旧 test/prod/QQCC 同步入口均以退出码 `2` fail closed。
- `git diff --check` 通过；未发现未跟踪 env、私钥、token 或 credential 文件。

验证仅证明当前本地代码候选满足仓库门禁，不替代 GitHub Actions、镜像 smoke、云测试真实任务、24 小时观察或生产晋级门禁。

## 3. Git 血缘整理

- 开发 lineage 相对 `origin/main` 含大量历史提交；`origin/main` 另有 4 个 RunPod workflow 提交。
- 这 4 个提交的文件已存在于开发 lineage，并有后续修正；首次候选以 merge commit 纳入 `origin/main` 血缘，同时保留已验证的较新 workflow 内容。
- `origin/deploy` 只创建首次切换前归档 tag，随后冻结，不再作为生产代码来源。
- 本地 `debug-main-bot-lag.md` 是未完成排障草稿，不进入 stabilization commit。

## 4. 送审与首次发布待办

1. 推送 stabilization 分支与两个 archive tags，创建 PR；这些是外部 mutation，需单独授权。
2. PR 合入受保护 `main`，以合并后的完整 40 位 SHA 触发 release workflow。
3. 核对 CI 成功、OCI revision、所有镜像 digest、Web SHA256 与不可覆盖的 release bundle。
4. 在目标机完成只读 deploy key、GHCR `read:packages` 凭据和 release host bootstrap；密钥不进入仓库或 CI。
5. 人工迁移并校验 `/etc/allbot/test.env`，先部署云测试与本地测试 Worker。
6. 完成 health、Bot、任务提交、Redis 锁、locale、Web、Worker heartbeat、图片/视频代表任务和回滚演练，并观察至少 24 小时。
7. 写入 verified 验收记录后，才允许以同一 SHA/digest 申请生产确认。
8. 首次生产切换前归档 legacy compose、容器 image ID、混合源码与 env；生产部署和 Pages 变更仍需明确确认。
