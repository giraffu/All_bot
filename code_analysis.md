# 代码全面静态分析与质量评估报告

## 1. 总体可量化指标

- **总分析文件数**: 100
- **总代码行数 (预估)**: 16799
- **死代码比例**: 1.01% (170 个潜在问题点)
- **代码重复率 (预估)**: 4.82% (发现多个大规模重复代码块)
- **平均圈复杂度 (CC)**: 4.33

## 2. 详细文件分析

### 文件: `analyze_code.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 69 | High | 作用域问题 (Scope) | [F841] Local variable `filepath` is assigned to but never used | - |
| 4 | Medium | 安全/性能 (Security/Performance) | Consider possible security implications associated with the subprocess module. | - |
| 23 | Medium | 安全/性能 (Security/Performance) | subprocess call - check for execution of untrusted input. | - |
| 149 | Medium | 安全/性能 (Security/Performance) | Try, Except, Pass detected. | - |
| 202 | Medium | 安全/性能 (Security/Performance) | Try, Except, Pass detected. | - |
| 102 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 129 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 130 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 131 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `backend/app/config.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 22 | Medium | 死代码 (Dead Code) | unused variable 'model_config' (60% confidence) | - |

### 文件: `backend/app/main.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 104 | Medium | 死代码 (Dead Code) | unused function 'create_img2img_task' (60% confidence) | - |
| 116 | Medium | 死代码 (Dead Code) | unused function 'create_img2img_lora_task' (60% confidence) | - |
| 128 | Medium | 死代码 (Dead Code) | unused function 'create_face_swap_task' (60% confidence) | - |
| 140 | Medium | 死代码 (Dead Code) | unused function 'create_video_insert_task' (60% confidence) | - |
| 152 | Medium | 死代码 (Dead Code) | unused function 'create_video_edit_task' (60% confidence) | - |
| 164 | Medium | 死代码 (Dead Code) | unused function 'create_video_lora_task' (60% confidence) | - |
| 178 | Medium | 死代码 (Dead Code) | unused function 'create_face_video_task' (60% confidence) | - |
| 190 | Medium | 死代码 (Dead Code) | unused function 'create_i2i_pro_task' (60% confidence) | - |
| 202 | Medium | 死代码 (Dead Code) | unused function 'create_ltx_video_task' (60% confidence) | - |
| 214 | Medium | 死代码 (Dead Code) | unused function 'create_t2i_pornmaster_turbo_task' (60% confidence) | - |
| 215 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=14): create_t2i_pornmaster_turbo_task | - |
| 317 | Medium | 死代码 (Dead Code) | unused function 'get_task_status_v1' (60% confidence) | - |
| 377 | Medium | 死代码 (Dead Code) | unused function 'get_task_image' (60% confidence) | - |
| 414 | Medium | 死代码 (Dead Code) | unused function 'get_task_video' (60% confidence) | - |
| 449 | Medium | 死代码 (Dead Code) | unused function 'get_system_workers' (60% confidence) | - |

### 文件: `backend/app/models.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 45 | Medium | 死代码 (Dead Code) | unused variable 'last_seen' (60% confidence) | - |
| 47 | Medium | 死代码 (Dead Code) | unused variable 'current_task_type' (60% confidence) | - |
| 48 | Medium | 死代码 (Dead Code) | unused variable 'current_task_progress' (60% confidence) | - |
| 49 | Medium | 死代码 (Dead Code) | unused variable 'current_task_created_at' (60% confidence) | - |
| 63 | Medium | 死代码 (Dead Code) | unused variable 'image' (60% confidence) | - |
| 64 | Medium | 死代码 (Dead Code) | unused variable 'image2' (60% confidence) | - |
| 68 | Medium | 死代码 (Dead Code) | unused variable 'num_inference_steps' (60% confidence) | - |
| 69 | Medium | 死代码 (Dead Code) | unused variable 'guidance_scale' (60% confidence) | - |
| 75 | Medium | 死代码 (Dead Code) | unused variable 'image' (60% confidence) | - |
| 76 | Medium | 死代码 (Dead Code) | unused variable 'image2' (60% confidence) | - |
| 80 | Medium | 死代码 (Dead Code) | unused variable 'num_inference_steps' (60% confidence) | - |
| 81 | Medium | 死代码 (Dead Code) | unused variable 'guidance_scale' (60% confidence) | - |
| 89 | Medium | 死代码 (Dead Code) | unused variable 'face_image' (60% confidence) | - |
| 90 | Medium | 死代码 (Dead Code) | unused variable 'body_image' (60% confidence) | - |
| 95 | Medium | 死代码 (Dead Code) | unused variable 'image' (60% confidence) | - |
| 104 | Medium | 死代码 (Dead Code) | unused variable 'image' (60% confidence) | - |
| 113 | Medium | 死代码 (Dead Code) | unused variable 'image' (60% confidence) | - |
| 123 | Medium | 死代码 (Dead Code) | unused variable 'face_image' (60% confidence) | - |
| 131 | Medium | 死代码 (Dead Code) | unused variable 'image' (60% confidence) | - |
| 138 | Medium | 死代码 (Dead Code) | unused variable 'image' (60% confidence) | - |

### 文件: `backend/app/queue_manager.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 61 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=12): dequeue_task | - |
| 115 | Medium | 死代码 (Dead Code) | unused method 'get_task_by_prompt_id' (60% confidence) | - |
| 253 | Medium | 死代码 (Dead Code) | unused method 'clear_running_tasks' (60% confidence) | - |

### 文件: `backend/app/routers/agent.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 55 | Medium | 死代码 (Dead Code) | unused function 'pop_task' (60% confidence) | - |
| 77 | Medium | 死代码 (Dead Code) | unused function 'check_task' (60% confidence) | - |
| 88 | Medium | 死代码 (Dead Code) | unused function 'update_status' (60% confidence) | - |
| 120 | Medium | 死代码 (Dead Code) | unused function 'task_heartbeat' (60% confidence) | - |
| 132 | Medium | 死代码 (Dead Code) | unused function 'heartbeat' (60% confidence) | - |

### 文件: `backend/tests/conftest.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 12 | Medium | 死代码 (Dead Code) | unused function 'fixture_mock_queue_manager' (60% confidence) | - |

