---
name: "frontend-browser-preview"
description: "前端 UI 任务需要在本服务器启动浏览器预览、截图、对照参考图或检查响应式布局时调用。优先使用 Playwright Chromium 生成截图，避免系统 google-chrome headless 在本机访问本地 HTTP 时卡住。"
---

# Frontend Browser Preview

本技能用于前端开发后的视觉验收：打开本地 Vite 页面、生成桌面/移动截图、用截图辅助判断布局是否符合参考图。

## 1. 适用场景
- 用户要求“预览效果”“截图看看”“对照参考图”“检查移动端/桌面端 UI”。
- 修改了 Vue 页面、组件、布局、主题、响应式样式后，需要视觉确认。
- 需要在服务器无桌面环境中获取浏览器截图。

若同时修改 `.vue`、Vue Router、Pinia 或 Vite 前端代码，仍需先加载 `vue-best-practices`。

## 2. 首选方案：Playwright Chromium
本服务器的系统 `google-chrome-stable --headless` 访问本地 HTTP 页面时可能卡住；不要把它作为默认截图方案。

本机已在以下前端包安装 `@playwright/test`，并已下载 Playwright Chromium 到 `/home/hfy/.cache/ms-playwright/`：
- 主 Web 前端：`/home/hfy/APP/All_bot/frontend`
- 管理后台前端：`/home/hfy/APP/All_bot/dashboard/frontend`

后续截图优先进入对应前端包执行 `npx playwright ...`。若缓存被清理或提示缺少浏览器，执行：

```bash
cd /home/hfy/APP/All_bot/dashboard/frontend
npx playwright install chromium
```

不要再用临时 `npm exec --package=playwright` 作为默认方案；项目包内已有稳定 CLI。

## 3. 标准截图流程
先选择实际被修改的前端包。管理后台 UI 任务使用 `dashboard/frontend`，主 Web 工作台任务使用 `frontend`。

启动前端开发服务：

```bash
cd /home/hfy/APP/All_bot/dashboard/frontend
npm run dev -- --host 127.0.0.1
```

读取终端输出的端口。若 `5173`、`5174` 被占用，Vite 会自动选择下一个端口，例如 `5175`。

移动端截图示例：

```bash
cd /home/hfy/APP/All_bot/dashboard/frontend
npx playwright screenshot \
  --browser chromium \
  --viewport-size=489,552 \
  --wait-for-selector='#app' \
  --wait-for-timeout=1000 \
  --timeout=20000 \
  http://127.0.0.1:5175 \
  /tmp/dashboard-mobile.png
```

桌面截图示例：

```bash
cd /home/hfy/APP/All_bot/dashboard/frontend
npx playwright screenshot \
  --browser chromium \
  --viewport-size=1440,900 \
  --wait-for-timeout=1000 \
  --timeout=20000 \
  http://127.0.0.1:5175 \
  /tmp/dashboard-desktop.png
```

截图后使用 `view_image` 查看本地图片；不要只依赖命令成功。

## 4. 参数选择
- `--wait-for-selector` 优先使用当前页面稳定存在的选择器，例如 `.lab-composer`、`#app`、`.dashboard-container`。
- 若页面依赖接口或动画，增加 `--wait-for-timeout=1500` 到 `3000`。
- 用 `--full-page` 获取完整长页面；对首屏对齐参考图时不要加。
- 输出文件放 `/tmp/`，避免污染仓库。

## 5. 清理与注意事项
- 截图完成后停止本轮启动的 dev server，避免遗留进程占端口。
- 若 `npx playwright screenshot` 失败，先确认 dev server URL 可被 `curl` 访问。
- 不要优先尝试 `google-chrome-stable --headless --screenshot`；本机已观察到它访问本地 HTTP 页面时可能被底层网络初始化卡住。
- `frontend/index.html` 会加载 Telegram WebApp SDK；Playwright Chromium 能正常处理该场景，系统 Chrome headless 更容易卡住。
