# Web端入口迁移与系统重构开发计划书

## 📖 文档概述
本文档旨在为本项目从单一的 Telegram Bot 入口向“多平台 Web + Bot 共存”架构演进提供全面、专业的开发指南与项目管理规划。计划涵盖底层重构、BFF后端开发及 Vue3 前端开发三大核心模块。

---

## � 最新进展与成果总结 (Project Status & Achievements)

截至目前，项目已成功完成前三个核心里程碑，Web 端的核心功能已经可以闭环运行。以下是近期取得的关键成果：

### 1. 前端体验大幅升级 (Frontend UX Improvements)
*   **统一的状态流转 (`useTaskResult.ts`)**：封装了标准的任务进度、排队人数 (`queuePos`) 监听与结果获取逻辑，彻底解决了前端状态不同步的问题。
*   **沉浸式内联预览**：在核心页面 (`FaceSwap.vue`, `VideoSwap.vue`, `SingleImage.vue` 等) 实现了基于 `URL.createObjectURL` 的图片/视频本地瞬间预览，彻底移除了老旧的跳转交互。
*   **优雅的结果展示**：集成了带有下载、重新生成功能的内联结果展示区，并配合 Tailwind CSS 实现了高度现代化的卡片与骨架屏加载动画。
*   **SPA 路由修复**：修复了 Vue 3 History 模式下刷新页面导致 404 或下载 HTML 文件的单页应用路由回退 (SPA Routing Fallback) Bug。

### 2. 后端稳定性与架构修复 (Backend Stability Fixes)
*   **SSE 竞态条件修复**：修复了任务过快完成导致前端 SSE 错过“成功”事件而永久卡在“0人排队”的 Bug（通过建立订阅前预检状态解决）。
*   **幽灵锁 (Ghost Locks) 终结**：通过引入 FastAPI `BackgroundTasks`，后端现在能异步监控任务流并可靠释放并发锁，解决了用户遇到 `429 Too Many Requests` 无法提交新任务的问题。
*   **文件路径解析修复 (`Errno 21`)**：重构了 MinIO 预签名 URL 的解析逻辑，正确剥离 Bucket 前缀，解决了 Worker 端把目录当文件读取的崩溃问题。
*   **空提示词透传修复**：为图生图等任务自动注入默认 Prompt，解决了生成的图片与原图完全一致 (Pass-through) 的问题。
*   **图生视频路由修正**：修复了 `is_video` 标志位的路由判断，确保视频类任务（如“动图后入”）正确派发给视频流 ComfyUI Worker，而非降级为静态图片生成。

---

## �📅 项目管理规划 (Project Management)

### 1. 里程碑设置与时间估算 (Milestones & Time Estimation)
整个项目预计耗时 **4-5 周**，当前进度：**Milestone 3 已完成，进入 Milestone 4 阶段**。

*   ✅ **Milestone 1: 核心解耦与数据迁移 (Completed)**
    *   完成数据库 `users` 表的多平台 ID 改造。
    *   完成 Bot 业务逻辑抽离至 `src/core/` 目录。
*   ✅ **Milestone 2: Web BFF 后端基建 (Completed)**
    *   完成 FastAPI BFF 框架搭建 (`web_api/`)。
    *   完成 JWT 鉴权体系与第三方 OAuth（Telegram Widget）接入。
    *   封装核心生图/视频接口及 MinIO 预签名直传接口。
*   ✅ **Milestone 3: Vue3 前端开发与对接 (Completed)**
    *   完成基础框架、Ant Design Vue 及 Tailwind CSS 引入。
    *   实现登录、主控制台、任务流交互界面（支持大图/视频实时预览）。
    *   实现基于 SSE 的任务状态与排队位置实时推送。
*   🔄 **Milestone 4: 支付闭环、联调与上线部署 (In Progress)**
    *   [待办] 接入 Web 端支付体系（如 TON Connect Web 或易支付扫码）。
    *   [待办] 全链路压测与 Nginx/CDN 缓存加速配置。
    *   [待办] 生产环境发布上线。

