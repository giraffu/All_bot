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
| `frontend/src/composables/useLegacySwapApply.ts` | 旧 swap 页 route apply 兼容壳 | 旧 swap 独立页面 | swap 能力统一进入练功房与模板应用链路，旧壳不再承担中转职责 | 已删除，compat 逻辑已回收到统一入口 |
| `src/web_api/routers/utils.py` | 仅为测试 patch 路径保留的 Web router re-export 壳 | `tests/web_api/test_router_utils.py` | 测试改贴 `src.web_api.common.utils` 公开边界 | 已删除，router 不再承接工具符号 re-export |
| `src/web_api/services/users_history_service.py:pick_history_media_urls` | 仅测试引用的历史媒体 URL 转发 helper | `tests/web_api/test_users_history_urls.py` | 相邻测试直接覆盖 `media_presenter.resolve_history_media_urls(...)` | 已删除，用户历史 service 不再保留 test-only helper |
| `frontend/src/utils/templateApplyEntry.ts:buildLegacyTemplateRoute` | 旧模板应用 legacy route builder | 无业务调用 | 主站模板应用已统一走 workbench / store 解析链 | 已删除，入口解析文件只保留真实主链 |
| `frontend/src/components/SiteNoticeCenterModal.vue:previewContent` | 未使用的公告预览 helper | 无调用方 | 公告中心改为仅保留标题裁剪与正文全量展示 | 已删除，公告弹窗不再保留死代码 |
| `src/services/task_service_message_support.py:translate_context_text` 的 `TypeError` 兼容分支 | 兼容旧单参 translator 与测试 double | `tests/services/test_task_service_message_support.py` 旧单参桩 | 测试桩与运行时 translator 统一成 `translator(key, **kwargs)` 协议 | 已删除，生产代码不再为测试 double 吞异常 |
| `src/web_api/services/users_history_service.py` 的 `resolve_history_media_urls` / `build_input_file_url` / `probe_media_metadata` 注入参数 | 公开 service 为测试 patch 暴露的 seam | `tests/web_api/test_users_apply_context.py` | 相邻测试改贴 `history_response_builder` 与 module-level helper | 已删除，公开 service 只保留业务参数 |
| `src/web_api/services/history_response_builder.py` 的 `resolve_history_media_urls_func` 注入参数 | 仅供测试替换媒体 URL resolver | `tests/web_api/test_history_response_builder.py`、`tests/web_api/test_users_apply_context.py` | 相邻测试直接 patch 模块级 `resolve_history_media_urls(...)` | 已删除，builder 不再暴露 test-only 注入参数 |
| `src/web_api/common/__init__.py` | 纯 re-export 包壳 | 无业务引用 | 仓库内调用方均直接引用 `src.web_api.common.utils` | 已删除，`common` 包不再保留空壳入口 |
| `src/core/task_core_service_providers.py` 中未调用的 getter wrapper | 历史 provider 细粒度透传符号 | 无业务引用 | 全仓确认无静态调用方 | 已删除，保留真实 capability builder 与运行时入口 |
| `src/context.py:trace_id_ctx` | 旧 trace context 变量 | 无业务引用；实际 trace 语义使用 `asgi_correlation_id.correlation_id` | `rg "trace_id_ctx"` 确认无动态引用 | 已删除，保留正在使用的 `user_id_ctx` |

## 已在本轮下沉的默认装配

