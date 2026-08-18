---
name: "allbot-gallery-storage"
description: "处理 Gallery 投稿/重复投稿、点赞点踩/收藏/评论、提示词解锁、一键应用、举报治理，以及 R2 媒体 404、预签 URL、CORS、缩略图、对象迁移和存储生命周期。社区数据或用户可见媒体异常时使用。"
---

# AllBot Gallery 与对象存储

修改 Gallery、R2、媒体 URL、apply-context、提示词解锁或社区治理时必须加载
本技能。异常排查叠加 `allbot-diagnosing-bugs`，新增行为叠加 `allbot-tdd`，
涉及扣费叠加 `allbot-billing-auth`。

## 1. 按需阅读

| 场景 | 必读事实源 |
| --- | --- |
| 社区、互动、举报、媒体和 apply-context | `docs/子模块_社区与存储_gallery_storage.md` |
| 业务展示与模板语义 | `docs/business/03_BIZ_社区广场与社交互动板块.md` |
| R2/legacy 迁移与运维 | `allbot-ops-deployment`、相关 `scripts/*r2* --help` |
| QQCC 修仙市集 | `allbot-qqcc-lazy-bot` |
| 计费和幂等 | `allbot-billing-auth` |

动态枚举与迁移命令只放专项文档。

## 2. 稳定模块边界

- 投稿、互动和错误 facade 位于 `src/core/gallery_*`；默认依赖通过
  `gallery_core_dependencies.py` 注入。
- feed SQL 拼装位于 `src/services/gallery_feed_queries.py`，不得回写 core。
- Web Gallery router/service/presenter 负责用户响应和展示转换；对象存储
  探测不能混在长数据库事务中。
- `/api/gallery/posts/{post_id}/apply-context` 是 Web 模板应用事实入口，
  必须从 `History` 还原请求语义，而不是只看输出展示字段。
- QQCC 市集是轻量 Bot adapter，不复制 Web feed/query 规则，也不注册主
  Bot 完整 Gallery handler。

## 3. 业务不变量

- 投稿必须尊重 `History.allow_contribute`，模板应用结果和 QQCC 自生成结果
  不得再次投稿。
- like/dislike/apply 的不变量是互斥 reaction、幂等 apply 和原子计数。
  reaction 修改前取 `(user_id, post_id)` advisory transaction lock；DB
  使用 reaction/apply 两个 partial unique index。
- 投稿使用 `(task_id, user_id)` unique、同粒度 advisory lock 和显式
  conflict target/`RETURNING`；只有 created/reactivated 才更新 History、贡献数、
  限额和媒体 side effect。
- migration 前先运行 `scripts/audit_gallery_consistency.py`；默认 dry-run。
  修复与在线索引 migration 分开，残留冲突必须 fail closed。
- 评论创建、分页和计数保持限频与原子更新；帖子并发下架时整笔回滚，不能
  留下脏评论。
- 未解锁 prompt 在列表和详情必须由服务端遮罩。提示词解锁以
  `gallery_prompt_unlocks(user_id, post_id)` 为幂等锚点，买家扣 1 灵石和
  作者入账同事务；作者查看自己的内容不扣费。
- 举报 reason 使用当前 API allowlist；同一举报人和帖子唯一。Dashboard
  下架必须同步 `GalleryPost.is_active=False` 与同作者/任务 History 的
  `is_public=False`，并在同事务收口相关 pending 举报。
- 用户级封禁下架同样同步全部帖子、History 与 pending 举报。用户硬删除投稿
  时，必须先把该作品 pending 举报以 `user_deleted` 收口为 resolved，保留
  举报快照供 Dashboard 已处理列表查看，再清理互动、提示词解锁和评论。
- `my-favorites` 和 `my-prompt-unlocks` 是现有互动/解锁记录的视图，不新增
  重复收藏或解锁表。
- 关注/粉丝方向必须保持清楚：我的关注按 follower 查询，我的粉丝按
  followee 查询；粉丝项的 `is_following` 表示当前用户是否回关。

## 4. apply-context