### 文件: `backend/tests/test_api.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 14 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 16 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 17 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 18 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 19 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 32 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 33 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 49 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 50 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 63 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 64 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 77 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 78 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 92 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 94 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 95 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 96 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 101 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 118 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 126 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 127 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 140 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `backend/tests/test_auth.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 9 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 10 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 21 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 22 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 34 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `backend/tests/test_t2i_pornmaster.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 17 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 19 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 20 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 27 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 37 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 45 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 47 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 48 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 49 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 58 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 66 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 74 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 89 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 97 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 98 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 112 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 120 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 131 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 133 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 134 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 155 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 170 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 192 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 203 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `config.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 10 | Medium | 死代码 (Dead Code) | unused variable 'FILE_BOT_TOKEN' (60% confidence) | - |
| 13 | Medium | 死代码 (Dead Code) | unused variable 'TELETHON_API_ID' (60% confidence) | - |
| 14 | Medium | 死代码 (Dead Code) | unused variable 'TELETHON_API_HASH' (60% confidence) | - |
| 15 | Medium | 死代码 (Dead Code) | unused variable 'PHONE' (60% confidence) | - |
| 16 | Medium | 死代码 (Dead Code) | unused variable 'PASSWORD' (60% confidence) | - |
| 17 | Medium | 死代码 (Dead Code) | unused variable 'GROUP_ID' (60% confidence) | - |
| 44 | Medium | 死代码 (Dead Code) | unused variable 'IMGPROXY_URL' (60% confidence) | - |
| 73 | Medium | 死代码 (Dead Code) | unused variable 'LLM_API_URL' (60% confidence) | - |
| 74 | Medium | 死代码 (Dead Code) | unused variable 'LLM_MODEL_NAME' (60% confidence) | - |
| 78 | Medium | 死代码 (Dead Code) | unused variable 'POLL_TIMEOUT' (60% confidence) | - |
| 88 | Medium | 死代码 (Dead Code) | unused variable 'DAILY_LIMIT' (60% confidence) | - |

### 文件: `cs_bot/bot.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 104 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=36): handle_group_message | - |
| 221 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=23): silent_logger_handler | - |
| 301 | Medium | 安全/性能 (Security/Performance) | Possible hardcoded password: 'your_bot_token_here' | - |

### 文件: `scripts/clear_stuck_tasks.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 27 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): clean_stuck_tasks_and_reset_locks | - |

### 文件: `src/api_client.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 308 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=25): listen_for_progress | - |
| 34 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |

### 文件: `src/bot_test.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 66 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 68 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 69 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 70 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |

### 文件: `src/constants.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 90 | Medium | 死代码 (Dead Code) | unused variable 'VIDEO_RESOLUTIONS' (60% confidence) | - |
| 164 | Medium | 死代码 (Dead Code) | unused variable 'DURATION_FRAMES' (60% confidence) | - |
| 170 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=13): get_video_settings_keyboard | - |

### 文件: `src/context.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 4 | Medium | 死代码 (Dead Code) | unused variable 'trace_id_ctx' (60% confidence) | - |

### 文件: `src/core/auth_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 21 | Medium | 死代码 (Dead Code) | unused class 'InsufficientPermissionError' (60% confidence) | - |
| 56 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=13): verify_telegram_webapp_initdata | - |

### 文件: `src/core/billing_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 79 | Medium | 死代码 (Dead Code) | unused function 'calculate_identity_conversion' (60% confidence) | - |
| 133 | Medium | 死代码 (Dead Code) | unused function 'calculate_identity_manual_conversion' (60% confidence) | - |
| 75 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 76 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |

### 文件: `src/core/gallery_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 240 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=27): get_gallery_feed | - |
| 49 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=20): process_submit_to_gallery | - |
| 142 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): toggle_like | - |
| 122 | Low | 代码规范 (Linting) | [E713] Test for membership should be `not in` | - |
| 259 | Low | 代码规范 (Linting) | [E712] Avoid equality comparisons to `True`; use `GalleryPost.is_active:` for truth checks | - |
| 261 | Low | 代码规范 (Linting) | [E712] Avoid equality comparisons to `False`; use `not GalleryPost.is_active:` for false checks | - |

### 文件: `src/core/task_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 109 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=34): process_and_submit_task | - |
| 50 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=15): monitor_task_and_release_lock | - |
| 293 | Medium | 死代码 (Dead Code) | unused function 'get_system_task_stats' (60% confidence) | - |
| 303 | Medium | 死代码 (Dead Code) | unused function 'force_terminate_task' (60% confidence) | - |
| 312 | Medium | 死代码 (Dead Code) | unused function 'sync_user_concurrency' (60% confidence) | - |
| 29 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 36 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 37 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 38 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |

### 文件: `src/core/task_dispatcher.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 21 | Medium | 死代码 (Dead Code) | unused method 'build_payload' (60% confidence) | - |
| 49 | Medium | 死代码 (Dead Code) | unused method 'build_payload' (60% confidence) | - |
| 61 | Medium | 安全/性能 (Security/Performance) | Standard pseudo-random generators are not suitable for security/cryptographic purposes. | - |
| 92 | Medium | 死代码 (Dead Code) | unused method 'build_payload' (60% confidence) | - |
| 133 | Medium | 死代码 (Dead Code) | unused method 'build_payload' (60% confidence) | - |
| 148 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=16): submit_task | - |
| 220 | Medium | 死代码 (Dead Code) | unused method 'build_payload' (60% confidence) | - |

### 文件: `src/core/user_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 65 | Medium | 死代码 (Dead Code) | unused function 'get_or_create_user_by_google' (60% confidence) | - |

### 文件: `src/core/user_facade.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 22 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=21): get_user_dashboard_info | - |

### 文件: `src/database/logger.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 23 | Medium | 死代码 (Dead Code) | unused function 'before_cursor_execute' (60% confidence) | - |
| 27 | Medium | 死代码 (Dead Code) | unused function 'after_cursor_execute' (60% confidence) | - |
| 60 | Medium | 死代码 (Dead Code) | unused function 'handle_error' (60% confidence) | - |

