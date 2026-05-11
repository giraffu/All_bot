# 画廊媒体封面（视频缩略图与图片压缩）生成与 R2 同步方案

## 1. 背景与痛点
为了彻底解决前端因为 `<video preload="metadata">` 导致的海量全量视频下载请求（504 宕机风暴），我们在前端移除了视频的自动加载机制。
带来的副作用是：在用户主动 Hover（悬停）前，视频处于黑屏或仅显示占位图状态，缺乏直观的视频封面。
同时，原始生成的图片可能体积较大（如 1024x1024 高清原图），在瀑布流中直接加载原图会消耗大量 CDN 带宽并影响渲染性能。

## 2. 方案目标（全量自托管生成 - 仅限画廊投稿数据）
*   **核心范围限制**：为了节省服务器算力和存储，**只为发布到画廊（投稿）的内容**生成缩略图。私有生成记录（未投稿）不生成缩略图。只处理已经落盘在 MinIO 且需要同步到 R2 桶中的数据。
*   **弃用外部依赖**：鉴于 Cloudflare Image Resizing 免费额度耗尽且不支持视频截帧，本项目采用完全自托管的后台脚本生成方案，同时处理视频和图片。
*   **零前端带宽压力**：视频封面必须是轻量的图片（`.jpg`），绝对不能让前端为了获取封面而去请求视频源文件。
*   **图片缩略图加速**：为原图生成更小尺寸的 WebP 压缩预览图（最大宽度 600px），提升瀑布流加载速度。
*   **全 CDN 加速**：生成的封面与缩略图必须双写至本地 MinIO 并同步推送到 Cloudflare R2，供前端通过 CDN 加速访问。
*   **最小化数据库侵入**：不新增独立的数据库字段，采用“扩展名/后缀约定”模式。

---

## 3. 架构设计与约定

### 3.1 核心约定：后缀与替换规则
为了避免修改 `History` 和 `GalleryPost` 的数据库结构，我们采用约定后缀名机制：
*   **视频源文件**：`bot-data/users/123/video_abc.mp4`
    *   **对应视频封面**：`bot-data/users/123/video_abc_thumb.jpg` （去除原扩展名追加 `_thumb.jpg`）
*   **图片源文件**：`bot-data/users/123/image_xyz.png` (或 `.jpg`)
    *   **对应图片缩略图**：`bot-data/users/123/image_xyz_thumb.webp` （去除原扩展名追加 `_thumb.webp`）

### 3.2 历史存量数据处理脚本：`scripts/generate_gallery_thumbnails.py`
针对目前已经发布到画廊的历史存量帖子，提供一个一次性的后台处理脚本。

**依赖库**：`boto3` (MinIO/R2交互), `subprocess` (调用 ffmpeg), `Pillow` (图片处理), `SQLAlchemy` (扫表)。

**核心处理逻辑**：
1.  **扫表获取任务**：连表查询 `GalleryPost` 和 `History`，只获取已发布到画廊 (`is_active=True`) 的有效记录。
2.  **存在性检查**：调用 `storage.object_exists()` 检查 `_thumb` 文件是否已在 MinIO/R2 存在，避免重复生成。
3.  **文件下载/流读取**：
    *   **视频**：推荐使用 HTTP Range 请求直接将 MinIO 的预签名 URL 提供给 FFmpeg (`-i URL`) 进行流式读取，避免全量下载数百 MB 的视频到本地磁盘。
    *   **图片**：通过 `storage.download_file()` 将目标文件拉取到本地，**必须使用 `tempfile.TemporaryDirectory()` 创建隔离的临时目录**以防止并发写入冲突。
4.  **分类处理**（核心代码必须包裹在 `try...finally` 中）：
    *   **视频处理 (FFmpeg)**：使用 Fast Seek 和高压缩率截取第一帧。
        `ffmpeg -y -ss 00:00:00.000 -i <input_url_or_file> -frames:v 1 -q:v 5 thumb.jpg`
    *   **图片处理 (Pillow)**：先调用 `ImageOps.exif_transpose()` 纠正方向，再进行 RGB 转换，使用 `Image.Resampling.LANCZOS` 等比缩放至最大宽度 600，保存为 WEBP，开启高效率压缩 `quality=80, method=6`。
5.  **双写上传**：调用现有封装将缩略图上传至 MinIO 并自动触发 R2 同步 (`storage._sync_upload_to_r2`)。
6.  **强制清理**：在 `finally` 块中使用 `shutil.rmtree()` 强制删除临时文件夹，防止 FFmpeg 或网络异常中断导致磁盘溢出。

### 3.3 增量数据处理：后台任务 (BackgroundTasks)
为了不阻塞 FastAPI 的响应，当用户**提交作品到画廊**时（即 `POST /api/gallery/posts/submit/{task_id}`），将缩略图生成逻辑作为 FastAPI 的 `BackgroundTasks` 异步执行。
*   **入口**：`src/core/gallery_core.py` 中的 `process_submit_to_gallery`。
*   **流程**：帖子写入数据库并完成文件迁移后，触发后台任务，执行与 3.2 相同的下载、生成、双写上传流程。这保证了私有内容不占用算力，只有公开展示的内容才生成缩略图。

### 3.4 后端接口改造：`src/web_api/routers/gallery.py`
修改目前直接返回原图 URL 的逻辑，强制下发约定后缀的缩略图链接。

**改造细节**：
```python
def generate_thumbnail_url(output_file: str, media_type: str) -> str:
    if not output_file:
        return ""
        
    # 剥离原扩展名
    base_path = output_file.rsplit(".", 1)[0]
    
    if media_type == "video":
        thumb_file = f"{base_path}_thumb.jpg"
    else:
        thumb_file = f"{base_path}_thumb.webp"
        
    return get_media_url(thumb_file)
```

### 3.5 前端渲染改造与 404 降级机制：`Gallery.vue`
1.  **清理废弃代码**：移除 `Gallery.vue` 中关于 `cdn-cgi`（Cloudflare Image Resizing）的被注释废弃代码。
2.  **强制降级机制（容灾核心）**：为了防止因为后台缩略图生成延迟、脚本失败等导致画廊大面积破图，必须在前端图片标签上加上 `@error` 降级事件。当 `_thumb` 链接加载失败（返回 404）时，自动回退到加载 `media_url`（原图文件）。对于因为服务器重启等原因丢失后台生成任务的极端情况，前端在触发 404 降级时，可考虑静默调用一次 `POST /api/gallery/retry-thumbnail` 来触发后端的重新生成补偿。
3.  **使用逻辑**：瀑布流组件绑定的 `src` 指向后端下发的 `thumbnail_url`，仅在点击放大查看（模态框）或下载时才使用 `media_url`。

---

## 4. 后续落地步骤

1.  **环境准备**：确认运行代码的宿主机/容器已安装 `ffmpeg` 并在 requirements 中引入 `Pillow`。
2.  **开发核心生成模块**：在项目中（如 `src/core/media_processor.py`）封装视频/图片的拉取、压缩与上传逻辑。
3.  **接入画廊投稿链路**：在 `process_submit_to_gallery` 结束前，将上述生成逻辑加入 `background_tasks`，实现增量处理。
4.  **实施 API 改造**：修改 `gallery.py`，确保向前端下发拼接好的 `_thumb` 链接。
5.  **前端容灾改造**：修改前端 `Gallery.vue`，增加 `@error` 降级加载机制并清理历史废弃代码。
6.  **全量修复历史数据**：编写并运行 `scripts/generate_gallery_thumbnails.py` 处理历史已发布帖子的存量缩略图。
