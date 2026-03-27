# Telegram Bot 应用服务与操作逻辑详解

## 1. 概述 (Overview)
本项目是一个修仙主题的 Telegram 图像与视频处理机器人。所有用户的输入（图片、视频、文本）和功能触发均通过 Telegram 交互面板进行。系统内置了多种快捷的 "懒人" 模式以及高自由度的 "自定义" 模式。

底层通过 `APIClient` 与后端的 ComfyUI/AI 推理服务通信，并通过 `PermissionService` 进行严格的积分（灵石）和权限（境界）控制。同时，系统配备了强大的高并发支持、Redis 任务恢复以及后台常驻任务机制。

---

## 2. 核心应用服务与用户操作逻辑

### 2.1 图像处理服务 (Image Services)

*   **快速脱衣 (Undress) / 快速自慰 (Masturbation)**
    *   **操作逻辑**: 用户点击 "🖼️ 懒人P图" 菜单选择对应模式 -> Bot 提示上传图片 -> 用户发送单张图片 -> 系统立即扣除灵石并下发任务。
    *   **后端接口**: `POST /img2img`
    *   **参数映射**: 使用预设 Prompt，`task_type` 分别为 "undress" 或 "masturbation"，基础消耗为 **2 灵石**。

*   **快速换脸 (Face Swap)**
    *   **操作逻辑**: 用户选择换脸模式 -> 步骤一：发送目标**人脸图片** -> 步骤二：发送目标**身体图片** -> 系统进行两步校验后合成并返回。
    *   **后端接口**: `POST /face_swap`
    *   **参数映射**: 将两次收集的图片组装为 `face_image` 和 `body_image` 提交，消耗 **2 灵石**。

*   **随机换脸 (Random Face Swap)**
    *   **操作逻辑**: 用户选择随机换脸 -> 仅需发送一张**人脸图片** -> 系统从内置的 MinIO 模板库 (`templates/quick_face/`) 中随机抽取一张身体图片进行合成。生成结果附带“🔄 再来一张”按钮，可复用人脸快速重新生成。
    *   **后端接口**: `POST /face_swap`

*   **自由 P 图 (Edit)**
    *   **操作逻辑**: 用户选择 "🎨 自由P图" -> 发送一张底图 -> Bot 提示输入提示词 -> 用户发送自定义提示词 (Text) -> 开始生成。
    *   **后端接口**: `POST /img2img`
    *   **参数映射**: 将用户发送的图片和自定义 `prompt` 一起提交。

*   **文生图 (Text to Image)**
    *   **操作逻辑**: 用户选择 "📝 文生图" -> 发送自定义提示词 -> 直接生成图片。
    *   **后端接口**: `POST /text_to_image`
    *   **参数映射**: 仅发送 `prompt`，消耗 **3 灵石**。

---

### 2.2 视频生成服务 (Video Services)

*   **懒人动图模板 (Preset Video Templates)**
    *   **包含模式**: 动图传教士、动图后入、口交黑人、脱衣吐舌、特写口交等。
    *   **操作逻辑**: 用户点击 "🎬 懒人动图" 菜单选择具体姿势 -> 发送单张图片 -> 系统读取用户当前全局设置的画质和时长，套用预设 Prompt 并立即触发生成。
    *   **后端接口**: `POST /perfect_video_insert` (用于插入类) 或 `POST /perfect_video_edit` (用于修改类)。
    *   **参数映射**: 传入单图与预设 prompt，动态传递 `width`, `height`, `length` (继承自全局配置)，消耗根据画质和时长倍率计算（基础 **6 灵石**）。

*   **自定义图生视频 (Custom Video)**
    *   **操作逻辑**: 用户选择 "🎬 自定义图生视频" -> 发送起始图片 -> 系统弹出 **画质与时长选择面板**（如 512p/720p/1024p，时长 5s/8s/10s） -> 用户点击内联按钮完成配置 -> 发送自定义提示词 (Text) 开始生成。
    *   **后端接口**: `POST /perfect_video_edit`
    *   **参数映射**: 动态传递 `prompt`, `width`, `height` (如 720x720), `length` (视频帧数：5s对应81帧, 8s对应129帧)。

