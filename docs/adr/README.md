# AllBot Architecture Decision Records

ADR 保存决策历史，不是日常 SOP。实现与运维先读取当前 Skill/专项文档；
只有需要理解取舍时再读 ADR。

| ADR | 状态 | 当前解释 |
| --- | --- | --- |
| `0001-postgresql-only-runtime.md` | Accepted | 运行时数据库统一 PostgreSQL |
| `0002-qqcc-private-bots-use-webhooks.md` | Accepted | 私有 QQCC 使用多租户 webhook |
| `0003-git-sha-immutable-image-promotion.md` | Superseded by 0009 | 不可变身份历史 |
| `0004-three-release-tracks-and-thin-images.md` | Superseded by 0009 | 三轨发布历史 |
| `0005-four-ai-worktrees-and-test-train.md` | Superseded by 0008 | 只保留 A–H 与共享测试站历史；test-train 不再是当前流程 |
| `0006-risk-based-artifact-release-gates.md` | Superseded by 0009 | 风险门禁历史 |
| `0007-promote-tested-candidate-artifacts.md` | Superseded by 0009 | candidate promotion 历史 |
| `0008-main-first-release-batches.md` | Superseded by 0009 | batch/PR/自动测试历史 |
| `0009-operator-decides-module-release.md` | Accepted | 独立模块、人工结果、轻量 main 单写者 |
| `0010-observer-bot-isolated-runtime.md` | Accepted | Observer 独立进程、逻辑数据库和本地 LM Studio |

新增 ADR 只有在决策难逆、非显然且存在真实替代方案时使用
`0000-template.md`。状态变化先更新 ADR 自身，再更新本索引和知识库矩阵。