| 对象 | 原位置 | 新位置 | 当前状态 |
| --- | --- | --- | --- |
| task_core submission 默认 wrapper | `src/core/task_core.py` | `src/core/task_core_submission.py` | 已下沉，`task_core.py` 仅保留 facade 绑定 |
| task_core finalization 默认 wrapper | `src/core/task_core.py` | `src/core/task_core_finalization.py` | 已下沉，失败/取消默认依赖由子模块自装配 |
| task_core web side-effect / monitor 默认装配 | `src/core/task_core.py` | `src/services/task_web_side_effects.py`、`task_web_lifecycle_monitor.py`、`task_web_terminal_finalization.py` | 已下沉，`task_core.py` 直接绑定 application 层 monitor 实现 |
| task_core warmup/persistence 默认 wrapper | `src/core/task_core.py` | `src/core/task_core_web_history_warmup.py`、`src/core/task_core_persistence.py` | 已下沉，web history warmup 与成功持久化默认绑定不再堆在 facade |
| TG gallery browse 链路 | `src/handlers/callbacks/gallery_callbacks.py` | `src/handlers/callbacks/gallery_callbacks_browse.py` | 已继续收口，分类菜单、`gallery_sort_`、`gallery_page_` 已直接在 browse 子模块注册，旧壳文件已删除 |
| 旧单图页与模板工作台 payload 组装 | 多个旧生成 `.vue` 页面内联 | `frontend/src/features/generation/buildGenerationTaskPayload.ts` | 已统一，旧生成 URL 进入 `CustomFeatures.vue` 后复用同一套提交 payload builder |
| swap 双文件页 payload 组装 | 旧 swap 独立页面与模板面板内联 | `frontend/src/features/generation/buildSwapTaskPayload.ts` | 已统一，统一工作台与模板面板共用 `face_swap/face_video` payload builder |
| swap 双文件页提交 controller | 旧 swap 独立页面与模板面板各自内联提交 | `frontend/src/composables/useSwapTaskSubmit.ts` | 已统一，统一工作台与模板面板共用校验 + payload + submit + taskId 回写主链 |
| `gallery_core` 默认 provider / side effects | `src/core/gallery_core.py` | `src/core/gallery_core_dependencies.py`、`src/core/gallery_submission_effects.py` | 已下沉，默认装配与投稿 side effects 不再堆在主文件顶部 |
| `user_core` 的默认持久化绑定 | `src/core/user_core.py` | `src/core/user_core_bindings.py` | 已下沉，`user_core.py` 仅保留稳定 facade 与 binding 解析 |
| `gallery_submission_core` / `gallery_interactions_core` 的 repository 默认绑定 | `src/core/gallery_submission_core.py`、`src/core/gallery_interactions_core.py` | `src/core/gallery_core_dependencies.py` | 已下沉，投稿/互动主链改走显式 dependencies，不再在子模块顶部直连 repository |
| task core runtime process 默认装配 | `src/core/task_core_default_dependencies.py` | `src/task_core_process_defaults.py` + input/billing/submission/side-effect builder | 已下沉，runtime-specific billing / strategy / web side-effect 装配退出热点 core builder，聚合入口按四组 builder 组合 |
| `run_bot_task_flow(...)` | `src/services/task_service_flow.py` | `run_bot_task_application(...)` | 已删除，Bot entrypoints 现直接构造 `BotTaskFlowContext(request/presentation/billing/failure/cleanup)` 后调用单一真实入口 |
| TG gallery 投稿 / 点赞主链 | `src/handlers/callbacks/gallery_callbacks.py` | `src/handlers/callbacks/gallery_callbacks_interactions.py` | 已继续收口，`public_share`、`rate_*`、`submit_gallery_`、`gallery_like_/gallery_dislike_` 已直接在 interactions 子模块注册，旧壳文件已删除 |
| `Profile.vue` metric 组装 | `frontend/src/views/Profile.vue` | `frontend/src/composables/useProfileMetrics.ts` | 已下沉，统计与返佣卡片数据组装不再堆在页面脚本 |
| `storage.py` R2 exists/cache runtime 细节 | `src/services/storage.py` | `src/services/storage_r2_exists.py` | 已下沉，`StorageService` 主要保留公开方法与薄包装 |
| `Profile.vue` 队列状态块 | `frontend/src/views/Profile.vue` | `frontend/src/components/profile/ProfileQueueStatusPanel.vue` | 已下沉，页面继续回到区块装配层 |
| `storage.py` MinIO bootstrap / presign 细节 | `src/services/storage.py` | `src/services/storage_minio_client.py`、`src/services/storage_presign.py` | 已下沉，bucket name/public client/bucket ensure 与 presign get/put/expiry 不再堆在主文件 |
| `Profile.vue` 欢迎区摘要 / 快捷入口装配 | `frontend/src/views/Profile.vue` | `frontend/src/composables/useProfileWelcomeSummary.ts`、`frontend/src/composables/useProfileQuickActions.ts` | 已下沉，欢迎区与快捷入口的数据/行为编排进一步退出页面脚本 |
| swap 双文件页结果重置 controller | 旧 swap 页面内联 | `frontend/src/composables/useSwapResetController.ts` | 已统一，reset 会同步清上传态、taskId、分辨率与模板态/sourcePostId |
| `billing_core` 私有 `_build_*` 测试 seam | `tests/core/test_billing_core.py` patch 私有 builder | `BillingCoreDependencies` 显式注入 | 已迁移，公开函数支持显式 dependencies，测试不再绑定私有 builder |
| `task_core_persistence` 模块内 materialization builder seam | `src/core/task_core_persistence.py` | `TaskSuccessPersistenceCommand` + `persist_successful_task_result_command(...)` + `task_core_persistence_flow.py` | 已收口，旧 `persist_successful_task_result(...)` 仅保留兼容包装，下载/`to_thread` 默认绑定回到公开 persistence 边界与 flow |
| `affiliate_redeem_service` membership 账本/结算混排 | `src/services/affiliate_redeem_service.py` | `_create_membership_redeem_ledger_entry(...)`、`_apply_affiliate_membership_settlement(...)` | 已拆开，主 service 继续保留事务/幂等编排，账本与结算边界更清晰 |
| `gallery_core.py` feed 查询拼装 | `src/core/gallery_core.py` | `src/services/gallery_feed_queries.py` | 已下沉到 service 层，旧 `src/core/gallery_feed_queries.py` 兼容 re-export 已删除；category/media_type/sort/time_range/page/count 查询拼装不再堆在 core 主文件 |
| `storage.py` MinIO object IO facade | `src/services/storage.py` | `src/services/storage_minio_objects.py` | 已下沉，upload/list/download/object exists 回到独立 helper，主类保留薄代理与兼容签名 |
| `gallery_core.py` 投稿 / 互动主链 | `src/core/gallery_core.py` | `src/core/gallery_submission_core.py`、`src/core/gallery_interactions_core.py`、`src/core/gallery_core_errors.py` | 已下沉，投稿/点赞/apply 计数与错误类型退出主文件，`gallery_core.py` 主要保留 outcome + facade |
| `storage.py` R2 copy / public URL facade | `src/services/storage.py` | `src/services/storage_r2_transfer.py` | 已下沉，MinIO->R2 copy 与 public URL 规则回到独立 helper，主类只保留薄包装 |
| 我的库收藏/投稿重复浏览链路 | `frontend/src/views/MyFavorites.vue`、`frontend/src/components/MySubmissionsPanel.vue` | `frontend/src/composables/useMyLibraryPostBrowser.ts` | 已收口，分页、详情、评论、互动、模板应用共享浏览组合退出页面内重复拼装 |