---

## 3. 辅助功能与菜单逻辑

*   **👤 个人中心 (Profile)**
    *   展示用户 ID、当前境界（如：外门弟子、金丹期）、灵石余额等。附带 "💎 充值" 按钮，点击拉起 TON 支付 Mini App。
*   **📅 每日签到 (Daily Check-in)**
    *   用户每日点击领取免费的灵石，连续签到达到阈值可触发“境界突破”。
*   **🤝 分享赚灵石 (Referral System)**
    *   生成专属 `t.me/Bot?start={user_id}` 链接，新用户点击进入后，邀请人自动获得 5 灵石基础奖励（若新用户加入频道再获 10 灵石）。
*   **⏳ 排队状态 (Queue Status)**
    *   调用 `GET /system/status` 接口，查询当前 AI 后端的排队任务总数，向用户展示当前服务器繁忙程度。
*   **📢 任务结果公开与分享 (Public Share)**
    *   任务生成完成后，Bot 会提供“公开”与“私密”按钮。
    *   点击“公开”时，系统会检查任务的提示词 (`prompt`) 是否触发违禁词（如儿童相关词汇）。
    *   若包含违禁词，系统会直接警告拦截，拒绝公开；若合规，则请求用户确认后将内容分享至公共大厅。
*   **🛠️ 维护模式 (Maintenance Mode)**
    *   **指令方式**: 管理员可通过 `/maintenance on|off` 指令一键开启或关闭维护模式。
    *   **容器后台方式**: 当 Bot 卡死或无法响应时，也可直接在宿主机通过命令在容器后台控制（开启: `docker exec tg-bot touch /app/MAINTENANCE`，关闭: `docker exec tg-bot rm -f /app/MAINTENANCE`，测试服使用 `tg-bot-test`）。
    *   开启期间，系统将暂停处理新的生成请求，并向用户返回系统维护提示。
*   **📂 多格式媒体接收 (Multi-format Media Handling)**
    *   除了普通的压缩图片（`Photo`），系统支持通过文档 (`Document`) 方式接收无损图片和视频，以及直接接收 `Video` 类型文件，主要用于 `模板共建` 等高级场景，确保获取最佳质量的素材。

---

## 4. 后端接口映射详情 (Backend API Mapping)

系统通过 `src/api_client.py` 封装所有与后端 AI 推理服务器的通信。内置了 **Circuit Breaker (熔断器)** 防雪崩机制，以及针对超时任务的 **Async Retry (异步重试)** 机制。同时所有的请求带上了 UUID 作为 `X-Trace-ID` 方便日志追踪。

| 接口端点 (Endpoint) | 请求方式 | 核心载荷 (Payload / FormData) | 业务场景说明 |
| :--- | :--- | :--- | :--- |
| `/img2img` | POST | `image`, `image2`(可选), `prompt`, `priority` | 通用图生图，支持单图或多图(例如抽插换图) |
| `/face_swap` | POST | `face_image`, `body_image`, `priority` | 换脸业务，需要两张素材图 |
| `/perfect_video_insert` | POST | `image`, `prompt`, `width`, `height`, `length` | 图生视频（插入型） |
| `/perfect_video_edit` | POST | `image`, `prompt`, `width`, `height`, `length` | 图生视频（编辑型，含自定义视频） |
| `/text_to_image` | POST | `prompt` (JSON) | 文生图快速通道 |
| `/system/status` | GET | 无 | 获取后端排队系统状态 |
| `/status/{task_id}` | GET | 无 | 长轮询接口，查询任务进度 `pending`/`done`/`error` |
| `/image/{task_id}` | GET | 无 | 任务完成后，下载图片成品文件流 |
| `/video/{task_id}` | GET | 无 | 任务完成后，下载视频成品文件流 |

