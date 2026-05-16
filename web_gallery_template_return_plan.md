# Web 端模板应用工作台执行方案（可落地修订稿）

## 1. 目标

将当前 `市集详情 -> 一键应用 -> 跳转生成页` 改为 `市集详情 -> 一键应用 -> 当前页弹出工作台`，并把实现约束写成可直接开发的接口与状态机，避免落地时再靠默认行为或临场判断补洞。

首期必须达成：
- 不切路由。
- 不丢 `Gallery.vue` 当前筛选、排序、已加载列表和滚动位置。
- 用户可在当前页完成模板回填、上传和任务提交。
- 同类模板连续打开时不串状态。
- 上传中关闭工作台时不产生脏回写。
- 普通路由切换、浏览器回退、接口拦截器跳转都不能绕过关闭协议。
- 工作台所有关闭入口都必须走统一 cleanup 链路。

首期明确不做：
- 不做“跳转生成页后再返回”的恢复方案。
- 不把现有整页组件直接塞进弹层。
- 不首期同时改 `MyFavorites.vue` / `MySubmissionsPanel.vue` 的入口行为。
- 不移除旧页面基于 `route.query + sessionStorage` 的兼容链路。
- 不首期重写旧页面正在使用的 `useUpload.ts` 公共接口。

## 2. 已核实现状

当前代码基线如下：
- `Gallery.vue`、`MyFavorites.vue`、`MySubmissionsPanel.vue` 都是先请求 `apply-context`，再写入 `sessionStorage.galleryApplyContext`，最后 `router.push()` 到目标生成页。
- 独立生成页依赖：
  - `route.query.apply`
  - `route.query.type/title/cost`
  - `sessionStorage.galleryApplyContext`
- `ImageAndPrompt.vue`、`SingleImageToVideo.vue`、`FaceSwap.vue`、`VideoSwap.vue`、`SingleImage.vue` 都是在 `onMounted()` 一次性读取模板上下文，不是响应式驱动。
- `MainLayout.vue` 没有 `KeepAlive`；从 `Gallery.vue` 跳走会导致列表重新挂载。
- `Gallery.vue` 的滚动容器是 `MainLayout.vue` 内部的 `a-layout-content`，不是 `body`。
- `useTaskResult.ts` 会保留最后一次提交任务的本地副本；如果不在新会话开始时清空，工作台会显示上一次结果。
- 当前 `useUpload.ts` 仅提供单实例本地上传状态，不具备跨组件管理上传句柄、批量中断、会话隔离能力。
- 后端 `ApplyContextResponse` 当前包含 `post_id/source_post_id/billing_resolution/task_type/input_file/input_file_url/prompt/lora_name/...`，但没有 `lora_strength`。
- `CustomFeatures.vue` 的 feature key 体系与后端 canonical `task_type` 不完全一致，例如 `faceswap` 与 `face_swap` 并存。
- `/users/history/{task_id}/apply-context` 返回的 `post_id` 在有 gallery post 时是 `gallery_post.id`，没有时才是 `history.id`，不能再把它简单理解为“当前入口实体 id”。

结论：
- 工作台方向可行。
- 但首期必须补齐“会话态”“统一归一化契约”“面板 cleanup 握手”“全局导航拦截”“上传注册表”“关闭统一入口”，否则高概率出现状态串线、导航绕过确认和关闭后脏回写。

## 3. 设计原则

首期采用以下原则：
- 工作台是“新状态容器”，不是旧页面的弹窗包装。
- 模板工作台与旧页面并存：旧页面继续服务普通入口和兼容链路，工作台只服务模板入口。
- 上下文转换只允许存在一条主路径，不能同时在入口和 Store 里各做一半。
- 会话必须显式建模；同一个 `taskType` 的不同模板，也必须强制重建实例。
- 上传管理必须明确“句柄归谁管、关闭时谁来中断、回写前谁来校验”。
- 路由切换拦截必须下沉到全局 Router 层，不能只依赖宿主组件自己感知。
- 工作台所有关闭入口都必须收口到统一协议，不允许任何入口直接 `visible = false`。
- 首期不支持工作台跨页面悬挂；用户离开当前页面时，工作台必须先被正确关闭或阻止离开。

## 4. 总体方案

### 4.1 单一入口契约

首期统一采用以下入口契约：

```ts
await templateApplyStore.openFromRawContext({
  source,
  entryEntityId,
  rawContext,
})
```

