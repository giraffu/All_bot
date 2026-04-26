# 全局代码静态分析与质量评估报告

> 自动生成的静态分析报告，包含死代码、注释、导入、作用域、代码重复、性能、架构和代码坏味道。


## 📊 可量化指标

- **总代码行数 (LOC)**: 91798
- **平均圈复杂度**: B (5.3692077727952165)
- **代码重复率**: 0.00% (0 行)
- **死代码预估比例**: 0.18% (164 处)


## 🚨 详细问题列表 (按严重程度)

### 🔴 Critical (致命)

| 文件路径 | 行号 | 问题类型 | 具体描述 |
|---|---|---|---|
| `src/core/auth_core.py` | 8 | 架构问题 (Architecture) | Core 层代码违反隔离原则，直接引入了外部依赖 (telegram/fastapi)。建议：重构为依赖倒置或通过接口/DTO传递参数。 |


### 🟠 High (高危)

| 文件路径 | 行号 | 问题类型 | 具体描述 |
|---|---|---|---|
| `backend/app/main.py` | 56 | 作用域/内存风险 (Scope/Memory) | Using the global statement |


### 🟡 Medium (中等)

| 文件路径 | 行号 | 问题类型 | 具体描述 |
|---|---|---|---|
| `src/api_client.py` | 68 | 代码坏味道 (Code Smell) | Too many arguments (7/5) |
| `src/api_client.py` | 87 | 代码坏味道 (Code Smell) | Too many arguments (7/5) |
| `src/api_client.py` | 105 | 代码坏味道 (Code Smell) | Too many arguments (8/5) |
| `src/api_client.py` | 152 | 代码坏味道 (Code Smell) | Too many arguments (7/5) |
| `src/api_client.py` | 200 | 代码坏味道 (Code Smell) | Too many arguments (6/5) |
| `src/api_client.py` | 237 | 代码坏味道 (Code Smell) | Too many arguments (7/5) |
| `src/api_client.py` | 287 | 代码坏味道 (Code Smell) | Too many local variables (18/15) |
| `src/api_client.py` | 287 | 复杂度过高 (High Complexity) | Too many branches (23/12) |
| `src/api_client.py` | 287 | 复杂度过高 (High Complexity) | Too many statements (79/50) |
| `src/constants.py` | 170 | 代码坏味道 (Code Smell) | Too many local variables (23/15) |
| `src/logger.py` | 24 | 代码坏味道 (Code Smell) | Too few public methods (1/2) |
| `src/logger.py` | 107 | 代码坏味道 (Code Smell) | Too many arguments (8/5) |
| `src/bot_test.py` | 34 | 代码坏味道 (Code Smell) | Too many arguments (6/5) |
| `src/bot_test.py` | 117 | 代码坏味道 (Code Smell) | Too many local variables (20/15) |
| `src/bot_test.py` | 117 | 复杂度过高 (High Complexity) | Too many statements (52/50) |
| `src/core/task_core.py` | 28 | 代码坏味道 (Code Smell) | Too many arguments (12/5) |
| `src/core/task_core.py` | 28 | 代码坏味道 (Code Smell) | Too many local variables (20/15) |
| `src/core/task_core.py` | 101 | 代码坏味道 (Code Smell) | Too many arguments (17/5) |
| `src/core/task_core.py` | 101 | 代码坏味道 (Code Smell) | Too many local variables (32/15) |
| `src/core/task_core.py` | 101 | 复杂度过高 (High Complexity) | Too many branches (26/12) |
| `src/core/task_core.py` | 101 | 复杂度过高 (High Complexity) | Too many statements (58/50) |
| `src/core/task_core.py` | 291 | 代码坏味道 (Code Smell) | Too many arguments (9/5) |
| `src/core/task_core.py` | 291 | 代码坏味道 (Code Smell) | Too many local variables (21/15) |
| `src/core/task_core.py` | 351 | 代码坏味道 (Code Smell) | Too many arguments (6/5) |
| `src/core/task_core.py` | 351 | 代码坏味道 (Code Smell) | Too many local variables (41/15) |
| `src/core/task_core.py` | 351 | 复杂度过高 (High Complexity) | Too many branches (18/12) |
| `src/core/task_core.py` | 351 | 复杂度过高 (High Complexity) | Too many statements (74/50) |
| `src/core/gallery_core.py` | 43 | 代码坏味道 (Code Smell) | Too many local variables (28/15) |
| `src/core/gallery_core.py` | 43 | 复杂度过高 (High Complexity) | Too many branches (13/12) |
| `src/core/gallery_core.py` | 43 | 复杂度过高 (High Complexity) | Too many statements (54/50) |
| `src/core/auth_core.py` | 98 | 代码坏味道 (Code Smell) | Too many local variables (17/15) |
| `src/core/auth_core.py` | 139 | 代码坏味道 (Code Smell) | Unused variable 'is_new' |
| `src/web_api/dependencies.py` | 30 | 代码坏味道 (Code Smell) | Too many local variables (17/15) |
| `src/web_api/core/config.py` | 6 | 代码坏味道 (Code Smell) | Too few public methods (0/2) |
| `src/web_api/schemas/auth_schema.py` | 43 | 代码坏味道 (Code Smell) | Too few public methods (0/2) |
| `src/web_api/schemas/user_schema.py` | 16 | 代码坏味道 (Code Smell) | Too few public methods (0/2) |
| `src/web_api/schemas/task_schema.py` | 12 | 代码坏味道 (Code Smell) | Too few public methods (0/2) |
| `src/web_api/routers/tasks.py` | 78 | 代码坏味道 (Code Smell) | Too many local variables (23/15) |
| `src/web_api/routers/tasks.py` | 190 | 复杂度过高 (High Complexity) | Too many nested blocks (6/5) |
| `src/web_api/routers/tasks.py` | 78 | 复杂度过高 (High Complexity) | Too many branches (29/12) |
| `src/web_api/routers/tasks.py` | 78 | 复杂度过高 (High Complexity) | Too many statements (111/50) |
| `src/web_api/routers/tasks.py` | 59 | 复杂度过高 (High Complexity) | Too many statements (119/50) |
| `src/web_api/routers/gallery.py` | 81 | 代码坏味道 (Code Smell) | Too many arguments (8/5) |
| `src/web_api/routers/gallery.py` | 81 | 代码坏味道 (Code Smell) | Too many local variables (37/15) |
| `src/web_api/routers/gallery.py` | 81 | 复杂度过高 (High Complexity) | Too many branches (16/12) |
| `src/web_api/routers/gallery.py` | 81 | 复杂度过高 (High Complexity) | Too many statements (60/50) |
| `src/web_api/routers/gallery.py` | 207 | 代码坏味道 (Code Smell) | Too many local variables (28/15) |
| `src/web_api/routers/gallery.py` | 294 | 代码坏味道 (Code Smell) | Too many local variables (30/15) |
| `backend/app/main.py` | 181 | 代码坏味道 (Code Smell) | Too many local variables (22/15) |
| `backend/app/main.py` | 181 | 复杂度过高 (High Complexity) | Too many statements (64/50) |
| ... | ... | ... | *还有 79 个类似问题省略* |


