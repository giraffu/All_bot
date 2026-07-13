# 子模块: 代码静态分析与质量评估规范 (Code Quality & Static Analysis)

## 1. 目标与范围
为了确保修仙主题 AI 创作工作台 (All_Bot) 在持续迭代中保持高内聚、低耦合的架构，系统必须定期进行全局静态代码分析与质量评估。本规范定义了在执行全面审查时的统一标准、关键检查维度以及自动化排查的静默与无痕输出要求。

## 2. 静态分析核心维度

在进行全面扫描时，必须涵盖以下 8 个维度的深度检查：

1. **死代码检测 (Dead Code)**：识别未被调用的函数、类、变量和未使用的导入语句。
2. **注释清理 (Comment Cleanup)**：标记过时、错误或误导性的注释，包括 TODO/FIXME 等长期遗留的占位符。
3. **导入优化 (Import Optimization)**：检查未使用的 import、循环依赖、冗余导入和导入顺序问题（尤其关注避免与 Core Isolation 冲突的导入）。
4. **作用域分析 (Scope & Namespace)**：识别变量作用域冲突、全局变量滥用、闭包导致的副作用。
5. **代码重复 (Code Duplication)**：通过逻辑相似度检测找出可提取的通用逻辑或重复粘贴代码。
6. **性能风险 (Performance Risks)**：标记低效算法、数据库 N+1 查询隐患、内存泄漏风险、事件循环中错误的同步阻塞操作。
7. **架构违规 (Architecture Violation)**：识别违反分层原则（如 Core 层引入了 Web 请求对象）、过度耦合、违反单一职责的模块。
8. **代码坏味道 (Code Smells)**：指出过长的函数或类、过深的嵌套层级、过多的参数列表、极度复杂的条件判断（高圈复杂度）。

## 3. 全局代码质量检测 SOP (Standard Operating Procedure)

当需要对系统代码进行全面静态分析时，请严格按照以下标准化步骤操作。此规范已封装为 `allbot-code-analyzer` AI 技能。

### 3.1 静态代码分析（静默执行）
- **分析范围**：对项目所有核心代码进行全局扫描与评估。
- **执行要求**：分析过程中仅做代码读取、逻辑解析与记录，**绝对禁止修改任何现有代码或功能**。
- **无痕记录**：采集到的所有代码切片与诊断结果必须暂存到专用的临时文件或内存变量中，不要在控制台或对话窗口打印长篇的原始代码或中间检测结果。

### 3.2 质量评估与重构建议
- **问题分级 (Triage)**：所有发现的问题必须按严重程度分为四级：Critical（致命违规）、High（高风险）、Medium（中等）、Low（建议优化）。
- **量化指标 (Metrics)**：评估并输出项目的宏观健康度指标，例如：代码重复率估值、死代码比例、平均圈复杂度等。
- **架构级建议**：针对检测出的“架构违规”，需提供明确、可落地的重构方向与思路。

### 3.3 报告生成与清理规范（核心要求）
- **生成报告**：输出一份结构清晰的 Markdown 分析报告，必须包含：
  - 分析时间范围与涵盖的核心目录。
  - 全局质量量化指标总览。
  - 核心问题清单：按优先级降序排列，每个条目必须包含**文件路径、行号、问题类型、严重程度、具体描述**。
  - 架构优化与重构建议汇总。
- **保存文件**：将报告统一命名为 `code_analysis_report_<yyyyMMdd_HHmm>.md`，使用 UTF-8 编码，写入项目根目录的 `logs/` 文件夹下。
- **清理中间产物**：**强制要求**在报告成功写入磁盘后，必须立即通过 Shell 命令彻底删除分析过程中产生的所有临时分析缓存、切片或暂存数据。
- **最终输出**：排查结束时，仅在终端或对话中输出“报告已生成完毕”及文件的绝对路径，并简要总结全局量化指标与 Critical 级核心风险。**严禁输出大段代码或中间检测细节。**

## 4. 历史质量基线

2026-06-03 历史全局评估报告位于 `logs/code_analysis_report_20260603_2332.md`，评估范围覆盖 `src/`、`backend/app/`、`workers/comfy_agent/`、`frontend/src/`、`tests/` 与核心部署脚本，并按当次要求降权或排除了 Dashboard、支付/订单/会员/affiliate 业务模块。