入参约束：
- `source` 只表示入口来源：`gallery | favorites | submissions`。
- `entryEntityId` 由调用方显式传入，表示“用户点开的当前列表项实体 id”；不得从后端 `post_id` 反推。
- `rawContext` 是后端 `apply-context` 原始响应。

调用方职责：
- 只负责请求后端原始响应。
- 只负责把当前点击对象的本地实体 id 一并传入 Store。
- 不再自行做 `normalizeTemplateApplyContext()`。
- 不再自行维护 `featureMap + router.push()`。

`openFromRawContext()` 内部必须完成：
- `normalizeTemplateApplyContext(rawContext, { source, entryEntityId })`
- `task_type -> supportMode/panelKind/taskMeta` 映射
- `workbench / legacy / unknown / invalid` 判定
- 已打开工作台时的替换打开关闭判定

建议返回结构：

```ts
type OpenTemplateApplyResult =
  | { status: 'opened'; sessionId: string }
  | {
      status: 'legacy_fallback'
      fallbackKind: 'legacy_supported' | 'unknown_task_type'
      rawTaskType: string
      meta: TemplateTaskMeta | null
    }
  | { status: 'invalid'; message: string }
  | {
      status: 'confirm_required'
      trigger: 'open_replace'
      confirmReason: CloseConfirmReason
    }
  | { status: 'blocked'; reason: 'opening' | 'closing' }
```

状态语义：
- `opened`：工作台已进入新会话。
- `legacy_fallback`：当前不进入工作台，但仍需由调用方按旧链路跳转。
- `invalid`：后端数据缺失或不可解析，应提示并终止。
- `confirm_required`：当前已有工作台会话，替换打开前必须先确认关闭。
- `blocked`：当前处于不允许打开新模板的中间态。

### 4.2 已打开工作台时再次打开模板

统一规则：
- 若工作台未打开，则直接进入 `openFromRawContext()` 正常流程。
- 若工作台已打开，则 `openFromRawContext()` 不得直接覆盖旧会话状态。
- 已打开状态下再次打开模板，必须先走 `requestClose('open_replace')`。
- 若返回 `close_now`，则立即执行 cleanup，再创建新会话。
- 若返回 `confirm_required`，由调用方弹确认框；确认后 cleanup，再重新进入打开流程。
- 若返回 `blocked`，则保持当前工作台，不创建新会话。

这样可以避免：
- 旧上传句柄还在运行时被新会话覆盖。
- 旧预览 URL / watcher / 本地结果副本泄漏到新会话。
- 同一个 `taskType` 连续打开时，因为组件未销毁而复用本地状态。

### 4.3 上下文模型

新增：
- `frontend/src/types/templateApply.ts`
- `frontend/src/utils/normalizeTemplateApplyContext.ts`

定义三层类型：

```ts
export type TemplateApplySource = 'gallery' | 'favorites' | 'submissions'

export type TemplateApplyTaskType =
  | 'i2i_pro'
  | 'i2i_draw'
  | 'edit'
  | 'img2img_lora'
  | 'face_swap'
  | 'face_video'
  | 'custom_video'
  | 'video_lora'
  | 'ltx_video'

export interface RawApplyContextResponse {
  post_id: number
  source_post_id?: number | null
  billing_resolution?: string | null
  task_id: string
  media_type: string
  prompt?: string | null
  lora_name?: string | null
  input_file?: string | null
  input_file_url?: string | null
  width?: number | null
  height?: number | null
  duration?: number | null
  task_type: string
}

export interface NormalizeContextOptions {
  source: TemplateApplySource
  entryEntityId: number | string | null
}

export interface TemplateApplyContext {
  raw: RawApplyContextResponse
  source: TemplateApplySource
  entryEntityId: number | string | null
  rawEntityId: number | null
  rawTaskType: string
  taskType: TemplateApplyTaskType | null
  supportMode: 'workbench' | 'legacy' | 'unknown'
  sourcePostId: number | null
  prompt: string | null
  loraName: string | null
  loraStrength: number | null
  inputFile: string | null
  inputFileUrl: string | null
  width: number | null
  height: number | null
  duration: number | null
  billingResolution: string | null
}
```

