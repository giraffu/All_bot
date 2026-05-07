# 闪回瓶（历史记录）“删除”功能实现方案分析

## 一、 需求背景
目前 Web 端“闪回瓶”（对应后端的 `History` 表）展示了用户生成的最新8条的历史记录。为了提升用户体验，需要增加“删除”按钮，使得用户点击后，指定的生成内容对用户不可见。

根据项目当前的架构与业务红线，由于涉及到数据库关联与对象存储（MinIO/R2）的物理空间占用，删除操作不能简单粗暴地执行，需要进行周密的方案设计。

---

## 二、 核心痛点与架构约束分析

通过对现有代码库的检索，我们面临以下几个关键约束：

1. **当前模型无隐藏状态**：当前的 `History` 模型中没有 `is_deleted` 或 `is_visible` 等字段。`GET /api/users/history` 接口是直接将用户的历史记录拉取展示的。
2. **与社区广场 (GalleryPost) 的深度绑定**：
   - 社区广场的帖子（`GalleryPost`）本身没有存储图片或视频的链接，而是通过 `task_id` 强依赖关联的 `History.output_file` 来渲染画面。
   - `GalleryPost` 还被 `UserInteraction`（点赞、应用记录）作为外键引用。强制物理删除会直接清除所有的点赞互动数据，导致业务数据断层与分析困难。

---

## 三、 方案设计：全局软删除与状态解耦策略（🌟 采纳方案）

结合保留数据完整性的考量，所有删除操作均采用**软删除**（Soft Delete），并根据记录的 `is_public`（是否已发布至广场）状态决定是否同步处理广场帖子。

#### 1. 若记录“未公开”（`is_public == False`）
该记录属于用户的私有财产，且无任何外部依赖。
- **执行逻辑**：**软删除**。
- **动作**：仅将 `History` 记录的 `is_visible` 置为 `False`（对用户自己的闪回瓶隐藏）。
- **收益**：实现简单，保留了底层数据结构完整性，方便未来可能的“回收站”或“恢复”功能拓展。

#### 2. 若记录“已公开”（`is_public == True`）
该记录已经进入公共广场，可能产生了点赞或被别人一键应用。
- **执行逻辑**：**软删除 + 广场下架 + 个人主页彻底隐藏**。
- **动作**：
  1. 将 `History` 记录的 `is_visible` 置为 `False`（对用户自己的闪回瓶隐藏）。
  2. 同步查找对应的 `GalleryPost`，将其 `is_active` 置为 `False`（从公共广场下架）。
  3. 保留底层的物理文件和点赞记录（维护数据完整性与互动分析数据）。
- **收益**：既满足了用户“彻底看不见”的诉求，又完美绕过了数据物理删除导致的互动记录丢失与广场裂图风险。

> **⚠️ 关键优化点（防“已下架”残留）**：
> 如果仅仅将 `GalleryPost.is_active` 置为 `False`，该帖子只是对“公共广场”不可见，但用户在个人的“个人心得”页面依然会看到它，并显示为“已下架”。
> 为了实现**真正的彻底删除体验**，我们会在后端的“个人心得查询接口（`/api/gallery/my-posts`）”中增加联合过滤条件：**不仅过滤用户 ID，还会通过左外连接校验底层 `History.is_visible.is_not(False)`**（⚠️ 必须使用 `is_not` 处理 NULL 值，防止早期未关联 `task_id` 的合法帖子被错误过滤）。这样只要用户在闪回瓶删除了，他的个人主页也会同步彻底消失，不会留下“已下架”的视觉残留。

---

## 四、 具体实施步骤（规划）

后续的代码修改步骤将如下：

### 1. 数据库层面 (Backend)
- 修改 `src/database/models.py`，在 `History` 类中新增 `is_visible = Column(Boolean, default=True, server_default=text("true"))`（⚠️ **必须加 `server_default`** 防止旧数据因 NULL 而被意外全部隐藏，需从 `sqlalchemy` 引入 `text`。这里建议使用 `"true"` 而非 `"1"` 以更好兼容 PostgreSQL 的布尔类型转换）。
- 生成 Alembic 迁移脚本并升级数据库（`alembic upgrade head`）。

