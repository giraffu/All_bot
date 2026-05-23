# All_bot 代码优化方案（按当前代码校准后的主线版本）

校准时间: 2026-05-23

## 1. 文档目的

本文档用于指导下一轮“用户主链路优先”的代码优化与架构收口工作。

本版基于当前仓库真实代码状态重新校准，重点处理以下问题：

- 修正上一版中已过期的现状描述
- 消除同一文档内“前文仍视为待做、后文又写已完成”的自相矛盾
- 将已进入维护态的模块降级处理，不再与主战场混排优先级
- 继续把管理后台（Dashboard backend/frontend）降级为非当前主线

本版适用边界：

- 重点关注 Bot 主链路、主站 Web API、任务域 `core`、主站用户侧前端
- 管理后台由于当前仅有单用户使用，其结构优化、状态拆分和进一步模式统一继续降级为“可延后事项”

本轮主线目标是：

- 降低任务主链路的认知复杂度
- 收紧 `core` 层依赖边界与 compat/provider 泄漏面
- 继续推进终态失败、恢复、取消、强制终止的统一模板，但不夸大当前统一程度
- 守住主站 Web API 的薄路由形态，防止业务重新回填 router
- 把主站前端的浏览/提交公共流程继续提升为稳定控制层
- 在不破坏现有功能和测试稳定性的前提下，以低风险切片推进重构

## 2. 当前代码快照

### 2.1 已完成或基本完成的主线收口

以下事项已不再适合作为“主要未完成问题”描述，而应视为已落地基础：

- `task_service.py` 已基本退出 Web 主路径，当前主要承担 Telegram 表示层职责；Web 提交与取消已主要走 `src/web_api/services/* -> src/core/task_core.py`
- `task_core.py` 已形成“façade + 依赖 builder + 独立流程模块”的基本结构，`submission/runtime/persistence/finalization/web_monitor` 已拆开
- `src/core/task_core_persistence.py` 已形成 builder/compat wrapper + `task_core_persistence_flow.py` 的分层，成功持久化主流程已下沉到专门 flow，但主路径仍保留若干运行时默认回填
- `src/core/billing_core.py` 已具备 loader/provider/dependency builder 结构，会员结算纯规则已下沉到 `billing_core_membership.py`；当前主要问题不再是“大文件混杂”，而是 provider 暴露面仍可继续缩小
- `src/core/auth_core_dependencies.py` 已更明确地承担受控 composition root 角色，`auth_core.py` 主流程未回退为直接抓全局单例
- `src/web_api/routers/users.py` 已基本薄路由化，资料、偏好、历史、apply-context、send-to-bot 等逻辑已下沉到 service
- `src/web_api/routers/gallery.py` 已基本薄路由化，帖子列表、互动、评论、状态更新、apply-context 已主要由 `gallery_service` 承接
- `src/web_api/routers/tasks.py` 已完成主体收口，提交、取消、结果查询、SSE 与残余基础设施拼装已基本下沉到专门 service
- `src/web_api/routers/payment.py` 已完成“router + service/presenter”收口，对外路径、字段与返回层级保持不变
- `src/web_api/routers/auth.py`、`src/web_api/routers/storage.py` 已完成 service 化补票，并已有 focused tests / passthrough tests；当前更适合归入“守约与防回填”而非“待补票热点”
- `task_core_finalization.py`、`task_failure_finalization_service.py`、`task_service_finalize.py` 已形成终态失败共享 helper / policy / presentation policy 的基础路径
- `recovery_service.py`、`zombie_cleaner_service.py` 已进一步收口到共享 helper，但外围服务仍保留少量恢复/清理特例，尚不能描述为“只剩发现问题和组装上下文”
- `task_service.py` 已连续移除多轮纯参数透传 seam，但剩余 seam 目前主要收敛在 `TaskService` 类内部，而非独立 façade seam 文件
- `task_core_persistence.py`、`task_core_runtime.py`、`task_core_finalization.py`、`auth_core_telegram_validation.py`、`auth_core_telegram_verify.py`、`auth_core_password_hash.py` 已连续清理多轮“默认参数提前绑定实现体”问题，运行时回填口径明显统一
- `task_core_submission.py`、`task_core_web_history_warmup.py`、`task_core_web_monitor.py` 等 `task_core` 周边支撑模块，近期也已补齐 `shield` / `create_task` 的运行时回填与 focused tests
- 主站前端 `Gallery` 家族页与生成页已具备一定共享基础，已有共享壳层、详情弹层适配、评论 composable、上传预览和任务流监听 composable，但控制层仍明显强于壳层复用，尚未收口为统一 page/submit controller
- 热点门禁与回归触发规则已落地，`scripts/run_hotspot_regression.sh` 与 `.github/workflows/hotspot_regression_gate.yml` 已存在；但 branch protection required checks 是否完全固化仍需以仓库设置侧为准，不能仅凭代码仓现状视为闭环

