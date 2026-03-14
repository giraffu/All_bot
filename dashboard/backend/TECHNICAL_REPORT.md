# TeleBot Dashboard 系统技术报告

## 1. 系统概览

本系统是一个 **Telegram Bot 管理后台 (Dashboard)**，采用 **前后端分离** 架构。
*   **前端**：基于 **Vue 3** (Composition API) + **Vite** + **Ant Design Vue** 构建，提供数据可视化看板、用户管理、历史记录查询及模板审核功能。
*   **后端**：基于 **FastAPI** 构建，利用 **SQLAlchemy (Async)** 直接复用 Bot 核心数据库，提供 RESTful API 接口，并负责静态资源（生成的图片/视频）的托管。

### 1.1 系统上下文图

```mermaid
graph TD
    User[管理员] -->|访问| Web[Web 前端 (Vue3)]
    Web -->|REST API| API[后台 API (FastAPI)]
    API -->|ORM 查询| DB[(SQLite/Postgres)]
    API -->|读取文件| Static[静态资源 (user_data/templates)]
    API -->|查询状态| Comfy[ComfyUI 服务]
    Bot[Telegram Bot] -->|写入数据| DB
    Bot -->|生成文件| Static
```

## 2. 核心架构与模块划分

### 2.1 后端架构 (`dashboard/backend/main.py`)

后端作为轻量级服务，核心设计理念是 **"复用与聚合"**：它不独立管理数据，而是直接挂载 Bot 的 `src` 目录，复用已有的 `database` 模型和 `services` 逻辑。

*   **入口与配置**：
    *   通过 `sys.path.append` 动态加载上层 `src` 模块。
    *   服务默认运行在 `8043` 端口。
    *   启用 CORS 允许跨域请求。
*   **静态资源挂载**：
    *   `/images` -> `user_data`: 访问用户生成的历史图片/视频。
    *   `/temps` -> `templates/temps`: 待审核的投稿模板。
    *   `/quick_face` / `/video_nice`: 已审核通过的模板库。
*   **API 路由模块**：
    *   **统计 (Stats)**: 聚合查询用户量、生成量、积分消耗、活跃度等。
    *   **用户 (Users)**: 分页查询用户列表，支持级联查询邀请人信息。
    *   **历史 (History)**: 查看特定用户或全局的生成记录，支持物理文件删除。
    *   **模板 (Templates)**: 审核用户提交的素材（批准/拒绝）。
    *   **队列 (Queue)**: 实时透传 ComfyUI 的任务排队状态。

### 2.2 前端架构 (`dashboard/frontend/src/App.vue`)

前端采用 **单页应用 (SPA)** 模式，`App.vue` 作为根组件承担了布局容器和全局状态管理的角色。

*   **布局 (Layout)**:
    *   采用典型的 **侧边栏 (Sidebar) + 顶部导航 (Header) + 内容区 (Content)** 结构。
    *   响应式设计，支持侧边栏折叠。
*   **状态管理**:
    *   使用 Vue 3 `ref` 和 `reactive` 管理全局数据（如 `stats`, `users`）。
    *   利用 `watch` 监听 `activeTab` 变化，实现"按需加载"数据（切换到 Users Tab 时才加载用户列表）。
*   **核心视图**:
    *   **首页看板 (Home)**: 集成 `StatsCards` (卡片), `QueueStats` (队列状态), 以及丰富的 ECharts 图表 (包括新增的 **用户生成量分布**、**日均生成量分布**、**用户积分消耗分布**、**日均积分消耗分布** 和 **用户持有积分分布** 柱状图)。
    *   **用户管理 (Users)**: 表格展示，支持查看详情弹窗。
    *   **历史生成 (History)**: 全局历史记录流水。
    *   **模板共建 (Templates)**: 瀑布流或网格形式展示待审核资源。

## 3. 接口契约与数据流

### 3.1 关键 API 定义