### 2. 关键路径分析 (Critical Path)
**数据库迁移 -> 核心逻辑抽离 -> BFF 接口暴露 -> 前端任务流对接**。
*注意：前端的基础 UI 组件可以与 BFF 开发并行，但涉及核心状态流转（如生图排队）的页面必须在 BFF 接口稳定后进行联调。*

---

## 🛠️ 阶段一：重构现有 Bot 系统

### 1.1 子步骤清单 (优先级排序)
1.  **[P0] 数据库表结构迁移 (Alembic)**：将 `users.id` 解耦，新增多平台登录字段。
2.  **[P0] 核心业务层 (Core Layer) 抽象**：在 `src/core/` 下新建服务类，剥离扣费、锁检测、任务分发逻辑，移除 Telegram `Update` 依赖。
3.  **[P1] Bot Handler 适配**：将原有的 `task_service.py` 和 `permission_service.py` 改造为调用 `src/core/` 中的纯函数。
4.  **[P2] 全局回归测试**：确保原有 Bot 流程（尤其是支付回调、发货）完全正常。

### 1.2 系统架构图
```mermaid
graph TD
    subgraph "重构后系统架构"
        TG[Telegram Bot Handlers] --> Core[Core Services<br/>业务核心逻辑层]
        Web[Web BFF API] --> Core
        Payment[Payment Webhooks] --> Core
        
        Core --> DB[(PostgreSQL)]
        Core --> Redis[(Redis Queue/Lock)]
        Core --> MinIO[(MinIO Object Storage)]
        
        Core --> CentralAPI[Central API 任务网派发]
    end
```

### 1.3 数据流图 (请求生命周期)
```mermaid
sequenceDiagram
    participant User as Telegram用户
    participant Handler as Bot Handler
    participant Core as Core Service
    participant DB as PostgreSQL
    participant Redis as Redis
    participant Central as Central API
    
    User->>Handler: 发送图片并点击生成
    Handler->>Core: 传入内部User_ID与图片路径
    Core->>Redis: 检查并发锁(MAX_CONCURRENT_TASKS)
    Core->>DB: 检查灵石余额并扣除流水
    Core->>Central: POST /face_swap (带Auth)
    Central-->>Core: 返回 Task ID
    Core-->>Handler: 返回成功状态与Task ID
    Handler-->>User: 发送排队成功消息
```

### 1.4 核心数据结构设计 (Alembic 迁移)
```sql
-- 目标 users 表核心结构
CREATE TABLE users (
    internal_id BIGSERIAL PRIMARY KEY, -- 纯内部系统ID，解耦TG
    telegram_id BIGINT UNIQUE,         -- 原有的 TG ID
    google_id VARCHAR(255) UNIQUE,     -- Google OAuth ID
    email VARCHAR(255) UNIQUE,         -- 邮箱注册
    hashed_password VARCHAR(255),      -- 密码哈希
    credits INTEGER DEFAULT 6,
    -- ... 其他原有业务字段保留
);
-- 索引
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
```

### 1.5 风险与应对、验收标准
*   **风险**：外键关联（如 `orders`, `history`）在迁移主键时断裂。
*   **应对**：采用两步迁移法。先加 `telegram_id` 列并复制数据，然后修改外键引用，最后更换主键类型。
*   **验收**：旧用户的积分和历史记录无缝保留，Bot 响应延迟无增加。

---

## 🌐 阶段二：开发 Web BFF 后端

### 2.1 子步骤清单
1.  **[P0] BFF 框架初始化**：基于 FastAPI，在项目根目录新建 `web_api/`。
2.  **[P0] JWT 认证体系**：实现 `/api/auth/login`, `/api/auth/google` 等接口。
3.  **[P0] API 路由与网关**：实现 `/api/tasks/`，内部调用 `src/core/` 逻辑。
4.  **[P1] MinIO 直传策略**：实现 `/api/storage/presigned-url` 接口，减轻 BFF 流量压力。
5.  **[P1] SSE 状态推送**：实现 `/api/tasks/stream` 供前端实时监听进度。

### 2.2 BFF 架构设计图
```mermaid
graph LR
    subgraph "Web BFF Backend"
        Router[FastAPI Routers]
        Auth[JWT Auth Middleware]
        Aggregator[Service Aggregator]
        
        Router --> Auth
        Auth --> Aggregator
        Aggregator --> Core[本地引入 src/core]
        Aggregator --> MinIO_Auth[MinIO STS / Presigned URL]
    end
```