### 文件: `src/database/models.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 30 | Medium | 死代码 (Dead Code) | unused variable 'hashed_password' (60% confidence) | - |
| 47 | Medium | 死代码 (Dead Code) | unused variable 'last_activity' (60% confidence) | - |
| 53 | Medium | 死代码 (Dead Code) | unused variable 'inviter_user' (60% confidence) | - |
| 54 | Medium | 死代码 (Dead Code) | unused variable 'referrals_made' (60% confidence) | - |
| 55 | Medium | 死代码 (Dead Code) | unused variable 'referred_by' (60% confidence) | - |
| 68 | Medium | 死代码 (Dead Code) | unused variable 'invitee' (60% confidence) | - |
| 82 | Medium | 死代码 (Dead Code) | unused variable 'is_public' (60% confidence) | - |
| 83 | Medium | 死代码 (Dead Code) | unused variable 'rating' (60% confidence) | - |
| 96 | Medium | 死代码 (Dead Code) | unused variable 'is_reviewed' (60% confidence) | - |
| 106 | Medium | 死代码 (Dead Code) | unused variable 'checkin_date' (60% confidence) | - |
| 145 | Medium | 死代码 (Dead Code) | unused variable 'original_price' (60% confidence) | - |
| 150 | Medium | 死代码 (Dead Code) | unused variable 'updated_at' (60% confidence) | - |
| 155 | Medium | 死代码 (Dead Code) | unused class 'WorkerLog' (60% confidence) | - |
| 159 | Medium | 死代码 (Dead Code) | unused variable 'worker_id' (60% confidence) | - |
| 164 | Medium | 死代码 (Dead Code) | unused variable 'end_time' (60% confidence) | - |
| 166 | Medium | 死代码 (Dead Code) | unused variable 'error_message' (60% confidence) | - |

### 文件: `src/handlers/callback_handler.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 11 | Low | 导入问题 (Imports) | [F401] `src.handlers.callbacks.misc_callbacks` imported but unused | - |
| 28 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/callbacks/billing_callbacks.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 34 | Medium | 死代码 (Dead Code) | unused function 'recharge_stars_menu_callback' (60% confidence) | - |
| 50 | Medium | 死代码 (Dead Code) | unused function 'recharge_stars_credit_menu_callback' (60% confidence) | - |
| 66 | Medium | 死代码 (Dead Code) | unused function 'recharge_back_callback' (60% confidence) | - |
| 83 | Medium | 死代码 (Dead Code) | unused function 'recharge_rmb_menu_callback' (60% confidence) | - |
| 99 | Medium | 死代码 (Dead Code) | unused function 'recharge_rmb_credit_menu_callback' (60% confidence) | - |
| 115 | Medium | 死代码 (Dead Code) | unused function 'select_rmb_plan_callback' (60% confidence) | - |
| 132 | Medium | 死代码 (Dead Code) | unused function 'buy_rmb_plan_callback' (60% confidence) | - |
| 133 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): buy_rmb_plan_callback | - |
| 216 | Medium | 安全/性能 (Security/Performance) | Try, Except, Pass detected. | - |
| 222 | Medium | 死代码 (Dead Code) | unused function 'buy_star_plan_callback' (60% confidence) | - |
| 254 | Medium | 安全/性能 (Security/Performance) | Possible hardcoded password: '' | - |
| 19 | Low | 代码规范 (Linting) | [E712] Avoid equality comparisons to `True`; use `MembershipPlan.is_active:` for truth checks | - |

### 文件: `src/handlers/callbacks/gallery_callbacks.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 33 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=37): public_share_callback | - |
| 259 | High | 作用域问题 (Scope) | [F811] Redefinition of unused `contextlib` from line 28: `contextlib` redefined here | - |
| 339 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=43): gallery_sort_page_callback | - |
| 32 | Medium | 死代码 (Dead Code) | unused function 'public_share_callback' (60% confidence) | - |
| 168 | Medium | 安全/性能 (Security/Performance) | Try, Except, Pass detected. | - |
| 206 | Medium | 死代码 (Dead Code) | unused function 'rate_like_callback' (60% confidence) | - |
| 210 | Medium | 死代码 (Dead Code) | unused function 'rate_dislike_callback' (60% confidence) | - |
| 268 | Medium | 死代码 (Dead Code) | unused function 'submit_gallery_callback' (60% confidence) | - |
| 318 | Medium | 死代码 (Dead Code) | unused function 'gallery_catmenu_callback' (60% confidence) | - |
| 337 | Medium | 死代码 (Dead Code) | unused function 'gallery_sort_page_callback' (60% confidence) | - |
| 492 | Medium | 死代码 (Dead Code) | unused function 'gallery_like_dislike_callback' (60% confidence) | - |
| 494 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=14): gallery_like_dislike_callback | - |
| 252 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 259 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |

### 文件: `src/handlers/callbacks/misc_callbacks.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 24 | Medium | 死代码 (Dead Code) | unused function 'noop_callback' (60% confidence) | - |
| 29 | Medium | 死代码 (Dead Code) | unused function 'fsm_fallback_callback' (60% confidence) | - |
| 37 | Medium | 死代码 (Dead Code) | unused function 'random_faceswap_again_callback' (60% confidence) | - |
| 38 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): random_faceswap_again_callback | - |
| 78 | Medium | 安全/性能 (Security/Performance) | Standard pseudo-random generators are not suitable for security/cryptographic purposes. | - |
| 60 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/command_handler.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 46 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=12): start | - |
| 47 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/conversation_states.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 31 | Medium | 死代码 (Dead Code) | unused class 'Img2ImgLoraState' (60% confidence) | - |
| 51 | Medium | 死代码 (Dead Code) | unused class 'CommonState' (60% confidence) | - |

### 文件: `src/handlers/fsm/custom_video_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 91 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 92 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 196 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/fsm/edit_image_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 149 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 150 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 56 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): start_edit_image | - |
| 189 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): receive_prompt | - |
| 94 | Low | 代码规范 (Linting) | [F541] f-string without any placeholders | - |
| 164 | Low | 代码规范 (Linting) | [F541] f-string without any placeholders | - |
| 167 | Low | 代码规范 (Linting) | [F541] f-string without any placeholders | - |
| 210 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/fsm/face_video_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 107 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 108 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 146 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |

### 文件: `src/handlers/fsm/faceswap_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 95 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 96 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 136 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 128 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/fsm/gallery_apply_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 44 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=31): start_gallery_apply | - |
| 229 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=14): receive_reference_image | - |
| 69 | Low | 导入问题 (Imports) | [F401] `src.database.models.UserInteraction` imported but unused | - |

