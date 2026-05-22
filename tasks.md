# All_Bot 代码质量优化执行清单

更新时间: 2026-05-22

文档目标:
- 将静态分析报告中的 `P0 / P1 / P2` 落成可执行项目清单。
- 本清单只覆盖代码质量优化与架构收口，不包含安全改造、部署策略调整和功能扩展。
- 执行原则为“小切片、低风险、可回归、不改功能语义”。

---

## 0. 使用说明

状态约定:
- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成
- `[!]` 有阻塞

执行约束:
- 每次只处理一个小切片，不做跨阶段大爆破重写。
- 每个任务完成后，必须运行对应 focused tests。
- 每个任务必须保持外部行为不变，包括接口返回、状态流、消息文案、权限判定结果。
- 若需新增兼容层，必须同时记录移除计划，避免 seam/facade 继续堆积。

验收总则:
- 路由层继续保持薄壳。
- 纯 passthrough 层减少，而不是换名字继续保留。
- Core 边界更清晰，平台字段不继续向核心层扩散。
- 每项任务都能给出“改了什么、没改什么、如何验证”。

---

## 1. 里程碑

### M0: 边界收口准备完成
- 完成双入口职责清单。
- 完成旧入口冻结规则。
- 完成重复能力 inventory。
- 修复或移除失效治理资产。

### M1: 任务主链路去缝合完成
- Web/Bot 任务主链路调用深度下降。
- 纯 passthrough seam 数量明显减少。
- 任务主路径参数爆炸得到缓解。
- 异常翻译边界统一。

### M2: Core 标识边界统一完成
- Core 主路径统一以 `internal_user_id` 为中心。
- Web 权限依赖不再回查 `telegram_id`。
- `permission_service` 开始按职责拆分。
- Core 对基础设施直接依赖继续收口。

---

## 2. P0 边界收口

### P0-1 双入口职责清单
- [ ] 任务目标
  - 明确 `backend/app` 与 `src/web_api` 的长期职责边界。
- [ ] 涉及文件
  - `backend/app/main.py`
  - `backend/app/routers/agent.py`
  - `backend/app/dependencies.py`
  - `src/web_api/main.py`
  - `src/web_api/routers/*.py`
  - `docs/system_architecture_report.md`
- [ ] 执行动作
  - 盘点两个入口各自承载的路由、生命周期、依赖注入和中控职责。
  - 输出一份“入口职责矩阵”，字段建议为:
    - 模块
    - 当前职责
    - 是否核心职责
    - 目标归属
    - 是否需要兼容保留
  - 明确 `backend/app` 是否只保留中控/队列相关职责。
- [ ] 交付物
  - 一份边界说明文档，建议落在 `docs/`。
- [ ] 验收标准
  - 每条能力都能明确归属到一个主入口。
  - 不再出现“两个入口都能改”的模糊区域。
- [ ] 建议回归
  - 无代码行为改动时，仅做文档 review。

### P0-2 旧入口冻结规则
- [ ] 任务目标
  - 在边界未完全收口前，禁止继续向旧入口扩张新逻辑。
- [ ] 涉及文件
  - `backend/app/main.py`
  - `backend/app/*.py`
  - `AGENTS.md`
  - 边界说明文档
- [ ] 执行动作
  - 给 `backend/app` 标注“冻结区”规则。
  - 约定新增 Web/BFF 逻辑默认进入 `src/web_api`。
  - 约定 `backend/app` 仅允许修复、迁移或中控职责内的小范围重构。
- [ ] 交付物
  - 文档规则更新。
  - 如有必要，在热点入口文件顶部增加简短约束注释。
- [ ] 验收标准
  - 后续任务评审时可以快速判断新逻辑是否落错层。
- [ ] 建议回归
  - 无。

### P0-3 双入口重复能力 Inventory
- [ ] 任务目标
  - 为后续迁移建立精确对象清单。
- [ ] 涉及文件
  - `backend/app/main.py`
  - `backend/app/main_*`
  - `src/web_api/main.py`
  - `src/web_api/routers/*.py`
  - `src/web_api/services/*.py`
- [ ] 执行动作
  - 将重复能力按三类标记:
    - 完全重复
    - 部分重复
    - 历史兼容残留
  - 输出迁移表，字段建议为:
    - 能力名
    - 当前文件
    - 当前调用方
    - 目标归属
    - 迁移阶段
    - 兼容清理条件
- [ ] 交付物
  - 一份 inventory 表。
- [ ] 验收标准
  - 后续 P1/P2 每个改动都能挂到某一条 inventory 项上。
- [ ] 建议回归
  - 无。

