# 热点门禁阶段历史

本文件保存从活跃热点门禁文档移出的阶段流水，仅用于追溯，不是当前回归 SOP。

## 已完成阶段

- 阶段 1：清理重复胶水、薄公共状态组件和后端 fallback/session 样板。
- 阶段 2：收口 Gallery、MyFavorites、MySubmissions 与生成工作台公共结构。
- 阶段 3：完成 message、users、gallery、tasks 主要薄控制器拆分。
- 阶段 4：下线 `bot_task_service.py` 兼容壳，并完成 Central main/queue 回归。
- 阶段 7：补齐共享详情弹层、工作台壳层、MyFavorites 组合流和 Dashboard
  App 基线；剩余缺口转入活跃文档的“当前缺口”。

## 历史质量快照

- 2026-06-03：未发现 Critical 级架构阻断；Worker 编排、Wan22 拼接、
  Gallery 响应组装、Bot 进度监控和前端 composable 被列为后续治理项。
- 2026-06-18：当次静态报告未发现 Critical/High 阻断；报告保存在
  `logs/code_analysis_report_20260618_0306.md`。

## 当时的收尾口径

第一批要求建立热点清单、改动到最小测试组映射，并区分任务主链与非任务热点。
第二批要求把共享详情弹层、工作台、Dashboard App 和关键组合流纳入 focused
tests，并显式记录 workflow path 尚未覆盖的缺口。

当时的后续建议是固化 required checks、补齐 workflow path 与热点清单差异，
并按风险增加跨页面端到端回归。这些建议是否仍适用，应以活跃热点文档和当前
workflow 为准。
