# All_Bot 代码质量优化执行清单

更新时间: 2026-05-25

文档目标:
- 基于当前仓库代码现状，回写 `P0 / P1 / P2` 优化项的真实执行状态。
- 本清单继续只覆盖代码质量优化与架构收口，不扩展到安全体系重构、功能开发或数据库大改。
- 本文档不再是“原始计划模板”，而是“阶段性执行台账 + 后续待办清单”。

---

## 0. 使用说明

状态约定:
- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成
- `[!]` 有明确阻塞或已知失效项

执行约束:
- 每次只处理一个边界问题或一组紧邻的小切片，不做跨阶段大爆破重写。
- 每个任务完成后，必须运行对应 focused tests 或主干回归。
- 每个任务必须保持外部行为不变，包括接口返回、状态流、消息文案、权限判定结果。
- 若需新增兼容层，必须同时记录移除计划，避免 seam/facade 继续堆积。

验收总则:
- 路由层继续保持薄壳。
- 纯 passthrough 层减少，而不是换名字继续保留。
- Core 边界更清晰，平台字段不继续向核心层扩散。
- 每项任务都能给出“改了什么、没改什么、如何验证”。

---

## 1. 当前阶段结论

### [~] M0: 边界收口准备推进中
- 双入口边界说明、任务调度文档、中控文档、系统总览等已同步到较新的口径。
- `docs/入口职责矩阵_entry_responsibility_matrix.md` 与 `docs/双入口重复能力_inventory.md` 已补齐。
- `docs_ci.yml -> scripts/doc_quality_checker.py` 失效治理链路已修复并完成本地校验。
- 当前 M0 仍未完成的核心原因是：`P0-2` 的“旧入口冻结规则”还没有正式写入 `AGENTS.md` 或热点入口约束注释。

### [x] M1: 任务主链路去缝合已基本完成
- Web 任务主链路已收口到薄 router + API service + `task_core facade`。
- Bot 主链已收口为分域 entrypoints + `run_bot_task_application(...)`，旧纯 compat seam 大幅减少。
- `BotTaskCancelled` 已替代字符串 sentinel；Bot 五段式上下文已落地。
- `task_core.py` 已显著向 facade/orchestrator 形态收口。

### [~] M2: Core 标识与边界统一推进中
- Core 对基础设施直接依赖已继续收口，`task_dispatcher.py`、`media_processor.py`、`user_facade.py` 等已改为 provider/capability 获取实现。
- `task_core` 方向上已更统一地围绕 `internal_user_id` 运转，但“身份字段边界表”“permission_service 拆分”“全量 internal_user_id 收口”尚未全部完成。

---

## 2. 已落地快照

截至当前代码状态，以下改动已确认落地:
- Bot 主链真实入口收口到 `run_bot_task_application(...)`，旧 `run_bot_task_flow(...)` 已退出。
- `bot_task_service.py` 已降级为薄兼容 facade，纯 compat-only 壳已删除。
- Bot 取消态已改用 `BotTaskCancelled`，不再使用 `"cancelled"` 字符串协议。
- `task_core.py` 当前主要保留 facade 语义，真实装配已下沉到 `task_core_service_providers.py`、`task_core_default_dependencies.py`、`task_core_submission.py`、`task_core_web_monitor.py`、`task_core_runtime.py`。
- Web stream/history fallback、`history_delivery_service` 显式依赖注入、`task_stream_api_service` 显式依赖注入已落地。
- `core` 中最后一批直接 `services` 依赖已继续收口，主线测试 seam 已更多迁到 provider/dependencies 边界。
- 更大范围主干回归与 warning 清理均已完成，当前主干测试为 `576 passed`。
- `docs/`、`.trae/skills/`、项目记忆已按当前代码口径完成一轮系统同步。

---

## 3. P0 边界收口

### P0-1 双入口职责清单
- 状态: `[x]`
- 当前情况:
  - `docs/system_architecture_report.md`、`docs/子模块_任务调度_task_scheduler.md`、`docs/子模块_中控API与节点通信_central_api.md` 已明确 Bot/Web/task core/Central API 的主职责边界。
  - 独立交付物 `docs/入口职责矩阵_entry_responsibility_matrix.md` 已补齐。