| 方法 | 路径 | 描述 | 关键参数/返回值 |
| :--- | :--- | :--- | :--- |
| **GET** | `/api/stats` | 全局统计数据 | 返回 `today_users`, `total_credits`, `generation_distribution`, `avg_daily_distribution`, `credit_distribution`, `avg_daily_credit_distribution`, `credit_holding_distribution` 等 |
| **GET** | `/api/stats/history` | 历史趋势数据 | `days=7` (默认), 返回每日新增用户、生成量、消耗积分、**用户增长率**等 |
| **GET** | `/api/users` | 用户列表 | `skip`, `limit`, 返回包含 `inviter_info`, `referral_count` 的用户对象 |
| **DELETE** | `/api/users/{id}` | 删除用户 | **高危**: 级联删除历史、签到、推荐关系等所有关联数据 |
| **GET** | `/api/bot/queue` | 队列状态 | 调用 `image_service` 获取 ComfyUI 实时排队数 |
| **POST** | `/api/templates/.../approve` | 批准模板 | 移动文件至正式目录，并自动发放积分奖励 |

### 3.2 积分消耗计算逻辑 (后端硬编码)

后端在统计积分消耗时，使用 SQL `CASE` 语句动态计算（非查表），这与 Bot 端的扣费逻辑需保持一致：

```python
# main.py L138-151
video_types = ['video', 'video_undress', 'custom_video', ...] # 视频类任务
cost_case = case(
    (History.type.in_(video_types), 6), # 视频消耗 6 积分
    else_=2                             # 图片消耗 2 积分
)
```

## 4. 关键代码实现细节

### 4.1 前端类型映射 (`App.vue`)

前端维护了一份详尽的 `typeMapping` 字典，将后端存储的英文类型转换为中文友好显示：

```javascript
// App.vue L67
const typeMapping = {
  'undress': '快速脱衣',
  'video_undress': '视频脱衣',
  'face_swap': '快速换脸',
  // ...
  'doggy_style': '动图后入',  // 特定姿势视频
  'template_contribute': '模板共建'
};
```

### 4.2 数据库级联删除策略

后端 `delete_user` 接口实现了手动级联删除（Soft Cascade），确保数据彻底清理：

```python
# main.py L649-674
# 依次删除: 签到记录 -> 生成历史 -> 邀请关系 -> 模板贡献 -> 会话记录 -> 会话状态 -> 权限 -> 用户本体
await db.execute(delete(CheckinHistory).where(CheckinHistory.user_id == user_id))
await db.execute(delete(History).where(History.user_id == user_id))
# ...
await db.delete(user)
```

### 4.3 静态资源挂载

后端通过 `FastAPI.mount` 将本地文件系统暴露为 HTTP 服务，这是 Dashboard 能预览图片的核心：

```python
# main.py L45
app.mount("/images", StaticFiles(directory=str(user_data_path)), name="images")
```
这意味着前端显示图片只需拼接 URL：`http://host:8043/images/{filename}`。

### 4.4 复杂统计指标的 SQL 实现

为了分析用户行为，后端在 `/api/stats` 中利用 SQLite 函数实现了复杂的分布统计，避免了在 Python 层进行全量数据遍历：

*   **用户生成量分布**: 使用 `CASE` 语句将 `User.generation_count` 划分为不同区间 (0, 1, 2... 1000+)。
*   **日均生成量**: 利用 `julianday` 计算用户加入天数，动态计算 `generation_count / days` 并进行区间分组。
*   **积分消耗分布**: 通过子查询聚合 `History` 表计算每位用户的总消耗，再结合 `CASE` 语句进行区间统计。
*   **日均积分消耗**: 结合用户加入天数和总积分消耗，计算日均值并分组。
*   **用户持有积分分布**: 直接查询 `User.credits`，使用 `CASE` 语句将用户按持有积分划分为 (0, 1-10... 5000+) 等区间。

