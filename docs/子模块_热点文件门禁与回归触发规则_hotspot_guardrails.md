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
- 阶段 4：本轮完成收口，`task_service.py`、`backend/app/main.py`、`backend/app/queue_manager.py` 已通过完整阶段 4 回归
- 阶段 7：当前进入第一批，目标是把热点文件门禁、回归触发规则与最小治理约束文档化

## 3. 热点文件

### 3.1 任务主链路

- `src/services/task_service.py`
- `src/services/task_service_flow.py`
- `src/services/task_service_completion.py`
- `src/services/task_service_finalize.py`
- `src/services/task_service_support.py`
- `src/services/task_service_message_support.py`
- `src/services/task_service_entrypoint_support.py`
- `backend/app/main.py`
- `backend/app/queue_manager.py`
- `src/core/task_core.py`
- `src/web_api/routers/tasks.py`
- `src/web_api/services/task_stream_api_service.py`
- `src/web_api/services/task_action_api_service.py`

### 3.2 Web 接入层

- `src/web_api/routers/users.py`
- `src/web_api/services/users_history_service.py`
- `src/web_api/services/users_history_mutation_service.py`
- `src/web_api/services/user_profile_service.py`
- `src/web_api/routers/gallery.py`
- `src/web_api/services/gallery_service.py`
- `src/handlers/message_handler.py`
- `src/handlers/message_handler_common.py`
- `src/handlers/message_handler_profile.py`
- `src/handlers/message_handler_media.py`
- `src/handlers/message_handler_menu.py`

### 3.3 前端公共壳层

- `frontend/src/views/Gallery.vue`
- `frontend/src/components/MySubmissionsPanel.vue`
- `frontend/src/components/ListStateBlock.vue`
- `frontend/src/components/template-apply/TemplateApplyWorkbenchHost.vue`
- `frontend/src/router/index.ts`
- `dashboard/frontend/src/App.vue`

## 4. 回归触发规则

### 4.1 修改任务主链路 facade 或 support

适用文件：

- `task_service.py`
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
  tests/services/test_task_service_entrypoint_support.py \
  src/tests/test_task_service_refactored.py \
  src/tests/test_queue_logic.py
```

如果改动涉及任务提交、取消、状态字段、completion/finalize seam，升级为执行“任务黄金路径最小必跑集”。

### 4.2 修改 `backend/app/main.py`、`backend/app/queue_manager.py` 或 `src/core/task_core.py`

至少执行“任务黄金路径完整集”：

```bash
pytest \
  tests/integration/test_saga_and_queue.py \
  tests/backend/test_main_helpers.py \
  tests/backend/test_queue_manager.py \
  tests/web_api/test_tasks_action_api_service.py \
  tests/web_api/test_tasks_router_passthrough.py \
  tests/web_api/test_tasks_stream.py \
  tests/services/test_task_service_completion.py \
  tests/services/test_task_service_flow.py \
  tests/services/test_task_service_support.py \
  tests/services/test_task_service_message_support.py \
  tests/services/test_task_service_entrypoint_support.py \
  src/tests/test_task_service_refactored.py \
  src/tests/test_queue_logic.py
```

原因：

- 这三处一旦漂移，通常会同时影响提交、排队、取消、同步等待、SSE 或历史兜底
- 单点 focused tests 不足以覆盖跨层行为

### 4.3 修改 `tasks` Web API 入口

适用文件：

- `src/web_api/routers/tasks.py`
- `src/web_api/services/task_stream_api_service.py`
- `src/web_api/services/task_action_api_service.py`

至少执行：

```bash
pytest \
  tests/web_api/test_tasks_action_api_service.py \
  tests/web_api/test_tasks_router_passthrough.py \
  tests/web_api/test_tasks_stream.py