### 2.2 当前仍然突出的主线剩余问题

### 2.2.1 `core -> services` 依赖边界已进入后半程，但 `task_core` compat/proxy 与非主战场直连残余仍未完全收口

重点文件：

- `src/core/task_core.py`
- `src/core/task_core_persistence.py`
- `src/core/billing_core.py`
- `src/core/auth_core_dependencies.py`
- `src/core/task_dispatcher.py`
- `src/core/gallery_core.py`
- `src/core/media_processor.py`
- `src/core/user_facade.py`

当前问题：

- `task_core.py` 已接近“稳定 façade + 依赖装配入口”，但仍保留 `_CompatServiceProxy`、getter 与基础设施泄漏面，尚未退到最终极简态
- `task_core_persistence.py` 的主路径虽已下沉到 flow，但 `persist_successful_task_result(...)` 仍保留多组运行时默认回填，不能视为“已完全摆脱 fallback 形态”
- `billing_core.py` 当前主要问题不是 compat proxy，而是 provider 暴露面、全局实例依赖和测试替换成本仍可继续缩减
- `auth_core_dependencies.py` 当前可被解释为受控 composition root；是否继续下沉为更薄 registry，应作为收益评估项，而非默认必须继续拆
- `task_dispatcher.py`、`gallery_core.py`、`media_processor.py`、`user_facade.py` 等非主战场文件中仍能看到 `core -> services` 直连残余，说明边界治理不能只盯主链路热点文件
- 当前主要矛盾已从“没有 seam”变为“builder/provider 已有，但 compat 壳、运行时 fallback 和非主战场直连还没有继续缩到最小”

### 2.2.2 `task_service.py` 已明显变薄，但残余 wrapper / seam 的治理对象已变成 `TaskService` 类内 patch 点，而非独立 façade seam 文件

重点文件：

- `src/services/task_service.py`
- `src/services/task_service_flow.py`
- `src/services/task_service_completion.py`
- `src/services/task_service_finalize.py`
- `src/services/task_service_entrypoints.py`

当前问题：

- `task_service.py` 已明显变薄，早先 `_run_* / _prepare_* / _monitor_* / _handle_*` 多层透传已大幅移除
- 原 `task_service_facade_seams.py` 已不存在；当前主要 seam/patch 点集中在 `TaskService` 类内部静态方法与 compat 导出，而不是独立 façade seam 文件
- `TaskService` 主文件仍保留若干 `_build_* / _run_* / _handle_* / _complete_*` 风格包装方法，阅读 Bot 提交主路径时的跨函数/跨文件跳转层数仍偏高
- 当前主要矛盾已从“职责混杂”转为“如何在保留必要 patch/compat 点的前提下继续减层，而不是让过渡包装长期常驻”

### 2.2.3 终态失败、恢复、取消与强制终止已具备共享模板基础，但边角入口与“请求发起 vs 终态收口”边界仍未完全理顺

重点文件：

- `src/core/task_core_finalization.py`
- `src/core/task_core_runtime.py`
- `src/services/recovery_service.py`
- `src/services/zombie_cleaner_service.py`
- `src/services/task_recovery_runtime.py`
- `src/services/tg_task_runtime.py`

当前问题：

- 共享 finalization primitive、task record -> policy -> finalize 路径、bot presentation policy 已存在；但还不能写成“所有入口都已完全统一收口”
- `cancel_user_task()` 当前更接近“取消请求发起”，而不是取消终态 finalize；Bot/Web 两端对“取消请求成功”和“终态清理完成”仍属于两段式理解
- `recovery_service.py` 仍保留恢复成功后的 runtime cleanup；`zombie_cleaner_service.py` 仍保留 no-user 分支下的 backend cancel 和并发锁自愈等外挂动作
- `task_core_runtime.py` 已接近运行态清理的真实核心边界，而 `tg_task_runtime.py` 更适合作为 Telegram 表示层运行时组件理解，不应在文档口径上与 finalization 核心边界混写
- 当前阶段的关键问题已不是“有没有共享模板”，而是“模板已有，但边角入口、命名和职责说明还没有完全稳定，外围服务仍有少量特例动作尚未归并”

