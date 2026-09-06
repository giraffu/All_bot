---
name: allbot-kb-auto-updater
description: 按实际代码审计并更新 AllBot 的 AGENTS.md、docs、项目 Skills、领域词汇、ADR 和知识矩阵。用户要求整理或精简知识库、修复过时文档、优化 Skill 触发，或代码改变入口、接口、状态语义和稳定术语时必须使用。
---

# AllBot 知识库维护

保持 `AGENTS.md → 命中 Skill → 代码/测试事实源 → 命中专题文档` 的低上下文导航。代码和 focused tests 是现状证据；知识冲突时先修正知识，再继续开发。

## 工作流

1. 确认变更的公开接口、状态 owner、provider/dependencies、异常、超时、ID 和术语。
2. 读取命中的最少 Skill、代码入口和专项文档；全系统校准才读
   `docs/system_module_inventory.md` 与 `docs/knowledge_base_audit_matrix.md`。
3. 更新最窄事实源：实现细节进专项文档，触发/路由/红线进 Skill，共享词义进
   `docs/domain/CONTEXT.md`。
4. 新增或退出兼容 seam 时更新 `config/compat_registry.json` 的 owner、telemetry、替代入口和退出条件。
5. 新增 Skill 时同步 Skill、`AGENTS.md`、`docs/skills/README.md` 和审计矩阵。
6. 校验路由、链接、体积和失真项；交付列出文件、原因及尚需运行态核验的事实。

## 分层边界

- Skill 只保留触发条件、稳定入口、按需文档路由、高压红线和最小验证。
- 专项文档维护当前架构、业务契约和 SOP；不要复制已有代码枚举或完整价格表。
- glossary 只解释稳定术语，不承载实现、事故或草稿。
- 难逆、非显然且存在真实替代方案的决策才新增 ADR。
- 审计矩阵一份活跃资料一行；它是索引，不替代模块 SOP。
- 日期化部署结果、节点数量、一次性任务、事故和 canary 进入 evidence、archive 或日志。
- 密钥、签名 URL、真实用户内容、支付或公司秘密不得进入 Git。

## 更新判定

- 局部接口或参数变化：更新对应专题文档；只有触发边界或稳定 seam 改变才更新 Skill。
- facade、provider、状态流或测试 seam 变化：同步架构/行为文档与领域 Skill；稳定新词再更新 glossary。
- 新模块：建立一篇 canonical 文档和一个必要的 Skill；影响全局导航时更新总路由。
- 退役入口：删除当前说明或转历史归档，不把已删除 seam 留成“下一步”。
- 依赖远端观测而本轮未核实时，标记 `runtime-verification-required`，不得写成已验证。

## 质量门禁

- 名称、路径、异常、超时、双 ID、注册责任和依赖注入语义必须与代码一致。
- 不用“读取全部 docs”作为 Skill 路由，不用拆 reference 规避上下文预算。
- 活跃文档不写逐日 changelog；交付摘要可以说明本次知识变更。
- 用项目知识质量检查器验证必需文件、路由覆盖、矩阵登记、链接、日期化运行态和体积预算；不得提高预算掩盖冗余。
