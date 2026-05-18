# 两个问题的代码复核结论与修复建议

## 1. `handle_prompt` 空指针

### 现象
- 日志报错：`'NoneType' object has no attribute 'chat'`
- 触发链路：`tg-bot -> src.handlers.message_handler.handle_prompt`

### 实际代码落点
- `src/handlers/message_handler.py`
- `src/bot_test.py`（handler 注册入口）
- 关键逻辑：

```python
message = update.message or update.edited_message
if not message:
    return

...

if update.message.chat.type == "private":
    ...
    await robust_reply_text(update.message, fallback_msg, reply_markup=reply_markup)
```

### 原因
- `handle_prompt` 前半段已经承认消息来源可能是 `update.message` 或 `update.edited_message`。
- 但后面兜底分支又直接写死成 `update.message.chat.type` 和 `robust_reply_text(update.message, ...)`。
- 因此问题本质是 **“前半段用 `message` 变量，后半段又回到 `update.message`” 的不一致**。
- 需要注意的是：`bot_test.py` 第 321 行通过 `MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt)` 注册 handler，而 `filters.TEXT` 在 python-telegram-bot 中会匹配 `update.effective_message`；对于已编辑的消息，`effective_message` 返回 `update.edited_message`。因此 `edited_message` **已被 handler 接住**，当前路径可达，风险已确认。
- `handle_prompt` 第 668 行明确写了 `message = update.message or update.edited_message`，说明 edited-message 已在设计范围内。
- 随后第 678-680 行会做路由分发，命中文案映射时会调用 `prompt_routes[route_key](update, context, text)`，而大量 `@prompt_route` 处理器（如 `handle_photo_edit_menu`、`handle_checkin`、`handle_recharge_menu` 等）直接使用 `update.message` 回复，**这意味着 edited text 不仅在 fallback 里会炸，命中菜单文案映射时也会在更早的分发阶段炸**。
- 在这种路径下，`message` 变量可能持有 `edited_message`，而 `update.message` 为 `None`，此时访问 `update.message.chat.type` 或在 `@prompt_route` 处理器中访问 `update.message` 都会触发 `AttributeError: 'NoneType' object has no attribute 'chat'` 或同类空指针错误。

### 修复方案
1. 统一只使用前面已经拿到的 `message` 变量，不再回退到 `update.message`。
2. 私聊判断改为基于 `message.chat` 或 `update.effective_chat`，不要混用不同来源。
3. 回复对象也统一改成 `message`，避免前半段和后半段对象不一致。
4. 所有 `@prompt_route` 处理器也需同步修正，将 `update.message` 替换为 `update.effective_message` 或通过 `update.message or update.edited_message` 获取的 `message` 变量。

### 建议改法

```python
message = update.message or update.edited_message
if not message:
    return

text = message.text.strip() if message.text else ""
if not text:
    return

chat = message.chat or update.effective_chat
if chat and chat.type == "private":
    await robust_reply_text(message, fallback_msg, reply_markup=reply_markup)
```

### 回归检查
- 普通私聊文本输入仍能正常兜底回复。
- edited-message 进入 `handle_prompt` 后，fallback 不再触发空指针。
- edited-message 命中 `@prompt_route` 路由分发时，各处理器不再空指针。
- 非 `message` 类型的更新不会再误入 `update.message.chat`。

## 2. `custom_video` 这条“文件被提前删掉”的结论与当前代码不一致

### 现象
- 日志报错：`本地输入文件不存在，无法继续派发任务`
- 触发链路：`tg-bot -> src.core.task_core`

### 实际代码落点
- `src/handlers/fsm/custom_video_fsm.py`
- `src/services/task_service.py`
- `src/core/task_core.py`
- `src/constants.py`

### 关键代码关系

`custom_video_fsm.receive_prompt()` 在提交后台任务前，先把 `image_path` 从 FSM 状态里取出来：

```python
image_path = fsm_data.pop("image_path", None)
if not image_path:
    return ConversationHandler.END
```

随后才提交后台任务并清理上下文：

```python
create_background_task(
    context,
    TaskService.process_custom_video_task(
        update=update,
        context=context,
        prompt=prompt,
        image_path=image_path,
        cleanup=True,
    ),
)

_cleanup_context(context, user_id)
```

`_cleanup_context()` 的确会尝试删除 `custom_video_data.image_path`：

```python
pending_files = context.user_data.pop("custom_video_data", {})
path = pending_files.get("image_path")
if path and os.path.exists(path):
    os.remove(path)
```

但这里有个关键前提：

- `image_path` 在提交前已经被 `fsm_data.pop("image_path", None)` 拿走了。
- 所以提交后的 `_cleanup_context()` 再去 `pop("custom_video_data")` 时，按当前 `receive_prompt()` 的执行顺序，已经拿不到这个路径。
- 也就是说，按当前实现，**不能据此认定是 `_cleanup_context()` 抢先删掉了后台任务要用的文件**。