### P0-4 治理漂移资产修补
- [ ] 任务目标
  - 先修补已确认失效的治理链路，避免后续优化过程被无效门禁干扰。
- [ ] 涉及文件
  - `.github/workflows/docs_ci.yml`
  - `scripts/doc_quality_checker.py`
  - `docs/子模块_代码静态分析与质量评估规范_code_quality.md`
  - `logs/`
- [ ] 执行动作
  - 二选一:
    - 补齐 `scripts/doc_quality_checker.py`
    - 或移除 `docs_ci.yml` 中的失效调用
  - 使文档规范与仓库真实状态一致。
  - 明确 `logs/` 是否作为正式目录保留。
- [ ] 交付物
  - 可执行的 docs CI。
  - 一致的文档规范。
- [ ] 验收标准
  - CI 不再引用不存在的脚本。
  - 文档中的路径与仓库现状一致。
- [ ] 建议回归
  - 文档类 workflow。

---

## 3. P1 任务主链路去缝合

### P1-1 Web/Bot 任务链路调用图
- [ ] 任务目标
  - 先固定真实调用路径和分层职责，避免盲拆。
- [ ] 涉及文件
  - `src/web_api/routers/tasks.py`
  - `src/web_api/services/task_action_api_service.py`
  - `src/web_api/services/task_submission_service.py`
  - `src/core/task_core.py`
  - `src/services/task_service.py`
  - `src/services/task_service_flow.py`
  - `src/services/task_service_facade_seams.py`
- [ ] 执行动作
  - 画出 Web 提交链路。
  - 画出 Bot 提交链路。
  - 对每个节点标记职责:
    - 输入适配
    - 应用编排
    - 领域动作
    - 基础设施调用
    - 纯 passthrough
- [ ] 交付物
  - 调用图。
  - 职责表。
  - seam 清单。
- [ ] 验收标准
  - 每个函数都能解释“存在的必要性”。
  - 纯 passthrough 函数被显式识别。
- [ ] 建议回归
  - 无。

### P1-2 收口 Web 提交链路
- [ ] 任务目标
  - 将 Web 提交主路径压缩为“薄 router + 单应用服务 + core”。
- [ ] 涉及文件
  - `src/web_api/routers/tasks.py`
  - `src/web_api/services/task_action_api_service.py`
  - `src/web_api/services/task_submission_service.py`
  - `src/core/task_core.py`
- [ ] 执行动作
  - 保留 router 的参数声明、依赖注入和 HTTP 异常映射。
  - 合并中间纯转发 service。
  - 将 Web 提交统一收口到一个稳定 app service。
- [ ] 非目标
  - 不改任务生成协议。
  - 不改计费逻辑。
  - 不改提交结果结构。
- [ ] 验收标准
  - 层级减少 1 到 2 层。
  - 相同输入输出下行为一致。
- [ ] 建议回归
  - `tests/web_api/test_tasks_generate.py`
  - `tests/web_api/test_tasks_action_api_service.py`
  - `tests/web_api/test_tasks_router_passthrough.py`

### P1-3 收口 Bot 提交链路
- [ ] 任务目标
  - 压缩 `_run_bot_task_flow -> seam -> flow` 的深层转发结构。
- [ ] 涉及文件
  - `src/services/task_service.py`
  - `src/services/task_service_flow.py`
  - `src/services/task_service_facade_seams.py`
  - `src/services/task_service_completion.py`
  - `src/services/task_service_finalize.py`
- [ ] 执行动作
  - 删除纯参数平移的 seam。
  - 保留有真实分层价值的 flow/helper。
  - 让 `TaskService` 只保留表示层和少量 patch 点。
- [ ] 非目标
  - 不改消息发送语义。
  - 不改回调按钮、状态消息更新时机。
- [ ] 验收标准
  - 主链路跳转层级下降。
  - `TaskService` 不再承担隐藏式多层转发。
- [ ] 建议回归
  - `tests/services/test_task_service_flow.py`
  - `tests/services/test_task_service_completion.py`
  - `tests/services/test_task_recovery_runtime.py`

### P1-4 参数爆炸收口
- [ ] 任务目标
  - 将超长函数签名收口为语义清晰的上下文对象。
- [ ] 涉及文件
  - `src/services/task_service_flow.py`
  - `src/services/task_service_completion.py`
  - `src/services/task_service_finalize.py`
  - `src/services/task_service_types.py`
- [ ] 执行动作
  - 识别可分组参数:
    - 执行上下文
    - 计费上下文
    - 消息上下文
    - 输出策略
  - 新建 DTO / dataclass / typed context 对象。
  - 逐步替换调用点。
- [ ] 交付物
  - 统一 context 对象。
  - 更短的函数签名。