```python
# main.py 计算日均生成量
days_diff = func.julianday('now') - func.julianday(User.created_at)
days_valid = case((days_diff < 1, 1), else_=days_diff) # 防止除零
avg_daily = func.cast(func.coalesce(User.generation_count, 0), Float) / days_valid

# 积分消耗分布统计 (简略)
consumption_stmt = select(History.user_id, func.sum(cost_case).label('consumed')).group_by(History.user_id)
# ...利用子查询和 CASE 语句进行分组统计...
```

## 5. 运行依赖与配置

### 5.1 后端依赖
*   **Python**: `>=3.9`
*   **核心库**: `fastapi`, `uvicorn`, `sqlalchemy`, `aiosqlite` (或对应异步驱动), `pydantic`.
*   **项目依赖**: 必须存在 `src/` 目录且包含 `config.py` 和 `database/` 模块。

### 5.2 前端依赖 (`package.json`)
*   **核心框架**: `vue` (^3.5.24)
*   **UI 组件库**: `ant-design-vue` (^4.2.6), `@ant-design/icons-vue`
*   **工具库**: `axios`, `tailwindcss`
*   **图表**: `echarts`, `vue-echarts`

### 5.3 环境变量
Dashboard 复用了 Bot 的 `config.py`，主要依赖：
*   `API_BASE`: ComfyUI 地址。
*   `STATUS_ENDPOINT`: ComfyUI 状态查询接口。
*   数据库连接字符串 (在 `src.database.core` 中定义)。

## 6. 部署与启动

### 6.1 开发环境

1.  **启动后端**:
    ```bash
    cd dashboard/backend
    # 确保 python 路径能找到 src
    python main.py
    # 或使用 uvicorn (需手动设置 PYTHONPATH)
    # set PYTHONPATH=../../ && uvicorn main:app --reload --port 8043
    ```

2.  **启动前端**:
    ```bash
    cd dashboard/frontend
    npm install
    npm run dev
    ```

### 6.2 生产部署

建议使用 Docker 或 Systemd 管理进程。

*   **后端**: 使用 `uvicorn` 生产模式启动。
*   **前端**: 运行 `npm run build` 生成 `dist` 目录，并将其作为静态文件挂载到 FastAPI 的 `/` 路径下，或者使用 Nginx 反向代理。

## 7. 常见问题排查表

| 现象 | 可能原因 | 排查方案 |
| :--- | :--- | :--- |
| **Dashboard 无法加载用户列表** | 数据库路径错误 / 后端未启动 | 检查 `main.py` 中的 `os.chdir(PROJECT_ROOT)` 是否正确指向数据库文件所在目录。 |
| **图片预览 404** | `user_data` 目录不存在 | 确认 Bot 根目录下是否有 `user_data` 文件夹，且权限正确。 |
| **跨域错误 (CORS)** | 前端端口未在白名单 | 检查 `main.py` 中 `CORSMiddleware` 配置，当前配置为 `["*"]` (允许所有)，生产环境建议收缩。 |
| **积分消耗统计不准** | 硬编码逻辑过时 | 检查 `main.py` 中的 `video_types` 列表是否包含了新增的生成类型。 |

## 8. 可扩展性建议

1.  **动态配置**: 目前积分消耗规则硬编码在 SQL 查询中，建议提取到 `src/constants.py` 或数据库配置表中，供前后端共享。
2.  **鉴权机制**: Dashboard 目前没有登录鉴权（前端仅有模拟的管理员UI），生产环境 **必须** 增加 API Key 校验或 OAuth 登录（如 Telegram Widget Login）。
3.  **前端优化**: `App.vue` 体积较大，建议将 Sidebar、Header 拆分为独立组件，将 API 调用逻辑进一步封装到 Store (Pinia) 中。
4.  **WebSocket**: 引入 WebSocket 替换轮询，实现队列状态和任务进度的实时推送。
