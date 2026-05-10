# 任务排队阶段撤销功能实施方案

## 一、 需求分析
允许用户在 Bot 端和 Web 端，对处于**排队中（pending）**状态的任务进行主动撤销。撤销后，系统需要：
1. 取消后端 Redis 队列中的任务（避免算力浪费）。
2. 释放用户的并发锁。
3. 从 `active_tasks` 记录中移除该任务。
4. 全额退还预扣的灵石，并明确通知用户。

## 二、 核心依赖接口扩展
目前底层的 `src/api_client.py` 尚未向外暴露删除任务的方法，需先在内部通信层补充对中控撤销接口的调用。

**1. 修改文件：`src/api_client.py`**
补充 `cancel_task` 方法，调用中控 API 将任务从 DB2 队列中移除：
```python
    @async_retry(max_retries=3)
    async def cancel_task(self, task_id: str) -> dict:
        url = f"{API_BASE}/api/tasks/{task_id}"
        response = await self._request("DELETE", url)
        return response.json()
```
并在文件末尾导出：`cancel_task = api_client.cancel_task`。

**2. 修改文件：`src/core/task_core.py`**
增加用户主动撤销的核心业务逻辑 `cancel_user_task`。
**⚠️ 架构红线注意**：此函数只负责鉴权与向中控发送撤销信号。**严禁在此处执行退费和清理锁操作**，中控取消后会广播 `cancelled` 事件，底层的 `_monitor_task_progress` 与 `monitor_task_and_release_lock` 会触发 Saga 补偿机制，自动完成退费与清理，避免双重退费 Bug。

```python
async def cancel_user_task(task_id: str, user_id: int):
    """供用户主动调用的任务撤销逻辑"""
    from src.services.redis_client import redis_client
    tasks = await redis_client.get_active_tasks()
    if not tasks or task_id not in tasks:
        raise CoreDomainError("任务不存在或已脱离排队阶段")
    
    task = tasks[task_id]
    if task.get("user_id") != user_id:
        raise CoreDomainError("无权撤销该任务")

    # 仅调用中控移除排队，触发 cancelled 事件广播
    # (注意：实施时建议将 import httpx 移到文件顶部符合 PEP 8 规范，此处仅保留 api_client 按需导入防循环引用)
    from src.api_client import api_client
    try:
        await api_client.cancel_task(task_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise CoreDomainError("任务已在执行中，无法撤销")
        raise CoreDomainError(f"撤销请求失败: HTTP {e.response.status_code}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"中控取消任务网络异常: {e}")
        raise CoreDomainError("撤销请求失败，请稍后重试")
```

**3. 修改文件：`src/api_client.py` (修复致命 404 死循环 Bug)**
**⚠️ 致命 Bug 防范**：如果中控立刻删除了任务，底层的 HTTP 轮询 (`listen_for_progress`) 会收到 404 错误。原代码会将其作为普通网络异常捕获并进入无限重试，导致 `cancelled` 信号永远无法向上透传，并发锁死锁。
必须修改 `listen_for_progress` 的兜底轮询部分（以及初始 HTTP poll 处）：
```python
# 在 except Exception as inner_e: 块中补充：
except Exception as inner_e:
    if isinstance(inner_e, httpx.HTTPStatusError) and inner_e.response.status_code == 404:
        logger.warning(f"Task {task_id} deleted by central (404), treating as cancelled.")
        yield {"status": "cancelled", "error": "Task cancelled (404)"}
        raise RuntimeError("cancelled")
    logger.warning(f"Poll status failed for {task_id}: {inner_e}")
    await asyncio.sleep(POLL_INTERVAL)
```

---

## 三、 Bot 端实施方案

**1. 在刷新排队位置的消息处挂载按钮**
**涉及文件：`src/services/task_service.py` -> `_monitor_task_progress`**
系统中所有的生成任务都依赖 `_monitor_task_progress` 来循环监听并更新进度文本。
- 在函数内部构建一个内联键盘：
  ```python
  from telegram import InlineKeyboardMarkup, InlineKeyboardButton
  cancel_markup = InlineKeyboardMarkup([[
      InlineKeyboardButton("❌ 撤销任务", callback_data=f"cancel_task_{task_id}")
  ]])
  ```
- 修改其内部的 `update_status_message` 闭包函数：当文本提示包含“排队中”时挂载键盘，当进入“生成中”时移除键盘：
  ```python
  async def update_status_message(text, **kwargs):
      try:
          if "排队中" in text:
              kwargs["reply_markup"] = cancel_markup
          else:
              kwargs["reply_markup"] = None
          await robust_edit_text(status_msg, text, **kwargs)
          return True
      # ...
  ```