关键语义：
- `entryEntityId`：调用方传入的“当前点击列表项 id”，只服务前端 UI 和埋点，不参与后端提交。
- `rawEntityId`：后端原始 `post_id`，保留其原语义，不在前端重新解释。
- `sourcePostId`：仅表示“可用于提交 `source_post_id` 的真实 gallery post id”，只来自后端 `source_post_id`，不要再把 `post_id` 当成兜底。

要求：
- Store 只持有 `TemplateApplyContext`，不直接暴露原始接口对象给面板。
- `normalizeTemplateApplyContext()` 负责兼容空值、派生字段、字段收敛，以及 `task_type -> supportMode` 判定。
- `lora_strength` 因后端当前未返回，归一化后统一填 `null`；`img2img_lora` 继续使用前端默认强度兜底。
- 视频类模板继续复用 `templateVideoApplyState.ts` 中已稳定的分辨率/时长归一逻辑，但统一由 `normalizeTemplateApplyContext()` 调用，不允许各面板自行绕过。
- 原始 `task_type` 必须保留为 `string`，只在归一化后生成 `taskType | null`。

### 4.4 Task Meta 分层

新增：
- `frontend/src/constants/templateTaskMeta.ts`

职责：
- 只服务模板工作台与旧页面降级链路。
- 以“后端 canonical `task_type`”为 key。
- 不和 `CustomFeatures.vue` 的 feature card 目录强绑在一起。

建议结构：

```ts
type PanelKind = 'imagePrompt' | 'imageToVideo' | 'faceSwap' | 'videoSwap'

interface TemplateTaskMeta {
  taskType: TemplateApplyTaskType
  supportMode: 'workbench' | 'legacy'
  panelKind?: PanelKind
  legacyRouteName: string
  legacyTitleKey: string
  buildLegacyQuery: (ctx: TemplateApplyContext, t: ComposerTranslation) => Record<string, string>
}
```

约束：
- `templateTaskMeta.ts` 不是价格真值源。
- 工作台价格展示与提交参数继续由各面板按现有逻辑独立推导。
- `legacyTitleKey` 存 i18n key，不在常量文件里塞中文展示文案。
- `supportMode='legacy'` 只表示“旧页面可处理”；`unknown` 则表示“工作台和旧页面都没有明确映射”，不得强行跳 `CustomFeatures` 伪降级。

### 4.5 Store 设计

新增：
- `frontend/src/stores/templateApply.ts`

状态定义升级为“会话态 + 中间态 + 面板控制器”：

```ts
interface TemplateApplySessionMeta {
  sessionId: string
  source: TemplateApplySource
  entryEntityId: number | string | null
  openedAt: number
}

interface TemplateApplyPanelController {
  sessionId: string
  cleanup: () => Promise<void> | void
}

interface TemplateApplyState {
  visible: boolean
  loading: boolean
  status: 'idle' | 'opening' | 'visible' | 'closing'
  session: TemplateApplySessionMeta | null
  taskType: TemplateApplyTaskType | null
  panelKind: 'imagePrompt' | 'imageToVideo' | 'faceSwap' | 'videoSwap' | null
  context: TemplateApplyContext | null
  featureTitleKey: string | null
  dirty: boolean
  hasPendingUploads: boolean
  panelController: TemplateApplyPanelController | null
}
```

必须提供的方法：
- `openFromRawContext(params)`
- `setDirtyState(isDirty)`
- `setPendingUploads(hasPendingUploads)`
- `registerPanelController(controller | null)`
- `requestClose(trigger)`
- `confirmCloseAndCleanup(trigger)`
- `forceCloseAfterCleanup(sessionId)`
- `reset()`

关键约束：
- 每次 `openFromRawContext()` 都必须生成新的 `sessionId`。
- 即使两次打开的是同一个 `taskType`，也必须视为新会话。
- `dirty` 不允许完全依赖“每个输入项手动 mark”；面板应基于“初始化快照 vs 当前状态”派生后再上报 Store。
- `requestClose(trigger)` 只做判定与返回结果，不直接销毁状态。
- `confirmCloseAndCleanup(trigger)` 才是真正的清理编排入口。
- `forceCloseAfterCleanup(sessionId)` 是唯一允许真正把 `visible=false` 的地方，并且必须校验 `sessionId` 仍然匹配当前会话，避免旧 cleanup 误关新会话。

### 4.6 关闭协议

这是首期优先级最高的约束。

先拆清两个概念：

