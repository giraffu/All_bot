# 修仙主题 Bot 多语言（i18n）后续改造方案 (阶段四与阶段五)

本文档基于当前代码库的最新状态（已完成数据层、Web 端 DTO、及服务层领域异常的拦截改造），梳理了 Telegram Bot 端多语言（i18n）彻底解耦与落地的详细方案。

---

## 1. 当前现状剖析 (Status Analysis)

### 1.1 已完成的基建 (Phase 1-3)
- **数据库与缓存**：`users` 表已增加 `language_code` 字段，且 `ensure_user` 已实现将其同步至 Redis 缓存（`allbot:user_lang:{user_id}`）。
- **翻译引擎**：`src/i18n/translator.py` 已就绪，提供安全的 `get_text` 和 `I18nTranslator` 类，支持 `SafeDict` 降级防崩溃。
- **领域异常解耦**：Service 层已剥离硬编码推送，改抛 `InsufficientCreditsError` 和 `AccessDeniedError`。`error_handlers.py` 已实现全局拦截并接入翻译引擎下发多语言提示。
- **Web端解耦**：FastAPI 接口 DTO 已剥离中文格式化字段，由 Vue3 前端接管多语言渲染。

### 1.2 亟待解决的技术债
- **路由正则地狱**：`prompt_router.py` 仍在使用硬编码的中文数组拼接巨型正则 `GLOBAL_MENU_FILTER`。
- **静态状态污染**：`constants.py` 中的 `MAIN_MENU_KEYBOARD` 等仍是全局静态变量，切换语言会导致全局键盘被污染。
- **上下文获取冗余**：各个 Handler 散落着 `context.user_data.get('language_code', 'zh')`，缺乏优雅的中间件统一注入。
- **跨用户推送污染**：异步任务（如 `notify_inviter_reward`）未进行目标用户的语言隔离。

---

## 2. 阶段四：Bot 核心路由与中间件解耦 (Phase 4)

本阶段目标是彻底消除 Bot 底层框架对中文文本的依赖，实现极速的 O(1) 路由。

### 2.1 全局语言上下文注入 (TypeHandler Middleware)
- **中间件扩展**：在 `bot_test.py` 的前置 `TypeHandler` 中（如现有的 `inject_trace_id` 旁），增加语言上下文的拦截与挂载。
- **Redis 缓存键双写策略 (Critical)**：目前 `src/services/permission_service.py` 中的 `ensure_user` 写入 Redis 的是基于内部 ID 的 `allbot:user_lang:{internal_user.id}`，但前置 `TypeHandler` 只能获取到 TG ID (`update.effective_user.id`)，这会导致严重 Cache Miss。**必须**在 `ensure_user` 中采用**双写**策略（同时写入内部 ID 键和 TG ID 键 `allbot:user_lang:tg:{tg_id}`），以兼顾 WebAPI/后台任务的内部调用与 Bot 侧的 O(1) 极速读取。**注意**：一旦用户在未来触发了类似 `/setlang` 的语言切换功能，必须同时更新这两个 Redis Key，否则会导致 Web 端与 Bot 端的语言状态严重割裂。
- **安全挂载与兜底**：从 `context.user_data` 或 Redis (`allbot:user_lang:tg:{tg_id}`) 获取当前用户的 `language_code`。若均为空（如新用户未执行 `/start` 直接点历史按钮），则兜底使用原生 `update.effective_user.language_code`。**注意：** 原生语言代码可能包含地区后缀（如 `zh-hans`），必须截取前两位并进行白名单过滤（`['zh', 'en']`），否则兜底为 `zh`。处理后将其直接作为瞬时属性挂载到 `context` 实例上（即 `context.lang = lang`）。
- **注入翻译闭包 (亮点设计)**：实例化 `context.t = I18nTranslator(lang)`。后续所有 Handler 只需调用 `context.t("key")`。该对象挂载到生命周期仅限于当前 Update 的 `context` 实例上，不仅全链路随取随用，更彻底避免了未来引入 Persistence 时因 `I18nTranslator` 对象引发的 Pickle 序列化崩溃。