### 4.1 当前总体结论
- 系统整体已经稳定演进为“Bot/Web 双入口 + task core facade + Central API + Worker + Web side-effect monitor”的分层形态。
- `src/core` 未发现直接依赖 Telegram `Update` 或 FastAPI `Request/APIRouter` 等平台对象，Core Isolation 当前成立。
- 未发现 Critical 级架构阻断；后续重点是控制热点函数、测试耦合、workflow 资产漂移与 compat 壳残留。

### 4.2 关键量化指标
- 主代码规模约 75,857 行，测试规模约 33,634 行。
- Python 复杂度块 1,832 个，平均圈复杂度约 2.94，整体为 A。
- A 级复杂度约 86.8%，D 级复杂度 5 个。
- 重复窗口估计约 2.3%，主要集中在 FSM 与生成页。
- 静态 import graph 未发现 Python 模块强循环依赖。
- `vulture --min-confidence 80` 未发现高置信死代码。
- `ruff` 剩余 34 条，主要是 E402、E712 与测试小问题。
- 主站前端 `vue-tsc --noEmit -p tsconfig.app.json` 通过；Dashboard 前端也已启用 `typescript` / `vue-tsc` / `@vue/tsconfig`，`npm run build` 会先执行类型检查。

### 4.3 当前 P1/P2 整改队列
- **workflow 资产事实源**：workflow 已收口到 `workers/comfy_agent/workflows`，Central API 不再维护 backend 副本或执行 workflow 启动校验。新增或修改 workflow 时仍需复核 Worker 映射、patcher 和 `SUPPORTED_TASK_TYPES`。
- **task core provider 契约**：`TaskCoreServiceProviders` 与主要 capability 已引入 `Protocol` / 精确 `Callable` 类型。后续新增 provider/capability 应继续保持显式类型，并让测试走 dependencies seam，而不是扩大模块级 patch。
- **高复杂编排热点**：`workers/comfy_agent/agent_main.py::process_task`、`src/web_api/services/wan22_history_chain_service.py::stitch_wan22_history_chain_response` 与 `frontend/src/composables/useLabWorkbench.ts` 仍是后续拆分优先级；`src/web_api/services/gallery_response_builder.py::build_post_responses` 已先拆出 bulk loader，`src/services/tg_task_runtime.py::monitor_task_progress` 已拆出纯状态渲染。
- **测试耦合**：现有测试仍大量 patch `AsyncSessionLocal`、模块级导入符号、全局单例与 runtime。新增测试优先通过公开 dependencies/dataclass 或 service seam 注入能力。
- **compat / 冗余清理**：`src/core/gallery_feed_queries.py`、`src/services/wan22_video_v2_config.py`、`src/services/wan22_video_v2_context.py` 与未引用的 `src/context.py:trace_id_ctx` 已删除；调用方已迁到真实 service/domain_config 或 `asgi_correlation_id.correlation_id` 入口。

### 4.4 知识库同步要求
- 代码质量报告写入 `logs/`，不作为长期入口文档；重要结论应同步到本文件、热点门禁、compat 退出表以及相关 Skill。
- 若报告发现的事实与 Skill 主张冲突，应先修 Skill，再继续开发。例如 Worker 虽已拆出多个 helper，但 `agent_main.py::process_task` 仍是当前执行链路热点，不能只写成“已完全薄壳化”。
- 若后续清理 compat 壳或迁移测试 seam，必须同步 `docs/compat_seam_exit_table.md` 与 `scripts/check_compat_registry.sh` 覆盖口径。

## 5. 2026-06-18 复核快照

最近一次完整复核报告位于 `logs/code_analysis_report_20260618_0306.md`。该轮覆盖 `src/`、`backend/app/`、`dashboard/backend/`、`workers/comfy_agent/`、`remote_workers/`、`ops/`、`scripts/` 与 `tests/`，并同步抽查知识库、部署 compose、云正式/云测试控制面和运行态资源。

当前结论：
- 未发现 Critical / High 级架构阻断。
- `src/core` 未发现 Telegram `Update`、FastAPI `Request/APIRouter` 等平台对象 import，Core Isolation 成立。
- Alembic 当前为单 head `7f3a9c1d2e4b`。
- 中等维护风险集中在 `workers/comfy_agent/agent_main.py`、`dashboard/backend/services/runpod_admin_service.py` 与 `src/web_api/services/task_submission_service.py`，后续改动应优先加 focused regression。

