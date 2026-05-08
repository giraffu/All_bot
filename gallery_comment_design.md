# Web 端修仙市集（Gallery）评论功能设计方案

## 1. 需求分析
1. **评论按钮与输入框**：UI 底部增加评论按钮，点击弹出文本框输入内容。
2. **下拉查看评论**：用户可下拉详情页面查看其他人的历史评论内容。
3. **数据打通**：从数据库持久化存储到后端 API 暴露，再到 Vue3 前端的交互展示。
4. **后台管理 (Dashboard)**：支持管理员查看、修改帖子评论数以及对违规评论进行软删除。

## 2. 数据库设计 (Database Schema)

### 2.1 新增表结构 `GalleryComment`
在 `src/database/models.py` 中新增 `GalleryComment` 模型，保存评论元数据。
**架构红线与数据完整性**：在外键层面必须使用 `ondelete="CASCADE"` 防止孤儿数据，在业务层面通过 `is_active` 控制软删除与审核，共同保障数据的一致性和可回溯性。
```python
class GalleryComment(Base):
    __tablename__ = "gallery_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("gallery_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True, nullable=False)
    content = Column(String(500), nullable=False) # 限制评论长度
    is_active = Column(Boolean, default=True) # 软删除与审核控制
    created_at = Column(DateTime, default=datetime.now, index=True)

    user = relationship("User")
    # 🚨 修复：必须配置级联删除，否则删除帖子时会导致 NOT NULL constraint failed
    post = relationship("GalleryPost", backref=backref("comments", cascade="all, delete-orphan", passive_deletes=True))
```

### 2.2 现有表结构扩展 `GalleryPost`
**性能优化考量**：为了避免每次获取热门帖子列表时进行大规模的 `COUNT()` 聚合查询，在 `GalleryPost` 中新增冗余统计字段。
**注意**：数据库中务必使用 `server_default="0"` 和 `nullable=False`。否则 Alembic 升级时历史数据会产生 `NULL`，导致后续进行 `comments_count + 1` 原子操作时直接报错。
```python
class GalleryPost(Base):
    # ... existing fields ...
    comments_count = Column(Integer, default=0, server_default="0", nullable=False)
```
并在 Alembic 生成 migration 脚本：
```bash
alembic revision --autogenerate -m "add gallery comments"
alembic upgrade head
```

## 3. 后端 API 设计 (FastAPI)

### 3.1 DTO Schemas (Web API)
在 `src/web_api/schemas/gallery_schema.py` 中增加：
```python
class CommentCreate(BaseModel):
    content: str = Field(..., max_length=500, min_length=1)

class CommentUserResponse(BaseModel):
    id: int
    author_name: str # 后端手动提取 user.full_name 或 username

class GalleryCommentResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    user: CommentUserResponse
    
    class Config:
        from_attributes = True

class PaginatedCommentResponse(BaseModel):
    items: List[GalleryCommentResponse]
    total: int
    page: int
    size: int
    pages: int # 保持与系统现有分页组件一致
```
同时在 `GalleryPostResponse` 中增加 `comments_count: int`。

### 3.2 路由 endpoints (Web API)
在 `src/web_api/routers/gallery.py` 中增加两个接口，并修改现有逻辑：

**1. 组装逻辑补充**
修改 `_build_post_responses` 函数，将 `GalleryPost.comments_count` 映射到 `GalleryPostResponse` 中返回。

**2. 发布评论 (POST `/api/gallery/posts/{post_id}/comments`)**
- **权限**：依赖 `get_current_user` 校验 JWT Token。
- **逻辑与事务安全**：
  1. **防刷校验**：在 `src/services/redis_client.py` 中新增防并发刷量限制，限制用户的发评频率防范脚本水军。建议利用 `nx=True` 实现原子获取：
     ```python
     async def set_comment_lock(self, user_id: int, ttl: int = 5) -> bool:
         key = f"{REDIS_PREFIX}comment_lock:{user_id}"
         # 💡 修复：nx=True 时若键已存在会返回 None，必须显式转换为 bool
         return bool(await self.redis.set(key, "1", ex=ttl, nx=True))
     ```
     路由中调用此方法限制单个用户每 5~10 秒只能发布一条评论。
  2. 校验 `post_id` 对应的帖子是否存在且 `is_active=True`。
  3. 开启数据库事务，插入 `GalleryComment` 记录。
  4. **原子更新**：`comments_count` 必须通过 SQL 层面的原子更新。注意事务执行顺序：
     ```python
     try:
         session.add(new_comment)
         await session.flush() # 先落库获取 ID 并捕获潜在的外键异常

         stmt = update(GalleryPost).where(GalleryPost.id == post_id)\
                                   .values(comments_count=GalleryPost.comments_count + 1)
         await session.execute(stmt)
         
         # 在 commit 前构造返回值对象，防止 commit 后 new_comment 对象过期导致 DetachedInstanceError
         response_data = GalleryCommentResponse(
             id=new_comment.id,
             content=new_comment.content,
             created_at=new_comment.created_at,
             user=CommentUserResponse(
                 id=current_user.id,
                 author_name=current_user.full_name or current_user.username or f"User {current_user.id}"
             )
         )

         await session.commit()
         return response_data
     except Exception:
         await session.rollback()
         raise
     ```

**3. 获取评论列表 (GET `/api/gallery/posts/{post_id}/comments`)**
- **权限**：公开访问。
- **参数**：`page: int = 1`, `size: int = 20`
- **逻辑**：
  1. 按照 `created_at` 降序 (DESC) 获取 `is_active=True` 的评论。
  2. `joinedload(GalleryComment.user)` 以避免 N+1 查询问题。
  3. 由于 `User` 模型没有 `author_name` 字段，需在查询后手动遍历组装 `author_name`（取 `full_name` 或 `username`），避免直接丢给 Pydantic 导致验证失败。
  4. 返回 `PaginatedCommentResponse`。

