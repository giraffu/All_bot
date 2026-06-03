---
name: "allbot-gallery-storage"
description: "处理对象存储、广场评论收藏、R2 媒体策略与 Web apply-context。当开发作品分享、互动防刷、模板应用和存储生命周期时必须调用本技能。"
---

# AllBot 社区广场与存储体系 (Gallery & Storage)

本技能覆盖社区广场、对象存储与模板应用上下文，不再局限于“投稿 + 点赞 + R2 转存”。

## 1. 模块功能描述
- **广场投稿与原创保护**：基于 `History.allow_contribute` 阻断模板套娃再投稿。
- **互动防刷**：`user_interactions` 记录 `like/dislike/apply`，依赖唯一约束与原子更新防止连点覆盖。
- **评论系统**：支持评论创建、分页查询、Redis 限频与 `comments_count` 原子维护。
- **个人视图**：支持 `my-posts` 与 `my-favorites`，后者从互动记录反查点赞/应用历史。
- **Web apply-context**：`/api/gallery/posts/{post_id}/apply-context` 已是模板应用主入口，返回 `prompt`、`lora_name`、`input_file_url`、`requested_duration`、`billing_resolution` 等上下文；旧 `custom_video` / `video_lora` 投稿会把旧分辨率映射为 Wan22 v2 档位并固定 5 秒。
- **Feed 查询边界**：Gallery feed SQL 查询拼装位于 `src/services/gallery_feed_queries.py`；`src/core/gallery_feed_queries.py` 仅是兼容 re-export，新增查询条件不要回写到 core。
- **媒体 URL 策略**：优先返回 R2 公网链接，找不到对象时回退原始存储路径；Web owner `/result` 延迟敏感路径必须用 R2 公网 HEAD 快探测，R2 warmup 未就绪时图片可短签 MinIO fallback，视频继续 `pending_result` 等 R2，缩略图也有独立 key 解析逻辑。
- **后台治理**：Dashboard 广场管理可显示投稿用户，列表接口 `GET /api/gallery/all` 支持 `username`、`prompt_contains`、`prompt_max_length` 治理筛选，并通过 `/api/gallery/users/{user_id}/ban-submissions-and-takedown` 一键设置 `is_submission_banned=True`、下架该用户全部 `GalleryPost`，同步取消相关 `History.is_public`。

## 2. 输入输出规范

### 社区互动
- **接口**：`POST /api/gallery/posts/{post_id}/interact`
- **输入**：`post_id`、`action=like|dislike`
- **输出**：更新后的互动状态与计数

### 评论
- **接口**：`POST /api/gallery/posts/{post_id}/comments`
- **输入**：评论内容
- **输出**：评论实体与作者信息

### 应用上下文
- **接口**：`GET /api/gallery/posts/{post_id}/apply-context`
- **输出**：`source_post_id`、`prompt`、`lora_name`、`input_file_url`、`requested_duration`、`billing_resolution`、媒体尺寸等
- **旧图生视频兼容**：`512p/720p/1024p` 分别映射为 `preview/standard/hd`，历史 duration 一律恢复为 5 秒，`video_lora` 需兼容从 prompt 的 `[模型: xxx]` 解析 `lora_name`。

### 后台广场列表治理筛选
- **接口**：`GET /api/gallery/all`
- **输入**：`username` 可按 `User.username/full_name` 模糊筛选，`prompt_contains` 对 `History.prompt` 模糊匹配，`prompt_max_length` 按去除首尾空白后的提示词字符数过滤。
- **输出**：分页投稿列表。

### 后台投稿封禁与批量下架
- **接口**：`POST /api/gallery/users/{user_id}/ban-submissions-and-takedown`
- **输入**：`reason` 可选；为空时使用默认封禁提示。
- **输出**：`affected_posts`、`affected_histories`、`is_submission_banned`、封禁原因与时间。

## 3. 核心红线
- 捕获互动类 `IntegrityError` 前必须先 `flush()`。
- 点赞、点踩、评论计数必须走数据库原子更新，不能先查再加。
- `apply` 次数不能在前端点击时预增，必须等任务真正进入成功链路后再记账。
- `apply-context` 必须优先从 `History` 还原请求语义，不能只看展示用输出元数据。
- 存储/R2 异常只能降级，不能阻断广场主流程。
- 投稿删除/下架必须兼容同一 `task_id + user_id` 下多条 `History`；不得用 `scalar_one_or_none()` 假设唯一。上架时只允许主 history 公开，删除/下架时所有匹配 history 都要 `is_public=False`。
- 用户级批量下架不得只改 `GalleryPost.is_active`；必须同步把该用户投稿关联的 `History.is_public` 置为 `False`，避免旧公开资源入口继续可见。

## 4. 边界条件处理
- 帖子并发下架时，评论创建必须整体回滚而不是留下脏评论。
- `my-favorites` 只是互动记录视图，不要额外维护一张重复收藏表。
- Telegram 端 `gallery_apply_fsm` 仅是兼容路径，新的模板应用设计应优先围绕 Web workbench 与 apply-context。

## 5. 测试要求
- 覆盖重复投稿与 `allow_contribute=False` 拦截。
- 覆盖并发点赞/点踩一致性。
- 覆盖评论限频、并发下架回滚、分页查询。
- 覆盖 apply-context 返回的 `requested_duration`、`billing_resolution`、`input_file_url` 正确性；旧图生视频需额外覆盖固定 5 秒、`512/720/1024 -> preview/standard/hd` 和 LoRA prompt 解析。
- 覆盖后台封禁投稿并批量下架时的用户状态、帖子状态与多条 `History` 同步。
