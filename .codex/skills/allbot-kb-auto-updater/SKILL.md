---
name: "allbot-kb-auto-updater"
description: "评估代码现状对 docs/skills/memory 的影响，并同步更新知识库。当项目新增功能、重构入口或接口语义变化时，必须调用本技能。"
---

# AllBot 智能知识库自动更新 (KB Auto-Updater)

本技能用于维护 AllBot 的知识体系与代码现状一致。当核心门面、运行时依赖、状态流、接口 I/O、测试策略或技能边界发生变化时，应优先用本技能同步 `docs/`、`.codex/skills/` 与项目记忆。

目标不是让每层都“完整”，而是形成低 token 的导航 interface：
`AGENTS.md → 命中 Skill → 代码/测试事实源 → 一篇命中专题文档`。普通任务不预读
审计矩阵、全部 docs 或 archive。

## 1. 模块核心能力
- **现状扫描优先**：优先基于代码现状、关键入口、公开 facade、provider/dependencies 边界判断知识是否失真；必要时再结合 `git diff` 或用户提供的片段。
- **技能失真识别**：当 `SKILL.md` 主张与代码入口冲突时，先更新技能，再继续开发，避免旧技能误导后续改动。
- **上下文预算治理**：Skill 只保留触发、按需路由、稳定 seam、红线和最小
  验证；日期、IP/邮箱 allowlist、当前部署结果、数量快照和一次性 canary
  进入运行态、evidence 或 archive。
- **结构一致性维护**：确保 `AGENTS.md`、`.codex/skills/`、`docs/` 与项目记忆在高层路由、入口文件、异常类型、超时值、双 ID 语义等关键点上一致。
- **核对矩阵维护**：全量或跨模块校准时，一份活跃文档/Skill 只登记一行
  canonical 事实源和状态；责任域由分节表示，静态复核日期和 archive 入口只
  写一次。archive、已删除 seam 与逐日处理结果不登记为活跃行。
- **领域词汇维护**：当术语含义被澄清、重命名或出现冲突时，同步更新 `docs/domain/CONTEXT.md`；该文件只写词汇含义，不写实现细节。
- **ADR 节制记录**：只有决策难逆、非显然且存在真实取舍时，才基于 `docs/adr/0000-template.md` 新增 ADR。
- **变更日志输出**：在交付时给出清晰的知识库 Changelog，说明改了哪些文件、为什么改、对应哪类代码变化。

## 2. 输入输出规范
### 触发条件 (When to invoke)
- **输入**：
  - 代码现状扫描需求
  - 架构重构、接口变化、主入口迁移、provider/capability 重构
  - 领域术语、共享语言、ADR 或架构决策记录变化
  - 需要同步 `docs/`、`SKILL.md`、memory 的任务
- **输出**：
  - 需更新的 docs / `.codex/skills` / memory 清单
  - 逐项核对矩阵或矩阵更新说明
  - 更新后的文档与技能内容
  - Changelog 与一致性说明

## 3. 更新策略
1. **局部接口/参数调整**：
   - 优先更新对应 `/docs/` 技术文档。
   - 若触发强边界约束或技能主张变化，同步更新相应 `SKILL.md`。
   - 价格、枚举、节点 ID 或部署清单已有代码事实源时，不再复制完整清单到 Skill。
2. **核心门面 / provider / 状态流重构**：
   - 优先同步 `docs/` 架构文档与回归清单。
   - 同步更新相关技能文档中的主入口、异常类型、超时值、测试要求。
   - 若产生新的稳定术语，写入 `docs/domain/CONTEXT.md`；若存在难逆取舍，再新增 ADR。
   - 必要时更新项目记忆，记录新的稳定架构事实。
3. **全新模块/微服务引入**：
   - 创建新的业务文档与技能文档。
   - 若影响全局路由，再同步 `AGENTS.md` 与 `docs/skills/README.md`。
4. **废弃或兼容壳退出**：
   - 删除或标记归档对应 docs/skill 说明。
   - 若存在 compat seam 退出，应在文档中明确新的真实入口。

## 4. 质量检查与验收
- 技能与文档中的主入口函数、关键对象名、异常类型、超时值、双 ID 语义必须与代码一致。
- 当测试策略已迁移到显式 `dependencies` / `*_func` seam，知识文档也必须同步更新，不能继续鼓励旧的模块级 patch 方式。
- 若说明依赖运行时 provider 注册，必须在文档中写明“入口负责注册，core 不自动注册”。
- `SKILL.md` 应优先记录稳定入口、触发边界、红线与最小验证要求；一次性 Pod ID、任务 ID、失败尝试流水账、真实密钥值和长篇现场日志不应沉淀到技能正文。
- 领域 `SKILL.md` 应提供任务到专项文档的按需路由；不要用“阅读整个 docs
  目录”作为路由。只在一次任务确实跨层时组合多篇。
- `docs/domain/CONTEXT.md` 只能作为 glossary 使用，不应变成 spec、runbook、事故记录或实现设计草稿。
- `docs/knowledge_base_audit_matrix.md` 不替代模块 SOP；依赖远端观测但本轮
  未探测时标记 `runtime-verification-required`，不能写成已验证。
- ADR 必须说明 context、decision、alternatives、consequences；缺少真实替代方案时不要新增 ADR。
- 最终总结必须包含 Changelog，列出修改文件与原因。
- 运行 `python scripts/doc_quality_checker.py`；不得通过提高预算掩盖新增冗余。

## 5. 使用示例 (最佳实践)
当开发者完成一轮核心重构后，可直接要求：
> “根据现在最新的代码，帮我更新一下 docs/ 下的文档、系统 skill 和记忆，保持知识体系最新。”

此时应先扫描代码现状，再落地更新 docs / skills / memory，而不是只机械复制 diff。