### 文件: `src/handlers/fsm/ltx_video_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 93 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 94 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 241 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/fsm/quick_image_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 136 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 137 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 52 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=13): start_quick_image | - |
| 101 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=17): receive_image | - |
| 165 | Medium | 安全/性能 (Security/Performance) | Standard pseudo-random generators are not suitable for security/cryptographic purposes. | - |
| 128 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/fsm/quick_video_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 113 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 114 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 54 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): start_quick_video | - |
| 236 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 240 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/fsm/video_lora_fsm.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 129 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 130 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 238 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/message_handler.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 106 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=13): _handle_template_contribution | - |
| 160 | Medium | 死代码 (Dead Code) | unused function 'handle_photo_edit_menu' (60% confidence) | - |
| 170 | Medium | 死代码 (Dead Code) | unused function 'handle_video_edit_menu' (60% confidence) | - |
| 180 | Medium | 死代码 (Dead Code) | unused function 'handle_gallery_menu' (60% confidence) | - |
| 196 | Medium | 死代码 (Dead Code) | unused function 'handle_back_to_main_menu' (60% confidence) | - |
| 202 | Medium | 死代码 (Dead Code) | unused function 'handle_recharge_menu' (60% confidence) | - |
| 239 | Medium | 死代码 (Dead Code) | unused function 'handle_personal_center' (60% confidence) | - |
| 284 | Medium | 死代码 (Dead Code) | unused function 'handle_checkin' (60% confidence) | - |
| 325 | Medium | 死代码 (Dead Code) | unused function 'handle_share' (60% confidence) | - |
| 348 | Medium | 死代码 (Dead Code) | unused function 'handle_queue_status' (60% confidence) | - |
| 366 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=12): handle_prompt | - |
| 53 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 54 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 56 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 66 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 67 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 69 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 79 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 80 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 82 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 241 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 309 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |
| 367 | Low | 代码规范 (Linting) | [E701] Multiple statements on one line (colon) | - |

### 文件: `src/handlers/payment_handler.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 25 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=19): successful_payment_callback | - |
| 201 | Low | 代码规范 (Linting) | [F541] f-string without any placeholders | - |

### 文件: `src/handlers/utils.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 32 | Medium | 死代码 (Dead Code) | unused function 'with_unified_error_handler' (60% confidence) | - |

### 文件: `src/logger.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 104 | Medium | 死代码 (Dead Code) | unused method 'log_interaction' (60% confidence) | - |
| 145 | Medium | 死代码 (Dead Code) | unused attribute 'last_activity' (60% confidence) | - |

### 文件: `src/payment_api_server.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 86 | High | 安全/性能 (Security/Performance) | Possible binding to all interfaces. | - |
| 16 | Medium | 死代码 (Dead Code) | unused function 'huanyuy_notify' (60% confidence) | - |
| 55 | Medium | 死代码 (Dead Code) | unused function 'payment_result' (60% confidence) | - |

### 文件: `src/quota.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 141 | Medium | 死代码 (Dead Code) | unused attribute 'last_activity' (60% confidence) | - |
| 313 | Medium | 死代码 (Dead Code) | unused attribute 'last_activity' (60% confidence) | - |

### 文件: `src/services/log_service.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 14 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): LogService | - |
| 72 | Medium | 死代码 (Dead Code) | unused method 'get_logs' (60% confidence) | - |
| 73 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=13): get_logs | - |

### 文件: `src/services/payment_fulfillment_service.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 15 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=19): fulfill_order | - |
| 153 | Low | 代码规范 (Linting) | [F541] f-string without any placeholders | - |

### 文件: `src/services/payment_validator.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 62 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=12): _check_new_transactions | - |
| 125 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=20): _process_order | - |

### 文件: `src/services/permission_service.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 198 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=13): refresh_user_group | - |
| 374 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): perform_checkin | - |
| 442 | Medium | 死代码 (Dead Code) | unused variable 'created' (60% confidence) | - |

### 文件: `src/services/rmb_payment_service.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 30 | Critical | 安全/性能 (Security/Performance) | Use of weak MD5 hash for security. Consider usedforsecurity=False | - |
| 64 | Critical | 安全/性能 (Security/Performance) | Use of weak MD5 hash for security. Consider usedforsecurity=False | - |

### 文件: `src/services/storage.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 34 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=11): _init_client | - |

### 文件: `src/services/task_registry.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 7 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |

### 文件: `src/services/task_service.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 291 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=29): process_generation_task | - |
| 490 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=21): _process_video_task_template | - |
| 1012 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=24): _monitor_task_progress | - |
| 1090 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=37): _handle_task_completion | - |
| 53 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=12): TaskService | - |
| 55 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=15): process_ltx_video_task | - |
| 173 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=15): process_face_video_task | - |
| 721 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=18): process_custom_video_task | - |
| 865 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=14): process_i2i_pro_task | - |
| 994 | Medium | 安全/性能 (Security/Performance) | Try, Except, Pass detected. | - |
| 998 | Medium | 死代码 (Dead Code) | unused method '_submit_generic_task' (60% confidence) | - |
| 1253 | Medium | 安全/性能 (Security/Performance) | Try, Except, Pass detected. | - |
| 952 | Low | 代码规范 (Linting) | [F541] f-string without any placeholders | - |

### 文件: `src/services/zombie_cleaner_service.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 12 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=14): clean_zombies | - |

### 文件: `src/tests/test_dynamic_priority.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 17 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 25 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 41 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 46 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 51 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 56 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 61 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 77 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 82 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 87 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 92 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 97 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 102 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 118 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 123 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 139 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 144 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 159 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 163 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 177 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 182 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `src/tests/test_imports.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 12 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 19 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `src/tests/test_points_system.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 15 | Medium | 安全/性能 (Security/Performance) | Standard pseudo-random generators are not suitable for security/cryptographic purposes. | - |
| 46 | Medium | 死代码 (Dead Code) | unused variable 'created' (60% confidence) | - |
| 50 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 54 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 57 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 61 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 67 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 72 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `src/tests/test_queue_logic.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 37 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 44 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 45 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 47 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 49 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 89 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 92 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `src/tests/test_task_service_refactored.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 53 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 54 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 60 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 63 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 64 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |

### 文件: `src/web_api/core/config.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 8 | Medium | 死代码 (Dead Code) | unused variable 'PROJECT_NAME' (60% confidence) | - |
| 9 | Medium | 死代码 (Dead Code) | unused variable 'VERSION' (60% confidence) | - |

### 文件: `src/web_api/main.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 51 | Medium | 死代码 (Dead Code) | unused function 'health_check' (60% confidence) | - |

### 文件: `src/web_api/routers/auth.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 17 | Medium | 死代码 (Dead Code) | unused function 'login_telegram' (60% confidence) | - |
| 58 | Medium | 安全/性能 (Security/Performance) | Possible hardcoded password: 'bearer' | - |
| 72 | Medium | 死代码 (Dead Code) | unused function 'default_login_form' (60% confidence) | - |