## 仍保留的 compat / seam

| 对象 | 当前用途 | 依赖它的调用方或测试 | 删除前置条件 | 预计删除阶段 |
| --- | --- | --- | --- | --- |
| `src/handlers/fsm/image_to_video_fsm.py:start_custom_video` | `/custom_video` 旧入口别名，对外保持稳定命令名 | `/custom_video` 命令、`menu.custom_video` 与 callback `fsm_start_custom_video` | 明确 `/custom_video` 是否长期保留为独立产品入口；若仅是图生视频变体，可与统一入口继续收口 | `D2` 后续轮次 |
| `src/constants.py:MODE_IMAGE_TO_VIDEO = MODE_VIDEO_LORA` | 兼容历史任务类型值，避免旧记录/旧 payload 失配 | 历史任务类型、旧 apply-context、统计与计费链路 | 当前主链已统一补上 `image_to_video` 新主名：dispatcher、API client、image service、backend `/image_to_video` 路由与 FSM 新入口已切到中性命名；旧 `video_lora` 仅保留入口 alias、兼容路由与历史值锚点，后续在数据迁移完成后退出该值别名 | 已压缩到外层兼容 |
| QQCC Wan22 `lora_items` 对 `lora_name` / `lora_strength` 与旧七模型名的兼容回退 | 让升级前官方/私有 QQCC scene checkpoint、任务 payload 与 continuation context 可迁移到最多 5 项的稳定模型键协议 | `src/qqcc_video_lora_catalog.py`、QQCC config/quick submission、Central 请求模型/API client/ImageService、Wan22 context 与本地/远端 worker patcher | 官方和私有 QQCC 存量配置已完成持久化迁移，受支持客户端只发送 `lora_items`，队列/History/continuation 观测窗口内不再出现单模型字段或旧七模型名；删除时同时移除请求模型和 worker 的单模型 fallback | `配置迁移及历史任务观察完成后` |
| `video_insert` / `video_edit` 任务类型 | legacy Central/Worker alias；旧 endpoint 或旧队列残留会归一到 `image_to_video` 执行 | `src/core/task_execution_types.py`、`src/domain_config/wan22_aio_video.py`、`backend/app/main_simple_task_routes.py`、Worker `mappings.json` 与 `TASK_SPECIFIC_PATCHERS` | 正式/测试队列不再出现这两个 backend task type，旧 endpoint 调用方已下线，worker `SUPPORTED_TASK_TYPES` 可只保留 canonical `image_to_video` | `待队列与旧入口观测清零后` |
| `src/database/models.py:Order.telegram_id` | 历史数据库列名，实际关联 `users.id` 内部用户主键 | 正式环境尚未执行迁移时的遗留 schema 名称 | 测试环境已实际执行 Alembic `7c0a4d5e6f71`，`orders` 物理列已切到 `internal_user_id`，ORM 也已删除 `telegram_id` alias；后续只需在生产切换窗口按同一 migration 执行正式环境升级 | `测试已完成 / 生产待执行` |
| `src/services/order_v2_service.py` 的 `ORDER:` / `ORDER_V2:` 双载荷兼容 | 兼容历史支付回调载荷格式与旧本地单号语义 | 旧支付链路、回调解析与 payment presenter 的 `legacy_order_id` 展示 | 对外查询全面切到 `business_order_id`，旧支付通道不再回传 `ORDER:` 载荷，Dashboard/Web 不再展示旧本地单号为主 ID | `待支付链路收口后` |
| `src/services/user_persistence_service.py` 的 `id == tg_id` legacy adopt 分支 | 兼容早期内部用户主键与 Telegram ID 混用的数据 | 仍存在历史用户记录但缺少 `telegram_id` 的存量数据 | 先确认正式/测试环境中不再存在 `id == tg_id && telegram_id is null` 的用户；随后移除 `_get_legacy_user_by_internal_id(...)` / `_adopt_legacy_internal_user(...)`，并保留 focused tests 作为删除前门禁 | `待数据治理完成后` |
| `src/core/gallery_feed_queries.py` | `src.services.gallery_feed_queries` 的单行 re-export | 静态引用已清零，gallery focused tests 已通过 | 已删除；后续只保留 `src/services/gallery_feed_queries.py` 事实源 | `已删除` |
| `src/services/wan22_video_v2_config.py` | `src.domain_config.wan22_aio_video` 的兼容 re-export | 生产与测试引用已迁到 `src.domain_config.wan22_aio_video` | 已删除；继续保持 `custom_video/video_lora` 与 `wan22_video_v2` 的公开类型语义不变 | `已删除` |
| `src/services/wan22_video_v2_context.py` | Wan22 chain context helper 的兼容 re-export | Wan22 extension service 已迁到 `src.domain_config.wan22_aio_video` | 已删除；Wan22 链路 focused tests 已通过 | `已删除` |
| `backend/workflows/*` 与 `workers/comfy_agent/workflows/*` 双目录 workflow 资产 | 已退出：`backend/workflows` 删除，Central API 不再挂载、COPY 或启动校验 workflow | Worker 镜像与运行时 workflow 选择链路 | 后续 workflow 只维护 `workers/comfy_agent/workflows`；新增 task type 仍需同步 `TASK_TYPE_WORKFLOW_FILENAMES`、`mappings.json` 与目标 Worker `SUPPORTED_TASK_TYPES` | `已收口` |
| Gallery 查询类型 `free_edit_v2_group` | 旧 Web/客户端查询别名，服务端与前端均归一到 `free_edit_v3_group`，覆盖 v3 BF16 与历史 single/multi v2 投稿 | 升级前客户端可能仍发送旧 group；历史 History 类型本身不迁移 | 先观察测试/正式访问日志确认旧 group 请求清零，并确保所有受支持 Web 版本只发送 `free_edit_v3_group`；仅删除查询别名，不改历史 History 数据 | `完成客户端观察后` |
| QQCC Config `main_menu_layout.buttons_per_row=null` / 前端 `legacy` 布局哨兵 | 兼容没有主菜单布局字段的官方与私有 Bot checkpoint；配置 Web 用 `legacy` 表示“沿用现有布局”，保存时仍归一为 `null`，运行时继续使用旧固定分行 | `src/services/qqcc_config_service.py`、`qqcc_bot/keyboards.py`、`dashboard/frontend/src/components/QqccBotSettings.vue` 与 QQCC/Config focused tests | 先把仍受支持的官方 checkpoint 与私有 Bot 配置迁移为显式 `1..4` 列，确认配置 Web 不再需要“沿用现有布局”且历史固定分行观察窗口结束；随后删除前端哨兵、`null` 分支及对应回归测试 | `配置迁移与历史布局观察完成后` |
| `free_edit_v2_5` 到 BF16 单/双图内部执行类型的动态 alias | 对外保留独立逻辑类型与 History；单图 3 灵石映射 `pornmaster_flux2_edit_bf16`，双图 7 灵石映射 `pornmaster_flux2_multi_edit_bf16`，对内复用 BF16 执行池 | task registry、dispatcher、Central simple route、Worker mapping/patcher 与共享 BF16 profile | 只有 Central/Worker 未来原生支持独立 v2.5 执行类型，且 workflow/profile 不再共享时才删除；删除前需完成队列、结果回流与退款链路迁移 | `共享执行池期间长期保留` |
| Bot callback `editlora_free_edit_v2` | 兼容升级前已发送键盘；点击后继续进入自由P图 v3，两阶段语义不变 | Telegram 客户端中仍可点击的历史消息键盘 | 发布后经过历史键盘最大观察窗口，并确认 callback 日志不再出现旧值；新键盘只发送 `editlora_free_edit_v2_5` 或当前 v3 入口值 | `旧键盘流量清零后` |
| `scripts/release.py` 的 legacy 无 track 发布合约回退与 `--dashboard-fast-track` 参数别名 | 允许 control-plane 回滚到 track 隔离上线前的历史 SHA，并兼容旧 Dashboard 发布调用方；新候选仍只写 track-scoped 合约，旧参数只映射到 `--strategy direct` | 历史 release state / rollback journal、尚未迁移的运维调用脚本 | 所有可回滚历史候选都已重新生成 track-scoped `release.env`，且仓库与外部运维入口不再传 `--dashboard-fast-track`；删除前须覆盖 preflight、失败恢复和恢复验证回归 | `历史回滚窗口与旧调用方同时清零后` |
| `test_train_release.py` candidate/freeze/approval 与 promoted bundle reader | main-first 生效前的候选、批准记录和 production rollback 仍需取证；新批次不得再创建 candidate、freeze、approval 或 promotion | 历史 main/promoted bundle、acceptance history、release rollback/recover | 所有受支持的正式回滚点都已有 main-channel bundle 与逐 artifact history，审计保留期结束，且生产 state 不再引用 promoted/candidate channel；删除前保留历史证据离线归档与读取回归 | `main-first 历史回滚及审计保留期结束后` |
| `migrate_legacy_test_env.py --control-plane-only` 的 `_TEST` 到 canonical key 迁移表 | 仅在云测试首次逐服务投影切换时，从同一 `/etc/allbot/test.env` 内的旧别名补齐严格运行键；已有 canonical 值永远优先，不参与日常加载 | 尚未完成配置契约首次收敛的云测试 env；旧容器回滚窗口仍需保留原 `_TEST` 键 | 测试环境的 canonical 逐服务投影已激活，回滚演练完成，且受支持回滚点不再需要旧 `_TEST` 键；删除迁移表前保留缺 canonical key 必须失败的回归 | `云测试首次配置收敛与历史回滚窗口结束后` |
| `safe_deploy_cloud_test.sh`、`safe_deploy_cloud_prod.sh` 与旧维护更新脚本 | 对旧现场 build/rsync 操作 fail closed，给仍在外部调用的旧入口返回明确迁移错误，不再执行部署 | 尚未迁移的人工 runbook、定时任务或 shell 调用方 | 只读审计确认所有外部调用已改为 `release.py` main-bundle/config 接口，并经过至少一个完整发布观察窗口；随后删除壳脚本及对应拒绝回归 | `外部调用清零并完成一个发布观察窗口后` |
| 用户可见 task type / operation 的 legacy alias 展示归一层 | 把 registry 历史 alias、执行阶段类型及旧账本 operation 归一到稳定 `display_key`，避免 Web/Bot 向用户泄漏内部原始值 | Web 历史、任务详情、用户主页、Gallery、Bot 结果与灵石流水展示 | 历史数据迁移为稳定公开类型，所有在支持期内的客户端只消费公开展示 key，并确认旧 alias/operation 观测清零；Dashboard 与协议诊断值不随展示层删除 | `历史数据迁移和客户端观察完成后` |