- [ ] 验收标准
  - 关键热点函数参数显著下降。
  - 调用点可读性明显提升。
- [ ] 建议回归
  - `tests/services/test_task_service_flow.py`
  - `tests/services/test_task_service_support.py`
  - `tests/services/test_task_service_completion.py`

### P1-5 `task_core` 编排减重
- [ ] 任务目标
  - 让 `task_core` 成为真正的 orchestrator，而不是一站式总控函数集合。
- [ ] 涉及文件
  - `src/core/task_core.py`
  - `src/core/task_core_submission.py`
  - `src/core/task_core_runtime.py`
  - `src/core/task_core_persistence.py`
  - `src/core/task_core_finalization.py`
- [ ] 执行动作
  - 将以下步骤进一步显式化:
    - 并发锁检查
    - 输入准备
    - 计费扣减
    - 提交 saga
    - 提交后副作用
    - 失败补偿
  - 主门面只保留步骤编排，不吞细节实现。
- [ ] 非目标
  - 不调整提交协议。
  - 不改变已有测试命名和返回结构。
- [ ] 验收标准
  - `task_core.py` 主文件更短、更像门面。
  - 失败补偿边界更清晰。
- [ ] 建议回归
  - `tests/core/test_task_core_submission.py`
  - `tests/core/test_task_core_r2_warmup.py`
  - `tests/integration/test_saga_and_queue.py`

### P1-6 异常语义统一
- [ ] 任务目标
  - 统一 Web/Bot 任务链路的异常翻译边界。
- [ ] 涉及文件
  - `src/web_api/routers/tasks.py`
  - `src/web_api/services/task_action_api_service.py`
  - `src/services/task_service.py`
  - `src/core/task_core.py`
- [ ] 执行动作
  - 盘点当前异常类型和翻译位置。
  - 规定“谁负责转译为用户可见语义”。
  - 移除重复 `try/except`。
- [ ] 验收标准
  - 同一类失败在 Web/Bot 中的日志和返回口径更一致。
  - router 不再重复处理下层已稳定语义化的异常。
- [ ] 建议回归
  - `tests/web_api/test_tasks_generate.py`
  - `tests/web_api/test_tasks_result.py`
  - `tests/web_api/test_tasks_stream.py`
  - Bot 任务链路 focused tests

---

## 4. P2 Core 标识与边界统一

### P2-1 身份字段边界表
- [ ] 任务目标
  - 明确 `internal_user_id`、`telegram_id`、`username`、Web 当前用户对象的层级边界。
- [ ] 涉及文件
  - `src/core/user_core.py`
  - `src/core/auth_core.py`
  - `src/web_api/dependencies.py`
  - `src/services/permission_service.py`
- [ ] 执行动作
  - 输出“身份字段边界表”，字段建议为:
    - 字段名
    - 来源
    - 允许出现的层级
    - 禁止出现的层级
    - 映射责任层
  - 明确 adapter/application/core 分层中的身份传递规则。
- [ ] 交付物
  - 身份字段边界说明。
- [ ] 验收标准
  - 团队能快速判断任一新代码是否越层。
- [ ] 建议回归
  - 无。

### P2-2 Core 统一使用 `internal_user_id`
- [ ] 任务目标
  - 将核心主路径的业务入参统一收口到内部用户 ID。
- [ ] 涉及文件
  - `src/core/user_core.py`
  - `src/core/auth_core*.py`
  - `src/core/task_core.py`
  - 相关 application/service adapter
- [ ] 执行动作
  - 在 adapter/application 层完成平台 ID 到内部 ID 的映射。
  - Core 对外接口不再继续扩大 `telegram_id` 使用面。
  - 保留兼容 wrapper 时，必须标注移除条件。
- [ ] 非目标
  - 不删除 Telegram 登录能力。
  - 不改用户表结构。
- [ ] 验收标准
  - Core 暴露函数签名中，平台字段使用点减少。
  - 新逻辑默认以 `internal_user_id` 进入 core。
- [ ] 建议回归
  - `tests/core/test_user_core.py`
  - `tests/core/test_auth_core.py`
  - `tests/web_api/test_dependencies.py`

### P2-3 Web 权限链路去 Telegram 依赖
- [ ] 任务目标
  - 让 Web 权限检查不再通过 `user.telegram_id` 回查动态权限。
- [ ] 涉及文件
  - `src/web_api/dependencies.py`
  - `src/services/permission_service.py`
  - 相关 presenter / auth service
- [ ] 执行动作
  - 为权限服务新增基于内部用户 ID 的查询入口。
  - Web 依赖层统一调用内部身份接口。
  - 逐步移除 `telegram_id` 作为 Web 权限桥接字段的直接使用。
