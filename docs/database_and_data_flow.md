# Bot 数据结构与数据流转梳理

本项目使用 **PostgreSQL** 作为底层数据库，并通过 **SQLAlchemy** 进行异步 ORM 映射。整体数据模型围绕“用户资产（灵石）、活跃度（境界）、消费历史、支付充值”这几个核心维度展开。

---

## 一、 核心数据表结构 (Models)

### 1. 用户表 (`users`)
系统的核心表，记录了用户的基础信息、资产、身份和活跃度统计。

*   **基础信息**: `id` (Telegram User ID, 主键), `username`, `full_name`, `created_at`, `last_activity`
*   **资产字段**:
    *   `credits`: 永久灵石（充值、邀请奖励获得）。
    *   `temp_credits`: 临时灵石（签到获得，每 48 小时清空）。
*   **身份与修为**:
    *   `user_group`: 宗门修为（如：凡人, 练气期, 筑基期, 金丹期）。
    *   `current_identity`: VIP 身份（如：外门弟子, 内门弟子, 核心弟子, 真传弟子）。
    *   `identity_expire_at`: VIP 身份过期时间。
    *   `is_channel_member`: 是否已加入官方频道（决定是否能脱离凡人）。
*   **活跃度统计 (反范式化设计，为了查询性能)**:
    *   `referral_count`: 累计邀请人数。
    *   `generation_count`: 累计生成任务数。
    *   `checkin_count`: 累计签到天数。

### 2. 用户流水表 (`user_logs`)
**极其重要的对账表**，记录了每一次灵石变动的明细，相当于用户的“银行流水”。

*   **核心字段**: 
    *   `operation_type`: 变动类型（如：`checkin` 签到, `generation` 生成消费, `referral_reward` 邀请奖励, `recharge` 充值）。
    *   `credit_change`: 变动额度（正数为增加，负数为扣除）。
    *   `current_balance`: 变动后的余额快照。
    *   `extra_info`: 附加信息（JSON 格式，例如充值的订单号、生成任务的参数等）。

### 3. 邀请关系表 (`referrals`)
记录用户的上下级邀请链路。

*   **核心字段**: `inviter_id` (邀请人), `invitee_id` (被邀请人，唯一), `channel_reward_claimed` (是否已领取进群的 20 灵石奖励)。

### 4. 任务历史表 (`history`)
记录用户每次 AI 生成任务的执行情况（与后端的交互）。

*   **核心字段**: `task_id` (后端返回的任务ID), `type` (生成模式，如 image, video), `prompt` (提示词), `input_file` (输入图片路径), `output_file` (输出结果路径)。

### 5. 支付与套餐表 (`membership_plans`, `orders`)
用于处理 TON 区块链的充值与对账。

*   **`membership_plans` (套餐表)**: `name` (如：基础月卡), `identity_name` (对应赋予的 VIP 身份), `price_ton` (TON 币标价), `reward_credits` (赠送灵石), `duration_days` (有效期)。
*   **`orders` (订单表)**: 
    *   `order_id`: 唯一订单号（对应链上转账的 Payload）。
    *   `status`: 状态 (`PENDING`, `SUCCESS`, `FAILED`)。
    *   `tx_hash`: 链上交易哈希（Unique约束，**防双花/重复处理的核心**）。

---

## 二、 核心业务数据流转 (Data Flow)

### 场景一：新用户注册与邀请奖励流转
1.  **点击专属链接**: 新用户点击 `t.me/bot?start=12345` 进入。
2.  **创建记录**: `QuotaManager.process_referral` 被调用。在 `users` 表插入新用户，获得初始 20 灵石。
3.  **绑定关系**: 在 `referrals` 表插入一条记录，绑定 `inviter_id=12345` 和 `invitee_id=新用户ID`。
4.  **发放初级奖励**: 邀请人 `credits` 增加 5，`referral_count` +1。
5.  **记录流水**: 在 `user_logs` 插入两条记录：一条新用户的 `welcome_bonus` (+20)，一条邀请人的 `referral_reward_initial` (+5)。

### 场景二：AI 生成任务消费流转
1.  **触发生成**: 用户发起一个消耗 6 灵石的视频任务。
2.  **权限与余额校验**: `PermissionService` 调用 `check_quota`。
3.  **优先扣除机制**: 
    *   先检查 `users.temp_credits`（临时灵石）。如果足够，只扣临时灵石。
    *   如果不够，清空 `temp_credits`，差额部分从 `users.credits`（永久灵石）中扣除。
4.  **记录流水**: 在 `user_logs` 中插入一条负数流水 (`credit_change = -6`)，并保存当前的余额快照。
5.  **生成与归档**: 任务完成后，将输入输出文件路径和 Prompt 写入 `history` 表。

### 场景三：TON 区块链支付与自动发货流转
1.  **拉起支付**: 前端 Mini App 生成一个包含订单信息的 Payload（如 `ORDER:user_id:plan_id:timestamp`），用户在钱包中确认转账。
2.  **轮询监听**: Bot 后台的 `TonPaymentValidator` 守护协程每 15 秒通过 TON RPC 接口拉取商家地址的最新交易。
3.  **解析与验签**: 识别到带有 `ORDER` 前缀的交易，解析出 `user_id` 和 `plan_id`，并校验转账的 TON 金额是否大于等于 `membership_plans.price_ton`。
4.  **防双花入库**: 将交易的 `hash` 尝试插入 `orders.tx_hash`。如果违反 Unique 约束，说明该笔交易已处理，直接跳过。
5.  **自动发货**: 
    *   更新 `users.credits`（增加套餐对应的灵石）。
    *   更新 `users.current_identity`（如变更为“内门弟子”）。
    *   更新 `users.identity_expire_at`（当前时间 + 30天）。
6.  **记录流水**: 在 `user_logs` 中插入一条 `recharge` 操作类型的流水。
7.  **下发通知**: 通过 Telegram Bot 接口向用户发送“充值成功”的实时通知。

---

## 三、 定时任务流 (Cron Jobs)

*   **临时灵石清理**: 在 `bot_test.py` 中注册了 `clear_temp_credits_job`。每隔 **48 小时** 的北京时间零点，执行 `UPDATE users SET temp_credits = 0 WHERE temp_credits > 0`。强制收回用户未使用的免费福利。
*   **境界自动刷新**: 每次用户触发签到 (`checkin`) 或完成生成任务时，都会异步触发 `refresh_user_group` 方法，根据最新的 `checkin_count` 和 `generation_count` 自动判断是否满足升级条件，如果满足则实时更新 `users.user_group`。