# 全局业务数据字典 (Global Data Dictionary)

本文档统一 AllBot 跨 Telegram、Web、Dashboard、支付与社区系统的核心业务术语。以下内容以当前代码已落地的数据模型与业务语义为准。

## 1. 核心实体

### 1.1 Users（用户）
**职责**：保存内部用户身份、Telegram 映射、基础资料、灵石余额与身份状态。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `id` | `Integer` | 内部用户主键；JWT `sub` 的来源；跨端核心用户标识。 |
| `telegram_id` | `BigInt` | Telegram 用户 ID。当前登录与权限统计仍会频繁用到。 |
| `username` | `String` | 当前同时承担 TG 用户名与 Web 账号用户名角色。 |
| `hashed_password` | `String` | Web 密码哈希，采用 `SHA256` 预处理后再 `bcrypt`。 |
| `password_version` | `Integer` | 改密后用于让旧 token 失效的版本号。 |
| `credits` | `Integer` | 当前可用灵石余额。 |
| `current_identity` | `String` | 当前会员身份，例如 `内门弟子`、`核心弟子`、`真传弟子`。 |
| `identity_expire_at` | `DateTime` | 当前会员身份的到期时间。 |

### 1.2 UserLogs（灵石流水）
**职责**：记录所有灵石变动，作为资产审计基线。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `user_id` | `Integer` | 关联 `users.id`。 |
| `credit_change` | `Integer` | 本次灵石增减值；正数表示加石，负数表示扣石。 |
| `operation_type` | `String` | 业务来源，如生成扣费、充值、返佣兑换灵石等。 |
| `description` | `String` | 审计描述。 |

### 1.3 Orders（订单）
**职责**：承载本地业务单、支付状态与履约相关字段。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `order_id` | `String` | 本地业务单号；RMB 回调与 TON 订单载荷都会使用。 |
| `telegram_id` | `BigInt` | 实际关联内部 `users.id`，字段名沿用旧命名。 |
| `plan_id` | `Integer` | 购买的套餐 ID。 |
| `status` | `String` | `PENDING / SUCCESS / FAILED`。 |
| `tx_hash` | `String` | 外部流水，TON 等链路的幂等锚点；唯一。 |
| `payment_channel` | `String` | 当前支付通道，如 `RMB`、`TON`、`STARS`。 |
| `commission_usdt` | `Decimal(10,4)` | 该订单对应的首单返佣金额快照。 |
| `paid_at` | `DateTime` | 实际支付成功时间。 |

### 1.4 AffiliateTransaction（返佣账本）
**职责**：记录返佣的入账与出账，是邀请体系的主账本。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `user_id` | `BigInt` | 邀请人内部用户 ID。 |
| `amount_usdt` | `Decimal(10,4)` | 本次返佣金额或兑换扣减金额。 |
| `transaction_type` | `String` | 如 `COMMISSION_ACCRUAL`、`CREDITS_REDEEM`。 |
| `direction` | `String` | `IN / OUT`。 |
| `reference_type` | `String` | 关联对象类型，如订单或返佣兑换记录。 |
| `reference_id` | `String` | 关联对象标识。 |
| `idempotency_key` | `String` | 返佣账本侧的唯一幂等键。 |
| `status` | `String` | 当前主要使用 `SUCCESS`。 |
| `details` | `JSON` | 返佣来源、汇率快照、兑换明细等。 |

### 1.5 AffiliateRedeem（返佣兑换记录）
**职责**：记录返佣余额兑换灵石的业务单与结果快照。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `user_id` | `BigInt` | 发起兑换的用户。 |
| `redeem_type` | `String` | 当前已落地类型为 `CREDITS`。 |
| `redeem_option_key` | `String` | 当前为灵活 USDT 兑换选项键。 |
| `requested_amount_usdt` | `Decimal(10,4)` | 请求兑换金额。 |
| `amount_usdt` | `Decimal(10,4)` | 实际兑换金额。 |
| `credits_granted` | `Integer` | 实际发放灵石数。 |
| `exchange_rate_snapshot` | `String` | 当前汇率快照，如 `1.0000 USDT = 90 credits`。 |
| `rounding_mode` | `String` | 当前使用 `ROUND_HALF_UP`。 |
| `idempotency_key` | `String` | 单用户幂等键。 |
| `details` | `JSON` | 当前已存 `current_credits`、`available_balance_usdt` 等快照。 |