```

如果改动同时触及任务状态字段、terminal payload 或历史兜底，补跑“任务黄金路径最小必跑集”。

### 4.4 修改 `users` Web API

适用文件：

- `src/web_api/routers/users.py`
- `src/web_api/services/users_history_service.py`
- `src/web_api/services/users_history_mutation_service.py`
- `src/web_api/services/user_profile_service.py`

至少执行：

```bash
pytest \
  tests/web_api/test_users_apply_context.py \
  tests/web_api/test_users_history_urls.py \
  tests/web_api/test_users_history_mutation_service.py \
  tests/web_api/test_users_affiliate_redeem.py \
  tests/web_api/test_users_affiliate_redeem_router.py
```

### 4.5 修改 `gallery` Web API

适用文件：

- `src/web_api/routers/gallery.py`
- `src/web_api/services/gallery_service.py`

至少执行：

```bash
pytest \
  tests/web_api/test_gallery_router_passthrough.py \
  tests/web_api/test_gallery_apply_context.py \
  tests/web_api/test_gallery_media_urls.py \
  tests/web_api/test_gallery_comments.py \
  tests/web_api/test_gallery_post_deletion.py \
  tests/web_api/test_gallery_task_type_filters.py
```

### 4.6 修改 Telegram `message_handler` 入口

适用文件：

- `src/handlers/message_handler.py`
- `src/handlers/message_handler_common.py`
- `src/handlers/message_handler_profile.py`
- `src/handlers/message_handler_media.py`
- `src/handlers/message_handler_menu.py`

至少执行：

```bash
pytest \
  tests/handlers/test_message_handler.py \
  tests/handlers/test_message_handler_common.py \
  tests/handlers/test_message_handler_profile.py \
  tests/handlers/test_message_handler_media.py \
  tests/handlers/test_message_handler_menu.py
```

### 4.7 修改前端公共壳层

适用文件：

- `frontend/src/views/Gallery.vue`
- `frontend/src/components/MySubmissionsPanel.vue`
- `frontend/src/components/ListStateBlock.vue`
- `frontend/src/components/template-apply/TemplateApplyWorkbenchHost.vue`
- `frontend/src/router/index.ts`

至少执行：

```bash
cd frontend && pnpm vitest run \
  src/views/Gallery.test.ts \
  src/components/ListStateBlock.test.ts \
  src/components/template-apply/TemplateApplyWorkbenchHost.test.ts \
  src/router/index.test.ts
```

如果改动涉及模板应用或生成工作台状态流，再补：

```bash
cd frontend && pnpm vitest run \
  src/stores/tasksRuntime.test.ts \
  src/stores/taskResultState.test.ts \
  src/stores/templateApply.test.ts \
  src/composables/useTemplateApplyUpload.test.ts \
  src/utils/normalizeTemplateApplyContext.test.ts
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
- 支持 `workflow_dispatch` 手动指定分组，例如 `task-min frontend-shared`
- 根据改动路径自动推导 Python 分组与 Frontend 分组
- 当命中 `task-full` 时，自动去重并跳过被其覆盖的 `task-facade`、`task-min`、`tasks-web`
- 若本次没有识别到热点分组，则以 no-op job 结束，避免 workflow 悬空
- `Hotspot Gate Result` 聚合 job 提供稳定检查名，供 branch protection 配置 required check

## 7. 当前缺口

- `dashboard/frontend/src/App.vue` 已列入热点文件，但当前尚无对应的高价值回归基线
- 前端页面家族已有基础测试，但“详情弹层 + 模板应用 + 列表态切换”的跨页组合回归仍偏少
- 当前门禁已收口到统一脚本和 GitHub Actions workflow，但还没有继续细化到更细粒度的 CI matrix 或强制 branch protection 配置说明

## 8. 阶段 7 第一批收尾标志

满足以下条件时，可认为阶段 7 第一批完成：

- 已形成明确的热点文件清单
- 已形成“改哪类文件就跑哪组测试”的最小规则
- 已把任务主链路回归与非任务热点回归区分开
- 已明确当前仍未覆盖的治理缺口，供下一批继续处理

## 9. 下一批建议

阶段 7 第二批建议只做两件事：

1. 为前端公共页面家族补 1 组更高价值的跨组件回归
2. 把当前 CI workflow 继续细化为更稳的 branch protection / matrix / cache 策略
