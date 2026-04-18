# 管理后台系统架构梳理 (Dashboard System)

该项目的管理后台（Dashboard）采用前后端分离的架构，用于管理员对整个修仙机器人的用户、数据、财务和素材进行全方位监控与管理。

后台系统与 Telegram Bot 机器人共享**同一个 PostgreSQL 数据库**和**同一个 MinIO 存储服务**。

---

## 1. 后端架构 (Backend)

后端采用了 **FastAPI** 框架，旨在提供高性能、异步的 RESTful API。

*   **入口文件**: `dashboard/backend/main.py`
*   **运行端口**: 默认 `8043` 端口（通过 Uvicorn 启动）
*   **数据库连接**: 复用了 Bot 项目下的 `src.database.core` (SQLAlchemy 异步会话)，直接读取和操作 `users`, `history`, `user_logs`, `orders`, `worker_logs`, `gallery_posts` 等核心表。

### 1.1 核心中间件与安全机制
*   **CORS**: 配置了跨域资源共享，允许前端应用访问。
*   **Auth Middleware**: 实现了一个自定义的 `check_auth_header` 中间件，除了 `/api/auth/login`、`/api/health` 和 `/api/status` 等公开接口外，所有请求都必须携带 `Bearer Token`（JWT）。
*   **路由**: 独立的 `auth_router` 用于处理登录发牌逻辑。

### 1.2 核心 API 端点与功能
*   **`/api/stats` (全局统计面板)**: 
    *   执行复杂的 SQL 聚合查询，返回：总用户数、总生成数、灵石流通总量、今日活跃、今日生成量等。
    *   包含用于画图的分布数据：`today_type_distribution` (按生成模式分类统计)、小时级生成热度、用户资产分布等。
*   **`/api/system` (系统任务与干预)**:
    *   读取并解析 Redis 队列，返回 Bot 实时活动任务池，提供强制退款和释放并发锁的接口。
*   **`/api/users` (用户管理)**:
    *   分页查询用户列表，支持排序，提供修改用户 `credits` 等核心资产的接口。
*   **`/api/history` (任务历史)**:
    *   查询全服的 AI 生成记录。通过调用底层 `storage.py` 生成 **MinIO 的 Presigned URL** 给前端渲染。
*   **`/api/workers` (Worker 性能与日志，新特性)**:
    *   用于获取所有底层的生图计算节点（ComfyUI Agents）的唯一 ID 列表（`/list`）。
    *   分页查询每个 Worker 的历史执行任务，包括耗时（duration）、成功/失败状态以及错误信息。
*   **`/api/gallery` (广场内容管理，新特性)**:
    *   管理社区广场投稿（`GalleryPost`）。
    *   支持查询、过滤（状态、媒体类型），以及修改帖子的点赞/踩数、应用次数、标签（Tags），控制其是否在前端广场展示（上架/下架），或者直接删除违规帖子。
*   **`/api/logs` (操作审计)**:
    *   分页读取 `user_logs` 表，展示用户的灵石消费与充值流水。
*   **`/api/orders` & `/api/plans` (充值系统)**:
    *   管理 TON 支付套餐配置，查看链上订单明细，支持后台手动赠送套餐。
*   **`/api/templates` (模板共建)**:
    *   管理用户上传的模板审核与应用。

### 1.3 后台守护任务 (Background Tasks)
*   **`worker_listener` (异步监控)**:
    *   在 FastAPI 启动时 (`startup`) 作为后台任务拉起。
    *   **核心逻辑**: 订阅 Redis Pub/Sub 中的 `comfy:task_events:*` 频道，实时监听底层生图节点的完成/失败事件。
    *   将每个任务的 Worker ID、耗时和异常信息持久化写入到 PostgreSQL 的 `worker_logs` 表中，用于统计节点健康度和生成速率。

---

## 2. 前端架构 (Frontend)

前端采用了 **Vue 3 (Composition API) + Vite + Ant Design Vue + Tailwind CSS** 的现代化技术栈。

*   **入口文件**: `dashboard/frontend/src/App.vue`
*   **状态管理**: 直接使用 Vue 3 的 `ref` 和 `computed` 进行轻量级状态管理。
*   **图表库**: 集成了 **ECharts** 进行各种数据大屏的渲染。

### 2.1 页面布局与导航 (Layout)
采用经典的侧边栏 (Sidebar) + 顶部栏 (Header) + 内容区 (Content) 结构。侧边栏目前已扩展为 **9 大核心模块**：

#### 模块一：数据大盘 (Home Dashboard)
*   **顶部指标卡片**: 展示当前系统的核心宏观数据（总用户、各等级弟子分布、总流水、今日活跃等）。
*   **可视化图表矩阵**:
    *   **分布图**: 包含生成类型分布 (饼图)、用户灵石消耗与持有量分布。
    *   **趋势图**: 历史用户增长曲线、日均生成量柱状图、累计分时生成热度图等。

#### 模块二：系统监控 (Monitor)
*   **实时队列监控 (`QueueStats`)**: 调用后端获取当前 AI 显卡排队的实时情况。
*   **Bot 活动任务池 (`ActiveTasksTable`)**: 
    *   展示 Bot 层面的排队请求列表（数据源自 Redis）。支持按状态过滤和搜索。
    *   提供红色的“强制退款”按钮，用于人工干预异常任务。

#### 模块三：用户管理 (User Table)
*   展示所有用户的详细列表，支持直接在表格中给指定用户充值灵石或修改签到天数，查看特定用户的生成历史。

#### 模块四：历史生成 (History Table)
*   全服 AI 生成任务的时间轴列表，直接在前端渲染生成的图片或视频。

#### 模块五：Worker记录 (Worker History Table) - 【新模块】
*   展示底层所有 ComfyUI 节点的执行流水。
*   支持按 Worker ID 筛选，查看每个节点的具体任务类型、执行耗时、成功/失败状态以及导致失败的具体异常日志 (`error_message`)。

#### 模块六：操作日志 (Log Table)
*   系统的对账与排错中心。展示每一次灵石的增减情况，支持组合条件搜索。

#### 模块七：充值系统 (Recharge System)
*   查看充值订单、管理套餐标价与赠送额度、手动下发指定套餐。

#### 模块八：模板共建 (Template Manager)
*   审核用户提交的素材模板，管理员可预览、批准或拒绝。

#### 模块九：广场内容管理 (Gallery Table) - 【新模块】
*   专门用于审核和干预 Web 前端社区广场 (`GalleryPost`) 的帖子。
*   **核心功能**:
    *   查看每一个上榜视频/图片的作者、媒体类型和长宽/时长规格。
    *   支持预览 (Modal 弹窗展示实际视频或图片内容)。
    *   快速切换上架/下架状态 (`is_active`) 以屏蔽违规内容。
    *   修改帖子数据：点赞数、点踩数、一键应用次数，以及修改关联的 JSON 标签格式 (`Tags`)。

### 2.2 核心特性与交互设计
*   **自动刷新与轮询**: 切换 Tab 时会自动触发 `refreshData()` 重新拉取最新数据。
*   **全局状态查询 (全局搜索)**: 
    *   顶部栏提供了一个全局搜索框，输入 `Task ID` 即可弹出一个独立的状态查询窗口。
    *   **实时追踪**: 若任务处于 `pending` 状态，展示剩余等待数和队列位置；若处于 `running` 状态，展示进度条百分比；若已 `done`，直接渲染并提供原文件下载。
*   **鉴权与路由守卫**: 监听原生 `unauthorized` 事件，Token 失效自动退回登录组件。