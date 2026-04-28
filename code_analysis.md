# 系统代码全面静态分析与质量评估报告

**生成时间**: 2026-04-28 20:20:24

## 1. 量化指标
- **总代码行数 (Python)**: 18448
- **总发现问题数**: 279
- **平均圈复杂度 (Radon)**: A (4.400606980273142)
- **死代码比例 (预估)**: 1.04% (191 处)
- **代码重复率 (预估)**: 0.33%

- **Code Duplication**: 6 处
- **Code Smell**: 82 处
- **Dead Code**: 191 处

## 2. 架构问题与重构建议
1. **依赖反转与核心层隔离**：`/src/core/` 目录中的代码发现有直接调用 FastAPI/Telegram 对象的倾向，建议通过接口或内部模型（如 `internal_user_id`）进行解耦。
2. **过长函数与上帝对象**：部分服务类（如 `stats.py`, `task_core.py`）方法过多、圈复杂度偏高（>15），违反单一职责原则，建议通过 Facade 模式或提取特定功能的服务类进行拆分。
3. **同步阻塞调用风险**：在异步事件循环中存在使用同步 I/O 或阻塞操作的潜在风险，必须完全替换为 `aiohttp` 和 `asyncio.sleep` 以防堵塞主线程。
4. **代码重复问题**：一些 `skill` 文件和数据模型之间存在明显的代码复制粘贴现象，可以通过继承、组合或提取公共模块（Utility functions）进行合并优化。

## 3. 问题详情列表

