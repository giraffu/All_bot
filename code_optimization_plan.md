# All_bot 代码优化方案（结合当前代码现状的校准版）

校准时间: 2026-05-23

## 1. 文档目的

本文档用于指导下一轮代码优化与架构收口工作。

本版不是对旧方案做文字润色，而是结合当前仓库真实实现状态，对优化目标、优先级和阶段状态进行重新校准，避免继续把已经完成的事项写成“未开始”，也避免把当前最重的问题排在后面。

本轮目标仍然是:

- 降低任务主链路的认知复杂度
- 收紧 `core` 层依赖边界
- 继续推进主站 Web API 的薄路由化
- 推进 Dashboard 后端从胖路由转向 `router + service/presenter`
- 收敛 Dashboard 前端状态复杂度和主站前端页面级重复
- 在不破坏现有功能和测试稳定性的前提下，以低风险切片推进重构

## 2. 当前代码快照

### 2.1 已完成或基本完成的收口

以下事项已不适合继续作为“主要未完成问题”来描述，而应视为已完成基础或部分完成基础:

- `task_service.py` 已基本退出 Web 主路径，当前主要承担 Telegram 表示层职责；Web 提交与取消已主要走 `src/web_api/services/* -> src/core/task_core.py`
- `task_core.py` 已形成“façade + 依赖 builder + 独立流程模块”的基本结构，`submission/runtime/persistence/finalization/web_monitor` 已拆开
- `src/core/task_core_persistence.py` 已形成 builder/compat wrapper + `task_core_persistence_flow.py` 的分层，成功持久化主流程已下沉到专门 flow
- `src/core/billing_core.py` 已具备 getter/provider/compat proxy 结构，会员结算纯规则已下沉到 `billing_core_membership.py`
- `src/core/auth_core_dependencies.py` 已更明确地承担受控 composition root 角色，`auth_core.py` 主流程未回退为直接抓全局单例
- `src/web_api/routers/users.py` 已基本薄路由化，资料、偏好、历史、apply-context、send-to-bot 等逻辑已下沉到 service
- `src/web_api/routers/gallery.py` 已基本薄路由化，帖子列表、互动、评论、状态更新、apply-context 已主要由 `gallery_service` 承接
- `src/web_api/routers/tasks.py` 已完成主体收口，提交、取消、结果查询、SSE 与残余基础设施拼装已基本下沉到专门 service
- `src/web_api/routers/payment.py` 已完成“router + service/presenter”收口，对外路径、字段与返回层级保持不变
- Dashboard backend 已大面积形成稳定的“薄路由 + service/presenter + 共享 helper”模式，`system/users/history/templates/gallery/plans/workers/stats/logs/referrals` 已不再适合作为主要胖路由问题描述
- `task_core_finalization.py`、`task_failure_finalization_service.py`、`task_service_finalize.py` 已形成终态失败共享 helper / policy / presentation policy 的基础路径
- `task_service.py` 已连续移除多轮纯参数透传 seam，`task_service_facade_seams.py` 当前仅剩极少数 compat seam
- `dashboard/frontend/src/App.vue` 已明显从“大一统状态入口”退化为页面装配层，导航与 tab 视图已拆到 composable
- 主站前端 `Gallery` 家族页与生成页已具备一定共享基础，已有共享壳层、详情弹层适配、评论 composable、上传预览和任务流监听 composable
- 热点门禁与回归触发规则已落地，`scripts/run_hotspot_regression.sh` 与 `.github/workflows/hotspot_regression_gate.yml` 已存在

### 2.2 当前仍然突出的剩余问题

### 2.2.1 `core -> services` 依赖边界已进入后半程，但 compat / provider 壳仍未完全收口

重点文件:

- `src/core/task_core.py`
- `src/core/task_core_persistence.py`
- `src/core/billing_core.py`
- `src/core/auth_core_dependencies.py`

当前问题:

- `task_core.py` 已接近“稳定 façade + 依赖装配入口”，但仍保留部分 getter/compat proxy 与基础设施泄漏面，尚未退到最终极简态
- `task_core_persistence.py` 的真实主路径已不再依赖旧式运行时兜底，但主文件仍保留 compat wrapper 形态与少量静态提示噪声
- `billing_core.py` 虽已完成 provider/getter 化与会员规则拆分，但 `QuotaManager`、`redis_client`、`permission_service` 仍通过 compat proxy 暴露，不是最终收口状态
- `auth_core_dependencies.py` 目前可以被解释为受控 composition root，但若要进一步降低认知成本，仍可继续评估是否下沉为更薄的 provider registry
- 当前主要矛盾已从“没有 seam”变为“builder/provider 已有，但 compat 壳和基础设施暴露面还没有继续缩到最小”

### 2.2.2 `task_service.py` 的纯透传 seam 已接近收尾，但最后一层 compat seam 仍待评估

重点文件:

- `src/services/task_service.py`
- `src/services/task_service_flow.py`
- `src/services/task_service_facade_seams.py`

当前问题:

- `task_service.py` 已明显变薄，早先 `_run_* / _prepare_* / _monitor_* / _handle_*` 多层透传已大幅移除
- `task_service_facade_seams.py` 当前基本只剩 `complete_monitored_bot_task_seam()`，主要问题已不再是“seam 偏多”，而是“最后这个 seam 是否仍有保留的 patch/compat 价值”
- 当前主要矛盾已从“职责混杂”变为“是否要为极少量兼容价值继续保留额外跳转层级”

### 2.2.3 终态失败、恢复、僵尸清理已形成共享模板，但还没有覆盖所有终态入口

重点文件:

- `src/core/task_core_finalization.py`
- `src/services/recovery_service.py`
- `src/services/zombie_cleaner_service.py`
- `src/services/task_recovery_runtime.py`
- `src/services/tg_task_runtime.py`

当前问题:

- 共享 finalization primitive、task record -> policy -> finalize 路径、bot presentation policy 已存在，但恢复失败、僵尸清理之外的取消、系统终止、后端失败等入口仍未完全并口
- 退款、清锁、通知、后端取消等动作已经具备共享 helper，但策略调整时仍存在“主线统一了，外围少数入口没跟上”的风险
- 当前阶段的关键问题已不是“没有统一模板”，而是“模板已经有了，还需要继续扩大覆盖面”

### 2.2.4 主站 Web API 已基本脱离主问题区，后续以小修、回归和契约守护为主

重点文件:

- `src/web_api/routers/payment.py`
- `src/web_api/routers/tasks.py`

当前问题:

- `payment.py` 已完成 service/presenter 化，本阶段重点变为持续守护“只改后端组织方式、不动前端契约”的约束
- `tasks.py` 已接近 passthrough router，后续只需在热点扫尾时留意是否又回填基础设施拼装
- 主站 Web API 已不再是当前最重问题区，不应继续占据方案主优先级

### 2.2.5 Dashboard 后端薄路由化已基本完成，后续转入热点巡检与模式守护

重点文件:

- `dashboard/backend/routers/system.py`
- `dashboard/backend/routers/users.py`
- `dashboard/backend/routers/templates.py`
- `dashboard/backend/routers/gallery.py`
- `dashboard/backend/routers/history.py`

当前问题:

- 主体热点已完成收口，当前更现实的风险是局部新改动把 SQL、事务、媒体 URL 组装或异常映射重新回填到 router
- 现阶段不再需要把 `system.py`、`users.py` 等作为主切口持续重构，而应把重点转为薄路由模式守护、热点续扫和相邻回归
- Dashboard 后端已明显领先于原方案文字描述，不应继续作为“当前最明显的胖路由集中区”

### 2.2.6 Dashboard 前端状态层仍是接下来最值得正式展开的主战场之一

重点文件:

- `dashboard/frontend/src/composables/useUserTableState.js`
- `dashboard/frontend/src/api/api.js`

当前问题:

- `useUserTableState.js` 仍同时管理筛选、分页、统计弹窗、赠送套餐、身份修改、修为修改、宗门修改等多类职责
- `client.js` 已承接 axios、token、401 和 query 构造等公共能力，但 `api.js` 仍是全站端点聚合文件，继续增长会成为新的热点巨石
- `App.vue` 已不再是主要问题文件，本轮应把重点放到 `useUserTableState.js` 和 `api.js`

