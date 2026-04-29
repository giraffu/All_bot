# 手机端市集（Gallery）预览与加载速度优化方案 (最终安全修正版)

针对手机端市集（广场）出现的“图片/视频预览速度慢”以及“一次只能看到一张图（预览图太大）”的问题，经过对当前 `Gallery.vue` 代码的深入分析，制定以下分步优化方案（已排除原方案中会导致报错和本地环境裂图的技术盲区）：

## 1. 布局调整：实现手机端“一屏多看”与桌面端体验升级（纯前端，立竿见影）
**当前问题**：移动端瀑布流使用了 `columns-1`（单列排版）和较大的卡片间距（`gap-6 space-y-6`），导致一张图占满整个手机屏幕。
**前端改造方案**：
- **移动端优化**：将容器的 Tailwind 类名从单列改为移动端双列（`columns-2`），减小间距为 `gap-3 space-y-3`。
- **Web 桌面端优化**：电脑屏幕较宽，可利用 Tailwind 的大屏断点（`lg`, `xl`, `2xl`）增加列数（如 4-6 列），确保大屏不会因为单图过大而显得空旷。

*预期代码修改点 (`Gallery.vue`)*：
```html
<!-- 修改前 -->
<div class="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-6 space-y-6">

<!-- 修改后 (增加对桌面大屏 xl/2xl 的支持) -->
<div class="columns-2 sm:columns-3 md:columns-4 lg:columns-5 xl:columns-6 gap-3 space-y-3 sm:gap-6 sm:space-y-6">
```

## 2. 资源加载优化：解决“速度极慢”的核心瓶颈
**当前问题**：
1. **原图直接渲染**：图片没有区分缩略图和原片，前端直接加载了 5MB 级别的高清大文件。
2. **视频直接加载**：列表页会并发请求视频数据。虽然完全禁用预加载（`preload="none"`）可以节省带宽，但由于后端未提供独立的图片格式封面，这会导致视频卡片在加载前呈现纯黑或空白，严重影响体验。

**改造方案（Cloudflare Polish Pro 方案，Web与移动端通用）**：
- **图片加载（CDN 边缘格式转换）**：
  依赖 CF 控制台开启的 Polish (有损) 和 WebP/AVIF 开关。当浏览器（无论是手机还是电脑 Web 端）请求图片时，CF 会自动判断浏览器是否支持 WebP/AVIF。如果支持，CF 会在边缘节点自动将原图转码为现代压缩格式返回，体积大幅缩小。
  **Web 端额外收益**：电脑浏览器（如 Chrome/Edge）均完美支持 AVIF 格式。AVIF 比 WebP 压缩率更高。只要您在 CF 后台同时开启了 AVIF，Web 端将享受到最顶级的图片加载速度。
  **⚠️ 安全红线**：
  1. 必须将 `isVideoFile` 的定义提前，防止产生暂时性死区（TDZ）导致 `ReferenceError` 页面白屏。
  2. 此方案取消了前端拼接 `/cdn-cgi/image/`，完全依靠 CF 边缘层透明优化，对代码侵入性最小。
- **视频加载（体验与性能的平衡）**：
  保持 `<video preload="metadata">`。我们牺牲少量带宽以获取首帧画面，防止出现大规模黑屏卡片。

*预期代码修改点 (`Gallery.vue` - script 部分)*：
```typescript
// 1. 必须将 isVideoFile 提前到 getFileUrl 之前，解决变量提升导致的 ReferenceError
const isVideoFile = (path: string, mediaType?: string) => {
  if (mediaType) {
    return mediaType === 'video'
  }
  if (!path) return false
  const lowerPath = path.toLowerCase()
  return lowerPath.endsWith('.mp4') || 
         lowerPath.endsWith('.mov') || 
         lowerPath.endsWith('.webm') || 
         lowerPath.endsWith('.mkv') ||
         lowerPath.endsWith('.avi')
}

// 2. 改造 getFileUrl，引入 isThumbnail、mediaType 及本地环境拦截
const getFileUrl = (path: string, postId?: number, isThumbnail: boolean = false, mediaType?: string) => {
  if (!path) return ''
  let url = path
  
  // 兼容 MinIO 本地回退模式
  if (!path.startsWith('http')) {
    const storageUrl = import.meta.env.VITE_STORAGE_URL || ''
    const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl
    
    if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
      if (!path.includes('/')) {
        url = `${base}/comfyui-temp/${path}`
      } else {
        url = `${base}/bot-data/${path}`
      }
    } else {
      url = `${base}/${path}`
    }
  }

  // ==========================================
  // 【方案二：依赖 Cloudflare Polish 无损/有损自动优化的免费方案】
  // 前置条件：必须在 CF 控制台开启 Polish (有损) + WebP/AVIF 开关。
  // 注意：此方案不再进行 /cdn-cgi/image/w=400 尺寸裁剪，完全依靠 CF 边缘节点的现代格式转换。
  // 如果原始图片(如 4K 巨幅图片)体积过大，移动端依然可能卡顿。建议后端在生成时控制图片最大分辨率。
  // ==========================================
  
  // 缓存策略：v=${postId} 作为静态版本号，仅在原 URL 无鉴权签名时安全拼接
  // 若 URL 为 S3/MinIO 预签名链接，追加未知参数会导致 403 Forbidden，请按需移除此段
  if (postId && !url.includes('X-Amz-Signature')) {
    const sep = url.includes('?') ? '&' : '?'
    url = `${url}${sep}v=${postId}`
  }
  return url
}
```

*预期代码修改点 (`Gallery.vue` - template 部分)*：
同步修改模板中 `getFileUrl` 的调用，**并强制增加 `loading="lazy"` 属性防止移动端并发连接耗尽**：
```html
<!-- 原图 -> 请求缩略图 + 原生懒加载 -->
<img v-if="!isVideoFile(post.thumbnail_url, post.media_type)" 
     :src="getFileUrl(post.thumbnail_url, post.id, true, post.media_type)"
     loading="lazy"
     ... />
```

## 3. 移动端交互体验增强
**当前问题**：视频依赖鼠标悬停 `@mouseenter="playVideo"`，这在手机触摸屏上完全失效。
**前端改造方案**：
- 移除移动端的 Hover 播放逻辑（或仅保留给桌面端使用）。
- 用户点击卡片统一触发 `openDetail` 弹窗，在弹窗的暗色背景下加载原片资源并自动播放（沉浸式观看）。

---

## 🚀 建议的实施路径 (Next Steps)
鉴于采用 Cloudflare 免费版优化方案，建议立即执行以下**纯前端**代码修改（不涉及任何后端改造）：
1. 更新 `Gallery.vue` 布局为双列。
2. 将 `isVideoFile` 移动到顶部。
3. 确保在 CF 后台已开启 Polish(有损) 和 WebP/AVIF 开关。
4. 同步更新模板中的图片 `:src` 绑定，传入 `isThumbnail=true` 参数，**并强制添加 `loading="lazy"`**。
