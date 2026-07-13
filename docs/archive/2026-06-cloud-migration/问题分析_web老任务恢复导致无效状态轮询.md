# Web 老任务恢复导致无效状态轮询问题分析与现状收口版

## 1. 文档目的

本文用于记录该问题在最新代码下的真实结论，替换旧口径中已经失效的判断，并明确当前服务端与前端各自的职责边界。

## 2. 当前结论

该问题对应的核心服务端收口已经完成，当前代码口径应表述为：

1. Web 端对运行态与结果恢复链路已经分流。
2. `/api/tasks/{task_id}/stream` 已把运行态 not-found 收口为明确 fallback / terminal 语义。
3. 旧版“老任务会持续制造无效 SSE 404 轮询”的表述不再适合作为当前主现象。
4. 剩余风险主要在前端本地 `active_tasks` 生命周期治理，而不是服务端 stream 实现缺终止条件。

## 3. 已完成的服务端收口

### 3.1 Stream not-found 终止语义

当前 `task_stream_service` 已显式处理运行态 not-found，并结合历史记录做 fallback：

- 历史存在：返回 success fallback
- 历史缺失：返回 failed fallback
- 非本人任务：继续保持 404

因此，服务端不会再把 not-found 当成“继续无限重试”的模糊状态。

### 3.2 历史恢复与运行态分流

当前 Web 恢复链路已明确区分：

- 真正仍在运行的任务：恢复 SSE / stream
- `awaitingResult` 或结果回查场景：走 result/history 路径
- 历史已落库任务：优先按历史/结果语义处理，而不是重新假装进入运行态

## 4. 旧结论中应废弃的内容

以下口径已不再代表当前代码现状：

- “`success && !resultUrl` 会被错误恢复为 SSE 主路径”
- “stream 404 没有终止条件，当前线上噪音主因在服务端”
- “优先修改 SSE 循环重试逻辑即可解决主问题”

这些判断在旧实现阶段可能成立，但对当前代码已失真。

## 5. 当前真实风险点

在最新代码下，风险主要转移为前端本地状态治理：

- 本地 `active_tasks` 若长期残留陈旧 `pending/running` 状态，页面刷新后仍可能尝试恢复监听
- 虽然服务端已能快速 fallback / 终止，但前端若不清理陈旧任务，仍会出现重复恢复尝试与 UI 噪音

因此，后续优化优先级应为：

1. 前端本地任务 TTL / 生命周期治理
2. 任务完成后本地状态的及时收口与悬浮球清理
3. 如再观察到异常，请优先排查前端状态持久化，而不是先怀疑 backend `/status/{task_id}`

## 6. backend_api 的职责边界

`backend_api /status/{task_id}` 仍只表达“当前运行态任务”语义：

- 运行态存在：返回状态
- 运行态不存在：返回 not-found

它不负责历史库查询，也不应为了兼容旧前端状态而扩展成“历史结果查询接口”。

## 7. 建议的后续维护口径

- 若再出现类似日志噪音，先验证是否有前端陈旧本地任务残留
- 若修改 `task_stream_service.py`、`task_stream_api_service.py`、`test_tasks_stream.py`，必须同步复核本问题文档
- 服务端 stream/history fallback 现已属于既有契约，后续重构不应回退为“吞掉 not-found 后继续无界轮询”

## 8. 对应测试与回归建议

建议将以下测试视为该问题的回归守护：

- `tests/web_api/test_tasks_stream.py`
- `tests/web_api/test_task_runtime_api_service.py`
- 与前端本地任务恢复相关的 flow / store 测试（若后续补齐）

## 9. 当前状态结论

当前知识口径应更新为：

- 该问题的服务端主因已收口
- stream/history 双路径当前语义清晰
- 剩余工作重心在前端本地任务生命周期，而不是继续反复修补服务端 404 处理