## 冗余清理候选

| 对象 | 当前状态 | 清理前置条件 | 建议动作 |
| --- | --- | --- | --- |
| 暂无 | 本轮已完成 `trace_id_ctx` 清理 | 后续静态扫描发现新候选再补充 | 保持本表同步 |

## 保留观察

| 对象 | 当前判断 | 继续保留条件 | 后续动作 |
| --- | --- | --- | --- |
| `backend/app/main_t2i_wiring.py` | 当前仍有“集中 callable 装配 + 降低 main.py 噪音”的边界价值 | `main.py` 仍需维持薄入口，且同一套 wiring 可能继续服务更多 simple task route | 若后续仅剩单入口且 helper 稳定，可评估并回 `main.py` 或更通用 wiring 层 |
| `frontend/src/components/PostBrowserShell.vue` | 仍有列表态壳层价值，不建议删除 | 继续只承接 header/slot/list-state 壳层职责，不承接业务数据逻辑 | 若后续再出现条件分支膨胀，优先拆 slot 协议而不是内联回页面 |
| `frontend/src/views/CustomFeatures.vue` | 统一练功房入口，承接旧生成 URL 重定向后的模式选择与提交编排 | 继续通过 `labModeConfig` / payload builder / workbench composable 分担模式配置、payload 与状态职责 | 若再出现第二套 Web 生成工作台，先扩展模式配置或抽公共 primitives，不恢复旧独立页面 |

## 删除原则

1. 先迁调用方与测试，再删 compat 导出。
2. 优先让测试 patch helper/service 边界，不再绑定 router 或 façade 私有符号。
3. 删除 compat 后必须补 focused tests，防止回滚式复活。
4. 对 legacy 双 ID 兼容分支，先做数据盘点与 focused tests，再删代码；不要在新增链路里继续把 compat 分支当成主路径。
5. 新增 `compat` / `legacy` / `alias` 标记时，必须同步更新本表，至少写明“删除前置条件”和“预计删除阶段”。
