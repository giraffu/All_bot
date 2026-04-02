# 代码质量清理报告

日期：2026-04-02

## 已完成清理

### 删除的死代码、调试文件与垃圾文件

- 根目录调试/测试脚本：
  - `test_db.py`
  - `test_db2.py`
  - `test_users_query.py`
- Backend：
  - `backend/perform_api_test.py`
  - `backend/workflows/debug_patched_face_swap.json`
  - `backend/workflows/debug_patched_img2img.json`
  - `backend/workflows/debug_patched_t2i-pornmaster-turbo.json`
  - `backend/workflows/debug_patched_video_edit.json`
  - `backend/workflows/debug_patched_video_insert.json`
- Dashboard：
  - `dashboard/check_plans_debug.py`
  - `dashboard/test_db.py`
  - `dashboard/frontend/src/components/HelloWorld.vue`
- Frontend：
  - `frontend/test_parse_boc_2.py`
- Bot：
  - `src/services/task_service.py.orig`
- Workers：
  - `workers/comfy_agent1/test_patch.py`
  - `workers/comfy_agent1/workflows/debug_patched_face_swap.json`
  - `workers/comfy_agent1/workflows/debug_patched_img2img.json`
  - `workers/comfy_agent1/workflows/debug_patched_t2i-pornmaster-turbo.json`
  - `workers/comfy_agent1/workflows/debug_patched_video_edit.json`
  - `workers/comfy_agent1/workflows/debug_patched_video_insert.json`
  - `workers/comfy_agent2/workflows/debug_patched_face_swap.json`
  - `workers/comfy_agent2/workflows/debug_patched_img2img.json`
  - `workers/comfy_agent2/workflows/debug_patched_t2i-pornmaster-turbo.json`
  - `workers/comfy_agent2/workflows/debug_patched_video_edit.json`
  - `workers/comfy_agent2/workflows/debug_patched_video_insert.json`
  - `workers/comfy_agent3/workflows/debug_patched_face_swap.json`
  - `workers/comfy_agent3/workflows/debug_patched_img2img.json`
  - `workers/comfy_agent3/workflows/debug_patched_t2i-pornmaster-turbo.json`
  - `workers/comfy_agent3/workflows/debug_patched_video_edit.json`
  - `workers/comfy_agent3/workflows/debug_patched_video_insert.json`

### 代码优化

- 清理生产代码与测试代码中的未使用 import / 未使用变量。
- 修复 `backend/app/main.py` 中任务状态接口未回传 `image_url` 的问题。
- 保持 Dashboard 与主 Frontend 构建通过。
- 扩展 `.gitignore`，防止以下产物再次进入仓库：
  - `*.tmp`
  - `*.temp`
  - `*.bak`
  - `*.backup`
  - `*.orig`
  - `project_analysis.json`
  - `project_tree.txt`
  - `**/debug_patched_*.json`
  - `workers/comfy_agent*/input/`

## 静态分析结果

### 已解决

- `ruff check . --select F401,F841`：通过

### 复杂度热点

- `src/handlers/callback_handler.py`：`handle_callback_query` 复杂度高
- `src/handlers/message_handler.py`：`handle_prompt`、`handle_photo`、`handle_document` 复杂度高
- `dashboard/backend/routers/stats.py`：`get_stats`、`get_stats_history` 复杂度高
- `src/services/task_service.py`：任务提交、进度监控、完成处理逻辑复杂
- `workers/comfy_agent*/agent_main.py`：`process_task` 与 `ws_listener_loop` 复杂度高
- `workers/comfy_agent*/workflow_patcher.py`：`heuristic_patch` 复杂度高

### 结构性问题

- `workers/comfy_agent1`、`workers/comfy_agent2`、`workers/comfy_agent3` 存在大面积复制代码，建议后续抽取共享模块。
- `src/handlers` 与 `dashboard/backend/routers/stats.py` 已出现“单函数承载过多职责”的迹象，建议拆分为更细的服务函数。
- `src/services/task_registry.py` 中 `refund_all` 当前为占位行为，建议后续明确其维护职责。

## 验证结果

- `npm run build` in `dashboard/frontend`：通过
- `npm run build` in `frontend`：通过
- `python -m py_compile` 定向编译 17 个修改后的 Python 文件：通过
- `pytest backend/tests src/tests/test_imports.py src/tests/test_task_service_refactored.py src/tests/test_text_to_image.py`：
  - 受现有环境配置影响未能直接运行
  - 已定位为 `backend/app/config.py` 的 `Settings` 对现有环境变量报 `extra_forbidden`
  - 属于现有测试/环境装配问题，不是本次清理引入的问题

## 未自动清理项

- `workers/comfy_agent1/input/` 下存在大量运行期媒体文件，且文件所有者为 `root`，当前会话无权限删除。
- 这些文件已通过 `.gitignore` 屏蔽后续跟踪，但如需清空工作区，需在宿主机使用具备权限的账号执行额外清理。
