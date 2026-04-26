# 全局业务数据字典 (Global Data Dictionary)

本文档旨在统一跨端（Bot/Web/Dash/ComfyUI）的业务词汇表和核心实体定义，防范领域模型的歧义。以下是修仙主题 AI 创作工作台的底层数据契约。

## 1. 核心实体说明

### 1.1 Users (用户实体)
**核心职责**：管理用户（包含跨平台的 TG 和 Web 身份）、修仙等级体系和灵石余额。
| 字段名 (Field) | 类型 (Type) | 业务约束/含义 (Constraints) |
| :--- | :--- | :--- |
| `id` | `Integer` | 内部递增主键（Web 端 JWT Payload 的 `sub` 来源，业务中流转的唯一标识）。 |
| `telegram_id` | `BigInt` | TG 用户唯一 ID（必须建立唯一索引）。 |
| `username` | `String` | TG 用户名。 |
| `credits` | `Integer` | 用户的当前可用灵石数量（代币）。必须大于等于 0。 |
| `current_identity` | `String` | 会员身份等级：`内门弟子`、`核心弟子`、`真传弟子` 等。若为空表示非会员。 |
| `identity_expire_at` | `DateTime` | 会员身份到期时间。 |

### 1.2 UserLogs (灵石流水实体)
**核心职责**：实现强一致性账本，所有灵石变动必须留下审计记录。
| 字段名 (Field) | 类型 (Type) | 业务约束/含义 (Constraints) |
| :--- | :--- | :--- |
| `user_id` | `Integer` | 关联的用户内部 `id`。 |
| `credit_change` | `Integer` | 灵石变化量：正数为充值或退款，负数为任务消耗。 |
| `operation_type` | `String` | 导致变动的行为类型，如：`ltx_video`, `face_swap`, `refund_zombie`, `recharge`。 |
| `description` | `String` | 面向管理端的变动原因描述文本。 |

### 1.3 Orders (充值订单实体)
**核心职责**：跟踪所有跨网关支付通道（微信、支付宝、TON、Stars）的异步回调履约状态，防重复发货（幂等）。
| 字段名 (Field) | 类型 (Type) | 业务约束/含义 (Constraints) |
| :--- | :--- | :--- |
| `out_trade_no` | `String` | 本地生成的预建单号，传给第三方网关作为回调唯一标识。 |
| `status` | `String` | 状态机：`PENDING`（等待支付）, `SUCCESS`（支付完成并已发货）, `FAILED`（支付失败）。 |
| `plan_id` | `Integer` | 购买的会员套餐/直充套餐 ID。 |
| `amount` | `Float` | 应付金额。 |
| `payment_method`| `String` | 支付通道类型，如：`rmb`, `ton`, `stars`。 |

### 1.4 History (任务历史实体)
**核心职责**：记录用户的每一笔创作历史（成功或失败），并用于控制能否投稿至社区。
| 字段名 (Field) | 类型 (Type) | 业务约束/含义 (Constraints) |
| :--- | :--- | :--- |
| `id` | `UUID` | 全局唯一的任务 ID（Redis 队列和 MinIO 对象存储文件名的前缀）。 |
| `user_id` | `Integer` | 创建者的内部 `id`。 |
| `type` | `String` | 任务类型：`i2i_pro` (文生图), `custom_video` (视频), 等。 |
| `params` | `JSON` | 生成时的具体参数（如 `prompt`, `resolution`, `duration`, `seed` 等）。 |
| `allow_contribute`| `Boolean` | **业务红线**：若为 True，允许用户投稿至画廊；若为 False（如克隆模板生成），禁止投稿防套娃。 |
| `is_template` | `Boolean` | 该任务是否是一键应用他人模板而产生的衍生任务。 |

### 1.5 GalleryPost (社区广场投稿实体)
**核心职责**：将私有 `History` 升格为公有社区资源，关联点赞数、应用数。
| 字段名 (Field) | 类型 (Type) | 业务约束/含义 (Constraints) |
| :--- | :--- | :--- |
| `id` | `UUID` | 社区帖子 ID（非历史任务 ID，避免暴露底层结构）。 |
| `task_id` | `UUID` | 关联的源创作任务 `History.id`（1对1）。 |
| `author_id` | `Integer` | 作者 ID（展示用）。 |
| `likes_count` | `Integer` | 收到的点赞总数（支持高并发原子更新）。 |
| `applied_count` | `Integer` | 被其他用户“一键应用（克隆）”的次数。 |
| `lora_model` | `String` | 若为 Lora 视频任务，此字段存储英文模型标签（如 `#BreastGrow`），前端负责本地化映射。 |

### 1.6 UserInteraction (社区互动实体)
**核心职责**：防止用户对同一帖子重复点赞或点踩，以及记录克隆行为。
| 字段名 (Field) | 类型 (Type) | 业务约束/含义 (Constraints) |
| :--- | :--- | :--- |
| `user_id` | `Integer` | 操作者 ID。 |
| `post_id` | `UUID` | 被操作的帖子 `GalleryPost.id`。 |
| `action_type` | `String` | 互动类型：`like`（点赞）, `dislike`（点踩）, `apply`（克隆应用）。 |
*注：`user_id`, `post_id`, `action_type` 存在联合唯一约束 (UniqueConstraint)。*

---

## 2. 状态机与业务枚举

### 2.1 会员体系枚举 (`identity` / `group`)
- **权限与排队优先级 (Priority)**:
  - `真传弟子` (Weight: 10): 最高优先级，不排队，享受所有高级视频节点权限。
  - `核心弟子` (Weight: 5): 中等优先级，享受进阶图像/视频权限。
  - `内门弟子` (Weight: 2): 低优先级，享受基础进阶权限。
  - `元婴期 / 金丹期 / 筑基期` (Weight: 1): 活跃用户等级，拥有基础免排队特权。
  - `凡人 / 练气期` (Weight: 0): 默认等级，可能在系统高负载时遭遇限流或强制排队。

### 2.2 任务状态枚举 (Redis / SSE 流推送)
- `pending`: 任务已提交，在 Redis DB2 队列中等待 Worker 认领。
- `running`: 任务已被 Worker 领取，正在执行 ComfyUI 推理。
- `completed`: 任务成功完成，且已将产物写入 MinIO 热数据桶。
- `failed`: 任务由于超时、配置错误或 OOM 导致执行失败。
- `refund_zombie`: （非标准状态）后台守护协程判定为超时僵尸任务并强制清退的状态。

---
*版本历史：*
* *v1.0.0 - 建立核心业务字典，增加 `allow_contribute` 与 `lora_model` 映射定义。*
