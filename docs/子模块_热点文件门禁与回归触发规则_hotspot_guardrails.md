# 热点文件门禁与回归触发规则

## 1. 目标

本规则用于把前几轮低风险重构的收益固化下来，避免后续功能开发再次把复杂度堆回热点文件。

本规则只约束以下事项：

- 哪些文件属于热点文件，改动后必须额外审视
- 改动不同热点文件时，至少要跑哪一组自动化回归
- 新逻辑应该优先进入哪一层，避免重新堆回 router、page 或大文件

本规则不替代具体业务文档，也不替代任务黄金路径清单；涉及任务主链路时，应与 `docs/子模块_任务黄金路径回归清单_task_golden_path.md` 配合使用。

统一执行入口：

- `scripts/run_hotspot_regression.sh`
- `.github/workflows/hotspot_regression_gate.yml`
- `docs/子模块_GitHub分支保护与热点回归门禁_branch_protection.md`

## 2. 当前阶段快照

截至本轮收口，阶段推进状态如下：

- 阶段 1：基本完成，重复胶水、最薄公共状态组件、后端 fallback/session 样板已完成一轮清理
- 阶段 2：主体完成，`Gallery`、`MyFavorites`、`MySubmissions` 与生成页工作台公共结构已收口
- 阶段 3：基本完成，`message_handler.py`、`users.py`、`gallery.py`、`tasks.py` 已完成主要薄控制器收口
- 阶段 4：本轮完成收口，历史 `bot_task_service.py` compat 壳已下线，`backend/app/main.py`、`backend/app/queue_manager.py` 已通过完整阶段 4 回归
- 阶段 7：第二批主体完成，已补齐共享详情弹层/工作台壳层 focused 回归、`MyFavorites` 组合流回归，以及 dashboard App 热点基线与独立门禁分组；但 router guard 仍未完全并入共享关闭协议，workflow 对部分新热点文件的 path 触发也仍有缺口

## 3. 热点文件

### 3.1 任务主链路

- Bot 分域 entrypoint 文件簇
- `src/services/task_service_entrypoints.py`
- `src/services/task_service_entrypoints_generation.py`
- `src/services/task_service_flow.py`
- `src/services/task_service_completion.py`
- `src/services/task_service_finalize.py`
- `src/services/task_service_support.py`
- `src/services/task_service_message_support.py`
- `src/services/task_service_entrypoint_support.py`
- `backend/app/main.py`
- `backend/app/main_bootstrap.py`
- `backend/app/main_t2i_wiring.py`
- `backend/app/dependencies.py`
- `backend/app/routers/agent.py`
- `backend/app/queue_manager.py`
- `src/core/task_core.py`
- `src/core/task_core_submission.py`
- `src/web_api/__init__.py`
- `src/web_api/main.py`
- `src/web_api/dependencies.py`
- `src/web_api/routers/tasks.py`
- `src/web_api/services/task_submission_service.py`
- `src/web_api/services/task_runtime_api_service.py`
- `src/web_api/services/task_result_service.py`
- `src/web_api/services/task_stream_api_service.py`
- `src/web_api/services/task_action_api_service.py`

### 3.2 Web 接入层

- `src/web_api/routers/users.py`
- `src/web_api/services/users_history_service.py`
- `src/web_api/services/users_history_mutation_service.py`
- `src/web_api/services/user_profile_service.py`
- `src/services/user_persistence_service.py`
- `src/web_api/routers/gallery.py`
- `src/web_api/services/gallery_service_queries.py`
- `src/web_api/services/gallery_service_mutations.py`
- `src/web_api/services/gallery_service_comments.py`
- `src/web_api/services/gallery_service_support.py`
- `src/core/gallery_core.py`
- `src/core/gallery_feed_queries.py`
- `src/core/gallery_submission_core.py`
- `src/core/gallery_interactions_core.py`
- `src/services/gallery_repository.py`
- `src/handlers/message_handler.py`
- `src/handlers/message_handler_common.py`
- `src/handlers/message_handler_profile.py`
- `src/handlers/message_handler_profile_menu.py`
- `src/handlers/message_handler_media.py`
- `src/handlers/message_handler_media_entry.py`
- `src/handlers/message_handler_menu.py`
- `src/handlers/message_handler_runtime.py`
- `src/handlers/message_handler_prompt.py`

### 3.3 前端公共壳层

