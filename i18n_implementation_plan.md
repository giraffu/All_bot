# 修仙主题 Bot & Web 端多语言（i18n）改造方案

本文档记录了为当前系统（Telegram Bot + Vue3 Web 端）引入多语言（中/英双语）支持的架构设计与实现方案。此次改造不仅是文字翻译，更是对当前系统架构中**“文字硬编码”与“功能触发”深度耦合**的一次彻底剥离与重构。

---

## 1. 核心设计：存储与状态同步 (Single Source of Truth)

为了确保用户在 Web 端或 Bot 端切换语言后，两端状态能够互通且实时生效，语言偏好必须统一持久化。

### 1.1 数据库层与数据防污染（关键红线）
- **持久化字段**：在 `users` 表中新增 `language_code` 字段（`String(20)`，初始阶段 `nullable=True`）。
- **Alembic 平滑迁移策略**：在 `models.py` 中新增 `language_code` 字段时，**绝对不要**使用 `server_default='zh'`，否则会导致历史海外用户的原生语言被永久覆盖为中文。初始迁移必须允许 `NULL`，由代码层的 `ensure_user` 负责动态嗅探和回填。待数月后存量老用户基本回填完毕，再通过新的 Alembic 脚本将剩余的 `NULL` 刷为默认值（如 `zh`）并加上 `nullable=False` 约束。
- **⚠️ 核心红线（防污染）**：数据库 `users` 表中的 `user_group`（修为）和 `current_identity`（身份）等枚举字段，**必须永远保持原有的中文（或统一底层代号）作为系统唯一标识**。多语言翻译只能在最终的“渲染展示层”进行映射，绝对禁止将翻译后的英文存回数据库或参与任何后端业务逻辑判断，否则将导致权限与排队系统全面崩溃。

### 1.2 原生语言感知与兜底策略
- **首次交互感知**：用户首次与 Bot 交互时，读取 Telegram 原生携带的 `update.effective_user.language_code`。
- **降级机制**：系统当前仅支持中文 (`zh`) 与英文 (`en`)。若原生语言为 `zh` 系列，存入 `zh`；若是其他非中文语言，统一降级存入 `en`。
- **兜底防范**：若原生语言为 `None`，默认赋予 `zh` 或 `en`，绝对避免将 `None` 写入数据库。

### 1.3 多进程缓存与跨端同步 (Cache Invalidation)
- **引入 Redis 共享缓存**：弃用单机 `context.user_data` 缓存，将语言偏好缓存至 Redis（如 `user_lang:{user_id}`）。
- **状态下发机制**：
  - Web 端调用 `PATCH /users/preferences` 接口更新 DB 时，后端同步刷新该 Redis Key。
  - Bot 端每次处理请求时，优先执行高并发的 Redis `GET`，未命中再穿透查 DB，实现跨端状态 100% 实时同步。

---

## 2. Web 端改造方案 (Vue3)

Web 端采用行业标准的 i18n 方案，确保体验一致性。

### 2.1 核心依赖与语言包复用
- **依赖集成**：使用 `vue-i18n`。
- **前后端语言包统一**：在项目根目录（如 `shared/locales/`）统一维护一套双语 JSON 文件（`zh.json`, `en.json`）。后端启动时加载，前端构建时打包，极大降低多端维护成本。

### 2.2 状态闭环与 Truth 优先级
- **入口设计**：在“个人中心”页面提供 🌐 语言切换按钮，切换后调用 `vue-i18n` 改变前端渲染，并静默异步调用后端 API 进行持久化。
- **优先级规则**：
  - **未登录状态**：以 `localStorage` > 浏览器 `navigator.language` 为准。
  - **已登录状态**：调用 `/users/me` 成功后，**强制以后端返回的 `language_code` 为准**，直接覆盖前端缓存，真正做到以 DB 为唯一的 Single Source of Truth。

---

## 3. Telegram Bot 端架构改造与解耦 (Python/PTB)

Bot 端改造是此次重构的核心。必须彻底剥离业务逻辑层与展示层，消除正则地狱与全局状态污染。

