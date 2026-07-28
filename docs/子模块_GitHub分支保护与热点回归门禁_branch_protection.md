# GitHub main 写入保护

## 当前规则

main 不要求 PR、status check 或 conversation resolution。唯一正常写者是本机
handoff 协调器，因此 GitHub ruleset 只保留：

- 禁止 force push；
- 禁止删除 main；
- 只允许协调器凭据正常 push（按 GitHub 实际能力配置 bypass/写权限）。

这些是并发写入保护，不是 CI 或发布门禁。协调器不查询 GitHub Actions。

仓库已删除旧 control-plane、modular、hotspot 和 GPU build workflow，仅保留
非阻断的文档质量 workflow。平台 ruleset 必须在新协调器代码进入 main 后再
移除 required PR/status check，避免切换窗口没有可用 main 写者。

GitHub 当前 ruleset 属于外部运行态，应通过只读 API 核对；不得把实时 rule ID、
actor ID 或 token 写入文档。
