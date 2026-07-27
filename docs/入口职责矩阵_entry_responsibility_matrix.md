# 双入口职责矩阵

## 1. 目的

本文档明确 `backend/app` 与 `src/web_api` 的长期职责，并合并仍需关注的双入口
重叠能力。已完成的旧 inventory 保存在 `docs/archive/`。

## 2. 判定原则

- `src/web_api` 是主 Web/BFF 入口：承接用户侧认证、任务提交、历史、广场、用户中心、支付展示面接口。
- `backend/app` 是执行面 / 中控入口：承接 QueueManager、Worker 通信、backend 执行态、系统任务视图与中控专用接口。
- 新增 Web/BFF 用户能力默认进入 `src/web_api`；只有确属中控执行面或 worker 协议的能力才进入 `backend/app`。
- 两个入口若暂时存在重叠能力，必须在本文标明性质与退出条件。

## 3. 入口职责矩阵

| 模块 | 当前职责 | 是否核心职责 | 目标归属 | 是否需要兼容保留 |
| :--- | :--- | :--- | :--- | :--- |
| `backend/app/main.py` | Central API 主入口，承接健康检查、系统状态、系统 worker 视图、少量 workflow 专用创建口与 backend cancel | 是 | `backend/app` | 是 |
| `backend/app/routers/agent.py` | Worker/Agent 拉取任务、回写状态、完成回调、heartbeat 协议 | 是 | `backend/app` | 是 |
| `backend/app/dependencies.py` | `Redis` 与 `QueueManager` 注入 | 是 | `backend/app` | 是 |
| `backend/app/main_t2i_wiring.py` | T2I request prepare/submit/status build 的中控侧 wiring | 是 | `backend/app` | 是 |
| `backend/app/main_simple_task_routes.py` | 中控简单任务路由注册 | 是 | `backend/app` | 是 |
| `backend/app/main_status_result_routes.py` | backend 结果/状态查询口注册 | 是 | `backend/app` | 是 |
| `backend/app/queue_manager.py` | pending/running 队列、worker 视图、取消、zombie/heartbeat 编排 | 是 | `backend/app` | 是 |
| `src/web_api/main.py` | Web BFF 主入口，承接生命周期、provider 注册、跨域、中间件与统一异常处理 | 是 | `src/web_api` | 是 |
| `paid_group_guard_bot/main.py` | 独立付费群审核 Bot 入口，处理目标群入群申请与轻量消息审核 | 是 | `paid_group_guard_bot` | 是 |
| `src/web_api/routers/auth.py` | Telegram/Web 登录、JWT 会话相关 API | 是 | `src/web_api` | 是 |
| `src/web_api/routers/tasks.py` | Web 用户侧任务提交、取消、stream/result/runtime 入口 | 是 | `src/web_api` | 是 |
| `src/web_api/routers/users.py` | 用户资料、偏好、历史、历史变更动作 | 是 | `src/web_api` | 是 |
| `src/web_api/routers/gallery.py` | 广场查询、详情、互动、模板应用上下文 | 是 | `src/web_api` | 是 |
| `src/web_api/routers/payment.py` | Web 支付展示面与支付结果交互口 | 是 | `src/web_api` | 是 |
| `src/web_api/routers/storage.py` | 用户侧上传/存储桥接接口 | 是 | `src/web_api` | 是 |
| `src/web_api/services/task_*` | Web 任务应用服务、stream/result/history fallback、异常映射 | 是 | `src/web_api` | 是 |
| `src/web_api/services/history_*` | 历史查询、投递到 Bot、HTTP 响应构造 | 是 | `src/web_api` | 是 |
| `src/web_api/services/auth_api_service.py` | Web 认证接口编排、密码登录与安全通知 | 是 | `src/web_api` | 是 |
| `src/web_api/services/gallery_*` | 广场查询、变更、评论、媒体解析、响应拼装 | 是 | `src/web_api` | 是 |

## 4. 入口边界说明

### 4.1 `backend/app` 应继续承接的能力

- Worker/Agent 协议与认证
- QueueManager、worker 视图、系统状态
- backend 执行态状态/结果口
- 中控侧 workflow 专用创建口与相关 wiring

### 4.2 `src/web_api` 应继续承接的能力

- 用户登录、JWT、会话与安全通知
- Web 用户发起的任务提交、取消、历史、结果、runtime stream
- 广场、收藏、评论、模板应用上下文
- 用户资料、偏好、账单、affiliate 兑换、支付展示面

### 4.3 明确不应继续扩张的方向

- 不要在 `backend/app` 新增普通 Web/BFF 用户功能。
- 不要让 `src/web_api` 直接承担 worker 协议、QueueManager 内部状态机或 backend 执行面职责。
- 不要让两个入口都定义同一用户功能的长期主路径；兼容残留写入本文。

### 4.4 跨入口 provider 注册补充

- provider 注册由应用入口负责，core 模块不在 import 时自动装配。
- `src/web_api/main.py`、`src/bot_main.py`、`src/payment_api_server.py` 和 `dashboard/backend/main.py` 只要会调用 billing core，都必须调用 `ensure_billing_core_providers_registered()`。
- Dashboard Backend 的退款、强制终止、资产调整等管理接口会进入 billing core；不能只注册 task core provider。
- `paid_group_guard_bot/main.py` 只读查询 `users` / `orders` 做付费群入群资格判断，并通过共享文件读取群管理配置、写入删除日志；不调用 billing core 履约或资产变更逻辑，因此不需要 billing provider 注册。

## 5. 当前重叠能力

| 能力 | 性质 | 稳定归属 | 保留条件 |
| --- | --- | --- | --- |
| 任务创建 | 调用方不同 | 用户入口归 Web；执行面专用创建归 Central | Central route 仅服务执行面协议 |
| 任务取消 | ID/权限不同 | 用户取消归 Web/core；backend best-effort cancel 归 Central | 文档与代码明确区分双 ID |
| 状态与结果 | 展示语义不同 | 用户 stream/result/history 归 Web；执行状态归 Central | Web 不直接暴露 backend 状态语义 |
| 系统状态 | 聚合层不同 | worker/queue 底座归 Central；管理展示归 Dashboard | Dashboard 只消费稳定管理 service |
| 鉴权 | 身份主体不同 | Agent token 归 Central；用户 JWT/TG/password 归 Web | 不抽象成一个宽泛 auth module |

这些能力“名称相似”不代表应该强行合并。新重叠点先判断调用方、ID、错误、
副作用和权限，再决定是合理 adapter 还是重复业务。

## 6. 评审规则

- 新增用户 API 默认进入 `src/web_api`。
- `backend/app` 新接口必须证明属于 Worker/Central 协议或执行状态。
- provider 由应用入口注册；core 不自动装配。
- 测试若必须跨入口 patch 私有函数，应先检查是否缺少公开 service/provider seam。
- 兼容层退出统一记录在 `docs/compat_seam_exit_table.md`。
