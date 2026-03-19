# TON Telegram Mini App 技术总结报告

## 目录
1. [项目概述](#1-项目概述)
2. [系统架构与技术栈](#2-系统架构与技术栈)
3. [核心功能模块](#3-核心功能模块)
4. [核心代码解析](#4-核心代码解析)
5. [项目运行与配置](#5-项目运行与配置)
6. [安全性与优化建议](#6-安全性与优化建议)
7. [总结对比](#7-总结对比)

---

## 1. 项目概述

`ton-telegram-app` 是一个现代化的前端单页应用（SPA），专门设计为在 Telegram 内部运行的 **Mini App (TWA - Telegram Web App)**。该项目主要演示了如何将 Telegram 的原生用户身份信息与 TON 区块链的去中心化钱包（TON Connect）深度结合，并实现了一个基于 TON 支付的“个人中心”充值逻辑雏形。

## 2. 系统架构与技术栈

### 技术选型
- **前端框架**：React 19 + TypeScript
- **构建工具**：Vite 7
- **Telegram 集成**：`@twa-dev/sdk` (Telegram Mini App 官方 SDK 的 React 封装)
- **TON 交互**：`@tonconnect/ui-react` (TON 官方提供的高级 React UI 组件库)
- **环境补丁**：`vite-plugin-node-polyfills` (解决浏览器端缺少 Node.js `Buffer` 模块导致的加密学计算报错问题)

### 架构设计
项目采用纯前端架构，所有页面渲染、状态管理（余额、积分暂存在 `localStorage` 中）以及唤起钱包签名的操作均在用户的客户端（Telegram 内置浏览器）完成。它充当了连接传统 Web2 (Telegram 账号体系) 和 Web3 (TON 钱包) 的桥梁。

## 3. 核心功能模块

1. **双重身份认证展示**
   - **Web2 身份**：通过 `WebApp.initDataUnsafe.user` 读取并展示用户的 Telegram ID、用户名及姓名。
   - **Web3 身份**：通过 `<TonConnectButton />` 唤起钱包授权，成功后展示用户的 TON 钱包地址。
2. **个人中心面板**
   - 使用 React 的 `useState` 配合 `localStorage` 模拟了一个基础的账户系统，展示“余额 (TON)”和“积分”。
3. **TON 充值与支付流程**
   - 提供输入框允许用户自定义充值金额。
   - 调用 `tonConnectUI.sendTransaction` 构建并发送包含指定收款地址（通过环境变量 `VITE_MERCHANT_ADDRESS` 配置）和金额（转换为 nanotons）的区块链交易。
   - 支付前端状态流转（处理中/成功/取消），并在成功后更新本地的余额和积分状态。
4. **原生 UI 交互**
   - 调用 `WebApp.showAlert` 替代浏览器的 `alert`，提供符合 Telegram 原生视觉体验的弹窗提示。

## 4. 核心代码解析

- **钱包提供者注入 (`src/main.tsx`)**
  在 React 的根节点使用 `<TonConnectUIProvider>` 包裹应用，并动态传入 `manifestUrl`。这是 `@tonconnect/ui-react` 正常工作的前提，用于告诉钱包当前 DApp 的身份信息。

- **支付逻辑 (`src/App.tsx -> handleTopUp`)**
  ```typescript
  const handleTopUp = async () => {
    // 1. 验证收款地址和金额
    // 2. 如果未连接钱包，调用 tonConnectUI.openModal() 唤起连接弹窗
    // 3. 构建并发送交易
    await tonConnectUI.sendTransaction({
      validUntil: Math.floor(Date.now() / 1000) + 600, // 10分钟有效期
      messages: [{
        address: merchantAddress,
        amount: nano, // 转换为 10^9 精度
      }],
    });
    // 4. 前端状态更新 (仅作 Demo，实际应由后端确认)
  };
  ```

- **Vite 构建配置 (`vite.config.ts`)**
  - 配置了 `nodePolyfills` 以注入 `Buffer`。
  - 配置了严格的 `server` 参数，并针对 HTTPS / HMR 进行了特定域名（如 `chuzeyu.cn`）的支持，以适应 Telegram Mini App 必须在 HTTPS 和特定公网域名下运行的严格要求。

## 5. 项目运行与配置

### 环境要求
- Node.js 环境
- 必须通过 HTTPS 协议暴露到公网（可使用 ngrok, frp 或 Cloudflare Tunnels）。

### 运行步骤
1. 安装依赖：`npm install`
2. 配置环境变量：在根目录创建 `.env` 文件，设置 `VITE_MERCHANT_ADDRESS="你的TON收款地址"`。
3. 本地启动开发服务器：`npm run dev`
4. 通过内网穿透工具将本地的 `5173` 端口映射到公网 HTTPS。
5. 在 Telegram 的 `@BotFather` 中将该 HTTPS 链接配置为 Bot 的 Web App URL。

## 6. 安全性与优化建议

### 当前存在的问题
1. **伪造支付状态**：当前充值成功后的状态更新（增加余额和积分）是直接在**前端**写死的 (`setBalance`, `setPoints`)，且保存在 `localStorage` 中。任何懂技术的用户都可以通过修改本地存储或拦截 JS 执行来伪造余额。
2. **缺乏订单标识**：`sendTransaction` 的 `messages` 中没有包含 `payload`（订单备注）。这会导致即使你将该项目与后端结合，后端也无法区分哪一笔链上转账对应哪一个 Telegram 用户。

### 优化建议
1. **引入后端闭环**：
   - 必须引入后端服务。前端的 `handleTopUp` 仅负责唤起钱包**发送交易**。
   - 交易发送后，前端应将用户的 Telegram ID 和交易意向发送给后端。
   - 由后端监听区块链（如使用 `ton_payment` 文件夹中的 `validator.py` 逻辑），在确认交易上链且金额匹配后，由后端更新数据库中的用户余额。
2. **添加 Payload**：在 `messages` 数组中增加 `payload` 字段，填入后端生成的唯一订单号的 BOC 编码格式，以实现资金的精确对账。
3. **校验 initData**：在向后端请求时，必须在 HTTP Header 中携带 `WebApp.initData`，并在后端验证其 Ed25519 签名，以确保请求确实来自 Telegram 官方客户端且未被篡改。

## 7. 总结对比

与 `/ton_payment` 下的纯原生 HTML/JS 实现相比，本 `ton-telegram-app` 项目：
- **工程化程度更高**：采用了 React 和 Vite，组件化开发，非常适合构建包含复杂交互逻辑的大型 Mini App（如复杂的商城、游戏界面）。
- **体验更佳**：使用了 `@twa-dev/sdk`，深度集成了 Telegram 的原生能力，如获取用户信息、原生弹窗等。
- **定位**：这是一个**优秀的前端工程模板**。如果将其前端界面与 `/ton_payment` 中的后端验证逻辑（`validator.py`）结合，并补齐 `payload` 机制，就能打造出一个生产级别的、企业级的 Telegram + TON 支付系统。