## 6. 2026-06-24 知识库校准轻量复核

本轮不是完整全局代码质量报告，只用于校准实时知识库中的可验证事实。

当前结果：
- Alembic 当前为单 head `7f3a9c1d2e4b`。
- `pytest --collect-only -q` 可收集 `1678` 个测试，用时约 74 秒；未执行完整测试套件。
- `ruff check --statistics` 剩余 `2` 个 `F401`，均为 `ops/gpu_pool_controller/runpod_pod_request.py` 中未使用的 RunPod LTX import。
- 文档结构检查 `python scripts/doc_quality_checker.py` 通过。

## 7. 2026-06-27 知识库校准轻量复核

本轮基于 `deploy` 分支 `2bd2866` 重新校准实时知识库，不做远端 SSH、线上 curl、Docker 运行态探测或完整测试执行。

当前结果：
- `src/core` 未发现 Telegram `Update`、FastAPI `Request/APIRouter` 等平台对象 import，Core Isolation 当前成立。
- Alembic 当前为单 head `7f3a9c1d2e4b`。
- `pytest --collect-only -q` 可收集 `1778` 个测试，用时约 118 秒；未执行完整测试套件。
- `ruff check --statistics` 剩余 `7` 个可自动修复问题：`local_analytics_platform/app/main.py` 1 个 `F541`，`local_analytics_platform/app/prompt_vectors.py`、`ops/gpu_pool_controller/runpod_pod_request.py`、`scripts/import_minio_bucket_normalized.py`、`tests/local_analytics/test_prompt_vectors_refresh.py` 与 `tests/scripts/test_cloud_prod_shadow_sync.py` 合计 6 个 `F401`。
- 文档结构检查 `python scripts/doc_quality_checker.py` 通过。

## 8. 2026-07-11 全仓静态复核

本轮覆盖 `src/`、`backend/`、`dashboard/backend/`、`workers/`、`remote_workers/`、`ops/`、`local_analytics_platform/`、`paid_group_guard_bot/`、`qqcc_bot/`、`scripts/`、前端源码、测试、compose、Skills 与实时文档；未执行远端 SSH、线上 API、Docker、Redis/PostgreSQL 或 Cloudflare 运行态探测，也未运行完整测试套件。完整报告位于 `logs/code_analysis_report_20260711_2140.md`。

当前结果：

- 1513 个 tracked 文件；769 个 Python 文件；Python/TypeScript/TSX/Vue/JavaScript/Shell 合计约 291,440 行，包含测试、生成/供应商静态资源与双 worker bundle。
- Alembic 为单 head `2d8b6f1a9c03`；`pytest --collect-only -q` 收集 2240 个测试，用时约 76 秒。
- `ruff check . --statistics` 零告警；`python scripts/doc_quality_checker.py` 通过。
- Radon 扫描 5335 个 Python block，平均圈复杂度 3.49；A/B/C/D/E/F 分别为 4391/683/220/32/7/2，41 个 block 复杂度不低于 21。最高两个热点是 `_refresh_prompt_token_stats_unindexed`（48）与 `execute_qqcc_draw_scene_chain`（41）。
- Symilar 对非测试 Python 使用 8 行窗口估算重复率为 4.45%；主要重复是 `workers/comfy_agent` 与 `remote_workers/comfy_agent` 的部署 bundle 镜像。该重复有部署目的，但需要自动同步/漂移门禁，不能视为普通可删除复制。
- Vulture 90% 置信度报告 2 个不可达候选；人工核对后均为包含显式 `break` 的异步分页循环误报，本轮未确认高置信死代码。死代码比例记为“0 个已确认候选 / 769 个 Python 文件”，不把工具误报换算成虚假百分比。
- Core 平台对象隔离仍成立：未发现 Telegram `Update`、FastAPI `Request/APIRouter` import；但基础设施隔离只部分完成，core 仍直接依赖 `config`、SQLAlchemy、HTTPX、PIL/subprocess 与默认 provider。后续应通过 composition root 和 capability adapter 迁移，不应继续把“无平台对象”写成“core 只消费 capability/provider 已完成”。

本轮未发现 Critical 级阻断。High/Medium 整改优先级依次为：收窄 core 基础设施 interface、拆分两个 F 级编排热点、为双 worker bundle 建立单事实源生成/同步门禁、继续拆分 1000 行以上高变更模块。知识库更新不授权直接执行这些业务重构。
