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
- **Web apply-context**：`/api/gallery/posts/{post_id}/apply-context` 已是模板应用主入口，返回 `prompt`、`lora_name`、`input_file_url`、`requested_duration`、`billing_resolution` 等上下文。
- **媒体 URL 策略**：优先返回 R2 公网链接，找不到对象时回退原始存储路径；缩略图也有独立 key 解析逻辑。

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

## 3. 核心红线
- 捕获互动类 `IntegrityError` 前必须先 `flush()`。
- 点赞、点踩、评论计数必须走数据库原子更新，不能先查再加。
- `apply` 次数不能在前端点击时预增，必须等任务真正进入成功链路后再记账。
- `apply-context` 必须优先从 `History` 还原请求语义，不能只看展示用输出元数据。
- 存储/R2 异常只能降级，不能阻断广场主流程。

## 4. 边界条件处理
- 帖子并发下架时，评论创建必须整体回滚而不是留下脏评论。
- `my-favorites` 只是互动记录视图，不要额外维护一张重复收藏表。
- Telegram 端 `gallery_apply_fsm` 仅是兼容路径，新的模板应用设计应优先围绕 Web workbench 与 apply-context。

## 5. 测试要求
- 覆盖重复投稿与 `allow_contribute=False` 拦截。
- 覆盖并发点赞/点踩一致性。
- 覆盖评论限频、并发下架回滚、分页查询。
- 覆盖 apply-context 返回的 `requested_duration`、`billing_resolution`、`input_file_url` 正确性。