- `frontend/src/views/Gallery.vue`
- `frontend/src/views/MyFavorites.vue`
- `frontend/src/components/GalleryDetailModal.vue`
- `frontend/src/components/DetailModalShell.vue`
- `frontend/src/components/MySubmissionsPanel.vue`
- `frontend/src/components/PostBrowserShell.vue`
- `frontend/src/components/ListStateBlock.vue`
- `frontend/src/components/GenerationWorkbenchShell.vue`
- `frontend/src/components/template-apply/TemplateApplyWorkbenchHost.vue`
- `frontend/src/composables/useDetailTemplateApply.ts`
- `frontend/src/composables/useTemplateApplyCloseProtocol.ts`
- `frontend/src/composables/useGalleryDetailModalAdapter.ts`
- `frontend/src/router/index.ts`
- `dashboard/frontend/src/App.vue`

## 4. 回归触发规则

### 4.1 修改任务主链路 facade 或 support

适用文件：

- Bot entrypoint 文件簇
- `task_service_entrypoints.py`
- `task_service_entrypoints_generation.py`
- `task_service_flow.py`
- `task_service_completion.py`
- `task_service_finalize.py`
- `task_service_support.py`
- `task_service_message_support.py`
- `task_service_entrypoint_support.py`

至少执行：

```bash
pytest \
  tests/services/test_task_service_flow.py \
  tests/services/test_task_service_completion.py \
  tests/services/test_task_service_support.py \
  tests/services/test_task_service_message_support.py \
  tests/services/test_task_service_entrypoint_support.py
```

如果改动涉及任务提交、取消、状态字段、completion/finalize seam，升级为执行“任务黄金路径最小必跑集”。

### 4.2 修改 `backend/app/main.py`、`backend/app/queue_manager.py`、`src/core/task_core.py` 或 `src/core/task_core_submission.py`

至少执行“任务黄金路径完整集”：

```bash
pytest \
  tests/integration/test_saga_and_queue.py \
  tests/backend/test_main_helpers.py \
  tests/backend/test_queue_manager.py \
  tests/core/test_task_core_submission.py \
  tests/web_api/test_tasks_action_api_service.py \
  tests/web_api/test_tasks_generate.py \
  tests/web_api/test_tasks_stream.py \
  tests/services/test_task_service_completion.py \
  tests/services/test_task_service_flow.py \
  tests/services/test_task_service_support.py \
  tests/services/test_task_service_message_support.py \
  tests/services/test_task_service_entrypoint_support.py
```

原因：

- 这三处一旦漂移，通常会同时影响提交、排队、取消、同步等待、SSE 或历史兜底
- 单点 focused tests 不足以覆盖跨层行为

双入口职责补充：

- `src/web_api` 只承接用户侧 Web/BFF 能力；新增用户可见 HTTP 能力默认放这里
- `backend/app` 只承接执行面、中控、worker/agent 协议；不要把新的用户侧接口接到这里
- 若 PR 同时修改 `src/web_api` 入口文件与 `backend/app` 入口文件，评审时必须显式说明该改动为何不属于入口漂移

### 4.3 修改 `tasks` Web API 入口

适用文件：

- `src/web_api/routers/tasks.py`
- `src/web_api/services/task_submission_service.py`
- `src/web_api/services/task_runtime_api_service.py`
- `src/web_api/services/task_result_service.py`
- `src/web_api/services/task_stream_api_service.py`
- `src/web_api/services/task_action_api_service.py`

至少执行：

```bash
pytest \
  tests/web_api/test_tasks_action_api_service.py \
  tests/web_api/test_tasks_generate.py \
  tests/web_api/test_tasks_stream.py \
  tests/web_api/test_task_runtime_api_service.py
```

如果改动同时触及任务状态字段、terminal payload 或历史兜底，补跑“任务黄金路径最小必跑集”。

### 4.4 修改 `users` Web API

适用文件：

- `src/web_api/routers/users.py`
- `src/web_api/services/users_history_service.py`
- `src/web_api/services/users_history_mutation_service.py`
- `src/web_api/services/user_profile_service.py`
- `src/services/user_persistence_service.py`

至少执行：

```bash
pytest \
  tests/services/test_user_persistence_service.py \
  tests/core/test_user_core.py \
  tests/web_api/test_users_apply_context.py \
  tests/web_api/test_users_history_urls.py \
  tests/web_api/test_users_history_mutation_service.py \
  tests/web_api/test_users_affiliate_redeem.py \
  tests/web_api/test_users_affiliate_redeem_router.py
```

