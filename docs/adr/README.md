# AllBot Architecture Decision Records

ADR 保存决策历史，不是日常 SOP。实现与运维先读取当前 Skill/专项文档；
只有需要理解取舍时再读 ADR。

| ADR | 状态 | 当前解释 |
| --- | --- | --- |
| `0001-postgresql-only-runtime.md` | Accepted | 运行时数据库统一 PostgreSQL |
| `0002-qqcc-private-bots-use-webhooks.md` | Accepted | 私有 QQCC 使用多租户 webhook |
| `0003-git-sha-immutable-image-promotion.md` | Accepted / amended | 不可变身份继续有效，artifact 晋级语义由后续 ADR 修订 |
| `0004-three-release-tracks-and-thin-images.md` | Accepted / partially superseded | 三轨与薄镜像有效，门禁以 ADR 0006/当前发布 policy 为准 |
| `0005-four-ai-worktrees-and-test-train.md` | Superseded by 0008 | 只保留 A–H 与共享测试站历史；test-train 不再是当前流程 |
| `0006-risk-based-artifact-release-gates.md` | Accepted | 按 artifact 风险与 assurance 执行门禁 |
| `0007-promote-tested-candidate-artifacts.md` | Superseded by 0008 | candidate promotion 只作历史兼容 |
| `0008-main-first-release-batches.md` | Accepted | 不可变 handoff、单批次 main PR、main 后按需测试 |

新增 ADR 只有在决策难逆、非显然且存在真实替代方案时使用
`0000-template.md`。状态变化先更新 ADR 自身，再更新本索引和知识库矩阵。
