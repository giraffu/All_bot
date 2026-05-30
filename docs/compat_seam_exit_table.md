# Compat / Seam 退出表

本表用于跟踪当前仓库内仍保留的兼容层、测试 seam 与过渡导出，避免“知道是历史层但没人敢删”。

## 已在本轮删除

| 对象 | 旧用途 | 依赖方 | 删除前置条件 | 实际动作 |
| --- | --- | --- | --- | --- |
| `src/handlers/fsm/video_lora_fsm.py` | 旧 `video_lora_fsm` 模块的 compat re-export | 仅剩兼容测试 | 调用方与测试退出旧模块路径 | 已删除，统一改走 `image_to_video_fsm.py` |
| `conversation_states.VideoLoraState` | 旧图生视频状态别名 | 仅剩兼容测试 | 所有调用方改用 `ImageToVideoState` | 已删除 |
| `image_to_video_fsm.start_video_lora` / `get_video_lora_fsm_handler` | 旧命名入口别名 | 仅剩兼容测试 | 统一入口改用 `start_image_to_video` / `get_image_to_video_fsm_handler` | 已删除 |
| `src/web_api/routers/users.py:invalidate_affiliate_redeem_cache_after_commit` | 仅为旧 patch 路径保留的 re-export | 旧集成测试 / service patch 习惯 | 相邻测试统一 patch `user_affiliate_redeem_api_service.py` | 已删除，router 不再保留该 re-export |
| `src/services/payment_fulfillment_service.py:LogService` 导入注释 | backward-compatible test patch target | 旧支付履约测试 | 相邻测试改贴 `src.services.log_service.LogService.log_action` | 已删除，支付履约文件不再暴露 compat patch target |
| `src/services/task_service_generation_entrypoints.py` | `TaskService` 到 generation entrypoints 的纯转发壳 | `bot_task_service.py` 旧 facade 调用面 | `bot_task_service.py` 改为直接导入真实 entrypoint，focused tests 改贴公开函数/flow | 已删除，生成/I2I 入口不再经过 compat-only 转发文件 |
| `src/services/task_service_entrypoints.py` | 仅聚合导出 TG task entrypoints 的 compat 壳 | `bot_task_service.py` 旧 facade 调用面 | `bot_task_service.py` 改为直接导入分域 entrypoint 模块 | 已删除，聚合 re-export 不再保留 |
| `src/services/task_service_entrypoints_common.py` | 仅保留 `resolve_internal_user_id(...)` 的薄包装壳 | 多个 TG generation/video entrypoint | 统一改由 `task_service_generation_common.py` 提供共享 helper | 已删除，入口共用 helper 已并回 generation common |
| `frontend/src/composables/useLegacySwapApply.ts` | 旧 swap 页 route apply 兼容壳 | `FaceSwap.vue`、`VideoSwap.vue` | 两个页面直接内联 route apply 初始化，旧壳不再承担中转职责 | 已删除，compat 逻辑已回收到页面 setup |

## 已在本轮下沉的默认装配