### 4.5 修改 `gallery` Web API

适用文件：

- `src/web_api/routers/gallery.py`
- `src/web_api/services/gallery_service_queries.py`
- `src/web_api/services/gallery_service_mutations.py`
- `src/web_api/services/gallery_service_comments.py`
- `src/web_api/services/gallery_service_support.py`
- `src/core/gallery_core.py`
- `src/core/gallery_feed_queries.py`
- `src/core/gallery_submission_core.py`
- `src/core/gallery_interactions_core.py`
- `src/services/gallery_repository.py`

至少执行：

```bash
pytest \
  tests/core/test_gallery_submission_and_interactions_core.py \
  tests/handlers/callbacks/test_gallery_callbacks_interactions.py \
  tests/web_api/test_gallery_router_passthrough.py \
  tests/web_api/test_gallery_apply_context.py \
  tests/web_api/test_gallery_media_urls.py \
  tests/web_api/test_gallery_comments.py \
  tests/web_api/test_gallery_post_deletion.py \
  tests/web_api/test_gallery_task_type_filters.py
```

补充约束：

- Gallery 的新查询/变更优先进入 repository/query seam，不要把 SQLAlchemy 查询继续堆回 callback/router/core 主流程。
- `task_core_submission.py` 的默认依赖只允许通过统一 default dependency builder 解析，不要新增新的 `*_default` 函数内现建依赖。
- `user_persistence_service.py` 中 `id == tg_id` 的旧双 ID 兼容分支属于待退出 seam；新增逻辑不得继续依赖该分支作为主路径。

### 4.6 修改 Telegram `message_handler` 入口

适用文件：

- `src/handlers/message_handler.py`
- `src/handlers/message_handler_common.py`
- `src/handlers/message_handler_profile.py`
- `src/handlers/message_handler_profile_menu.py`
- `src/handlers/message_handler_media.py`
- `src/handlers/message_handler_media_entry.py`
- `src/handlers/message_handler_menu.py`
- `src/handlers/message_handler_runtime.py`
- `src/handlers/message_handler_prompt.py`

至少执行：

```bash
pytest \
  tests/handlers/test_message_handler.py \
  tests/handlers/test_message_handler_common.py \
  tests/handlers/test_message_handler_profile.py \
  tests/handlers/test_message_handler_media.py \
  tests/handlers/test_message_handler_menu.py \
  tests/handlers/test_message_handler_media_entry.py \
  tests/handlers/test_message_handler_runtime.py \
  tests/handlers/test_message_handler_prompt.py
```

### 4.7 修改前端公共壳层

适用文件：

- `frontend/src/views/Gallery.vue`
- `frontend/src/views/MyFavorites.vue`
- `frontend/src/components/GalleryDetailModal.vue`
- `frontend/src/components/DetailModalShell.vue`
- `frontend/src/components/MySubmissionsPanel.vue`
- `frontend/src/components/PostBrowserShell.vue`
- `frontend/src/components/ListStateBlock.vue`
- `frontend/src/components/GenerationWorkbenchShell.vue`
- `frontend/src/components/template-apply/TemplateApplyWorkbenchHost.vue`
- `frontend/src/composables/useDetailTemplateApply.ts`
- `frontend/src/composables/useTemplateApplyCloseProtocol.ts`
- `frontend/src/composables/useGalleryDetailModalAdapter.ts`
- `frontend/src/router/index.ts`

至少执行：

```bash
cd frontend && pnpm vitest run \
  src/views/Gallery.test.ts \
  src/views/MyFavoritesFlow.test.ts \
  src/components/GalleryDetailModal.test.ts \
  src/components/DetailModalShell.test.ts \
  src/components/MySubmissionsPanelFlow.test.ts \
  src/components/PostBrowserShell.test.ts \
  src/components/ListStateBlock.test.ts \
  src/components/GenerationWorkbenchShell.test.ts \
  src/components/template-apply/TemplateApplyWorkbenchHost.test.ts \
  src/composables/useGalleryDetailModalAdapter.test.ts \
  src/router/index.test.ts \
  src/stores/tasksRuntime.test.ts \
  src/stores/taskResultState.test.ts \
  src/stores/templateApply.test.ts \
  src/composables/useTemplateApplyUpload.test.ts \
  src/utils/normalizeTemplateApplyContext.test.ts
```