### 2.3 数据流图 (Web 端生成任务)
```mermaid
sequenceDiagram
    participant Vue as Vue3 Frontend
    participant BFF as Web BFF API
    participant MinIO as MinIO Storage
    participant Core as Core Service
    
    Vue->>BFF: 请求上传图片凭证 (Presigned URL)
    BFF-->>Vue: 返回 MinIO PUT URL
    Vue->>MinIO: 直接 PUT 上传大文件 (绕过BFF)
    MinIO-->>Vue: 200 OK
    Vue->>BFF: 提交任务 (带 MinIO Object Key)
    BFF->>Core: 鉴权通过，调用核心层处理
    Core-->>BFF: 返回 Task ID
    BFF-->>Vue: 任务创建成功
    Vue->>BFF: 建立 SSE 连接监听进度
```

### 2.4 接口定义示例
*   `POST /api/auth/login`: 账号密码/OAuth 登录，返回 `{ "access_token": "jwt..." }`
*   `GET /api/storage/upload-url`: 返回 MinIO 直传 URL。
*   `POST /api/tasks/generate`: 提交生图任务，参数 `{"task_type": "face_swap", "inputs": {"face": "key1", "target": "key2"}}`。

### 2.5 风险与应对、验收标准
*   **风险**：SSE 占用大量后端连接导致 FastAPI Worker 耗尽。
*   **应对**：使用异步 ASGI (Uvicorn) 运行 BFF，并配置合理的 Timeout 机制，前端加入断线重连逻辑。
*   **验收**：前端能稳定获取 JWT，且所有受保护的路由正确拦截未授权请求。

---

## 🖥️ 阶段三：开发 Vue3 前端

### 3.1 子步骤清单
1.  **[P0] 项目初始化**：`npm create vite@latest web_frontend -- --template vue-ts`。
2.  **[P0] 引入组件与路由**：配置 Ant Design Vue (UI) + Vue Router + Pinia。
3.  **[P1] Auth 模块开发**：登录、注册、Google/TG 一键登录组件。
4.  **[P1] 核心工作台页面**：包含不同模式（换脸、动图等）的表单提交与大文件分片上传组件。
5.  **[P2] 响应式与状态优化**：处理移动端适配，接入 SSE 实现进度条动画。

### 3.2 前端架构设计图
```mermaid
graph TD
    subgraph "Vue 3 Frontend Architecture"
        UI[Ant Design Vue Components]
        Views[Pages / Views]
        Store[Pinia State Management]
        Router[Vue Router & Navigation Guards]
        API[Axios / VueUse (SSE)]
        
        UI --> Views
        Views --> Store
        Views --> Router
        Views --> API
        Store --> API
    end
```

### 3.3 数据流与状态管理方案
*   **Store 设计 (Pinia)**：
    *   `useAuthStore`: 管理 `token`, `user_info` (包含灵石余额、境界)，处理登出逻辑。
    *   `useTaskStore`: 管理当前活动的 `task_id` 列表、进度百分比、历史记录缓存。
*   **路由守卫 (Navigation Guard)**：全局拦截，未登录重定向至 `/login`，已登录拦截重复访问登录页。

### 3.4 性能优化与懒加载策略
1.  **路由懒加载**：使用 `const Console = () => import('./views/Console.vue')` 分割代码块。
2.  **大文件上传优化**：针对大于 50MB 的视频，前端直传 MinIO，避免通过 Base64 或表单编码占用浏览器内存。
3.  **按需引入组件**：Ant Design Vue 配合 `unplugin-vue-components` 实现组件按需加载，减小首屏打包体积。

### 3.5 风险与应对、验收标准
*   **风险**：移动端 (H5) 下复杂表单（如换脸+参数调节）布局错乱。
*   **应对**：严格遵循 Ant Design Vue 的 Grid 栅格系统，所有核心操作面板采用响应式抽屉 (Drawer) 或堆叠布局。
*   **验收**：Lighthouse 性能评分 > 85，首屏加载时间 < 1.5s，PC 与手机端均能顺畅完成一套完整的换脸任务闭环。