### 2.2.4 主站 Web API 主体业务路由已进入维护态，但仍需持续守住薄路由形态、防止业务回填

重点文件：

- `src/web_api/routers/tasks.py`
- `src/web_api/routers/payment.py`
- `src/web_api/routers/auth.py`
- `src/web_api/routers/storage.py`
- `src/web_api/services/task_action_api_service.py`
- `src/web_api/services/auth_api_service.py`
- `src/web_api/services/storage_api_service.py`

当前问题：

- `payment.py` 已完成 service/presenter 化，本阶段重点变为持续守护“只改后端组织方式、不动前端契约”的约束
- `tasks.py` 的 router 已接近 passthrough，但仍保留少量接入层依赖注入；后续应防止基础设施细节重新回填
- `auth.py`、`storage.py` 已完成 service 化，不再属于“待补票热点”；但如果后续新增鉴权、预签名或异常处理逻辑，仍需防止堆回 router
- 对主线业务而言，Web API 当前的主要任务已不是继续大拆，而是守约、热点巡检、focused tests 与相邻回归持续跟进

### 2.2.5 主站前端共享壳层已先行收口，但页面控制层仍未真正统一

重点文件：

- `frontend/src/views/Gallery.vue`
- `frontend/src/views/MyFavorites.vue`
- `frontend/src/components/MySubmissionsPanel.vue`
- `frontend/src/views/ImageAndPrompt.vue`
- `frontend/src/views/SingleImage.vue`
- `frontend/src/views/FaceSwap.vue`
- `frontend/src/views/SingleImageToVideo.vue`
- `frontend/src/views/VideoSwap.vue`

当前问题：

- Gallery 家族页已经具备 `usePagedPostBrowser`、详情弹层适配、模板应用入口等共享底座，但当前更多是“共享壳层 + 局部 composable 复用”，还不能算稳定 page controller
- 多个生成页已经存在 `templateApply` store、共享 workbench host 与上传/监听基础积木，但 `ImageAndPrompt`、`SingleImage`、`FaceSwap`、`SingleImageToVideo`、`VideoSwap` 的模板预填、上传/提交/监听/重置逻辑仍未统一到单一 submit controller
- 当前阶段的核心问题是“壳层复用先于控制层统一”，若继续只抽外壳而不抽 controller，页面认知成本不会明显下降
- 现阶段更适合在已有 composable 基础上组合出稳定 controller，而不是先引入新的抽象名词再回头找落点

### 2.2.6 compat 第二轮清理已具备条件，但仍缺系统化盘点与防回涨约束

重点文件：

- `src/core/task_core.py`
- `src/services/task_service.py`
- `src/core/task_core_persistence.py`
- `src/core/billing_core.py`
- `frontend/src/views/ImageAndPrompt.vue`
- `frontend/src/views/SingleImage.vue`
- `frontend/src/views/FaceSwap.vue`
- `frontend/src/views/SingleImageToVideo.vue`
- `frontend/src/views/VideoSwap.vue`

当前问题：

- 虽然 focused tests 和热点门禁已经存在，但“哪些 compat seam 仍要保留，哪些已可删”的第二轮收口还没有形成明确盘点表与删除条件
- `src/core/` 禁止新增 `import src.services.*`、router 禁止重新回填业务编排等规则，目前更多依赖人工纪律而不是更强的静态门禁
- 热点门禁虽已存在，但 branch protection required checks 是否已在仓库设置侧固化仍待人工确认；因此当前状态更接近“已有回归门禁基础，但防回涨约束未完全闭环”
- 当前真正缺的不是再起一个大计划，而是把“该删 / 该留 / 暂缓”的 seam、wrapper、compat、双栈入口盘清楚，并持续回写状态

### 2.3 降级关注事项（非当前主线）

以下事项继续不作为当前方案的主要推进对象：

- `dashboard/backend/*` 的进一步模式统一
- `dashboard/frontend/src/composables/useUserTableState.js` 的职责拆分
- `dashboard/frontend/src/api/api.js` 的领域化拆分
- 管理后台 UI / 状态组织的进一步打磨

说明：

