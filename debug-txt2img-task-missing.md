# Debug Session: txt2img-task-missing [OPEN]

## 症状
- 测试 mini app 中提交文生图后，结果面板显示“任务不存在或无权限”。

## 期望
- 文生图任务提交后应进入统一任务流，SSE/结果接口可正常查询到任务并返回图片结果。

## 当前假设
- H1: Web 前端提交成功后拿到的 `task_id` 与后端实际登记/返回的任务 ID 不一致，导致后续查询命中不存在。
- H2: `txt2img` 走 legacy `t2i-pornmaster-turbo` 时返回了新的 backend task id，但统一主链仍按旧 registry task id 查询，产生双 ID 断链。
- H3: Web 侧 SSE / result 接口在归属校验时拿不到对应测试用户的任务记录，因此被映射成“任务不存在或无权限”。
- H4: legacy t2i 任务没有按统一监控链持久化/注册，导致提交后很快从运行态视角变成 not found。
- H5: 测试环境 Web / Bot / 中控 仍存在入口或缓存错位，前端打到的接口和当前部署代码不一致。

## 已知环境
- 用户在测试 mini app 中复现。
- 文生图入口刚接入 Web，并桥接 legacy `t2i-pornmaster-turbo`。
- 测试 worker `agent1` 已承接 `t2i-pornmaster-turbo`。

## 下一步
- [已完成] 检查 `web-api-test`、`central-api-test`、`comfy-agent-test-1`、前端网络日志。
- [已完成] 对照统一任务主链的 registry/backend 双 ID 语义，确认发生 ID 断链。

## 证据
- `POST /api/tasks/generate` 后，legacy t2i 返回 backend 任务 ID `5673ddb2-...`。
- Web 任务主链对外返回 registry 任务 ID `dae08f0f-...`。
- `GET /api/tasks/dae08.../stream` 建立后，Web API 内部错误轮询了 `/status/dae08...` 并收到 `404 Not Found`。
- 同一次任务最终仍以 registry 任务 ID `dae08...` 成功写入 history，说明任务本身成功，失败点在 Web stream 跟踪层。
- 随后浏览器网络证据显示：悬浮球 `/api/tasks/{id}/result` 返回的是 `http://192.168.1.115:9000/...png` 这类 MinIO 内网预签名地址；而历史页展示使用的是 `https://r2-test.aivison.it.com/history/{task_id}/original.png`，因此历史可见、即时预览不可见。

## 已确认 / 已排除
- H1: 部分成立，但根因不是前端显示错 ID，而是 stream 内部错误使用 registry ID 查 backend 状态。
- H2: 已确认。legacy `t2i` 的 backend task id 与 Web 主链 registry task id 发生双 ID 断链。
- H3: 已排除。任务最终成功按当前用户写入 history，不是归属校验问题。
- H4: 已排除。legacy t2i 结果可以被统一持久化，只是 stream 查询错了运行时 ID。
- H5: 已排除。本次复现使用的测试站/测试 Bot 已在正确测试环境。

## 修复
- `task_stream_api_service` 现在从 active task 中提取 `backend_task_id`，作为运行时跟踪 ID。
- `task_stream_service` 对外仍维持 registry `task_id`，但内部状态轮询与 Redis Pub/Sub 订阅改用 `runtime_task_id`（即 backend task id）。
- `task_result_service` 对 `source=web` 的结果不再下发 MinIO 内网预签名地址，而是优先等待测试 R2 公网对象就绪；未就绪时返回 `pending_result`，让前端继续轮询，待 `history/{task_id}/original.*` 可访问后再返回成功结果 URL。

## 验证
- `pytest -q tests/web_api/test_tasks_stream.py` 通过。
- `pytest -q tests/web_api/test_tasks_result.py tests/web_api/test_tasks_stream.py` 通过。