### 文件: `src/web_api/routers/gallery.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 62 | Medium | 死代码 (Dead Code) | unused function 'generate_thumbnail_url' (60% confidence) | - |
| 67 | Medium | 死代码 (Dead Code) | unused function 'get_gallery_config' (60% confidence) | - |
| 82 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=18): _build_post_responses | - |
| 149 | Medium | 死代码 (Dead Code) | unused function 'get_gallery_posts' (60% confidence) | - |
| 183 | Medium | 死代码 (Dead Code) | unused function 'get_my_gallery_posts' (60% confidence) | - |
| 217 | Medium | 死代码 (Dead Code) | unused function 'get_my_favorite_posts' (60% confidence) | - |
| 262 | Medium | 死代码 (Dead Code) | unused function 'update_post_status' (60% confidence) | - |
| 279 | Medium | 死代码 (Dead Code) | unused function 'delete_post' (60% confidence) | - |
| 310 | Medium | 死代码 (Dead Code) | unused function 'interact_with_post' (60% confidence) | - |
| 350 | Medium | 死代码 (Dead Code) | unused function 'get_apply_context' (60% confidence) | - |
| 412 | Medium | 死代码 (Dead Code) | unused function 'submit_to_gallery' (60% confidence) | - |
| 39 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |
| 236 | Low | 代码规范 (Linting) | [E712] Avoid equality comparisons to `True`; use `GalleryPost.is_active:` for truth checks | - |
| 405 | Low | 代码规范 (Linting) | [E402] Module level import not at top of file | - |

### 文件: `src/web_api/routers/storage.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 15 | Medium | 死代码 (Dead Code) | unused function 'get_presigned_upload_url' (60% confidence) | - |

### 文件: `src/web_api/routers/tasks.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 26 | Medium | 死代码 (Dead Code) | unused function 'create_generation_task' (60% confidence) | - |
| 76 | Medium | 死代码 (Dead Code) | unused function 'task_status_stream' (60% confidence) | - |

### 文件: `src/web_api/routers/users.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 20 | Medium | 死代码 (Dead Code) | unused function 'get_user_profile' (60% confidence) | - |
| 50 | Medium | 死代码 (Dead Code) | unused function 'get_user_history' (60% confidence) | - |

### 文件: `src/web_api/schemas/auth_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 12 | Medium | 死代码 (Dead Code) | unused variable 'photo_url' (60% confidence) | - |
| 14 | Medium | 死代码 (Dead Code) | unused variable 'hash' (60% confidence) | - |
| 19 | Medium | 死代码 (Dead Code) | unused class 'Token' (60% confidence) | - |
| 21 | Medium | 死代码 (Dead Code) | unused variable 'token_type' (60% confidence) | - |
| 24 | Medium | 死代码 (Dead Code) | unused variable 'recharged_invitees_count' (60% confidence) | - |
| 25 | Medium | 死代码 (Dead Code) | unused variable 'total_recharge_count' (60% confidence) | - |
| 42 | Medium | 死代码 (Dead Code) | unused variable 'invitation_count' (60% confidence) | - |
| 46 | Medium | 死代码 (Dead Code) | unused variable 'from_attributes' (60% confidence) | - |

### 文件: `src/web_api/schemas/gallery_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 26 | Medium | 死代码 (Dead Code) | unused variable 'has_liked' (60% confidence) | - |
| 27 | Medium | 死代码 (Dead Code) | unused variable 'has_disliked' (60% confidence) | - |

### 文件: `src/web_api/schemas/task_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 16 | Medium | 死代码 (Dead Code) | unused variable 'json_schema_extra' (60% confidence) | - |
| 31 | Medium | 死代码 (Dead Code) | unused variable 'balance_remaining' (60% confidence) | - |

### 文件: `src/web_api/schemas/user_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 19 | Medium | 死代码 (Dead Code) | unused variable 'from_attributes' (60% confidence) | - |

### 文件: `tests/test_saga_and_queue.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 29 | Medium | 死代码 (Dead Code) | unused attribute 'side_effect' (60% confidence) | - |
| 54 | Medium | 安全/性能 (Security/Performance) | Use of assert detected. The enclosed code will be removed when compiling to optimised byte code. | - |
| 2 | Low | 导入问题 (Imports) | [F401] `asyncio` imported but unused | - |
| 3 | Low | 导入问题 (Imports) | [F401] `unittest.mock.MagicMock` imported but unused | - |

### 文件: `workers/comfy_agent/agent_main.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 39 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 40 | High | 安全/性能 (Security/Performance) | Probable insecure usage of temp file/directory. | - |
| 143 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=24): ws_listener_loop | - |
| 272 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=49): process_task | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==payment_fulfillment_service:[52:105]
==payment_handler:[81:138]
            new_expire_at = user.identity_expire_at
            converted_days = 0
            final_identity = plan.identity_name
            is_downgrade = False
            is_pure_credit = (plan.duration_days == 0)

            # 定义身份优先级和折算比例
            identity_priority = {
                "外门弟子": 0,
                "内门弟子": 1,
                "核心弟子": 2,
                "真传弟子": 3
            }
            identity_ratio = {
                "外门弟子": 1,
                "内门弟子": 2,
                "核心弟子": 5,
                "真传弟子": 10
            }

            current_priority = identity_priority.get(user.current_identity, 0)
            new_priority = identity_priority.get(plan.identity_name, 0)

            if is_pure_credit:
                # 直购模式：完全不改变原有的身份和到期时间
                final_identity = user.current_identity
                new_expire_at = user.identity_expire_at
            elif new_expire_at and new_expire_at > now:
                if user.current_identity == plan.identity_name:
                    # 同套餐续费
                    new_expire_at += timedelta(days=plan.duration_days)
                elif new_priority > current_priority:
                    # 升级：将旧身份残值折算为新身份天数
                    remaining_days = (new_expire_at - now).total_seconds() / 86400.0
                    old_ratio = identity_ratio.get(user.current_identity, 1)
                    new_ratio = identity_ratio.get(plan.identity_name, 1)

                    # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
                    converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
                    new_expire_at = now + timedelta(days=plan.duration_days + converted_days)
                else:
                    # 降级或同级：保留高等级身份，将新购买的低等级套餐价值折算为高等级身份的天数
                    is_downgrade = True
                    final_identity = user.current_identity # 保持原身份

                    old_ratio = identity_ratio.get(user.current_identity, 1)
                    new_ratio = identity_ratio.get(plan.identity_name, 1)

                    # 新购价值 = 新套餐天数 * 新比例，折算天数 = 新购价值 / 旧比例
                    extra_days = math.ceil((plan.duration_days * new_ratio) / old_ratio)
                    converted_days = extra_days
                    new_expire_at += timedelta(days=extra_days)
            else:
                # 身份已过期或首次充值
                new_expire_at = now + timedelta(days=plan.duration_days)

            # 更新用户信息 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[244:278]
