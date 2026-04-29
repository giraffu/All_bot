# Web 端与 Telegram Mini App (TMA) 移动端 UI/UX 响应式优化实施方案

## 核心前提与原则

本方案的最高原则是\*\*“双端解耦，互不干扰”\*\*。

- **电脑端（PC）**：维持现有的“左侧边栏 + 宽屏大卡片 + 大留白”的大气布局。所有针对移动端的样式覆盖均通过 Tailwind 的响应式前缀（如 `md:`、`lg:`）或 Vue 的响应式变量（如 `isMobile`）进行隔离。
- **移动端（Mobile）**：包含**普通手机浏览器**与 **Telegram 内置环境 (TMA)** 两种情况。方案将智能识别运行环境，在 TMA 中调用原生 API 提供极致体验，在普通浏览器中提供优雅的降级（Fallback）体验。

***

## 一、 核心导航范式转换 (Navigation Paradigm)

目前移动端使用的是“顶部汉堡菜单 -> 呼出左侧抽屉”的传统 Web 范式，操作路径过长。我们将重构 `MainLayout.vue`：

### 1. 引入底部标签栏 (Bottom Tabbar)

- **实现方式**：在 `MainLayout.vue` 中，利用 `v-if="isMobile"` 隐藏原有的 Drawer，在页面最底部（`fixed bottom-0`）增加一个毛玻璃质感的 Tabbar。
- **入口精简**：精选 4-5 个最高频的操作（如：个人中心、修仙市集、练功房、闪回瓶），采用“图标 + 小文字”的垂直布局。
- **PC端兼容**：通过 `v-if="!isMobile"` 依然保留 PC 端的左侧大导航栏 `<a-layout-sider>`。

### 2. 顶部 Header 瘦身

- **实现方式**：在手机端取消 Header 左侧的汉堡按钮，将“页面标题”居中。右侧仅保留“灵石余额”和“用户头像（点击弹出版面板而非下拉菜单）”。

***

## 二、 空间与排版微调 (Spacing & Typography)

手机端“寸土寸金”，我们需要对现有的页面（如 `Profile.vue`）进行高密度信息重排。

### 1. 响应式间距与字体缩放 (Tailwind 前缀)

- **外边距/内边距**：将全局的大 Padding 改为响应式。例如 `Profile.vue` 中的欢迎卡片，将 `p-8` 改为 `p-5 md:p-8`；页面主容器的 margin 将 `m-6` 改为 `m-2 md:m-6`。
- **字体降级**：将过大的标题（如 `text-3xl`）改为 `text-xl md:text-3xl`，避免在窄屏手机上发生尴尬的折行。

### 2. 数据卡片网格重组 (Data Density)

- **现状**：手机端数据总览（如系统ID、施法次数、签到等）是 `grid-cols-1`，导致页面被拉得很长。
- **优化**：修改为 `grid-cols-2 md:grid-cols-4` 或 `grid-cols-2 lg:grid-cols-5`。在手机端两两并排，配合稍微缩小的图标（`size=20`），大幅提升首屏的信息密度。

***

## 三、 深度融合 Telegram 原生体验与浏览器兼容

为了兼顾 Telegram 内部打开和普通手机浏览器打开，我们需要封装一个环境检测工具（Composable）。

### 1. 状态识别 (`useTelegram.ts`)

新建一个 composable，用于判断当前环境：

```typescript
const isTMA = window.Telegram?.WebApp?.platform !== 'unknown' && window.Telegram?.WebApp?.initData !== '';
```

### 2. 原生主按钮 (MainButton) 与降级

对于页面级的核心操作（例如 `Profile.vue` 里的“签到”大按钮）：

- **在 TMA 环境**：隐藏网页内的签到按钮，调用 `Telegram.WebApp.MainButton.setText('签到').show()`。这个原生按钮会固定悬浮在键盘上方，体验极佳。
- **在普通手机浏览器**：保留网页内的按钮，但将其样式改为固定在底部 Tabbar 上方（`fixed bottom-[tabbar高度]`）的悬浮大按钮，方便单手点击。
- **在 PC 端**：保留现有的按钮位置不变。

### 3. 触觉反馈 (Haptic Feedback)

