# 子模块：前端浏览器预览与截图

## 1. 目标

当前 Web 前端经常需要对照参考图做视觉验收。AI 助手在修改 Vue 页面、组件布局或响应式样式后，应能在本服务器启动浏览器并生成截图，用截图判断首屏布局、移动端适配、元素重叠和文本溢出等问题。

对应技能：

- `.codex/skills/frontend-browser-preview/SKILL.md`

## 2. 稳定方案

优先使用 Playwright Chromium：

```bash
cd /home/hfy/APP/All_bot/frontend
npx playwright screenshot \
  --browser chromium \
  --viewport-size=489,552 \
  --wait-for-selector='.lab-composer' \
  --wait-for-timeout=1000 \
  --timeout=20000 \
  http://127.0.0.1:5175/lab-preview \
  /tmp/lab-preview-mobile.png
```

首次使用若提示缺少浏览器：

```bash
cd /home/hfy/APP/All_bot/frontend
npx playwright install chromium
```

浏览器会下载到用户缓存目录，一般不需要改动依赖声明。

## 3. 本机 Chrome Headless 风险

本服务器上观察到 `google-chrome-stable --headless --screenshot` 访问本地 HTTP 页面时可能卡住。即使访问最小本地页面，也可能在底层网络初始化、代理、DNS-over-HTTPS 或后台服务探测阶段阻塞，导致没有截图输出。

因此 AI 助手执行视觉验收时：

- 不要默认使用系统 Chrome headless。
- 不要把系统 Chrome 卡住误判为 Vite 页面不可访问。
- 先用 `curl http://127.0.0.1:<port>/<route>` 判断 dev server 是否可达。
- 再用 Playwright Chromium 截图。

## 4. 推荐工作流

1. 启动 dev server：

```bash
cd /home/hfy/APP/All_bot/frontend
npm run dev -- --host 127.0.0.1
```

2. 读取 Vite 输出端口，例如 `http://127.0.0.1:5175/`。

3. 对目标路由截图，移动端常用 `489,552`，桌面端常用 `1440,900`。

4. 使用 `view_image` 检查截图。

5. 停止本轮启动的 dev server，避免占用端口。

## 5. 截图验收要点

- 首屏主要信息是否符合参考图。
- 移动端是否出现横向溢出、文字挤压或按钮遮挡。
- 高度固定的工具条、输入框、卡片是否因为动态文案改变尺寸。
- 弹窗、抽屉、Popover 是否在桌面/移动端分别只出现一种。
- 文案是否来自 i18n，而非硬编码中文或英文。

## 6. 维护约定

若后续引入正式 Playwright 测试依赖、截图脚本或 CI 视觉回归，应同步更新：

- `.codex/skills/frontend-browser-preview/SKILL.md`
- `docs/skills/README.md`
- 本文档
