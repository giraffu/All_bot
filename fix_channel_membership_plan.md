# 频道入宗识别与邀请奖励修复方案

## 一、 问题现象与根源分析

目前系统中存在“新用户已加入频道，但仍被识别为凡人，无法签到且邀请人未获得 10 灵石奖励”的问题。经过链路排查，该问题由以下三个机制的缺失导致：

### 1. 签到功能 (Check-in) 缺乏实时状态同步
用户在加入频道后，最常见的首个动作就是点击“每日签到”。
当前 `handle_checkin` 函数在执行时，仅仅检查了用户是否在“避难所群组”，随后直接读取了数据库中缓存的 `is_channel_member` 状态（默认为 `False`）。**它没有主动调用 Telegram API 去核实用户是否已经在官方频道内**。这导致系统直接判定用户为“凡人”并拒绝签到。

### 2. 文本菜单交互 (Prompt) 缺乏实时状态同步
当用户点击菜单按钮（如“图片编辑”、“个人中心”等），请求会路由到 `handle_prompt`。
虽然该函数调用了 `permission_service.check_access`，但**并未传入实时的 `is_member` 参数**。根据底层的设计，如果不传入实时的频道状态，系统只会降级使用数据库的旧状态，导致状态一直无法刷新。

### 3. Dashboard 后台手动修改未联动业务逻辑
在 Dashboard 界面手动将用户的“已入宗门”状态改为“是”时，对应的 API (`update_user_channel_member`) 仅仅是简单地执行了 `UPDATE users SET is_channel_member = True`。
它**漏掉了两项关键的业务逻辑**：
- 没有调用 `refresh_user_group` 重新计算用户的修为（从凡人升级为练气期）。
- 没有调用 `check_channel_reward` 为邀请人补发 10 灵石奖励。

---

## 二、 修复方案与代码变更计划

为了彻底解决上述问题，我们需要在三个关键位置补充缺失的状态同步和业务联动代码。

### 修复点 1：签到动作强制同步频道状态
**文件**: `src/handlers/message_handler.py` -> `handle_checkin`
**修改内容**: 
在执行签到逻辑 `perform_checkin` 之前，主动向 Telegram 服务器查询最新的频道状态，并同步到数据库。
```python
# 新增逻辑：在签到前强制获取最新频道状态并同步
is_member = await get_user_channel_status(context.bot, update.effective_user.id)
if is_member is not None:
    inviter_id_reward = await permission_service.sync_channel_status(
        user.id, user.username, user.full_name, is_member
    )
    if inviter_id_reward:
        create_background_task(context, notify_inviter_reward(context.bot, inviter_id_reward, user.full_name))
```

### 修复点 2：普通菜单点击同步频道状态
**文件**: `src/handlers/message_handler.py` -> `handle_prompt`
**修改内容**: 
在鉴权时，补充获取实时的 `is_member` 参数，确保用户点击任何菜单都能触发状态刷新和奖励下发。
```python
# 修改前：
await permission_service.check_access(user.id, user.username, user.full_name)

# 修改后：
is_member = await get_user_channel_status(context.bot, user.id)
inviter_id_reward = await permission_service.check_access(user.id, user.username, user.full_name, is_member)
if inviter_id_reward:
    create_background_task(context, notify_inviter_reward(context.bot, inviter_id_reward, user.full_name))
```

### 修复点 3：Dashboard 补齐业务联动
**文件**: `dashboard/backend/routers/users.py` -> `update_user_channel_member`
**修改内容**: 
在管理员将状态改为 `True` 时，主动触发重新计算修为并尝试发放邀请奖励。
```python
old_status = user.is_channel_member
user.is_channel_member = request.is_channel_member
await db.commit()

# 新增逻辑：如果是从 False 改为 True，则联动触发奖励和修为刷新
if request.is_channel_member and not old_status:
    from src.services.permission_service import permission_service
    # 尝试发放邀请奖励
    await permission_service.check_channel_reward(
        tg_id=user.telegram_id or user.id, 
        username=user.username, 
        full_name=user.full_name, 
        internal_user_id=user.id
    )
    # 刷新修为境界（凡人 -> 练气期）
    await permission_service.refresh_user_group(user.id, is_member=True)
```

---

## 三、 预期效果

执行上述修改后：
1. 新用户只要加入了频道，无论是点击**“每日签到”**，还是点击**其他任意菜单按钮**，系统都会瞬间捕获到其已入群的状态。
2. 用户的境界会立刻从“凡人”突破为“练气期”，允许正常签到。
3. 邀请人会在同一时刻收到 10 灵石的入宗奖励通知。
4. 即使 Telegram API 偶尔延迟，管理员在 Dashboard 手动勾选“是”时，也能完美触发相同的升级和奖励逻辑，不会再出现“改了状态但还是没发奖励”的数据不一致问题。