| 优先级 | 问题类型 | 文件路径 | 行号 | 问题描述 |
| --- | --- | --- | --- | --- |
| High | Code Duplication | `cs_bot/skills/system_status_skill.py` | 1 | Similar lines in 2 files |
| High | Code Duplication | `cs_bot/skills/system_status_skill.py` | 1 | Similar lines in 2 files |
| High | Code Duplication | `cs_bot/skills/system_status_skill.py` | 1 | Similar lines in 2 files |
| High | Code Duplication | `cs_bot/skills/system_status_skill.py` | 1 | Similar lines in 2 files |
| High | Code Duplication | `cs_bot/skills/system_status_skill.py` | 1 | Similar lines in 2 files |
| High | Code Duplication | `cs_bot/skills/system_status_skill.py` | 1 | Similar lines in 2 files |
| Medium | Code Smell | `backend/app/main.py` | 215 | Too many local variables (22/15) |
| Medium | Code Smell | `backend/app/main.py` | 215 | Too many statements (64/50) |
| Medium | Code Smell | `cs_bot/bot.py` | 104 | Too many local variables (22/15) |
| Medium | Code Smell | `cs_bot/bot.py` | 104 | Too many branches (18/12) |
| Medium | Code Smell | `cs_bot/bot.py` | 104 | Too many statements (57/50) |
| Medium | Code Smell | `cs_bot/bot.py` | 221 | Too many branches (13/12) |
| Medium | Code Smell | `cs_bot/db.py` | 38 | Too many arguments (8/5) |
| Medium | Code Smell | `dashboard/backend/routers/gallery.py` | 24 | Too many arguments (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/history.py` | 18 | Too many arguments (7/5) |
| Medium | Code Smell | `dashboard/backend/routers/history.py` | 18 | Too many local variables (23/15) |
| Medium | Code Smell | `dashboard/backend/routers/history.py` | 18 | Too many branches (13/12) |
| Medium | Code Smell | `dashboard/backend/routers/logs.py` | 14 | Too many arguments (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/plans.py` | 88 | Too many arguments (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/plans.py` | 88 | Too many local variables (17/15) |
| Medium | Code Smell | `dashboard/backend/routers/referrals.py` | 16 | Too many local variables (27/15) |
| Medium | Code Smell | `dashboard/backend/routers/referrals.py` | 16 | Too many statements (57/50) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 73 | Too many local variables (126/15) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 73 | Too many branches (46/12) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 73 | Too many statements (208/50) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 365 | Too many nested blocks (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 470 | Too many local variables (25/15) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 470 | Too many branches (20/12) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 470 | Too many statements (63/50) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 472 | Too many nested blocks (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 566 | Too many local variables (25/15) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 566 | Too many branches (18/12) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 566 | Too many statements (60/50) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 568 | Too many nested blocks (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 730 | Too many local variables (93/15) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 730 | Too many branches (47/12) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 730 | Too many statements (195/50) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 732 | Too many nested blocks (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/stats.py` | 732 | Too many nested blocks (6/5) |
| Medium | Code Smell | `dashboard/backend/routers/system.py` | 153 | Too many local variables (19/15) |
| Medium | Code Smell | `dashboard/backend/routers/system.py` | 153 | Too many branches (19/12) |
| Medium | Code Smell | `dashboard/backend/routers/system.py` | 153 | Too many statements (56/50) |
| Medium | Code Smell | `dashboard/backend/routers/users.py` | 229 | Too many local variables (18/15) |
| Medium | Code Smell | `dashboard/backend/services/worker_listener.py` | 49 | Too many local variables (29/15) |
| Medium | Code Smell | `dashboard/backend/services/worker_listener.py` | 49 | Too many branches (17/12) |
| Medium | Code Smell | `dashboard/backend/services/worker_listener.py` | 49 | Too many statements (65/50) |
| Medium | Code Smell | `src/api_client.py` | 80 | Too many arguments (8/5) |
| Medium | Code Smell | `src/api_client.py` | 100 | Too many arguments (8/5) |
| Medium | Code Smell | `src/api_client.py` | 119 | Too many arguments (9/5) |
| Medium | Code Smell | `src/api_client.py` | 140 | Too many arguments (6/5) |
| Medium | Code Smell | `src/api_client.py` | 168 | Too many arguments (8/5) |
| Medium | Code Smell | `src/api_client.py` | 218 | Too many arguments (7/5) |
| Medium | Code Smell | `src/api_client.py` | 240 | Too many arguments (6/5) |
| Medium | Code Smell | `src/api_client.py` | 257 | Too many arguments (8/5) |
| Medium | Code Smell | `src/api_client.py` | 308 | Too many local variables (17/15) |
| Medium | Code Smell | `src/api_client.py` | 308 | Too many branches (23/12) |
| Medium | Code Smell | `src/api_client.py` | 308 | Too many statements (78/50) |
| Medium | Code Smell | `src/bot_test.py` | 42 | Too many arguments (6/5) |
| Medium | Code Smell | `src/bot_test.py` | 127 | Too many local variables (20/15) |
| Medium | Code Smell | `src/bot_test.py` | 127 | Too many statements (52/50) |
| Medium | Code Smell | `src/constants.py` | 170 | Too many local variables (23/15) |
| Medium | Code Smell | `src/core/billing_core.py` | 79 | Too many local variables (16/15) |
| Medium | Code Smell | `src/core/gallery_core.py` | 49 | Too many arguments (6/5) |
| Medium | Code Smell | `src/core/gallery_core.py` | 49 | Too many local variables (28/15) |
| Medium | Code Smell | `src/core/gallery_core.py` | 49 | Too many branches (13/12) |
| Medium | Code Smell | `src/core/gallery_core.py` | 49 | Too many statements (53/50) |
| Medium | Code Smell | `src/core/gallery_core.py` | 214 | Too many arguments (10/5) |
| Medium | Code Smell | `src/core/gallery_core.py` | 214 | Too many local variables (22/15) |
| Medium | Code Smell | `src/core/gallery_core.py` | 214 | Too many branches (20/12) |
| Medium | Code Smell | `src/core/gallery_core.py` | 214 | Too many statements (57/50) |
| Medium | Code Smell | `src/core/task_core.py` | 50 | Too many arguments (9/5) |
| Medium | Code Smell | `src/core/task_core.py` | 50 | Too many local variables (19/15) |
| Medium | Code Smell | `src/core/task_core.py` | 109 | Too many arguments (10/5) |
| Medium | Code Smell | `src/core/task_core.py` | 109 | Too many local variables (47/15) |
| Medium | Code Smell | `src/core/task_core.py` | 109 | Too many branches (28/12) |
| Medium | Code Smell | `src/core/task_core.py` | 109 | Too many statements (103/50) |
| Medium | Code Smell | `src/core/task_dispatcher.py` | 148 | Too many local variables (18/15) |
| Medium | Code Smell | `src/core/task_dispatcher.py` | 148 | Too many branches (14/12) |
| Medium | Code Smell | `src/core/user_facade.py` | 22 | Too many local variables (22/15) |
| Medium | Code Smell | `src/logger.py` | 108 | Too many arguments (8/5) |
| Medium | Code Smell | `src/web_api/dependencies.py` | 30 | Too many local variables (17/15) |
| Medium | Code Smell | `src/web_api/routers/gallery.py` | 82 | Too many local variables (21/15) |
| Medium | Code Smell | `src/web_api/routers/gallery.py` | 150 | Too many arguments (8/5) |
| Medium | Code Smell | `src/web_api/routers/tasks.py` | 76 | Too many statements (118/50) |
| Medium | Code Smell | `src/web_api/routers/tasks.py` | 94 | Too many local variables (23/15) |
| Medium | Code Smell | `src/web_api/routers/tasks.py` | 94 | Too many branches (29/12) |
| Medium | Code Smell | `src/web_api/routers/tasks.py` | 94 | Too many statements (111/50) |
| Medium | Code Smell | `src/web_api/routers/tasks.py` | 208 | Too many nested blocks (6/5) |
| Low | Dead Code | `backend/app/config.py` | 10 | unused variable 'workflows_dir' |
| Low | Dead Code | `backend/app/config.py` | 22 | unused variable 'model_config' |
| Low | Dead Code | `backend/app/main.py` | 104 | unused function 'create_img2img_task' |
| Low | Dead Code | `backend/app/main.py` | 116 | unused function 'create_img2img_lora_task' |
| Low | Dead Code | `backend/app/main.py` | 128 | unused function 'create_face_swap_task' |
| Low | Dead Code | `backend/app/main.py` | 140 | unused function 'create_video_insert_task' |
| Low | Dead Code | `backend/app/main.py` | 152 | unused function 'create_video_edit_task' |
| Low | Dead Code | `backend/app/main.py` | 164 | unused function 'create_video_lora_task' |
| Low | Dead Code | `backend/app/main.py` | 178 | unused function 'create_face_video_task' |
| Low | Dead Code | `backend/app/main.py` | 190 | unused function 'create_i2i_pro_task' |
| Low | Dead Code | `backend/app/main.py` | 202 | unused function 'create_ltx_video_task' |
| Low | Dead Code | `backend/app/main.py` | 214 | unused function 'create_t2i_pornmaster_turbo_task' |
| Low | Dead Code | `backend/app/main.py` | 317 | unused function 'get_task_status_v1' |
| Low | Dead Code | `backend/app/main.py` | 377 | unused function 'get_task_image' |
| Low | Dead Code | `backend/app/main.py` | 414 | unused function 'get_task_video' |
| Low | Dead Code | `backend/app/main.py` | 449 | unused function 'get_system_workers' |
| Low | Dead Code | `backend/app/models.py` | 45 | unused variable 'last_seen' |
| Low | Dead Code | `backend/app/models.py` | 47 | unused variable 'current_task_type' |
| Low | Dead Code | `backend/app/models.py` | 48 | unused variable 'current_task_progress' |
| Low | Dead Code | `backend/app/models.py` | 49 | unused variable 'current_task_created_at' |
| Low | Dead Code | `backend/app/models.py` | 63 | unused variable 'image' |
| Low | Dead Code | `backend/app/models.py` | 64 | unused variable 'image2' |
| Low | Dead Code | `backend/app/models.py` | 68 | unused variable 'num_inference_steps' |
| Low | Dead Code | `backend/app/models.py` | 69 | unused variable 'guidance_scale' |
| Low | Dead Code | `backend/app/models.py` | 75 | unused variable 'image' |
| Low | Dead Code | `backend/app/models.py` | 76 | unused variable 'image2' |
| Low | Dead Code | `backend/app/models.py` | 80 | unused variable 'num_inference_steps' |
| Low | Dead Code | `backend/app/models.py` | 81 | unused variable 'guidance_scale' |
| Low | Dead Code | `backend/app/models.py` | 89 | unused variable 'face_image' |
| Low | Dead Code | `backend/app/models.py` | 90 | unused variable 'body_image' |
| Low | Dead Code | `backend/app/models.py` | 95 | unused variable 'image' |
| Low | Dead Code | `backend/app/models.py` | 104 | unused variable 'image' |
| Low | Dead Code | `backend/app/models.py` | 113 | unused variable 'image' |
| Low | Dead Code | `backend/app/models.py` | 123 | unused variable 'face_image' |
| Low | Dead Code | `backend/app/models.py` | 131 | unused variable 'image' |
| Low | Dead Code | `backend/app/models.py` | 138 | unused variable 'image' |
| Low | Dead Code | `backend/app/queue_manager.py` | 115 | unused method 'get_task_by_prompt_id' |
| Low | Dead Code | `backend/app/queue_manager.py` | 253 | unused method 'clear_running_tasks' |
| Low | Dead Code | `backend/app/routers/agent.py` | 55 | unused function 'pop_task' |
| Low | Dead Code | `backend/app/routers/agent.py` | 77 | unused function 'check_task' |
| Low | Dead Code | `backend/app/routers/agent.py` | 88 | unused function 'update_status' |
| Low | Dead Code | `backend/app/routers/agent.py` | 120 | unused function 'task_heartbeat' |
| Low | Dead Code | `backend/app/routers/agent.py` | 132 | unused function 'heartbeat' |
| Low | Dead Code | `backend/tests/conftest.py` | 12 | unused function 'fixture_mock_queue_manager' |
| Low | Dead Code | `backend/tests/test_t2i_pornmaster.py` | 27 | unused attribute 'side_effect' |
| Low | Dead Code | `backend/tests/test_t2i_pornmaster.py` | 37 | unused attribute 'side_effect' |
| Low | Dead Code | `backend/tests/test_t2i_pornmaster.py` | 89 | unused attribute 'side_effect' |
| Low | Dead Code | `backend/tests/test_t2i_pornmaster.py` | 112 | unused attribute 'side_effect' |
| Low | Dead Code | `backend/tests/test_t2i_pornmaster.py` | 155 | unused attribute 'side_effect' |
| Low | Dead Code | `backend/tests/test_t2i_pornmaster.py` | 192 | unused attribute 'side_effect' |
| Low | Dead Code | `dashboard/backend/auth.py` | 29 | unused variable 'token_type' |
| Low | Dead Code | `dashboard/backend/auth.py` | 37 | unused function 'get_password_hash' |
| Low | Dead Code | `dashboard/backend/auth.py` | 72 | unused function 'login_for_access_token' |
| Low | Dead Code | `dashboard/backend/auth.py` | 86 | unused function 'read_users_me' |
| Low | Dead Code | `dashboard/backend/main.py` | 50 | unused function 'startup_event' |
| Low | Dead Code | `dashboard/backend/main.py` | 72 | unused function 'check_auth_header' |
| Low | Dead Code | `dashboard/backend/main.py` | 93 | unused function 'root' |
| Low | Dead Code | `dashboard/backend/routers/gallery.py` | 23 | unused function 'get_all_gallery_posts' |
| Low | Dead Code | `dashboard/backend/routers/gallery.py` | 95 | unused function 'update_gallery_post' |
| Low | Dead Code | `dashboard/backend/routers/gallery.py` | 128 | unused function 'delete_gallery_post' |
| Low | Dead Code | `dashboard/backend/routers/history.py` | 17 | unused function 'get_all_history' |
| Low | Dead Code | `dashboard/backend/routers/history.py` | 93 | unused function 'get_user_history' |
| Low | Dead Code | `dashboard/backend/routers/plans.py` | 20 | unused function 'get_membership_plans' |
| Low | Dead Code | `dashboard/backend/routers/plans.py` | 32 | unused function 'create_membership_plan' |
| Low | Dead Code | `dashboard/backend/routers/plans.py` | 45 | unused function 'update_membership_plan' |
| Low | Dead Code | `dashboard/backend/routers/plans.py` | 68 | unused function 'delete_membership_plan' |
| Low | Dead Code | `dashboard/backend/routers/plans.py` | 87 | unused function 'get_orders' |
| Low | Dead Code | `dashboard/backend/routers/referrals.py` | 15 | unused function 'get_referral_rewards' |
| Low | Dead Code | `dashboard/backend/routers/referrals.py` | 102 | unused variable 'inv_tg_id' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 72 | unused function 'get_stats' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 469 | unused function 'get_finance_hourly_stats' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 565 | unused function 'get_cumulative_finance_hourly_stats' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 653 | unused function 'get_hourly_stats' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 678 | unused function 'get_type_distribution' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 696 | unused function 'get_cumulative_type_distribution' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 709 | unused function 'get_cumulative_hourly_stats' |
| Low | Dead Code | `dashboard/backend/routers/stats.py` | 729 | unused function 'get_stats_history' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 23 | unused function 'refund_bot_task' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 53 | unused function 'clean_zombie_tasks' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 89 | unused function 'health_check' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 114 | unused function 'get_concurrency_stats' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 152 | unused function 'get_active_bot_tasks' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 228 | unused function 'get_bot_queue' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 257 | unused function 'get_system_status_proxy' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 296 | unused function 'get_system_workers_proxy' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 319 | unused function 'get_task_status_proxy' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 336 | unused function 'get_task_image_proxy' |
| Low | Dead Code | `dashboard/backend/routers/system.py` | 370 | unused function 'get_task_video_proxy' |
| Low | Dead Code | `dashboard/backend/routers/templates.py` | 18 | unused function 'get_template_contributions' |
| Low | Dead Code | `dashboard/backend/routers/templates.py` | 65 | unused function 'approve_contribution' |
| Low | Dead Code | `dashboard/backend/routers/templates.py` | 113 | unused function 'delete_contribution' |
| Low | Dead Code | `dashboard/backend/routers/users.py` | 32 | unused function 'get_users' |
| Low | Dead Code | `dashboard/backend/routers/users.py` | 116 | unused function 'delete_user' |
| Low | Dead Code | `dashboard/backend/routers/users.py` | 142 | unused function 'update_user_credits' |
| Low | Dead Code | `dashboard/backend/routers/users.py` | 182 | unused function 'clear_user_history' |
| Low | Dead Code | `dashboard/backend/routers/users.py` | 228 | unused function 'admin_gift_plan' |
| Low | Dead Code | `dashboard/backend/routers/users.py` | 304 | unused function 'update_user_identity' |
| Low | Dead Code | `dashboard/backend/routers/workers.py` | 12 | unused function 'get_worker_list' |
| Low | Dead Code | `dashboard/backend/routers/workers.py` | 19 | unused function 'get_worker_history' |
| Low | Dead Code | `dashboard/backend/schemas.py` | 52 | unused variable 'from_attributes' |
| Low | Dead Code | `dashboard/backend/schemas.py` | 59 | unused variable 'original_price' |
| Low | Dead Code | `dashboard/backend/schemas.py` | 68 | unused variable 'from_attributes' |
| Low | Dead Code | `dashboard/backend/schemas.py` | 89 | unused variable 'output_file_url' |
| Low | Dead Code | `dashboard/backend/schemas.py` | 93 | unused variable 'from_attributes' |
| Low | Dead Code | `dashboard/backend/schemas.py` | 124 | unused variable 'total_pages' |
| Low | Dead Code | `dashboard/backend/schemas.py` | 127 | unused class 'OrderRefundRequest' |
| Low | Dead Code | `src/constants.py` | 90 | unused variable 'VIDEO_RESOLUTIONS' |
| Low | Dead Code | `src/constants.py` | 164 | unused variable 'DURATION_FRAMES' |
| Low | Dead Code | `src/context.py` | 4 | unused variable 'trace_id_ctx' |
| Low | Dead Code | `src/core/auth_core.py` | 21 | unused class 'InsufficientPermissionError' |
| Low | Dead Code | `src/core/task_dispatcher.py` | 21 | unused method 'build_payload' |
| Low | Dead Code | `src/core/task_dispatcher.py` | 49 | unused method 'build_payload' |
| Low | Dead Code | `src/core/task_dispatcher.py` | 92 | unused method 'build_payload' |
| Low | Dead Code | `src/core/task_dispatcher.py` | 133 | unused method 'build_payload' |
| Low | Dead Code | `src/core/task_dispatcher.py` | 220 | unused method 'build_payload' |
| Low | Dead Code | `src/core/user_core.py` | 65 | unused function 'get_or_create_user_by_google' |
| Low | Dead Code | `src/database/logger.py` | 23 | unused function 'before_cursor_execute' |
| Low | Dead Code | `src/database/logger.py` | 27 | unused function 'after_cursor_execute' |
| Low | Dead Code | `src/database/logger.py` | 60 | unused function 'handle_error' |
| Low | Dead Code | `src/database/models.py` | 54 | unused variable 'referrals_made' |
| Low | Dead Code | `src/database/models.py` | 55 | unused variable 'referred_by' |
| Low | Dead Code | `src/database/models.py` | 145 | unused variable 'original_price' |
| Low | Dead Code | `src/database/models.py` | 150 | unused variable 'updated_at' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 34 | unused function 'recharge_stars_menu_callback' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 50 | unused function 'recharge_stars_credit_menu_callback' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 66 | unused function 'recharge_back_callback' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 83 | unused function 'recharge_rmb_menu_callback' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 99 | unused function 'recharge_rmb_credit_menu_callback' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 115 | unused function 'select_rmb_plan_callback' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 132 | unused function 'buy_rmb_plan_callback' |
| Low | Dead Code | `src/handlers/callbacks/billing_callbacks.py` | 222 | unused function 'buy_star_plan_callback' |
| Low | Dead Code | `src/handlers/callbacks/gallery_callbacks.py` | 32 | unused function 'public_share_callback' |
| Low | Dead Code | `src/handlers/callbacks/gallery_callbacks.py` | 206 | unused function 'rate_like_callback' |
| Low | Dead Code | `src/handlers/callbacks/gallery_callbacks.py` | 210 | unused function 'rate_dislike_callback' |
| Low | Dead Code | `src/handlers/callbacks/gallery_callbacks.py` | 268 | unused function 'submit_gallery_callback' |
| Low | Dead Code | `src/handlers/callbacks/gallery_callbacks.py` | 318 | unused function 'gallery_catmenu_callback' |
| Low | Dead Code | `src/handlers/callbacks/gallery_callbacks.py` | 337 | unused function 'gallery_sort_page_callback' |
| Low | Dead Code | `src/handlers/callbacks/gallery_callbacks.py` | 492 | unused function 'gallery_like_dislike_callback' |
| Low | Dead Code | `src/handlers/callbacks/misc_callbacks.py` | 24 | unused function 'noop_callback' |
| Low | Dead Code | `src/handlers/callbacks/misc_callbacks.py` | 29 | unused function 'fsm_fallback_callback' |
| Low | Dead Code | `src/handlers/callbacks/misc_callbacks.py` | 37 | unused function 'random_faceswap_again_callback' |
| Low | Dead Code | `src/handlers/conversation_states.py` | 31 | unused class 'Img2ImgLoraState' |
| Low | Dead Code | `src/handlers/conversation_states.py` | 51 | unused class 'CommonState' |
| Low | Dead Code | `src/handlers/message_handler.py` | 160 | unused function 'handle_photo_edit_menu' |
| Low | Dead Code | `src/handlers/message_handler.py` | 170 | unused function 'handle_video_edit_menu' |
| Low | Dead Code | `src/handlers/message_handler.py` | 180 | unused function 'handle_gallery_menu' |
| Low | Dead Code | `src/handlers/message_handler.py` | 196 | unused function 'handle_back_to_main_menu' |
| Low | Dead Code | `src/handlers/message_handler.py` | 202 | unused function 'handle_recharge_menu' |
| Low | Dead Code | `src/handlers/message_handler.py` | 239 | unused function 'handle_personal_center' |
| Low | Dead Code | `src/handlers/message_handler.py` | 284 | unused function 'handle_checkin' |
| Low | Dead Code | `src/handlers/message_handler.py` | 325 | unused function 'handle_share' |
| Low | Dead Code | `src/handlers/message_handler.py` | 348 | unused function 'handle_queue_status' |
| Low | Dead Code | `src/handlers/utils.py` | 32 | unused function 'with_unified_error_handler' |
| Low | Dead Code | `src/logger.py` | 104 | unused method 'log_interaction' |
| Low | Dead Code | `src/payment_api_server.py` | 16 | unused function 'huanyuy_notify' |
| Low | Dead Code | `src/payment_api_server.py` | 55 | unused function 'payment_result' |
| Low | Dead Code | `src/services/permission_service.py` | 442 | unused variable 'created' |
| Low | Dead Code | `src/services/task_service.py` | 992 | unused method '_submit_generic_task' |
| Low | Dead Code | `src/tests/test_points_system.py` | 46 | unused variable 'created' |
| Low | Dead Code | `src/tests/test_queue_logic.py` | 37 | unused attribute 'side_effect' |
| Low | Dead Code | `src/web_api/core/config.py` | 8 | unused variable 'PROJECT_NAME' |
| Low | Dead Code | `src/web_api/core/config.py` | 9 | unused variable 'VERSION' |
| Low | Dead Code | `src/web_api/main.py` | 51 | unused function 'health_check' |
| Low | Dead Code | `src/web_api/routers/auth.py` | 17 | unused function 'login_telegram' |
| Low | Dead Code | `src/web_api/routers/auth.py` | 72 | unused function 'default_login_form' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 62 | unused function 'generate_thumbnail_url' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 67 | unused function 'get_gallery_config' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 149 | unused function 'get_gallery_posts' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 183 | unused function 'get_my_gallery_posts' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 217 | unused function 'get_my_favorite_posts' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 262 | unused function 'update_post_status' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 279 | unused function 'delete_post' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 310 | unused function 'interact_with_post' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 350 | unused function 'get_apply_context' |
| Low | Dead Code | `src/web_api/routers/gallery.py` | 423 | unused function 'submit_to_gallery' |
| Low | Dead Code | `src/web_api/routers/storage.py` | 15 | unused function 'get_presigned_upload_url' |
| Low | Dead Code | `src/web_api/routers/tasks.py` | 26 | unused function 'create_generation_task' |
| Low | Dead Code | `src/web_api/routers/tasks.py` | 75 | unused function 'task_status_stream' |
| Low | Dead Code | `src/web_api/routers/users.py` | 20 | unused function 'get_user_profile' |
| Low | Dead Code | `src/web_api/routers/users.py` | 50 | unused function 'get_user_history' |
| Low | Dead Code | `src/web_api/schemas/auth_schema.py` | 12 | unused variable 'photo_url' |
| Low | Dead Code | `src/web_api/schemas/auth_schema.py` | 21 | unused variable 'token_type' |
| Low | Dead Code | `src/web_api/schemas/auth_schema.py` | 24 | unused variable 'recharged_invitees_count' |
| Low | Dead Code | `src/web_api/schemas/auth_schema.py` | 25 | unused variable 'total_recharge_count' |
| Low | Dead Code | `src/web_api/schemas/auth_schema.py` | 42 | unused variable 'invitation_count' |
| Low | Dead Code | `src/web_api/schemas/auth_schema.py` | 46 | unused variable 'from_attributes' |
| Low | Dead Code | `src/web_api/schemas/gallery_schema.py` | 26 | unused variable 'has_liked' |
| Low | Dead Code | `src/web_api/schemas/gallery_schema.py` | 27 | unused variable 'has_disliked' |
| Low | Dead Code | `src/web_api/schemas/task_schema.py` | 15 | unused variable 'json_schema_extra' |
| Low | Dead Code | `src/web_api/schemas/task_schema.py` | 30 | unused variable 'balance_remaining' |
| Low | Dead Code | `src/web_api/schemas/user_schema.py` | 19 | unused variable 'from_attributes' |
