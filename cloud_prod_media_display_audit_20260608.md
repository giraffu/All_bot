# 云正式媒体展示链路核查报告

生成时间：2026-06-08 20:47 CST  
范围：只读代码查看、配置核验、生产聚合查询、日志聚合、service 级只读实测。未执行部署、迁移、上传、删除、Nginx reload 或服务重启。

## 1. 结论摘要

结论是：用户描述的现象存在，而且可以拆成两个不同问题。

| 场景 | 核验结论 | 主要原因 |
| :--- | :--- | :--- |
| 修仙市集「最新」 | 相对快。service 实测首轮 3.8s，后续约 0.78s；20 条里 19 条返回 R2 presigned URL，1 条 legacy assets。 | 最新页大部分对象已经在 R2 `user-data-prod`，只有少量落 legacy。 |
| 修仙市集「最多点赞」 | 明显慢。service 实测 12.9-13.6s；20 条 media 和 thumbnail 全部返回 `assets.aivison.it.com` legacy。 | 高赞内容集中在 2026-04 到 2026-05 的历史投稿，尚未规整到 R2 标准 key/缩略图。 |
| 修仙市集「最多使用」 | 同样慢。service 实测 11.8-13.7s；20 条 media 和 thumbnail 全部 legacy。 | 与高赞类似，排序选中了旧投稿集合。 |
| 修仙笔记 | 也会慢，但根因不完全一样。最近 5 个活跃用户样本中，前 4 个用户最近 8 条 media 全是 R2，但 thumbnail 全空，接口仍耗时 6.6-12.6s。 | 很多未投稿的 bot 生成历史没有标准缩略图，列表解析缩略图时连续 R2/legacy/current miss 探测；部分记录还会 legacy fallback。 |

你的怀疑大方向是对的，但桶的理解需要修正：

- 当前云正式没有发现「历史投稿专用的另一个 R2 bucket」。实际正式 R2 bucket 是 `user-data-prod`。
- 历史内容慢，不是因为历史内容在另一个 R2 桶，而是大量旧对象仍只在 legacy 本地 MinIO，浏览器通过 `https://assets.aivison.it.com` 经 VPS/Tailscale 回源。
- 新生成内容现在会进 R2 兼容桶 `user-data-prod`；但未投稿的 bot 历史通常没有被标准化复制为 `history/{task_id}/original.*` 和 `history/{task_id}/thumb.*`，所以修仙笔记仍会慢。

## 2. 当前正式配置事实

云 Web API 当前配置事实：

| 配置 | 当前值/状态 |
| :--- | :--- |
| `MINIO_ENDPOINT` | Cloudflare R2 S3 endpoint |
| `MINIO_BUCKET` / `MINIO_RESULT_BUCKET` / `MINIO_TEMPLATE_BUCKET` | `user-data-prod` |
| `MINIO_PUBLIC_URL` | 空 |
| `R2_BUCKET` | `user-data-prod` |
| `R2_PUBLIC_DOMAIN` | `https://r2.aivison.it.com` |
| `LEGACY_MINIO_ENDPOINT` | `100.99.254.53:9000` |
| `LEGACY_MINIO_BUCKET` | `bot-data` |
| `LEGACY_MINIO_RESULT_BUCKET` | `comfyui-temp` |
| `LEGACY_MINIO_PUBLIC_URL` | `https://assets.aivison.it.com` |
| Web API storage clients | current/R2 client=True, R2 client=True, legacy client=True, legacy public client=True |

代码依据：

- Web API 同时配置 current R2 与 legacy MinIO fallback：`deploy/docker-compose-cloud-prod.yml:61`、`deploy/docker-compose-cloud-prod.yml:70`、`deploy/docker-compose-cloud-prod.yml:77`。
- Worker/relay 新数据写入 current storage，正式默认也是 `user-data-prod`：`workers/docker-compose-cloud-prod-worker.yml:5`。
- 本地 relay 先上传结果，再通知 complete；上传失败会 502，不会正常完成任务：`workers/local_relay/relay_main.py:363`。

## 3. 数据分布核验

只读 SQL 聚合结果：

