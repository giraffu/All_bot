# 临时灵石字段及相关接口变更文档

## 1. 数据库模型变更
**目标表**: `users`

**新增字段**:
- `temporary_ingot`: 整数类型，默认值为 `0`。

**说明**: 该字段用于记录用户每日的临时灵石数量，每日 00:00 自动清零。临时灵石可以和普通灵石一样用于抵扣积分，但仅限当日有效。

## 2. API 接口变更

### 2.1 `/api/stats` (全局统计数据)
**响应字段变更**:
- **新增**: `total_temporary_ingot` (全站流通的临时灵石总数)
- **新增**: `total_active_temporary_ingot` (活跃用户流通的临时灵石总数)

**响应示例**:
```json
{
  "total_users": 1000,
  "total_generations": 5000,
  "total_credits": 20000,
  "total_temporary_ingot": 1500,
  "total_active_credits": 18000,
  "total_active_temporary_ingot": 1200,
  ...
}
```

### 2.2 `/api/users` (用户列表)
**响应字段变更**:
- **新增**: 在返回的每个用户对象中增加 `temporary_ingot` 字段。

**响应示例**:
```json
[
  {
    "id": 123456789,
    "username": "test_user",
    "credits": 50,
    "temporary_ingot": 10,
    "user_group": "练气期",
    ...
  }
]
```

## 3. 定时任务日志样例
定时任务每天凌晨 00:00 自动执行，清空所有用户的临时灵石。

**执行日志样例**:
```log
[2024-05-20 00:00:00,001] [INFO] [bot.jobs] 🕒 Running daily temporary credits and ingots clearance...
[2024-05-20 00:00:00,045] [INFO] [src.quota] Cleared temporary credits for 150 users.
[2024-05-20 00:00:00,089] [INFO] [src.quota] Cleared temporary ingots for 120 users.
[2024-05-20 00:00:00,090] [INFO] [bot.jobs] ✅ Daily temporary credits and ingots clearance completed.
```
