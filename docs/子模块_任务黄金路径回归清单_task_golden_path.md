# 任务黄金路径回归清单

## 1. 目标
本清单用于保护 AllBot 任务主链路在重构期间的外部行为不漂移，覆盖以下高风险区域：

- Bot entrypoint / flow 子模块（已不再经过 `src/services/bot_task_service.py` compat 壳）
- `backend/app/main.py` 与 `backend/app/main_t2i_wiring.py` 的中控任务创建入口
- `backend/app/queue_manager.py` 的排队、取消、zombie 清理与 worker 视图
- `src/web_api/routers/tasks.py` 及对应 API service / SSE stream 路径
- `src/core/task_core.py` facade 以及 provider / default dependencies / submission / web-monitor / runtime 子模块

本清单只关注“任务能否被正确提交、排队、取消、完成、回查与恢复”，不扩展到支付、安全、部署与前端视觉回归。

## 2. 适用时机
出现以下任一场景时，至少执行一次“最小必跑集”：

- 修改 `task_service_flow`、Bot entrypoint
- 修改 `task_core.py`、`task_core_service_providers.py`、`task_core_default_dependencies.py`、`task_core_submission.py`、`src/services/task_web_side_effects.py`、`src/services/task_web_lifecycle_monitor.py`、`src/services/task_web_terminal_finalization.py`、`task_core_runtime.py`
- 修改 `backend/app/main.py`、`backend/app/main_t2i_wiring.py`、`queue_manager.py`
- 修改 `src/web_api/routers/tasks.py`、`task_submission_service.py`、`task_runtime_api_service.py`、`task_result_service.py`、`task_stream_api_service.py`、`task_action_api_service.py`
- 修改任务状态字段、not-found fallback、取消语义、排队语义、双 ID 语义

出现以下任一场景时，执行“完整黄金路径集”：

- 调整任务提交 facade 或 provider/dependency 装配结构
- 调整任务状态机、僵尸任务清理、队列过滤、worker 视图
- 调整同步 T2I 等待逻辑或 T2I wiring/use-case 分层
- 调整历史兜底、SSE terminal payload、取消接口异常映射
- 调整 Bot `run_bot_task_application(...)` 五段式上下文契约

## 3. 热点文件
- `src/services/task_service_entrypoints_video.py`
- `src/services/task_service_flow.py`
- `src/services/task_service_completion.py`
- `src/services/task_service_message_support.py`
- `src/services/task_service_entrypoints_generation.py`
- `src/services/task_service_entrypoints_specialized.py`
- `src/services/task_service_entrypoints_video.py`
- `backend/app/main.py`
- `backend/app/main_t2i_wiring.py`
- `backend/app/queue_manager.py`
- `src/web_api/routers/tasks.py`
- `src/web_api/services/task_submission_service.py`
- `src/web_api/services/task_runtime_api_service.py`
- `src/web_api/services/task_result_service.py`
- `src/web_api/services/task_stream_api_service.py`
- `src/web_api/services/task_action_api_service.py`
- `src/web_api/services/task_stream_service.py`
- `src/core/task_core.py`
- `src/core/task_core_service_providers.py`
- `src/core/task_core_default_dependencies.py`
- `src/core/task_core_submission.py`
- `src/services/task_web_side_effects.py`
- `src/services/task_web_lifecycle_monitor.py`
- `src/services/task_web_terminal_finalization.py`
- `src/core/task_core_runtime.py`

## 4. 最小必跑集
适用于低风险重构后的快速确认，目标是在几分钟内确认黄金路径没有明显漂移。

```bash
pytest   tests/backend/test_main_helpers.py   tests/backend/test_queue_manager.py   tests/web_api/test_tasks_action_api_service.py   tests/web_api/test_tasks_generate.py   tests/web_api/test_tasks_stream.py   tests/web_api/test_task_runtime_api_service.py   tests/services/test_task_service_flow.py   tests/services/test_task_service_completion.py   tests/services/test_task_service_message_support.py
```

## 5. 完整黄金路径集
适用于修改任务提交、状态机、同步等待、not-found fallback 或补偿逻辑后的完整回归。

```bash
pytest   tests/integration/test_saga_and_queue.py   tests/backend/test_main_helpers.py   tests/backend/test_queue_manager.py   tests/web_api/test_tasks_action_api_service.py   tests/web_api/test_tasks_generate.py   tests/web_api/test_tasks_stream.py   tests/web_api/test_task_runtime_api_service.py   tests/services/test_task_service_flow.py   tests/services/test_task_service_completion.py   tests/services/test_task_service_message_support.py
```

