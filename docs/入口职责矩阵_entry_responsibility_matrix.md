# 双入口职责矩阵

更新时间: 2026-06-10

## 1. 目的
本文档用于明确 `backend/app` 与 `src/web_api` 的长期职责边界，作为 P0-1 的独立交付物。目标不是重复系统总览，而是提供后续评审可以直接引用的模块级职责矩阵。

## 2. 判定原则
- `src/web_api` 是主 Web/BFF 入口：承接用户侧认证、任务提交、历史、广场、用户中心、支付展示面接口。
- `backend/app` 是执行面 / 中控入口：承接 QueueManager、Worker 通信、backend 执行态、系统任务视图与中控专用接口。
- 新增 Web/BFF 用户能力默认进入 `src/web_api`；只有确属中控执行面或 worker 协议的能力才进入 `backend/app`。
- 两个入口若暂时存在重叠能力，必须在 inventory 中标明其性质与迁移条件。

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
- 不要让两个入口都定义同一用户功能的长期主路径；如确有兼容残留，必须写入 inventory。

### 4.4 跨入口 provider 注册补充
- provider 注册由应用入口负责，core 模块不在 import 时自动装配。
- `src/web_api/main.py`、`src/bot_main.py`、`src/payment_api_server.py` 和 `dashboard/backend/main.py` 只要会调用 billing core，都必须调用 `ensure_billing_core_providers_registered()`。
- Dashboard Backend 的退款、强制终止、资产调整等管理接口会进入 billing core；不能只注册 task core provider。

## 5. 冻结规则建议
在 P0-2 完成前，评审时可先采用以下临时规则：
- 新增用户面 API 默认进入 `src/web_api`。
- `backend/app` 只允许：
  - 修复中控执行面问题
  - 中控职责内的小范围重构
  - 既有中控接口的 wiring 收口
- 若需要在 `backend/app` 新增接口，必须先说明它为什么不属于 `src/web_api`。

## 6. 后续动作
- 与《双入口重复能力 inventory》配套使用。
- 后续若补 `backend/app` 冻结区规则，可直接引用本矩阵的“目标归属”列。
