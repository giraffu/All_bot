# 社区投稿、排行榜与一键应用功能 - 详细实施方案

本文档基于最新需求更新，去除了手动选择标签的繁琐步骤，并为视频增加了元数据支持。本方案完全复用现有的核心并发、排队和计费机制。

---

## 一、 数据库表结构变更 (models.py)

需在 `src/database/models.py` 中新增以下两张表，并使用 Alembic 生成迁移脚本：

### 1. `GalleryPost` (社区投稿表)
```python
class GalleryPost(Base):
    __tablename__ = "gallery_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), ForeignKey("tasks.id"), index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)  # internal_user_id
    
    # 元数据
    media_type = Column(String(20)) # 'image' 或 'video'
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True) # 视频时长(秒)
    
    # 标签 (JSON 格式存储列表)
    tags = Column(Text, default="[]") 
    
    # 统计数据
    likes_count = Column(Integer, default=0)
    dislikes_count = Column(Integer, default=0)
    applied_count = Column(Integer, default=0)
    
    is_active = Column(Boolean, default=True) # 审核/下架控制
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", backref="gallery_posts")
    task = relationship("Task", backref="gallery_post")
```

### 2. `UserInteraction` (用户互动记录表)
```python
class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), index=True)
    post_id = Column(Integer, ForeignKey("gallery_posts.id"), index=True)
    action_type = Column(String(20)) # 'like', 'dislike', 'apply'
    created_at = Column(DateTime, default=datetime.now)
    
    # 防止单个用户对同一个帖子重复点赞/点踩
    # 注意：'apply' 可以多次，需要业务代码额外处理，或将 'apply' 独立约束
```

---

## 二、 核心逻辑优化：自动标签与元数据

### 1. 自动附加标签逻辑
取消用户的下拉选择，改为系统在点击“一键投稿”时静默生成：
*   **基础类型标签**：从 `Task.task_type` 映射。例如 `face_video` -> `#视频换脸`，`i2i_pro` -> `#幻想换脸`。
*   **LoRA 模型提取**：当 `task_type` 为带有附加模型的图生视频模式时，解析 `Task.params` (JSON)，提取其中的 LoRA 列表。例如，如果 `params["loras"]` 包含 `["cyberpunk_v2", "anime_style"]`，则自动追加标签 `#cyberpunk_v2` `#anime_style`。
*   **组合结果**：`["#视频换脸", "#cyberpunk_v2"]`，将其序列化后存入 `GalleryPost.tags`。

### 2. 视频元数据提取 (时长与分辨率)
*   **来源**：生成视频时，前端或 Bot 传入了对应的参数，通常记录在 `Task.params` 中（例如 `width: 1080, height: 1920, frames: 120, fps: 24`）。
*   **计算**：
    *   分辨率：直接读取 `params["width"]` 和 `params["height"]`。
    *   时长：通过 `frames / fps` 计算得出（例如 120/24 = 5秒）。如果 `params` 中没有直接保存这些字段，则可以通过 Bot 上传到 Telegram 时获取的 `Video` 对象的元数据来回填。

---

## 三、 交互与展示流程

### 1. 极简投稿流程
*   在生成任务成功的最终回复中，增加一个 Inline 按钮：`[🚀 一键投稿至广场]`。
*   用户点击后，Bot 后台读取 `Task`，自动提取标签和元数据，写入 `GalleryPost`，并弹窗提示 (CallbackQuery `answer()`)：“投稿成功！已自动添加标签：#视频换脸 #动漫”。（全程不阻塞，无感体验）。

### 2. 广场排行榜与面板
*   主菜单增加 `[🏆 发现/排行榜]`。
*   发送带有三个选项的导航消息：`[🔥 最新投稿] [❤️ 最多点赞] [🪄 最多应用]`。
*   用户点击选项后，按对应字段（如 `created_at DESC` 或 `likes_count DESC`）查询 `GalleryPost`。
*   **卡片渲染展示**：
    *   发送对应的图片或视频。
    *   **Caption (文本)**：
        ```text
        作者：@username
        标签：#图生视频 #赛博朋克
        规格：5秒 | 1080x1920

        ❤️ 120  |  👎 3  |  🪄 45 次应用
        ```
    *   **Inline 键盘**：
        ```text
        [👍 点赞] [👎 点踩]
        [🪄 一键应用]
        [⬅️ 上一个] [➡️ 下一个] [❌ 退出]
        ```

---

## 四、 一键应用 (One-click Apply) FSM 注入机制

这是该功能的**核心技术点**。为了不重写生成逻辑，我们采用“状态机（FSM）数据注入与跳步”方案：

1. **点击捕获**：用户在广场点击 `[🪄 一键应用]`，Callback 携带 `post_id`。
2. **数据溯源**：
   *   通过 `post_id` 查询 `GalleryPost` -> `Task`。
   *   提取原任务的 `prompt`、`loras`、`input_file` (MinIO Object Key)、`width`、`height` 等核心参数。
3. **FSM 上下文注入**：
   *   识别原任务对应的 FSM（如 `faceswap_fsm` 或 `video_lora_fsm`）。
   *   将提取到的参数直接赋值给用户的 `context.user_data`。
   *   例如：`context.user_data['template_video'] = original_task.input_file`。
4. **状态跳转**：
   *   正常 FSM 的第一步是让用户“发送模板”，我们直接跳过这一步。
   *   强行将当前用户的状态机置为 `WAIT_FACE_IMAGE`。
   *   回复用户：“*您正在应用热门模板，扣费标准与原模板一致。请直接发送您的人脸照片进行替换！*”
5. **复用底层**：
   *   用户发送人脸后，FSM 按既定逻辑组装 `user_data`，调用 `task_core.submit_generation_task()`。
   *   任务完成后，更新 `UserInteraction` 记录，并将原贴的 `applied_count` + 1。

---

## 五、 开发红线备忘

1. **MinIO 引用传递**：“一键应用”使用的模板文件，绝对不能通过 Bot 下载后再上传。必须直接传递原任务记录在数据库中的 MinIO Object Key。
2. **并发锁与退出**：广场面板的“一键应用”将用户推入 FSM。必须确保在 FSM 的 `unexpected_input` 处理函数中，能正确响应“退出”、“取消”或其他主菜单按钮，避免并发锁卡死（参考 `AGENTS.md` 的 FSM 红线）。
3. **用户 ID 一致性**：`GalleryPost` 和 `UserInteraction` 的 `user_id` 必须是 PostgreSQL 中的 `users.id` (`internal_user_id`)，严禁直接使用 Telegram ID。
