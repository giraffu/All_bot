---
name: allbot-system-acceptance
description: 规划或执行 AllBot 大更新后的真实用户旅程全量验收，以及小更新后的局部验收。用户要求全面测试、端到端验收、模拟用户提交、发布后 smoke，或按 Web、Bot、任务、计费、Gallery、媒体、Worker 等改动做局部回归时使用；不是单元测试或压力测试。
---

# AllBot 系统用户验收

从真实入口提交真实任务，验证身份、执行、计费、媒体和通知闭环；不能用测试代码代替用户结果。

## 选择范围

- 大更新或影响不明：`FULL-LITE`。
- 小更新：`LOCAL-SLICE`，按行为、状态 owner、副作用和 profile 选切片。
- 发布后快速确认：`CORE-SPINE`，只证明身份、便宜提交、终态、结果和账本主干。
- 只要求计划时，不连接环境或提交任务。

切片、选例、顺序和证据读取
`docs/子模块_任务黄金路径回归清单_task_golden_path.md`。边界不清再读
`docs/system_module_inventory.md`，并只加载所选切片的领域 Skill。部署、配置、数据库、Cloudflare、支付或 GPU/LAN mutation 必须叠加 `allbot-ops-deployment`；本 Skill 不授予变更权限。

## 执行纪律

1. 固定环境、Git SHA、artifact digest、入口、账号和切片。
2. 使用专用账号和小素材；串行跑最短样本并复用结果。
3. 高成本、真实支付、正式专属 Bot、归档恢复及可变管理操作默认 gated。
4. 从用户入口观察 Central、Worker、R2 与 History，不直写数据库、伪造终态或直调 Worker 冒充验收。
5. 状态只用 `pass`、`fail`、`blocked`、`not-applicable`；未执行不得记为通过。

身份串号、越权、重复任务/扣退款、success 后原件丢失、错误环境、意外支付或 test/prod Worker 混用时立即停止。生产、数据库、Cloudflare、GPU/LAN、支付和灾备仍需明确授权。

局部验收补齐上游身份、下游结果及计费/媒体副作用。改变双 ID、终态、扣退款、对象耐久语义或无法界定影响时升级为 `FULL-LITE`。

## 交付与最小验证

报告 release、模式、切片、资源、状态、脱敏证据、清理和残余风险。关键项失败、阻塞或 gated 时不得声称全面通过。

知识不新增可直接执行脚本。维护后用 Skill 校验器和知识质量检查器核对 frontmatter、路由、链接与体积。
