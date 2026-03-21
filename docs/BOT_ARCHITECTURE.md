# Bot 机器人服务七大核心模块架构梳理

目前整个系统采用了**高内聚低耦合的分层设计**，分为网关层、业务逻辑层（多个独立 Agent 负责不同业务）以及基础设施层。从 `src/bot_test.py` 这个入口文件延伸，目前的系统可以分为以下 7 大核心模块系统：

## 1. 🚀 生命周期与网络网关 (Entry & Lifecycle Management)
**核心文件：** `src/bot_test.py`
* **双环境切换**：通过读取 `.env` 中的 `BOT_TYPE`（PROD 或 TEST），动态加载不同的 Telegram Token，支持正式服与测试服共用一套代码的“双机器人部署”机制。
* **动态代理探活 (`get_best_proxy`)**：内建了多个常见代理端口（如 7890、10808 等）的自动连通性检测。如果默认代理不可用，会自动降级尝试本地代理甚至回退到直连，保证 Bot 在各种网络环境下的存活率。
* **后台任务调度**：注册了 `clear_temp_credits_job` 定时任务，利用 `JobQueue` 每 48 小时自动清空用户的临时“灵石”（免费积分）。
* **路由注册与事件分发**：负责初始化 `ApplicationBuilder` 并挂载所有的命令、文本、图片、视频和按钮点击事件处理器（Handlers）。

## 2. 💬 用户交互界面系统 (Interface Agent / Handlers)
**核心目录：** `src/handlers/` (`command_handler.py`, `message_handler.py`, `callback_handler.py`)
* **会话状态机**：利用 Telegram 的 `context.user_data` 维护用户当前处于哪种工作模式（如 `MODE_FACESWAP` 换脸、`MODE_CUSTOM_VIDEO` 自定义视频等），从而决定对用户发送的媒体文件执行什么操作。
* **UI 渲染**：负责生成回复菜单、内联按钮（Inline Keyboard），如“签到”、“个人中心”、“充值”、“私密生成”等选项。
* **内容合规与拦截**：对用户发送的图片尺寸、视频格式进行初步校验拦截，同时在结果公开分享前进行提示词违禁词（`FORBIDDEN_WORDS`）筛查，然后再派发给下层的 Service 层。

## 3. ⚖️ 经济、权限与修仙体系 (Permission Agent / Sect Elder)
**核心文件：** `src/services/permission_service.py`, `src/quota.py`
* **双轨制积分经济**：管理“永久灵石” (`credits`) 和“临时灵石” (`temp_credits`)。用户消耗时，系统会优先扣除临时灵石。
* **修仙境界 (Leveling System)**：根据用户的活跃度（签到、邀请、生成次数），动态计算“境界”（凡人 -> 练气期 -> 筑基期 -> 金丹期），境界越高的用户，任务调度的优先级越高。
* **强制频道订阅**：作为看门人，验证用户是否已经加入了官方指定的 Telegram 频道 (`REQUIRED_CHANNEL_ID`)。
* **推广与邀请**：处理用户的邀请链接逻辑，为邀请者和被邀请者发放对应奖励。

## 4. 🧠 AI 任务编排系统 (Generation Agent / Alchemist)
**核心文件：** `src/services/task_service.py`
* **工作流编排**：接收 Handler 传来的文件和模式指令后，负责将图片/视频下载到本地临时目录进行预处理。
* **多步骤状态维护**：处理复杂的任务流，例如换脸需要“先传目标人脸图片，再传身体图片”的 2 步流程。
* **轮询与投递**：将构建好的 payload（包含分辨率、Prompt 等）提交给底层的 ImageService，并启动异步任务轮询 AI 后端的生成进度。
* **后处理**：生成成功后，将成品下载回 Bot 服务器，并最终发送给用户，随后清理临时文件。

## 5. 🔌 底层通信与高可用系统 (Backend Connector)
**核心文件：** `src/api_client.py`, `src/services/image_service.py`, `src/circuit_breaker.py`
* **REST 协议封装**：负责所有发往 AI 推理服务器（如 ComfyUI 后端）的 HTTP 异步请求（`img2img`, `face_swap`, `perfect_video_edit` 等）。
* **熔断器 (Circuit Breaker)**：为防止 AI 后端宕机或过载导致 Bot 线程全部卡死，引入了熔断机制。如果请求连续失败多次，系统会快速失败（Fast-fail），并提示用户“后端正在维护”。
* **自动重试**：处理网络抖动造成的偶发超时，进行安全的异步重试。

## 6. 💰 TON 区块链支付系统 (Payment Agent)
**核心文件：** `src/services/payment_validator.py`
* **去中心化对账**：以独立守护协程的形式（在 `bot_test.py` 的 `post_init` 中启动），每 15 秒主动轮询一次 TON Center RPC 节点，拉取商家钱包地址的最新链上交易。
* **BOC Payload 解析**：解析转账附带的格式化备注（`ORDER:{tgUserId}:{planId}:{timestamp}`），防止数据篡改。
* **防双花机制**：校验转账金额是否符合套餐要求，并将交易哈希记录入库 (`orders` 表) 防止同一笔转账被重复处理。处理成功后，自动为用户开通内门/核心/真传弟子身份，下发“灵石”并发放通知。

## 7. 💾 数据持久化系统 (Data Steward Agent)
**核心目录/文件：** `src/database/` (`core.py`, `models.py`), `src/services/log_service.py`, `src/services/storage.py`
* **ORM 与数据库**：使用 SQLAlchemy + PostgreSQL 管理 `User`（用户资产与身份）、`History`（生成历史）、`Referral`（邀请关系）等表。
* **行为审计 (`UserLog`)**：记录每一笔“灵石”的变动明细（消费流水、充值记录、任务报错原因等），以便后续的对账和客服排查。
* **资源存储**：与 MinIO（S3兼容存储）对接，用于持久化保存生成出来的视频和图片文件，减轻 Bot 服务器磁盘压力。