==quick_image_fsm:[207:241]
            )
        )

    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
    await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_quick_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[ | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==custom_video_fsm:[128:163]
==video_lora_fsm:[167:202]
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer("交互已失效或任务已提交，请重新开始", show_alert=True)
        return ConversationHandler.END

    if data.startswith("set_res_"):
        new_res = data.split("_")[2]
        if new_res == "1024p" and fsm_data.get('duration') == "10s":
            fsm_data['duration'] = "8s"
            with contextlib.suppress(Exception):
                await query.answer("1024p和10s无法同时选择，已自动将时长调为8s", show_alert=True)
        fsm_data['resolution'] = new_res
    elif data.startswith("set_dur_"):
        new_dur = data.split("_")[2]
        if new_dur == "10s" and fsm_data.get('resolution') == "1024p":
            fsm_data['resolution'] = "720p"
            with contextlib.suppress(Exception):
                await query.answer("1024p和10s无法同时选择，已自动将画质调为720p", show_alert=True)
        fsm_data['duration'] = new_dur

    res = fsm_data['resolution']
    dur = fsm_data['duration']

    from src.core.user_core import get_or_create_user_by_telegram
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    reply_markup = get_video_settings_keyboard(user_group, user_identity, res, dur)

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==custom_video_fsm:[222:256]
==video_lora_fsm:[270:304]
        )
    )

    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
    await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_video_lora_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[ | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==ltx_video_fsm:[270:300]
==quick_image_fsm:[211:241]
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
    await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_ltx_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[ | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==ltx_video_fsm:[35:63]
==video_lora_fsm:[43:71]
    path = pending_files.get('image_path')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logger.error(f"Failed to remove {path}: {e}")

async def start_ltx_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 高级图生视频"""
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)

    from src.utils import is_maintenance_mode
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_video_fsm:[163:193]
==video_lora_fsm:[172:202]
    if data.startswith("set_res_"):
        new_res = data.split("_")[2]
        if new_res == "1024p" and fsm_data.get('duration') == "10s":
            fsm_data['duration'] = "8s"
            with contextlib.suppress(Exception):
                await query.answer("1024p和10s无法同时选择，已自动将时长调为8s", show_alert=True)
        fsm_data['resolution'] = new_res
    elif data.startswith("set_dur_"):
        new_dur = data.split("_")[2]
        if new_dur == "10s" and fsm_data.get('resolution') == "1024p":
            fsm_data['resolution'] = "720p"
            with contextlib.suppress(Exception):
                await query.answer("1024p和10s无法同时选择，已自动将画质调为720p", show_alert=True)
        fsm_data['duration'] = new_dur

    res = fsm_data['resolution']
    dur = fsm_data['duration']

    from src.core.user_core import get_or_create_user_by_telegram
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    reply_markup = get_video_settings_keyboard(user_group, user_identity, res, dur)

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==payment_handler:[109:138]
==payment_validator:[230:261]
                            if user.current_identity == plan.identity_name:
                                # 同套餐续费
                                new_expire_at += timedelta(days=plan.duration_days)
                            elif new_priority > current_priority:
                                # 升级：将旧身份残值折算为新身份天数
                                import math
                                remaining_days = (new_expire_at - now).total_seconds() / 86400.0
                                old_ratio = identity_ratio.get(user.current_identity, 1)
                                new_ratio = identity_ratio.get(plan.identity_name, 1)

                                # 残值 = 剩余天数 * 旧比例，折算天数 = 残值 / 新比例
                                converted_days = math.ceil((remaining_days * old_ratio) / new_ratio)
                                new_expire_at = now + timedelta(days=plan.duration_days + converted_days)
                            else:
                                # 降级或同级：保留高等级身份，将新购买的低等级套餐价值折算为高等级身份的天数
                                is_downgrade = True
                                final_identity = user.current_identity

                                import math
                                old_ratio = identity_ratio.get(user.current_identity, 1)
                                new_ratio = identity_ratio.get(plan.identity_name, 1)

                                # 新购价值 = 新套餐天数 * 新比例，折算天数 = 新购价值 / 旧比例
                                extra_days = math.ceil((plan.duration_days * new_ratio) / old_ratio)
                                converted_days = extra_days
                                new_expire_at += timedelta(days=extra_days)
                        else:
                            # 身份已过期或首次充值
                            new_expire_at = now + timedelta(days=plan.duration_days)

                        # Perform update | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[174:199]
==quick_image_fsm:[216:241]
        await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_faceswap_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[ | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[253:278]
==quick_video_fsm:[301:327]
    await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_edit_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[ | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==payment_handler:[88:104]
==payment_validator:[213:229]
            identity_priority = {
                "外门弟子": 0,
                "内门弟子": 1,
                "核心弟子": 2,
                "真传弟子": 3
            }
            identity_ratio = {
                "外门弟子": 1,
                "内门弟子": 2,
                "核心弟子": 5,
                "真传弟子": 10
            }

            current_priority = identity_priority.get(user.current_identity, 0)
            new_priority = identity_priority.get(plan.identity_name, 0)
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==face_video_fsm:[256:278]
==quick_image_fsm:[222:241]
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_quick_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[ | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==face_video_fsm:[54:72]
==faceswap_fsm:[50:66]
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    # 1. Concurrency Check (User Data Lock)
    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        else:
            await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    # 2. Lock the user context for this flow | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==custom_video_fsm:[187:205]
==video_lora_fsm:[229:247]
    if res == "1024p" and dur == "10s":
        res = "720p"
        fsm_data['resolution'] = "720p"

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)

    if not update.effective_user: return ConversationHandler.END
    user = update.effective_user
    if not await permission_service.check_quota(user.id, user.username, user.full_name, context.bot, update.effective_chat.id, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    image_path = fsm_data.pop('image_path', None)
    if not image_path:
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[57:74]
==quick_video_fsm:[55:72]
    message = update.message or update.edited_message
    text = message.text.strip() if message and message.text else ""

    from src.utils import is_maintenance_mode
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==face_video_fsm:[48:65]
==video_lora_fsm:[52:68]
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)

    from src.utils import is_maintenance_mode
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    # 1. Concurrency Check (User Data Lock)
    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==src.core.user_core:[17:31]
==src.quota:[51:63]
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                updated = True

            if updated:
                await session.commit() | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==payment_handler:[88:101]
==src.core.billing_core:[87:100]
            identity_priority = {
                "外门弟子": 0,
                "内门弟子": 1,
                "核心弟子": 2,
                "真传弟子": 3
            }
            identity_ratio = {
                "外门弟子": 1,
                "内门弟子": 2,
                "核心弟子": 5,
                "真传弟子": 10
            }
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_image_fsm:[59:73]
==quick_video_fsm:[59:73]
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    mode = None | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[61:74]
==quick_image_fsm:[59:72]
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_video_fsm:[59:72]
==video_lora_fsm:[58:71]
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。"
        await robust_reply_text(update.message, msg)
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==face_video_fsm:[228:254]
==faceswap_fsm:[162:180]
        )
    )

    # Conversation finished successfully!
    _cleanup_context(context, user_id)
    return ConversationHandler.END

# --- Fallbacks & Timeout ---
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User invoked /cancel during the FSM."""
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"

    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)

    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered when conversation times out (e.g. user took too long)."""
    # Note: Depending on PTB version, timeout might be triggered via different mechanism.
    # But usually it calls the TIMEOUT fallback.
    user_id = update.effective_user.id if update.effective_user else "Unknown" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_video_fsm:[124:138]
==video_lora_fsm:[139:153]
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)

    res = fsm_data['resolution']
    dur = fsm_data['duration']
    reply_markup = get_video_settings_keyboard(user_group, user_identity, res, dur)

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==callbacks.billing_callbacks:[70:79]
==message_handler:[203:214]
    webapp_url = WEBAPP_URL if 'WEBAPP_URL' in globals() and WEBAPP_URL else "https://pay.aivison.it.com/"
    keyboard = [
        [InlineKeyboardButton("💎 TON月卡套餐", web_app=WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton("⭐️ Star月卡套餐", callback_data="recharge_stars_menu")],
        [InlineKeyboardButton("⭐️ Star直充灵石", callback_data="recharge_stars_credit_menu")],
        [InlineKeyboardButton("¥ 人民币充值月卡", callback_data="recharge_rmb_menu")],
        [InlineKeyboardButton("¥ 人民币直充灵石", callback_data="recharge_rmb_credit_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard) | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[50:60]
==quick_image_fsm:[59:69]
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[61:71]
==face_video_fsm:[54:65]
    if is_maintenance_mode():
        msg = "⚠️ 🛠️ **系统正在维护升级中**\n\n为了提供更好的服务，当前生图/生视频节点正在维护，暂不接受新任务。\n\n您的灵石和会员权益不受影响，请稍后再试！"
        if update.callback_query:
            await robust_edit_text(update.callback_query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get('in_conversation'):
        msg = "⚠️ 您当前有未完成的交互流程，请先发送 /cancel 退出当前流程后再试。" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[34:46]
==video_lora_fsm:[44:58]
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Failed to remove {path}: {e}")

async def start_faceswap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Two-person Face Swap (快速换脸)."""
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text="⏳ 任务初始化中...", cache_time=2) | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==ltx_video_fsm:[238:250]
==video_lora_fsm:[235:247]
    cost = int(base_cost * multiplier)

    if not update.effective_user: return ConversationHandler.END
    user = update.effective_user
    if not await permission_service.check_quota(user.id, user.username, user.full_name, context.bot, update.effective_chat.id, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    image_path = fsm_data.pop('image_path', None)
    if not image_path:
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==custom_video_fsm:[267:276]
==video_lora_fsm:[319:328]
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300, | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[210:218]
==quick_image_fsm:[246:254]
                MessageHandler(filters.TEXT & ~filters.COMMAND, unexpected_input)
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300, | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[165:199]
==quick_video_fsm:[292:327]
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"
    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(update.message, "⏰ 操作超时，为节省系统资源，本次流程已自动取消。您可以随时重新开始。")
    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        await robust_reply_text(update.message, "🔄 已为您退出当前输入步骤（后台正在生成的任务不受影响）。\n👉 **请再次点击刚才的按钮**，即可开始新任务！")
        return ConversationHandler.END

    await robust_reply_text(update.message, "⚠️ 当前处于交互流程中。请按提示操作，或发送 /cancel 取消本次操作。")
    return None

def get_quick_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[ | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==face_video_fsm:[232:254]
==quick_video_fsm:[292:307]
    _cleanup_context(context, user_id)
    return ConversationHandler.END

# --- Fallbacks & Timeout ---
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User invoked /cancel during the FSM."""
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。"

    if update.callback_query:
        await robust_edit_text(update.callback_query.message, msg)
    else:
        await robust_reply_text(update.message, msg)

    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def timeout_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered when conversation times out (e.g. user took too long)."""
    # Note: Depending on PTB version, timeout might be triggered via different mechanism.
    # But usually it calls the TIMEOUT fallback.
    user_id = update.effective_user.id if update.effective_user else "Unknown" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==ltx_video_fsm:[317:325]
==video_lora_fsm:[320:328]
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        conversation_timeout=300, | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==custom_video_fsm:[217:226]
==ltx_video_fsm:[260:269]
            update=update,
            context=context,
            prompt=prompt,
            image_path=image_path,
            cleanup=True
        )
    )

    _cleanup_context(context, user_id) | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[127:135]