### 3.1 独立 i18n 模块与插值渲染
- 建立 `src/i18n/` 目录，对外提供统一接口 `get_text(key, lang, **kwargs)`。
- 语言映射表**必须支持 kwargs 传参**，使用 `.format(**kwargs)` 进行动态插值。
  ```json
  { "zh": { "balance": "道友 {name}，余额 {credits}" }, "en": { "balance": "Fellow {name}, balance: {credits}" } }
  ```

### 3.2 路由机制彻底解耦 (告别正则地狱与硬编码)
当前 Bot 大量使用硬编码中文（如 `@prompt_route("🖼️ 懒人P图")` 及 FSM 中的 `MessageHandler(filters.Regex(...))`）作为路由键，翻译后将导致死锁或冗长的 OR 正则。
- **O(1) 字典反向路由**：启动时读取双语 JSON，构建全局扁平字典 `GLOBAL_REVERSE_MAP`（如 `{"🖼️ 懒人P图": "menu.photo_edit", "🖼️ AI Edit": "menu.photo_edit"}`）。
- **标识符重构**：将所有路由装饰器重构为语言无关的唯一标识符（如 `@prompt_route("menu.photo_edit")`）。
- **极速分发**：在 `handle_prompt` 入口处，收到文本后直接执行 `i18n_key = GLOBAL_REVERSE_MAP.get(text)`，实现 O(1) 精确匹配。
- **FSM 入口正则剥离与严格 O(1) 字典匹配 (I18nRouteFilter)**：不再支持自然语言交互的模糊匹配。无论是主菜单还是 FSM 入口（如 `quick_image_fsm.py`），用户交互统一依赖点击按钮触发的精确文本。在系统启动时，基于双语 JSON 提取所有可能作为按钮的文本构建 `GLOBAL_REVERSE_MAP`，实现全盘 O(1) 精确匹配。FSM 内部再通过 `i18n_key` 判断对应的 `MODE`，实现即使未来新增语种，FSM 内部业务逻辑代码也无需修改。
- **内联回调边界**：CallbackData 的 pattern（如 `set_res_512p`）**必须保持纯英文缩写**，绝不参与翻译。
- **⚠️ 路由红线（ReplyKeyboardMarkup 静态化约束）**：为了保证 O(1) 精确匹配的绝对可靠，作为路由入口的底部键盘（ReplyKeyboardMarkup）按钮文本，**绝对不允许包含任何动态变量插值**（如 `(剩余 {count} 次)`）。如果需要展示动态信息，必须放在上方回复的 Message Text 中，或者改用不受文本翻译影响的内联键盘（InlineKeyboardMarkup）。

### 3.3 业务核心层的极限剥离 (Service 层纯粹化与跨端复用)
当前 `permission_service.py` 存在严重越权，方法签名中透传了 `bot` 和 `chat_id`，并包含了大量 `robust_send_message` 的硬编码下发逻辑，导致鉴权逻辑与展示层严重耦合。
- **定义领域异常基类 (Domain Exceptions)**：彻底移除服务层中的 `bot`, `chat_id` 与推送逻辑。当权限或额度校验失败时，仅抛出携带数据的领域异常。例如：
  ```python
  class InsufficientCreditsError(Exception):
      def __init__(self, current, cost):
          self.current = current
          self.cost = cost
  ```
- **统一下沉拦截与动态渲染 (Bot端)**：在外层（Handler 层）封装 `@with_unified_error_handler` 统一拦截这些异常，实时读取用户语言偏好，调用 `get_text("error.insufficient_credits", lang, current=e.current, cost=e.cost)` 获取翻译，并由拦截器统一调用 `robust_send_message` 下发。
- **Web 端全局异常处理 (FastAPI端)**：在 FastAPI 层（如 `src/web_api/main.py`）同样注册全局的 Exception Handler，将抛出的领域异常统一捕获，并转化为带标准错误码的 JSON 响应（如 `HTTP 402 Payment Required` 或业务自定义的 `code: 4001`）。这样才真正实现了后端核心业务逻辑在 Bot 和 Web 端的 100% 跨端无缝复用。
- **跨用户异步通知解耦与语言隔离**：移除服务层直接向邀请人推送奖励的逻辑。对于类似邀请人奖励推送这类跨用户通知，无需引入重量级的 Event Bus，只需在鉴权通过后的外层 Handler 中调用 `create_background_task(context, notify_inviter_task(inviter_id, reward))`。**极其重要**：在 `notify_inviter_task` 内部，绝对不能使用当前触发者（被邀请人）的 `context.lang`，必须显式地去 DB/Redis 查询 `inviter_id`（邀请人）的语言偏好，再进行翻译下发，防止出现“中国邀请人收到英文到账通知”的上下文污染。