### 2.2 真正的 O(1) 字典反向路由 (`GLOBAL_REVERSE_MAP`)
- **标识符重构**：将 `@prompt_route` 绑定的中文替换为纯英文标识符（例如 `@prompt_route("menu.photo_edit")`）。
- **指令与文本路由彻底剥离 (Critical)**：绝不能将原生命令（如 `/queue`, `/checkin`）或带有前缀命令的回退数组（如 `additional_menus`）与文本按钮混在一起塞入正则或字典！`GLOBAL_REVERSE_MAP` 应纯粹只处理**键盘按钮文本**。对于命令，直接在 `bot_test.py` 中统一使用 `CommandHandler("queue", handle_queue_status)` 等方式显式注册。
- **字典预编译与全语种支持**：在系统启动时（`build_global_menu_filter` 中），调用 `load_locales()` 读取所有语种（`zh`, `en` 等）的 JSON 字典。
- **反向映射安全构建**：不要遍历深层 JSON 字典去“猜”菜单。系统启动时，直接遍历代码中已注册的 `prompt_routes.keys()`（重构后即 `menu.xxx`）以及 `additional_menus`（需提前赋予对应的 `i18n_key` 如 `"menu.back_main"`），分别查询所有语种的翻译结果，将其作为键反向存入字典，构建全局扁平反向字典 `GLOBAL_REVERSE_MAP`。这样即使英文用户在流程内点击了英文菜单，也能实现 O(1) 拦截。
  *(示例: `{"🖼️ 懒人P图": "menu.photo_edit", "🖼️ AI Edit": "menu.photo_edit"}`)*
- **构建时序依赖 (Initialization Order)**：在系统启动构建 `GLOBAL_REVERSE_MAP` 之前，必须确保所有 `@prompt_route` 装饰器已被执行。注意 Python 的 `import` 顺序，确保 `src/handlers/message_handler.py` 等文件在预编译字典前已被加载，否则会导致反向字典为空。
- **极速拦截器**：废弃巨型正则表达式，将 `is_global_menu_command(text)` 改写为 `return text in GLOBAL_REVERSE_MAP`。
- **重构 handle_prompt (关键)**：在 `message_handler.py` 中，彻底废弃对 `prompt_routes` 的遍历匹配逻辑。改为 `route_key = GLOBAL_REVERSE_MAP.get(text)`，若匹配则直接执行 `prompt_routes[route_key]`，实现 O(1) 触发，解决菜单按钮点击失效的致命问题。

### 2.3 静态菜单与常量的工厂化 (Constants Factory)
- **废弃静态变量**：彻底删除 `constants.py` 中的 `MAIN_MENU_KEYBOARD` 等包含展示文本的全局静态变量。
- **动态工厂与缓存优化**：重构为带语言参数的工厂函数，如 `get_main_menu_keyboard(lang: str)`，内部调用 `get_text` 实时拼装并返回 `ReplyKeyboardMarkup`。**优化建议**：Telegram 的 `ReplyKeyboardMarkup` 对象在同一语种下是无状态的，建议引入 `@lru_cache(maxsize=10)` 缓存该函数结果，避免每次 Update 产生不必要的内存分配开销。
- **深层枚举清理**：对于 `TASK_TYPE_DISPLAY_NAMES` 和 `MODE_NAME_MAP` 这样强耦合了中文图标的深层枚举，不建议包装为工厂函数，而是**直接将其值全部替换为对应的 `i18n_key`**（如 `"img2img": "task.type.img2img"`）。在展示排队状态等业务逻辑中，组装前再通过 `context.t(TASK_TYPE_DISPLAY_NAMES[type])` 动态翻译即可。另外，`get_video_settings_keyboard` 中硬编码的境界名（如 `"外门弟子"`）也不能返回中文，应做类似处理。
- **内联键盘改造**：修改已有的 `get_video_settings_keyboard` 等函数，加入 `lang` 参数，将 `f"{res} ({cost}灵石)"` 替换为多语言插值翻译。

---

## 3. 阶段五：业务场景全链路多语言化 (Phase 5)

