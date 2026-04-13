# 阶段三：基于 Vue3 的 Web 前端开发详细方案

## 📖 阶段概述
阶段三的核心目标是构建一个现代化的单页面应用 (SPA)，全面替代或补充现有的 Telegram Bot 聊天交互方式。前端将通过阶段二开发好的 Web BFF (FastAPI) 接口，实现用户登录、资产查看、生图/视频任务提交以及实时进度监控等功能。

---

## 🛠️ 1. 技术栈选型与规范

严格遵循 Vue 最佳实践：
*   **核心框架**：Vue 3
*   **开发范式**：Composition API + `<script setup>` (强制规范)
*   **语言**：TypeScript (开启严格模式，确保 API 接口数据类型安全)
*   **构建工具**：Vite (极速冷启动与 HMR)
*   **状态管理**：Pinia (轻量、模块化、Type-safe)
*   **路由管理**：Vue Router 4
*   **UI 组件库**：Ant Design Vue 4.x (适合中后台与复杂表单，支持按需引入)
*   **CSS 框架**：TailwindCSS (用于响应式布局与原子化样式，辅助 AntD)
*   **网络与工具**：
    *   `axios` (HTTP 请求封装，带拦截器)
    *   `@vueuse/core` (提供现成的 `useEventSource` 监听 SSE 进度条等 Hooks)

---

## 🗂️ 2. 项目目录结构规划

在项目根目录执行 `npm create vite@latest frontend -- --template vue-ts`，推荐的内部结构如下：

```text
frontend/
├── src/
│   ├── api/            # Axios 实例与所有 BFF API 请求方法
│   │   ├── auth.ts     # 登录相关
│   │   ├── tasks.ts    # 任务提交相关
│   │   └── storage.ts  # MinIO 预签名相关
│   ├── assets/         # 静态资源 (Logo, 全局 CSS)
│   ├── components/     # 通用/业务组件 (细粒度拆分)
│   │   ├── common/     # 基础组件 (如自定义上传按钮)
│   │   └── tasks/      # 任务相关组件 (如参数表单、进度条弹窗)
│   ├── composables/    # 封装的组合式 API (业务逻辑剥离)
│   │   ├── useTask.ts  # 封装 SSE 监听与任务提交流程
│   │   └── useUpload.ts# 封装大文件直传 MinIO 逻辑
│   ├── layouts/        # 页面布局
│   │   └── MainLayout.vue # 包含侧边栏、顶部导航(显示灵石)
│   ├── router/         # Vue Router 配置与路由守卫
│   ├── stores/         # Pinia 状态管理
│   │   ├── auth.ts     # 管理 Token 与用户信息
│   │   └── tasks.ts    # 管理当前运行中的任务列表与进度
│   ├── views/          # 路由级别的视图页面
│   │   ├── Login.vue   # 登录页 (集成 TG Widget)
│   │   ├── Dashboard.vue # 工作台首页 (选择功能)
│   │   ├── FaceSwap.vue  # 换脸功能页
│   │   └── History.vue   # 历史记录页
│   ├── App.vue         # 根组件
│   └── main.ts         # Vue 实例初始化
├── .env                # 环境变量 (VITE_API_BASE_URL)
├── tailwind.config.js  # Tailwind 配置
├── vite.config.ts      # Vite 配置 (代理、按需加载插件)
└── tsconfig.json       # TS 配置
```

---

## 🔄 3. 核心数据流与状态流转

### 3.1 鉴权与路由守卫流 (Auth Flow)
1. 用户访问 `/dashboard`，触发 Vue Router 全局前置守卫 (`beforeEach`)。
2. 守卫检查 Pinia `auth` store 中是否存在 `token`。
3. 无 `token`，重定向至 `/login`。
4. 在 `/login` 页面，用户点击 Telegram Login Widget。
5. 拿到 TG 数据后，调用 `api/auth.ts` 发送 POST 请求给 BFF。
6. BFF 返回 JWT 与 User 信息，存入 Pinia 和 `localStorage`。
7. 路由跳转回 `/dashboard`。