```ts
type CloseTrigger =
  | 'user_close'
  | 'mask_close'
  | 'esc'
  | 'gesture_close'
  | 'route_leave'
  | 'open_replace'

type CloseConfirmReason =
  | 'dirty'
  | 'uploading'
  | 'dirty_and_uploading'
```

建议返回结构：

```ts
type RequestCloseResult =
  | { status: 'close_now' }
  | {
      status: 'confirm_required'
      trigger: CloseTrigger
      confirmReason: CloseConfirmReason
    }
  | { status: 'blocked'; reason: 'opening' | 'closing' }
```

统一协议：

```ts
requestClose(trigger)
  -> confirm if needed
  -> confirmCloseAndCleanup(trigger)
  -> forceCloseAfterCleanup(sessionId)
```

必须遵守：
- 不允许任何地方直接 `templateApplyStore.visible = false`。
- 不允许宿主组件在 `@cancel` 中直接销毁工作台。
- 不允许面板内部自行决定“我先把弹层关掉，再慢慢收尾”。

`confirmCloseAndCleanup()` 内部固定顺序：
1. 读取当前 `sessionId`。
2. 调用 `templateApplyUploadStore.abortBySession(sessionId)`。
3. `await panelController?.cleanup()`，由面板释放本地预览 URL / object URL / watcher / 临时状态。
4. 调用 `forceCloseAfterCleanup(sessionId)`。

说明：
- 这里必须有 `registerPanelController()` 这类握手；否则 Store 无法真实等待面板 cleanup 完成，文档就会再次悬空。
- 面板卸载时仍要保留 `onBeforeUnmount()` 兜底释放，但主关闭链路不能只依赖卸载副作用。

### 4.7 宿主组件与滚动锁定

在 `frontend/src/layouts/MainLayout.vue` 挂载 `TemplateApplyWorkbenchHost.vue`。

同时新增：
- `frontend/src/composables/useWorkbenchScrollLock.ts`

实现要求：
- `MainLayout.vue` 中给 `a-layout-content` 增加 `ref`，不要让宿主通过裸 `document.querySelector()` 查找容器。
- `TemplateApplyWorkbenchHost.vue` 接收或注入该 `contentRef`，统一加锁和恢复滚动。
- 桌面端使用大尺寸 `a-modal`。
- 移动端使用全屏 `a-drawer` 或全屏 `a-modal`。
- 工作台内容必须有独立滚动容器，不能与背景页面共用同一个滚动容器。

挂载边界：
- 背景锁定的对象是 `MainLayout` 的 `contentRef`。
- 工作台自身的内容滚动发生在工作台内部容器。
- 不允许把“背景列表内容”和“工作台内容”放进同一个受锁容器里。

滚动锁定要求：
- 工作台打开时锁定 `MainLayout` 的内容容器，不锁 `body`。
- 关闭时恢复原有 `overflow`、滚动位置和必要的 style。
- 打开期间底层 `Gallery.vue` 不应继续触发滚动懒加载。
- 若宿主需要把工作台渲染到 `body`，可以使用默认 teleport；但无论是否 teleport，滚动锁定都必须仍然操作 `contentRef`。

### 4.8 全局路由关闭协议

关闭协议必须放到 Router 层，而不是只由宿主 UI 自己兜底。

首期实现方式：
- 在 `frontend/src/router/index.ts` 的全局 `beforeEach` 中接入 `templateApplyStore`。
- 路由守卫采用异步返回值风格，不再使用“弹异步确认框后多次 `next()`”的写法。
- 若工作台处于打开状态，且目标路由不是白名单，则必须先调用 `requestClose('route_leave')`。
- 若返回 `close_now`，先执行 cleanup，再允许导航。
- 若返回 `confirm_required`，弹确认框；用户确认后 cleanup，再继续导航；取消则返回 `false`。
- 若返回 `blocked`，直接返回 `false`。

建议写法：

```ts
router.beforeEach(async (to) => {
  const templateApplyStore = useTemplateApplyStore()

  if (!templateApplyStore.visible) {
    return true
  }

  if (to.meta.bypassTemplateApplyGuard) {
    await templateApplyStore.confirmCloseAndCleanup('route_leave')
    return true
  }

  const result = await templateApplyStore.requestClose('route_leave')

  if (result.status === 'close_now') {
    await templateApplyStore.confirmCloseAndCleanup('route_leave')
    return true
  }

  if (result.status === 'confirm_required') {
    const confirmed = await confirmTemplateClose(result.confirmReason)
    if (!confirmed) return false
    await templateApplyStore.confirmCloseAndCleanup('route_leave')
    return true
  }

  return false
})
```