### 🟢 Low (低优先级)

| 文件路径 | 行号 | 问题类型 | 具体描述 |
|---|---|---|---|
| `backend/app/config.py` | 15 | 死代码 (Dead Code) | unused variable 'minio_bucket' (60% confidence) |
| `backend/app/config.py` | 17 | 死代码 (Dead Code) | unused variable 'minio_template_bucket' (60% confidence) |
| `backend/app/config.py` | 22 | 死代码 (Dead Code) | unused variable 'minio_input_bucket' (60% confidence) |
| `backend/app/config.py` | 25 | 死代码 (Dead Code) | unused variable 'env_file' (60% confidence) |
| `backend/app/main.py` | 53 | 死代码 (Dead Code) | unused function 'startup_event' (60% confidence) |
| `backend/app/main.py` | 70 | 死代码 (Dead Code) | unused function 'shutdown_event' (60% confidence) |
| `backend/app/main.py` | 79 | 死代码 (Dead Code) | unused function 'create_img2img_task' (60% confidence) |
| `backend/app/main.py` | 90 | 死代码 (Dead Code) | unused function 'create_img2img_lora_task' (60% confidence) |
| `backend/app/main.py` | 101 | 死代码 (Dead Code) | unused function 'create_face_swap_task' (60% confidence) |
| `backend/app/main.py` | 112 | 死代码 (Dead Code) | unused function 'create_video_insert_task' (60% confidence) |
| `backend/app/main.py` | 123 | 死代码 (Dead Code) | unused function 'create_video_edit_task' (60% confidence) |
| `backend/app/main.py` | 134 | 死代码 (Dead Code) | unused function 'create_video_lora_task' (60% confidence) |
| `backend/app/main.py` | 147 | 死代码 (Dead Code) | unused function 'create_face_video_task' (60% confidence) |
| `backend/app/main.py` | 158 | 死代码 (Dead Code) | unused function 'create_i2i_pro_task' (60% confidence) |
| `backend/app/main.py` | 169 | 死代码 (Dead Code) | unused function 'create_ltx_video_task' (60% confidence) |
| `backend/app/main.py` | 180 | 死代码 (Dead Code) | unused function 'create_t2i_pornmaster_turbo_task' (60% confidence) |
| `backend/app/main.py` | 283 | 死代码 (Dead Code) | unused function 'get_task_status_v1' (60% confidence) |
| `backend/app/main.py` | 343 | 死代码 (Dead Code) | unused function 'get_task_image' (60% confidence) |
| `backend/app/main.py` | 379 | 死代码 (Dead Code) | unused function 'get_task_video' (60% confidence) |
| `backend/app/main.py` | 413 | 死代码 (Dead Code) | unused function 'get_system_workers' (60% confidence) |
| `backend/app/models.py` | 43 | 死代码 (Dead Code) | unused variable 'last_seen' (60% confidence) |
| `backend/app/models.py` | 45 | 死代码 (Dead Code) | unused variable 'current_task_type' (60% confidence) |
| `backend/app/models.py` | 46 | 死代码 (Dead Code) | unused variable 'current_task_progress' (60% confidence) |
| `backend/app/models.py` | 47 | 死代码 (Dead Code) | unused variable 'current_task_created_at' (60% confidence) |
| `backend/app/models.py` | 60 | 死代码 (Dead Code) | unused variable 'image' (60% confidence) |
| `backend/app/models.py` | 61 | 死代码 (Dead Code) | unused variable 'image2' (60% confidence) |
| `backend/app/models.py` | 65 | 死代码 (Dead Code) | unused variable 'num_inference_steps' (60% confidence) |
| `backend/app/models.py` | 66 | 死代码 (Dead Code) | unused variable 'guidance_scale' (60% confidence) |
| `backend/app/models.py` | 71 | 死代码 (Dead Code) | unused variable 'image' (60% confidence) |
| `backend/app/models.py` | 72 | 死代码 (Dead Code) | unused variable 'image2' (60% confidence) |
| `backend/app/models.py` | 76 | 死代码 (Dead Code) | unused variable 'num_inference_steps' (60% confidence) |
| `backend/app/models.py` | 77 | 死代码 (Dead Code) | unused variable 'guidance_scale' (60% confidence) |
| `backend/app/models.py` | 84 | 死代码 (Dead Code) | unused variable 'face_image' (60% confidence) |
| `backend/app/models.py` | 85 | 死代码 (Dead Code) | unused variable 'body_image' (60% confidence) |
| `backend/app/models.py` | 89 | 死代码 (Dead Code) | unused variable 'image' (60% confidence) |
| `backend/app/models.py` | 97 | 死代码 (Dead Code) | unused variable 'image' (60% confidence) |
| `backend/app/models.py` | 105 | 死代码 (Dead Code) | unused variable 'image' (60% confidence) |
| `backend/app/models.py` | 114 | 死代码 (Dead Code) | unused variable 'face_image' (60% confidence) |
| `backend/app/models.py` | 121 | 死代码 (Dead Code) | unused variable 'image' (60% confidence) |
| `backend/app/models.py` | 127 | 死代码 (Dead Code) | unused variable 'image' (60% confidence) |
| `backend/app/queue_manager.py` | 116 | 死代码 (Dead Code) | unused method 'get_task_by_prompt_id' (60% confidence) |
| `backend/app/queue_manager.py` | 254 | 死代码 (Dead Code) | unused method 'clear_running_tasks' (60% confidence) |
| `backend/app/routers/agent.py` | 56 | 死代码 (Dead Code) | unused function 'pop_task' (60% confidence) |
| `backend/app/routers/agent.py` | 59 | 死代码 (Dead Code) | unused variable 'authorized' (100% confidence) |
| `backend/app/routers/agent.py` | 78 | 死代码 (Dead Code) | unused function 'check_task' (60% confidence) |
| `backend/app/routers/agent.py` | 81 | 死代码 (Dead Code) | unused variable 'authorized' (100% confidence) |
| `backend/app/routers/agent.py` | 89 | 死代码 (Dead Code) | unused function 'update_status' (60% confidence) |
| `backend/app/routers/agent.py` | 92 | 死代码 (Dead Code) | unused variable 'authorized' (100% confidence) |
| `backend/app/routers/agent.py` | 110 | 死代码 (Dead Code) | unused variable 'authorized' (100% confidence) |
| `backend/app/routers/agent.py` | 121 | 死代码 (Dead Code) | unused function 'task_heartbeat' (60% confidence) |
| ... | ... | ... | *还有 216 个类似问题省略* |


## 🏗️ 架构重构建议

1. **核心层隔离**：严格遵守 `AGENTS.md` 中定义的 Core Isolation 原则，`src/core/` 下的模块不应直接导入 `telegram` 或框架特有对象。

2. **降低模块耦合**：部分模块存在较高的圈复杂度，尤其是处理回调和消息的 Handler，建议使用策略模式 (Strategy Pattern) 或责任链模式重构。

3. **清理死代码**：上述报告列出的未调用函数和类建议通过 `vulture` 进行二次人工确认后删除，减小代码库体积。

4. **解耦导入依赖**：修复报告中的 `cyclic-import`（循环导入），建议提取公共接口或调整初始化顺序。
