# All Bot 无功能变更修复清单（P0 / P1 / P2）

## 说明
- 目标：只做降风险、不改业务语义、不影响现有用户功能的修复。
- 原则：优先修安全边界、权限边界、资源回收、错误实现、分层收口，不碰计费规则、任务调度策略、会员口径、返佣口径。
- 方式：尽量采用“局部替换 + 补测试/补断言 + 不改接口返回结构”的推进方式。

## P0

### 2. 封堵素材泄漏面
- 收紧 [gallery.py](file:///home/hfy/APP/All_bot/src/web_api/routers/gallery.py) 中 `/posts/{post_id}/apply-context` 的输入文件回传逻辑。
- 明确“哪些帖子允许复用原始输入、哪些只能复用提示词/尺寸/时长元信息”。
- 在不改接口主体结构前提下，可先把 `input_file_url` 变为条件返回或默认不返回。

### 3. 修复任务注册键不一致
- 统一 [task_core.py](file:///home/hfy/APP/All_bot/src/core/task_core.py) 中 `task_id`、`registry_task_id`、`backend_task_id` 的职责和生命周期。
- 确保注册、状态更新、失败回滚、删除、恢复全链路只使用同一主键语义。
- 这是“无功能变更”里最关键的一项，因为它修的是一致性，不改业务逻辑。

### 4. 移除 SSE query token
- 修正 [tasks.ts](file:///home/hfy/APP/All_bot/frontend/src/stores/tasks.ts) 与 [tasks.py](file:///home/hfy/APP/All_bot/src/web_api/routers/tasks.py) 的鉴权传递方式。
- 若暂时不能改成 cookie，可先做“后端仅接受 header / 内部短期票据”，但不要改返回事件格式。
- 这项属于安全修复，不应改变任务流表现。

### P0 验收重点
- 现有登录、提交任务、任务流监听、广场应用模板功能可正常使用。
- 不再存在“登录后即可拿到别人原始输入文件”的路径。
- 失败回滚后注册表无脏任务残留。

## P1

### 1. 修复结果接口存在性泄漏
- 调整 [tasks.py](file:///home/hfy/APP/All_bot/src/web_api/routers/tasks.py) 的 `/tasks/{task_id}/result` 查询方式。
- 改成“按当前用户 + task_id 一起查”，避免通过 403/200 区分任务是否属于别人。
- 保持接口返回结构不变，只修鉴权判定路径。

### 2. 修复下载临时文件清理失效
- 修正 [backend/app/main.py](file:///home/hfy/APP/All_bot/backend/app/main.py) 中 `FileResponse(background=...)` 的写法。
- 确保临时文件生命周期和响应绑定，避免磁盘积累。
- 不改下载地址、不改响应内容、不改 MinIO 取文件逻辑。

### 3. 修正取消链路的“假取消”
- 在 [queue_manager.py](file:///home/hfy/APP/All_bot/backend/app/queue_manager.py) 和中控 API 中把“取消状态”与“执行中断能力”区分清楚。
- 第一阶段先补明确状态和日志，避免系统误报“已取消但实际还在跑”。
- 如果短期无法真正中断 ComfyUI，也至少把返回语义收敛为“已请求取消/待执行端确认”，避免错误承诺。

### 4. 修复 Dashboard 明显运行时错误
- 处理 [UserTable.vue](file:///home/hfy/APP/All_bot/dashboard/frontend/src/components/UserTable.vue) 中未定义的 `updatingIdentity`。
- 修正未导入图标 `team-outlined`。
- 这类修复属于纯正确性修复，不影响业务规则。

### 5. 修复维护页健康检查路径
- 对齐 [Maintenance.vue](file:///home/hfy/APP/All_bot/frontend/src/views/Maintenance.vue) 和 [index.ts](file:///home/hfy/APP/All_bot/frontend/src/api/index.ts) 的 baseURL 语义。
- 保证维护页探活真正打到 `/api/health` 而不是 `/api/api/health`。
- 不改页面交互，只修路径拼接错误。

### 6. 去掉 Agent 默认密钥回退
- 收紧 [agent.py](file:///home/hfy/APP/All_bot/backend/app/routers/agent.py) 的鉴权初始化。
- 配置缺失时直接 fail fast，不允许落到固定字符串。
- 这是运维安全加固，不改正常链路功能。

### P1 验收重点
- 下载、结果查询、维护页恢复、后台用户管理正常。
- 取消任务至少不再产生误导性状态。
- 中控磁盘不再堆积临时文件。
- 未配置鉴权密钥时系统明确报错而不是静默降级。

## P2

### 1. 收敛 Web API 依赖注入
- 把 [tasks.py](file:///home/hfy/APP/All_bot/src/web_api/routers/tasks.py)、[users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py)、[gallery.py](file:///home/hfy/APP/All_bot/src/web_api/routers/gallery.py) 中手写 `AsyncSessionLocal()` 和认证解析迁回统一依赖。
- 这是代码结构清理，不改路由协议、不改响应字段。

### 2. 缩小 `task_core` 职责面
- 以 [task_core.py](file:///home/hfy/APP/All_bot/src/core/task_core.py) 为中心，把“任务注册/派发”“结果监控”“补偿回滚”“历史落库”拆为更小的内部协作函数或 service。
- 先做文件内重构或模块内抽取，避免一次性跨层大改。
- 目标是降复杂度，不是重写业务。

### 3. 解耦恢复服务对 TG 表示层的反向依赖
- 收敛 [recovery_service.py](file:///home/hfy/APP/All_bot/src/services/recovery_service.py) 对 `TaskService` 私有方法的调用。
- 提炼稳定的任务恢复接口，让 Web/TG/恢复链路依赖同一服务。
- 这属于架构清理，短期不改变恢复结果。

### 4. 拆 Dashboard 根组件
- 拆分 [App.vue](file:///home/hfy/APP/All_bot/dashboard/frontend/src/App.vue) 的认证、导航、数据加载、页面容器职责。
- 先分离 composable/store/service，不必立即重构 UI。
- 保持页面结构、菜单项、接口返回都不变。

### 5. 收口前端跨页隐式状态
- 逐步减少 [Gallery.vue](file:///home/hfy/APP/All_bot/frontend/src/views/Gallery.vue) 等页面对 `sessionStorage.galleryApplyContext` 的直接依赖。
- 可以先加一层统一的状态读写封装，再考虑迁移到 store/router state。
- 先做封装，不改用户交互路径。

### 6. 补健康检查与部署门禁
- 为关键 compose 增加 healthcheck：`web-api`、`central-api`、`dashboard backend`、相关代理/静态服务。
- 收敛 [safe_deploy.sh](file:///home/hfy/APP/All_bot/safe_deploy.sh) 和 [safe_deploy_test.sh](file:///home/hfy/APP/All_bot/safe_deploy_test.sh) 对旧 `docker-compose` 和固定容器名的耦合。
- 先补等待 ready 和失败早停，不改部署拓扑。

### 7. 对齐测试/生产环境差异
- 对比 [workers/docker-compose.yml](file:///home/hfy/APP/All_bot/workers/docker-compose.yml) 与 [workers/docker-compose-test.yml](file:///home/hfy/APP/All_bot/workers/docker-compose-test.yml)。
- 优先收敛 worker 能力集、关键挂载方式、Web API 并发形态。
- 目标是“验证条件一致”，不改业务本身。

### P2 验收重点
- 对外接口、页面行为、任务结果、数据库口径不变。
- 文件复杂度下降，依赖注入与任务服务边界更清晰。
- 测试环境对生产问题的复现能力提高。
- 发布脚本失败更早暴露，不再依赖人工猜测服务是否 ready。

## 建议执行顺序
- 第 1 批：P0 全部。
- 第 2 批：P1 中“结果泄漏、临时文件清理、Dashboard 明显错误、维护页路径”。
- 第 3 批：P1 中“取消链路语义收敛、Agent 鉴权 fail fast”。
- 第 4 批：P2 的依赖注入收口、`task_core` 拆分、Dashboard 根组件拆分。
- 第 5 批：P2 的部署健康检查、测试/生产对齐。

## 最小交付形态
- 每项修复都建议带一条最小验证：
- 后端：补 1 个回归测试或断言。
- 前端：补 1 个组件/状态单测或手工验证记录。
- 部署：补 1 个脚本自检或 healthcheck 验证。
- 不建议把 P0/P1/P2 混成一个大改动；最好按批次提交，便于回归和回滚。

## 后续可继续细化
- 可进一步拆成“可执行工单版”：
- 任务项
- 影响文件
- 改动边界
- 回归点
- 风险等级