## 6. 检查项
### 6.1 提交与补偿
- [ ] `task_core` 提交失败时会退款并释放并发锁
- [ ] facade 默认路径与显式 `dependencies` 注入路径口径一致
- [ ] 中控同步任务必须先订阅，再入队，再等待
- [ ] `registry_task_id` 与 `backend_task_id` 的返回与后续流转不混淆

对应测试：
- `tests/integration/test_saga_and_queue.py`
- `tests/backend/test_main_helpers.py`
- `tests/core/test_task_core_dependencies.py`

### 6.2 中控同步 T2I 路径
- [ ] prompt 校验失败仍返回 `400`
- [ ] body 内 `priority` 继续覆盖 query priority
- [ ] T2I request prepare / submit / status build 已由 wiring/use-case 层统一收口
- [ ] 同步模式下若任务已终态，仍能 immediate-return
- [ ] 同步等待超时仍返回 `504`

对应测试：
- `tests/backend/test_main_helpers.py`

### 6.3 QueueManager 状态机
- [ ] `dequeue_task()` 默认取最前任务
- [ ] `dequeue_task(allowed_types=...)` 只取允许类型
- [ ] 取出任务后状态改为 `running`，并写 heartbeat
- [ ] `cancel_task()` 对 `pending` / `running` / 终态任务口径不漂移
- [ ] zombie 清理不误杀仍活跃的运行任务
- [ ] worker 视图与 metrics 仍能补齐任务详情

对应测试：
- `tests/backend/test_queue_manager.py`

### 6.4 Web API 任务入口
- [ ] `/tasks/generate` 成功时仍返回统一提交 DTO
- [ ] `/tasks/generate` 继续映射 `429 / 402 / 400 / 500`
- [ ] `/tasks/cancel/{task_id}` 继续返回统一 success shape
- [ ] router 仍保持薄壳，只做 service 转发

对应测试：
- `tests/web_api/test_tasks_action_api_service.py`
- `tests/web_api/test_tasks_generate.py`

### 6.5 SSE 与历史兜底
- [ ] terminal backend 状态仍映射为 Web success/failed payload
- [ ] 历史存在时，not-found 仍回 success fallback
- [ ] 历史缺失时，not-found 仍回 failed fallback
- [ ] 非本人任务仍返回 `404`
- [ ] stream router 与 api service 继续保持 thin wrapper

对应测试：
- `tests/web_api/test_tasks_stream.py`
- `tests/web_api/test_task_runtime_api_service.py`

### 6.6 Telegram Bot Task 主链路
- [ ] `run_bot_task_application(...)` 的 request / presentation / billing / failure / cleanup 五段式上下文装配不漂移
- [ ] 取消态仍通过 `BotTaskCancelled` 收口，不回退为字符串 sentinel
- [ ] completion 阶段在 metadata 探测失败时仍不破坏成功链路
- [ ] 结果 reply markup、caption、display mode、status message 清理逻辑不漂移
- [ ] Bot entrypoint 与 thin compat facade 边界保持稳定

对应测试：
- `tests/services/test_task_service_flow.py`
- `tests/services/test_task_service_completion.py`
- `tests/services/test_task_service_message_support.py`

## 7. 手工抽查点
当自动化通过，但本轮改动碰到任务入口或状态同步时，建议再手工抽查以下 4 项：

1. 异步任务创建后能返回正确的 `registry_task_id`
2. 同步 T2I 路径在成功、失败、超时三种分支下口径正确
3. 运行中任务取消后，前端或 Bot 侧仍能看到“已请求取消”或明确终态
4. 任务完成后，历史/结果回查与 SSE terminal payload 一致

## 8. 执行建议
- 改 Bot flow / entrypoints：先跑最小必跑集，再补 `tests/services/test_task_service_flow.py`
- 改 `task_core` facade / provider / dependencies / monitor：直接跑完整黄金路径集
- 改 `queue_manager`、`backend/app/main.py`、`main_t2i_wiring.py`：直接跑完整黄金路径集
- 改 `tasks.py` router/service：至少跑 Web API 相关 3 组测试，再视影响补全量
- 若同时需要判断热点文件应该触发哪组回归，配合 `docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md` 一起使用

## 9. 收口原则
- 新增任务功能时，优先把测试并入现有黄金路径集，而不是再散落新的入口测试清单
- 新增 helper 或 seam 时，优先提供 focused tests 和显式依赖注入契约
- 文档中的入口函数、fallback 语义、双 ID 口径、Bot 五段式上下文必须与代码保持一致
- 若本清单中的任一检查项失效，应先补测试或更新清单，再继续重构