### 2.2.7 主站前端仍缺少统一 page controller / submit controller

重点文件:

- `frontend/src/views/Gallery.vue`
- `frontend/src/views/MyFavorites.vue`
- `frontend/src/components/MySubmissionsPanel.vue`
- `frontend/src/views/ImageAndPrompt.vue`
- `frontend/src/views/FaceSwap.vue`
- `frontend/src/views/SingleImageToVideo.vue`
- `frontend/src/views/VideoSwap.vue`

当前问题:

- Gallery 家族页已经共享了不少壳层和局部 composable，但还没有统一的页面控制层来承接分页、详情、评论、互动、模板应用编排
- 多个生成页已经存在 `templateApply` store、共享 workbench host 与旧路由兼容入口两套路径，但提交、重置、错误处理和关闭保护还没有统一到单一控制层
- 当前阶段的核心问题是“共享积木和主路径已有，但浏览页控制层与生成页双栈编排仍未收口”

### 2.3 当前阶段判断

- `A 阶段`：主体已落地，当前更像 compat/provider 收口期，可视为后半程
- `B 阶段`：接近收尾，主要待决事项是 `complete_monitored_bot_task_seam()` 的最终去留
- `C 阶段`：共享模板已形成，但还需把更多终态入口并到同一套 policy / finalization flow
- `D 阶段`：主站 Web API 与 Dashboard backend 薄路由化已基本完成，已从主战场转入守护与扫尾
- `E 阶段`：已有共享底座，但统一 controller / 领域 composable 尚未系统展开，仍是后续大头
- `F 阶段`：热点门禁已起步，但 compat 第二轮清理与更强静态门禁还没有真正开始

## 3. 调整后的总体目标

### 3.1 架构目标

- `task_core.py` 只保留稳定 façade、依赖构建入口和少量跨模块编排
- `src/core/` 不再新增对 `src.services.*` 的直接依赖，既有依赖逐步收口到 builder/provider
- `task_service.py` 继续保留 Telegram 表示层职责，但减少纯参数透传 seam
- 主站 Web API Router 只做参数声明、依赖注入、权限和响应映射
- Dashboard Backend Router 只做接入层职责，业务编排、统计、媒体装配和异常映射下沉到 service/presenter
- Dashboard 前端页面和主站前端页面只保留页面装配，公共流程下沉到领域 composable/controller

### 3.2 可维护性目标

- 优先治理“当前仍重”的文件，而不是继续重复治理已基本收口的模块
- 继续降低任务主链路无价值跳转
- 统一终态失败与清理动作模板
- 降低 Dashboard 前后端的状态编排复杂度
- 将主站前端公共积木提升为公共控制层，而不是只停留在局部复用

### 3.3 风险控制目标

- 继续坚持低风险切片，不做一次性大改
- 每一阶段结束都保留 focused tests 或热点回归点
- compat 先保留，再在新路径稳定后删除
- 不为了文档整洁而提前删除仍在被测试 patch 点依赖的 seam

## 4. 分阶段优化方案

## 阶段 A: 收紧 `core -> services` 依赖边界

状态: 进行中（后半程）

### A1. `task_core.py`

目标状态:

- builder seam 保留在 façade 附近，并继续作为 focused tests 的稳定 patch 点
- `task_core.py` 不再直接持有 `storage`、`image_service`、`TaskRegistry`、`redis_client` 这类具体实现引用
- 流程函数内部不再临时 import `src.services.*`

具体动作:

1. 将 `TaskRegistry`、`redis_client`、`image_service`、`storage` 的使用点继续收口到最小依赖接口或 provider
2. 对现有 builder 进行二次瘦身，明确哪些 builder 负责“依赖构造”，哪些模块负责“流程执行”
3. 明确 `process_and_submit_task` 等 façade 的稳定输入输出，不在主文件继续回填基础设施细节，并逐步取消 `__all__` 级别的基础设施泄漏
4. 在 `tests/core/` 补齐或维持 focused tests，保证 builder 收口后行为不变

验收标准:

