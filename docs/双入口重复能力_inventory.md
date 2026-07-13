# 双入口重复能力 Inventory

更新时间: 2026-05-25

## 1. 目的

本文档作为 P0-3 的独立交付物，记录 `backend/app` 与 `src/web_api` 之间当前存在的重复能力、部分重叠能力与历史兼容残留，为后续 P1/P2 的收口提供挂载依据。

## 2. 分类标准

- **完全重复**：两个入口长期暴露了相同性质、面向相同调用方的能力。
- **部分重复**：领域相邻，但面向的调用方或语义边界不同，需保留双入口但要写清职责。
- **历史兼容残留**：旧路径仍存在，但不应继续扩张，后续应继续收口或标记兼容边界。

## 3. Inventory 表

| 能力名 | 当前文件 | 当前调用方 | 类型 | 目标归属 | 迁移阶段 | 兼容清理条件 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 任务创建接口 | `backend/app/main.py` 的 workflow/T2I 创建口；`src/web_api/routers/tasks.py` 的 `/api/tasks/generate` | Worker 执行面上游 / Web 用户侧 | 部分重复 | Web 用户入口归 `src/web_api`；中控专用创建归 `backend/app` | 已分流，继续固化 | 当所有用户侧创建语义都只经 `src/web_api`，且中控口仅保留执行面专用场景 |
| 任务取消接口 | `backend/app/main.py` 的 `DELETE /api/tasks/{task_id}`；`src/web_api/routers/tasks.py` 的用户取消口 | backend 执行面 / Web 用户侧 | 部分重复 | 用户取消归 `src/web_api`；backend best-effort cancel 归 `backend/app` | 已分层，继续文档化 | 当文档与调用方都明确区分 `registry_task_id` 与 `backend_task_id` |
| 任务状态/结果查询 | `backend/app/main_status_result_routes.py`；`src/web_api/services/task_stream_api_service.py`、`task_result_service.py` | backend 状态视图 / Web 用户态 | 部分重复 | backend 执行态归 `backend/app`；用户态 stream/result/history 归 `src/web_api` | 已分层 | 当前端与 Web API 不再直接依赖 backend 口的用户语义 |
| 系统状态与队列/worker 视图 | `backend/app/main.py`、`queue_manager.py`；Dashboard backend `stats/system/workers` | 管理端 / 运维 | 部分重复 | 执行态底座归 `backend/app`；管理视图编排归 dashboard backend | 持续维护 | 当 dashboard 全部改为消费稳定管理 service，而不再重复定义底层语义 |
| T2I request prepare / submit wiring | `backend/app/main_t2i_wiring.py`；`src/web_api` 中用户任务提交链 | 中控专用上游 / Web 用户侧 | 历史兼容残留 | 中控专用仍在 `backend/app`；用户主链在 `src/web_api` | 已分流 | 当中控 workflow 专用口不再被误用为通用用户创建口 |
| 任务运行态恢复与 fallback 叙事 | backend not-found/result 口；Web `task_stream_api_service` / `task_stream_service` | backend / 前端 | 部分重复 | 用户态 fallback 归 `src/web_api` | 已完成主要收口 | 当所有用户态恢复逻辑都只通过 Web BFF 暴露 |
| 认证与鉴权 | `backend/app` 的 token 校验；`src/web_api` 的 JWT / Telegram / password auth | Agent/worker / Web 用户 | 部分重复 | Agent token 留在 `backend/app`；用户认证留在 `src/web_api` | 已分流 | 当后续文档不再把它们视为同一认证面 |

## 4. 当前判断

### 4.1 当前没有必要强行合并的能力

以下能力属于“看起来相似，但本质调用方不同”，不建议为了表面统一而硬合并：

- backend best-effort cancel 与 Web 用户取消
- backend 状态/结果口 与 Web stream/result/history fallback
- Agent token 鉴权 与 Web JWT/Telegram/password 鉴权

### 4.2 当前最需要继续收口的残留

- 文档与评审语境里仍会把 `backend/app` 误当成普通 Web/BFF 入口。
- 中控 workflow/T2I 专用创建口容易被误解为“全站主任务创建 API”。
- 缺少统一 inventory，导致后续改动难以快速判断“这是继续分流，还是在制造重复能力”。

## 5. 与后续任务的挂载关系

- P1-1 调用图与 seam 清单，应引用本文中的“任务创建 / 取消 / 状态结果”三项。
- P1-6 异常语义统一，应优先检查“任务取消接口”“任务状态/结果查询”两项。
- P2-5 Core 依赖审计，不直接改本表，但如改变入口归属，应同步更新本文。

## 6. 维护原则

- 新发现的双入口重叠点，必须先写入本 inventory，再决定是否迁移。
- 若某项已彻底完成迁移，应在“兼容清理条件”达成后把该项改为“已退出”。
- 本文只记录入口级能力重叠，不替代更细粒度的函数 seam 清单。
