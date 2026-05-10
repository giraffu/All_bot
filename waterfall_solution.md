# 社区广场瀑布流重构方案 (基于成熟第三方库)

## 0. 需求背景与问题分析

目前 Web 端“修仙市集”（社区广场）的瀑布流使用的是 **CSS 多列布局 (CSS Columns)** 实现的（即 Tailwind 的 `columns-X` 类）。
CSS Columns 的排版逻辑是：将容器分为多列，然后将子元素从上到下、从左到右依次排列，并且**浏览器为了让各列的高度尽可能平衡，会动态地重新分配所有元素**。

这就导致了一个严重的体验问题：当用户下拉到页面末尾触发懒加载，将新的内容追加到列表时，浏览器会重新对所有卡片（包括老卡片）进行平衡分配。原本位于某一列的老卡片，可能会被自动“挤”到另一列，造成旧内容大面积横向跨列、上下跳动的“乱跑”现象，严重影响浏览体验。

为了解决这个问题，我们需要放弃 CSS `columns` 的自动流排版，引入一套能够将新卡片严格追加在下方（例如通过绝对定位计算 X/Y 坐标）且确保老卡片位置固定不动的真正瀑布流方案。

## 1. 库选型推荐：`vue-waterfall-plugin-next`

在 Vue 3 体系下，推荐使用 `vue-waterfall-plugin-next`。
**推荐理由**：
- **专为 Vue 3 设计**：原生支持 Composition API (`<script setup>`)。
- **自动处理高度**：不需要预先知道图片高度，它会在图片加载完成后自动重新计算排版。
- **不会改变旧卡片位置**：底层采用绝对定位 (`position: absolute`) 计算 X/Y 坐标，新追加的数据只会严格排布在下方，上方老卡片稳如泰山。
- **内置响应式与过渡动画**：自带优雅的追加动画，且支持配置多端断点（Breakpoints），完美契合现在的响应式需求。

## 2. 安装命令

在 `frontend` 目录下执行：
```bash
npm install vue-waterfall-plugin-next
```

## 3. 代码改造指南 (`src/views/Gallery.vue`)

### 3.1 引入依赖
在 `<script setup lang="ts">` 中引入组件和必须的 CSS（注意：无需引入 `LazyImg`，保留原有的 `<img>` 和 `<video>` 渲染机制即可）：
```typescript
import { Waterfall } from 'vue-waterfall-plugin-next'
import 'vue-waterfall-plugin-next/dist/style.css'
```

### 3.2 补充类型定义与动态追加 `src` 字段
首先，需要在 `interface Post` 中增加 `src` 属性的声明以解决 TypeScript 编译报错：
```typescript
interface Post {
  // ... 原有属性保持不变
  src?: string // 瀑布流插件预加载图片高度专用
}
```
其次，插件内部通过预加载图片来计算高度，默认读取对象的 `src` 字段。现有的 `Post` 接口使用 `thumbnail_url` 且需要动态计算签名 URL。必须在 `loadPosts` 时拦截并追加 `src` 字段：
```typescript
// 在 loadPosts 方法中处理接口返回的 res.data.items
const newItems = res.data.items.map((p: Post) => ({
  ...p,
  // 必须提前计算出真实的完整 URL 并赋给 src 字段
  src: isVideoFile(p.thumbnail_url, p.media_type) 
    ? getVideoPosterUrl(p.thumbnail_url, p.id) 
    : getFileUrl(p.thumbnail_url, p.id, true)
}))

if (reset) {
  posts.value = newItems
} else {
  posts.value = [...posts.value, ...newItems]
}
```

### 3.3 配置响应式断点 (Breakpoints)
`vue-waterfall-plugin-next` 的 `breakpoints` 是基于 **max-width** 的（当屏幕宽度**小于等于**该值时生效）。为了保持现有的多端展示效果，**必须将最大断点设置得足够大（例如 99999）**，否则在超大带鱼屏下会回退到默认的 200px 宽度导致排版崩坏：
```typescript
const breakpoints = {
  99999: { rowPerView: 6 }, // 极大值兜底，xl 及以上超大屏 (覆盖 >= 1280)
  1280: { rowPerView: 5 },  // lg: 屏幕小于等于 1280px 时 5 列
  1024: { rowPerView: 4 },  // md: 屏幕小于等于 1024px 时 4 列
  768:  { rowPerView: 3 },  // sm: 屏幕小于等于 768px 时 3 列
  640:  { rowPerView: 2 }   // mobile: 屏幕小于等于 640px 时 2 列
}
```

### 3.4 模板改造与加载状态控制
将原本的 `<div class="columns-2 ...">` 替换为 `<Waterfall>` 组件。注意最新版本（v2.6.0+）的插槽名为 `#default`，并且需要监听 `@afterRender` 来释放 `loading` 锁防雪崩：

**改造前：**
```html
<div class="columns-2 sm:columns-3 md:columns-4 lg:columns-5 xl:columns-6 gap-3 sm:gap-6">
  <div v-for="post in posts" :key="post.id" class="mb-3 break-inside-avoid ...">
    <!-- 卡片内容 -->
  </div>
</div>
```

**改造后：**
```html
<Waterfall 
  :list="posts" 
  :breakpoints="breakpoints" 
  :gutter="isMobile ? 12 : 24" 
  :animationDuration="400"
  backgroundColor="transparent"
  @afterRender="() => { loading = false }"
>
  <template #default="{ item: post }">
    <div 
      class="rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-400/50 bg-slate-500/40 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
      @click="openDetail(post)"
    >
      <!-- 原有的卡片内容完整迁移到这里，比如图片、视频、点赞条等 -->
      <!-- 注意：原来依靠外层 columns 的 mb-3 (margin-bottom) 和 break-inside-avoid 可以去掉了，Waterfall 的 gutter 会自动处理间距 -->
    </div>
  </template>
</Waterfall>
```

## 4. 实施注意事项与潜在踩坑点

1. **视频封面加载逻辑**：由于广场包含**视频** (`media_type: 'video'`)，我们需要确保视频的 poster（封面图）能在瀑布流初始化时被正确读取高度。通过追加 `src` 字段已经解决了这个问题，同时仍需保留现在的 `getVideoPosterUrl` 逻辑用于视频海报展示。
2. **无限滚动防雪崩（致命问题）**：目前的 `Gallery.vue` 是监听滚动事件触发懒加载，原先 `loadPosts()` 会在 `finally` 块中立即设置 `loading.value = false`。但瀑布流渲染是**异步计算**的，若立即释放 `loading` 锁，此时 DOM 高度还没撑开，页面滚动检测依然满足触底条件，会瞬间触发数百次 API 请求造成接口雪崩。**必须**在 `loadPosts` 中移除关闭 `loading` 的代码，改为依赖 `<Waterfall @afterRender="() => { loading = false }">` 事件来释放锁，并在异常情况下增加 `setTimeout` 兜底。
3. **样式去重**：必须移除旧卡片最外层由于 CSS Columns 机制所必需的 `break-inside-avoid` 和 `mb-3`。

## 5. 下一步行动
如果您觉得这个方案符合预期，您可以直接回复我“**开始改造**”，我将为您自动完成依赖安装、组件替换以及样式的精细调整。