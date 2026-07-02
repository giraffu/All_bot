---
name: "allbot-gallery-storage"
description: "处理对象存储、广场评论收藏、R2 媒体策略与 Web apply-context。当开发作品分享、互动防刷、模板应用和存储生命周期时必须调用本技能。"
---

# AllBot 社区广场与存储体系 (Gallery & Storage)

本技能覆盖社区广场、对象存储与模板应用上下文，不再局限于“投稿 + 点赞 + R2 转存”。

涉及 Gallery、R2、媒体 URL、apply-context 或提示词解锁异常时，叠加 `allbot-diagnosing-bugs` 建立可复现反馈环；新增社区/存储行为时，叠加 `allbot-tdd` 先锁定服务端行为。

## 1. 模块功能描述
- **广场投稿与原创保护**：基于 `History.allow_contribute` 阻断模板套娃再投稿。
- **互动防刷**：`user_interactions` 记录 `like/dislike/apply`，依赖唯一约束与原子更新防止连点覆盖。
- **评论系统**：支持评论创建、分页查询、Redis 限频与 `comments_count` 原子维护。
- **个人视图**：支持 `my-posts`、`my-favorites` 与 `my-prompt-unlocks`；`my-favorites` 从互动记录反查点赞/应用历史，`my-prompt-unlocks` 从提示词解锁记录反查已解锁模板。
- **用户主页与关注关系**：Web 用户公开主页 `GET /api/users/{user_id}/public-profile` 返回公开投稿分页 `posts` 并兼容 `recent_posts`；公开主页详情必须复用 Gallery 提示词解锁能力。`/api/users/me/follows` 与 `/api/users/me/followers` 分别返回我关注的人和关注我的人，粉丝列表的 `is_following` 表示我是否已回关。
- **提示词付费解锁**：Gallery 列表/详情未解锁时只能返回服务端遮罩 prompt；`POST /api/gallery/posts/{post_id}/prompt-unlock` 固定消耗 1 灵石并给作者入账，`gallery_prompt_unlocks.user_id + post_id` 是幂等锚点。
- **Web apply-context**：`/api/gallery/posts/{post_id}/apply-context` 已是模板应用主入口，返回 `prompt`、`negative_prompt`、`lora_name`、`input_file/input_file_url`、`input_files/input_file_urls`、`requested_duration`、`billing_resolution` 等上下文；自由P图 v2 投稿在独立 `free_edit_v2_group` 中展示，一键应用复用并锁定 prompt、重新上传 1/2 张参考图、不展示 LoRA，并按图数提交 single/multi v2 任务；`i2i_draw` 局部重绘当前已在 Web 一键应用关闭，列表/详情返回 `template_apply_disabled_reason="i2i_draw_disabled"`，apply-context 必须 400；旧 `custom_video` / `video_lora` 投稿会把旧分辨率映射为 Wan22 v2 档位，并恢复 canonical `5s/8s/10s` 时长；`wan22_video_v2` 单段投稿可回填正向/负面提示词、分辨率档位与 canonical 时长；LTX `ltx_video`/`ltx_video_flf2v` 从 `_ltx_context` 回填 LoRA、宽高、时长并保留起始帧/终止帧输入顺序；SCAIL-2 `scail2_action_transfer` / `scail2_video_replacement` / `scail2_face_swap_v2` 投稿可作为视频模板，apply-context 只复用原 motion/driving video，复用者必须上传自己的 reference image。
- **Feed 查询边界**：Gallery feed SQL 查询拼装位于 `src/services/gallery_feed_queries.py`；旧 `src/core/gallery_feed_queries.py` 兼容 re-export 已删除，新增查询条件不要回写到 core。LTX 高级图生视频只展示一个 `ltx_video` 入口，投稿/筛选兼容 `ltx_video_flf2v` 历史/执行别名。
- **媒体 URL 策略**：
  - R2 key 候选顺序为标准 `history/{task_id}/original.ext`、原始 object key、raw `output_file`（兼容 `bot-data/...` 前缀镜像）、旧 basename。
  - 正式 Web/Dashboard 运行时已退出 legacy MinIO 回源：默认 `LEGACY_MINIO_READ_FALLBACK_ENABLED=false`，R2 miss 后只能返回当前 R2/S3 短签、空值或 `pending_result`，不得生成 `assets.aivison.it.com` URL。
  - legacy MinIO 只保留给迁移脚本、人工回滚和旧外链排障；新数据仍写 R2，worker 不得写 legacy MinIO。
  - web/bot 新成功历史都应预热标准 R2 原文件和缩略图，只有 web 来源执行用户历史 R2 cache prune。
  - 云正式 worker 可通过本地上传 sidecar 把 `/app/spool` 结果上传 R2，但仍必须等待 R2/S3 put 成功后才调用 Central `/complete`。
  - Gallery 列表热路径不得对每条媒体做公网 `HEAD`；R2 S3 命中时优先返回 R2 S3 短签 URL，避免 `R2_PUBLIC_DOMAIN` 自定义域名 miss 导致前端空白，预签不可用时才退回公网 URL。
  - 列表页缩略图 R2 miss 后应快速返回空值，不做深度探测。
  - 历史详情、Wan22 预览等读路径可短超时探测 R2 公网 URL，公网 miss 但 R2 S3 `HEAD` 命中时可返回 R2 S3 短签 URL。
  - Web owner `/result` 延迟敏感路径仍必须用 R2 公网 HEAD 快探测，R2 warmup 未就绪时图片可短签 storage fallback，视频继续 `pending_result` 等 R2。
  - 缩略图和 `input_file_url` 使用当前 R2 key/短签逻辑。
  - 迁移脚本可使用 `--hotset-profile web-visible-retire-legacy --source-storage legacy --include-input-files` 补齐 Web 可见热集的原文件、缩略图和输入文件。
  - 若只迁移 Gallery 投稿、History 收藏、Gallery like/apply active posts 与 prompt unlock active posts，可追加 `--skip-per-user-recent-history` 并使用独立 cursor，再用 `--source-storage current --generate-missing-thumbnails` 从已补齐到 R2 的原文件生成缺失缩略图。