### 3.4 动态渲染与状态上下文传递
- **静态常量工厂化防污染**：彻底废弃 `src/constants.py` 中包含展示文本的全局静态变量（如 `MAIN_MENU_KEYBOARD` 等列表常量）。将其全部重构为带 `lang` 参数的动态工厂函数（如 `def get_main_menu(lang: str)`）。在回复消息时实时调用，防止全局状态被某一种语言污染，确保键盘底层刷新的永远是最新的语言结构。
- **避免无意义持久化的状态挂载**：PTB 的 `user_data` 用于跨请求持久化，在高频交互中每次写入都会触发无意义的 IO。建议通过继承 PTB 的 `CallbackContext` 实现 `CustomContext`，在拦截器中从 Redis 拉取 `lang` 后，将其作为瞬时内存属性挂载（如 `context.lang`），彻底避开持久化机制引发的性能隐患。
- **异步任务工作流的全链路语言透传**：在 `task_service.py` 等后台生成任务中，不仅主入口函数需要透传 `lang` 参数，**所有相关的私有辅助方法（如 `_get_acceleration_notice`）也必须同步透传 `lang`**，避免出现“主干是英文，后缀提示是中文”的割裂现象。底层直接使用透传的 `lang` 进行状态通知的多语言渲染。

### 3.5 UI 交互流程
- **入口位置**：将语言切换放入“👤 个人中心”的内联键盘（InlineKeyboardMarkup）中，避免占用主菜单空间。
- **交互流**：用户点击切换后，更新 DB 与 Redis，Bot 回复提示并携带重新生成的 `ReplyKeyboardMarkup`，以刷新底部的键盘结构。
- **PTB API 刷新陷阱 (⚠️ 极易踩坑)**：因为触发语言切换的是内联键盘 (CallbackQuery)，开发者习惯使用 `await query.edit_message_text(...)`。但 Telegram API **严格禁止**在 `edit_message_text` 中挂载 `ReplyKeyboardMarkup`（会报错 `BadRequest: reply markup is invalid`）。**必须要求**：收到语言切换指令后，使用 `await context.bot.send_message(...)` 发送一条新的文本消息，以刷新底部的按键菜单。

### 3.6 原生命令菜单的多语言化 (Native Commands)
- **独立注册机制**：当前 `set_my_commands` 硬编码了中文菜单。必须在 Bot 启动时（如 `bot_test.py` 的 `post_init` 钩子中），利用 Telegram API 原生支持的 `language_code` 参数，为支持的每种语言分别注册一次命令。
- **实现规范**：调用 `await app.bot.set_my_commands(commands_zh, language_code='zh')` 和 `commands_en`，这样用户的 Telegram 客户端会根据其原生语言自动显示对应的菜单提示，实现 100% 的 Native i18n 体验。

---

## 4. 部署与落地补充

- **Alembic 数据库迁移**：
  在 `src/database/models.py` 中新增 `language_code` 字段后，必须生成并执行迁移脚本（`alembic upgrade head`）。测试与正式环境共用 DB 时仅需执行一次。
- **历史存量用户数据平滑过渡 (Data Patch)**：
  必须在代码逻辑层 (`permission_service.ensure_user`) 增加动态感知逻辑：当老用户触发交互且 DB 中 `language_code` 为空（`None`）时，实时读取其 Telegram 原生语言 (`update.effective_user.language_code`)，降级写入 `zh` 或 `en`。这种“懒加载”回填策略能最大程度保护老用户的多语言体验。

---

## 5. 架构进阶优化点 (基于实际代码的深度解耦)

基于对当前代码（如 `message_handler.py`, `permission_service.py`, `quick_image_fsm.py` 等）的现状分析，方案可进一步做如下极限优化：