说明：

- `frontend-shared` 分组当前默认就包含模板应用与生成工作台状态流相关测试，不再区分“基础壳层必跑”与“涉及时再补跑”两档
- `useTemplateApplyCloseProtocol.ts` 已属于应纳入同组门禁的共享协议文件；在 workflow path 规则补齐前，修改该文件时应手动执行 `frontend-shared`

### 4.8 修改 dashboard App 壳层

适用文件：

- `dashboard/frontend/src/App.vue`

至少执行：

```bash
cd dashboard/frontend && npm exec -- vitest run \
  src/App.test.js
```

## 5. 热点文件修改约束

- 新逻辑优先进 `service`、`presenter`、`composable`、`support helper`，不要直接堆进 `router`、`handler`、`page`
- 新增 helper 前，优先补 focused test，再移动主流程代码
- 超过 300 行的新文件需要自查是否还能继续按职责拆分
- 超过 500 行的新增或重写文件，必须在提交说明里解释为何不能继续拆
- 若只是为了兼容测试或 monkeypatch seam 而保留 facade wrapper，应在说明里明确标注“兼容壳”

## 6. CI 门禁入口

当前已提供两层统一入口：

- 本地/终端执行：`scripts/run_hotspot_regression.sh`
- GitHub Actions 门禁：`.github/workflows/hotspot_regression_gate.yml`

`hotspot_regression_gate.yml` 的行为约束如下：

- 对热点文件变更的 `pull_request` 和 `main` 分支 `push` 自动触发
- 支持 `workflow_dispatch` 手动指定分组，例如 `task-min frontend-shared dashboard-frontend`
- 根据改动路径自动推导 Python、主站 Frontend 与 Dashboard Frontend 分组
- 当命中 `task-full` 时，自动去重并跳过被其覆盖的 `task-facade`、`task-min`、`tasks-web`
- 若本次没有识别到热点分组，则以 no-op job 结束，避免 workflow 悬空
- `Hotspot Gate Result` 聚合 job 提供稳定检查名，供 branch protection 配置 required check

说明：

- 本文的“热点文件清单”以当前代码结构为准；workflow 的 `paths` 配置若仍使用粗粒度 glob 或旧文件名，应视为待同步项，而不是反向收窄文档口径

## 7. 当前缺口

- 当前热点门禁已补齐 dashboard App 独立分组，但 branch protection 的 required checks 清单仍需在仓库设置侧正式固化
- 页面家族已补到“列表切换 + 详情弹层 + 模板工作台”关键组合流，但仍未覆盖更重的跨页面端到端场景
- workflow `paths` 仍有少量与当前代码结构不一致的地方：Bot 分域 entrypoint 尚未全部具备稳定路径触发；修改这些文件时不能只依赖自动门禁
- `frontend-shared` 当前实际已默认执行模板应用状态流测试，但文档早先的“两段式补跑”口径已不再适用，后续应统一按单一分组理解

## 8. 阶段 7 第一批收尾标志

满足以下条件时，可认为阶段 7 第一批完成：

- 已形成明确的热点文件清单
- 已形成“改哪类文件就跑哪组测试”的最小规则
- 已把任务主链路回归与非任务热点回归区分开
- 已明确当前仍未覆盖的治理缺口，供下一批继续处理

## 9. 阶段 7 第二批收尾标志

满足以下条件时，可认为阶段 7 第二批完成：

- 共享详情弹层、页面壳层与工作台壳层已进入 focused tests，且大部分已进入热点门禁
- 至少存在 1 组“列表切换 + 详情弹层 + 模板工作台”的组合回归
- `dashboard/frontend/src/App.vue` 已具备最小可用回归基线
- workflow 已按 Python、主站 Frontend、Dashboard Frontend 拆分热点执行入口
- 与模板应用关闭共享协议、gallery 拆分 service 对应的 path 触发缺口已被明确记录，未再混入“已完成”口径

## 10. 下一批建议

阶段 7 主体完成后，后续治理建议保留三类长期项：

1. 在仓库设置里固化 required checks / branch protection
2. 继续补齐 workflow `paths` 与热点清单之间的剩余缺口，尤其是 Bot 分域 entrypoint
3. 视风险再补更重的跨页面端到端回归，而不是继续堆 focused tests 数量
