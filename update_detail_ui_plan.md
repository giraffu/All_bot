# 详情页 UI 统一更新实施计划 (Update Detail UI Plan)

## 目标
将修仙笔记中的“点赞”（含收藏、应用）和“我的投稿”三个 tab 中的详情弹窗 UI，对齐修仙市集（Gallery）的全新现代化设计。在此过程中，**严格保留各 tab 独有的功能按钮**（如：取消收藏、复制提示词、重新上架/下架、删除等），不改变底层数据结构与 API 交互逻辑。

## 涉及文件
1. `frontend/src/views/MyFavorites.vue` （负责“收藏”、“点赞”、“应用” tab，移动端为双列排布）
2. `frontend/src/components/MySubmissionsPanel.vue` （负责“我的投稿” tab，移动端为单列排布）

---

## 具体实施步骤

### 1. 响应式 Modal 容器升级
- 引入 `@vueuse/core` 的 `useWindowSize` 以实现 `isMobile` 状态判断。
- 更新 `<a-modal>` 的属性：
  - 移动端：`width="100%"`，去除 margin/padding，全屏显示 (`wrapClassName="mobile-full-modal"`)。
  - PC 端：`width="90%"`，最大宽度 `1000px`，深色毛玻璃背景。
- **布局重构**：将原先的固定布局改为 `flex-col lg:flex-row`。确保移动端是上下排布，PC端是左右排布（左侧 2/3 为媒体，右侧 1/3 为信息）。

### 2. 新增移动端专属 Header
- 在媒体区域上方（仅移动端显示，`lg:hidden`），增加一个吸顶的深色半透明 Header。
- 包含“返回/关闭”图标按钮以及标题展示（如显示“修仙界作品”或用户头像占位）。

### 3. 信息区域 (Info Area) 样式重绘
- **排版左对齐**：去除原有的居中排版，将作品尺寸（如 `512x704`）、生成时长（`21秒`）和创建时间等元数据改为紧凑的左对齐流式布局。
- **标签 (Tags) 样式升级**：抛弃旧版大边框样式，采用市集中的圆角药丸风格 (`rounded-full`, 细边框, 亮青色字体)。
- **专属管理按钮 (针对移动端的我的投稿)**：由于底部悬浮栏空间有限，“我的投稿”中的**“重新上架/下架”**和**“删除”**按钮，在移动端将放置于 Info Area 内部内容的底部（随内容滚动），采用柔和但有区分度的 UI（如删除按钮使用微红背景 `bg-red-500/10 text-red-400`）。
- **滚动与留白防遮挡**：在 Info Area 增加 `overflow-y-auto`，并针对移动端增加 `pb-[80px]`，确保内容不会被底部悬浮操作栏遮挡。

### 4. 桌面端操作区 (Desktop Interactions) 更新
保留原有的功能事件绑定，但使用市集的半透明、带 Hover 动效的按钮样式。
- **MyFavorites.vue**：
  - `filterType === 'favorite'` 时：渲染大尺寸的“取消收藏”与“一键应用”按钮。
  - `filterType !== 'favorite'` 时：并排渲染“点赞(Like)”和“踩(Dislike)”，并在下方渲染“一键应用”。
- **MySubmissionsPanel.vue (我的投稿)**：
  - 第一行：并排渲染“点赞”和“踩”。
  - 第二行（管理功能）：并排渲染“重新上架/下架”和“删除”（保留原有红绿状态区分，但融入暗黑磨砂风格）。
  - 第三行：并排渲染“复制提示词”与“一键应用”按钮。

### 5. 新增移动端底部悬浮操作栏 (Mobile Bottom Action Bar)
- 在外层容器底部添加固定定位的栏 (`fixed bottom-0 left-0 right-0 bg-[#0f172a]/95 backdrop-blur-lg`)，仅在移动端显示 (`lg:hidden`)。
- **左侧图标区**：
  - `MyFavorites.vue` (`favorite`)：放“取消收藏”的图标（Trash2）。
  - `MyFavorites.vue` (非 `favorite`)：放“心形(Like)”和“大拇指向下(Dislike)”图标+数字。
  - `MySubmissionsPanel.vue`：放“心形”、“踩”和“复制(Copy)”图标。
- **右侧主操作区**：
  - 统一放置青色的“一键应用此模板”主按钮，带加载中(`applying`)的 Spinner 状态。

### 6. 列表页 (List View) 卡片 UI 优化注意点
- **单双列差异化适配**：`MySubmissionsPanel` 在移动端是**单列显示** (`columns-1`)，而其他 tab 是双列。在统一详情 UI 的同时，需要复查列表页的卡片 UI（如缩略图比例、状态徽章大小、底部统计栏排版），确保单列下大图的视觉比例协调，不会因为拉伸显得突兀，且风格对齐最新的画廊卡片（圆角 `rounded-2xl`，Hover 阴影等）。

---

## 风险防范与测试点
1. **移动端手势冲突**：需要确保 `Gallery.vue` 中使用的 CSS 类 `.mobile-full-modal` 能够在所有视图中正常生效，避免遮罩层导致无法滚动。
2. **事件参数一致性**：原组件中 `handleInteract(post, type)`、`handleStatusToggle`、`handleDelete` 需要传入 `post` 对象，复制代码时需确保引用的是 `currentPost.value` 而不是丢失上下文。
3. **视频兼容性**：需要确保视频在移动端全屏 Modal 下能正常通过 `controls` 播放和静音。
4. **状态联动更新**：在详情页内点击“下架”或“删除”后，关闭详情页时，外层的单列列表必须能正确移除或更新该卡片状态（测试原有的 Vue 响应式绑定是否依然生效）。