- **在 TMA 环境**：用户点击底部 Tabbar、点击签到、或成功弹出提示时，调用 `Telegram.WebApp.HapticFeedback.impactOccurred('light')`，增加类原生的物理震动反馈。
- **普通环境**：静默忽略。

### 4. 底部半屏弹窗 (Bottom Sheet)

- 移动端不再使用 Ant Design 默认的屏幕居中 Modal（如“设置密咒”弹窗）。
- **优化**：封装一个响应式弹窗。当 `isMobile` 为 true 时，使用 `<a-drawer placement="bottom" height="auto" class="rounded-t-2xl">` 从底部滑出；当为 false 时，依然使用居中的 `<a-modal>`。

### 5. 安全区域适配 (Safe Area Insets)

- 为了防止全面屏手机（刘海、灵动岛、底部横条）遮挡 UI，在 CSS 中加入环境变量支持：

```css
padding-top: env(safe-area-inset-top, var(--tg-safe-area-inset-top, 0px));
padding-bottom: env(safe-area-inset-bottom, var(--tg-safe-area-inset-bottom, 0px));
```

***

## 四、 关键补充与防坑指南 (Pitfall Prevention)

结合当前代码库（Vue 3 + Tailwind CSS + Ant Design Vue）的实际情况，在落地实施时需注意以下细节：

### 1. 底部 Tabbar 遮挡内容问题 (布局防坑)

- **问题**：将 Tabbar 设置为 `fixed bottom-0` 时，页面滚动到底部最下方的内容会被 Tabbar 遮挡。
- **对策**：在 `MainLayout.vue` 中，当处于移动端模式时，给主内容容器 `<a-layout-content>` 增加底部的响应式内边距（如 `pb-20` 或 `pb-24`）。

### 2. Telegram 原生 MainButton 的生命周期管理 (内存防坑)

- **问题**：在 Vue 的单页应用（SPA）中组件是动态销毁的，直接调用原生 MainButton 容易导致事件重复绑定或在其他页面幽灵显示。
- **对策**：在接入 MainButton（如 `Profile.vue` 的签到）时，**必须在** **`onBeforeUnmount`** **钩子中严格处理事件解绑和状态重置**（调用 `tg.MainButton.offClick` 和 `tg.MainButton.hide()`）。加载状态可配合使用 `tg.MainButton.showProgress()` 提供原生动画。

### 3. 避免全局样式冗余修改 (细节纠正)

- **现状**：审查 `MainLayout.vue` 发现 `<a-layout-content>` 已经应用了 `m-2 p-3 md:m-6 md:p-6`，外层响应式已具备良好基础。
- **对策**：实施排版微调时，只需专注修改内部页面（如 `Profile.vue` 的 `p-8` 改为 `p-5 md:p-8`）的内部卡片和网格布局即可，无需盲目修改全局容器的 margin。

### 4. 底部抽屉 (Bottom Sheet) 的暗黑主题适配

- **问题**：现有的居中 `<a-modal>` 已经定制了 `.dark-modal` 的深色背景（`#1e293b`）。
- **对策**：将其在移动端降级为 `<a-drawer>` 时，必须通过 `:bodyStyle="{ background: '#1e293b' }"` 等方式注入相同的深色背景和边框颜色，以保持 UI 质感在双端的一致性。

***

## 五、 实施步骤计划 (Action Items)

如果你同意本方案，我们可以按以下顺序逐步实施（随时可以检查效果，确保 PC 端不被破坏）：

- [ ] ** cPhase 1: 基础设施**
  - 创建 `src/composables/useTelegram.ts` 封装环境与原生 API 交互。
- [ ] **Phase 2: 导航重构**
  - 修改 `MainLayout.vue`，实现底部 Tabbar，并处理 Header 在移动端的精简。
- [ ] **Phase 3: 页面排版微调**
  - 以 `Profile.vue` 为起点，将 `grid-cols-1` 修改为 `grid-cols-2 md:grid-cols-x`，优化 padding 和字号的响应式断点。
- [ ] **Phase 4: 交互组件升级**
  - 将弹窗（Modal）在移动端统一转为底部抽屉（Bottom Sheet）。
  - 在 TMA 环境下接入原生 `MainButton` 和震动反馈。