必须增加白名单路由 meta：
- `/login`
- `/maintenance`

建议配置：

```ts
meta: { requiresAuth: false, bypassTemplateApplyGuard: true }
```

说明：
- 白名单不是“忽略 cleanup”，而是“允许无确认阻塞地优先完成 cleanup 后继续跳转”。
- 这样才能覆盖当前 `api` 拦截器里的 `router.push('/login')` 与 `router.push('/maintenance')`。

### 4.9 工作台会话重建策略

宿主渲染面板时，必须用 `sessionId` 作为 key：

```vue
<component
  :is="resolvedPanel"
  :key="templateApplyStore.session?.sessionId"
/>
```

原因：
- 现有独立页大量初始化逻辑依赖 `onMounted()`。
- 不强制重挂载会复用旧 `prompt`、旧上传对象、旧任务结果和旧锁定状态。

额外要求：
- 新会话创建前必须清空当前面板上一次的 `submittedTaskId`。
- 旧会话 cleanup 未完成前，不允许挂载新会话面板。

### 4.10 面板拆分

新增：
- `frontend/src/components/template-apply/TemplateApplyWorkbenchHost.vue`
- `frontend/src/components/template-apply/TemplateImagePromptPanel.vue`
- `frontend/src/components/template-apply/TemplateImageToVideoPanel.vue`
- `frontend/src/components/template-apply/TemplateFaceSwapPanel.vue`
- `frontend/src/components/template-apply/TemplateVideoSwapPanel.vue`

覆盖范围：
- `TemplateImagePromptPanel.vue`
  - `i2i_pro`
  - `i2i_draw`
  - `edit`
  - `img2img_lora`
- `TemplateImageToVideoPanel.vue`
  - `custom_video`
  - `video_lora`
  - `ltx_video`
- `TemplateFaceSwapPanel.vue`
  - `face_swap`
- `TemplateVideoSwapPanel.vue`
  - `face_video`

首期原则：
- 不直接复用整页组件。
- 允许复用已有 composable 和纯函数。
- 不追求四类任务抽成一个总组件。

建议按任务域拆共享逻辑：
- `useTemplateImagePromptPanel()`
- `useTemplateImageVideoPanel()`
- `useTemplateFaceSwapPanel()`
- `useTemplateVideoSwapPanel()`

每个面板必须负责：
- 根据归一化后的 `TemplateApplyContext` 建立本地初始化状态。
- 打开新会话时立即调用 `setSubmittedTaskId(null)`，清理上一任务结果副本。
- 在本地状态变化时上报 `dirty`。
- 在上传开始/结束时上报 `hasPendingUploads`。
- 在挂载时 `registerPanelController({ sessionId, cleanup })`。
- 在卸载时 `registerPanelController(null)`，并在 `onBeforeUnmount()` 中做兜底释放。

### 4.11 上传架构

首期不直接在旧的 `useUpload.ts` 上叠加会话语义，避免影响现有页面。

改为新增：
- `frontend/src/stores/templateApplyUpload.ts`
- `frontend/src/composables/useTemplateApplyUpload.ts`

职责拆分：

1. `templateApplyUploadStore`
- 负责持有所有工作台上传句柄。
- 负责按 `sessionId` 批量中断。
- 负责校验回写是否仍然有效。

2. `useTemplateApplyUpload(sessionId)`
- 提供给工作台面板使用的组合式封装。
- 负责把 `slot`、进度、完成回调等信息桥接到面板本地状态。

建议接口：

```ts
interface UploadHandle {
  uploadId: string
  sessionId: string
  slot: string
  xhr: XMLHttpRequest
  status: 'pending' | 'uploading' | 'done' | 'aborted' | 'failed'
}

uploadFile(file, { sessionId, slot }): Promise<{ uploadId: string; objectKey: string | null }>
abortUpload(uploadId): void
abortBySession(sessionId): void
isUploadStillActive(uploadId, sessionId, slot): boolean
```

强约束：
- 每次上传生成独立 `uploadId`。
- 每个上传句柄必须登记在 `templateApplyUploadStore` 中。
- 回写前必须同时校验：
  - `uploadId` 仍存在
  - `sessionId` 仍等于当前会话
  - `slot` 仍对应当前槽位
