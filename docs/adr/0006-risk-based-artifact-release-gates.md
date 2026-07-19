# ADR 0006：按 artifact 风险分级发布门禁

- 状态：Accepted
- 日期：2026-07-16
- 取代：ADR 0004 中“所有生产 artifact 都依赖全局 verified”以及“GPU profile 必须有业务 canary 才能发布”的部分结论

## 背景

三 track 不可变发布解决了产物隔离，但单一 control-plane SHA 的全局 verified 仍把管理后台、公共 Web、测试 Worker 和正式 GPU profile 绑定到同一测试节奏。实际故障影响不同：管理面只有 owner 使用，公共 Web 只有刷新后生效，GPU worker 的单槽失败可由队列吸收；核心 API/Bot、migration 和共享部署契约则仍需强门禁。

## 决策

发布器按自动选择的 artifact 集合计算最高风险，支持 `standard/direct/emergency`。核心默认 standard，owner-tools 和 execution 默认 direct，公共 Web 默认 standard 可 direct，核心可 emergency；locked 变更只能 standard。策略只决定 CI 测试、test deploy、acceptance、observation 和 GPU business canary 是否可跳过，不影响不可变产物、main 血缘、配置、健康、事务、回滚、非目标服务和生产确认。

测试状态按 `track + artifact + digest` 保存在 history。standard 写 tested，低风险直发写 waived，GPU attestation-only 写 attested。按需共享测试发布默认不部署 test-execution，Dashboard/QQCC 管理服务从测试 Compose 移除。GPU artifact 强制 attestation；业务 canary 只对 standard 必需。RunPod/LAN operator 每次只滚动一个 slot，disabled 验证失败即恢复旧 digest 并停止。

CI 增加 `full` 与 `build-only`。build-only 仍由受保护 SHA 的成功构建任务产出 digest-pinned bundle，manifest 明确记录 tests skipped；消费它必须显式跳过 ci-tests 并记录风险接受，禁止用发布器的 CI 校验绕过开关执行。

## 后果

低风险模块和执行面可以快速正式修复，且审计不会把未测试产物伪装成 tested。状态读取从全局 current 改为精确 SHA history，因此低风险新 SHA 不会抹掉核心 artifact 的既有证据。代价是计划、preflight、状态和运维文档必须始终携带 risk/strategy/validation/skipped gates 与逐 artifact assurance。
