# 关于在 Bot 端和 Web 端个人中心展示“邀请分成数据”的实施方案 (已深度优化)

## 1. 需求背景
目前管理后台（Dashboard）已经实现了全局的“邀请奖励与充值数据分析”，能够统计每个邀请人名下所有受邀者**首笔充值金额的 10%** 作为分成奖励（统一折算为 USDT）。
现需要在面向 C 端用户的 **Telegram Bot 个人中心** 和 **Web 端个人中心 (Profile)** 中，同步向用户展示其个人的“预估分成收益”，以激励用户进行推广。

---

## 2. 核心架构调整方案 (遵循 Core Isolation 与高性能原则)

由于目前的分成计算逻辑（汇率折算、首单过滤、10% 提成）硬编码在 Dashboard 的全局路由 `dashboard/backend/routers/referrals.py` 中，无法直接被 Bot 和 Web 端复用。我们需要将该逻辑下沉至共享的业务服务层（Core Service）。

为了避免 N+1 查询、严格遵守依赖倒置原则，并最大化查询性能，采取以下优化方案：

### 2.1 数据库模型优化 (解决致命性能瓶颈)
**现状**：`src/database/models.py` 中 `Referral.inviter_id` 仅定义了外键，未建立索引，导致按邀请人查询时会触发全表扫描。
**调整**：
- 在 `Referral` 模型中，为 `inviter_id` 补充索引 (`index=True`)。这将把查询性能提升数个数量级。

### 2.2 抽离公共汇率服务与常量 (消除魔法数字)
**现状**：汇率获取方法 `get_exchange_rates()` 硬编码在 Dashboard，且 10% 的提成比例也是魔法数字。
**调整**：
- 新建/抽取至独立的工具模块 `src/utils/exchange_rates.py`，供 Dashboard 和 Core Service 共同调用。
- 在 `src/constants.py` 中统一定义 `COMMISSION_RATE = 0.10`，确保前后端及所有模块计算标准一致。

### 2.3 复用并扩展数据层查询 (SQL排序 & 延迟折算)
**现状**：`src/services/permission_service.py` 中已存在 `get_invitation_recharge_stats` 方法。
**调整**：
- **SQL 层排序**：在原 SQL 语句中额外查出 `Order.created_at`，并在末尾追加 `.order_by(Order.created_at.asc())`。
- **内存过滤首单**：遍历结果时，利用 `if tg_id not in recharged_invitees:` 精准截获绝对首单，避免复杂的 Python 内存排序。
- **批处理化折算**：在遍历时仅分别累加各币种（TON, RMB, Stars）的“首单总计额”。循环结束后，**仅调用一次**汇率公式进行汇总计算：`total_commission_usdt = (ton_first_total * ton_rate + rmb_first_total * rmb_rate + ...) * COMMISSION_RATE`。
- 在返回的字典中增加键值：`"commission_usdt": total_commission_usdt`。

### 2.4 Web 端 (BFF/API & Vue 前端) 改造
**后端 API 调整 (`src/web_api/schemas/auth_schema.py`)**：
- 在返回的 `InvitationRechargeStats` 结构体中，新增字段 `commission_usdt: float = 0.0`。

**前端展示调整 (`frontend/src/views/Profile.vue`)**：
- 在现有的“邀请与推广明细”卡片区域，新增一行高亮显示的数据项：**“预估邀请分成：$ XXX USDT”**（数据绑定 `authStore.user.invitation_recharge.commission_usdt`）。

### 2.5 Telegram Bot 端展示防客诉优化 (极简透传)
**展示适配器 (无需修改)**：
- DTO (`UserDashboardDTO`) 中的 `invitation_recharge` 自动透传新增的 `commission_usdt`。

**消息渲染调整 (`src/handlers/message_handler.py`)**：
- 在 `handle_personal_center` 函数中，为防止首单规则引发用户歧义，需使用极度严谨的文案标注边界。
- 在“累积贡献”下方追加一行文案：
  `  - 预估分成：*$ {dto.invitation_recharge.get('commission_usdt', 0.0):.2f} USDT* (仅计算受邀者历史首充金额的10%)`

---

## 3. 性能与缓存解耦策略

由于每次点击个人中心都会触发全量查询，考虑到补齐了 `inviter_id` 索引后单用户查询速度在毫秒级，建议采用**轻量级短 TTL 缓存**，**摒弃复杂的事件驱动失效**：
1. **整体短缓存**：对 `get_invitation_recharge_stats` 的结果字典在 Redis 中设置短 TTL（如 60-120 秒）缓存。
2. **架构解耦**：绝不要在支付成功回调（`fulfill_order`）中去查推荐关系清缓存。支付模块不应关心推荐业务，通过短缓存自动过期，既保护了数据库，又实现了模块的绝对解耦。

---

## 4. 落地步骤总结 (Todo List)

1. [ ] **数据库优化**：修改 `src/database/models.py`，为 `Referral.inviter_id` 添加 `index=True`。
2. [ ] **常量定义**：在 `src/constants.py` 中增加 `COMMISSION_RATE = 0.10`。
3. [ ] **抽离汇率服务**：将 `dashboard/backend/routers/stats.py` 中的 `get_exchange_rates` 抽离至 `src/utils/exchange_rates.py`，并更新 Dashboard 引用。
4. [ ] **底层查询扩展**：修改 `src/services/permission_service.py` 中的 `get_invitation_recharge_stats`，引入 `order_by(Order.created_at.asc())`，实现首单批处理汇总和 USDT 折算，返回 `commission_usdt`。
5. **Web端透传与展示**：
   - [ ] 修改 `src/web_api/schemas/auth_schema.py` 增加 `commission_usdt` 字段。
   - [ ] 修改 `frontend/src/views/Profile.vue`，渲染分成金额。
6. [ ] **Bot端展示防客诉**：修改 `src/handlers/message_handler.py`，直接通过 `dto.invitation_recharge` 渲染预估分成，并附带明确的“(仅计算受邀者历史首充金额的10%)”提示。
7. [ ] **(可选) 轻量缓存**：在查询处增加 60-120 秒的 Redis 缓存。