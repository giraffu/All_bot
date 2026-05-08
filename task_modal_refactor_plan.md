# 悬浮球详情弹窗重构方案 (Task Modal Refactor Plan)

## 1. 背景与目标
当前逻辑中，用户在生成完成后点击右下角的悬浮球（Task Progress FAB）查看详情时，系统会通过 `router.push('/history')` 跳转至“闪回瓶”（历史记录）页面。这会打断用户在“练功房”连续创作的心流。
**目标**：实现点击悬浮球时，直接在当前页面弹出详情 Modal；关闭 Modal 后，用户依然停留在当前创作页面。

## 2. 架构方案：全局状态 + 共享 Modal 组件 (方案一)
采用全局挂载与状态接管的方式，实现高复用、低侵入的弹窗效果。

### 2.1 抽取独立组件
将目前位于 `src/views/History.vue` 中的大体量详情弹窗（`<a-modal class="history-detail-modal">` 及内部代码）抽离，封装为一个独立的共享组件 `src/components/TaskDetailModal.vue`。

### 2.2 全局挂载
将封装好的 `TaskDetailModal.vue` 引入并挂载到全局布局文件 `src/layouts/MainLayout.vue` 中。由于其位于 DOM 树的最外层，任何子路由页面均可无缝呼出该弹窗，无需在每个页面重复引入。

### 2.3 Pinia 状态接管
在全局状态管理（如 `src/stores/tasks.ts` 或新建专门的 store）中新增状态变量：
- `detailModalVisible` (boolean): 控制详情弹窗的显示与隐藏。
- `currentDetailRecord` (object | null): 当前需要展示的完整任务历史记录数据。

## 3. 数据层策略：静默刷新列表匹配 (策略 A)
悬浮球组件（TaskProgress）内部维护的任务对象仅包含基础信息（`task_id`, `resultUrl`, `status`），而详情 Modal 需要完整的 History 记录对象（含 `is_public`, `is_favorited`, `created_at` 等）以正确渲染底部的发布、收藏等交互按钮。

**具体实施路径：**
1. **拦截跳转**：修改悬浮球中完成状态的点击事件，**移除**原有的路由跳转逻辑。
2. **静默拉取**：点击触发时，前端（或 Store 的 Action）开启一个短暂的 Loading 状态，并静默调用获取历史记录列表的接口（`GET /api/users/history`，通常请求第一页即可覆盖最新生成的任务）。
3. **数据匹配**：从返回的历史列表中，通过数组的 `find` 方法匹配对应的 `task_id`，提取出完整的历史记录对象。
4. **状态赋值与弹出**：将提取到的完整对象赋值给 Pinia 的 `currentDetailRecord`，随后将 `detailModalVisible` 设为 `true`，唤起全局 Modal。
*(注：如果因网络延迟未能在第一页找到，可以考虑回退到一个包含基础信息的 Mock 记录对象，仅供展示图片/视频)*

## 4. 实施步骤清单 (Todo)
- [ ] **步骤一**：创建 `src/components/TaskDetailModal.vue` 并将 `History.vue` 中的 Modal 相关代码（UI及内部事件）迁移过去。
- [ ] **步骤二**：在 Pinia store (`src/stores/tasks.ts`) 中补充控制 Modal 的状态变量及静默拉取数据的 Action。
- [ ] **步骤三**：修改 `src/layouts/MainLayout.vue`，在合适位置挂载 `TaskDetailModal.vue` 组件，并绑定对应的 Pinia 状态。
- [ ] **步骤四**：修改 `src/components/TaskProgress.vue` 中的点击事件 `handleTaskClick`，替换 `router.push` 为调用 Pinia 的弹窗 Action。
- [ ] **步骤五**：清理 `src/views/History.vue` 中的冗余代码，并将其自身的列表项点击事件也改为触发全局弹窗状态，确保系统内详情弹窗的唯一性与统一性。