- `abortBySession(sessionId)` 是工作台关闭、路由离开、替换打开的统一入口。

关闭策略：
- 若存在进行中的上传，关闭前必须二次确认。
- 用户确认关闭后：
  1. `abortBySession(sessionId)`
  2. `await panelController.cleanup()`
  3. `forceCloseAfterCleanup(sessionId)`
- 若浏览器层面未及时终止，仍通过 `uploadId/sessionId/slot` 校验丢弃过期回写。

备注：
- 若后续希望与旧页面共用底层 PUT 上传逻辑，可在 Phase 2 再从 `useUpload.ts` 中抽出低层 transport helper；Phase 1 不做这件事。

### 4.12 提交后的行为

首期不要自动关闭工作台。

改为：
- 提交成功后，工作台保留当前面板。
- 用户可在工作台内看到任务进入 `pending/running`。
- 用户可手动关闭。
- 关闭后由全局 `TaskProgress` 继续承接。

实现要求：
- 每个面板内部继续使用 `useTaskStream.ts` + `useTaskResult.ts`。
- 打开新会话前必须清空上一次 `submittedTaskId`。
- 工作台关闭时不自动移除 `tasksStore` 中的活动任务。
- 若工作台已提交成功但仍处于打开状态，再次打开其他模板时，仍需先走替换打开关闭协议。

## 5. Gallery 首期改造范围

首期只改 `Gallery.vue` 的模板入口行为。

唯一有效流程：
1. 点击“一键应用”时请求 `/gallery/posts/{post_id}/apply-context`。
2. 调用 `templateApplyStore.openFromRawContext({ source: 'gallery', entryEntityId: currentPost.id, rawContext })`。
3. 根据返回值分流：
   - `opened`：关闭详情弹窗，展示工作台。
   - `legacy_fallback`：关闭详情弹窗，提示后走旧页面兼容链路。
   - `invalid`：提示错误，不关闭当前上下文或按产品决定是否关闭详情弹窗。
   - `confirm_required`：弹关闭确认；确认后先执行 cleanup，再重新进入打开流程。
   - `blocked`：保持当前工作台，不关闭详情弹窗。
4. 删除 `Gallery.vue` 当前内联 `featureMap + router.push()` 的模板入口逻辑。

降级链路要求：
- 旧页面跳转参数统一由 `templateTaskMeta.ts` 提供，不允许 `Gallery.vue` 再内联一套映射。
- `legacy_fallback` 分两类：
  - `legacy_supported`：写 `sessionStorage.galleryApplyContext`，再按明确的旧页面 meta 跳转。
  - `unknown_task_type`：提示“当前模板暂不支持打开”，默认不跳转；如后续产品要求跳卡片目录，再单独设计，不在本期混入。

这样可以直接保留：
- 当前筛选。
- 当前排序。
- 已加载列表。
- 当前滚动位置。

首期不改：
- `MyFavorites.vue`
- `MySubmissionsPanel.vue`

但本次必须先抽好公共 meta 与归一化工具，避免二期返工。

## 6. 实施顺序

### Phase 1A：公共模型与统一契约

- 新增 `templateApply.ts` 类型。
- 新增 `normalizeTemplateApplyContext.ts`。
- 新增 `templateTaskMeta.ts`。
- 复用并收口 `templateVideoApplyState.ts`。
- 新增 `templateApply` Store，并确定 `openFromRawContext()` / `requestClose()` / `confirmCloseAndCleanup()` 契约。

### Phase 1B：宿主与关闭协议

- 在 `MainLayout.vue` 中给 `a-layout-content` 增加 `ref`。
- 新增 `TemplateApplyWorkbenchHost.vue`。
- 新增 `useWorkbenchScrollLock.ts`。
- 明确 `a-modal` / `a-drawer` 的关闭配置，禁止默认关闭行为绕过 cleanup。

### Phase 1C：全局导航协议

- 在 `router/index.ts` 中接入全局关闭协议。
- 将路由守卫改为异步返回值风格。
- 为 `/login`、`/maintenance` 增加 `bypassTemplateApplyGuard` 白名单 meta。

### Phase 1D：会话级上传能力

- 新增 `templateApplyUpload` Store。
- 新增 `useTemplateApplyUpload(sessionId)`。
- 完成 `abortBySession(sessionId)` 与过期回写校验。

