---
name: allbot-tdd
description: "AllBot 测试驱动开发纪律。用户要求 test-first、红绿重构、补回归测试、开发新功能、修 bug 并需要锁定行为时使用；强调通过 public facade/API/FSM/provider dependencies seam 做行为测试，一次一个 vertical slice。"
---

# AllBot 测试驱动开发

本技能用于让 AllBot 新功能和 bug 修复先有行为信号，再实现。它可与 `allbot-task-engine`、`allbot-billing-auth`、`allbot-gallery-storage`、`allbot-tg-fsm`、`allbot-comfy-models` 叠加使用。

## 1. 测什么
- 测行为，不测内部形状。测试名称应描述用户或系统能力，而不是私有函数名。
- 首选 public seam：
  - Web API：router/service/presenter 返回与副作用。
  - Task core：`TaskApplication.submit(command, policy, journal)`、monitor/finalizer、显式 `dependencies`；旧宽 facade 只用于兼容测试。
  - Billing：履约命令、账本/幂等/会员结算结果。
  - Gallery：apply-context、prompt unlock、互动并发、媒体 URL 策略。
  - TG FSM：入口 handler、callback route、全局菜单退出、临时文件清理。
  - Worker：阶段 helper、workflow mapping validation、结果物化/上报语义。
- 避免把模块级 monkeypatch 当主路径；项目已支持 provider/dependencies seam 时优先使用显式依赖注入。

## 2. 一次一个纵切
- 不要先写一批测试再集中实现。
- 循环方式：
  1. 写一个能失败的行为测试。
  2. 只写让它通过的最小实现。
  3. 跑相关测试确认变绿。
  4. 根据新学到的行为再写下一个测试。
- 每轮只新增一个清晰行为，避免测试幻想未来实现。

## 3. AllBot 测试选择
- 金钱、身份、幂等、退款、并发锁、双 ID、对象存储回退、workflow 映射、FSM callback 应答必须有 focused tests。
- 前端变更若涉及 Vue UI/交互，叠加 `vue-best-practices`；视觉验收叠加 `frontend-browser-preview`。
- 任务链路变更需要至少覆盖一个成功主链和一个失败/取消/补偿分支。
- 运维脚本或部署路径优先 dry-run/preflight 测试；生产 execute 需要用户明确确认，不因测试驱动而绕过部署红线。

## 4. 重构规则
- 只在绿色状态下重构。
- 重构目标是让模块更深、接口更小、测试更自然；若测试必须越过接口才能断言，先用 `allbot-codebase-design` 重新评估 seam。
- 重构后重跑当前 focused tests；触及热点链路时补跑对应黄金路径。

## 5. 每轮检查
- 测试是否通过 public seam 观察行为。
- 测试是否会在真实行为坏掉时失败。
- 是否避免了过度 mock 内部协作者。
- 实现是否只覆盖当前测试，没有预支未来功能。
- 涉及 docs/skills 语义变化时，是否调用 `allbot-kb-auto-updater` 同步知识库。