### 5.1 FSM 防死锁与全局路由的 O(1) 极限解耦
- **废弃巨型正则匹配**：当前 `prompt_router.py` 拼接的 `GLOBAL_MENU_FILTER` 巨型正则可被彻底废弃。`is_global_menu_command(text)` 直接简化为 `return text in GLOBAL_REVERSE_MAP`，性能从 O(N) 提升至 O(1)，且免疫新增语言导致的正则爆炸。
- **真正的 O(1) 路由落地**：在 `handle_prompt` 入口，先执行 `i18n_key = GLOBAL_REVERSE_MAP.get(text)`，接着直接执行 `handler_func = prompt_routes.get(i18n_key)` 实现真正的 O(1) 派发。只有当 `i18n_key` 为空时，才 fallback 到 `is_regex=True` 的遍历匹配（作为兜底）。
- **FSM 防死锁的多语言闭环 (`unexpected_input`)**：在 FSM（如 `quick_image_fsm.py`）中，防死锁逻辑强依赖 `is_global_menu_command(text)` 来拦截误触的菜单点击并释放锁。在落地时，只需确保中英双语的所有菜单按钮文本都注册进了 `GLOBAL_REVERSE_MAP`，即可让防死锁逻辑在多语言环境下实现 O(1) 的自动闭环。
- **FSM 内部逻辑彻底剥离输入文本**：在状态机中（如 `quick_image_fsm.py`），废弃按中文文本查找 Mode 的逻辑。由于不再需要支持部分匹配，入口拦截后，Handler 内部直接根据输入的文本通过字典查询出 `i18n_key`（如 `menu.quick_undress`），FSM 内部仅通过内部字典映射决策（如 `{"menu.quick_undress": MODE_UNDRESS}`），彻底与外部输入绝缘。

### 5.2 Service 层的纯粹化与事件驱动 (Event Bus)
- **方法签名的极限净化**：在重构 `permission_service.py` 时，**彻底删除**所有方法中的 `bot` 和 `chat_id` 参数，使其成为纯粹的后端领域服务。
- **跨用户推送与上下文解耦**：当前 `permission_service.py` 中的 `check_channel_reward` 在鉴权通过时会同步调用 `robust_send_message` 给邀请人发奖励。由于此时是“新用户”触发的动作，当前请求上下文中无法直接拿到“邀请人”的语言偏好 `lang`。
- **轻量级异步通知解耦**：必须移除服务层直接推送消息的底层代码，抛出带有期望动作标识的领域异常或返回成功标志。对于类似邀请人奖励推送这类跨用户通知，无需引入重量级的 Event Bus，只需在鉴权通过后的外层 Handler 中调用 `create_background_task(context, notify_inviter_task(inviter_id, reward))`，在 `notify_inviter_task` 中单独查一次邀请人的 `lang` 并下发，既实现解耦，又保持了改造成本最低。

### 5.3 静态菜单与常量的全面工厂化
- **局部字典与内联键盘重构**：除了主菜单，文件中所有的局部包含文本的字典（如 `message_handler.py` 中的 `TASK_TYPE_DISPLAY_NAMES`）和内联键盘（`InlineKeyboardMarkup`）绝不能在模块加载时实例化为全局静态变量。必须全部包装为 `get_xxx(lang: str)` 动态求值函数，防止广播消息或共享状态被单一语言污染。
- **现有函数的改造成本极低**：实际代码中（如 `constants.py` 的 `get_video_settings_keyboard`）已经实现了局部键盘函数化。只需在其签名中增加 `lang: str` 参数，并将硬编码的拼接文本（如 `f"{res} ({cost}灵石)"`）替换为 `get_text("video.resolution_cost", lang, res=res, cost=cost)` 即可。