- Web apply-context 完整 prompt 仅限作者/已解锁用户；否则服务端返回 403。
- 每类任务的支持范围、必要重新上传素材和历史兼容映射以 Gallery 专项文档
  和 focused tests 为准。
- Wan22 拼接记录和当前关闭的 `i2i_draw` 必须由服务端拒绝 apply-context，
  不能只隐藏前端按钮。
- 各模板的输入顺序、复用素材、History context 与禁用理由属于公开响应契约，
  修改时同步前端 presenter 和回归测试。
- H3 仅 I2V/FLF2V 可投稿；应用锁定 `_minimax_h3_context`、重传 1/2 张图且不复用原图，
  缺上下文以 `minimax_h3_context_missing` 拒绝。
- QQCC 原生应用只承接安全单图模板，并传 `source_post_id`、
  `allow_contribute=False`、`client_type=bot:qqcc`；复杂模板只返回 Web
  handoff。

## 5. 媒体与 R2 红线

- 正式 Web/Dashboard 只返回当前 R2/S3 短签、公网 URL、空值或
  `pending_result`，不能生成 legacy MinIO URL。
- 新成功 History 应物化标准 R2 原文件和缩略图；对象 key 兼容候选顺序和
  backfill 细节以专项文档/脚本为准。
- 列表热路径不得对每条媒体做公网 `HEAD`，也不得在持有 DB 事务时等待 R2
  探测或短签。集合路径复用 existence cache/singleflight。
- owner `/result` 的延迟敏感探测可以使用连接池和按 key singleflight，但
  公网 miss 仍只能回退当前 R2/S3；视频未就绪返回 `pending_result`。
- Dashboard History 列表分别返回原件与缩略图。图片先加载缩略图；视频列表
  不挂载原视频，点击后才加载，避免批量下载。
- Telegram Gallery 优先使用 `GalleryPost.telegram_file_id`；失效时只从
  当前 Gallery R2/S3 resolver 下载目标作品并刷新。测试 Bot 不持久化缓存。
- Worker sidecar 上传必须等 R2 put 成功后才向 Central `/complete`；不能把
  本地 spool 成功误写成已交付。
- 存储异常应降级用户展示但保留可恢复信息；不能因一次慢探测阻断整个 feed。
- R2 审计、backfill、缩略图补齐和 shadow 同步默认 dry-run。执行前明确
  env、bucket、范围、cursor、方向和授权，不得把生产 env 或预签 URL输出。

## 6. 公开接口重点

- `POST /api/gallery/posts/{post_id}/interact`
- `POST /api/gallery/posts/{post_id}/comments`
- `POST /api/gallery/posts/{post_id}/reports`
- `POST /api/gallery/posts/{post_id}/prompt-unlock`
- `GET /api/gallery/posts/{post_id}/apply-context`
- `GET /api/gallery/my-prompt-unlocks`
- `GET /api/users/search`、`/api/users/me/follows`、`/api/users/me/followers`
- Dashboard 举报查询/处理与用户级封禁下架接口

变更字段、状态码或幂等语义时先检查调用方和类型定义，避免只改 router。

## 7. 最小验证

- 投稿：重复投稿、`allow_contribute=False`、多 History 同步和硬删除外键。
- 互动/评论：并发 like/dislike、原子计数、限频和并发下架回滚。
- schema：仓库 migration 能创建目标 unique/partial unique，重复数据预检和
  counter 重算可重复执行；不能只在 ORM/SQLite fake 中通过。
- 解锁：首次扣费、重复幂等、并发唯一冲突、作者免扣和个人列表。
- 举报：非法 reason、重复 409、媒体预览、单帖/用户级下架和 pending 举报
  同事务收口。
- apply-context：payload、输入顺序、历史兼容、未解锁 403、禁用记录 400。
- 存储：R2 hit/miss、短签/空值/`pending_result`、无 legacy URL、缩略图
  fallback、慢对象存储时 DB 事务已释放。
- QQCC：file ID fallback、安全单图原生应用、复杂模板 Web handoff、不预增
  apply count。
- 交付时说明是否触及公开 API、扣费、R2 生命周期、迁移脚本或生产运行态；
  本地测试不得描述成已完成线上 backfill。