### 3.2 大文件直传与任务提交流 (Upload & Submit Flow)
*由于视频文件可能 > 50MB，前端必须直传 MinIO。*
1. 用户在 `<FaceSwap />` 页面选择视频文件。
2. 触发 `useUpload` composable：
   - 向 BFF 发起 `GET /api/storage/presigned-url`。
   - 拿到 `upload_url` 和 `object_key`。
   - 使用 Axios 原生 `PUT` 请求，将 `File` 对象直接发往 MinIO `upload_url`，可附带 `onUploadProgress` 显示上传进度。
3. 上传成功后，组装表单数据（包含 `object_key`）调用 `POST /api/tasks/generate`。

### 3.3 SSE 实时进度流 (Progress Flow)
1. 任务提交成功，拿到 `task_id`。
2. 调用 VueUse 的 `useEventSource(VITE_API_BASE_URL + '/api/tasks/{task_id}/stream')`。
3. 监听 `progress` 事件，解析 JSON，更新 Pinia `tasks` store 中的进度条百分比。
4. 当接收到 `status: 'success'` 时，关闭 SSE 连接，展示最终的图片/视频结果。

---

## 🚀 4. 详细执行子步骤 (优先级排序)

| 步骤 | 任务描述 | 重点/难点 | 优先级 |
| :--- | :--- | :--- | :--- |
| **1. 工程初始化** | 创建 Vite+Vue3+TS 项目，安装 AntD, Tailwind, Pinia, Vue Router。配置 `vite.config.ts` 中的按需加载插件 (`unplugin-vue-components`)。 | 配置 Proxy 解决本地开发跨域问题。 | **P0** |
| **2. 状态与路由** | 搭建 Pinia Stores 和 Vue Router。实现路由白名单 (`/login`) 与全局登录拦截守卫。封装 Axios 请求拦截器（自动注入 Token）。 | Axios 处理 401 自动登出逻辑。 | **P0** |
| **3. 登录页开发** | 开发 `Login.vue`。引入 Telegram Login Widget ( `<script async src="https://telegram.org/js/telegram-widget.js?...">`) 并捕获回调事件。 | 动态挂载外部 Script 并处理 TS 类型报错。 | **P0** |
| **4. Layout与首页** | 开发 `MainLayout.vue`。左侧菜单栏，右上方显示当前登录用户的头像、昵称和 **灵石余额**。 | 响应式设计（移动端抽屉菜单）。 | **P1** |
| **5. 任务页面开发** | 开发换脸/生图功能页。重点实现大文件上传组件（带本地预览和直传 MinIO 进度条），及参数调节表单。 | UI 组件的细粒度拆分，避免单文件代码过长。 | **P1** |
| **6. SSE 进度反馈** | 封装 `useTask.ts`。任务提交后弹出全局 Modal 或全局抽屉，显示动画进度条。接收完成事件后渲染产物。 | 确保组件销毁时断开 EventSource 连接，防内存泄漏。 | **P1** |
| **7. 历史记录页** | 开发 `History.vue`。使用 AntD 的 Table 或瀑布流组件，分页展示用户的历史生成记录与 MinIO 图片/视频预览。 | 媒体懒加载与图片预加载。 | **P2** |

---

## ⚠️ 5. 最佳实践与风险应对

1. **Composition API 规范**
   - 严禁在大型表单页面中将所有逻辑揉在一个 `<script setup>` 中。
   - 必须遵循 Vue Best Practices，将**大文件上传逻辑**和**SSE监听逻辑**抽离到 `composables/useUpload.ts` 和 `composables/useTaskStream.ts` 中。
2. **移动端适配风险**
   - *问题*：Telegram Web App 通常是在手机端半屏打开的，如果 UI 不适配会导致表单无法点击。
   - *应对*：在 Tailwind 中严格使用响应式前缀 (`md:`, `lg:`)，核心操作区（如“立即生成”按钮）在移动端采用底部吸息 (Fixed Bottom) 设计。
3. **状态同步延迟**
   - *问题*：用户扣费后，前端显示的“灵石余额”没有及时刷新。
   - *应对*：在 SSE 接收到 `success` 事件，或者任务提交接口返回 200 时，从接口响应的 `balance_remaining` 字段同步更新 Pinia 中的余额状态。
4. **视频跨域播放问题**
   - *问题*：从 MinIO 拿到的预签名 URL 播放视频时可能报 CORS 错误。
   - *应对*：需要在 MinIO 服务端配置允许跨域 (CORS) 规则，或者通过 BFF 做轻量级的流媒体代理转发。