### Phase 1E：落 4 个工作台面板

- 新增 4 个工作台面板。
- 每个面板接入模板初始化、提交、dirty 上报、关闭确认、任务结果清理、资源释放。
- 每个面板接入 `registerPanelController()`。

### Phase 1F：改造入口

- 改造 `Gallery.vue` 的 `handleApply()`。
- 删除其模板应用时的内联 `router.push()` 分支。
- 接入新 Store 返回值与降级逻辑。

### Phase 2：扩展入口与公共目录收口

- `MyFavorites.vue`
- `MySubmissionsPanel.vue`
- 视实际收益决定是否收口 `CustomFeatures.vue` 的 feature card 目录。
- 视实际收益决定是否抽取旧 `useUpload.ts` 的底层传输能力。

## 7. 涉及文件

首期必改：
- `frontend/src/views/Gallery.vue`
- `frontend/src/layouts/MainLayout.vue`
- `frontend/src/router/index.ts`
- `frontend/src/stores/templateApply.ts`
- `frontend/src/stores/templateApplyUpload.ts`
- `frontend/src/constants/templateTaskMeta.ts`
- `frontend/src/types/templateApply.ts`
- `frontend/src/utils/normalizeTemplateApplyContext.ts`
- `frontend/src/composables/useWorkbenchScrollLock.ts`
- `frontend/src/composables/useTemplateApplyUpload.ts`
- `frontend/src/components/template-apply/TemplateApplyWorkbenchHost.vue`
- `frontend/src/components/template-apply/TemplateImagePromptPanel.vue`
- `frontend/src/components/template-apply/TemplateImageToVideoPanel.vue`
- `frontend/src/components/template-apply/TemplateFaceSwapPanel.vue`
- `frontend/src/components/template-apply/TemplateVideoSwapPanel.vue`

首期优先复用：
- `frontend/src/composables/useTaskStream.ts`
- `frontend/src/composables/useTaskResult.ts`
- `frontend/src/utils/templateVideoApplyState.ts`

首期明确不动的旧兼容链路：
- `frontend/src/views/MyFavorites.vue`
- `frontend/src/components/MySubmissionsPanel.vue`
- `frontend/src/views/ImageAndPrompt.vue`
- `frontend/src/views/SingleImageToVideo.vue`
- `frontend/src/views/FaceSwap.vue`
- `frontend/src/views/VideoSwap.vue`
- `frontend/src/views/SingleImage.vue`
- `frontend/src/composables/useUpload.ts`

建议新增单测：
- `frontend/src/stores/templateApply.test.ts`
- `frontend/src/stores/templateApplyUpload.test.ts`
- `frontend/src/utils/normalizeTemplateApplyContext.test.ts`
- `frontend/src/components/template-apply/*.test.ts`

## 8. 验收标准

满足以下条件才算首期完成：
- 在 `Gallery.vue` 点击“一键应用”后不发生路由跳转。
- 关闭工作台后，筛选、排序、列表和滚动位置保持不变。
- 工作台打开时，底层内容容器不可滚动，`Gallery.vue` 不继续懒加载，工作台自身仍可正常滚动。
- 同一个 `taskType` 连续打开两个不同模板时，第二次打开不会继承第一次的输入、上传状态或任务结果。
- 工作台已打开时再次点击其他模板，不会直接覆盖旧会话，而是先进入替换打开关闭协议。
- 4 类任务都能正确回填 `apply-context`。
- 已支持任务的提交 payload 与现有独立页行为一致。
- 提交后用户能看到任务进入排队/运行。
- 关闭工作台后，`TaskProgress` 能继续接管任务。
- 上传中关闭工作台后，不会把旧上传结果写回新会话或已关闭面板。
- 弹层右上角、遮罩层、Esc、移动端关闭手势、侧边栏、底部导航、浏览器回退、普通 `router.push()` 都不能绕过关闭协议。
- 登录页与维护页跳转不被工作台错误拦截，也不会与关闭确认形成死锁。
- 遇到 `legacy_supported` 的任务时，能稳定走旧页面链路。
- 遇到 `unknown_task_type` 时，不会报错或卡死，而是明确提示并中止。

## 9. 测试清单

### 9.1 Store / Utils 单测