本阶段聚焦于具体业务逻辑的替换与边缘场景的隔离。

### 3.1 FSM 状态机防死锁与入口解耦
- **无状态过滤器 (PTB 最佳实践)**：编写 `I18nFilter(i18n_keys)`，直接继承自 PTB 的 `telegram.ext.filters.MessageFilter`。支持传入单键或多键列表（`List[str]`）。**优化建议**：在初始化时将 `i18n_keys` 转为 Set 以实现 O(1) 查询。在 `filter` 方法中必须增加防御性判断 `if not message.text: return False`（防止纯图片等无文本消息引发异常），随后返回 `GLOBAL_REVERSE_MAP.get(message.text) in self.i18n_keys`。
- **替换正则入口**：将所有状态机（如 `quick_image_fsm.py`、`faceswap_fsm.py`）的 `entry_points` 从硬编码的正则匹配替换为 `MessageHandler(I18nFilter("menu.photo_edit"), callback)`。
- **防死锁闭环与字典构建关联**：在 FSM 内部的 `unexpected_input` 防死锁拦截中，依赖更新后的 `is_global_menu_command` 实现双语兼容的自动放行。这要求 `GLOBAL_REVERSE_MAP` 构建时必须**同时将所有支持语种（如中、英）的翻译结果作为键反向存入**，这样无论是英文还是中文界面的用户，在流程内误触了全局菜单按钮，都能实现 O(1) 拦截与平滑退出。**注意**：退出 FSM 时保持当前的“二次点击”体验，但引导文案（如“已为您退出...请再次点击”）也必须提取到多语言 JSON 中，并用 `context.t` 翻译输出。
- **原生命令拦截与“幽灵死锁”规避 (Critical)**：由于 Phase 4 将 `/queue`, `/checkin` 等指令剥离出全局路由，FSM 现有的 `~filters.COMMAND` 兜底拦截器会放行这些指令。这会导致用户在 FSM 流程内点击指令菜单时触发全局 Handler，但 FSM 无法退出，形成“幽灵死锁”。**解决方案**：将 FSM 的兜底 Filter 修改为 `MessageHandler((filters.TEXT | filters.COMMAND) & ~filters.Regex(r'^/cancel$'), unexpected_input)`，并在 `is_global_menu_command` 判断逻辑中额外放行这些被抽离的全局命令，确保 FSM 安全退出。

### 3.2 跨用户通知的绝对语言隔离 (Critical)
- **隐患**：当前 `command_handler.py` 触发邀请奖励时调用的 `notify_inviter_reward` 未隔离上下文。
- **重构要求**：除了 `notify_inviter_reward`，需全局搜索 `robust_send_message`。凡是目标 `chat_id != current_user_id`（如发给管理员、受邀者或群组广播）的地方，**绝对不能使用当前上下文的语言**。
- **实现方案 (优化)**：无需额外查 Redis 获取语言。在 `src/utils.py` 的 `notify_inviter_reward` 内部，已有一行 `session.execute(select(User)...)` 查出了目标用户对象。因为这是后台异步任务，没有复杂的生命周期，**无需显式实例化 `I18nTranslator`，直接调用底层的 `get_text("key", lang=inviter.language_code, **kwargs)` 静态方法即可**，既省去一次网络 IO，又使代码高内聚且更轻量。

### 3.3 业务 Handler 文本大替换
- **全面排查**：梳理 `command_handler.py`、`message_handler.py` 及各个 FSM。
- **文本提取**：将 `update.message.reply_text("中文...")` 统一替换为 `update.message.reply_text(context.t("key"))`。
- **词典同步**：将提取出的中文文案及英文翻译同步写入 `shared/locales/zh.json` 和 `en.json`。

### 3.4 原生 Telegram 菜单注册 (`set_my_commands`)
- **多语言菜单注入**：修改 `src/handlers/command_handler.py` 中的 `setup_commands`（该方法在 `bot_test.py` 的 `post_init` 阶段被调用），利用 Telegram API 原生支持的 `language_code` 参数进行多次注册：
  ```python
  await app.bot.set_my_commands(commands_zh, language_code='zh')
  await app.bot.set_my_commands(commands_en, language_code='en')
  await app.bot.set_my_commands(commands_en) # 兜底默认
  ```