- 已完成:
  - 双入口总体职责口径已回写到系统总览与调度文档。
  - `backend/app` 更接近中控/执行面，`src/web_api` 更接近主 Web/BFF 入口，这一认知已进入文档。
  - 已形成模块级矩阵，可直接用于评审与后续迁移挂载。
- 剩余动作:
  - 后续仅需把冻结规则继续回写到 `AGENTS.md` 或热点入口注释。
- 建议回归:
  - 无代码行为改动时，仅做文档 review。

### P0-2 旧入口冻结规则
- 状态: `[~]`
- 当前情况:
  - 文档层已经逐步把 `backend/app` 描述为执行面 / 中控职责，而不是 Web/BFF 主入口。
  - 但 `AGENTS.md` 与热点入口文件中还没有形成一份可直接执行的“冻结区规则”。
- 已完成:
  - 新知识口径默认新增 Web/BFF 逻辑应进入 `src/web_api`，中控与执行面逻辑留在 `backend/app`。
- 剩余动作:
  - 在 `AGENTS.md` 或专门边界文档中写明冻结规则。
  - 如有必要，在 `backend/app/main.py` 或相关入口加简短约束注释。
- 建议回归:
  - 无。

### P0-3 双入口重复能力 Inventory
- 状态: `[x]`
- 当前情况:
  - 独立交付物 `docs/双入口重复能力_inventory.md` 已补齐。
- 已完成:
  - 已按“完全重复 / 部分重复 / 历史兼容残留”给出 inventory 分类标准。
  - 已把任务创建、取消、状态/结果查询、认证与执行面视图等重叠能力写入 inventory。
  - 后续 P1/P2 改动可以直接挂到某一条 inventory 项上。
- 剩余动作:
  - 后续若入口归属发生变化，只需继续维护 inventory 条目。
- 建议回归:
  - 无。

### P0-4 治理漂移资产修补
- 状态: `[x]`
- 当前情况:
  - `scripts/doc_quality_checker.py` 已补齐，`docs_ci.yml` 的失效脚本引用已恢复为可执行状态。
- 已完成:
  - 脚本已落地到 `scripts/doc_quality_checker.py`。
  - 本地执行 `python scripts/doc_quality_checker.py` 已通过。
- 剩余动作:
  - `logs/` 是否作为正式目录保留，仍可在后续文档治理中继续明确。
- 验收标准:
  - CI 不再引用不存在脚本
  - 文档中的路径与仓库现状一致
- 建议回归:
  - 文档类 workflow

---

## 4. P1 任务主链路去缝合

### P1-1 Web/Bot 任务链路调用图
- 状态: `[~]`
- 当前情况:
  - Bot/Web 主链路的真实口径已在 `docs/子模块_任务调度_task_scheduler.md`、`docs/business/image_to_video_flow.md`、`docs/business/image_to_image_flow.md` 中体现。
  - `docs/compat_seam_exit_table.md` 也承担了部分 seam 清单作用。
  - 但仍缺专门的“调用图 + 职责表 + seam 清单”一体化交付物。
- 已完成:
  - Web 主链和 Bot 主链都已有较稳定的新叙事。
  - 纯 passthrough seam 的主要热点已被识别并清掉一批。
- 剩余动作:
  - 产出单独的调用图/职责表/旧 facade 认知清单，便于后续评审挂载。
- 建议回归:
  - 无。

### P1-2 收口 Web 提交链路
- 状态: `[x]`
- 当前情况:
  - `src/web_api/routers/tasks.py` 已继续保持薄壳。
  - `task_action_api_service.py`、`task_submission_service.py`、`task_runtime_api_service.py`、`task_stream_api_service.py` 等已承接真实应用服务逻辑。
- 已完成:
  - Web 提交主路径已基本收口为“薄 router + API service + core facade”。
  - history/stream/result 侧的异常映射和 fallback 语义也已同步收口。
- 验证:
  - `tests/web_api/test_tasks_generate.py`
  - `tests/web_api/test_tasks_action_api_service.py`
  - `tests/web_api/test_tasks_stream.py`
  - `tests/web_api/test_task_runtime_api_service.py`