---

## 5. 消耗与权限控制限制 (Cost & Permission Limits)

系统通过 `src/quota.py` 与 `src/services/permission_service.py` 构筑了严密的阶梯式权限控制：

1.  **任务基础消耗 (Base Task Costs)**:
    *   快速图片类（脱衣、自慰、换脸）：**2 灵石**
    *   文生图：**3 灵石**
    *   懒人动图、视频类：基础 **6 灵石**
2.  **自定义视频进阶消耗**:
    *   消耗计算公式：`基础画质价格 * 时长倍率`
    *   **画质**: 512p (6 灵石), 720p (18 灵石), 1024p (36 灵石)
    *   **时长**: 5s (x1.0), 8s (x2.0), 10s (x3.0)
    *   *示例：生成 720p 且 10s 的视频，需消耗 18 * 3.0 = 54 灵石。*
    *   *注意：系统禁止同时选择 1024p 和 10s，若触发此非法配置会自动降级为 720p + 10s 并按降级后标准扣费。*
3.  **动态优先级调度 (Dynamic Priority Rules)**:
    *   发送给后端的任务带有 `priority` 参数。用户的优先级根据 **身份（境界）** 以及 **近期使用量** 动态计算。
    *   *例如：真传弟子基础优先级极高，但如果当天生成次数超过 60 次，优先级会自动降级为 0，防止单用户霸占算力。*
4.  **权限控制墙 (Resolution & Duration Permissions)**:
    *   低境界（凡人、练气期）只能生成 512p / 5s 规格的视频。
    *   高境界（筑基期、金丹期）或充值用户（内门、核心、真传弟子）才能解锁 720p/1024p 和 8s/10s 的选项。

---

## 6. 系统级服务与容灾机制 (System-Level Services & Disaster Recovery)

为了保障系统的高可用性、处理高并发请求，以及在异常情况下不损害用户利益，系统实现了以下底层机制：

1.  **动态代理与高并发网络 (Dynamic Proxy & High Concurrency)**:
    *   在启动时 (`bot_test.py`)，系统通过 `get_best_proxy` 自动探测并切换到最佳可用的代理节点。
    *   网络请求模块 (`HTTPXRequest`) 默认配置了超大连接池 (`connection_pool_size=250`)，确保在海量用户同时排队查询时不会发生本地端口耗尽或连接阻塞。
2.  **Redis 任务注册表与异常恢复 (Redis Task Registry & Crash Recovery)**:
    *   **任务追踪**: 所有下发到 AI 后端的任务均实时记录在 Redis (`TaskRegistry`) 中，包含用户上下文和扣费信息。
    *   **异常退款**: 捕获到停机信号时 (`post_shutdown`)，会自动触发 `TaskRegistry.refund_all`，将所有因重启中断的排队/生成中任务强制拦截并全额退还灵石。
    *   **启动恢复**: 在 Bot 重启初始化时 (`post_init`)，会通过 `recovery_service.py` 获取 Redis 中残留的活动任务并尝试进行状态补偿。
3.  **异步后台调度任务 (Async Background Jobs)**:
    *   **TON 交易轮询**: `TonPaymentValidator` 作为独立的守护协程，通过 `poll_transactions` 周期性（每 15 秒）在后台轮询 TON 区块链网络，核对用户的充值订单并自动发货，与主消息循环完全解耦。
4.  **支付双通道机制 (Dual Payment Channels)**:
    *   支持 **TON 区块链支付** 与 **Telegram Stars 原生支付** 双通道。两者共享订单系统逻辑。
5.  **灵石机制与数据审计 (Credits & Audit)**:
    *   **临时灵石 (`temp_credits`) 废弃**: *注：此机制已被完全废弃。* 目前所有的途径（包括签到）获取的均为永久灵石。所有的代码中均不再使用和判断临时灵石。
    *   **强制数据流审计**: 任何涉及灵石增减的操作，**必须**同步在 `user_logs` 表中插入流水记录。