| 对象 | 原位置 | 新位置 | 当前状态 |
| --- | --- | --- | --- |
| task_core submission 默认 wrapper | `src/core/task_core.py` | `src/core/task_core_submission.py` | 已下沉，`task_core.py` 仅保留 facade 绑定 |
| task_core finalization 默认 wrapper | `src/core/task_core.py` | `src/core/task_core_finalization.py` | 已下沉，失败/取消默认依赖由子模块自装配 |
| task_core web side-effect / monitor 默认装配 | `src/core/task_core.py` | `src/services/task_web_side_effects.py`、`task_web_lifecycle_monitor.py`、`task_web_terminal_finalization.py` | 已下沉，`task_core.py` 直接绑定 application 层 monitor 实现 |
| task_core warmup/persistence 默认 wrapper | `src/core/task_core.py` | `src/core/task_core_web_history_warmup.py`、`src/core/task_core_persistence.py` | 已下沉，web history warmup 与成功持久化默认绑定不再堆在 facade |
| TG gallery browse 链路 | `src/handlers/callbacks/gallery_callbacks.py` | `src/handlers/callbacks/gallery_callbacks_browse.py` | 已继续收口，分类菜单、`gallery_sort_`、`gallery_page_` 已直接在 browse 子模块注册，旧壳文件已删除 |
| 旧单图页与模板工作台 payload 组装 | 多个 `.vue` 页面内联 | `frontend/src/features/generation/buildGenerationTaskPayload.ts` | 已统一，旧单图页与 A4 工作台共用提交 payload builder |
| swap 双文件页 payload 组装 | `FaceSwap.vue`、`VideoSwap.vue` 与模板面板内联 | `frontend/src/features/generation/buildSwapTaskPayload.ts` | 已统一，页面与模板面板共用 `face_swap/face_video` payload builder |
| swap 双文件页提交 controller | `FaceSwap.vue`、`VideoSwap.vue` 与模板面板各自内联提交 | `frontend/src/composables/useSwapTaskSubmit.ts` | 已统一，四处入口共用校验 + payload + submit + taskId 回写主链 |
| `gallery_core` 默认 provider / side effects | `src/core/gallery_core.py` | `src/core/gallery_core_dependencies.py`、`src/core/gallery_submission_effects.py` | 已下沉，默认装配与投稿 side effects 不再堆在主文件顶部 |
| `run_bot_task_flow(...)` | `src/services/task_service_flow.py` | `run_bot_task_application(...)` | 已删除，Bot entrypoints 现直接构造 `BotTaskFlowContext(request/presentation/billing/failure/cleanup)` 后调用单一真实入口 |
| TG gallery 投稿 / 点赞主链 | `src/handlers/callbacks/gallery_callbacks.py` | `src/handlers/callbacks/gallery_callbacks_interactions.py` | 已继续收口，`public_share`、`rate_*`、`submit_gallery_`、`gallery_like_/gallery_dislike_` 已直接在 interactions 子模块注册，旧壳文件已删除 |
| `Profile.vue` metric 组装 | `frontend/src/views/Profile.vue` | `frontend/src/composables/useProfileMetrics.ts` | 已下沉，统计与返佣卡片数据组装不再堆在页面脚本 |
| `storage.py` R2 exists/cache runtime 细节 | `src/services/storage.py` | `src/services/storage_r2_exists.py` | 已下沉，`StorageService` 主要保留公开方法与薄包装 |
| `Profile.vue` 队列状态块 | `frontend/src/views/Profile.vue` | `frontend/src/components/profile/ProfileQueueStatusPanel.vue` | 已下沉，页面继续回到区块装配层 |
| `storage.py` MinIO bootstrap / presign 细节 | `src/services/storage.py` | `src/services/storage_minio_client.py`、`src/services/storage_presign.py` | 已下沉，bucket name/public client/bucket ensure 与 presign get/put/expiry 不再堆在主文件 |
| `Profile.vue` 欢迎区摘要 / 快捷入口装配 | `frontend/src/views/Profile.vue` | `frontend/src/composables/useProfileWelcomeSummary.ts`、`frontend/src/composables/useProfileQuickActions.ts` | 已下沉，欢迎区与快捷入口的数据/行为编排进一步退出页面脚本 |
| swap 双文件页结果重置 controller | `FaceSwap.vue`、`VideoSwap.vue` 页面内联 | `frontend/src/composables/useSwapResetController.ts` | 已统一，reset 会同步清上传态、taskId、分辨率与模板态/sourcePostId |
| `billing_core` 私有 `_build_*` 测试 seam | `tests/core/test_billing_core.py` patch 私有 builder | `BillingCoreDependencies` 显式注入 | 已迁移，公开函数支持显式 dependencies，测试不再绑定私有 builder |
| `task_core_persistence` 模块内 materialization builder seam | `src/core/task_core_persistence.py` | `persist_successful_task_result(...)` + `task_core_persistence_flow.py` | 已收口，下载/`to_thread` 默认绑定回到公开 persistence 边界与 flow |
| `affiliate_redeem_service` membership 账本/结算混排 | `src/services/affiliate_redeem_service.py` | `_create_membership_redeem_ledger_entry(...)`、`_apply_affiliate_membership_settlement(...)` | 已拆开，主 service 继续保留事务/幂等编排，账本与结算边界更清晰 |
| `gallery_core.py` feed 查询拼装 | `src/core/gallery_core.py` | `src/core/gallery_feed_queries.py` | 已下沉，category/media_type/sort/time_range/page/count 查询拼装不再堆在主文件 |
| `storage.py` MinIO object IO facade | `src/services/storage.py` | `src/services/storage_minio_objects.py` | 已下沉，upload/list/download/object exists 回到独立 helper，主类保留薄代理与兼容签名 |
| `gallery_core.py` 投稿 / 互动主链 | `src/core/gallery_core.py` | `src/core/gallery_submission_core.py`、`src/core/gallery_interactions_core.py`、`src/core/gallery_core_errors.py` | 已下沉，投稿/点赞/apply 计数与错误类型退出主文件，`gallery_core.py` 主要保留 outcome + facade |
| `storage.py` R2 copy / public URL facade | `src/services/storage.py` | `src/services/storage_r2_transfer.py` | 已下沉，MinIO->R2 copy 与 public URL 规则回到独立 helper，主类只保留薄包装 |