==quick_image_fsm:[127:135]
    if not update.effective_user: return ConversationHandler.END
    user = update.effective_user
    if not await permission_service.check_quota(user.id, user.username, user.full_name, context.bot, update.effective_chat.id, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    try:
        new_file = await context.bot.get_file(file_id) | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==custom_video_fsm:[221:231]
==face_video_fsm:[227:241]
            cleanup=True
        )
    )

    _cleanup_context(context, user_id)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = "🚫 流程已取消。已清空历史上传内容。" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==clear_stuck_tasks:[53:59]
==zombie_cleaner_service:[43:49]
                if cost > 0 and user_id:
                    try:
                        await permission_service.increment_quota(
                            user_id,
                            cost=-cost,
                            username=username, | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==payment_handler:[94:101]
==src.core.billing_core:[141:148]
            identity_ratio = {
                "外门弟子": 1,
                "内门弟子": 2,
                "核心弟子": 5,
                "真传弟子": 10
            }
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_image_fsm:[44:53]
==quick_video_fsm:[46:55]
    image_path = fsm_data.get('image_path')
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except Exception as e:
            logger.error(f"Failed to remove {image_path}: {e}")

async def start_quick_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 懒人动图 (单步图生视频)""" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_video_fsm:[221:231]
==video_lora_fsm:[229:237]
    if res == "1024p" and dur == "10s":
        res = "720p"
        fsm_data['resolution'] = "720p"

    base_cost = RESOLUTION_COST.get(res, 6)
    multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
    cost = int(base_cost * multiplier)
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==ltx_video_fsm:[104:112]
==quick_video_fsm:[124:132]
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)

    res = fsm_data['resolution']
    dur = fsm_data['duration'] | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==ltx_video_fsm:[156:165]
==quick_video_fsm:[178:187]
    res = fsm_data['resolution']
    dur = fsm_data['duration']

    from src.core.user_core import get_or_create_user_by_telegram
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id

    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id) | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==agent:[17:27]
==main:[76:87]
    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.close()

# Dependency for QueueManager
async def get_queue_manager(redis: Redis = Depends(get_redis)):
    return QueueManager(redis)
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==src.core.task_core:[147:153]
==src.core.task_dispatcher:[233:239]
        dur_str = str(duration).replace("s", "")
        try:
            dur_val = int(dur_str)
        except ValueError:
            dur_val = 5
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==task_service:[270:276]
==utils:[48:53]
            error_msg = str(e)
            if any(kw in error_msg for kw in ["Circuit is open", "All connection attempts failed", "Connection refused", "timeout", "ConnectError"]) or "CircuitBreaker" in str(type(e)):
                user_msg = "当前服务器繁忙，请稍后再试"
            else:
                user_msg = f"系统错误：{error_msg}"
            # status_msg might not be defined if exception occurs early | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[139:144]
==quick_image_fsm:[111:116]
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！") | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[209:215]
==quick_image_fsm:[127:133]
    if not update.effective_user: return ConversationHandler.END
    user = update.effective_user
    if not await permission_service.check_quota(user.id, user.username, user.full_name, context.bot, update.effective_chat.id, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[237:242]
==quick_image_fsm:[184:189]
        create_background_task(
            context,
            TaskService.process_generation_task(
                context, message.chat_id, user_id,
                update.effective_user.username or update.effective_user.full_name, | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[156:161]
==quick_image_fsm:[201:206]
    create_background_task(
        context,
        TaskService.process_generation_task(
            context, message.chat_id, user_id,
            update.effective_user.username or update.effective_user.full_name, | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_image_fsm:[74:81]
==quick_video_fsm:[74:81]
        if key in text:
            mode = val
            break

    if not mode:
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==quick_image_fsm:[137:143]
==quick_video_fsm:[114:120]
        await new_file.download_to_drive(local_path)
        fsm_data['image_path'] = local_path
    except Exception as e:

        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。") | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[49:57]
==faceswap_fsm:[34:42]
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Failed to remove {path}: {e}")

async def start_edit_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 自由P图 and 幻想换脸""" | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==edit_image_fsm:[189:196]
==video_lora_fsm:[213:220]
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[85:90]
==quick_video_fsm:[103:108]
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！") | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[119:124]
==video_lora_fsm:[119:124]
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！") | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==faceswap_fsm:[127:133]
==video_lora_fsm:[237:243]
    if not update.effective_user: return ConversationHandler.END
    user = update.effective_user
    if not await permission_service.check_quota(user.id, user.username, user.full_name, context.bot, update.effective_chat.id, cost=cost):
        _cleanup_context(context, user_id)
        return ConversationHandler.END
 | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==ltx_video_fsm:[94:100]
==video_lora_fsm:[130:135]
        await new_file.download_to_drive(local_path)
        fsm_data['image_path'] = local_path
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, "❌ 下载图片失败，请重试或发送 /cancel 退出。") | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==gallery_apply_fsm:[45:51]
==video_lora_fsm:[52:59]
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text="⏳ 任务初始化中...", cache_time=2)

    from src.utils import is_maintenance_mode
    if is_maintenance_mode(): | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==custom_video_fsm:[180:187]
