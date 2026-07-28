# ADR 0009：人工结果决定独立模块发布

日期：2026-07-28

## Status

Accepted。取代 ADR 0003、0004、0006、0007、0008 中关于 bundle、三轨、
CI/test evidence、promotion 和 release batch 的发布决策。

## Context

旧流程把 change scope、全量 CI、三轨完整性、GPU baseline、共享测试部署和
promotion evidence 串成资格状态机，独立业务模块会被无关模块阻断。项目已有
人工测试环境，操作者愿意直接对实际结果负责。

## Decision

- main 单写者只串行合并精确 handoff；冲突进入 `needs-rebase` 后继续队列。
- 构建由操作者明确选择模块和 SHA，只包含必要 base。
- test/prod 直接部署单个精确 digest；prod 仅要求 `--confirm-prod`。
- 系统不查询 CI、diff、测试批准、bundle、其它模块或 track 完整性。
- adapter 检查目标结果；失败只回滚目标 previous，migration 不自动回滚。
- 历史 bundle、acceptance、transaction 和 failed batch 保持只读取证。

## Consequences

发布速度和模块隔离提高，同时机器不再判断人工测试质量。操作者必须明确选择
构建输入、测试范围、部署目标和生产时机。不可变 digest、精确目标、结果检查、
局部恢复与 prod 显式确认继续作为执行安全边界。