### P1-3 收口 Bot 提交链路
- 状态: `[x]`
- 当前情况:
  - `bot_task_service.py` 已退化为薄 facade。
  - 真实入口收口到 generation / specialized / video entrypoints 与 `run_bot_task_application(...)`。
  - 纯 compat-only 文件 `task_service_generation_entrypoints.py`、`task_service_entrypoints.py` 已删除。
- 已完成:
  - 主链路跳转层级下降。
  - Bot 主链不再隐藏式多层转发。
- 验证:
  - `tests/services/test_task_service_flow.py`
  - `tests/services/test_task_service_completion.py`
  - `tests/services/test_task_recovery_runtime.py`

### P1-4 参数爆炸收口
- 状态: `[x]`
- 当前情况:
  - `task_service_types.py` 已拆出五段式上下文与相关类型。
  - `task_service_flow.py`、`task_service_completion.py` 等主热点的超长签名和语义分组已有明显收口。
- 已完成:
  - `request / presentation / billing / failure / cleanup` 五段式上下文落地。
  - 调用点可读性和 patch seam 稳定性显著提升。
- 验证:
  - `tests/services/test_task_service_flow.py`
  - `tests/services/test_task_service_completion.py`

### P1-5 `task_core` 编排减重
- 状态: `[x]`
- 当前情况:
  - `task_core.py` 当前已更接近 facade/orchestrator，而不再是总控巨石文件。
  - 默认装配、submission、runtime、persistence、web-monitor 已下沉到专门模块。
- 已完成:
  - 并发锁、输入准备、提交 saga、side effect、补偿等步骤更显式化。
  - `task_core.py` 主文件显著更短、更像稳定门面。
- 验证:
  - `tests/core/test_task_core_submission.py`
  - `tests/core/test_task_core_r2_warmup.py`
  - `tests/integration/test_saga_and_queue.py`

### P1-6 异常语义统一
- 状态: `[~]`
- 当前情况:
  - Bot 取消态已统一到 `BotTaskCancelled`。
  - Web stream/history fallback、result/runtime 异常映射也已有较稳定语义。
  - 但“Web/Bot 全链统一异常翻译边界”的专项盘点和清理并未单独完成。
- 已完成:
  - 取消协议已完成一轮显式类型化。
  - 多处重复测试 seam 和异常 patch 点已减少。
- 剩余动作:
  - 盘点 `task_core`、Web API service、Bot flow 之间的异常翻译职责。
  - 再清一轮重复 `try/except` 与边界重叠的语义化处理。
- 建议回归:
  - `tests/web_api/test_tasks_generate.py`
  - `tests/web_api/test_tasks_stream.py`
  - Bot 任务链路 focused tests

---

## 5. P2 Core 标识与边界统一

### P2-1 身份字段边界表
- 状态: `[ ]`
- 当前情况:
  - 方向上已经更强调 `internal_user_id` 进入 core，但尚无正式“身份字段边界表”交付物。
- 剩余动作:
  - 输出字段边界表，明确 `internal_user_id`、`telegram_id`、`username`、Web 当前用户对象在 adapter/application/core 的允许层级与禁止层级。
- 建议回归:
  - 无。

### P2-2 Core 统一使用 `internal_user_id`
- 状态: `[~]`
- 当前情况:
  - `task_core` 及多条核心路径已更偏向 `internal_user_id`。
  - 但 auth/user/permission 全链仍未完成统一收口，且还缺专门的边界文档与专项回归说明。
- 已完成:
  - Bot/Web 主路径对 `internal_user_id` 的依赖更明确。
  - Core 内平台字段扩散已减少。
- 剩余动作:
  - 继续盘点 `auth_core`、`user_core`、Web dependencies 中残留的 `telegram_id` 直通点。
  - 形成明确的映射责任层文档。
- 建议回归:
  - `tests/core/test_user_core.py`
  - `tests/core/test_auth_core.py`
  - `tests/web_api/test_dependencies.py`

### P2-3 说明
- 状态: `[!]`
- 当前情况:
  - 原文“执行顺序建议”中引用了 `P2-3`，但正文没有对应任务定义。
