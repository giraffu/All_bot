# 两个问题的代码复核结论与修复建议

## 说明

- 本文结论分为两类证据：
  - **代码直接可证实**：可由当前仓库代码直接复核。
  - **日志直接可证实**：可由当前仓库保留的原始日志或历史分析报告直接复核。
- 对于“谁删了文件”“是否一定由 Telegram 重试触发”这类问题，若当前证据链未闭环，本文统一按“候选方向”处理，不写死成根因。

## 1. `handle_prompt` 空指针

### 现象
- 日志报错：`'NoneType' object has no attribute 'chat'`
- 触发链路：`tg-bot -> src.handlers.message_handler.handle_prompt`

### 当前可直接复核的证据

- 原始日志可直接看到 traceback 落在 `src/handlers/message_handler.py` 的 fallback 分支。
- 当前仓库代码可直接看到：前半段使用 `message = update.message or update.edited_message`，后半段却回到 `update.message.chat.type` 与 `robust_reply_text(update.message, ...)`。

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
- 因此问题本质是 **"前半段用 `message` 变量，后半段又回到 `update.message`" 的不一致**。
- 需要注意的是：`bot_test.py` 通过 `MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt)` 注册 handler，而 `filters.TEXT` 在 python-telegram-bot 中会基于 `update.effective_message` 做匹配；对已编辑文本，`effective_message` 会落到 `update.edited_message`。因此 `edited_message` **可进入当前 handler**，这不是纯理论路径。
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

## 2. `custom_video` / `edit_image` 文件不存在

### 现象
- 日志报错：`本地输入文件不存在，无法继续派发任务: /tmp/bot_fsm_tmp/xxx_ref.png`
- 触发链路：`tg-bot -> src.core.task_core`

### 当前可直接复核的证据

- 当前仓库保留的原始 `bot.log` 中，存在“先扣费，再 `Saga Execute Failed: 本地输入文件不存在...`，最后 `refund_saga_failed`”的完整样例。
- 当前仓库代码中，`process_and_submit_task()` 的执行顺序确实是先 `check_and_deduct_credits()`，再 `_process_input_path()` 校验并上传本地文件。
- 当前仓库代码中，多个 FSM 在提交前已存在基础判空保护，因此不能直接把问题归因成“所有 FSM 都没有防重复/防空保护”。

### 实际代码落点
- `src/handlers/fsm/custom_video_fsm.py`（`receive_prompt` 函数）
- `src/handlers/fsm/edit_image_fsm.py`（`receive_prompt` 函数）
- `src/core/task_core.py`（`_process_input_path` 函数）
- `src/core/task_dispatcher.py`（`get_file_paths_to_upload` 方法）

### 日志分析：已证实的事实

这里区分两类来源：

- **当前仓库保留的原始日志，可直接复核的样例**：如 `fc48d20b-196e-4e5e-a3fd-f2245a130919`
- **历史分析报告中引用过的样例**：如 `518ab760-6224-48dd-bd92-5e38d095edd7`

下面先写“当前仓库可直接复核”的事实：

1. 失败任务确实在 `task_core._process_input_path()` 报错，报错信息为：

```text
本地输入文件不存在，无法继续派发任务: /tmp/bot_fsm_tmp/xxx_ref.png
```

2. 该路径是 **Bot 容器内本地临时文件路径**，不是 MinIO 对象路径。
3. `process_and_submit_task()` 当前执行顺序是：

```text
先 check_and_deduct_credits()
后 _process_input_path() -> os.path.exists(path) 校验 -> 上传 MinIO
```

4. 当前失败链路不是“扣费后直接吞掉”：
   - 先预扣
   - 随后命中 `Saga Execute Failed`
   - 最后进入 `refund_saga_failed` 自动退款

补充说明：

- 若后续需要引用 `518ab760-6224-48dd-bd92-5e38d095edd7`，应明确标注它来自历史日志分析报告，而不是当前保留的原始 `bot.log` 样例。

### 当前不能直接下结论的部分

以下判断 **目前只能算推测，不能当作已证实根因**：

