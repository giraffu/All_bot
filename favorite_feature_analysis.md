# “闪回瓶”收藏至 R2 与“修仙笔记”展示方案分析

根据需求，我们需要在“闪回瓶”中增加“收藏”功能，点击后将内容上传到 Cloudflare R2；并在“修仙笔记”中增加“我的收藏”分类，供用户查看已收藏的内容。以下是详细的技术分析与方案设计。

## 1. 数据库设计方案 (Database Design)

推荐直接在 `History` 表中增加 `is_favorited` 字段，而不是创建新表。因为收藏的本质是用户标记自己生成的记录，这种一对一的关系直接加字段最为高效。

- **修改 `src/database/models.py`**：
  在 `History` 模型中增加布尔字段，并在 `__table_args__` 中为查询性能添加联合索引（注意 `History` 目前没有定义 `__table_args__`，需要新增）：
  ```python
  is_favorited = Column(Boolean, default=False)
  
  # 必须使用元组形式定义 __table_args__
  __table_args__ = (
      Index('idx_history_user_favorite', 'user_id', 'is_favorited'),
  )
  ```
- **Alembic 迁移**：
  执行 `alembic revision --autogenerate -m "add is_favorited to history"` 生成迁移脚本并更新数据库。

## 2. 后端接口设计 (Backend API)

**2.1 新增“收藏”操作接口**
- **Endpoint**: `POST /api/users/history/{task_id}/favorite`
- **核心逻辑**:
  1. 鉴权并查询对应的 `History` 记录，确保其属于当前用户且存在生成文件。
  2. 若未收藏，则更新 `is_favorited = True`。
  3. **触发 R2 上传**：复用 `allbot-gallery-storage` 规范，通过 FastAPI 的 `BackgroundTasks` 调用现有的 `async_copy_to_r2`，异步将 MinIO 中的文件复制到 Cloudflare R2，实现 CDN 加速和永久保存。
  4. 返回操作成功状态。

**2.2 获取“我的收藏”列表接口**
- **Endpoint**: `GET /api/users/my-favorites`
- **核心逻辑**:
  查询当前用户所有 `is_favorited == True` 的 `History` 记录：
  ```python
  stmt = select(History).where(
      History.user_id == current_user.id,
      History.is_favorited == True
  ).order_by(desc(History.created_at))
  ```
  **响应结构适配**：为了让前端“修仙笔记”页面能够无缝渲染并支持一键应用，后端需将 `History` 对象映射为兼容 `GalleryPost` 结构的 JSON 返回。例如：
  - 必须返回 `task_id`、`prompt` 和 `type` 字段，以便前端能正常唤起一键应用的 FSM 参数提取。
  - `thumbnail_url` 和 `media_url` 均取自 `History.output_file`。
  - **字段兼容注意**：`History.type`（如 `video_lora`）需转换为前端兼容的 `media_type`（如包含 `video` 则为 `video`，否则为 `image`），以免导致前端 `isVideoFile` 判断逻辑异常。
  - `tags` 可通过正则从 `History.prompt` 中提取（如提取 Lora 名称）。
  - `likes_count`、`applied_count` 等社区互动数据固定为 0。

**2.3 Schema 更新与一键应用支持**
- **更新 `HistoryItem` Schema**：必须在 `src/web_api/schemas/user_schema.py` 的 `HistoryItem` 中增加 `is_favorited: bool = False` 字段，否则前端无法在闪回瓶获取收藏状态。
- **新增收藏记录的“一键应用”接口**：由于收藏的是私人 `History` 记录，不能复用广场的 `/gallery/posts/{id}/apply-context` 接口（会导致 404 或越权）。需在 `users.py` 中新增 `GET /api/users/history/{task_id}/apply-context`，专门用于解析历史记录的生成参数。

## 3. 前端修改方案 (Frontend Implementation)

**3.1 闪回瓶 (`frontend/src/views/History.vue`)**
- **UI 增加按钮**：在表格的操作列（Actions）中，增加一个“收藏”按钮（使用 Lucide 的 `Star` 或 `Bookmark` 图标）。
- **状态联动**：接口 `/users/history` 需要在返回值中带上 `is_favorited`。若为 `true`，按钮显示为“已收藏”并置灰，防止重复点击。
- **交互逻辑**：点击触发收藏 API，显示 loading 状态，成功后通过 `message.success` 提示用户已存入修仙笔记。

**3.2 修仙笔记 (`frontend/src/views/MyFavorites.vue`)**
- **Tab 栏扩展**：在顶部的分类过滤按钮数组中，新增一项 `{id: 'favorite', name: '我的收藏'}`。
- **数据加载路由分离**：
  修改 `loadPosts` 函数，当用户切换到“我的收藏”时，请求独立的 API：
  ```javascript
  const endpoint = filterType.value === 'favorite' 
      ? '/users/my-favorites' 
      : '/gallery/my-favorites'
  const res = await api.get(endpoint, { params: { page, size } })
  ```
- **交互隔离与状态适配**：
  由于收藏的内容属于私人记录，不具备社区互动属性，当打开收藏内容的详情弹窗时，必须使用 `v-if="filterType !== 'favorite'"` 隐藏“点赞”、“踩”按钮，防止误触导致接口报错，并增加“取消收藏”按钮。
- **一键应用路由动态化**：**重点保留“一键应用”按钮**，但点击 `handleApply` 时，必须根据 `filterType` 动态请求不同的接口：
  ```javascript
  const applyEndpoint = filterType.value === 'favorite'
      ? `/users/history/${currentPost.value.task_id}/apply-context`
      : `/gallery/posts/${currentPost.value.id}/apply-context`
  const res = await api.get(applyEndpoint)
  ```
  让用户可以随时基于自己收藏的历史参数再次提交生成任务，同时彻底解决硬编码 `GalleryPost.id` 导致的 404 和越权漏洞。

## 4. 容灾与性能考量 (Reliability & Performance)
1. **R2 异步长效存储**：R2 上传完全在后台运行，不阻塞用户操作。收藏后的文件即使 MinIO 中的源文件被清理脚本删除，由于 R2 中存有备份且 CDN 路径一致，前端依然可以正常访问（前端的 `getFileUrl` 方法天然支持直接读取 R2 加速域名）。
2. **数据隔离**：将私人收藏与社区广场（GalleryPost）在物理表上完全隔离，避免了由于将私人记录混入公共表而引发的鉴权漏洞或数据污染。
3. **性能保证**：收藏查询依赖 `(user_id, is_favorited)` 联合索引，可保证随着历史记录增加，查询“我的收藏”依然保持毫秒级响应。