- [ ] 验收标准
  - Web 用户、TG 用户、混合身份用户共用同一权限检查入口。
  - 权限判断结果保持不变。
- [ ] 建议回归
  - `tests/web_api/test_dependencies.py`
  - 用户权限/偏好相关 API tests

### P2-4 `permission_service` 拆分
- [ ] 任务目标
  - 将横切胖服务拆成职责清晰的子域模块。
- [ ] 涉及文件
  - `src/services/permission_service.py`
  - 新拆分的 `src/services/permission_*`
- [ ] 执行动作
  - 首轮建议至少拆分为:
    - access check
    - identity/group resolution
    - checkin/referral
    - web access bridge
  - 主 facade 保留兼容导出，逐步缩薄。
- [ ] 非目标
  - 不改变业务规则。
  - 不重写权限系统。
- [ ] 验收标准
  - 单文件规模明显下降。
  - 无新增循环依赖。
  - 权限调用方向更清晰。
- [ ] 建议回归
  - `tests/web_api/test_dependencies.py`
  - 相关服务测试

### P2-5 Core 对基础设施依赖审计
- [ ] 任务目标
  - 继续落实 Core Isolation，避免只做“文件名拆分”。
- [ ] 涉及文件
  - `src/core/task_core.py`
  - `src/core/gallery_core.py`
  - `src/core/auth_core.py`
  - 相关 `src/services/*` 和 adapter
- [ ] 执行动作
  - 审计 Core 中直接引用的:
    - storage
    - logger
    - registry
    - redis
    - 平台特定 helper
  - 标记哪些依赖应下沉到 adapter/infrastructure。
  - 建立收口顺序和替换计划。
- [ ] 交付物
  - Core 依赖审计表。
  - 下一轮替换清单。
- [ ] 验收标准
  - Core 中直接依赖全局单例和平台对象的点持续减少。
- [ ] 建议回归
  - Core focused tests 全跑

---

## 5. 执行顺序建议

### 第 1 周
- [ ] 完成 `P0-1`
- [ ] 完成 `P0-2`
- [ ] 完成 `P0-3`
- [ ] 完成 `P0-4`

### 第 2 周
- [ ] 完成 `P1-1`
- [ ] 完成 `P1-2`
- [ ] 完成 `P1-3`

### 第 3 周
- [ ] 完成 `P1-4`
- [ ] 完成 `P1-5`
- [ ] 完成 `P1-6`

### 第 4 周
- [ ] 完成 `P2-1`
- [ ] 完成 `P2-2`
- [ ] 完成 `P2-3`

### 第 5 周
- [ ] 完成 `P2-4`
- [ ] 完成 `P2-5`

---

## 6. 每次提交前的检查项

- [ ] 本次改动是否只收口一个边界问题
- [ ] 是否删除或缩薄了至少一个纯 passthrough 层
- [ ] 是否避免引入新的 seam/facade 叠层
- [ ] 是否保持了接口、消息和权限行为不变
- [ ] 是否补齐了 focused tests 或复用了现有测试
- [ ] 是否更新了相关文档或迁移表
- [ ] 是否记录了兼容层的移除条件

---

## 7. 第一批建议直接开工的工单

### 工单 A: 双入口职责边界清单
- [ ] 输出入口职责矩阵
- [ ] 明确 `backend/app` 冻结规则
- [ ] 明确 `src/web_api` 主承接范围

### 工单 B: 任务链路调用图与 seam 清单
- [ ] 输出 Web 提交链路图
- [ ] 输出 Bot 提交链路图
- [ ] 标注纯 passthrough seam

### 工单 C: 身份字段边界表
- [ ] 输出字段边界表
- [ ] 明确 `telegram_id -> internal_user_id` 映射责任层
- [ ] 列出 Web 权限链路改造点

---

## 8. 非目标清单

以下内容不属于本轮 `tasks.md` 执行范围:
- 安全体系重构
- 部署脚本和环境发布策略调整
- 支付链路业务规则改版
- Gallery 新功能开发
- Dashboard 全量视觉重做
- 数据库 schema 大改

---

## 9. 完成定义

当以下条件同时成立时，可认为本轮 `P0 / P1 / P2` 质量优化阶段完成:
- 双入口边界已文档化且不再继续漂移
- 任务主链路的纯转发层显著减少
- 参数爆炸热点得到阶段性收口
- Core 主路径以 `internal_user_id` 为统一身份入口
- Web 权限链路不再直接依赖 `telegram_id`
- `permission_service` 已开始按职责拆分
- 所有改动均通过对应 focused tests
