# Web 端修仙市集（Gallery）评论功能设计方案

## 1. 需求分析
1. **评论按钮与输入框**：UI 底部增加评论按钮，点击弹出文本框输入内容。
2. **下拉查看评论**：用户可下拉详情页面查看其他人的历史评论内容。
3. **数据打通**：从数据库持久化存储到后端 API 暴露，再到 Vue3 前端的交互展示。

## 2. 数据库设计 (Database Schema)

### 2.1 新增表结构 `GalleryComment`
在 `src/database/models.py` 中新增 `GalleryComment` 模型，保存评论元数据。
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
    post = relationship("GalleryPost", backref="comments")
```

### 2.2 现有表结构扩展 `GalleryPost`
为了避免每次获取帖子列表时去 `COUNT()` 评论表，在 `GalleryPost` 中新增冗余统计字段。
```python
class GalleryPost(Base):
    # ... existing fields ...
    comments_count = Column(Integer, default=0)
```
并在 Alembic 生成 migration 脚本：
```bash
alembic revision --autogenerate -m "add gallery comments"
alembic upgrade head
```

## 3. 后端 API 设计 (FastAPI)

### 3.1 DTO Schemas
在 `src/web_api/schemas/gallery_schema.py` 中增加：
```python
class CommentCreate(BaseModel):
    content: str = Field(..., max_length=500, min_length=1)

class CommentUserResponse(BaseModel):
    id: int
    author_name: str # 复用前端现有的“首字母生成头像”逻辑，无需 avatar 字段

class GalleryCommentResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    user: CommentUserResponse

class PaginatedCommentResponse(BaseModel):
    items: List[GalleryCommentResponse]
    total: int
    page: int
    size: int
```
同时在 `GalleryPostResponse` 中增加 `comments_count: int`。

### 3.2 路由 endpoints
在 `src/web_api/routers/gallery.py` 中增加两个接口，并修改现有逻辑：

**1. 组装逻辑补充**
修改 `_build_post_responses` 函数，将 `GalleryPost.comments_count` 映射到 `GalleryPostResponse` 中返回。

**2. 发布评论 (POST `/api/gallery/posts/{post_id}/comments`)**
- **权限**：依赖 `get_current_user` 校验 JWT Token。
- **逻辑**：
  1. **防刷校验**：使用 Redis 锁（如 `SETNX`）限制单个用户每 5~10 秒只能发布一条评论。
  2. 校验 `post_id` 对应的帖子是否存在且 `is_active=True`。
  3. 插入 `GalleryComment` 记录。
  4. 原子增加 `GalleryPost.comments_count`：
     ```python
     stmt = update(GalleryPost).where(GalleryPost.id == post_id)\
                               .values(comments_count=GalleryPost.comments_count + 1)
     await session.execute(stmt)
     ```
  5. 返回新建的 `GalleryCommentResponse`。

**3. 获取评论列表 (GET `/api/gallery/posts/{post_id}/comments`)**
- **权限**：公开访问。
- **参数**：`page: int = 1`, `size: int = 20`
- **逻辑**：
  1. 按照 `created_at` 降序 (DESC) 获取 `is_active=True` 的评论。
  2. `joinedload(GalleryComment.user)` 以避免 N+1 查询问题。
  3. 返回 `PaginatedCommentResponse`。

## 4. 前端交互设计 (Vue3 + TailwindCSS)

主要修改文件：`frontend/src/views/Gallery.vue`

### 4.1 UI 结构改造
**0. 图标导入**
在 `<script setup>` 顶部引入 `MessageCircle` 图标：
```typescript
import { ..., MessageCircle } from 'lucide-vue-next'
```

**1. Mobile 端底部交互栏 (Bottom Interaction Bar)**
在现有的 Like / Dislike 旁边，增加 Comment 按钮：
```html
<button @click="showCommentInput = true" class="flex items-center gap-1.5 transition-all text-slate-300">
  <MessageCircle :size="22" />
  <span class="text-sm font-medium">{{ currentPost.comments_count }}</span>
</button>
```

**2. Desktop 端交互按钮区**
在现有的按钮行中，增加评论按钮。

**3. 评论列表展示区**
在作品详细信息（Info Area）的下方，扩展一个展示区域 `<div class="comments-section">`：
- **桌面端**：使用 `overflow-y-auto flex-1` 限制高度并允许内部滚动。
- **移动端**：无需额外设滚动属性，直接跟随 `.mobile-full-modal` 全局滚动即可；但需在底部预留出 `safe-area-bottom`（如 `padding-bottom: 80px`），防止列表底部被固定在下方的交互栏遮挡。
- 内部展示：
  - 评论总数 Header
  - `v-for="comment in comments"` 渲染的评论列表（自动生成头像、昵称、内容、时间）。
  - 底部显示“加载更多”按钮或基于 `IntersectionObserver` 的无限滚动。

**4. 弹出式输入框 (Popup Input Box)**
- 在 `Gallery.vue` 模板最后引入一个 `<a-modal>` 或底层滑动弹窗（Action Sheet，移动端友好）。
- 包含一个 `<textarea v-model="newComment" maxlength="500">` 以及“发送”按钮。
- 发送成功后，乐观更新（Optimistic Update）当前列表，将新评论 `unshift` 到列表头部，并将 `comments_count++`。

### 4.2 状态管理与 API 对接
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

## 5. 最佳实践与架构红线考量
根据 `allbot-gallery-storage` 规范：
1. **防并发刷量限制**：必须在 POST 接口显式使用 Redis 锁（如 `SETNX`，设置 5 秒 TTL）限制用户的发评频率，防范脚本水军。
2. **原子更新防覆盖**：`comments_count` 必须通过 SQL 层面的原子更新 `values(comments_count=GalleryPost.comments_count + 1)` 执行，绝对不能在 Python 内存中取值后计算写回，避免高并发下数据错乱。
3. **性能优化**：通过保留 `comments_count` 冗余字段，避免了在获取热门列表时进行大规模的 COUNT 聚合查询。
4. **数据完整性**：在外键层面通过 `ondelete="CASCADE"`，在业务层面通过 `is_active` 软删除，共同保障数据的一致性和可回溯性。