### 1.6 History（任务历史）
**职责**：记录任务输入、产物、展示元数据与后续复用上下文。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `task_id` | `String` | 任务唯一标识；广场与结果查询都会引用。 |
| `user_id` | `Integer` | 创建者内部 ID。 |
| `type` | `String` | 任务类型，如图像、视频、编辑、LoRA 等。 |
| `prompt` | `Text` | 当前任务提示词主文本。 |
| `input_file` | `String` | 输入文件存储路径。 |
| `output_file` | `String` | 输出文件路径。 |
| `width/height/duration` | `Integer` | 输出媒体元数据。 |
| `requested_duration` | `Integer` | 业务请求语义下的视频时长，不等同于输出元数据。 |
| `billing_resolution` | `String` | 视频计费档位分辨率语义。 |
| `allow_contribute` | `Boolean` | 是否允许投稿到社区。 |
| `is_template` | `Boolean` | 是否由模板应用衍生。 |

### 1.7 GalleryPost（广场帖子）
**职责**：把历史任务升格为公开社区帖子。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `id` | `Integer` | 帖子主键。 |
| `task_id` | `String` | 关联历史任务。 |
| `user_id` | `BigInt` | 帖子作者。 |
| `media_type` | `String` | `image / video`。 |
| `width/height/duration` | `Integer` | 帖子展示用媒体元数据。 |
| `likes_count` | `Integer` | 点赞数。 |
| `dislikes_count` | `Integer` | 点踩数。 |
| `applied_count` | `Integer` | 被成功应用次数。 |
| `comments_count` | `Integer` | 评论数。 |
| `is_active` | `Boolean` | 是否仍上架可见。 |

### 1.8 UserInteraction（互动记录）
**职责**：记录用户对帖子的一次性互动，防止重复记账。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `user_id` | `BigInt` | 操作者。 |
| `post_id` | `Integer` | 目标帖子。 |
| `action_type` | `String` | `like / dislike / apply`。 |
| `created_at` | `DateTime` | 互动发生时间。 |

注：`user_id + post_id + action_type` 存在联合唯一约束。

### 1.9 GalleryComment（广场评论）
**职责**：保存帖子评论与分页读取基础数据。

| 字段 | 类型 | 当前语义 |
| :--- | :--- | :--- |
| `id` | `Integer` | 评论主键。 |
| `post_id` | `Integer` | 关联帖子。 |
| `user_id` | `BigInt` | 评论作者。 |
| `content` | `Text/String` | 评论内容。 |
| `is_active` | `Boolean` | 是否仍有效。 |
| `created_at` | `DateTime` | 评论时间。 |

## 2. 核心业务枚举

### 2.1 身份与权限
- `current_identity`
  - `内门弟子`
  - `核心弟子`
  - `真传弟子`
- `user_group`
  - 代表修为境界线，用于优先级与部分准入判断。
- Web 准入
  - 当前不是单看身份或单看境界，而是由允许身份集合与允许境界集合共同判定。

### 2.2 任务状态
- `pending`
- `running`
- `success/completed`
- `failed`
- 僵尸清理属于运维恢复语义，不应简单当作常规用户态业务状态。

### 2.3 支付与返佣状态口径
- 订单状态：`PENDING / SUCCESS / FAILED`
- 返佣账本方向：`IN / OUT`
- 返佣兑换状态：当前主口径为 `SUCCESS`

## 3. 当前必须统一的词汇口径
- **内部用户 ID**：指 `users.id`，是核心业务与 JWT 的统一用户标识。
- **Telegram ID**：指 Telegram 平台用户 ID，不等同于内部用户 ID。
- **灵石余额**：指 `users.credits`。
- **返佣可兑换余额**：指通过 `affiliate_transactions` 汇总得到的可用 USDT 余额，不是单独冗余列。
- **请求语义时长**：指 `requested_duration`，不是最终媒体探测到的 `duration`。
- **模板应用主路径**：指 Web `apply-context -> workbench -> generate`，不是 Telegram 老 FSM。

## 4. 维护声明
- 若字段名与历史文档、当前代码存在旧命名兼容，应在字典中同时说明“字段名来源”和“当前真实语义”。
- 若新业务仅存在实施方案、尚未落地代码，不应提前写入本数据字典的“当前语义”部分。