==video_lora_fsm:[221:227]
    if not fsm_data:
        await robust_reply_text(message, "⚠️ 任务已提交或已过期，请勿重复操作。")
        return ConversationHandler.END

    res = fsm_data['resolution']
    dur = fsm_data['duration'] | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==face_video_fsm:[95:100]
==ltx_video_fsm:[83:88]
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, "❌ 无法识别。请发送图片！") | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==main:[276:282]
==src.web_api.routers.tasks:[153:160]
                        data = message["data"]
                        import json
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        try:
                            parsed = json.loads(data) | - |
| 1 | Medium | 代码重复 (Duplication) | Similar lines in 2 files
==payment_fulfillment_service:[51:56]
==payment_validator:[207:213]
            now = datetime.now()
            new_expire_at = user.identity_expire_at
            converted_days = 0
            final_identity = plan.identity_name
            is_downgrade = False | - |
| 246 | Medium | 死代码 (Dead Code) | unused method 'upload_result_to_minio' (60% confidence) | - |

### 文件: `workers/comfy_agent/workflow_patcher.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 | 重构建议 |
|---|---|---|---|---|
| 65 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=39): patch_workflow | - |
| 159 | High | 代码坏味道 (Smells) | 圈复杂度过高 (CC=40): heuristic_patch | - |
| 8 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=18): WorkflowPatcher | - |
| 30 | Medium | 代码坏味道 (Smells) | 圈复杂度过高 (CC=14): load_workflow | - |
| 74 | Medium | 安全/性能 (Security/Performance) | Standard pseudo-random generators are not suitable for security/cryptographic purposes. | - |
| 151 | Medium | 安全/性能 (Security/Performance) | Standard pseudo-random generators are not suitable for security/cryptographic purposes. | - |

## 3. 架构优化与重构总结

基于核心层的架构规则，以下是针对系统中常见架构问题的通用重构建议：

- **核心层隔离 (Core Isolation)**: 绝对禁止在 `src/core/` 目录中引入特定平台的上下文对象（如 Telegram 的 `Update` 或 FastAPI 的 `Request`）。应使用 `internal_user_id` 等内部模型进行流转。
- **事务管理与退款逻辑 (Transaction & Refund)**: 在外层路由和 Handler 中，避免在捕获异常后手动调用 `refund_credits` 等补偿机制。应统一依赖 Unit of Work (UoW) 进行 `rollback` 和数据状态的一致性保障，防止重复退款。
- **任务与并发控制 (Task Engine & Pub/Sub)**: 后端接口应避免循环轮询任务状态，建议使用 Redis Pub/Sub (`comfy:task_events:{task_id}`) 实现状态的实时触达；任务分发时，必须确保客户端提前生成 `task_id`，防止并发导致的时序问题。
- **避免过度耦合**: 识别模块之间互相引用的部分（循环依赖），通过提取公共接口（Interface）或引入事件总线（Event Bus）来解耦。