### 5.4 Web 端 DTO 数据边界防踩坑 (极致解耦)
- **严重“破窗”纠正 (`user_facade.py`)**：审查发现 `UserDashboardDTO` 中包含了高度格式化的中文展示字段（如带 ✅/❌ 的 `breakthrough_msg` 和带过期时间的 `identity_display`）。**必须彻底重构 `user_facade.py`**，直接从 DTO 中彻底删除 `breakthrough_msg` 和 `identity_display` 这类仅用于视图渲染的字段。
- **突破条件与时间计算的结构化下沉**：为了让 Vue3 前端能渲染复杂的进度状态，后端仅返回原始数值与时间戳。例如返回结构化的条件数组 `breakthrough_conditions: [{ type: 'invite', target: 1, current: 2, done: true }]`，以及 ISO 8601 格式的时间戳（如 `identity_expire_at: "2024-12-31T23:59:59Z"`）。前端接收后利用 `v-for`、`dayjs` 和 `vue-i18n` 自行计算剩余时间、拼装进度条与渲染多语言文案，真正做到“后端只传数据，前端负责渲染”。
- **DTO 纯粹性红线**：后端 API（如 `/users/me`）返回给 Vue3 Web 端的 DTO 必须保留原始的中文枚举值或统一定义的内部代号（如 `user_group: "练气期"`），绝对不要在后端接口层进行翻译。前端接收后统一通过 `vue-i18n` 的 `$t(user.group)` 进行渲染，严格遵循 Single Source of Truth。

### 5.5 依赖注入与序列化防坑 (Middleware 优化)
- **拒绝 Lambda 闭包注入 `user_data`**：由于 `context.user_data` 在未来可能接入 DB/Redis 持久化，且日志打印可能抛出异常，**绝对不要**在其中注入不可序列化的对象（如 `lambda key...` 翻译函数）。
- **多语言函数调用的语法糖增强 (CustomContext)**：如前所述，摒弃对 `user_data` 的依赖。在自定义的 `CustomContext` 初始化或拦截器中，将无状态的翻译闭包直接挂载到 context 实例本身上（如 `context.t = I18nTranslator(lang)`）。在后续 Handler 中只需清爽地调用 `context.t('error.insufficient_credits')`，既保证了状态序列化的安全，避免了持久化引发的 IO 开销，又极大提升了开发体验。

### 5.6 FastAPI 全局校验异常的拦截与多语言化 (Web API)
- **Pydantic 校验割裂隐患**：当前 FastAPI 依赖 Pydantic 进行请求体验证，如果前端提交的字段不合法，FastAPI 会抛出 `RequestValidationError`，默认返回纯英文的报错信息（如 `field required`）。这会严重破坏 Web 端中文用户的体验。
- **统一异常接管**：在 `src/web_api/main.py` 中，除了捕获领域异常，**必须**覆盖默认的 `RequestValidationError` 处理器。将其转化为统一的业务错误码（如 `code: 4220`），交由 Vue 前端拦截并使用 `vue-i18n` 渲染出多语言的“参数校验失败”提示。

## 6. 具体落地的防坑与安全建议 (Technical Gotchas)

在将上述架构方案落地到 Python 和 PTB (python-telegram-bot) 代码时，必须注意以下几个关键的安全细节：

### 6.1 PTB 过滤器的状态挂载陷阱 (无状态 Filter)
- **隐患**：在自定义 `I18nRouteFilter.filter()` 中修改 `update` 或 `context` 状态极易在并发或过滤器链短路时引发副作用，**绝对不要在 Filter 中挂载状态**。
- **规范**：过滤器只做极简的匹配判断。真正的映射逻辑放在 Handler 内部第一行：
  ```python
  # I18nRouteFilter 仅返回 bool
  def filter(self, message):
      return GLOBAL_REVERSE_MAP.get(message.text) in self.expected_keys
  
  # Handler 内部安全获取
  async def start_fsm(update, context):
      i18n_key = GLOBAL_REVERSE_MAP.get(update.message.text)
      mode = MODE_MAP.get(i18n_key)
  ```

### 6.2 翻译插值 (.format) 的线上容灾安全
- **隐患**：若 `en.json` 漏写占位符，或传错了 kwargs，直接调用 `.format(**kwargs)` 会触发 `KeyError` 导致 Bot 抛出 500 异常中断流程。
- **规范**：在 `get_text` 底层实现时，使用安全的字典包装类（SafeDict）进行降级渲染，确保翻译缺失不会阻断业务：
  ```python
  class SafeDict(dict):
      def __missing__(self, key):
          return '{' + key + '}'
  # text.format_map(SafeDict(**kwargs))
  ```

