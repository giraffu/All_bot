# 任务黄金路径回归清单

## 1. 目标

本清单用于保护 AllBot 任务主链路在重构期间的外部行为不漂移，覆盖以下高风险区域：

- `src/services/task_service.py` 及其 facade/support/entrypoint 子模块
- `backend/app/main.py` 的中控任务创建与同步等待入口
- `backend/app/queue_manager.py` 的排队、取消、zombie 清理与 worker 视图
- `src/web_api/routers/tasks.py` 及对应 API service / SSE stream 路径
- `src/core/task_core.py` 的提交 Saga 补偿与并发锁释放

本清单只关注“任务能否被正确提交、排队、取消、完成、回查与恢复”，不扩展到支付、安全、部署与前端页面视觉回归。

## 2. 适用时机

出现以下任一场景时，至少执行一次“最小必跑集”：

- 修改 `task_service`、`task_core`、`queue_manager`、`backend/app/main.py`
- 修改 `src/web_api/routers/tasks.py`、`task_stream_api_service.py`、`task_action_api_service.py`
- 修改任务状态字段、Pub/Sub 事件格式、取消语义、排队语义
- 修改 Telegram 任务完成消息、结果发送、cleanup 或 caption 组装逻辑

出现以下任一场景时，执行“完整黄金路径集”：

- 调整任务提交骨架或 facade 结构
- 调整任务状态机、zombie 清理、队列过滤、worker 视图
- 调整中控同步任务等待逻辑
- 调整历史兜底、SSE terminal payload、取消接口异常映射

## 3. 热点文件

- `src/services/task_service.py`
- `src/services/task_service_completion.py`
- `src/services/task_service_support.py`
- `src/services/task_service_message_support.py`
- `src/services/task_service_entrypoint_support.py`
- `backend/app/main.py`
- `backend/app/queue_manager.py`
- `src/web_api/routers/tasks.py`
- `src/web_api/services/task_stream_api_service.py`
- `src/web_api/services/task_action_api_service.py`
- `src/core/task_core.py`

## 4. 最小必跑集

适用于低风险重构后的快速确认，目标是在几分钟内确认黄金路径没有明显漂移。

```bash
pytest \
  tests/backend/test_main_helpers.py \
  tests/backend/test_queue_manager.py \
  tests/web_api/test_tasks_action_api_service.py \
  tests/web_api/test_tasks_generate.py \
  tests/web_api/test_tasks_stream.py \
  tests/services/test_task_service_completion.py \
  tests/services/test_task_service_support.py \
  tests/services/test_task_service_message_support.py \
  tests/services/test_task_service_entrypoint_support.py
```

## 5. 完整黄金路径集

适用于修改任务提交、状态机、同步等待或补偿逻辑后的完整回归。

```bash
pytest \
  tests/integration/test_saga_and_queue.py \
  tests/backend/test_main_helpers.py \
  tests/backend/test_queue_manager.py \
  tests/web_api/test_tasks_action_api_service.py \
  tests/web_api/test_tasks_generate.py \
  tests/web_api/test_tasks_stream.py \
  tests/services/test_task_service_completion.py \
  tests/services/test_task_service_support.py \
  tests/services/test_task_service_message_support.py \
  tests/services/test_task_service_entrypoint_support.py
```

## 6. 检查项

### 6.1 提交与补偿

- [ ] `task_core` 提交失败时会退款并释放并发锁
- [ ] 中控入队接口必须由外部预生成 `task_id`
- [ ] 中控同步任务必须先订阅 `comfy:task_events:{task_id}`，再入队，再等待
- [ ] 常规 `create_*_task` 路由仍统一通过任务类型注册表入队

对应测试：

- `tests/integration/test_saga_and_queue.py`
- `tests/backend/test_main_helpers.py`

### 6.2 中控同步 T2I 路径