**2. 增加对应的 Callback 处理器**
**涉及文件：`src/handlers/callbacks/misc_callbacks.py` (或新建 `task_callbacks.py`)**
- 使用 `@register_callback("cancel_task_")` 装饰器注册处理器，替代直接写正则匹配 `CallbackQueryHandler` 的方式。
- **⚠️ 关键 Bug 防范 (user_id 类型)**：在 Handler 中解析出 `task_id` 后，**绝对不能**直接传入 `update.effective_user.id`。必须先通过 `get_or_create_user_by_telegram` 获取内部 `User.id`，否则会永远触发“无权撤销”错误。同时建议传入 `username` 以便同步更新。
- **⚠️ 细节优化 (异常拦截)**：不能仅做轻量提示，必须包含 `try...except` 块来捕获并提示 `CoreDomainError`（例如“任务已在执行中”）。
- 示例代码：
  ```python
  from src.core.user_core import get_or_create_user_by_telegram
  from src.core.task_core import cancel_user_task, CoreDomainError

  internal_user, _ = await get_or_create_user_by_telegram(
      update.effective_user.id,
      update.effective_user.username
  )
  try:
      await cancel_user_task(task_id, internal_user.id)
      await query.answer("撤销指令已发送，正在处理...", show_alert=False)
  except CoreDomainError as e:
      await query.answer(str(e), show_alert=True)
  except Exception as e:
      import logging
      logger = logging.getLogger(__name__)
      logger.error(f"撤销失败: {e}")
      await query.answer("撤销失败，请稍后重试", show_alert=True)
  ```

**3. 修改 `_monitor_task_progress` 主动抛出异常（关键 Bug 防范）**
**涉及文件：`src/services/task_service.py` -> `_monitor_task_progress`**
- 在内部判断任务状态为 `cancelled` 时，原本的逻辑是将 `final_info` 置空并返回，这会导致外层把它当做普通的生成超时或失败（提示 "Task generation failed or timed out."）。
- **必须**在此处主动抛出异常，让撤销信号穿透到外层，以便外层精准拦截并退费：
  ```python
  if status in ["error", "failed", "cancelled"]:
      if status == "cancelled":
          logger.warning(f"Task {task_id} was cancelled.")
          from src.core.task_core import CoreDomainError
          raise CoreDomainError("cancelled") # ！！！必须主动抛出，携带 cancelled 关键字
      else:
          error_msg = info.get("error", "Unknown error")
          logger.error(f"Task {task_id} failed: {error_msg}")
          raise RuntimeError(error_msg) # ⚠️ 必须保留 RuntimeError 抛出，否则会吞没底层错误导致重试逻辑错乱
  ```

**4. 优雅拦截异常并修改原消息（确保明确的退费通知）**
**涉及文件：`src/services/task_service.py` (包含所有调用 `_monitor_task_progress` 的入口，如 `process_generation_task`、`process_faceswap_task`、`process_music_generation_task` 等)**
- **⚠️ 致命 Bug 防范 (异常拦截顺序)**：由于 Python 的异常捕获链会优先捕获 `CoreDomainError`，如果把撤销逻辑写在最后的 `except Exception as e:` 中，代码永远不会执行到，导致**必定吞费**。
- 必须修改原有的 `except CoreDomainError as e:` 代码块，精准放行 "cancelled" 信号，并在其中处理退费和消息更新：
  ```python
        except CoreDomainError as e:
            # 拦截专门的撤销异常
            if str(e) == "cancelled":
                if task_submitted and actual_cost > 0: # 注意使用函数里的实际成本变量名(如 actual_cost 或 cost)
                    await asyncio.shield(
                        refund_credits(internal_user_id, actual_cost, "refund_user_cancel", username)
                    )
                # 优雅地把原来的 "⏳ 排队中..." 消息变成成功撤销的提示
                await robust_edit_text(status_msg, f"✅ 任务已撤销，预扣的 {actual_cost} 灵石已全额退回。")
                return None, None
                
            # 原有的普通业务错误提示
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
  ```