### 3.3 Dashboard (Admin 管理后台) 适配
必须同步修改后台相关文件以防数据丢失和便于管理：
1. **DTO 扩展**：`/dashboard/backend/routers/gallery.py` 的 `GalleryPostUpdate` 中补充 `comments_count: Optional[int] = None`。
2. **列表组装**：在 `get_all_gallery_posts` 函数中，返回的字典必须补充 `"comments_count": p.comments_count`。
3. **评论管理与软删同步**：预留 `PUT /comments/{comment_id}` 接口供管理员对违规评论进行软删除（`is_active=False`）。
   - **🚨 严重路由冲突警告**：由于现有代码已存在 `@router.put("/{post_id}")`，如果将 `comments` 路由写在帖子路由下方，请求会被错误匹配并抛出 422 错误。必须将本接口放置在 `/{post_id}` **之前**，或者将原接口改为 `@router.put("/{post_id:int}")`。
   - **注意**：由于该文件顶部已声明 `prefix="/api/gallery"`，路由装饰器直接写 `@router.put("/comments/{comment_id}")` 即可。
   - **⚠️ 关联更新逻辑**：当管理员调用软删除接口时，必须在软删的同时原子递减 `comments_count`。因为软删接口的参数中没有 `post_id`，执行原子递减前，必须先查询出对应的 `post_id`，并利用 `func.greatest` 防止负数：
   ```python
   # 先获取评论以拿到 post_id
   comment = await db.get(GalleryComment, comment_id)
   if not comment:
       raise HTTPException(status_code=404)
       
   stmt = update(GalleryPost).where(GalleryPost.id == comment.post_id)\
                             .values(comments_count=func.greatest(GalleryPost.comments_count - 1, 0))
   ```
4. **前端适配**：在 `dashboard/frontend/src/components/GalleryTable.vue` 的表格列定义 (`columns`) 中同步增加 `comments_count` 字段，供管理员查看。

## 4. 前端交互设计 (Vue3 + TailwindCSS)

主要修改文件：`frontend/src/views/Gallery.vue`。

### 4.1 TypeScript 接口更新
在 `Gallery.vue` 顶部补充 `comments_count` 字段，以及评论相关接口：
```typescript
interface Post {
  // ... 现有字段
  comments_count: number;
}

interface CommentUser {
  id: number;
  author_name: string;
}

interface GalleryComment {
  id: number;
  content: string;
  created_at: string;
  user: CommentUser;
}
```

### 4.2 UI 结构改造
**0. 图标导入**
在 `<script setup>` 顶部引入 `MessageCircle` 图标：
```typescript
import { ..., MessageCircle } from 'lucide-vue-next'
```

**1. 画廊首页瀑布流卡片 (Grid Card Stats Bar)**
在 `Gallery.vue` 首页卡片底部的 Stats Bar 同步渲染评论数，保持交互一致性：
```html
<div class="flex items-center text-slate-300 hover:text-blue-400 transition-colors" @click.stop="openDetail(post)">
  <MessageCircle :size="14" class="mr-1" />
  <span class="text-xs font-medium">{{ post.comments_count }}</span>
</div>
```

**2. Mobile 端详情页底部交互栏 (Bottom Interaction Bar)**
在现有的 Like / Dislike 旁边，增加 Comment 按钮：
```html
<button @click="showCommentInput = true" class="flex items-center gap-1.5 transition-all text-slate-300">
  <MessageCircle :size="22" />
  <span class="text-sm font-medium">{{ currentPost.comments_count }}</span>
</button>
```

**3. Desktop 端详情页交互按钮区**
在现有的按钮行中，增加评论按钮。

**4. 评论列表展示区**
在作品详细信息（Info Area）的下方，扩展一个展示区域 `<div class="comments-section">`：
- **桌面端**：使用 `overflow-y-auto flex-1` 限制高度并允许内部滚动。
- **移动端**：无需额外设滚动属性，直接跟随 `.mobile-full-modal` 全局滚动即可；但需在底部预留出 `safe-area-bottom`（如 `padding-bottom: 80px`），防止列表底部被固定在下方的交互栏遮挡。
- 内部展示：
  - 评论总数 Header
  - `v-for="comment in comments"` 渲染的评论列表（自动生成头像、昵称、内容、时间）。
  - 底部显示“加载更多”按钮或基于 `IntersectionObserver` 的无限滚动。

**5. 弹出式输入框 (Popup Input Box)**
- 在 `Gallery.vue` 模板最后引入一个 `<a-modal>` 或底层滑动弹窗（Action Sheet，移动端友好）。
- 包含一个 `<textarea v-model="newComment" maxlength="500">` 以及“发送”按钮。
- 发送成功后，乐观更新（Optimistic Update）当前列表，将新评论 `unshift` 到列表头部，并将 `comments_count++`。

### 4.3 状态管理与 API 对接
在 `<script setup>` 中新增状态：
```typescript
const comments = ref<GalleryComment[]>([])
const commentsLoading = ref(false)
const commentsPage = ref(1)
const showCommentInput = ref(false)
const newComment = ref('')

// 当 currentPost 变化时，触发加载评论
watch(currentPost, (newPost) => {
  if (newPost) {
    comments.value = []
    commentsPage.value = 1
    loadComments(newPost.id)
  }
})

const loadComments = async (postId: number) => { /* 调用 GET API */ }
const submitComment = async () => { /* 调用 POST API并局部更新UI */ }
```