| 数据集 | 结果 |
| :--- | :--- |
| `history` 总量 | 1,746,659 条都有 `output_file` |
| `history.source` | web=265,126；bot=1,481,533 |
| `history.output_file` 形态 | `history/%`=0；basename-only=20,777；other-path=1,725,881；`bot-data/%`=1 |
| 活跃 GalleryPost | 16,352 条 |
| 活跃 GalleryPost source | web=2,185；bot=14,167 |
| 活跃 GalleryPost 时间范围 | 2026-04-15 到 2026-06-08 |
| 市集 latest 前 20 | 2026-06-08 19:27 到 20:38；web=7，bot=13 |
| 市集 likes 前 20 | 2026-04-16 到 2026-05-14；全部 bot，点赞 163-786 |

关键解释：

- DB 里的 `output_file` 不是标准 R2 展示 key；标准 key 是运行时从 `task_id + output_file` 推导出来的。
- 代码会先探测 `history/{task_id}/original.*` 和 `history/{task_id}/thumb.*`，再探测旧 object key、原始 `output_file`、basename。
- 因此旧数据只要没有回填到标准 key，就会多走探测或落到 legacy。

## 4. 接口实测证据

直接调用同一层 service/presenter 生成 Gallery 响应，不伪造登录态，不输出用户内容。

| 样本 | 耗时 | media URL | thumbnail URL |
| :--- | :--- | :--- | :--- |
| Gallery latest 第 1 次 | 3808.3ms | R2 presigned=19，legacy=1 | R2 presigned=19，legacy=1 |
| Gallery latest 第 2 次 | 775.9ms | R2 presigned=19，legacy=1 | R2 presigned=19，legacy=1 |
| Gallery latest 第 3 次 | 781.4ms | R2 presigned=19，legacy=1 | R2 presigned=19，legacy=1 |
| Gallery likes 第 1 次 | 13098.0ms | legacy=20 | legacy=20 |
| Gallery likes 第 2 次 | 13553.0ms | legacy=20 | legacy=20 |
| Gallery likes 第 3 次 | 12860.7ms | legacy=20 | legacy=20 |
| Gallery applied 第 1 次 | 12738.1ms | legacy=20 | legacy=20 |
| Gallery applied 第 2 次 | 13678.2ms | legacy=20 | legacy=20 |
| Gallery applied 第 3 次 | 11833.8ms | legacy=20 | legacy=20 |

修仙笔记最近活跃用户样本：

| 样本 | 耗时 | media URL | thumbnail URL | source |
| :--- | :--- | :--- | :--- | :--- |
| 用户样本 1 | 8731.3ms | R2 presigned=8 | empty=8 | bot=8 |
| 用户样本 2 | 7663.5ms | R2 presigned=8 | empty=8 | bot=8 |
| 用户样本 3 | 12622.0ms | R2 presigned=8 | empty=8 | bot=8 |
| 用户样本 4 | 7691.0ms | R2 presigned=8 | empty=8 | bot=8 |
| 用户样本 5 | 6633.4ms | R2 presigned=2，R2 public=3，legacy=3 | empty=4，R2=4 | bot=7，web=1 |

这个结果说明：修仙笔记慢不一定表现为 legacy URL。即使原图/视频已经在 R2，缩略图缺失也会触发慢探测。

## 5. 日志侧证据

只读聚合窗口：

| 日志源 | 观察结果 |
| :--- | :--- |
| `cloud-web-api-prod` 最近 2h | `Timed out resolving web result R2 URL`=294；`Unexpected object_exists failure`=30 |
| `cloud-web-api-prod` 最近 30m | `Timed out resolving web result R2 URL`=95；`Unexpected object_exists failure`=14 |
| `cloud-prod-worker-relay` 最近 2h | `sidecar_upload_succeeded`=2598；`sidecar_upload_failed`=0 |
| edge Nginx access tail 5000 | `/bot-data` legacy asset 请求约 4120 次；499=4，500=1 |
| edge Nginx error tail 1000 | `assets.aivison.it.com` 相关 824 行；`upstream prematurely closed`=717；`upstream timed out`=108；`connect() failed`=153 |

判读：

- 新生成上传链路本身稳定，relay 近 2h 没看到 R2 upload failed。
- 读路径有明显 R2 URL 探测 timeout 与 legacy assets 回源异常。
- legacy assets 仍有大量真实流量，不是已经完全退出热路径。