### 6.3 异步任务通知的上下文隔离 (Event Bus Context)
- **隐患**：在 Bot 进程上下文中，并没有 FastAPI 的 `BackgroundTasks` 可用。同时，跨用户触发异步任务时，直接复用当前 `context` 会导致严重的“语言污染”。
- **规范**：对于 Bot 侧发起的跨用户通知（如邀请奖励推送），应统一调用代码库已有的 `src.utils.create_background_task(context, coro)` 进行异步派发。在异步任务 `coro` 的内部，**必须重新查询目标用户的 `language_code`**，绝不允许直接透传或使用发起者的 `lang` 状态。

### 6.4 Alembic 部署执行环境的“坑”
- **隐患**：生产环境 `tg-bot` 容器通常不会映射本地 `src` 目录，如果在旧容器内执行迁移将找不到新脚本。
- **规范**：Alembic 数据库迁移命令（`alembic upgrade head`）**必须在宿主机上执行**，或者在执行 `docker-compose up -d --build` 重建容器挂载最新代码后，再进入容器执行。

### 6.5 前端 (Vue3) 类型的极致安全 (Type Safety)
- **规范**：利用 TypeScript 的类型检查机制，在构建阶段通过 `vue-tsc` 或相关 i18n 插件，将 `zh.json` 中的 Key 自动提取为 TS 联合类型 (Union Types)。这样前端在调用 `$t('menu.photo_edit')` 时若出现拼写错误，IDE 将直接红线报错，杜绝多语言漏配。

### 6.6 Service 层异常的 UI 降级表现力 (Action Intent)
- **隐患**：剥离 `permission_service.py` 抛出 `InsufficientCreditsError` 后，原先代码中附带的 `[💎 充值灵石]` 内联键盘引导可能丢失，导致用户体验降级。
- **规范**：领域异常除了携带 `cost` 和 `current` 等数值，还应携带一个 **期望动作标识 (Action Intent)**。外层的 `@with_unified_error_handler` 统一拦截器在捕获异常时，根据 `lang` 与 Intent 动态渲染带有多语言翻译的 `InlineKeyboardMarkup`，确保体验不降级。

### 6.7 动态权重与排队系统的绝对纯净性
- **隐患**：`constants.py` 中的 `DYNAMIC_PRIORITY_RULES` 强依赖如“真传弟子”等中文枚举计算排队权重。
- **规范**：无论展现层如何翻译（如 Core Disciple），在传入 `task_service.py` 或计算 Redis 并发锁时，**必须且只能读取 DB 原始的中文枚举值**。所有多语言 `get_text` 渲染必须严格压后到下发给用户（`send_message`）的最后一刻。

### 6.8 异步后台任务的全链路语言参数必传防线
- **隐患**：`task_service.py` 在被异步调用时，如果外层 Handler 忘记透传 `lang` 参数，或其内部的私有辅助方法（如 `_get_acceleration_notice` 等特权提示）未接收 `lang` 参数，将导致后续通知文案翻译失败、抛出异常或出现双语混杂的割裂体验。
- **规范**：在 `TaskService` 等异步任务服务的所有函数签名（**包括内部私有辅助方法**）中，必须强制增加 `lang: str = "zh"` 的带有兜底默认值的参数，确保全链路的语言上下文不丢失，并稳健回退到默认语言完成最终下发。

---

## 7. 涉及模块与分步实施计划 (Implementation Steps)

本次多语言改造是对全栈架构的一次深度解耦，主要涉及以下核心服务模块的更新：

1. **数据层 (Database & Config)**
   - `src/database/models.py`：新增 `language_code` 字段。
   - `src/constants.py`：废弃静态全局键盘和文本常量，改为带 `lang` 参数的工厂函数。
   - `shared/locales/`（新增）：存放双语 JSON 字典，供前后端共同读取。
2. **核心业务服务 (Service & Facade)**
   - `src/services/permission_service.py`：剥离表现层代码，彻底移除 `bot`, `chat_id` 和推送逻辑，改为抛出带数据的领域级异常（Domain Exceptions）。
   - `src/core/user_facade.py`：重构 DTO，移除 `breakthrough_msg` 等硬编码的展示文本，下沉为纯粹的结构化数据（如时间戳、进度数组）。