### 3.5 Markdown 转义防崩溃陷阱 (Edge Case)
- **隐患**：由于 Bot 大量使用 `parse_mode="Markdown"`（V1），它对 `_` 和 `*` 等保留字符极其敏感。当把带有外部变量（如 `name`）的文本抽离到 JSON 并用 `SafeDict` 格式化时，如果输入包含保留字符，直接替换会导致 Telegram 抛出 `Can't parse entities` 异常。如果在底层 `get_text` 对整个长字符串进行 `escape_markdown`，又会破坏 JSON 中原本写好的样式（如 `**加粗**` 会被转义）。
- **实现方案 (选择性转义与局部转义)**：**绝对不要**在底层的 `get_text` 中强制对整个文本转义，否则会导致内联键盘（`InlineKeyboardButton`）等非 Markdown 场景出现丑陋的 `\_` 和 `\*`。在 `translator.py` 中引入 `from telegram.helpers import escape_markdown`，修改 `I18nTranslator.__call__` 增加 `escape_md: bool = False` 参数。当 `escape_md=True` 时，**仅对传入的 `kwargs` 变量的值进行转义**，然后再传入 `SafeDict` 执行 `format_map`。**注意：** `kwargs` 传入的变量可能是数字（如 `reward=10`），在执行 `escape_markdown` 前务必强制转换为字符串并显式指定版本（`escape_markdown(str(v), version=1)`），避免引发 `TypeError` 或转义逻辑错乱崩溃。这样既能保证用户输入的特殊字符不报错，又能完美保留翻译文本预设的 Markdown 结构。

---

## 4. 实施顺序建议 (渐进式重构路径)

强烈建议**分阶段独立部署**，以控制爆炸半径并保证测试环境的持续可用：

### 🟢 第一步：阶段四代码改动（底层基建替换）
1. **TypeHandler 注入与 Redis 双写**：实现中间件挂载 `context.t`，兼顾 Web 端与 Bot 端的语言状态一致性。
2. **O(1) 路由引擎重构**：构建 `GLOBAL_REVERSE_MAP`，重写 `handle_prompt` 与 `is_global_menu_command`，实现双语向下兼容拦截。
3. **工厂化 Constants**：消除静态键盘与深层枚举，引入 `@lru_cache` 优化性能。
4. **【关键前置补丁】修复 FSM 原生命令漏拦**：由于步骤 2 剥离了 `/queue` 等命令，必须在此阶段同步修改所有 FSM 的兜底 Filter（改为 `(filters.TEXT | filters.COMMAND) & ~filters.Regex(r'^/cancel$')`），防止幽灵死锁。

### 🚀 第二步：阶段四独立部署与验证
- **操作**：此时即可**重建更新 Bot 服务**。
- **验证点**：因为路由字典实现了对现有中文的向下兼容，新服务上线后，老用户的点击应全部正常响应。重点测试 FSM 流程中点击“主菜单”或全局命令是否能正常退出。确认底层路由引擎平滑接管。

### 🔵 第三步：阶段五代码改动（业务彻底重构）
5. **FSM 过滤器替换**：将所有 FSM 的入口从硬编码正则替换为安全的 `I18nFilter`。
6. **跨用户隔离与 Markdown 转义**：处理 `notify_inviter_reward` 等异步通知的语言绝对隔离，并在翻译引擎中加入安全的局部转义逻辑。
7. **Handler 文本大替换**：全面排查散落的 `reply_text` 文案，将其抽离至 JSON 词典，统一使用 `context.t` 翻译输出。
8. **原生菜单注册**：修改 `setup_commands`，注入各语种的原生 Telegram 菜单。

### 🏁 第四步：阶段五最终部署与交付
- **操作**：完成彻底重构后，**再次重建更新 Bot 服务**。
- **验证点**：在 Telegram 客户端中切换不同语言环境，进行全链路回归测试，确保所有文案、跨用户推送、按键及排版样式均符合多语言预期。