- 这些工作并非没有价值，而是当前仅有单用户使用管理后台，收益明显低于继续打磨任务主链路、前端控制层与 `core` 边界治理
- 因此本版方案仅保留“现状说明”，不再把它们放进主线优先级

### 2.4 当前阶段判断

- `A 阶段`：主体已落地，近期又继续完成 `task_core_persistence.py`、`task_core_runtime.py`、`auth_core_dependencies.py`、输入准备链的多轮收口；整体仍处于后半程，但重点已从“先拆出模块”转为“继续缩 compat/proxy/fallback 暴露面”
- `B 阶段`：主路径已进一步瘦身；独立 façade seam 文件已退出历史，当前已进入“盘点 `TaskService` 类内剩余 patch 点并继续压缩残余 wrapper”的收尾型减层阶段
- `C 阶段`：共享模板已形成，但当前转为“边角入口收口、取消请求与终态收口边界澄清、僵尸/恢复特例归并”的中后段治理
- `D 阶段`：主站 Web API 主体业务路由与例外热点补票已基本完成；当前已进入维护态，以守约、热点巡检和相邻回归为主，不再是主线阻塞项
- `E 阶段`：已成为用户主链路下的主要前端战场；共享壳层基础已形成，但 page controller / submit controller 仍未真正成型
- `F 阶段`：热点门禁与 focused tests 基础已具备，compat 第二轮清理也已开始实质推进；但盘点表、静态门禁补齐、required checks 固化与阶段文档持续回写仍未系统落实

## 3. 调整后的总体目标

### 3.1 架构目标

- `task_core.py` 只保留稳定 façade、依赖构建入口和少量跨模块编排
- `src/core/` 不再新增对 `src.services.*` 的直接依赖，既有依赖逐步收口到 builder/provider
- `task_service.py` 继续保留 Telegram 表示层职责，但减少纯参数透传 seam
- 主站 Web API Router 只做参数声明、依赖注入、权限和响应映射
- 主站前端页面尽量只保留页面装配，公共浏览/提交流程下沉到 composable/controller

### 3.2 可维护性目标

- 优先治理“当前仍重”的主链路文件，而不是继续重复治理已进入维护态的模块
- 继续降低任务主链路无价值跳转
- 统一终态失败与清理动作模板，并明确“请求发起”与“终态收口”的职责边界
- 将主站前端公共积木提升为公共控制层，而不是只停留在局部复用
- 在不破坏现有 patch 点与 focused tests 的前提下，逐步进入 compat 第二轮清理

### 3.3 风险控制目标

- 继续坚持低风险切片，不做一次性大改
- 每一阶段结束都保留 focused tests 或相邻主链路回归
- compat 先保留，再在新路径稳定后删除
- 不为了文档整洁而提前删除仍在被测试 patch 点依赖的 seam

### 3.4 收口原则（防止过度重构）

- 优先删除无价值跳转层，而不是继续新增过渡层；主路径跳转层数下降，比文件数变少更重要
- 只保留三类长期层次：稳定 façade / 入口层、真实复用的 controller 或 helper、必要的 compat/patch 点
- 纯参数平移 wrapper、只换名字不换职责的 seam、只有壳层复用但页面并未变薄的半成品抽象，不应长期常驻
- 新增任何过渡层时，必须同时写明退出条件：何时迁移测试、何时删除 compat、何时结束双栈路径
- 主链路文件允许保留少量稳定 patch 点，但不得继续为小改动叠加 `_build_* / _run_* / _handle_*` 代理方法
- 前端优先抽 controller，再抽 shell；若页面级编排没有明显变薄，则不应继续新增展示壳层
- `router/service/core` 的收口目标不是“层数越多越专业”，而是“边界更清楚、主路径更短、回归面更稳定”

## 4. 分阶段优化方案（按当前代码校准）

## 阶段 A: 收紧 `core -> services` 依赖边界

状态: 进行中（后半程，重点转向 compat/proxy/fallback 缩面）

### A1. `task_core.py`

目标状态：

- builder seam 保留在 façade 附近，并继续作为 focused tests 的稳定 patch 点
- `task_core.py` 不再直接持有 `storage`、`image_service`、`TaskRegistry`、`redis_client` 这类 compat proxy 暴露
- 流程函数内部不再临时 import `src.services.*`

具体动作：