- 剩余动作:
  - 若仍需要 `P2-3`，必须先补完整任务目标、交付物与验收标准。
  - 否则后续周计划不再引用该编号。

### P2-4 `permission_service` 拆分
- 状态: `[ ]`
- 当前情况:
  - `src/services/permission_service.py` 仍然存在，尚未拆成清晰的 `permission_*` 子域模块。
- 剩余动作:
  - 按 access check / identity-group resolution / checkin-referral / web access bridge 至少完成第一轮拆分。
- 建议回归:
  - `tests/web_api/test_dependencies.py`
  - 相关服务测试

### P2-5 Core 对基础设施依赖审计
- 状态: `[~]`
- 当前情况:
  - 这一项已有明显进展，但未形成正式审计表。
- 已完成:
  - `task_dispatcher.py`、`media_processor.py`、`user_facade.py` 等关键点已改为 provider/capability 获取实现。
  - Core 对基础设施直接依赖继续减少。
- 剩余动作:
  - 输出审计表，列出 remaining 直接依赖点与替换顺序。
  - 将“已改造完成的 provider seam”与“仍待收口的基础设施直连”分开列清楚。
- 建议回归:
  - Core focused tests 全跑

---

## 6. 当前优先级建议

### 第一优先级
- `[~]` P0-2 旧入口冻结规则
- `[~]` P1-6 异常语义统一
- `[ ]` P2-1 身份字段边界表
- `[~]` P2-2 Core 统一使用 `internal_user_id`

### 第二优先级
- `[ ]` P2-4 `permission_service` 拆分
- `[~]` P2-5 Core 对基础设施依赖审计表补齐
- `[~]` P1-1 Web/Bot 任务链路调用图

### 第三优先级
- 维护 `入口职责矩阵` 与 `双入口重复能力 inventory` 的后续演进
- 视需要补 `P2-3` 正文定义或从周计划中彻底移除该编号

---

## 7. 每次提交前的检查项

- [ ] 本次改动是否只收口一个边界问题
- [ ] 是否删除或缩薄了至少一个纯 passthrough 层
- [ ] 是否避免引入新的 seam/facade 叠层
- [ ] 是否保持了接口、消息和权限行为不变
- [ ] 是否补齐了 focused tests 或复用了现有测试
- [ ] 是否更新了相关文档或迁移表
- [ ] 是否记录了兼容层的移除条件

---

## 8. 非目标清单

以下内容不属于本轮 `tasks.md` 主范围:
- 安全体系重构
- 支付链路业务规则改版
- Gallery 新功能开发
- Dashboard 全量视觉重做
- 数据库 schema 大改

说明:
- 本轮虽然同步过部署与知识文档口径，但不代表“部署脚本逻辑重构”已经纳入本执行清单完成项。

---

## 9. 完成定义

当以下条件同时成立时，可认为本轮 `P0 / P1 / P2` 质量优化阶段完成:
- 双入口边界已文档化，且具备独立职责矩阵与 inventory
- 任务主链路的纯转发层显著减少
- 参数爆炸热点得到阶段性收口
- Core 主路径以 `internal_user_id` 为统一身份入口
- Web 权限链路不再直接依赖 `telegram_id`
- `permission_service` 已开始按职责拆分
- Core 基础设施依赖审计表已完成并可继续驱动后续收口
- 文档治理链路不再引用失效脚本，`doc_quality_checker.py` 可本地执行通过
- 所有改动均通过对应 focused tests 或主干回归

---

## 10. 测试与入口命名约定

- `tests/` 是当前主测试目录:
  - 新增 focused tests、回归测试、集成测试统一放这里。
- `src/tests/` 归类为历史遗留/本地辅助测试区:
  - 仅保留旧 smoke/system/import 用例，除非迁移，不再新增。
  - 后续若继续维护，应逐步迁入 `tests/` 并补齐与生产入口一致的 fixture。
- `src/bot_test.py` 是共享 Telegram Bot 入口:
  - 文件名是历史遗留，不代表“只给测试环境用”。
  - 实际运行环境由 `BOT_TYPE`、容器编排和 token 注入决定。
  - 新文档、脚本和说明应统一称其为“Telegram Bot shared entrypoint (`src/bot_test.py`)”。
