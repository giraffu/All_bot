# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全面开发指南。它总结了项目的架构、核心逻辑、数据流以及关键系统。

## 1. 项目概述
这是一个提供 AI 图像和视频生成服务（例如：换脸、文生图、视频模板等）的 Telegram 机器人。它具有独特的“修仙”主题进度系统、双轨制代币经济模型，并集成了去中心化的 TON 区块链支付。

## 2. 系统架构 (7 大核心模块)
* **入口与生命周期 (`src/bot_test.py`)**：处理 PROD/TEST 双环境切换、动态代理探活、路由注册以及后台定时任务调度（例如 48 小时定时清理临时灵石）。
* **交互与处理器 (`src/handlers/`)**：管理用户状态机（如处理多步换脸逻辑）、渲染 UI（内联键盘 Inline Keyboards），并拦截和初步校验用户输入。
* **权限与经济 (`src/services/permission_service.py`, `src/quota.py`)**：管理双代币系统，计算动态排队优先级，并基于用户的修为和身份执行权限控制。
* **任务编排 (`src/services/task_service.py`)**：处理复杂的工作流编排、多步状态维护、构建发送给 AI 的 payload，并异步轮询 AI 后端的任务状态。
* **底层通信 (`src/api_client.py`)**：封装与 AI 后端（如 ComfyUI）的 REST API 通信。内置了**熔断器 (Circuit Breaker)**和异步重试机制，以保障系统高可用性。
* **TON 支付系统 (`src/services/payment_validator.py`)**：一个独立的守护协程，每 15 秒主动轮询一次 TON Center RPC 节点，以校验链上交易并自动完成发货。
* **数据持久化 (`src/database/`, `src/services/storage.py`)**：使用 PostgreSQL + SQLAlchemy 管理关系型数据，使用 MinIO（兼容 S3 的对象存储）存储生成的媒体文件。

## 3. 修仙与 VIP 身份系统
机器人使用双轨制特权系统来控制高画质（最高 1024p）和长时长（最高 10s）视频生成的访问权限，以及决定在 AI 后端的排队优先级。

* **修为系统（免费/活跃度驱动）**： 
  * 晋升路线：凡人 -> 练气期 -> 筑基期 -> 金丹期。
  * 通过每日签到、邀请新用户和累计生成次数自动升级。升级可解锁更高的画质和基础排队优先级。
* **VIP 身份（付费驱动）**： 
  * 晋升路线：外门弟子（默认） -> 内门弟子 -> 核心弟子 -> 真传弟子。
  * 通过 TON 支付购买套餐获得。立即无条件解锁最高画质/时长，并获得极高的排队优先级加成。
* **动态优先级叠加机制**：`最终优先级 = 修为优先级 + 身份优先级`。无论境界多高，该优先级都会根据用户当日的生成次数动态衰减，以防止单用户霸占算力。

## 4. 经济与消耗模型
* **双轨制代币**：
  * `credits`（永久灵石）：通过充值或邀请奖励获得。永不过期。
  * `temp_credits`（临时灵石）：通过每日签到获得。消费时**优先扣除**。后台每 48 小时会自动清空全服的临时灵石。
* **任务消耗**：
  * 图像类任务（换脸、修图）：基础消耗约 2-3 灵石。
  * 视频类任务：基础消耗 6 灵石。自定义视频的消耗根据用户选择的画质和时长成倍增加（例如：1024p 10s 的视频 = 55 灵石）。

## 5. 数据库与数据流转
* **`users`**：核心用户表，存储灵石余额、修为境界、身份信息和各种活跃度统计。
* **`user_logs`**：**极其关键的审计表**。记录每一次灵石变动的明细（签到发放、生成扣费、充值等），用于后续对账。
* **`referrals`**：记录邀请人与被邀请人的上下级关系。
* **`history`**：记录全服每一次 AI 生成任务的执行情况（Task ID、提示词、输入输出路径）。
* **`orders` & `membership_plans`**：处理 TON 区块链的充值与对账。`orders.tx_hash` 字段设有 Unique 约束，这是防止同一笔转账被双花/重复处理的核心。

## 6. TON 支付数据流
1. **前端 (Mini App)**：部署在 Cloudflare Pages 的 React 应用。用户点击充值后，前端生成特定的 BOC payload（包含备注 `ORDER:{userId}:{planId}:{timestamp}`）并唤起钱包请求签名。
2. **后端轮询监听**：Bot 中的 `TonPaymentValidator` 协程每 15 秒通过 TON RPC 接口拉取商家地址的新交易。
3. **解析与校验**：解析交易中的 BOC 备注，校验 `tx_hash` 是否在 `orders` 中已存在（防双花），并核对转账的 TON 金额是否充足。
4. **自动发货**：如果校验通过，开启数据库事务原子性地更新 `users.credits` 和 `users.current_identity`，并在 `user_logs` 中插入一条 `recharge` 流水。

## 7. 管理后台 (Dashboard)
* **后端 (FastAPI)**：与 Bot 共享同一个 PostgreSQL 数据库和 MinIO 实例。实现了 JWT 鉴权，提供数据统计、用户管理、日志审计接口。它不会直接暴露文件，而是生成 MinIO 预签名 URL 供前端访问。
* **前端 (Vue 3 + Vite)**：使用 Ant Design Vue 和 ECharts 渲染可视化数据大屏，监控实时队列，审计日志，并支持管理员给特定用户手动发货。

## 8. 服务重启与部署指令 (Deployment & Restart)
本项目使用 Docker Compose 进行容器化部署。如果在开发或维护过程中需要重启服务，请在**项目根目录**执行以下指令（注意：重启服务时需要强制重建镜像以确保代码变更生效）：

* **正式服 Bot (Production)**
  * **重启并重建**: `docker-compose -f deploy/docker-compose.yml up -d --build bot`
* **测试服 Bot (Test)**
  * **重启并重建**: `docker-compose -f deploy/docker-compose-test.yml up -d --build bot-test`
* **管理后台 (Dashboard)**
  * **一键重启并重建 (包含前后端)**: `docker-compose -f dashboard/docker-compose.yml up -d --build`
  * **仅重启并重建后端**: `docker-compose -f dashboard/docker-compose.yml up -d --build dashboard-backend`
  * **仅重启并重建前端**: `docker-compose -f dashboard/docker-compose.yml up -d --build dashboard-frontend`

---
**👨‍💻 开发者注意事项**：在实现新功能或修复 Bug 时，请务必确保：
1. 任何涉及灵石的扣除或增加，都必须同步在 `user_logs` 表中插入流水记录。
2. 遵守高可用性设计，与外部 AI 接口交互时必须走 `api_client.py` 以利用熔断器和重试机制。
3. 数据库操作必须正确使用 SQLAlchemy 的异步会话 (`async session`)，处理支付或扣费时合理使用事务回滚。