1. 将 `TaskRegistry`、`redis_client`、`image_service`、`storage` 的使用点继续收口到最小依赖接口或 provider
2. 对现有 builder 进行二次瘦身，明确哪些 builder 负责“依赖构造”，哪些模块负责“流程执行”
3. 明确 `process_and_submit_task` 等 façade 的稳定输入输出，不在主文件继续回填基础设施细节，并逐步取消 `__all__` 级别的基础设施泄漏
4. 维持 `tests/core/` focused tests 的稳定 patch 面，不贸然拆 compat seam

验收标准：

- `task_core.py` 可以被描述为“稳定 façade + 依赖装配入口”
- 流程模块内部不再偷偷回查 `src.services.*`
- 新增基础设施能力时，不再默认往 `task_core.py` 顶部追加 service import

### A2. `task_core_persistence.py` / `billing_core.py`

目标状态：

- `task_core_persistence.py` 的主路径更接近“compat wrapper + 明确注入能力”，而不是大量运行时默认回填
- `billing_core.py` 的计费、权限、限流依赖尽量缩到最小能力面

具体动作：

1. 继续压缩 `task_core_persistence.py` 中 `user_logger_factory`、媒体元数据提取、materialization flow 等默认回填入口
2. 继续压薄 `task_core_persistence.py` 的主文件壳层，减少静态提示噪声
3. 继续处理 `billing_core.py` 的 provider 暴露面，缩减对全局实例 patch 的依赖
4. 继续维持 persistence 链与周边 helper 的 runtime binding 一致口径

验收标准：

- `src/core/` 内新增直接 `import src.services.*` 的需求显著下降
- `billing_core.py`、`task_core_persistence.py` 的测试替换成本继续下降
- `task_core_persistence.py` 主文件更接近“compat wrapper + dependency builder”

### A3. `auth_core_dependencies.py`

目标状态：

- `auth_core.py` 继续保持“主流程不直接依赖 service 单例”的现状
- `auth_core_dependencies.py` 被明确定位为允许存在的 composition root，除非收益显著，否则不为拆而拆

具体动作：

1. 明确阶段边界：本轮先不回退 `auth_core.py` 当前的依赖收口成果
2. 评估 `auth_core_dependencies.py` 是否需要继续抽成更薄 registry；若收益不明显，则只保留文档校准，不再强推拆分
3. 若继续拆分，只移动装配逻辑，不改 `auth_core.py` 对外行为和认证语义

验收标准：

- `auth_core.py` 主流程不重新出现 `redis_client`、`permission_service` 等直接依赖
- `auth_core_dependencies.py` 的角色在代码和文档中保持一致

## 阶段 B: 收缩任务域双门面的残余纯透传

状态: 进行中（主路径已瘦身，进入 `TaskService` 类内 patch 点盘点与减层阶段）

### B1. `task_service.py`

目标状态：

- 继续保留 Telegram 输入适配、消息发送、入口绑定、少量 patch 点
- 尽量移除没有兼容价值的纯参数透传 wrapper

具体动作：

1. 盘点 `TaskService` 类内的 `_prepare_* / _run_* / _handle_* / _complete_*` 包装点
2. 将真正需要 compat/patch 的 seam 留下
3. 将只有参数平移价值的 wrapper 合并或删除
4. 对 `TaskService._complete_monitored_bot_task(...)`、`_prepare_and_submit_bot_task(...)`、`_run_bot_task_flow(...)` 等关键桥接点做最终去留评估
5. 为保留的 seam 标注明确身份：是 patch 点、兼容壳，还是副作用隔离层；未满足任一条件的 wrapper 优先删除
6. 不再新增 `_build_* / _run_* / _handle_*` 风格代理方法，新增行为优先直挂稳定入口或下沉到 flow/helper

验收标准：

- 新增需求不需要继续给 `TaskService` 叠加 `_build_*` / `_run_*` / `_handle_*` 代理方法
- 阅读 Bot 提交主路径时，跨文件跳转层数继续下降
- 保留的 seam 都能被一句话解释其存在理由，且能对应测试 patch 点或明确 compat 价值

## 阶段 C: 统一终态失败与清理流程

状态: 进行中（共享模板已形成，当前重点是边角入口收口与职责边界澄清）

### C1. 目标

将以下场景进一步统一到共享 finalization 模板：

- 恢复失败
- 僵尸任务清理
- 用户取消
- 系统终止
- 后端失败
- API 发起取消请求与终态清理的职责边界

### C2. 具体动作

