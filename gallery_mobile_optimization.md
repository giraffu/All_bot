# 手机端市集（Gallery）预览与加载速度优化方案 (最终安全修正版)

针对手机端市集（广场）出现的“图片/视频预览速度慢”以及“一次只能看到一张图（预览图太大）”的问题，经过对当前 `Gallery.vue` 代码的深入分析，制定以下分步优化方案（已排除原方案中会导致报错和本地环境裂图的技术盲区）：

## 1. 布局调整：实现手机端“一屏多看”（纯前端，立竿见影）
**当前问题**：移动端瀑布流使用了 `columns-1`（单列排版）和较大的卡片间距（`gap-6 space-y-6`），导致一张图占满整个手机屏幕。
**前端改造方案**：
- **增加列数**：将容器的 Tailwind 类名从单列改为移动端双列（`columns-2`），平板以上递增。
- **缩小间距**：移动端减小间距为 `gap-3 space-y-3`，让视觉更紧凑。

*预期代码修改点 (`Gallery.vue`)*：
```html
<!-- 修改前 -->
<div class="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-6 space-y-6">

<!-- 修改后 -->
<div class="columns-2 sm:columns-3 md:columns-4 lg:columns-5 gap-3 space-y-3 sm:gap-6 sm:space-y-6">
```

## 2. 资源加载优化：解决“速度极慢”的核心瓶颈
**当前问题**：
1. **原图直接渲染**：图片没有区分缩略图和原片，前端直接加载了 5MB 级别的高清大文件。
2. **视频直接加载**：列表页会并发请求视频数据。虽然完全禁用预加载（`preload="none"`）可以节省带宽，但由于后端未提供独立的图片格式封面，这会导致视频卡片在加载前呈现纯黑或空白，严重影响体验。

**改造方案（Cloudflare 速度优化已开启）**：
- **图片加载（CDN 动态边缘压缩）**：
  改造 `getFileUrl` 函数，增加 `isThumbnail` 参数。判断如果是图片类型，自动在 URL 加上压缩参数 `/cdn-cgi/image/w=400,q=75,format=auto/`，将原图瞬间压缩到 30KB 加载。
  **⚠️ 安全红线**：
  1. 必须将 `isVideoFile` 的定义提前，防止产生暂时性死区（TDZ）导致 `ReferenceError` 页面白屏。
  2. 必须加入域名拦截，防止在本地开发时（localhost/内网 IP）强行拼接 CF 路径导致全部图片裂图。
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

  // 核心修正：仅对图片资源且非本地环境注入 CF 压缩参数
  if (isThumbnail && !isVideoFile(path, mediaType)) {
    try {
      const urlObj = new URL(url)
      // 防止本地开发环境裂图
      const isLocal = urlObj.hostname === 'localhost' || 
                      urlObj.hostname === '127.0.0.1' || 
                      /^\d+\.\d+\.\d+\.\d+$/.test(urlObj.hostname)
      
      if (!isLocal && !urlObj.pathname.startsWith('/cdn-cgi/image/')) {
        urlObj.pathname = `/cdn-cgi/image/w=400,q=75,format=auto${urlObj.pathname}`
        url = urlObj.toString()
      }
    } catch (e) {
      console.error("URL 解析失败", e)
    }
  }
  
  if (postId) {
    const sep = url.includes('?') ? '&' : '?'
    url = `${url}${sep}v=${postId}`
  }
  return url
}
```

*预期代码修改点 (`Gallery.vue` - template 部分)*：
同步修改模板中 `getFileUrl` 的调用：
```html
<!-- 原图 -> 请求缩略图 -->
<img v-if="!isVideoFile(post.thumbnail_url, post.media_type)" 
     :src="getFileUrl(post.thumbnail_url, post.id, true, post.media_type)" ... />
```

## 3. 移动端交互体验增强
**当前问题**：视频依赖鼠标悬停 `@mouseenter="playVideo"`，这在手机触摸屏上完全失效。
**前端改造方案**：
- 移除移动端的 Hover 播放逻辑（或仅保留给桌面端使用）。
- 用户点击卡片统一触发 `openDetail` 弹窗，在弹窗的暗色背景下加载原片资源并自动播放（沉浸式观看）。

---

## 🚀 建议的实施路径 (Next Steps)
鉴于 Cloudflare 优化功能已激活，建议立即执行以下**纯前端**代码修改（不涉及任何后端改造）：
1. 更新 `Gallery.vue` 布局为双列。
2. 将 `isVideoFile` 移动到顶部。
3. 更新 `getFileUrl`，对图片卡片安全地启用 CF 边缘压缩（已包含本地开发环境保护）。
4. 同步更新模板中的图片 `:src` 绑定，传入 `isThumbnail=true` 参数。