- [ ] prompt 校验失败仍返回 `400`
- [ ] body 内的 priority 继续覆盖 query priority
- [ ] 同步模式下若任务已终态，仍能 immediate-return
- [ ] 同步等待超时仍返回 `504`
- [ ] enqueue 异常仍统一映射为 `500`

对应测试：

- `tests/backend/test_main_helpers.py`

### 6.3 QueueManager 状态机

- [ ] `dequeue_task()` 默认取最前任务
- [ ] `dequeue_task(allowed_types=...)` 只取允许类型
- [ ] 取出任务后状态改为 `running`，并写 heartbeat
- [ ] `cancel_task()` 对 `pending` 任务直接取消并发布事件
- [ ] `cancel_task()` 对 `running` 任务写入 `cancel_requested`
- [ ] `cancel_task()` 对终态任务返回 `not_cancellable`
- [ ] `check_zombie_tasks()` 会失败无 heartbeat 的运行任务
- [ ] `check_zombie_tasks()` 不误杀仍有 heartbeat 的运行任务
- [ ] `get_queue_metrics_by_type()` 继续统计已知和未知类型
- [ ] `get_all_workers()` 继续补齐当前任务详情
- [ ] `get_active_workers_count()` 只统计 agent heartbeat key

对应测试：

- `tests/backend/test_queue_manager.py`

### 6.4 Web API 任务入口

- [ ] `/tasks/generate` 成功时仍返回提交结果 DTO
- [ ] `/tasks/generate` 继续映射 `429 / 402 / 400 / 500`
- [ ] `/tasks/cancel/{task_id}` 继续返回统一 success shape
- [ ] router 仍保持 passthrough，不重新堆业务编排

对应测试：

- `tests/web_api/test_tasks_action_api_service.py`
- `tests/web_api/test_tasks_generate.py`

### 6.5 SSE 与历史兜底

- [ ] terminal backend 状态仍映射为 Web 侧 success/failed payload
- [ ] 历史存在时，not-found 仍回 success fallback
- [ ] 历史缺失时，not-found 仍回 failed fallback
- [ ] 非本人任务仍返回 `404`
- [ ] stream router 继续只做 service 转发

对应测试：

- `tests/web_api/test_tasks_stream.py`

### 6.6 Telegram TaskService 主链路

- [ ] completion 阶段在 metadata 探测失败时仍不破坏成功链路
- [ ] 下载与落库后仍保留 width/height/duration 等回写口径
- [ ] 结果 reply markup 仍会注入投稿按钮
- [ ] 自定义视频非法分辨率/时长组合仍按既有规则降级
- [ ] 状态消息、caption、display mode、entrypoint inputs 等 support helper 输出不漂移

对应测试：

- `tests/services/test_task_service_completion.py`
- `tests/services/test_task_service_support.py`
- `tests/services/test_task_service_message_support.py`
- `tests/services/test_task_service_entrypoint_support.py`

## 7. 手工抽查点

当自动化通过，但本轮改动碰到任务入口或状态同步时，建议再手工抽查以下 4 项：

1. 异步任务创建后能返回 `task_id`
2. 同步 T2I 路径在成功、失败、超时三种分支下口径正确
3. 运行中任务取消后，前端或 Bot 侧仍能看到“已请求取消”状态
4. 任务完成后，历史/结果回查与 SSE terminal payload 一致

## 8. 执行建议

- 改 `task_service` facade/support：先跑“最小必跑集”
- 改 `queue_manager`、`backend/app/main.py`、`task_core`：直接跑“完整黄金路径集”
- 改 `tasks.py` router/service：至少跑 Web API 相关 3 组测试，再视影响补全量
- 若同时需要判断“改哪类热点文件该跑哪组测试”，配合 `docs/子模块_热点文件门禁与回归触发规则_hotspot_guardrails.md` 一起使用

## 9. 收口原则

- 新增任务功能时，优先把测试加到现有黄金路径文件，而不是再散落新入口
- 新增 helper 时，先补 focused test，再移动主流程代码
- 若本清单中的任一检查项失效，应先补测试或更新清单，再继续重构