1. 继续收敛统一的终态上下文对象或等价 policy/helper 结构，至少覆盖 registry task id、user、refund、cleanup、backend cancel、notify
2. 让 `recovery_service.py` 和 `zombie_cleaner_service.py` 更明确地只负责发现问题、组装上下文和调用共享 finalization flow；对暂时不能下沉的特例动作单独标记例外原因
3. 把 `task_core_runtime.py` 明确为取消/强制终止/运行态清理的核心边界文件，避免外围模块重新各自实现 runtime cleanup
4. 在 helper 命名与文档中明确“取消请求发起”和“取消终态收口”的分工
5. 将僵尸清理中仍留在服务层的 backend cancel / cleanup 特例、恢复链 runtime cleanup 特例继续归并到共享 helper 或 runtime 边界

验收标准：

- 新增一种失败终态时，不需要复制恢复/清理脚本的大段逻辑
- 退款、清锁、通知口径一致
- 僵尸清理、恢复失败、取消和强制终止的剩余额外挂动作显著减少，并被清楚记录为“已归并”或“暂留例外”
- `tg_task_runtime.py` 在文档中被清晰定义为 Telegram 表示层运行时组件，而非终态清理核心边界

## 阶段 D: 主站 Web API 薄路由守护

状态: 维护态（主体完成，后续以守约、防回填、测试巡检为主）

### D1. 当前策略

- `users.py`、`gallery.py`、`tasks.py`、`payment.py`、`auth.py`、`storage.py` 以维持和小修为主，不再作为本轮主要重构战场
- 若出现新增业务逻辑，优先下沉到 service / presenter，而不是重新堆回 router
- 后续更关注 focused tests、passthrough tests、热点巡检与相邻回归

### D2. 具体动作

1. 持续守住 `tasks.py` / `payment.py` / `auth.py` / `storage.py` 的 passthrough 路由形态，不允许基础设施细节重新回填
2. 若新增 JWT、异常映射、预签名、对象 key 生成等逻辑，优先写入 service，而不是 router
3. 保持现有 `auth.py` / `storage.py` focused tests 与 router/service 契约测试不过期
4. 将 Web API 薄路由守约要求纳入 review checklist 与热点巡检清单

验收标准：

- 主站 Web API 的主体业务路由继续保持薄路由
- `auth.py` / `storage.py` 的新增逻辑不再继续堆回 router
- `tasks.py` / `payment.py` 继续保持以 service/presenter 为主
- Web API 维护态的测试覆盖和热点巡检不明显退化

## 阶段 E: 收敛主站前端页面级重复

状态: 进行中（已成为用户主链路下的主要前端战场，当前重点是控制层补课）

### E1. Gallery 家族页控制层继续收口

目标文件：

- `frontend/src/views/Gallery.vue`
- `frontend/src/views/MyFavorites.vue`
- `frontend/src/components/MySubmissionsPanel.vue`

具体动作：

1. 在现有共享底座上优先补统一页面控制层，而不是继续优先抽新的展示壳层
2. 基于 `usePagedPostBrowser`、评论、互动、详情弹层、模板应用等现有 composable 收敛页面级装配
3. 页面本身只保留数据源差异、少量 slot 和视图结构

验收标准：

- 三个页面的逻辑差异被压缩到“数据来源和特例动作”
- 公共逻辑不再以碎片形式散落在各页内
- 若页面逻辑未明显变薄，则不再接受仅新增 adapter/shell 的“伪收口”改法

### E2. 多种生成页 submit controller 收口

目标文件：

- `frontend/src/views/ImageAndPrompt.vue`
- `frontend/src/views/SingleImage.vue`
- `frontend/src/views/FaceSwap.vue`
- `frontend/src/views/SingleImageToVideo.vue`
- `frontend/src/views/VideoSwap.vue`

具体动作：

1. 先把 `templateApply` store + `TemplateApplyWorkbenchHost` 视为已落地的主路径控制层，再梳理旧路由兼容入口的退出条件
2. 在现有共享壳层、上传预览和任务流监听基础上，优先抽统一任务提交流程 composable/controller
3. 收敛模板预填、上传前置校验、payload 组装、提交任务、stream/result 监听、重置结果和错误提示
4. 对双文件上传类页面优先抽公共控制逻辑，避免 `FaceSwap` / `VideoSwap` 继续各自维护相似状态机

验收标准：

