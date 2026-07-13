# TON Connect + Telegram Mini App 快速入门

这个项目是基于 `https://github.com/ton-connect` 和 Telegram Web Apps (TWA) SDK 构建的示例项目。

## 核心技术栈
- **React + TypeScript + Vite**: 现代前端框架和构建工具。
- **@tonconnect/ui-react**: TON 官方提供的钱包连接 UI 组件库。
- **@twa-dev/sdk**: Telegram Mini App SDK，用于与 Telegram 客户端交互。
- **vite-plugin-node-polyfills**: 解决浏览器环境中缺少 Node.js 内置模块（如 Buffer）的问题。

## 如何运行

1. **安装依赖**:
   ```bash
   npm install
   ```


2. **本地启动**:
   ```bash
   npm run dev
   ```

3. **接入 Telegram**:
   - 由于 Telegram Mini App 需要通过 HTTPS 访问，建议使用 `ngrok` 或 `frp`（你已经有相关文件夹）将本地端口 `5173` 映射到公网。
   - 打开 Telegram 找 `@BotFather`。
   - 创建新机器人 (`/newbot`)。
   - 配置 Mini App (`/newapp`)，在填写 Web App URL 时输入你的公网 HTTPS 链接。
   - 获取你的 App 链接并在 Telegram 中打开。

## 项目结构
- [main.tsx](src/main.tsx): 配置 `TonConnectUIProvider`。
- [App.tsx](src/App.tsx): 实现钱包连接按钮和 Telegram 用户信息显示。
- [vite.config.ts](vite.config.ts): 配置 Node.js Polyfills 插件。

## 注意事项
- **Manifest URL**: 在 `main.tsx` 中，`manifestUrl` 目前使用的是测试链接。生产环境下，你需要将项目目录下的 `public/tonconnect-manifest.json`（你可以自己创建一个）部署到公网，并确保其 URL 与你的域名匹配。
- **HTTPS**: Telegram Mini App 必须在 HTTPS 环境下运行。