3. **Bot 路由与底层框架 (Handlers)**
   - `src/handlers/prompt_router.py`：废弃巨型正则匹配，启动时预编译 JSON，实现 O(1) 字典反向路由 (`GLOBAL_REVERSE_MAP`)。
   - `src/handlers/command_handler.py`（或 `bot_test.py`）：为不同语种注册原生的 Telegram 命令菜单 (`set_my_commands`)。
4. **Bot 业务场景与异步任务 (FSM & Task)**
   - `src/handlers/fsm/quick_image_fsm.py` 及其他 FSM：剥离入口正则，内部判定彻底改用英文标识符，完善多语言下的防死锁逻辑。
   - `src/services/task_service.py`：在所有函数签名中透传 `lang` 参数，确保跨用户通知（如邀请奖励）时，独立查询并使用目标用户的语言偏好。
5. **Web 端 (API & Vue3)**
   - `src/web_api/main.py`：接管 FastAPI 全局异常与 Pydantic 校验异常，统一返回 JSON 错误码供前端翻译。
   - `Vue3 Dashboard`：接入 `vue-i18n`，依据纯净的 DTO 重新编写进度条、身份倒计时等动态渲染组件。

### 分步实施建议（平滑过渡路径）

为了保证线上业务的稳定性，强烈建议按照以下 **5 个阶段** 渐进式实施：

#### 阶段一：基础设施与数据层准备（基建期）
- **DB 改造**：在 `models.py` 中新增 `language_code`（允许 `NULL`），生成 Alembic 迁移脚本并在生产环境执行。
- **i18n 模块初始化**：建立 `src/i18n/` 核心解析工具（如 `get_text`，支持 SafeDict 降级），并维护 `zh.json` 和 `en.json`。
- **用户态感知**：修改 `ensure_user` 等核心鉴权逻辑，在用户交互时动态捕获 Telegram 原生语言并存入 DB 与 Redis 缓存。

#### 阶段二：核心业务层“去表现化”解耦（核心期）
- **领域异常重构**：新建 `src/core/exceptions.py`，定义 `InsufficientCreditsError` 等业务异常。
- **Service 瘦身**：重构 `permission_service.py`，将所有业务拦截改为抛出异常。
- **DTO 净化**：重构 `user_facade.py` 中的 `UserDashboardDTO`，移除所有格式化的中文文本。

#### 阶段三：Web 端多语言闭环（前后端联合发布期）
- **API 异常接管**：在 FastAPI 中注册全局异常拦截器，统一返回标准 JSON 错误码。
- **前端重构**：Vue3 引入 `vue-i18n`，依据新版 DTO 渲染界面。
- **⚠️ 核心红线**：由于 DTO 发生了 Breaking Change，**必须确保后端 API 与 Vue3 前端在同一时刻同步上线**，否则会导致前端页面白屏崩溃。

#### 阶段四：Bot 底层路由与中间件重构（框架期）
- **全局中间件**：利用 `TypeHandler` 作为全局前置中间件，将当前用户的 `lang` 挂载到 `context.lang`，并注入 `context.t` 翻译闭包。
- **O(1) 路由替换**：重构 `prompt_router.py`，将所有的 `@prompt_route` 替换为语言无关的标识符，启用 `GLOBAL_REVERSE_MAP`。
- **静态键盘工厂化**：将 `constants.py` 中的硬编码键盘重构为 `get_xxx_keyboard(lang)` 动态工厂。

#### 阶段五：Bot 业务场景全覆盖与验收（业务期）
- **FSM 与任务下发**：改造所有状态机与 `task_service.py`，确保提示文本均通过 `context.t` 渲染。针对异步跨用户通知，确保重新查询目标用户语言。
- **原生菜单注入**：调用 `set_my_commands` 注入多语言原生命令菜单。
- **回归验收**：重点测试老用户点击历史中文菜单是否正常进入 FSM，余额不足是否能弹出带有预期动作意图的多语言键盘。

---

**结论**：本方案以**“DB统一存储 + Web/Bot共享语言包 + 架构极致解耦”**为核心。通过 O(1) 反向路由、Service 层纯粹化抛出异常、静态菜单工厂化以及稳健的 Redis 缓存，不仅实现了多端体验一致的多语言支持，更扫清了历史代码中高耦合的架构技术债。