- “消息一定绕过了正常 FSM 流程”
- “一定是 Telegram 重试导致重复提交”
- “一定是状态过期导致 `fsm_data` 为空”

原因如下：

1. 单个失败 TraceID 主要覆盖 `process_and_submit_task()` 及其后续日志，不天然覆盖更早的 FSM 下载阶段。
2. “同一个 Trace 里没有看到文件下载 / Saved input to MinIO” 只能说明 **当前 Trace 上缺少前序日志链**，不能直接推出“前序逻辑根本没执行”。
3. 现有多个 FSM 在提交前其实已经有基础防御性检查，说明问题并不等同于“完全没有判空保护”。
4. 当前原始日志虽然能证明“文件在派发阶段已不存在”，但**不能单靠这一点推出究竟是谁删掉了文件**。

### 代码复核结论

#### 结论 1：多个 FSM 已有基础防御性检查

以下流程在提交前都已有判空保护：

- `custom_video_fsm.py`：`image_path = fsm_data.pop("image_path", None)`，为空则直接 `return ConversationHandler.END`
- `ltx_video_fsm.py`：同上
- `video_lora_fsm.py`：同上
- `faceswap_fsm.py`：`face_path/body_path` 任一为空则直接 `return ConversationHandler.END`
- `edit_image_fsm.py`：`images = list(fsm_data["images"])` 后若为空则直接 `return ConversationHandler.END`

因此，原问题不能简单归因于“FSM 完全缺少提交前检查”。

#### 结论 2：`edit_image` 的当前处理更接近幂等兜底，而不是明显缺陷

`edit_image_fsm.py` 的处理顺序是：

```python
images = list(fsm_data["images"])
if not images:
    return ConversationHandler.END

fsm_data["images"] = []
```

这意味着在并发或重复投递场景下：

- 第一条请求可能拿到真实图片列表并继续提交
- 第二条请求可能拿到空列表并直接结束

这属于合理的“只放行一次”语义，不应再把它写成“空列表也可能继续提交后台任务”的代码缺陷。

#### 结论 3：真正已确认的问题在于“扣费早于文件存在性校验”

当前 `process_and_submit_task()` 会先扣费，再校验本地文件，再上传 MinIO：

```python
if deduct_quota:
    success, err = await check_and_deduct_credits(...)

paths_to_upload = strategy.get_file_paths_to_upload(inputs)
for path in paths_to_upload:
    processed_img = await _process_input_path(user_logger, path)
```

而 `_process_input_path()` 对本地绝对路径会执行：

```python
if not os.path.exists(path):
    raise CoreDomainError(f"本地输入文件不存在，无法继续派发任务: {path}")
```

这会导致：

- 用户先被预扣
- 随后因为文件不存在而失败
- 最后再由 saga 补偿退款

所以当前最准确的表述应是：

- **存在“扣后退”的失败体验与无效流程消耗**
- **当前日志未证明存在“最终余额损失”**
- **当前日志已经足以证明问题落点在“扣费后、派发前的本地文件校验阶段”**

#### 结论 4：临时目录不统一是独立问题，值得修，但不是本次根因的直接证据

当前多个 FSM 把上传内容写入 `/tmp/bot_fsm_tmp`，而 `TaskService._cleanup_files()` 只清理 `TMP_DIR(./tg_tmp)` 前缀的文件。

这说明：

- 目录约定不一致
- 清理职责不一致
- 长期看会产生临时文件堆积

但这只能说明“清理体系不统一”，**不能单凭这一点直接解释为什么某次任务在提交前文件已经不存在**。

### 更严谨的根因表述

截至当前代码与日志证据，问题 2 的根因应表述为：

> 在 `process_and_submit_task()` 执行到 `_process_input_path()` 时，输入中的本地绝对路径已经失效；直接报错点已确认，但“是谁、在什么时候、通过什么路径让该文件消失”尚未由现有日志闭环证实。

当前可保留为候选方向、但不能写死为结论的包括：

- Telegram webhook 重复投递
- 并发请求导致会话状态只允许一次提交
- 会话/上下文异常导致 FSM 数据与本地文件状态不一致
- 外部清理或其他路径提前删除了临时文件