## 6. 展示链路梳理

### 6.1 Web 用户上传

- 前端调用 `/api/storage/presigned-url`。
- 后端生成 object key：`web_uploads/{user_id}/{date}_{uuid}.{ext}`。
- 云正式 `MINIO_BUCKET=user-data-prod`，所以 Web 上传直传 R2 兼容桶。
- 代码依据：`src/web_api/services/storage_api_service.py:13`、`src/web_api/services/storage_api_service.py:46`。

### 6.2 生成结果写入

- Worker 生成结果落本地 spool。
- relay sidecar 把 primary/extra outputs 上传到 `MINIO_RESULT_BUCKET`。
- 云正式 `MINIO_RESULT_BUCKET=user-data-prod`，所以新结果进入 R2。
- 上传成功后才 `/complete`，失败不应生成成功历史。
- 代码依据：`workers/local_relay/relay_main.py:363`。

### 6.3 修仙笔记展示

- `/api/users/history` 取当前用户最近 8 条。
- DB 查询后释放只读事务，再并发解析每条 media/thumbnail URL。
- media/thumbnail 解析流程会先探测 R2 candidate，再 fallback 到 legacy/current storage。
- 代码依据：`src/web_api/services/users_history_service.py:40`、`src/web_api/services/history_response_builder.py:76`、`src/web_api/presenters/media_presenter.py:195`、`src/web_api/presenters/media_presenter.py:234`。

### 6.4 修仙市集展示

- `/api/gallery/posts` 取 `GalleryPost`，根据 `sort_by=latest|likes|applied` 排序。
- 每个帖子再按 `task_id` 找 `History.output_file`，解析 media/thumbnail。
- Gallery 热路径会优先 R2 S3 HEAD 命中并返回 R2 presigned URL；R2 miss 后 fallback 到 legacy。
- 代码依据：`src/services/gallery_feed_queries.py`、`src/web_api/services/gallery_media_resolver.py:26`、`src/web_api/services/gallery_media_resolver.py:62`。

### 6.5 标准 R2 key

运行时候选顺序：

- 原文件：`history/{task_id}/original.{ext}` -> storage object key -> raw `output_file` -> basename。
- 缩略图：`history/{task_id}/thumb.webp|jpg` -> storage thumbnail key -> raw thumbnail path -> basename。
- 代码依据：`src/core/media_urls.py:18`、`src/core/media_urls.py:40`。

## 7. 根因

1. 历史热门 Gallery 仍在 legacy 回源。

高赞/高使用榜选中的主要是 4-5 月历史投稿，service 返回全部 `https://assets.aivison.it.com`。这会经过 edge VPS -> Tailscale -> 本地 MinIO，明显慢于 R2。

2. 未投稿 bot 历史缺标准缩略图。

当前 Web 历史 warmup 只对 `source == "web"` 执行，会复制标准 media key 并生成标准 thumbnail。bot source 直接 return。代码依据：`src/core/task_core_web_history_warmup.py:30`。

3. 列表读路径在 miss 时仍会做多级探测。

修仙笔记对 media 和 thumbnail 同时解析；thumbnail miss 会走 R2 candidate、legacy、current storage 多级探测。样本显示 8 条 R2 media + 8 个空 thumbnail 仍可耗时 7-12s。

4. Gallery latest 和 likes 的速度差，不是 SQL 排序本身造成的。

latest 和 likes 都是同一列表构建逻辑；差异来自排序选出的对象集合不同。latest 多数 R2，likes/applied 全 legacy。

## 8. 最佳优化方案

建议分两条线推进：先规整历史数据，再修正后续写入/展示逻辑。

### 阶段 A：历史数据规整，优先用户可见集合

目标：不改 DB 字段，先把对象补齐到代码已经支持的标准 R2 key。

必须补齐：

- 原文件：`history/{task_id}/original.{ext}`
- 缩略图：图片 `history/{task_id}/thumb.webp`，视频 `history/{task_id}/thumb.jpg`
- 范围优先级：活跃 Gallery、likes/apply 互动过的 Gallery、prompt unlock、用户最近 8 条、用户收藏。

