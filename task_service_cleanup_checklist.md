# task_service 清理清单（当前批次）

校准时间: 2026-05-23

## 1. 处理原则

- 优先删除只为旧测试保留、且当前主路径不再依赖的 compat 壳
- 保留 Telegram 表示层必须承担的入口绑定、消息适配和 patch 点
- 暂缓删除仍被 focused tests 大量直接 monkeypatch 的 seam，先迁测试再收口

## 2. 该删

| 对象 | 类型 | 原因 | 当前动作 |
| --- | --- | --- | --- |
| `task_service.py::_COMPAT_TEST_EXPORTS` | compat 常量 | 仅服务旧 monkeypatch，运行时无引用 | 本批删除 |
| `task_service.py` 中仅为 `_COMPAT_TEST_EXPORTS` 保留的 `UserLogger` / `image_service` / `TaskRegistry` 导入 | compat 导入 | 本文件运行时无实际用途 | 本批删除 |
| `src/tests/test_task_service_refactored.py` | 旧测试 | 继续依赖已过时 compat patch 面，且与 `tests/services/*` 新测试体系重复 | 本批删除 |
| `src/tests/test_queue_logic.py` | 旧脚本式测试 | 非标准测试风格，继续绑 `task_service.image_service`，与现有 focused tests 重叠 | 本批删除 |

## 3. 该留

| 对象 | 类型 | 原因 | 后续策略 |
| --- | --- | --- | --- |
| `TaskService.process_*` 系列公开入口 | 稳定入口 | handlers / FSM / callbacks 仍直接依赖 | 继续保留 |
| `TaskService._run_bot_task_flow` | 门面桥接 | 承接 entrypoints 到 flow/completion/finalize 的组合装配，且仍是 entrypoint focused tests 稳定 patch 面 | 暂保留，后续减层 |
| `TaskService._complete_monitored_bot_task` | seam/patch 点 | focused tests 明确依赖该桥接层，并负责注入 Telegram 表示层 seam | 暂保留，后续评估 |
| `_finalize_*_for_bot` / `_send_bot_*` / `_cleanup_runtime_state_if_needed` | Telegram 表示层适配 | 负责把 `robust_*` seam 注入 finalize helper | 保留 |

## 4. 暂缓

| 对象 | 类型 | 暂缓原因 | 退出条件 |
| --- | --- | --- | --- |
| `task_service_flow.py` 中大批 `*_func` 注入 seam | 测试 seam | `tests/services/test_task_service_flow.py` 仍直接依赖 | 先迁测试，再评估合并 |
| `task_service_completion.py` 中 `handle_task_completion_func` 等注入 seam | 测试 seam | `tests/services/test_task_service_completion.py` 仍直接依赖 | 先迁测试，再评估缩面 |
| `TaskService` 类内若干私有 `_prepare_* / _run_* / _complete_*` | patch 面 | 仍是当前 focused tests 的 monkeypatch 入口；其中 `_run_bot_task_flow` 当前牵动多个 entrypoint 用例 | 先建立盘点表，逐步收口 |

## 5. 当前批次实施项

1. 删除 `_COMPAT_TEST_EXPORTS`
2. 删除 `task_service.py` 中仅服务 compat 的无效导入
3. 保持 `TaskService` 类内关键 patch 面不动
4. 清理两份继续绑旧 compat 面的旧测试
5. 跑 `task_service` 相邻 focused tests，确认不回归

## 6. 本轮新增进展

- `TaskService._complete_monitored_bot_task` 现在通过 `task_service_completion` 模块运行时调用 `complete_monitored_bot_task(...)`
- `tests/services/test_task_service_completion.py` 中对应 monkeypatch 已从 `src.services.task_service.complete_monitored_bot_task` 下沉到 `src.services.task_service_completion.complete_monitored_bot_task`
- 这意味着 `_complete_monitored_bot_task` 周围的一层 patch 面已开始从 `task_service.py` 模块级符号迁往真实 helper 模块
- `TaskService._handle_task_completion` 已删除，相关测试与默认调用均已下沉到 `src.services.task_service_completion.handle_task_completion`
- `TaskService._download_and_log_task_output` 已删除，默认 `download_and_log_task_output` seam 已下沉到 `src.services.task_service_completion.download_and_log_task_output`
- `tests/services/test_task_service_completion.py` 中对应下载/完成 seam 的 monkeypatch 与直调测试均已下沉到真实 helper 模块
- `TaskService._build_result_reply_markup`、`TaskService._record_result_message_meta` 两个仅供测试直调的静态壳已删除，相关测试改为直打 `tg_task_runtime` helper
- `TaskService._monitor_task_progress` 已删除，`robust_edit_text` seam 直接由 `TaskService._monitor_submitted_bot_task -> task_service_completion.monitor_submitted_bot_task(...)` 注入
- `task_service.py` 现对 `complete_monitored_bot_task`、`handle_task_completion`、`download_and_log_task_output`、`monitor_submitted_bot_task` 均统一为运行时经真实 helper 模块取值，不再保留本地导入副本
- `TaskService._monitor_submitted_bot_task` 已删除；`_run_bot_task_flow` 现在直接把 `get_user_priority_and_identity`、`monitor_bot_task_progress` 与 `robust_edit_text` seam 注给 `task_service_completion.monitor_submitted_bot_task(...)`
- `TaskService._prepare_and_submit_bot_task` 已删除；`_run_bot_task_flow` 现在直接把 `with_submitted_status`、`get_or_send_status_msg`、`send_initial_task_status`、`submit_bot_task`、`update_submitted_task_status` 以及 `robust_reply_text/robust_edit_text` seam 注给 `task_service_flow.prepare_and_submit_bot_task(...)`
- 当前 `TaskService` 仍建议暂保留 `_run_bot_task_flow`，因为它仍是多个 entrypoint focused tests 的稳定 patch 面，继续硬拆收益暂时低于风险
- `src/services/bot_task_service.py` 现已反转为 Telegram Bot task facade 的主实现模块，`src/services/task_service.py` 仅保留 compat re-export 壳；新代码与 focused tests 开始改贴 `bot_task_service` 入口
- `src/handlers/message_handler.py` 内仅作历史表象的 `process_generation_task = task_service.process_generation_task` 模块级别名已删除，减少主路径的旧命名回流
