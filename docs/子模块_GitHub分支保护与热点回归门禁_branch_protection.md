# GitHub 分支保护与热点回归门禁

## 1. 目标

本说明用于把热点回归门禁真正接入 GitHub 平台侧规则，避免 workflow 已存在但未被设置成必过检查，导致门禁只“会跑”而不会“拦”。

本说明只覆盖以下内容：

- `main` 分支建议开启哪些保护项
- 热点回归门禁应配置成哪个 required status check
- 为什么应要求聚合结果 job，而不是直接要求分流 job

## 2. 当前仓库内入口

当前热点回归门禁由以下两层入口组成：

- 本地统一脚本：`scripts/run_hotspot_regression.sh`
- GitHub Actions workflow：`.github/workflows/hotspot_regression_gate.yml`

其中 workflow 已具备以下能力：

- 对热点文件变更的 `pull_request` 自动触发
- 对 `main` 分支热点文件变更的 `push` 自动触发
- 支持 `workflow_dispatch` 手工指定分组
- 按改动路径自动推导 Python/Frontend 分组
- 通过 `Hotspot Gate Result` 聚合 job 输出稳定检查名

## 3. 推荐的分支保护配置

目标分支：

- `main`

建议至少开启：

- Require a pull request before merging
- Require approvals
- Dismiss stale pull request approvals when new commits are pushed
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Do not allow bypassing the above settings（若仓库治理希望更严格）

## 4. Required Checks 建议

### 4.1 热点回归门禁

应要求的检查名：

- `Hotspot Gate Result`

原因：

- `Python Hotspot Gate` 与 `Frontend Hotspot Gate` 是按路径条件触发的分流 job
- 某些 PR 只会命中其中一个 job，另一个 job 可能被跳过
- 如果直接把分流 job 配成 required check，GitHub 分支保护容易出现“检查缺失/检查被跳过”的配置噪音
- `Hotspot Gate Result` 会在任何情况下出现，并聚合判断：
  - 无热点改动时，no-op 通过
  - 有热点改动时，依赖实际命中的 Python/Frontend gate
  - 任一上游 gate 失败或取消时，聚合 job 失败

### 4.2 文档门禁

若希望文档修改也受保护，可额外要求：

- `Docs CI`

适用前提：

- 仓库希望 `docs/**/*.md` 和 `README.md` 的变更也成为合并门禁的一部分

## 5. 平台侧配置步骤

在 GitHub 仓库页面依次进入：

1. `Settings`
2. `Branches`
3. `Add branch protection rule`
4. Branch name pattern 填 `main`
5. 勾选 `Require status checks to pass before merging`
6. 在 checks 列表中选择：
   - `Hotspot Gate Result`
   - 可选：`Docs CI`
7. 保存规则

如果仓库使用新的 Rulesets 而不是旧 Branch protection rules，配置思路相同：

- 目标分支仍为 `main`
- 仍以 `Hotspot Gate Result` 作为 required check

## 6. 维护原则

- 新增热点文件后，要同步更新：
  - `docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md`
  - `.github/workflows/hotspot_regression_gate.yml`
  - `scripts/run_hotspot_regression.sh`
- 新增回归分组后，必须保证：
  - 本地脚本可执行
  - workflow 能自动检测或手工 dispatch
  - 聚合 job 仍保持稳定通过/失败语义
- 不要把分流 job 名称频繁改动；branch protection 依赖稳定检查名

## 7. 当前限制

- GitHub branch protection 是平台设置，不在仓库文件内，无法仅通过提交代码直接替你在平台完成配置
- 当前 workflow 已足够作为 required check 使用，但是否“真正拦截合并”仍取决于仓库管理员是否在 GitHub 设置页启用该检查

## 8. 后续建议

下一步若继续加强这条门禁，可以考虑：

1. 为 `hotspot_regression_gate.yml` 增加更细粒度的 matrix 拆分
2. 为失败场景补充更清晰的摘要输出或 artifact
3. 在仓库治理文档中补一条“新增热点文件时必须同步更新门禁配置”的维护规则
