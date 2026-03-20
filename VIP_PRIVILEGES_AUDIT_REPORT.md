# 充值身份组与特权系统现状审计报告

## 1. 体系概述

当前 Bot 系统在数据库层面设计了两套并行的用户等级体系：
*   **修仙境界 (`user_group`)**：代表用户的活跃度（如：凡人、练气期、筑基期、金丹期），通过签到、邀请和完成生成任务免费晋升。
*   **当前身份 (`current_identity`)**：代表用户的付费状态（如：凡人、内门弟子、核心弟子、真传弟子），通过充值购买套餐获得，并受 `identity_expire_at` 字段控制过期时间。

---

## 2. 现状审计结论：**“已发货，但特权未实装”**

目前，用户在完成 TON 支付后，后端的 `TonPaymentValidator` 会成功为其发放“永久灵石”，并成功将其 `current_identity` 更新为对应的 VIP 身份。

**然而，在实际的任务执行与业务逻辑中，系统目前仅对免费的“修仙境界 (`user_group`)”进行了特权判定，完全忽略了付费的“当前身份 (`current_identity`)”。** 充值用户除了获得了额外的灵石外，无法享受其身份应有的排队、画质和折扣等特权。

---

## 3. 具体缺失的特权代码分析

### 3.1 特权 A：极速排队通道（高优先级未生效）
*   **预期**：VIP 身份（如真传弟子）在拥堵时应获得极高的动态优先级，实现插队。
*   **代码现状**：
    在 `src/services/permission_service.py` 的 `calculate_user_priority` 方法中：
    ```python
    group = await self.get_user_group(user_id) # 仅查询了 user_group
    usage = await self.quota_manager.get_daily_usage(user_id)
    rules = DYNAMIC_PRIORITY_RULES.get(group, [])
    ```
*   **问题**：排队权重完全依赖 `user_group`。`src/constants.py` 中的 `DYNAMIC_PRIORITY_RULES` 仅配置了金丹期、筑基期等境界，未配置任何 VIP 身份。

### 3.2 特权 B：解锁高画质（720x720 未生效）
*   **预期**：拥有 VIP 身份的用户生成视频时，应自动解锁 `720x720` 的高清画质。
*   **代码现状**：
    在 `src/services/task_service.py` 中处理视频生成前：
    ```python
    user_group = await permission_service.get_user_group(user_id) # 仅查询了 user_group
    width, height = VIDEO_RESOLUTIONS.get(user_group, VIDEO_RESOLUTIONS["default"])
    ```
*   **问题**：`VIDEO_RESOLUTIONS` 字典中仅有“金丹期”和“筑基期”的配置。如果一个刚注册就充值的用户（境界还是“凡人”，但身份是“核心弟子”），系统依然会按默认的 `512x512` 处理。

### 3.3 特权 C：消费折扣未生效
*   **预期**：高阶身份在执行任务时，应享受一定的积分消耗折扣（如 8 折）。
*   **代码现状**：
    虽然在 `src/database/models.py` 中设计了 `DiscountRule` 表，并在 `src/database/core.py` 中预设了折扣数据，但生产环境并未调用。
    在 `PermissionService.check_quota` 和 `TaskService` 的实际扣费环节，系统依然从 `constants.py` 中的 `TASK_COSTS` 字典读取固定数值（如图生图 2 灵石，视频 6 灵石）进行刚性扣除。

---

## 4. 修复与实装建议

若要兑现向付费用户承诺的特权，必须在核心业务链路上进行如下改造：

1.  **扩展配置字典 (`src/constants.py`)**：
    在 `DYNAMIC_PRIORITY_RULES` 和 `VIDEO_RESOLUTIONS` 中补充 `current_identity` 的键值对映射。例如：
    ```python
    VIDEO_RESOLUTIONS = {
        "真传弟子": (1024, 1024),
        "核心弟子": (720, 720),
        "内门弟子": (720, 720),
        "金丹期": (720, 720),
        "筑基期": (720, 720),
        "default": (512, 512)
    }
    ```
2.  **重构权限查询服务 (`src/services/permission_service.py`)**：
    新增 `get_user_identity(user_id)` 方法以查询用户的付费身份，并判断该身份是否过期。
3.  **重构优先级与画质判定逻辑**：
    修改 `calculate_user_priority` 和 `task_service.py` 中的判定逻辑，采用 **“就高原则”**：比较用户的 `user_group` 和 `current_identity`，取两者中能获得的最高画质和最高优先级。
4.  **实装动态折扣计费**：
    在扣费前，根据用户的有效 `current_identity`，计算出折扣后的实际 `cost` 再执行扣款操作。