- `task_core.py` 可以被描述为“稳定 façade + 依赖装配入口”
- 流程模块内部不再偷偷回查 `src.services.*`
- 新增基础设施能力时，不再默认往 `task_core.py` 顶部追加 service import

### A2. `task_core_persistence.py` / `billing_core.py`

目标状态:

- `task_core_persistence.py` 不再直接依赖 `image_service` 和运行时 `permission_service`
- `billing_core.py` 的计费、权限、限流依赖改为最小能力注入

具体动作:

1. 先处理 `billing_core.py`，抽出额度、权限、限流、系统状态所需的最小能力接口，降低对全局单例 patch 的依赖
2. 为 `task_core_persistence.py` 显式注入下载结果、下载视频、刷新用户组等能力，去掉 `permission_service` 的运行时兜底导入
3. 保持现有接口和返回结构兼容，不改外部语义

验收标准:

- `src/core/` 内新增直接 `import src.services.*` 的需求显著下降
- `billing_core.py`、`task_core_persistence.py` 的测试替换成本下降
- `task_core_persistence.py` 中运行时 `permission_service` 导入不再出现在真实调用路径

### A3. `auth_core_dependencies.py`

目标状态:

- `auth_core.py` 继续保持“主流程不直接依赖 service 单例”的现状
- `auth_core_dependencies.py` 被明确定位为允许存在的 composition root，或继续下沉为更薄的 provider 转发层

具体动作:

1. 明确阶段边界: 本轮先不回退 `auth_core.py` 当前的依赖收口成果
2. 评估 `auth_core_dependencies.py` 是否需要继续抽成更薄的 provider registry；若暂不拆，则在文档中明确它是受控装配点
3. 若继续拆分，只移动装配逻辑，不改 `auth_core.py` 对外行为和认证语义

验收标准:

- `auth_core.py` 主流程不重新出现 `redis_client`、`permission_service` 等直接依赖
- `auth_core_dependencies.py` 的角色在代码和文档中保持一致，不再出现“被列为问题文件但没有阶段动作”的范围错位

## 阶段 B: 收缩任务域双门面的残余纯透传

状态: 进行中（接近收尾）

### B1. `task_service.py`

目标状态:

- 继续保留 Telegram 输入适配、消息发送、入口绑定、少量 patch 点
- 尽量移除没有兼容价值的纯参数透传 seam

具体动作:

1. 盘点 `task_service.py -> task_service_facade_seams.py -> task_service_flow.py` 的长链透传点
2. 将真正需要 compat/patch 的 seam 留下
3. 将只有参数平移价值的 seam 合并或删除
4. 确保主文件仍能被一句话描述为“Telegram 表示层 façade”

验收标准:

- 新增需求不需要继续给 `TaskService` 叠加 `_build_*` / `_run_*` / `_handle_*` 代理方法
- 阅读 Bot 提交主路径时，跨文件跳转层数下降

说明:

- 该阶段不再是全仓第一优先级，因为 `task_service.py` 已明显比之前更薄
- 本阶段应放在 `core` 依赖边界和 Dashboard 胖路由之后推进

## 阶段 C: 统一终态失败与清理流程

状态: 进行中（共享模板已形成，仍待扩大覆盖）

### C1. 目标

将以下场景进一步统一到共享 finalization 模板:

- 恢复失败
- 僵尸任务清理
- 用户取消
- 系统终止
- 后端失败

### C2. 具体动作

1. 继续收敛统一的终态上下文对象，至少包含:
   - registry task id
   - internal user id
   - username
   - refund policy
   - cleanup policy
   - backend cancel policy
   - user notify policy
   - message template
2. 让 `recovery_service.py` 和 `zombie_cleaner_service.py` 只负责:
   - 发现问题
   - 组装终态上下文
   - 调用共享 finalization flow
3. 把 Telegram 通知拼装、runtime 清理、退款和后端取消进一步压到共享 helper

验收标准:

- 新增一种失败终态时，不需要复制恢复/清理脚本的大段逻辑
- 退款、清锁、通知口径一致

## 阶段 D: 推进主站 Web API 与 Dashboard 后端薄路由化

状态: 基本完成（转入守护与热点巡检）