现有脚本已经覆盖这个方向：`scripts/backfill_history_r2_objects.py`。

推荐执行顺序，正式执行前先 dry-run，小批量观察：

```bash
# 1. legacy 原文件预热到 R2，先 dry-run
docker exec -it cloud-web-api-prod python scripts/backfill_history_r2_objects.py \
  --visible-scope user-visible \
  --source-storage legacy \
  --media-only \
  --limit 500 \
  --concurrency 4

# 2. 加 --apply 后按批执行原文件预热
docker exec -it cloud-web-api-prod python scripts/backfill_history_r2_objects.py \
  --visible-scope user-visible \
  --source-storage legacy \
  --media-only \
  --limit 500 \
  --concurrency 4 \
  --apply

# 3. copy legacy 中已有缩略图
docker exec -it cloud-web-api-prod python scripts/backfill_history_r2_objects.py \
  --visible-scope user-visible \
  --source-storage legacy \
  --limit 500 \
  --concurrency 4 \
  --apply

# 4. 从已在 R2 的原文件生成缺失缩略图
docker exec -it cloud-web-api-prod python scripts/backfill_history_r2_objects.py \
  --visible-scope user-visible \
  --source-storage current \
  --generate-missing-thumbnails \
  --limit 200 \
  --concurrency 2 \
  --apply
```

执行策略：

- 先只跑 top 用户可见集合，不建议一口气扫 174 万条全历史。
- 每批记录 summary：media exists/uploaded/source_missing、thumbnail copied/generated/source_missing。
- 每批后用 service 级样本验收：latest/likes/applied 是否从 legacy 转为 R2，修仙笔记 thumbnail empty 是否下降。
- 若目标是彻底消灭历史问题，再扩大到 `--visible-scope all`，但应安排维护窗口和限速。

### 阶段 B：后续新数据默认走最佳逻辑

建议改代码：

1. 把 `schedule_web_history_r2_warmup` 泛化为 history R2 warmup，不只处理 `source == "web"`。

当前 `source != "web"` 直接 return，导致大量 bot 历史没有标准缩略图。云正式 bot 结果已经写 R2，所以可以对 bot source 也生成标准 `history/{task_id}` media/thumbnail。

2. 新增轻量负缓存或跳过列表缩略图深度 fallback。

列表页对 thumbnail miss 不应把整个 API 拖到 7-13s。建议：

- R2 negative cache 对 thumbnail key 单独生效更久。
- History/Gallery 列表若标准 thumbnail miss，可快速返回空或原图，不再同步探测 legacy/current。
- 详情页或 apply-context 可保留更完整 fallback。

3. Gallery media/thumbnail 解析可并发。

当前单个 Gallery post 内先解析 media 再解析 thumbnail；可以像 history 一样 gather 两者，降低 legacy 场景的串行等待。

4. 新增后台健康指标。

建议统计并暴露：

- Gallery latest/likes/applied 每页 R2/legacy/empty 占比。
- History 最近 8 条 thumbnail empty 占比。
- Web API 中 R2 timeout、legacy fallback、thumbnail miss 计数。

### 阶段 C：边缘 legacy 降载

历史补齐后：

- `assets.aivison.it.com` 只作为兜底，不再是 hot path。
- 缩小 edge Nginx cache 或调整 cache/log 生命周期，避免根盘风险再次出现。
- 保留 legacy MinIO 只读 fallback 一段观察期，等命中率降到很低再讨论退役。

## 9. 风险与注意事项

- 不建议直接改 `History.output_file` 为标准 R2 key。现有代码已经支持标准 key candidate，不改 DB 更安全。
- 迁移脚本要小批量、低并发、先 dry-run；大批生成视频缩略图会消耗 FFmpeg/网络/R2 请求。
- `visible-scope=user-visible` 在全量无 limit 场景仍可能扫大集合，应分批执行并记录 summary。
- 生产执行前先确认 cloud-web-api-prod 容器内脚本版本与本仓库一致。

## 10. 本次未做的事

- 未执行 backfill apply。
- 未上传、复制、生成任何对象。
- 未修改生产配置。
- 未重启、重建、reload 任何服务。
- 未输出密钥、Token、数据库连接串或预签名 URL。