- 新增一种生成页时，不需要再复制现有页面的大段提交流程
- 公共逻辑从“共享积木”提升为“共享提交流程控制层”
- 新 workbench 主路径与旧路由兼容路径的职责边界清晰
- 旧生成页若仍保留大量页面内 payload / 上传 / 重置编排，则不得视为 submit controller 已完成

## 阶段 F: 清理 compat、扩展静态门禁与阶段文档

状态: 进行中（回归门禁已具备，第二轮清理盘点与静态约束仍待系统展开）

### F1. compat 清理原则

只在满足以下条件后才删除 compat：

- 新路径已稳定被主流程使用
- focused tests 已覆盖新路径
- 旧 patch 点或旧测试已迁移
- 至少完成一轮相邻模块回归

补充原则：

- 每个 compat / seam 在保留时都要记录“存在理由”“删除前提”“对应测试”
- 若 compat 只剩纯参数平移价值，且无 patch / compat / 副作用隔离意义，应优先进入删除候选表
- 第二轮清理优先删除“主路径已不经过，但阅读时仍会被看到”的常驻过渡层

### F2. 建议补齐的门禁

建议新增或强化以下静态检查 / review 门禁：

- `src/core/` 禁止新增直接 import `src.services.*`
- `src/web_api/routers/` 禁止新增复杂业务编排
- `task_service.py` 禁止继续增加纯参数平移 seam
- 主站前端新增页面若复用已有任务提交流程或浏览流程，优先接 controller，不允许复制旧页面大段逻辑
- 将热点 workflow 的结果纳入 branch protection required checks，避免门禁仅停留在 workflow 存在层面
- 为 `task_dispatcher.py`、`gallery_core.py`、`media_processor.py`、`user_facade.py` 等残余 `core -> services` 直连点补轻量扫描或 review checklist

### F3. 文档与回归同步要求

- 每阶段完成后同步更新本方案状态表
- 若职责边界发生变化，补充到 `docs/` 的对应模块文档
- 继续沿用热点门禁与黄金路径回归，不另起一套平行规则
- 若某阶段以“减层”为目标，文档需同步记录已删除的 wrapper / seam 与仍保留的例外点，避免下一轮继续误判状态

## 5. 推荐实施顺序（按当前代码重排）

建议按下面顺序推进：

1. 先建立第二轮清理盘点表：列出 `task_service`、`task_core`、`task_core_persistence`、`billing_core`、旧生成页中“该删 / 该留 / 暂缓”的 wrapper、seam、compat 与双栈入口
2. `src/services/task_service.py` 类内残余 wrapper / seam 评估与减层收尾
3. 主站旧生成页 submit controller 收敛，优先统一模板预填、payload 与上传/监听/重置流程
4. Gallery 家族页在现有共享底座基础上继续收口为统一 page controller，避免继续只加壳层
5. `src/core/task_core.py`、`task_core_persistence.py`、`billing_core.py`、`auth_core_dependencies.py` 的 compat/provider/fallback 第二轮缩面
6. `src/core/task_core_runtime.py`、`task_core_finalization.py`、`recovery_service.py`、`zombie_cleaner_service.py` 的边角入口和职责边界继续统一
7. compat 第二轮清理、静态门禁补齐与阶段文档持续回写
8. Web API 薄路由守护、focused tests 与热点巡检并行跟进
9. 管理后台相关结构优化（降级项，有空再做）

原因：

- 当前最重的问题已经不再是 `auth.py` / `storage.py` 补票，也不再是管理后台，而是用户主链路中仍存在的过渡层常驻、前端控制层缺口和 `core` 边界缩面
- 若不先盘点“哪些层该删、哪些层该留”，继续推进重构容易演变成边拆边叠，进一步放大过度重构感
- `task_service.py` 的残余 wrapper / seam、旧生成页 controller 缺口，以及 Gallery 家族页控制层缺口，都是当前最能直接降低认知复杂度的切口
- `core` compat/provider/fallback 缩面与 `finalization` 边角统一仍重要，但应建立在“先控层数、再推进边界”的节奏上
- Web API 当前更适合并行守护，而不是继续占据主线前几位

## 6. 每阶段交付物

每个阶段至少应交付以下内容：

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

本轮主线优化完成后，应满足以下结果：