### D1. 主站 Web API

当前策略:

- `users.py`、`gallery.py` 以维持和小修为主，不再作为本轮主要治理对象
- `tasks.py` 进入守约与小修阶段
- `payment.py` 已完成本轮主治理目标，后续重点是契约守护与局部回归

#### D1.1 `payment.py`

目标状态:

- 已达成 Router 只保留参数、依赖和响应的主目标
- 后续重点转为保持套餐查询、订单创建、支付链接生成、状态组装继续留在 service/presenter

建议拆分:

- `payment_plan_service`
- `payment_order_service`
- `payment_presenter` 或返回对象 builder

当前状态:

1. `get_plans` 已完成套餐查询和返回装配下沉
2. `create_order` 已收口为独立 service 流程，并保持前端契约不变
3. `create_ton_order` 已收口为单独 service 流程
4. 订单状态查询与鉴权逻辑已下沉到 service

验收状态:

- `payment.py` 已达到近似 passthrough router
- 支付主流程已可在 service 级测试覆盖，后续以守约回归为主

#### D1.2 `tasks.py` 收尾

当前状态:

1. `queue-status` 已收口到专门 service
2. SSE 端点中的基础设施拼装已继续下沉
3. `generate/cancel/stream/result` 对外契约保持不变

验收状态:

- `tasks.py` 已接近只保留依赖注入与 service 转发
- 后续主要检查是否有新逻辑重新回填到路由层

### D2. Dashboard 后端

目标状态:

- 已基本达成 Router 只保留参数、权限、依赖和响应映射
- 后续重点转为防止 SQL 聚合、外部 HTTP、对象存储访问、DTO 组装、事务提交重新回填到 router

建议拆分:

- `dashboard/backend/services/system_service.py`
- `dashboard/backend/services/user_admin_service.py`
- `dashboard/backend/services/template_admin_service.py`
- `dashboard/backend/presenters/*`

当前状态:

1. `system.py`、`users.py` 的 service 化已完成主目标
2. `history.py`、`gallery.py`、`templates.py` 的 presenter/DTO/媒体 URL/异常映射已完成主要收口
3. `plans.py`、`workers.py`、`stats.py`、`logs.py`、`referrals.py` 也已补齐同类模式

验收状态:

- Dashboard router 已不再作为大段 SQL + 事务 + DTO 拼装的主要承载层
- 管理后台主要流程已可以用 service/presenter 级测试覆盖

## 阶段 E: 收敛 Dashboard 前端状态复杂度与主站前端页面级重复

状态: 进行中（已有底座，尚未系统展开）

### E0. Dashboard 前端状态层

目标文件:

- `dashboard/frontend/src/composables/useUserTableState.js`
- `dashboard/frontend/src/api/api.js`

具体动作:

1. 将 `useUserTableState.js` 按职责拆分:
   - `useUserListFilters`
   - `useUserAdminActions`
   - `useMembershipGiftActions`
   - `useUserDialogsState`
2. 保持 `client.js` 作为共享 HTTP client，不回填业务端点；将 `api.js` 按领域拆分:
   - `userApi`
   - `systemApi`
   - `galleryAdminApi`
   - `templateAdminApi`
3. 保持 `App.vue` 继续作为装配层，不再回填业务状态

验收标准:

- Dashboard 前端的状态和动作按领域拆开
- 新增管理动作时，不需要继续往单一 composable 堆逻辑
- `client.js` 继续稳定提供鉴权、query 构造和统一响应处理，不与领域 API 混写

### E1. Gallery 家族页

目标文件:

- `frontend/src/views/Gallery.vue`
- `frontend/src/views/MyFavorites.vue`
- `frontend/src/components/MySubmissionsPanel.vue`

具体动作:

1. 在现有共享壳层和 composable 基础上，再抽统一页面控制层，例如:
   - `useGalleryBrowserPageController`
2. 统一控制层装配:
   - 分页帖子加载
   - 评论逻辑
   - 点赞收藏互动
   - 详情弹层
   - 模板应用工作台
3. 页面本身只保留:
   - 数据源差异
   - 少量 slot
   - 页面文案和视图结构

验收标准:

- 三个页面的逻辑差异被压缩到“数据来源和特例动作”
- 公共逻辑不再以碎片形式散落在各页内

### E2. 多种生成页

目标文件:

- `frontend/src/views/ImageAndPrompt.vue`
- `frontend/src/views/FaceSwap.vue`
- `frontend/src/views/SingleImageToVideo.vue`
- `frontend/src/views/VideoSwap.vue`

具体动作:

1. 先把 `templateApply` store + `TemplateApplyWorkbenchHost` 继续稳定为主路径，再梳理旧路由兼容入口的退出条件
2. 在现有共享壳层、上传预览和任务流监听基础上，再抽统一任务提交流程 composable，例如:
   - `useGenerationSubmitController`
3. 收敛公共逻辑:
   - 上传前置校验
   - payload 组装
   - 提交任务
   - stream/result 监听
   - 重置结果
   - 错误提示
4. 页面仅保留:
   - 专属表单字段
   - 专属校验规则
   - 专属 payload 补充字段

验收标准:

- 新增一种生成页时，不需要再复制现有页面的大段提交流程
- 公共逻辑从“共享积木”提升为“共享提交流程控制层”
- 新 workbench 主路径与旧路由兼容路径的职责边界清晰，并具备后续继续删 compat 的前提

## 阶段 F: 清理 compat、扩展静态门禁与阶段文档

状态: 进行中（门禁基础已落地，compat 第二轮清理待启动）

### F1. compat 清理原则

只在满足以下条件后才删除 compat:

- 新路径已稳定被主流程使用
- focused tests 已覆盖新路径
- 旧 patch 点或旧测试已迁移
- 至少完成一轮相邻模块回归

### F2. 建议补齐的门禁

建议新增或强化以下静态检查 / review 门禁:

- `src/core/` 禁止新增直接 import `src.services.*`
- `src/web_api/routers/` 禁止新增复杂业务编排
- `dashboard/backend/routers/` 禁止新增复杂 SQL、对象存储访问和外部 HTTP 编排
- `task_service.py` / `task_service_facade_seams.py` 禁止继续增加纯参数平移 seam
- Dashboard 前端新增管理动作时，优先进入领域 composable，不继续堆到 `useUserTableState.js`
- 主站前端新增页面若复用已有任务提交流程或浏览流程，优先接 controller，不允许复制旧页面大段逻辑

### F3. 文档与回归同步要求

- 每阶段完成后同步更新本方案状态表
- 若职责边界发生变化，补充到 `docs/` 的对应模块文档
- 继续沿用热点门禁与黄金路径回归，不另起一套平行规则

## 5. 推荐实施顺序

建议按下面顺序推进，而不是继续把已基本完成的 D 阶段对象放在主优先级:

1. `src/services/task_service.py` / `task_service_facade_seams.py` 最后一层纯透传 seam 评估与收尾
2. `src/services/recovery_service.py`、`zombie_cleaner_service.py` 及其相邻入口继续统一到共享 finalization flow
3. `src/core/billing_core.py`、`task_core_persistence.py`、`task_core.py`、`auth_core_dependencies.py` 的 compat/provider 第二轮收口
4. Dashboard 前端状态层拆分
5. Gallery 家族页页面控制层收敛
6. 多种生成页双栈控制流收敛
7. compat 第二轮清理与静态门禁补齐
8. 主站 Web API 与 Dashboard backend 做热点巡检、模式守护和回归补强

原因:

- 当前最重的问题已经不是 `payment.py`、Dashboard backend router 或 `App.vue` 这类已基本收口文件
- `task_service.py` 的纯透传 seam 已压到只剩极少数尾项，投入很小就有望形成完整闭环
- 终态统一已经有共享模板，继续把取消、系统终止、后端失败等入口并口的收益很高
- `core` 依赖边界已进入后半程，更适合以 compat/provider 第二轮收口方式推进，而不是重新开辟新战场
- 真正尚未系统展开的大头已经转移到 Dashboard 前端状态层与主站前端页面控制层

## 6. 每阶段交付物

每个阶段至少应交付以下内容:

### 6.1 代码交付

