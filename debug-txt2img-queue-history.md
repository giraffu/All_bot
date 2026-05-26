# Debug Session: txt2img-queue-history [OPEN]

## 症状
- 文生图排队时显示“正在生成中... 0%”。
- 排队阶段不显示队列数量。
- 修仙笔记中看不到自己生成的文生图记录。

## 期望
- 排队阶段显示明确排队状态与队列位置，而不是误导性的 0% 生成进度。
- 文生图记录应进入修仙笔记并可正常查看。

## 当前假设
- H1: `stream` 修复后改用 `backend_task_id` 轮询，排队状态 payload 未再携带 `queue_pos`，导致前端失去排队信息。
- H2: 前端任务面板对 `pending` 状态默认渲染 `0%`，即使尚未进入生成阶段，也会显示为“生成中 0%”。
- H3: 修仙笔记的数据接口本身包含 `txt2img`，但前端过滤 tabs / task type 映射未纳入 `txt2img`，因此页面被筛掉。
- H4: 修仙笔记接口或历史响应构造对 `txt2img` 仍走旧 task type 枚举，导致返回后未被正确归类/显示。

## 下一步
- 检查浏览器网络里的 `/tasks/{id}/stream` payload。
- 检查前端任务浮球/结果面板对 `pending/queue_pos/progress` 的展示逻辑。
- 检查修仙笔记页面与历史接口的 task type 过滤、标签映射和列表构造。

## 证据
- 前端 `tasks.ts` 仅在 `payload.queue_pos != null` 时写入 `task.queuePos`，但 `TaskResultPreviewPanel.vue` 使用 `v-if="currentTask.queuePos"`，因此 `queuePos=0` 时被当成 falsy 隐藏。
- `TaskResultPreviewPanel.vue` 把 `pending` 和 `running` 合并成同一块展示，固定文案为“正在生成中... {{progress}}%”，而新建任务默认 `progress=0`，所以排队时会误显示 `0%` 生成进度。
- 测试环境 `web-api-test` 日志显示本次 `txt2img` 已成功写入 `history`：`INSERT INTO history ... type='txt2img' ... source='web'`，说明“闪回瓶”最近历史链路正常。
- 当前“修仙笔记”对应的是 `MyFavorites` 页面（收藏/点赞/应用/我的投稿），并非最近历史；其作品类型配置来自 `/gallery/config.allowed_types`。
- 当前后端 `DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS` 与 `ALLOWED_WEB_SUBMIT_TYPES` 均未包含 `txt2img`，前端 `History.vue` / `TaskDetailModal.vue` 里的可投稿类型白名单也未包含 `txt2img`，因此文生图详情会显示“暂不支持投稿”，也无法进入“我的投稿/类型筛选”体系。

## 已确认 / 已排除
- H1: 否。后端 SSE 仍会透传 `queue_pos`，问题在前端 `0` 值显示与 pending 文案。
- H2: 是。排队态被错误渲染成“生成中 0%”。
- H3: 部分成立。“修仙笔记”本就不是最近历史，但 `txt2img` 也确实未纳入该页支持的投稿/类型配置。
- H4: 否。`/users/history` 最近历史接口已包含 `txt2img` 持久化记录。