后台任务真正开始处理本地路径时，`task_core` 又要求文件还在：

```python
if not os.path.exists(path):
    raise CoreDomainError(f"本地输入文件不存在，无法继续派发任务: {path}")
```

另外，`TaskService.process_custom_video_task(..., cleanup=True)` 虽然会在 `finally` 里调用清理：

```python
if cleanup and image_path:
    TaskService._cleanup_files([image_path])
```

但 `TaskService._cleanup_files()` 只删除 `TMP_DIR` 下的文件，而 `TMP_DIR` 实际是 `./tg_tmp`：

```python
TMP_DIR = os.path.abspath("./tg_tmp")
```

而 `custom_video_fsm` 下载文件用的是 `/tmp/bot_fsm_tmp/...`。因此当前这条后台清理逻辑**并不会清理这类 FSM 临时文件**。

### 原因
- 现有代码**无法支持**“FSM 提交后立刻删文件，导致后台读取失败”这个结论。
- 当前能够确认的是两个事实：
1. `本地输入文件不存在` 这个报错，**不能仅凭现有链路**归因到 `_cleanup_context()` 提前删除，真实删除来源需要继续排查。
2. FSM 下载目录是 `/tmp/bot_fsm_tmp`，而 `TaskService` 只清理 `./tg_tmp`，这说明当前实现至少存在**临时文件清理缺失 / 目录约定不一致**的问题。

### 待验证假设
- `create_background_task` 是异步的，理论上确实存在“FSM 返回后，后台任务稍后才读取文件”的时间窗口。
- 如果还有其他代码、容器清理机制、宿主机清理策略或外部回收逻辑删除了 `/tmp/bot_fsm_tmp` 下文件，也可能触发同样报错。
- 但就当前仓库代码而言，**还没有直接证据**证明 `/tmp/bot_fsm_tmp` 确实会被系统 / Docker / 其他代码主动清理。
- 因此“真正根因就是容器 `/tmp` 清理机制”这句话证据不足，最多只能作为**待排查假设**，不能写成已确认事实。

### 修复方案
1. 先不要按“提前删文件”方向修复 `custom_video_fsm`，因为当前代码证据不足。
2. 文档结论应先收敛到已证实事实：`_cleanup_context()` 不是当前证据下的直接删除者，且 `TMP_DIR` 与 `/tmp/bot_fsm_tmp` 的清理职责不一致。
3. 单独修正临时文件生命周期：统一 FSM 下载目录与 `TaskService._cleanup_files()` 的清理范围。
4. 真实删除来源另行排查；即使后续发现还有别的因素，统一目录和清理职责本身也是合理收敛。

### 推荐落地方式
- 先把“定位问题”和“收敛清理”拆开做，不要混成一个修复：

```python
# 第一步：排查真实删除来源，不先改 _cleanup_context 的职责判断
# 第二步：统一临时文件目录，例如全部收敛到 TMP_DIR
```

- 如果要让 `TaskService` 接管成功提交后的文件清理，推荐把 FSM 下载目录统一到 `TMP_DIR`：

```python
os.makedirs(TMP_DIR, exist_ok=True)
local_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}_custom_vid.png")
```

- 或者反过来，让 `_cleanup_files()` 兼容 `/tmp/bot_fsm_tmp`；但无论选哪条路，都必须统一所有相关 FSM 的目录约定，避免有的入口能清、有的入口不能清。

### 为什么这样改更稳
- 这和当前代码事实一致，不会把问题误判成 `_cleanup_context()` 抢删。
- 能把“真实报错归因”与“临时文件目录不统一”两个问题拆开处理。
- 即使最后证明还有别的删除来源，统一目录和清理职责本身也是合理收敛。

### 顺手建议
- 同类视频 FSM 如 `ltx_video_fsm.py`、`video_lora_fsm.py`、`quick_video_fsm.py`、`face_video_fsm.py` 也有"先 `pop("image_path")`，再提后台任务，再 `_cleanup_context()`"的相似结构。
- 它们和 `custom_video` 一样，**不能直接下结论**说存在"FSM 抢先删文件"的竞争条件。
- 另外，仓库里不止视频 FSM 在使用 `/tmp/bot_fsm_tmp`；`quick_image_fsm.py`、`edit_image_fsm.py`、`faceswap_fsm.py` 也使用了同一临时目录。后续若统一临时目录或清理策略，建议一并检查。

### 回归检查
- `handle_prompt` 相关文档结论已与当前代码范围保持一致，已明确 `edited_message` 风险属于当前可达路径下的已确认问题。
- `custom_video` 相关文档结论已与当前代码一致，不再把根因误记为 `_cleanup_context()` 提前删文件，也不再把 `/tmp` 外部清理写成已确认事实。
- 若后续统一临时目录，应验证成功、失败、取消三条路径都能按预期清理文件。