- **⚠️ 注意 (扣费变量名风险)**：全局排查 `task_service.py` 中依赖 `_monitor_task_progress` 的所有入口（如 `process_generation_task`、`process_ltx_video_task` 等）时，**务必注意上下文中使用的扣费变量名**。大部分方法使用的是 `actual_cost`，但如 `process_ltx_video_task` 等部分方法使用的是 `cost`。如果直接复制粘贴可能导致 `UnboundLocalError` 从而吞费。
- **⚠️ 致命陷阱 (消息对象变量名不统一)**：除了扣费变量名，**务必注意不同入口函数中“状态消息”的变量名是不一样的**！例如 `process_generation_task` 和 `process_face_video_task` 中使用的是 `status_msg`，但在 `process_ltx_video_task`、`_process_video_task_template`、`process_custom_video_task` 和 `process_i2i_pro_task` 中使用的是 **`msg`**！如果不加修改地直接粘贴 `await robust_edit_text(status_msg, ...)`，会立即触发 `NameError`，不仅无法退款还会导致消息永远卡死在“排队中”。修改时必须根据函数上下文进行替换。同时也要注意部分函数（如 `process_generation_task`）中判断退费的条件包含了 `deduct_quota` 等变量，修改时务必镜像原有的异常处理判断逻辑。

---

## 四、 Web 端实施方案

**1. 新增 Web API 端点**
**涉及文件：`src/web_api/routers/tasks.py`**
向前端暴露一个专用于用户撤销的接口：
```python
@router.delete("/cancel/{task_id}")
async def cancel_pending_task(task_id: str, current_user: User = Depends(get_current_user)):
    try:
        from src.core.task_core import cancel_user_task
        await cancel_user_task(task_id, current_user.id)
        return {"status": "success", "message": "任务已成功撤销，灵石已退回"}
    except CoreDomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**2. 前端数据流层 (Pinia Store)**
**涉及文件：`frontend/src/stores/tasks.ts`**
- Store 层：在 `tasksStore` 中添加 `cancelActiveTask` action，直接使用 `api.delete(\`/api/tasks/cancel/${taskId}\`)` 进行调用，不需要在 `frontend/src/api/index.ts` 中额外定义。如果请求成功，则直接在 `activeTasks` 列表中将该任务 `removeTask(taskId)`。
- **⚠️ 细节优化 (竞态条件防范)**：由于后端的退费是由 `monitor_task_and_release_lock` 异步处理的，中控接口返回成功时，实际的 Redis 扣款回退可能还需几十毫秒。因此在触发右上角的余额刷新前，必须增加一个延迟（如 `setTimeout(..., 1500)`），或直接依赖后端的 SSE 余额变更推送，避免用户看到旧余额产生疑虑。

**3. 前端 UI 层 (悬浮球交互)**
**涉及文件：`frontend/src/components/TaskProgress.vue`**
- 新增组件响应式状态：`const expandedTaskId = ref<string | null>(null)`。
- 修改圆球的点击事件 `@click="handleTaskClick(task)"`：
  ```javascript
  const handleTaskClick = (task: any) => {
    if (task.status === 'pending') {
        // 当为排队状态时，点击圆球切换展开/收起状态
        expandedTaskId.value = expandedTaskId.value === task.id ? null : task.id;
    } else if (task.status === 'success' && task.resultUrl) {
        // 原有成功后打开弹窗逻辑...
    }
  }
  ```
- 在模板的 `v-for` 循环内，增加一个绝对定位的气泡面板（当该任务是被展开的任务时显示）：
  ```html
  <transition name="fade-slide">
    <div v-if="expandedTaskId === task.id && task.status === 'pending'"
         class="absolute right-16 top-1/2 -translate-y-1/2 bg-slate-800 border border-slate-600 rounded-lg p-2 shadow-lg flex items-center whitespace-nowrap z-50">
      <span class="text-xs text-slate-300 mr-3">任务排队中</span>
      <a-button type="primary" danger size="small" @click.stop="doCancelTask(task.id)">
        撤销任务
      </a-button>
    </div>
  </transition>
  ```
- `doCancelTask` 调用 `tasksStore.cancelActiveTask(taskId)`，并使用 `message.success('✅ 任务已撤销，灵石已退回')` 明确提示用户。

## 五、 总结与一致性保障
本方案在 `task_core.py` 层面抽象了统一的 `cancel_user_task` 业务，确保 Bot 和 Web 双端撤销时的逻辑一致。
通过**利用底层已有的 Saga 补偿机制**，中控节点下发中止广播（`cancelled`）后：
1. Redis 队列记录清除。
2. Web端并发锁由后台监控 `monitor_task_and_release_lock` 自动释放；Bot端并发锁在抛出 `CoreDomainError("cancelled")` 后，会被原本外层的 `finally` 块（`release_concurrency_lock` 和 `TaskRegistry.remove_task`）稳妥清理。
3. 灵石精准退还并清晰地向用户展示退费金额与成功状态。
完美避免了双重退费、消息双重发送以及死锁或算力空转等问题。