- 目标文件职责收口
- 新增或调整的 helper/service/composable/controller
- 必要 compat wrapper

### 6.2 测试交付

- 至少一组 focused tests
- 至少一组相邻主链路回归或热点门禁回归

### 6.3 文档交付

- 更新本方案对应阶段状态
- 如出现职责变化，补一段简短说明到对应模块文档

## 7. 验收标准

本轮优化完成后，应满足以下结果:

- `task_core.py` 可以被一句话描述为“稳定 façade + 依赖装配入口”
- `src/core/` 不再继续扩大对 `src.services.*` 的直接依赖面
- `payment.py` 不再承担完整业务流程
- Dashboard router 不再直接承载大段 SQL、事务、媒体装配和外部 HTTP 编排
- `tasks.py` 只剩少量接入层职责
- Dashboard 前端状态逻辑按领域拆开
- Gallery 家族页和生成页的公共浏览/提交逻辑被控制层统一
- `task_service.py` 的纯透传 seam 数量开始下降，而不是继续增长
- compat 层数量开始下降，热点门禁继续有效

## 8. 暂不建议做的事

- 不建议本轮重写 `backend/app/queue_manager.py`
- 不建议本轮大规模调整 worker 协议
- 不建议把所有 compat / seam 一次性删光
- 不建议一次性重写整个 Dashboard 前后端
- 不建议在重构期同时引入大规模新业务需求

## 9. 建议的起手第一刀

如果现在就开始动代码，建议从下面这一刀开始:

### 起手项

- 先处理 `src/core/billing_core.py`、`src/core/task_core_persistence.py`，再回到 `task_core.py` / `auth_core_dependencies.py`

### 第一刀的具体目标

- 让 `billing_core.py` 改为显式依赖注入，而不是直接抓 `QuotaManager`、`redis_client`、`permission_service`
- 让 `task_core_persistence.py` 停止依赖运行时 `permission_service` 导入，并显式接收下载/刷新用户组能力
- 在不破坏现有 builder seam 的前提下，把 `task_core.py` 中对 `storage`、`image_service`、`TaskRegistry`、`redis_client` 的直接依赖继续收口到 builder/provider
- 明确 `auth_core_dependencies.py` 在本轮中的角色是“受控 composition root”还是“继续拆薄的 provider 转发层”
- 不改外部接口，不改返回结构，只改依赖进入方式

### 选择这个切口的原因

- 风险相对可控
- 当前收益最大
- 能为后续 Dashboard 后端 service 化、支付链路 service 化和终态统一打基础

## 10. 完成状态跟踪

| 阶段 | 目标 | 状态 | 备注 |
| --- | --- | --- | --- |
| A | 收紧 `core -> services` 依赖边界 | 进行中（后半程） | `billing_core.py`、`task_core_persistence.py`、`task_core.py`、`auth_core_dependencies.py` 的主体收口已完成，当前重点转为 compat/provider 泄漏面继续缩减 |
| B | 收缩任务域双门面的残余纯透传 | 进行中（接近收尾） | `task_service.py` 已明显变薄，`task_service_facade_seams.py` 基本只剩 `complete_monitored_bot_task_seam()` 待评估去留 |
| C | 统一终态失败与清理流程 | 进行中（共享模板已形成） | shared finalization primitive、policy 与 bot presentation policy 已落地，恢复/僵尸已接入，取消/系统终止/后端失败等入口仍待进一步收敛 |
| D | 推进主站 Web API 与 Dashboard 后端薄路由化 | 基本完成 | `payment.py`、`tasks.py` 与 Dashboard backend 主体热点已完成主目标，后续以守约、热点巡检和相邻回归为主 |
| E | 收敛主站前端重复与 Dashboard 前端状态复杂度 | 进行中（已有底座，尚未系统展开） | Dashboard `client.js` 公共层、Gallery 家族页共享壳层、生成页 workbench 主路径均已存在，但统一 controller、领域拆分和双栈收口仍待正式推进 |
| F | 清理 compat、扩展静态门禁与阶段文档 | 进行中（基础已具备） | 热点门禁已落地，compat 第二轮清理、静态门禁补齐与阶段文档持续回写仍待推进 |