- `templateApplyStore.openFromRawContext()`
  - 每次打开都会生成新的 `sessionId`
  - 能正确归一化 `rawContext`
  - `workbench / legacy / unknown / invalid` 分流正确
  - 工作台已打开时再次打开会返回正确的替换打开结果
- `templateApplyStore.requestClose()/confirmCloseAndCleanup()/forceCloseAfterCleanup()/reset()`
  - `route_leave` 不再和确认原因枚举混用
  - `forceCloseAfterCleanup(sessionId)` 不会误关新会话
- `normalizeTemplateApplyContext()`
  - 空字段兼容
  - `billing_resolution` 兼容
  - `lora_strength` 缺失时默认行为正确
  - `entryEntityId` 与 `raw.post_id` 语义分离正确
  - `source_post_id` 只在可提交时保留
- `templateApplyUploadStore`
  - `abortBySession(sessionId)` 能正确中断多句柄
  - 关闭后旧 `uploadId` 回写会被拒绝

### 9.2 面板单测

- 不同 `taskType` 的上下文回填
- payload 拼装
- cost 计算
- 新会话打开时清理旧 `submittedTaskId`
- 关闭时 dirty 判断
- 上传完成晚于关闭时不会脏回写
- 同一面板多个上传槽位并发上传时，旧回调不会覆盖新槽位状态
- 面板卸载时会释放本地 object URL
- `registerPanelController()` 生命周期正确

### 9.3 路由交互验证

- 打开工作台后通过侧边栏切换路由，会先经过关闭协议
- 打开工作台后通过移动端底部导航切换路由，会先经过关闭协议
- 打开工作台后浏览器回退，会先经过关闭协议
- 工作台打开时跳转 `/login`、`/maintenance` 不会死锁
- 工作台打开时，接口拦截器触发跳转也能正确 cleanup

### 9.4 关闭入口验证

- 点击右上角关闭按钮会先经过关闭协议
- 点击遮罩层不会直接关闭工作台
- 按 `Esc` 不会直接关闭工作台
- 移动端关闭手势不会直接关闭工作台

### 9.5 手工回归

- `市集 -> 详情 -> 一键应用 -> 关闭工作台 -> 回到原滚动位置`
- `市集 -> 详情 -> 一键应用 -> 上传 -> 关闭工作台 -> 不出现旧上传结果回写`
- `市集 -> 模板A(i2i_pro) -> 关闭 -> 模板B(i2i_pro) -> 不继承模板A的 prompt/结果`
- `市集 -> 模板A工作台打开 -> 直接点模板B -> 先弹关闭确认，再决定是否切换`
- `市集 -> 详情 -> 一键应用 -> 上传 -> 提交 -> 关闭工作台 -> TaskProgress 继续显示`
- `市集 -> 详情 -> 一键应用 -> 提交成功 -> 再打开另一模板 -> 不显示上一次任务结果`
- `市集 -> 一键应用 -> 上传槽位A与槽位B并发上传 -> 关闭工作台 -> 不残留任一旧回写`
- `市集 -> 一键应用 -> 打开工作台 -> 浏览器回退 / 底部导航切页 -> 先弹关闭确认，再决定是否跳转`
- `市集 -> 一键应用 -> 遇到 legacy_fallback -> 正常按旧链路打开`
- `市集 -> 一键应用 -> 遇到 unknown_task_type -> 明确提示，不发生错误跳转`

## 10. 本稿相对上一版的修正点

本稿重点修正了四类会直接影响开发落地的问题：
- 把 `requestClose()` 的“触发原因”与“确认原因”拆成两个枚举，消除 `route_leave` 与 `dirty/uploading` 混用冲突。
- 新增 `registerPanelController()`，让 `confirmCloseAndCleanup()` 能真实等待面板 cleanup，而不是把关键步骤悬空。
- 不再把后端 `post_id` 当成统一的“入口实体 id”，改为显式区分 `entryEntityId`、`rawEntityId`、`sourcePostId`。
- 把“工作台不支持但旧页面可处理”和“完全未知 task_type”拆开，避免把未知类型错误地伪降级到 `CustomFeatures`。

按本方案实施，首期工作量仍然可控，但关键边界已经写死，能显著降低以下回归风险：
- 同类模板二次打开串状态
- 上传异步回调写脏状态
- 导航绕过关闭确认
- 默认弹层关闭绕过 cleanup
- 工作台与旧生成页行为漂移
- 二期接 `favorites/submissions` 时的字段语义误用
