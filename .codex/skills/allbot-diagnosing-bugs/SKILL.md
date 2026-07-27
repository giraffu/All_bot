---
name: allbot-diagnosing-bugs
description: "AllBot 专用 bug 诊断闭环。用户报告线上/测试环境失败、慢、卡住、异常、任务不可见、支付/鉴权异常、R2/RunPod/Worker/FSM 问题，或要求 debug/diagnose/troubleshoot 时使用；需要先建立可复现反馈环，再做假设、插桩、修复与回归。"
---

# AllBot Bug 诊断闭环

先从 `AGENTS.md` 选择故障所属领域 Skill，再按该 Skill 路由读取对应
`docs/子模块_*.md`。任务/队列问题优先读取
`docs/子模块_生成任务全链路_task_full_chain.md`，发布/环境问题优先读取
`docs/子模块_运维指南与容器管理_ops_deployment.md`；不要预加载全部文档。

本技能把“先构造反馈环”作为排障主纪律。日志监控可先用 `ops-log-monitor` 采集事实；一旦进入代码修复或根因验证，必须用本技能把问题收束到可复现、可回归的信号。

## 1. 先建立反馈环
- 先找一个能触发用户真实症状的命令或脚本，再深入猜原因。
- 优先顺序：focused test、API/curl 脚本、任务链路 replay、Playwright、worker/ComfyUI 最小任务、日志 trace replay、临时 harness。
- AllBot 常见反馈环：
  - Web/API：pytest 覆盖 router/service/presenter，或 curl 测 `/api/tasks/generate`、`/result`、Gallery/apply-context。
  - 任务链路：用云测试或本地 mock seam 验证 `process_and_submit_task(...)`、Web finalizer、Central queue/worker 回报。
  - Telegram FSM：用 handler focused tests 覆盖 callback 应答、全局菜单退出、临时文件清理。
  - Worker/workflow：用 workflow mapping 校验、agent focused tests、目标 ComfyUI `/object_info` 和最小 smoke 任务。
  - R2/媒体：用只读审计或短签/HEAD 快探测复现空白、pending_result、legacy URL 回退。
- 完成标准：能说清一个已运行过的命令，它能稳定暴露该 bug 或以足够高概率复现该 bug。

## 2. 复现并最小化
- 先确认反馈环命中的就是用户描述的症状，不是旁边的另一个错误。
- 逐项删输入、配置、调用层和环境依赖；每删一次重新跑反馈环。
- 非确定性问题要提高复现率：循环触发、并发触发、固定时间/随机种子、缩小网络或对象存储变量。
- 如果确实无法建立反馈环，停止猜测并向用户要可复现环境、HAR/日志/录屏/任务 ID 或临时观测授权。

## 3. 排列假设
- 一次列出 3 到 5 个可证伪假设，并按可能性排序。
- 每个假设必须有预测：如果它是根因，哪条日志、哪项状态、哪个测试或哪个参数变化会让症状消失、加重或转移。
- AllBot 排障不要只盯单层：先判定问题位于前端提交、Web API、task core、Central、worker、ComfyUI、对象存储、支付通道还是外部网络。

## 4. 精准插桩
- 一次只验证一个假设。
- 优先用现有 trace id、structured log、pytest assertion、DB/Redis 只读查询和目标端点测量；不要“到处加日志再 grep”。
- 临时 debug log 必须带唯一前缀，例如 `[DEBUG-20260621-a]`，结束前用 `rg` 清掉。
- 性能问题先分段测量：云内 API、公网 API、Pages、R2/短签、Central Redis 队列、GPU 利用率、ComfyUI queue、前端串行请求。

## 5. 修复与回归
- 有正确 seam 时，先把最小复现固化成失败测试，再改代码。
- 正确 seam 应匹配真实 bug 发生处：public API、facade、provider/dependencies seam、FSM handler、worker phase helper 或 presenter。
- 没有正确 seam 时，记录这是架构问题；修复后用 `allbot-codebase-design` 判断是否需要加深模块或移动 seam。
- 修复后必须重跑：最小回归测试、原始反馈环、相关黄金路径或目标环境 smoke。

## 6. 收尾
- 删除临时 harness、临时日志和 `[DEBUG-...]` 插桩。
- 总结中写清：反馈环命令、最终根因、修复面、已跑验证、残余风险。
- 涉及任务、计费、Gallery、TG、Comfy、部署等业务边界时，同步加载对应 AllBot 业务技能；本技能只提供诊断流程，不替代业务红线。