### 2. 接口层面 (Backend)
- **修改闪回瓶查询**：在 `src/web_api/routers/users.py` 中，调整 `GET /api/users/history` 查询，追加 `.where(History.is_visible.is_not(False))`（兼容历史遗留的 NULL 值）。
- **修改我的收藏查询**：在 `src/web_api/routers/users.py` 中，调整 `GET /my-favorites` 接口，同样追加 `.where(History.is_visible.is_not(False))`，防止已删除的记录在收藏列表灵异出现。
- **修改个人主页查询（关键优化）**：在 `src/web_api/routers/gallery.py` 中，调整 `GET /api/gallery/my-posts` 接口。引入**左外连接（`outerjoin`）**关联 `History`，并追加条件 `History.is_visible.is_not(False)`。⚠️ **特别注意**：由于 `GalleryPost` 到 `History` 是一对多关系（`uselist=True`），执行 `outerjoin` 后**必须追加 `.distinct()`** 进行去重，否则会导致返回重复数据及分页 `total` 统计错误。这既能确保删除的记录不会作为“已下架”显示在个人主页，又能防止因早期数据无 `task_id` 导致 NULL 值被错误过滤，丢失合法帖子。
- **改造现有帖子删除接口（统一软删除）**：修改 `src/web_api/routers/gallery.py` 中的 `DELETE /posts/{post_id}`（个人心得页面的删除接口），废弃原有的物理删除逻辑（**删除 `delete(UserInteraction)` 和 `delete(GalleryPost)` 的代码**），统一改为**软删除**（仅将 `GalleryPost.is_active` 置为 `False`），彻底防止点赞等互动分析数据断层。
  - ⚠️ **必须保留的逻辑**：
    1. `update(History).where(History.task_id == post.task_id).values(is_public=False)`，这样帖子下架后，用户在闪回瓶中还能看到并可以重新投稿。
    2. 扣减用户贡献值的逻辑（`user_obj.total_contributions -= 1`）。
- **新增闪回瓶删除接口**：新增 `DELETE /api/users/history/{history_id}`（⚠️ **必须使用主键 `id`**，因为 `task_id` 可能为空且不唯一）：
  - 校验请求者必须是该 `History` 的所有者。
  - 无论是否公开，都将 `History.is_visible` 置为 `False`。
  - 如果 `is_public == True`，则额外将关联的 `GalleryPost.is_active` 置为 `False`（⚠️ **更新时必须附带 `user_id == current_user.id` 条件**，防止越权修改；🚨 **极端重要**：执行关联下架前必须判断 `task_id is not None`，否则 SQLAlchemy 会将条件翻译为 `task_id IS NULL`，导致该用户所有早期未绑定 `task_id` 的公开帖子被一次性全部误伤下架！）。
  - ⚠️ **业务联动要求**：如果关联的 `GalleryPost` 被成功置为 `False` 下架，**必须同步执行 `user_obj.total_contributions -= 1`**，确保用户主页的贡献统计数据一致。

### 3. 前端交互 (Vue3)
- **UI 改造**：在 `History.vue` 的闪回瓶卡片组件上，右上角增加一个🗑️（Trash）删除按钮。
- **交互流程**：点击删除后，弹出二次确认框：“确认删除该记录吗？（若已发布至广场也将同步下架）”。
- **状态同步**：调用接口成功后，在前端的 `ref` 数组中 `filter` 剔除该项，实现无感知的丝滑移除，无需刷新页面（保持删除后列表缩水留白的视觉体验即可）。

---

## 五、 涉及修改的代码文件清单

为了方便开发与 Review，以下是本次方案落地所需要改动的全部核心文件定位：

#### 🟢 后端部分 (Backend)
1. **数据库模型**：[`src/database/models.py`](file:///home/hfy/APP/All_bot/src/database/models.py)
   - 目标：修改 `History` 类，新增 `is_visible` 字段。
2. **用户相关路由**：[`src/web_api/routers/users.py`](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py)
   - 目标：调整 `GET /history` 和 `GET /my-favorites` 接口过滤逻辑；新增 `DELETE /history/{history_id}` 接口实现核心的软删除与下架逻辑。
3. **广场相关路由**：[`src/web_api/routers/gallery.py`](file:///home/hfy/APP/All_bot/src/web_api/routers/gallery.py)
   - 目标：调整 `GET /my-posts` 接口（个人心得），增加左外连接过滤，防止删除后出现“已下架”残留。
4. **数据迁移脚本**：`alembic/versions/` (自动生成)
   - 目标：通过 `alembic revision --autogenerate` 自动生成。

#### 🔵 前端部分 (Frontend)
1. **闪回瓶组件**：[`frontend/src/views/History.vue`](file:///home/hfy/APP/All_bot/frontend/src/views/History.vue)
   - 目标：在 UI 卡片内注入删除按钮及绑定 API 调用，调用成功后通过局部状态移除对应的 `record`。

---

## 结论
采用 **全局软删除策略** 可以最大程度保障系统的稳定性与数据完整性。虽然没有立即释放云端存储，但彻底规避了互动数据断层与裂图的风险，是兼顾开发效率与用户体验的最稳妥方案。