- `task_core.py` 可以被一句话描述为“稳定 façade + 依赖装配入口”
- `src/core/` 不再继续扩大对 `src.services.*` 的直接依赖面
- 主站 Web API 的主体业务路由继续保持薄路由，新增逻辑不再回填 router
- Gallery 家族页和生成页的公共浏览/提交逻辑继续向统一控制层收敛
- `task_service.py` 的纯透传 seam 数量继续下降，而不是继续增长
- compat 层数量开始下降，热点门禁继续有效
- 新增重构不再以“继续加一层 wrapper / shell / seam”为默认手段，而是优先通过缩面、减层和统一 controller 解决问题

## 8. 暂不建议做的事

- 不建议本轮重写 `backend/app/queue_manager.py`
- 不建议本轮大规模调整 worker 协议
- 不建议把所有 compat / seam 一次性删光
- 不建议一次性重写整个 Dashboard 前后端
- 不建议在重构期同时引入大规模新业务需求

## 9. 当前主线起手优先项（按现状重排）

如果现在继续沿主线推进，建议优先从下面几类切口继续：

### 第一优先级

- 建立“该删 / 该留 / 暂缓”的第二轮清理盘点表
- `task_service.py` 类内残余 wrapper / seam 减层
- 主站旧生成页 submit controller 收敛

### 第二优先级

- Gallery 家族页 page controller 继续收口
- `task_core.py`、`task_core_persistence.py`、`billing_core.py`、`auth_core_dependencies.py` 的 compat/provider/fallback 第二轮缩面
- `task_core_runtime.py`、`task_core_finalization.py`、`recovery_service.py`、`zombie_cleaner_service.py` 的边角入口与职责边界继续统一

### 第三优先级

- 静态门禁与 branch protection required checks 补齐
- 非主战场 `core -> services` 直连残余点清理
- Web API 薄路由守护、focused tests 与热点巡检

### 后续主战场

- compat 第二轮清理持续回写
- 前端共享控制层沉淀为稳定模式

## 10. 完成状态跟踪

| 阶段 | 目标 | 状态 | 备注 |
| --- | --- | --- | --- |
| A | 收紧 `core -> services` 依赖边界 | 进行中（后半程，重点转向 compat/proxy/fallback 缩面） | `task_core_persistence.py`、`task_core_runtime.py`、`auth_core_dependencies.py` 与输入准备链已继续清掉多处转发壳或局部 adapter；当前重点仍是 `task_core.py` 本体 compat proxy、`task_core_persistence.py` fallback 面、`billing_core.py` provider 暴露面，以及非主战场 `core -> services` 直连残余 |
| B | 收缩任务域双门面的残余纯透传 | 进行中（主路径继续瘦身，进入 `TaskService` 类内盘点与收尾型减层） | 独立 façade seam 文件已退出历史，`task_service.py` 又移除了多轮 public 转发壳、局部 seam wrapper 与死别名；当前重点转为盘点 `TaskService` 类内剩余 patch 点的真实价值，并继续降低 Bot 主路径跨函数/跨文件跳转层数 |
| C | 统一终态失败与清理流程 | 进行中（共享模板已形成，转入边角入口收口与职责边界澄清） | shared finalization primitive、policy 与 bot presentation policy 已落地；`recovery/zombie` 已进一步并到共享 helper，但恢复成功 cleanup、zombie no-user 分支 cancel、取消请求 vs 终态 finalize 的边界仍需继续收口 |
| D | 主站 Web API 薄路由守护 | 维护态（主体完成） | `payment.py`、`tasks.py`、`auth.py`、`storage.py` 与主体业务路由已完成当前阶段主目标；后续以守约、防回填、focused tests、热点巡检和相邻回归为主，不再是主线阻塞项 |
| E | 收敛主站前端页面级重复 | 进行中（已成为用户主链路下的主要前端战场，重点是控制层补课） | Gallery 家族页共享壳层与生成页 workbench 主路径均已存在，但 page controller / submit controller 仍未成型；后续应优先抽 controller，而不是继续只抽 shell |
| F | 清理 compat、扩展静态门禁与阶段文档 | 进行中（已开始实质清理，但制度闭环仍待补齐） | 热点门禁已落地，compat 第二轮清理已在 `task_service`、`task_core` 周边与若干依赖装配模块中持续推进；但清理盘点表、静态门禁补齐、required checks 固化与阶段文档持续回写仍待推进 |
| 降级项 | Dashboard backend/frontend 进一步结构优化 | 延后处理 | 管理后台当前仅单用户使用，不再列为本版主线推进对象 |
