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
- **个人视图**：支持 `my-posts`、`my-favorites` 与 `my-prompt-unlocks`；`my-favorites` 从互动记录反查点赞/应用历史，`my-prompt-unlocks` 从提示词解锁记录反查已解锁模板。
- **提示词付费解锁**：Gallery 列表/详情未解锁时只能返回服务端遮罩 prompt；`POST /api/gallery/posts/{post_id}/prompt-unlock` 固定消耗 1 灵石并给作者入账，`gallery_prompt_unlocks.user_id + post_id` 是幂等锚点。
- **Web apply-context**：`/api/gallery/posts/{post_id}/apply-context` 已是模板应用主入口，返回 `prompt`、`negative_prompt`、`lora_name`、`input_file_url`、`requested_duration`、`billing_resolution` 等上下文；旧 `custom_video` / `video_lora` 投稿会把旧分辨率映射为 Wan22 v2 档位，并恢复 canonical `5s/8s/10s` 时长；`wan22_video_v2` 单段投稿可回填正向/负面提示词、分辨率档位与 canonical 时长。
- **Feed 查询边界**：Gallery feed SQL 查询拼装位于 `src/services/gallery_feed_queries.py`；`src/core/gallery_feed_queries.py` 仅是兼容 re-export，新增查询条件不要回写到 core。
- **媒体 URL 策略**：优先返回 R2 公网链接，找不到对象时回退原始存储路径；Web owner `/result` 延迟敏感路径必须用 R2 公网 HEAD 快探测，R2 warmup 未就绪时图片可短签 MinIO fallback，视频继续 `pending_result` 等 R2，缩略图也有独立 key 解析逻辑。
- **后台治理**：Dashboard 广场管理可显示投稿用户，列表接口 `GET /api/gallery/all` 支持 `username`、`prompt_contains`、`prompt_max_length` 治理筛选，并通过 `/api/gallery/users/{user_id}/ban-submissions-and-takedown` 一键设置 `is_submission_banned=True`、下架该用户全部 `GalleryPost`，同步取消相关 `History.is_public`。

## 2. 输入输出规范

### 社区互动
- **接口**：`POST /api/gallery/posts/{post_id}/interact`
- **输入**：`post_id`、`action=like|dislike`
- **输出**：更新后的互动状态与计数

### 提示词解锁
- **接口**：`POST /api/gallery/posts/{post_id}/prompt-unlock`
- **输出**：完整 `prompt`、`current_credits`、`already_unlocked` 与 prompt 解锁状态字段。
- **个人列表**：`GET /api/gallery/my-prompt-unlocks` 返回当前用户已解锁提示词的活跃帖子，供修仙笔记“提示词模版”tab 使用。

### 评论
- **接口**：`POST /api/gallery/posts/{post_id}/comments`
- **输入**：评论内容
- **输出**：评论实体与作者信息

### 应用上下文
- **接口**：`GET /api/gallery/posts/{post_id}/apply-context`
- **输出**：`source_post_id`、`prompt`、`negative_prompt`、`lora_name`、`input_file_url`、`requested_duration`、`billing_resolution`、媒体尺寸等
- **Wan22 图生视频兼容**：旧 `custom_video` / `video_lora` 的 `512p/720p/1024p` 分别映射为 `preview/standard/hd`，`0.36 MP - Small` 映射为 `small`，历史 canonical duration 恢复为 `5s/8s/10s`，缺失或非 canonical 时回退 5 秒；`video_lora` 需兼容从 prompt 的 `[模型: xxx]` 解析 `lora_name`；`wan22_video_v2` 单段投稿从 `_wan22_context` 恢复 `wan22_negative_prompt`、`wan22_resolution_preset` 与 `wan22_duration_seconds`。
- **拼接记录禁用**：所有 Wan22 stitched 记录（旧 `custom_video` / `video_lora` 与 `wan22_video_v2`）都不能返回 apply-context，接口应返回 400，列表/详情响应需给出 `template_apply_supported=false` 与 `template_apply_disabled_reason="wan22_stitched"`。

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
- 未解锁提示词不能通过 Gallery 列表/详情响应返回完整内容；必须服务端遮罩，并通过 `prompt_is_masked` 等字段告知前端展示状态。
- 提示词解锁必须以 `gallery_prompt_unlocks` 唯一记录为幂等锚点；扣买家 1 灵石和给作者 +1 灵石必须同事务完成。
- `apply-context` 必须优先从 `History` 还原请求语义，不能只看展示用输出元数据。
- `apply-context` 必须服务端拒绝 Wan22 stitched 记录，不能只依赖前端按钮禁用。
- 存储/R2 异常只能降级，不能阻断广场主流程。
- 投稿删除/下架必须兼容同一 `task_id + user_id` 下多条 `History`；不得用 `scalar_one_or_none()` 假设唯一。上架时只允许主 history 公开，删除/下架时所有匹配 history 都要 `is_public=False`。
- 用户级批量下架不得只改 `GalleryPost.is_active`；必须同步把该用户投稿关联的 `History.is_public` 置为 `False`，避免旧公开资源入口继续可见。

## 4. 边界条件处理
- 帖子并发下架时，评论创建必须整体回滚而不是留下脏评论。
- `my-favorites` 只是互动记录视图，不要额外维护一张重复收藏表。
- `my-prompt-unlocks` 是提示词解锁记录视图；重复解锁同一 `post_id` 不得重复扣费，作者查看自己的帖子不创建解锁记录。
- Telegram 端 `gallery_apply_fsm` 仅是兼容路径，新的模板应用设计应优先围绕 Web workbench 与 apply-context。

## 5. 测试要求
- 覆盖重复投稿与 `allow_contribute=False` 拦截。
- 覆盖并发点赞/点踩一致性。
- 覆盖评论限频、并发下架回滚、分页查询。
- 覆盖提示词解锁首次扣费、重复解锁幂等、唯一约束并发冲突回滚、作者自看免扣费与 `my-prompt-unlocks` 列表。
- 覆盖 apply-context 返回的 `requested_duration`、`billing_resolution`、`negative_prompt`、`input_file_url` 正确性；旧图生视频需额外覆盖 `5s/8s/10s` 恢复、`512/720/1024 -> preview/standard/hd`、`0.36 MP - Small -> small` 和 LoRA prompt 解析，v2 单段需覆盖 `_wan22_context` 负面词/档位/时长回填，Wan22 stitched 需覆盖 apply-context 400 与列表禁用字段。
- 覆盖后台封禁投稿并批量下架时的用户状态、帖子状态与多条 `History` 同步。