## 仍保留的 compat / seam

| 对象 | 当前用途 | 依赖它的调用方或测试 | 删除前置条件 | 预计删除阶段 |
| --- | --- | --- | --- | --- |
| `src/handlers/fsm/image_to_video_fsm.py:start_custom_video` | `/custom_video` 旧入口别名，对外保持稳定命令名 | `/custom_video` 命令、`menu.custom_video` 与 callback `fsm_start_custom_video` | 明确 `/custom_video` 是否长期保留为独立产品入口；若仅是图生视频变体，可与统一入口继续收口 | `D2` 后续轮次 |
| `src/constants.py:MODE_IMAGE_TO_VIDEO = MODE_VIDEO_LORA` | 兼容历史任务类型值，避免旧记录/旧 payload 失配 | 历史任务类型、旧 apply-context、统计与计费链路 | 当前主链已统一补上 `image_to_video` 新主名：dispatcher、API client、image service、backend `/image_to_video` 路由与 FSM 新入口已切到中性命名；旧 `video_lora` 仅保留入口 alias、兼容路由与历史值锚点，后续在数据迁移完成后退出该值别名 | 已压缩到外层兼容 |
| `src/database/models.py:Order.telegram_id` | 历史数据库列名，实际关联 `users.id` 内部用户主键 | 正式环境尚未执行迁移时的遗留 schema 名称 | 测试环境已实际执行 Alembic `7c0a4d5e6f71`，`orders` 物理列已切到 `internal_user_id`，ORM 也已删除 `telegram_id` alias；后续只需在生产切换窗口按同一 migration 执行正式环境升级 | `测试已完成 / 生产待执行` |
| `src/services/order_v2_service.py` 的 `ORDER:` / `ORDER_V2:` 双载荷兼容 | 兼容历史支付回调载荷格式与旧本地单号语义 | 旧支付链路、回调解析与 payment presenter 的 `legacy_order_id` 展示 | 对外查询全面切到 `business_order_id`，旧支付通道不再回传 `ORDER:` 载荷，Dashboard/Web 不再展示旧本地单号为主 ID | `待支付链路收口后` |
| `src/services/user_persistence_service.py` 的 `id == tg_id` legacy adopt 分支 | 兼容早期内部用户主键与 Telegram ID 混用的数据 | 仍存在历史用户记录但缺少 `telegram_id` 的存量数据 | 先确认正式/测试环境中不再存在 `id == tg_id && telegram_id is null` 的用户；随后移除 `_get_legacy_user_by_internal_id(...)` / `_adopt_legacy_internal_user(...)`，并保留 focused tests 作为删除前门禁 | `待数据治理完成后` |

## 删除原则

1. 先迁调用方与测试，再删 compat 导出。
2. 优先让测试 patch helper/service 边界，不再绑定 router 或 façade 私有符号。
3. 删除 compat 后必须补 focused tests，防止回滚式复活。
4. 对 legacy 双 ID 兼容分支，先做数据盘点与 focused tests，再删代码；不要在新增链路里继续把 compat 分支当成主路径。
