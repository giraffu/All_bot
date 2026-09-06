---
name: "allbot-code-analyzer"
description: "执行全局代码静态分析与质量评估任务。当用户要求进行死代码检测、性能评估、架构审查、注释清理等全盘代码质量分析时必须触发此技能。"
---

# AllBot 静态代码分析与质量评估技能 (Code Analyzer)

用于全仓静态分析、质量评估、死代码和架构审查。扫描阶段必须静默、只读，
并清理临时文件。

报告口径与工具选择按需读取
`docs/子模块_代码静态分析与质量评估规范_code_quality.md`。

架构审查叠加 `allbot-codebase-design`，使用 module/interface/seam/adapter/depth/
leverage/locality 给出可验证结论。

## 1. 扫描阶段

- 覆盖仓库所有生产代码；排除 `.venv`、构建产物、缓存和一次性日志。
- 只读检查死代码、注释/TODO、未使用与循环 import、作用域、重复、N+1/阻塞/
  内存风险、Core Isolation、浅模块、错误 seam、长函数和高复杂度。
- 原始输出进入临时文件或内存，不在对话打印长代码和全量诊断。
- 区分“静态候选”与“已核实可删除”：动态注册、CLI、callback、反射、migration
  和兼容入口必须结合调用点、契约测试与 `config/compat_registry.json` 核对。

## 2. 评估与报告

- 按 Critical/High/Medium/Low 分级，给出覆盖范围、行数、复杂度、重复率估值、
  dead-code 候选/确认数、import SCC 和前后端热点。
- 每个核心问题记录路径、行号、类型、等级、证据和建议；不要把工具告警直接当
  结论，也不要把历史扫描数字写进活跃架构文档。
- 保存 UTF-8 `logs/code_analysis_report_<yyyyMMdd_HHmm>.md`，然后删除所有临时
  缓存/切片。报告不提交 Git。

## 3. 与整改任务的衔接

- 仅要求审查/报告时，到报告为止，不能修改代码。
- 用户同时明确要求“分析并优化/重构/更新”时，先完成上述只读扫描和报告，再
  退出扫描阶段；随后按 `allbot-concurrent-workspaces`、命中领域 Skill、
  `allbot-codebase-design`、`allbot-tdd` 和 `allbot-kb-auto-updater` 实施已确认项。
- 删除兼容 seam 必须满足 registry 的 telemetry、观测窗口和历史数据条件；不满足
  时只记录债务。一次只整改可验证的纵向切片，运行 focused tests 后再扩展。

最终交付给出报告绝对路径、关键指标、Critical 风险、已整改项和未整改优先级；
不得粘贴大段中间输出。