- **R2 可见热集审计**：只读排查 Web 可见热集在 R2 中还缺什么时，使用 `scripts/audit_visible_hotset_r2_objects.py --env-file .env.cloud.prod --recent-limit 8 --report-dir logs`。默认范围包含每用户最近 8 条可见历史、全部 Gallery post、History 收藏、Gallery like/apply active posts 与 prompt unlock active posts，并默认审计原文件、缩略图和本地 `input_file`。报告会同时区分“运行时 R2 全候选缺失”和“标准 `history/{task_id}/...` key 缺失但 fallback key 命中”，并在 `logs/` 生成 JSON、Markdown 概要和 CSV 缺失附录；脚本只做 R2 `HEAD` 与 DB 只读查询，不上传、不删除、不改 cursor。全量生产审计默认用 `--db-batch-size 1000` 分批读取 History 详情，`--concurrency` 同时控制 R2 HEAD semaphore 与线程池 worker，`--progress-interval` 输出进度，避免大热集黑盒长跑；若只看社区强可见、不含最近 8 条，可追加 `--skip-per-user-recent-history`。
- **Web 读路径性能边界**：历史、用户历史、Gallery 响应构造在慢对象存储/R2 探测/短签生成前应释放只读数据库事务；新增列表或详情读路径时，不要在 DB 事务内等待对象存储探测。云正式已补 Gallery/History 热路径索引，新增查询条件前先确认索引命中。
- **云测试/R2 直连 CORS**：`.env.cloud.test` 可将 `MINIO_*` 兼容变量全部指向 R2 S3 endpoint 与 `user-data-test` 桶；当前云测试应保持 `MINIO_PUBLIC_URL=`，并设置 `R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`。Web owner 视频 `/result` 依赖 R2 公网 URL，`R2_PUBLIC_DOMAIN` 缺失会停在 99% / `pending_result`；若公开域名临时返回 403，图片可走短签 fallback，视频必须优先修复公开域名或实现受控 fallback。旧测试 MinIO 对象镜像到 R2 桶根路径，不能额外加旧桶名前缀，否则历史 `output_file` 无法命中。Web 参考图/视频上传会由浏览器直传 R2，R2 桶 CORS 必须允许当前 Web Origin：`https://web-test.aivison.it.com`、正式 `https://web.aivison.it.com`、正式 Pages 默认域 `https://allbot-web-prod.pages.dev`；若历史 Cloudflare canary 仍保留，可额外允许 `https://web-cf-test.aivison.it.com`/`https://allbot-web-cf-test.pages.dev`。方法 `GET/PUT/HEAD`、`AllowedHeaders=["*"]`、`ExposeHeaders=["ETag"]`。否则前端会报 `Network error during upload`。
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
- **输出**：`source_post_id`、`prompt`、`negative_prompt`、`lora_name`、`input_file_url`、`input_files/input_file_urls`、`requested_duration`、`billing_resolution`、媒体尺寸等
- **Wan22 图生视频兼容**：旧 `custom_video` / `video_lora` 的 `512p/720p/1024p` 分别映射为 `preview/standard/hd`，`0.36 MP - Small` 映射为 `small`，历史 canonical duration 恢复为 `5s/8s/10s`，缺失或非 canonical 时回退 5 秒；`video_lora` 需兼容从 prompt 的 `[模型: xxx]` 解析 `lora_name`；`wan22_video_v2` 单段投稿从 `_wan22_context` 恢复 `wan22_negative_prompt`、`wan22_resolution_preset` 与 `wan22_duration_seconds`。
- **LTX 高级图生视频兼容**：`ltx_video` 与执行别名 `ltx_video_flf2v` 都按同一个高级图生视频能力展示；首尾帧 tag、段号/拼接 tag 从 `_ltx_context` 或 stitch payload 补齐，apply-context 从 `_ltx_context` 回填 `lora_items`、宽高和请求时长。
- **SCAIL-2 视频模板**：`scail2_action_transfer` / `scail2_video_replacement` / `scail2_face_swap_v2` 投稿进入 Web 模板应用时，`History.input_file` 的第二个输入即 motion/driving video 是唯一可复用输入；`input_file` 旧字段也指向该视频以兼容旧前端。缺失该视频时列表/详情应返回 `template_apply_supported=false`、`template_apply_disabled_reason="missing_scail2_motion_video"`，apply-context 入口必须 400。
- **局部重绘禁用**：`i2i_draw` 投稿仍可作为历史/广场作品展示，但 Web 一键应用已关闭；列表/详情必须返回 `template_apply_supported=false` 与 `template_apply_disabled_reason="i2i_draw_disabled"`，apply-context 入口必须 400。
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
- `apply-context` 必须服务端拒绝 Wan22 stitched 记录和 Web 已关闭的 `i2i_draw` 记录，不能只依赖前端按钮禁用。
- 存储/R2 异常只能降级，不能阻断广场主流程。
- Gallery 列表热路径不得恢复为“持有 DB 只读事务 + 每条媒体公网 HEAD 探测”的模式。
- 投稿删除/下架必须兼容同一 `task_id + user_id` 下多条 `History`；不得用 `scalar_one_or_none()` 假设唯一。上架时只允许主 history 公开，删除/下架时所有匹配 history 都要 `is_public=False`。硬删除 `GalleryPost` 前必须同步清理 `user_interactions`、`gallery_prompt_unlocks` 与 `gallery_comments`，避免提示词解锁记录外键阻断删除。
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
- 覆盖 apply-context 返回的 `requested_duration`、`billing_resolution`、`negative_prompt`、`input_file_url`、`input_files/input_file_urls` 正确性；旧图生视频需额外覆盖 `5s/8s/10s` 恢复、`512/720/1024 -> preview/standard/hd`、`0.36 MP - Small -> small` 和 LoRA prompt 解析，v2 单段需覆盖 `_wan22_context` 负面词/档位/时长回填，LTX 需覆盖首尾帧 tag、两张输入图顺序、`ltx_video_flf2v` alias 与 `_ltx_context` 回填，SCAIL-2 需覆盖只复用 motion video 与缺失 motion video 400，Wan22 stitched 与 Web 关闭的 `i2i_draw` 需覆盖 apply-context 400 与列表禁用字段。
- 覆盖后台封禁投稿并批量下架时的用户状态、帖子状态与多条 `History` 同步。
- 覆盖 R2 hit、R2 miss 后当前 R2/S3 短签或空值/`pending_result`、不得返回 legacy URL、缩略图 fallback、对象存储慢响应时释放 DB 只读事务后的响应路径。
- 覆盖已下架投稿硬删除时仍会清理提示词解锁记录、互动记录与评论记录，尤其是已被他人解锁提示词的投稿。
