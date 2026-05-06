# 社区广场点赞/点踩 Toggle 机制实现方案

这是一个为了支持用户在 Web 端和 Telegram 端“再次点击取消”点赞/点踩操作的全栈实现方案。

## 1. 后端核心逻辑改造 (`src/core/gallery_core.py`)
核心层负责处理点赞状态的流转。我们需要修改 `toggle_like` 函数，将“重复操作”定义为“取消操作”。

* **状态判定**：当查询到用户对该帖子已存在 `UserInteraction` 记录，且 `inter.action_type == action`（即当前操作与历史操作一致）时，不再抛出异常，而是执行取消操作。
* **原子递减与删除**：
  * 执行 `DELETE` 语句删除该条 `UserInteraction` 记录。
  * **【核心优化点：防并发多扣漏洞】**：在实现“取消点赞”时，极快双击可能导致并发漏洞。必须通过判断 `DELETE` 语句的 `rowcount > 0` 来决定是否执行递减。只有真正删除了记录的那次请求，才使用 `sqlalchemy.update` 对 `GalleryPost` 的 `likes_count` 或 `dislikes_count` 进行**原子递减**（`- 1`），避免并发下点赞数被扣到负数。
  * 确保底层的原子 `DELETE` 和 `UPDATE` 在同一个 `session.commit()` 中执行，保证事务一致性。
* **返回状态透传**：调整返回值，增加一个 `action_state` 字段（分为 `added` 新增、`switched` 赞踩切换、`canceled` 取消），并一并返回原子更新后的最新 `likes_count` 和 `dislikes_count`。

## 2. API 路由层透传保障 (Pydantic Model)
* **【优化点：无需修改 Schema】**：经排查 `src/web_api/routers/gallery.py` 中的 `interact_with_post` 路由，发现该接口并未限制 `response_model`，而是直接返回 `{"status": "success", "data": result}`。因此，只要在 `gallery_core.py` 中返回了 `action_state`，前端就能无损接收，无需改动现有的 Pydantic 模型。
* **【补充细节：动态返回文案】**：接口返回的 `message` 需要动态化。解析 `result["action_state"]`，如果是 `canceled`，则返回 `"取消成功"` 或 `"已取消点踩"`，以确保前后端语义的严谨一致。

## 3. Web 前端改造 (`frontend/src/views/Gallery.vue` & `MyFavorites.vue`)
目前前端的 `handleInteract` 方法是“乐观预测”机制：只要接口不报错，就盲目执行 `count++` 和 `has_liked = true`。这需要改为**基于后端响应的状态同步**。

* **【核心优化点：移除硬拦截与状态反转】**：
  * 必须删掉 `handleInteract` 函数开头写死的拦截逻辑（如 `if ((action === 'like' && post.has_liked) || ...) return`），否则前端在触发“取消操作”前就会被直接拦截。
* **接收状态**：解析接口返回的 `res.data.data.action_state`。
* **精确更新 UI**：
  * 如果是 `added`：对应的 `has_xxx` 设为 `true`。
  * 如果是 `canceled`：对应的 `has_xxx` 设为 `false`，并使用 `message.success("已取消点赞/点踩")` 给出提示。
  * 如果是 `switched`：反转双端的 `has_xxx` 状态（例如由赞切换到踩时，设 `has_liked = false` 且 `has_disliked = true`）。
* **计数同步**：直接使用后端返回的 `likes_count` 和 `dislikes_count` 覆盖前端的响应式对象，确保并发下前端显示的数字始终与数据库真实值对齐。

## 4. Telegram Bot 端兼容性评估 (`src/handlers/callbacks/gallery_callbacks.py`)
由于 `gallery_core.py` 是双端共享的核心业务逻辑，这一改动会自动波及 Telegram Bot。

* **当前机制**：TG 端用户点击点赞后，底层原先会抛出 `DuplicateInteractionError` 拦截。且回调中会将按钮的 `callback_data` 替换为 `noop`，导致用户目前在不刷新画廊的情况下无法进行“二次点击”。
* **兼容处理与【核心优化点：动态重绘双按钮】**：
  * 彻底废弃 `noop`，利用回调数据拆分出的参数，永远重新组装完整的 `callback_data`（包含 `sort_type`, `category`, `page` 等上下文）。
  * **【补充细节：动态 Toast 弹窗】**：在调用 `safe_answer_query` 时，提示语应根据 `action_state` 动态生成。如果是取消操作，提示 `"已取消点赞"` 或 `"已取消点踩"`，避免给用户造成困惑。
  * **【补充细节：简化重绘逻辑】**：在 TG 的 `gallery_like_dislike_callback` 中接收新的 `action_state` 后，**不需要**去遍历匹配旧按钮的状态。可以直接根据 `action_state` 的结果（`added`, `switched`, `canceled`）推导出两个按钮的最终文本和状态，直接重新生成当前行的“赞”和“踩”两个按钮进行替换，这样代码更清晰且不易出错。