### 修复方案

#### 方案 A：前置文件校验，减少“扣后退”

这是最值得优先落地的改动。

```python
# 在扣费前先获取待上传输入
paths_to_upload = strategy.get_file_paths_to_upload(inputs)

# 复用与 _process_input_path 一致的“本地文件识别”语义做预校验
for path in paths_to_upload:
    if not path:
        continue

    is_local_file = os.path.isabs(path) or os.path.exists(path)
    if is_local_file and not os.path.exists(path):
        raise CoreDomainError(f"本地输入文件不存在，无法继续派发任务: {path}")

# 文件校验通过后再扣费
if deduct_quota:
    success, err = await check_and_deduct_credits(...)
```

注意：

- 这里只应校验“按当前主链规则会被视为本地文件”的路径
- 不要新写一套与 `_process_input_path()` 语义不一致的判定逻辑
- 更稳妥的实现方式是：抽共享 helper，或让预校验与 `_process_input_path()` 复用同一套本地路径识别规则

#### 方案 B：保留 FSM 判空保护，但补充更友好的日志与用户提示

当前多数 FSM 已有判空保护，建议做的是“增强可观测性”，而不是重复发明一套错误的数据结构兜底。

例如：

```python
image_path = fsm_data.pop("image_path", None)
if not image_path:
    logger.warning(f"user={user_id} image_path missing before submit")
    await robust_reply_text(message, "⚠️ 任务状态已过期，请重新发送图片和提示词。")
    return ConversationHandler.END
```

对于 `edit_image`：

```python
images = list(fsm_data["images"])
if not images:
    logger.warning(f"user={user_id} images empty before submit")
    await robust_reply_text(message, "⚠️ 任务已提交或状态已失效，请重新发送图片。")
    return ConversationHandler.END
```

#### 方案 C：消息幂等保护（增强项）

如果后续日志继续显示同一用户短时间内重复进入同一提交流程，可以增加按 `user_id + message_id` 的幂等保护。

但应注意：

- 这属于“增强排查和保护”
- 不能在当前证据不足时，把它写成“唯一根因修复”

#### 方案 D：统一临时文件目录（补充优化）

建议把 FSM 下载目录统一到 `TMP_DIR`，并让 `TaskService._cleanup_files()` 与 FSM 使用同一目录约定。

这能解决：

- 清理职责不一致
- 临时文件长期堆积
- 后续排障时路径语义不统一

但它应被表述为“配套优化”，而不是本次问题的唯一根因修复。

### 推荐落地顺序

1. **优先实施**：方案 A，前置本地文件存在性校验，减少“扣后退”
2. **同步实施**：方案 B，为现有 FSM 判空分支补充 warning 日志和友好提示
3. **补充优化**：方案 D，统一 `/tmp/bot_fsm_tmp` 与 `TMP_DIR`
4. **视后续日志决定**：方案 C，如重复投递特征持续出现，再做幂等保护

### 顺手建议
- 不要再把 `custom_video`、`ltx_video`、`video_lora` 等 `image_path` 型 FSM，和 `edit_image` 这种 `images` 列表型 FSM 混写成同一段伪代码
- 如果需要写通用兜底逻辑，必须显式区分 `images: list[str]` 与 `image_path: str`，不能对字符串路径直接 `list(image_path)`
- 所有使用 `/tmp/bot_fsm_tmp` 的 FSM 都建议统一检查一遍：`ltx_video_fsm.py`、`video_lora_fsm.py`、`quick_video_fsm.py`、`quick_image_fsm.py`、`faceswap_fsm.py`、`face_video_fsm.py`

### 回归检查
- 正常提交流程不受影响
- 本地文件提前失效时，应在扣费前直接失败，避免进入“扣后退”
- 重复提交或状态失效场景下，用户应收到明确提示，而不是静默 `END`
- saga 失败补偿链路仍能正常工作
- 临时文件目录统一后，FSM 与 `TaskService._cleanup_files()` 的清理职责保持一致
- 若文档继续引用具体 TraceID，应区分“当前原始日志可直接复核”与“历史分析报告引用”两类来源
