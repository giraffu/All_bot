# 子模块: QQCC 懒人 Bot (QQCC Lazy Bot)

AI 视频场景面向用户统一称为“高级图生视频pro”。当前普通场景提交 H3 I2V，配置
尾帧生成链的场景提交 H3 FLF2V。旧 LTX engine 在配置归一化时迁移，旧 LoRA 项
清空；`ai_video_addon_models` 作为未来附加模型 catalog，当前为空且前端隐藏。
AI 视频分辨率 catalog 使用 `preview|small|standard|hd` 四档；旧 `1280x704` 或未知
值读取时归一为 `preview`。I2V 与尾帧链 FLF2V 都跟随首帧比例，场景固定价格继续
权威覆盖模型分辨率价格，官方与私有 Bot 保持相同规范化行为。

## 1. 范围与定位

QQCC 懒人 Bot 是主业务 Bot 的独立 Telegram polling 入口，代码位于仓库根目录 `qqcc_bot/`，正式名称为 `@QQCC666_bot`。它提供简化生成入口与 QQCC 专用轻量 `修仙市集`，用户、灵石、会员、历史、并发锁、队列、对象存储、worker 与结果回流全部复用现有生产数据和任务链路。主业务 Bot 底部的旧 `修仙市集` 入口已改为 `懒人bot`；正式使用 main-bot 专属 `MAIN_BOT_LAZY_BOT_ENABLED=true` 与 `MAIN_BOT_LAZY_BOT_USERNAME=@QQCC666_bot`，解析为 `https://t.me/QQCC666_bot`。旧 `QQCC_LAZY_BOT_*` 仅作整组兼容回退。

官方 polling 入口的 `qqcc_bot.polling_liveness` 只观测 Local Bot API
`getUpdates` 是否持续成功；polling 连续 180 秒停滞时，独立 watchdog 线程以专用
退出码终止 QQCC 进程，由容器 `restart: always` 只重建该服务。业务 update
积压或媒体发送慢不得触发进程重启。官方 QQCC 使用
`PerUserUpdateProcessor`，同一用户严格串行、不同用户默认最多并发 16 个；
`concurrent_updates(True)` 仍被禁止。官方 QQCC callback 共享路由有 45 秒总预算；
可选示范媒体、修仙市集媒体发送、场景上传提示和视频提交状态等非关键 Telegram
I/O 分别有 15 秒总预算。quick image/video 与修仙市集一键应用的用户图片接收，
其 `get_file`、Telegram 文件下载和 FSM 临时文件落盘也共用一个 15 秒 QQCC
总预算；超时取消或下载异常会删除可能已写入的半文件、提示下载失败并保持当前
上传状态，用户可直接重试。市集一键应用下载成功后只在当前 update 内完成受限
接收，完整生成与终态监视由受管后台任务继续；后台异常仍清理临时文件并提示
用户。交互预算只作用于 QQCC 上下文，不改变主 Bot 行为。私有 Bot 使用 webhook
worker，不启用 polling watchdog，但复用 QQCC 上下文的非关键交互预算。

它不是主 Bot 的完整副本，不承载充值、affiliate 菜单、主 Bot 完整 gallery 浏览、Web 登录、支付回调或高级视频/高级图像入口。

主菜单可额外展示非生成入口：`修仙市集`、`前往主bot`，以及仅官方 QQCC 展示的 `私有bot`。`修仙市集` 是 QQCC 专用轻量 Gallery 浏览/应用入口；`前往主bot` 用于把用户引回完整主 Bot；`私有bot` 进入 owner token 申请/管理流程。管理后台“主菜单”中的 `main_buttons.private_bot` 可独立隐藏官方入口；它默认开启、不跟随生成能力的 `global_enabled`，也不会停止 private worker 或禁用既有私有 Bot。关闭后旧 reply keyboard 点击会回复 `功能暂未开放`，已经进入 token 步骤的申请会先尽力删除 token 消息再拒绝创建。Telegram 底部菜单按钮不能直接承载 URL，因此用户点击 `前往主bot` 后，QQCC Bot 会回复一条带 inline URL 的跳转按钮。私有 Bot Application 不展示 `私有bot`，避免嵌套申请。

Telegram 底部主菜单的编排由 `main_menu_layout` 控制。`buttons_per_row=null` 表示继续使用升级前固定分行的行数与每行按钮数量，因此未调整顺序的官方或私有 Bot 上线后不会改变菜单；此模式也会按 `button_order` 填充各行。设为 `1..4` 后，Bot 先按现有开关、全局 gate、场景有效性和官方/私有上下文过滤按钮，再按 `button_order` 排序并统一分行。隐藏项不占空位，但配置中保留原排序位置，重新开启或补齐有效场景后回到该位置。排序只接受 `quick_faceswap` / `ai_draw_v1` / `ai_draw_v2` / `ai_filter` / `video_edit_v1` / `video_edit_v2` / `ai_video` / `market` / `private_bot` / `main_bot_link`；未知、重复和旧兼容 key 被丢弃，缺失的有效 key 按默认顺序追加。官方与每个私有 Bot 通过各自现有配置 JSON 独立保存，不新增数据库表。

## 2. 功能边界

自由P图 v3 的配置 engine 为 `free_edit_v3`，AI绘图和 AI滤镜均可选择；它不支持 LoRA，单图映射到独立执行类型 `pornmaster_flux2_edit_bf16`，固定计费 6 灵石。新增场景默认 engine 仍为 `free_edit_v2`，已有 v2 配置保持不变。Central 正式 BF16 路由已于 2026-07-12 通过单服务 force-recreate 生效，后台配置、Bot 提交和 gpu-226 BF16 worker 队列现已贯通。

主菜单业务入口只包含：

- `快速换脸`
- `AI绘图`
- `AI滤镜`
- `AI动图`

`AI动图` 是 QQCC Bot 的专用展示文案，对应共享兼容路由 `menu.video_edit`。不要直接修改共享 `menu.video_edit` 文案来实现 QQCC 菜单改名，否则会影响旧按钮兼容和 QQCC 动图路由。场景配置 v2 起将旧 `video_scenes` / `draw_scenes` 作为 V2 兼容投影，并持久化 `video_scenes_v1`、`video_scenes_v2`、`draw_scenes_v1`、`draw_scenes_v2`：V1 固定旧图生视频/自由P图，V2 固定图生视频 V2/自由P图 V2.5；旧菜单与 callback 仍进入 V2。`main_buttons.ai_draw_v1` 与 `video_edit_v1` 默认关闭，旧 `ai_draw` / `video_edit` 开关只回填 V2，因此代码部署后、正式配置迁移前也不会向用户提前显示 V1；后台显式开启版本开关后才显示对应入口。运行时从场景 callback、素材接收、参数确认到最终提交必须按场景版本检查 `ai_draw_v1|v2` / `video_edit_v1|v2`，不能再次读取旧兼容键，否则会形成一级入口可见、二级场景被错误拒绝的分裂状态。

`快速换脸` 是 QQCC Bot 的专用主菜单文案，对应 `qqcc.menu.quick_faceswap`，复用现有单图随机换脸流程，发送 1 张正脸图后自动匹配模板；它不是主 Bot 的双图 `faceswap_fsm`，也不属于四类场景配置。该入口继续提交 `face_swap` V1、扣 2 灵石，不读取 `credit_cost`。

`AI绘图` 是 QQCC Bot 的专用展示文案，对应 `qqcc.menu.ai_draw` 专用路由。旧配置首次归一化时会通过 `scene_preset_version=1` 一次性种子化两个预设 `draw_scenes`：`快速自慰` 与 `快速脱衣`；种子化后它们和自定义场景没有结构差异，可编辑、删除、调整模型、绘图后处理、滤镜终止后处理和原图换脸。关闭直接入口通过 `main_buttons.ai_draw=false`；管理员也可以清空 `draw_scenes` 删除所有直接 AI绘图场景。配置有效滤镜场景后，默认功能行按 `AI绘图 / AI滤镜 / AI动图` 排列；无滤镜场景时不展示 `AI滤镜`。

`AI滤镜` 是 QQCC Bot 的专用展示文案，对应 `qqcc.menu.ai_filter` 专用路由。它使用独立 `filter_scenes` 场景池，默认配置不种子化场景；`main_buttons.ai_filter=true` 只是允许直接入口，仍需要至少一个有效滤镜场景才在主菜单展示。滤镜场景复用 AI绘图的提示词、负面提示词、engine、LoRA 与 `original_face_swap_enabled` 配置规则，但自身不支持继续配置后处理链。

主菜单非生成入口：

- `修仙市集`
- `前往主bot`
- `私有bot`（仅官方 QQCC；私有实例隐藏）

旧 `快速脱衣` 主菜单、旧 `懒人P图` 主菜单、旧 P 图子按钮和旧快速脱衣二级方式均不再作为 QQCC 用户入口。用户点到旧 reply keyboard 或旧 callback 时必须回复 `功能暂未开放`，不得提交任务。

`AI动图` 场景由管理后台动态配置。默认配置兼容旧五个懒人动图场景：

- 传教士
- 后入
- 口交
- 脱衣吐舌
- 近景口交

后台可增删场景、调整按钮名称、提示词、负面提示词、固定时长、底层模型和可选尾帧来源。旧五个默认动图也只是一次性种子化的普通预设，保存后与自定义场景一致。`image_to_video` 与 `wan22_video_v2` 都支持从 QQCC 专用视频 LoRA 清单按顺序选择最多 5 个模型，并为每项编辑 `0.1..2.0`、步长 `0.05` 的强度；切换 engine 保留选择。清单固定为本地模型注册表 `wan22_explicit_lora_library/2026-07-18` 已下载并逐项核对的 49 组 High/Low；后台 options 返回带编号中文标签和单强度保守推荐值，Vue 只消费 options 并支持搜索，不硬编码清单。旧七模型键在配置归一化时迁移到最接近的新条目。尾帧来源、场景 callback 与菜单规则保持不变；该能力只作用官方/私有 QQCC Bot，主 Bot 不增加多选入口。

`AI动图` 与 `AI视频` 场景还可通过 `next_scene_id` 选择同类型的下一个模板。每个场景只有一个后继，但可形成任意长度的线性链；后台过滤自身和会回到当前场景的候选，保存 API 也会拒绝缺失目标、自环和间接循环并返回循环路径。提交时迭代快照完整链，配置后续修改不影响运行中任务。上一段 Worker 产出的 `extra_outputs.last_frame` 是下一段首帧；每段仍使用自己的 prompt、时长、模型、LoRA、比例和尾帧绘图链。全部成功后按第一段画布对后续视频等比放大、居中裁剪并统一音视频格式后拼接；拼接免费。根场景未配置固定价时，官方后续段失败沿用现有分段退款且成功段保持计费；配置固定价时，后续任一阶段或最终投递失败都按根任务实际扣费全额幂等退款。私有 Bot 用 durable checkpoint 保存当前段、首帧、视频引用和根计费锚点，重启后不重复生成或扣费。后台“生成示例”使用 TTL 24 小时的 Redis checkpoint 推进完整链并只保存最终拼接草稿，始终不扣灵石。

`video_scenes` 和 `ai_video_scenes` 可选填 `jump_draw_scene_id`，只能引用有效 `draw_scenes[].id`。后台在“首尾帧配置”中提供选择；点击对应动图/视频场景后，示范媒体和上传提示下会出现“先去 AI绘图生成”按钮，点击后进入目标绘图场景的单图上传流程。若用户正处于该 AI动图/AI视频的等待上传流程，点击按钮会只清理该待上传视频状态并立即进入绘图流程；其它进行中的交互仍保留原有冲突保护。目标场景删除、失效或关闭 `main_buttons.ai_draw` 时，引用会在归一化时清空或运行时隐藏。

链式视频的尾帧提取、规格归一化、拼接和智能画幅适配发生在控制面媒体编排层。
官方 QQCC、私有 Bot continuation、QQCC Config 示例和 Private Owner 示例分别
运行在 `qqcc-bot`、`private-bot-worker`、`qqcc-config-backend`、
`dashboard-backend`，四者统一继承不可运行的 `python-media-runtime-base`；
该层提供 ffmpeg/ffprobe、OpenCV headless、SmartCrop 和 SHA-256 锁定的 YuNet
ONNX。镜像 focused smoke 必须对四个最终 digest 分别执行双媒体工具、Python
依赖导入和模型存在验证。若某段已生成但尾帧处理失败，用户提示必须明确为
“该段已生成，但尾帧处理失败”；只有生成任务本身失败时才显示“生成失败”。

`AI绘图` 场景由管理后台 `draw_scenes` 动态配置，`快速自慰` 与 `快速脱衣` 两个默认项是一次性种子化的普通预设，底层 engine 均为旧 `free_edit`。每个场景包含按钮名称、提示词、负面提示词、底层模型、可选 `postprocess_draw_scene_id` 绘图后处理、可选 `postprocess_filter_scene_id` 滤镜终止后处理和 `original_face_swap_enabled` 原图换脸，`id` 使用短安全 callback 字符串；所有场景都必须有非空按钮名称和提示词，`negative_prompt` 可选，缺省或非法归一为空字符串，QQCC 运行时只读取场景自身 `prompt` 与 `negative_prompt`，不再通过 `prompt_key` 或 `prompts.ini` 回退。新增自定义场景默认 engine 是自由P图 v2 `free_edit_v2`，不支持附加模型；切到旧 `free_edit` 时才可选图片 LoRA。绘图后处理只能选择其它有效绘图场景；滤镜后处理只能选择有效滤镜场景并作为终止步骤。`postprocess_draw_scene_id` 与 `postprocess_filter_scene_id` 互斥，若两者都有效则保存时保留绘图后处理并清空滤镜引用；后端还会清空非法引用、自引用和绘图循环引用，前端也过滤会形成循环的选项。`original_face_swap_enabled` 只接受布尔 `true`，缺省或非法值归一为 `false`；开启后该步骤按“场景绘图/滤镜 -> 使用用户最初上传原图做人脸来源换脸 -> 后处理链下一步”执行，内部任务类型为 `face_swap_v2`。根场景 `credit_cost=null` 时每个开启步骤额外计费 `2` 灵石；固定价链则包含该费用，内部换脸不得重复扣费。内部换脸不传负面提示词。用户点击主菜单 `AI绘图` 后，QQCC Bot 回复 `system.ai_draw_hint`，并按三个一行展示 inline 场景按钮，callback 使用 `qdraw_scene:<scene_id>`。该 callback 由 `get_quick_image_fsm_handler()` 承接，进入发送 1 张图片步骤；收到图片后按 `draw -> draw...` 或 `draw -> filter` 串行提交绘图/滤镜/原图换脸，每步使用自身负面提示词，只把最终图发给用户。若最终可见输出来自内部原图换脸，历史、结果展示和完成文案仍按原 AI绘图场景归类，不暴露成 `快速换脸`。新 continuation 必须写 V2；恢复升级前 QQCC checkpoint 时，仅把内部原脸恢复 stage 的旧 `face_swap` 解释为 V2，不影响快速换脸。QQCC 生成结果不可投稿、不可公开。旧消息中的已删除场景 callback 必须回复 `功能暂未开放`，不提交任务。本次复用现有 `free_edit`/`img2img` 与 V2 执行面，不新增数据库表。

`AI滤镜` 场景由管理后台 `filter_scenes` 动态配置。每个场景包含按钮名称、提示词、负面提示词、底层模型、可选图片 LoRA 和 `original_face_swap_enabled`，最多 20 个；所有归一化规则与 AI绘图一致，但不提供后处理选择。用户点击主菜单 `AI滤镜` 后，QQCC Bot 回复 `system.ai_filter_hint`，并按三个一行展示 inline 场景按钮，callback 使用 `qfilter_scene:<scene_id>`。该 callback 同样由 `get_quick_image_fsm_handler()` 承接，收到 1 张图片后按单步滤镜场景提交；直接滤镜结果展示滤镜场景名。关闭 `main_buttons.ai_filter` 只隐藏直接入口和拒绝旧 `qfilter_scene:*`，不影响 AI绘图通过有效 `postprocess_filter_scene_id` 引用滤镜模板。

四类场景都可在独立配置 Web 的操作区上传“输入示范”和“输出示范”，上传后当前功能行下方出现左右双栏预览。AI绘图/AI滤镜的两个槽位都只接受 JPEG/PNG；AI动图/AI视频输入接受 JPEG/PNG，输出接受 MP4。用户点击 Telegram 场景按钮时，绘图/滤镜先发送两张图片组成的 media group，动图/视频先发送一张图片和一个视频组成的 media group，然后才发送“请上传一张图片”的文字提示；只配置一个槽位时发送已有媒体，媒体发送失败时降级为文字提示并继续 FSM。

示范文件写入 R2 确定性对象键 `qqcc/demo/<scene_kind>/<scene_id>/<input|output>`，同一槽位替换时覆盖原对象，不新增随机孤儿 key。媒体描述保存 `object_key`、`media_type`、`mime_type`、`file_name`、`content_sha256` 和按 Bot ID 划分的 `telegram_file_ids`；配置 Web 的 `preview_url` 是按请求生成的短签，不写入 checkpoint。Bot 第一次通过 R2 短签发送成功后写回当前 Bot 的 Telegram file_id，后续点击直接使用 file_id；缓存失效自动回退 R2 并刷新。替换文件时内容哈希变化，保存逻辑不会继承旧 file_id，避免继续展示旧示范。

用户点击主菜单 `修仙市集` 后，QQCC Bot 使用专用 `qqcc_bot/gallery_market.py` 入口展示精选的 Web Gallery 可见类型投稿，不复用旧主 Bot 的 gallery 分类常量。callback 前缀为 `qg:`，支持分类、分页、点赞、点踩、一键应用和 Web 应用跳转；不提供留言入口。普通可应用投稿的卡片同时展示 `一键应用` 与 `Web应用`，视频换脸类模板只展示 `Web应用`，Wan22/LTX 多段拼接结果不展示任何应用入口；Bot caption 中的类型和 `#task.mode_*` 标签走当前语言翻译，不直接暴露内部变量名。当前分类为 `all`、`i2i_pro`、`edit_group`、`free_edit_v2_5_group`、`img2video_group`、`ltx_video`、`wan22_video_v2`、`scail2_action_transfer`、`scail2_video_replacement`、`scail2_face_swap_v2`；不展示 `txt2img`、已关闭应用的 `i2i_draw` 或旧 `free_edit_v2_group` v3 兼容分类。

市集与 Web 共用 `src/services/gallery_feed_queries.py`。需要 History 关联时查询会去重；按净赞或净踩排序的计算表达式必须作为稳定别名进入 PostgreSQL select-list，分页 count 子查询移除无意义的 `ORDER BY`，避免 `SELECT DISTINCT` 与计算排序组合导致整页加载失败。

QQCC 市集代码按 Bot 层职责拆分：`qqcc_bot/gallery_market.py` 保留 `qg:` callback 注册、分页加载和兼容 facade；`qqcc_bot/gallery_market_view.py` 负责菜单/帖子按钮与 caption view；`qqcc_bot/gallery_market_interactions.py` 负责点赞/点踩 callback、计数替换和消息更新；`qqcc_bot/gallery_market_apply.py` 负责 apply session、图片下载、原生单图提交和失败清理。Web/Bot 共用 apply-context presenter seam 位于 `src/services/gallery_apply_context_presenter.py`；QQCC Bot 不再直接导入 `src.web_api.common.utils`。

`修仙市集` 媒体发送优先使用 `GalleryPost.telegram_file_id`，失效或缺失时通过当前 Gallery R2/S3 URL resolver 下载当前作品并重新写回 Telegram file_id；测试 Bot 不持久化新 file_id。

QQCC 市集一键应用是轻量 Bot 流程：安全的单图模板在 Bot 内提示用户重新发送 1 张参考图，并以 `source_post_id`、`allow_contribute=False`、`client_type=bot:qqcc` 提交任务；复杂模板、SCAIL-2、多图/多视频复用与首尾帧复杂链路的 `一键应用` callback 只做 Web handoff，返回 `/gallery?apply_source=gallery&apply_id=<post_id>` 深链，不在 Bot 内强行复用视频或多素材。`apply` 次数仍只能在任务成功链路记账，不能在点击按钮时预增。

QQCC 市集 apply 下载的用户图片属于 FSM 临时文件；提交异常、unsupported task type、`/cancel` 或全局异常清理都必须删除已下载路径。原生 Bot apply 只支持安全单图模板，提交时必须透传 `source_post_id` 且 `allow_contribute=False`，复杂模板只 Web handoff，不预增 `applied_count`。

QQCC 功能开关与 QQCC 专用提示词覆盖由独立 QQCC Config Web 维护，主 Dashboard 不再显示 `懒人Bot配置` 导航，也不挂载 `/api/qqcc/config`。配置存入 `runtime_checkpoints`，固定 key 为 `qqcc_lazy_bot_config:v1`，不新增表。独立配置后端 `dashboard.backend.qqcc_config_main:app` 暴露：

- `GET /api/qqcc/config`：返回合并默认值后的有效配置，并附带非持久化 `options`，包含 `scene_preset_version`、默认动图/绘图 engine、engine 选项、LoRA catalog 与 `default_scene_credit_costs`，前端不得手写模型清单、默认场景或新场景价格。
- `PUT /api/qqcc/config`：规范化并保存配置，只保留已知 key。

独立配置页底部“提示词覆盖”只展示 `快速换脸`（`prompts.face_swap`）。`快速自慰`、`快速脱衣` 和默认动图预设都在各自场景行填写提示词，不能留空；后端仍保留 `prompts.undress` / `prompts.masturbation` / 旧动图 prompt 字段用于旧配置迁移兼容。

独立配置页还提供“交互文案”覆盖。`quick_faceswap_start`、`ai_draw_menu`、`ai_filter_menu`、`video_menu` 分别覆盖快速换脸与 AI绘图/AI滤镜/AI动图主菜单点击后的提示；`ai_draw_scene_start`、`ai_filter_scene_start`、`video_scene_start` 覆盖三类二级场景点击后的上传提示。输入框的 placeholder 直接展示当前中文系统默认文案，便于对照，但不会写入配置；所有字段留空时仍使用现有 i18n 默认文案。二级场景模板中的 `{butten}` 会在 Bot 发送前替换成实际点击的场景按钮名称（同时兼容 `{button}`），配置值最长 4000 字符。该配置只影响 QQCC 官方和私有 Bot，主 Bot 不受影响。

QQCC Config Web 使用独立后台账号，不复用 Dashboard 管理员 token：

- `QQCC_CONFIG_ADMIN_USERNAME`
- `QQCC_CONFIG_ADMIN_PASSWORD_HASH`
- `QQCC_CONFIG_SECRET_KEY`

配置结构固定包含：

- `scene_preset_version`: 当前为 `1`；缺失或小于 `1` 视为旧配置，保存时一次性补齐 QQCC 绘图/动图预设并迁移旧 prompt override；已有 `scene_preset_version>=1` 时尊重管理员删除后的空 `draw_scenes` / `video_scenes`
- `global_enabled`
- `main_buttons`: `quick_undress`, `quick_faceswap`, `photo_edit`, `ai_draw`, `ai_filter`, `video_edit`, `market`, `main_bot_link`, `private_bot`；`quick_undress` 与 `photo_edit` 仅保留旧配置兼容，QQCC 主菜单不再渲染；`private_bot` 只控制官方 QQCC 申请/管理入口，默认开启且不跟随 `global_enabled`
- `main_menu_layout`: `{ buttons_per_row, button_order }`；`buttons_per_row` 仅允许 `null` 或整数 `1..4`，`null` 保持旧固定分行的行容量；`button_order` 只保留可渲染主菜单 key 且自动去重/补齐。独立配置 Web 在兼容布局和统一列数下都可上移/下移，关闭按钮仍保留排序位置
- `photo_buttons`: `masturbation`, `random_faceswap`；仅保留旧配置兼容
- `undress_methods`: `legacy`, `i2i_draw`；仅保留旧配置兼容
- `video_scenes`: `[{ id, name, prompt, negative_prompt, duration, engine, aspect_ratio, lora_items, lora_name, lora_strength, end_frame_draw_scene_id, jump_draw_scene_id, credit_cost }]`；`jump_draw_scene_id` 可选且只能引用有效 AI绘图场景，供示范输入跳转按钮使用；其余约束不变。`aspect_ratio` 只允许 `source / 9:16 / 16:9 / 1:1`，缺失、空值或非法值归一为 `source`，旧 checkpoint 无需迁移或提高 preset version；`lora_items` 最多 5 个有序 `{name,strength}`，后端只接受 49 项稳定键、去重保序并截断；旧单模型字段和七个旧键迁移为新列表，响应继续镜像第一项。两个 engine 都保留列表。
- `ai_video_scenes`: `[{ id, name, prompt, negative_prompt, engine, duration, lora_items, end_frame_draw_scene_id, jump_draw_scene_id, demo_input_media, demo_output_media, credit_cost }]`；`jump_draw_scene_id` 语义与 AI动图相同。默认空数组。`engine` 首版固定 `ltx_video`，尺寸固定 `1280x704`，配置时长仅允许数字 `5/10/15/20`（提交到 LTX 任务边界时转为 `5s/10s/15s/20s`）；`lora_items` 使用 `{path,strength}`，来自配置选项接口的 QQCC 专用 LTX catalog，最多 3 个、不可重复，强度 `0.1..2.0` 且按 `0.05` 归一。该专用目录由 `src/qqcc_ltx_lora_catalog.py` 在公开目录之外追加，当前接入本机 2026-07-17 校验库的 32 个权重（26 个为公开目录外新增项）；主 Bot 和公共 Web 不读取该目录。`negative_prompt` trim 后为空仍保存为空，但提交任务时完全省略。
- `draw_scenes`: `[{ id, name, prompt, negative_prompt, engine, lora_name, postprocess_draw_scene_id, postprocess_filter_scene_id, original_face_swap_enabled, credit_cost }]`；所有场景 `prompt` 必填，`negative_prompt` 可选，缺失或非字符串归一为空，字符串保存前 trim；不设置应用层数量上限，独立配置 Web 保存完整数组，后端归一化保留全部有效场景；`engine` 只能是 `free_edit` 或 `free_edit_v2`，缺省 `free_edit_v2`；`lora_name` 只允许在 `free_edit` 下来自 `IMAGE_LORA_MODELS`，v2 自动清空；`postprocess_draw_scene_id` 缺省 `""`，只能引用其它有效绘图场景，非法、自引用和循环引用必须清空；`postprocess_filter_scene_id` 缺省 `""`，只能引用有效 `filter_scenes[].id` 并作为终止后处理，若绘图和滤镜后处理同时有效则保留绘图后处理；`original_face_swap_enabled` 只能为布尔 `true`，缺省或非法值归一为 `false`；`id` 只能用于短安全 callback
- `filter_scenes`: `[{ id, name, prompt, negative_prompt, engine, lora_name, original_face_swap_enabled, credit_cost }]`；所有场景 `prompt` 必填，`negative_prompt` 可选，最多 20 个，engine/LoRA/原图换脸归一规则与 AI绘图一致；自身不支持后处理链，默认配置不种子化任何滤镜场景
- 四类场景的 `credit_cost` 只允许 `null` 或大于等于 1 的整数；缺失字段按 `null` 归一，无需迁移。固定价只读取用户直接点击的根场景，代表完整链总价；清空恢复旧动态/分段计费。新增场景从 options 读取默认值：AI动图 `6`、AI视频 `10`、AI绘图/AI滤镜 `2`。修改模型、时长、尾帧或后处理不会自动改价。
- 四类 scene 均可附带 `demo_input_media` / `demo_output_media`：`{ object_key, media_type, mime_type, file_name, content_sha256, telegram_file_ids }`。AI绘图/滤镜的两个字段都是 image；AI动图/AI视频 input 是 image、output 是 video。`preview_url` 只属于 GET/上传响应，不持久化。
- `video_buttons` 与 `video_settings` 仅保留旧配置兼容；管理后台不再编辑 AI 动图画质或全局时长
- `prompts`: `undress`, `i2i_draw_quick_undress`, `masturbation`, `face_swap`, `perfect_video_insert`, `doggy_style`, `blowjob`, `undress_tongue`, `closeup_blowjob`
- `copywriting`: `quick_faceswap_start`, `ai_draw_menu`, `ai_filter_menu`, `video_menu`, `ai_draw_scene_start`, `ai_filter_scene_start`, `video_scene_start`；只保留上述已知字符串 key，保存时 trim，留空回退默认文案；二级场景模板支持 `{butten}` 按钮名称占位符

`video_scenes`、`ai_video_scenes`、`draw_scenes`、`filter_scenes` 的数组顺序分别决定 AI动图、AI视频、AI绘图、AI滤镜二级场景菜单的展示顺序。独立 QQCC Config Web 使用四个 Tab，每类场景独立按每页 5 条分页；分页只优化当前渲染行，保存仍提交完整场景数组。每个场景行提供上移/下移按钮，首行不能上移、末行不能下移；移动后仍通过现有整份配置 PUT 保存，仅交换数组位置并保持场景 `id` 和引用不变。新增场景自动打开其所在末页，删除和跨页移动后自动校正到包含目标行的有效页。

AI动图模型配置中，每个已选 Wan22 附加模型的强度行提供说明按钮。说明内容固定来自本地模型 registry 的 `wan22_explicit_lora_library/2026-07-18`，前端静态覆盖当前 catalog 的 49 个稳定键，展示分类、用途、触发词、High/Low 强度范围与推荐值、模型页、全部中英提示词示例和注意点；提示词示例默认折叠。该说明只随 QQCC Config 前端发布，运行时不读取 `/srv/allbot/model-registry`，不进入配置 checkpoint、API payload、Bot 提交、workflow 或 GPU 模型装配。

每个场景行只保留一个“场景配置”按钮，弹窗使用单份草稿，取消不修改、确定一次性写回。四类场景均按独立子标题展示“基础配置”和“模型配置”；AI动图/AI视频另有“首尾帧配置”，AI绘图/AI滤镜另有“后处理配置”。灵石消耗属于基础配置；AI动图的分辨率、时长、画面比例和 AI视频的分辨率、时长也在基础配置；AI滤镜的原图换脸从模型区移到后处理区。桌面与移动端弹窗均使用内部滚动。

`video_scenes[].resolution` 允许 `512p`、`720p`、`1024p`，旧场景缺失字段按 `720p` 归一；`ai_video_scenes[].resolution` 当前只允许 `1280x704`。GET options 下发可选清单和默认值，前端不维护另一份运行时清单。PUT 对非法显式值返回 422，并拒绝 AI动图 `1024p + 10s`，不静默改值。QQCC AI动图上传后只显示固定参数摘要和“开始生成”，AI视频继续收图后直接提交；提交、重新生成、结果续作和多段链逐段读取当前场景的分辨率、时长、模型与动态价格，根场景固定价仍只扣一次。非 QQCC 主 Bot 的画质设置和用户权限不变。该扩展继续存储在现有 `runtime_checkpoints` JSON 中，不新增数据库表或 migration，也不改变 workflow、Worker mapping 或 GPU runtime。

示范媒体上传主接口为 `PUT /api/qqcc/demo-media-json/{scene_kind}/{scene_id}/{slot}`，前端以 Base64 JSON 传输，规避 Cloudflare 对 multipart 文件请求的边缘拦截；旧 `/demo-media/...` POST/PUT 仅保留兼容，全部仍由独立 QQCC Config JWT 保护。图片上限 10MB、视频上限 50MB；前端先按槽位校验 MIME 与大小，后端解码后仍检查 MIME、文件签名与大小。上传失败时前端必须优先展示后端 `detail` 的安全中文映射或明确的网络/413/401/403 原因。上传返回媒体描述和短期预览 URL，管理员仍需点击页面“保存”把描述写入当前配置。

上传 input 示范后，每个场景操作区可点击“生成”。`POST /api/qqcc/demo-generation/{scene_kind}` 把 input 示范复制到 Central 可读的临时 MinIO key 并按场景当前草稿的 engine、prompt、negative prompt、LoRA 和动图 duration 提交；响应后 Config Backend 启动最长 24 小时的完成监视，所以浏览器关闭或停止轮询不会中断自动配置。提交入口只用独立短数据库会话读取配置快照，并在注册 BackgroundTasks 前关闭；长时监视轮询 Central 时不占数据库连接，仅在终态写回时短暂创建自己的会话。禁止让 request-scoped `get_db` 跨越后台监视生命周期，否则三个并发视频监视就会占满默认 `pool_size=2 + max_overflow=1`，导致配置 GET 500 和生成 POST 503。前端仍每 2 秒轮询 `GET /api/qqcc/demo-generation/{scene_kind}/{scene_id}/{generation_id}`，最长等待 15 分钟，终态 GET 同时提供幂等写回兜底。`qqcc-config-backend` 的最小服务环境投影必须包含与 Central 一致的 `API_TOKEN`，配置缺失时应在投影阶段 fail closed；该预览链不需要 Worker 控制使用的 `AGENT_SECRET_TOKEN`。成功终态下载图片或 MP4，经签名校验后写入场景目录下带 generation ID 的唯一 output key，并清理临时 input；服务端以行锁读取最新 checkpoint，只替换目标场景的 `demo_output_media`，不覆盖其它场景或并发配置。Central/数据库瞬时异常在监视窗口内重试；generation namespace 不匹配或场景已删除时拒绝写入。前端只有收到 `config_saved=true` 才显示“已自动保存”，不再要求管理员手动点击“保存”。图片输入/输出沿用点击放大预览；视频输入/输出缩略图支持鼠标点击或键盘 Enter/Space 打开大尺寸播放器弹窗，并提供播放与全屏控制。该后台预览链不调用用户任务 facade，不扣灵石、不占用户并发、不写 History，也没有退款语义。私有 Bot owner 复用对应 owner API，输入/输出严格限定在 `qqcc/private/<private_bot_id>/demo/...`，不得跨租户引用。

示范媒体 key allowlist 是 Config Backend 与 QQCC Bot 的共享契约，新增 generated key 形状时必须同时发布两个服务。Bot 在示范发送成功后会通过 `cache_qqcc_demo_telegram_file_ids()` 归一化并回写整份配置；旧 Bot 不认识新 output key 时，会在缓存 input file_id 的成功路径中把 output 从 checkpoint 删除，表面症状是“只显示输入示范且没有发送错误”。回归必须验证 input file_id 缓存回写仍保留 generated output。若发生版本裂缝，R2 的 generation 对象不会被该回写删除，应在升级 Bot 后按 scene ID 选择最新对象补回媒体描述，不要重新生成。

关闭功能后，QQCC Bot 会隐藏新菜单按钮，并在旧 reply keyboard / 旧 callback 入口回复 `功能暂未开放`，不提交新任务。`quick_faceswap` 关闭后，旧 `random_faceswap_again` 也必须拒绝继续提交。AI 动图每个场景的时长由后台固定，用户在 Bot 中只选择画质；画质只受用户权限过滤，仍保持 `1024p` 与 `10s` 不能同时选择。QQCC draw/filter/video 场景正负提示词只来自场景自身 `prompt` / `negative_prompt`，只作用于 QQCC Bot，主 Bot 不受影响。无尾帧来源时，动图 `image_to_video` 无模型提交 `custom_video`，带模型提交 `video_lora`；动图 `wan22_video_v2` 提交 `wan22_video_v2`。两者都透传场景最多 5 项有序 `lora_items`，旧 `lora_name/lora_strength` 只作首项兼容。配置尾帧来源时，用户仍只发送 1 张图；Bot 会先按被引用 AI绘图场景的完整后处理链串行提交隐藏绘图或滤镜任务，每步使用该场景自己的 `negative_prompt`，链内每个开启 `original_face_swap_enabled` 的步骤都会在本步生成后插入内部原图换脸，成功后下载最终图作为尾帧，再以用户原图和生成尾帧提交首尾帧视频；最终视频仍只使用视频场景自己的 `negative_prompt`。旧 `custom_video` / `video_lora` 传两张图并写入 `use_end_frame=true`；`wan22_video_v2` 传 `images=[start,end]`。官方、私有 durable continuation、示范生成与重新生成必须使用同一模型列表，`_wan22_context` 保存完整列表。提交前按“绘图/滤镜链 + 每步原图换脸 + 视频”做合计额度预检，尾帧链任一步生成/换脸失败都不提交视频，视频失败只按视频任务现有退款策略处理，已成功生成的前置隐藏任务历史不回滚且不可投稿。QQCC 链式生成只把第一个真实子任务按普通 Central 队列规则提交并允许 pending 取消；第 2 个及以后子任务都是同一链路的 continuation，统一以 `base_priority=100` 入队，不展示取消按钮，active task registry 写入 `user_cancel_allowed=false`。用户点旧消息上的取消按钮时，`cancel_user_task(...)` 会返回 `not_cancellable`，不调用 Central cancel，也不触发退款。单任务快速换脸、无尾帧 AI动图、单步 AI绘图和单步 AI滤镜保持普通 pending 可取消。`free_edit_v2` 提交 `pornmaster_flux2_single_edit`，旧 `free_edit` 无模型提交 `edit`，带模型提交 `img2img_lora` 并透传 catalog 默认强度；绘图/滤镜任务透传每步自身 `negative_prompt`，为空时保持空负向。QQCC 直接生成链路中，快速换脸、AI绘图、AI滤镜和 AI动图最终可见结果都提交 `allow_contribute=false`，结果按钮不展示投稿或公开入口；旧消息上的 `submit_gallery_*` / `public_share*` 在 QQCC callback 入口回复 `功能暂未开放`。最终可见结果的完成文案使用 QQCC 实际功能名或场景名，避免显示嵌套链路最后一个底层任务；直接 AI滤镜显示滤镜场景名，AI绘图套滤镜后处理仍显示原 AI绘图场景名。结果 metadata 通过 `_qqcc_regenerate` 写入 History `extra_outputs`，展示层据此追加 `qqcc_regenerate:<task_id>` 的 `重新生成` 按钮；metadata 新增 `scene_kind=draw|filter`，旧历史缺失时按 `draw` 兼容。QQCC 重生成 callback 会校验本人历史、下载原始用户输入、按当前配置重建 quick image/video 提交计划并重新做额度检查；场景禁用/删除或历史缺少原图时只回复失败，不进入 worker。中间绘图、原图换脸和视频尾帧链路也均隐藏且不可投稿。新增配置仍复用 `runtime_checkpoints` 的 `qqcc_lazy_bot_config:v1`，不新增 workflow、RunPod profile 或数据库表。

AI视频只有在 `main_buttons.ai_video=true` 且存在有效 `ai_video_scenes` 时才紧随 AI动图显示，callback 为 `qaivid_scene:<id>`。它复用 quick video FSM，但跳过用户分辨率/时长设置：发送一张图后，无尾帧引用提交 LTX I2V；有引用时先执行完整绘图/滤镜链，再以原图和最终尾帧提交 LTX FLF2V。额度预检为尾帧链费用加 LTX 时长费用；中间失败不提交视频。官方与私有 Bot 共用配置，演示输入只接收 JPEG/PNG、输出只接收 MP4，并分别使用 `qqcc/demo/ai_video/...` 与 `qqcc/private/<id>/demo/ai_video/...` 命名空间。私有多阶段链通过 durable continuation 的 `ltx_video` executor 保存原图、当前尾帧和阶段状态。最终结果显示当前场景名和重新生成，重新生成读取最新场景配置并重新核费；不显示 LTX 扩展或拼接按钮。QQCC 控制面发布可直接复用现有正式 LTX GPU runtime，不得因此重建 GPU 容器或创建 RunPod canary；空负面提示词保持工作流默认，非空 LTX 负面提示词只有在 Worker mapping 独立发布验收后才可宣称生效。

QQCC Config 专用 LoRA 的“可配置”和“运行时可加载”是两个门禁。控制面合入后，认证后台会显示专用目录并允许保存，懒人 Bot 会把保存值转换成 Worker 的 `{name,strength}`；目标 LTX Worker 只有在对应 `.safetensors` 已按同名路径进入 `ComfyUI/models/loras/ltx2.3/` 后才能真正执行。本机完整说明、触发词、示范提示词、模型页、预览图、强度范围与哈希位于 `/srv/allbot/model-registry/bundles/ltx23_explicit_lora_library/2026-07-17`；本轮没有发布 RunPod/LAN AIO manifest，也没有修改正式 GPU 运行时。

私有 `bot:qqcc-private:<id>` 的多步绘图、原图换脸插入链和尾帧视频链通过 Redis durable continuation checkpoint 跨进程续跑。quick image/video service 必须先持久化用户原图和完整 stage plan，再派发第一阶段；每个中间结果先 CAS 推进 checkpoint 再清理 registry，不对用户发送。最终可见结果先进入 `delivery_pending`，续跑租约 owner 发送成功后再标记 delivered。`_bot_task_recovery` 仍还原展示语义，`_private_qqcc_continuation` 将 active task 精确关联到阶段 checkpoint；缺少有效关联的隐藏中间输出不得作为最终结果发送。

多阶段状态展示按真实子任务序号确定：首个真实任务使用默认 `show_queue_status=true`，保留排队位置和取消按钮；后续 AI绘图后处理、内部原图换脸、AI动图/AI视频尾帧链及最终 Wan22/旧视频/LTX 使用 `show_queue_status=false`，从提交起持续显示现有图片/视频“生成中”，Central pending/队列位置变化不得触发排队回退。成功、失败、拒绝、退款及最终结果仍走原终态展示。官方 QQCC active registry 的恢复 contract 与私有 Bot durable stage plan 都持久化该策略，重启后不得重新显示后续任务排队；单任务功能继续使用默认值。该展示参数不改变 `base_priority`、`user_cancel_allowed`、计费、History、任务顺序或 Worker 调度。

注册的 FSM 只允许：

- `get_quick_image_fsm_handler()`
- `get_quick_video_fsm_handler()`

不得注册 `faceswap_fsm`、`txt2img_fsm`、`edit_image_fsm`、`image_to_video_fsm`、`wan22_video_v2_fsm`、`ltx_video_fsm`、`scail2_video_fsm`、充值、affiliate redeem 或主 Bot 完整 gallery 菜单入口。`修仙市集` 只能通过 QQCC 专用 handler 与 `qg:` callback 实现轻量浏览/应用。

AI绘图的最终结果若带有 `scene_kind=draw` 的 QQCC 重生成 metadata，结果按钮除“重新生成”外还提供“换个主题”“生成动图”“生成视频”。换主题从该 History 的用户原图开始并选择新的绘图场景；动图和视频从该 History 的最终生成图开始并分别选择当前可用的 AI动图和 AI视频场景。每次点击均重新校验 History 归属、场景有效性和灵石余额，临时素材只用于这一条后续提交。

链式 AI 绘图/滤镜的中间绘图、原图换脸和视频尾帧步骤必须 `record_history=false`，不写入 History/闪回瓶、不可投稿且不发送结果。每条链仅最终可见步骤写一条 History 并发送一份结果；首个真实子任务复用一条生成状态消息，后续阶段不得新增排队或生成展示。

### 2.1 AI动图输入比例适配

后台场景编辑面板的“视频比例”从配置 GET `options.video_aspect_ratios` 读取原始枚举，中文标签仅由 Vue 映射；默认和新增场景均为 `source`。非 `source` 时，QQCC 专属适配器在任务提交前执行 JPEG/PNG 校验和 EXIF 方向归一，再把 Pillow 图像交给可复用的 `src/services/smart_image_aspect_service.py`：

- 最大内接裁剪框预计保留面积低于原图 55% 时，不尝试硬裁，直接生成目标比例画布；完整前景等比缩放居中，背景使用原图 cover、强模糊、降饱和和压暗填充。
- 其余情况先用 `src/services/yunet_face_detector.py` 的 CPU YuNet 检测人脸，并对每张脸向头顶、左右和肩颈方向扩展安全框；全部安全框能容纳时只沿需要裁掉的轴移动裁剪框，使头部接近画面上三分之一。
- 多人联合安全框装不下、YuNet 模型/运行时缺失或检测异常时，一律补边；不得为了继续生成退回可能切头的居中裁剪。
- YuNet 成功执行但未检测到人脸时，使用 `smartcrop.py` 的皮肤/边缘/饱和度显著性候选；SmartCrop 自身不可用或返回非法框才居中裁剪。

整个流程不拉伸前景。后续 Wan22 仍只根据适配后图片比例和用户画质档位缩放。

单首帧 `image_to_video` / `wan22_video_v2` 都提交适配后的首图。尾帧链先用适配首图执行绘图链，再适配最终尾图，保证首尾比例一致。私有 Bot checkpoint 保存内部比例策略，最终 executor 对 durable `original/current` 执行同一处理并在调用既有任务入口前剥离内部字段；后台示例生成也在上传 Central 临时输入前适配 R2 bytes。重新生成和 AI绘图结果的“生成动图”按当前配置重建同一 plan。适配失败时清理 FSM 临时文件、提示图片处理失败，且不调用任务入口、不扣灵石。

该能力是 QQCC 输入适配，不是 workflow 比例开关。检测与裁剪通过
`FocusDetector` / `SaliencyCropper` callable seam 注入，行为测试使用 fake，
不要求测试机持有模型。真实 `qqcc-bot`、`private-bot-worker`、
`qqcc-config-backend` 和 `dashboard-backend` 继承
`python-media-runtime-base`；其中固定 OpenCV headless、SmartCrop 和官方
YuNet 2023 ONNX，模型在镜像构建时按 SHA-256 校验，focused image smoke
分别验证四个最终镜像的依赖导入和模型存在。

## 3. 代码入口

- `qqcc_bot/main.py`：独立启动入口，读取 `QQCC_BOT_TOKEN` 或 `QQCC_BOT_TOKEN_TEST`，设置 `bot_client_type=bot:qqcc`，注册最小 handler 集。
- `qqcc_bot/keyboards.py`：QQCC 专用主菜单、旧 P 图兼容键盘、`AI绘图` / `AI滤镜` / `AI动图` inline 场景菜单。
- `qqcc_bot/commands.py`：QQCC `/start` 与 `/cancel`，复用用户创建和准入逻辑，返回简化菜单。
- `qqcc_bot/prompt_handlers.py`：只路由旧 `menu.photo_edit` 禁用提示、`qqcc.menu.ai_draw`、`qqcc.menu.ai_filter`、`menu.video_edit`、`qqcc.menu.market`、`menu.main_menu`、`menu.back_main` 与 `menu.open_main_bot`。
- `qqcc_bot/gallery_market.py`：QQCC 专用修仙市集 facade，负责 `qg:` callback 注册、分页加载、Gallery file_id 缓存发送和 Web handoff。
- `qqcc_bot/gallery_market_view.py`：市集菜单、帖子 caption、互动/apply 按钮 view-model。
- `qqcc_bot/gallery_market_interactions.py`：点赞/点踩 callback 与 caption 计数更新。
- `qqcc_bot/gallery_market_apply.py`：轻量一键应用 session、受限图片下载、受管后台原生单图提交和失败临时文件清理。
- `qqcc_bot/regeneration_callback.py`：QQCC `qqcc_regenerate:<task_id>` callback，负责从本人 History 准备同功能重生成、额度检查、后台启动和失败临时文件清理；不要把重生成逻辑写回 FSM。
- `qqcc_bot/callback_handler.py`：只导入任务取消、结果评分、随机换脸再来一张、QQCC 市集等必要 callback 注册模块，并在导入后校验 QQCC 必需 callback prefix manifest；旧投稿/公开分享 callback 在这里直接拒绝，不进入共享 Gallery 投稿或公开处理。
- `src/handlers/fsm/quick_image_fsm.py`：在 `bot_client_type=bot:qqcc` 时承接 `qqcc.menu.quick_faceswap` 进入单图随机换脸，并承接 `qdraw_scene:<id>` / `qfilter_scene:<id>` 进入 AI绘图或 AI滤镜单图提交流程；FSM 只负责 Telegram 状态、图片接收、额度检查和回复。主 Bot 的旧 `快速脱衣` / `快速自慰` / `快速换脸` / `AI滤镜` 文本入口只回复 QQCC 懒人 Bot 跳转或入口未配置提示，不提交任务。
- `src/handlers/fsm/quick_video_fsm.py`：在 `bot_client_type=bot:qqcc` 时承接 `qvid_scene:<id>`，按场景 engine 提交旧图生视频或 `wan22_video_v2`；配置 `end_frame_draw_scene_id` 时先复用对应 AI绘图场景的完整后处理链生成隐藏尾帧，再提交首尾帧视频。主 Bot 的旧 `menu.video_edit_*` 文本入口和 `qvid_*` callback 只回复 QQCC 懒人 Bot 跳转或入口未配置提示，不提交任务。
- `src/services/qqcc_draw_chain_service.py`：QQCC AI绘图/AI滤镜链共享 helper，负责解析 `draw -> draw...`、`draw -> filter` 和直接 `filter` 链、计算链路费用、串行执行绘图/滤镜/原图换脸并复用中间产物；直接 AI绘图、直接 AI滤镜和 AI动图尾帧共用这里的 `original_face_swap_enabled` 语义，并在真实子任务维度标记首任务可取消、后续 continuation 不可取消且 `base_priority=100`。
- `src/services/quick_image_submission_service.py`：Quick Image / QQCC AI绘图/AI滤镜提交计划事实源，负责随机换脸模板过滤、QQCC draw/filter scene engine 分支、后处理链成本合计、`scene_kind` metadata 和最终 image payload；旧 `WAIT_UNDRESS_METHOD` 选择态已清理，`i2i_draw` payload 仅保留兼容。
- `src/services/qqcc_demo_media_service.py`：示范媒体上传校验、R2 确定性 key、配置预览短签、Telegram 图片/视频 media group 发送、file_id 优先与失效回退的事实源；当 Telegram 拒绝 R2 短签 URL 时，在同一媒体大小和文件签名校验内从 R2 读取并直接上传，再缓存新的 file_id。file_id checkpoint 更新由 `qqcc_config_service.py` 完成。
- `src/services/quick_video_submission_service.py`：Quick Video / QQCC AI动图提交计划事实源，负责 QQCC video scene engine 分支、尾帧绘图链成本合计和最终 video payload；FSM 只保留 Telegram 状态和额度/回复 orchestration。
- `src/services/qqcc_regenerate_metadata.py`：QQCC 结果重生成 metadata 与 callback prefix 事实源，统一 `_qqcc_regenerate` 结构，供 History 持久化和结果按钮展示层共用。
- `src/services/qqcc_regeneration_service.py`：QQCC 结果重生成准备 service，负责校验本人 History、下载原始用户输入、按当前 QQCC 配置重建 quick image/video 提交计划和复用原结果展示名。
- `src/services/qqcc_config_service.py`：QQCC 配置默认值、normalize、runtime checkpoint 读写与 QQCC prompt override 解析。
- `src/services/qqcc_runtime_context.py`：集中维护 `bot:qqcc` 常量、QQCC Bot 上下文判断和按上下文加载运行时配置的兜底逻辑，供 quick image/video FSM 与 callback helper 复用。
- `dashboard/backend/qqcc_config_main.py`：独立 QQCC Config API 入口，只做 DB 初始化、独立认证、健康检查与 QQCC 配置 router，不启动 Dashboard 后台循环。
- `dashboard/backend/qqcc_config_auth.py`：独立 QQCC Config 账号与 JWT。
- `dashboard/backend/routers/qqcc.py`：QQCC 配置 router，被独立配置后端挂载。
- `dashboard/frontend/src/QqccConfigApp.vue` / `dashboard/frontend/index.qqcc-config.html`：独立 QQCC Config Web 入口。
- `dashboard/frontend/src/components/QqccBotSettings.vue`：QQCC 配置页主体组件，供独立 Web 复用；通过 props 接收独立配置 API handler，只渲染后端返回的 config/options，不在组件内合成默认场景。
- `dashboard/frontend/src/data/wan22LoraHelp.zh-CN.json`：AI动图 49 个 Wan22 附加模型的版本化中文帮助数据，只供配置页说明弹窗使用；选项可用性、默认强度和运行时路径仍以服务端 catalog 为准。

主 Bot 入口仍是 `src/bot_main.py`。不要在 `qqcc_bot/` 中导入 `src.bot_main`，否则会把主 Bot 的完整 handler 面一起注册进来。
QQCC Bot 注册 quick image/video ConversationHandler，`qqcc_bot/main.py` 使用按
用户串行的 keyed update processor，不得启用 PTB `concurrent_updates(True)`；
`/cancel` 必须调用 `cleanup_fsm_user_data(...)` 清理 `*_data` 与临时文件，再清理
`qqcc_gallery_apply` session。

## 4. 任务来源归属

Telegram Bot 任务默认来源为 `client_type="bot"`。QQCC Bot 在 `application.bot_data["bot_client_type"]` 写入 `bot:qqcc`，`run_bot_task_application(...)` 读取该值并透传到 `process_and_submit_task(client_type=...)`。
`bot:qqcc` 常量与上下文判断统一来自 `src/services/qqcc_runtime_context.py`，避免 QQCC main、quick image/video FSM 和 callback 侧各自复制来源判断。

active task registry 必须持久化 `client_type`：

- 主 Bot 恢复 `client_type=bot` 与缺失 `client_type` 的 legacy 任务。
- QQCC Bot 只恢复 `client_type=bot:qqcc` 的任务。

新增 Bot 入口或任务提交 seam 时，不得让两个 polling 进程交叉恢复或发送彼此的任务恢复消息。

### 4.1 用户私有 Bot 来源隔离

官方 QQCC 主菜单额外提供 `私有bot` 申请入口；每个已注册用户无需审核即可绑定一个全新的 Telegram Bot。该入口由官方 QQCC 配置的 `main_buttons.private_bot` 控制，并与部署总 gate `PRIVATE_QQCC_BOT_ENABLED` 叠加生效。菜单开关只暂停新入口和新申请，不影响已创建私有 Bot 的 webhook worker。私有实例使用 webhook，不参与官方 QQCC polling，也不展示再次申请入口。每个实例把 `application.bot_data["bot_client_type"]` 设为 `bot:qqcc-private:<private_bot_id>`，运行时配置从 `private_qqcc_bots.config` 加载。

私有 worker 重启时只恢复 exact client type 匹配的任务。`bot:qqcc`、`bot`、legacy 和其它 private ID 都必须跳过。完整凭据、状态、Owner WebApp、管理员治理和发布契约见 `docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md`。

owner 轮换凭据时只允许同一 `telegram_bot_id`；即使仍有已扣费/active task 也必须允许用新 token 救援被撤销的旧凭据，worker 按 token 指纹关闭旧 Application 并重建。不同 Bot ID 必须由管理员永久解绑后再申请，永久解绑仍须等待 active task 清空。

私有租户的频道会员判断统一走 worker 持有的官方 QQCC membership checker：正式使用 `QQCC_BOT_TOKEN`，测试使用 `QQCC_BOT_TOKEN_TEST`，仅执行频道成员查询，不启动 polling，租户 Application 也拿不到官方 Bot/token。checker 在进程内对同一 Telegram 用户 singleflight，Redis 在租户间共享正向 60 秒、负向 5 秒缓存，不能改成用租户 Bot 查询官方频道。

webhook worker 使用全局 inflight、单 Bot prefetch 和 deferred ID 三层有界背压（默认 `64/8/1024`）；启动必须先完整 `XAUTOCLAIM` 旧 PEL，catch-up 完成前不读新 `>` update，避免同一 Bot 新消息越过旧 pending。管理员 `/api/private-bots/admin/metrics` 汇总 stream backlog/pending、webhook enqueue/duplicate/error counters 与 worker active Application、inflight/deferred、处理/DLQ/恢复失败 heartbeat。

## 5. 部署与 token 红线

云正式 compose service：

- service: `qqcc-bot-prod`
- container: `cloud-qqcc-bot-prod`
- profile: `qqcc-bot`
- command: `python -m qqcc_bot.main`
- token env: `QQCC_BOT_TOKEN`
- optional main Bot jump: `QQCC_MAIN_BOT_URL` 或 `QQCC_MAIN_BOT_USERNAME`

云测试 compose service：

- service: `qqcc-bot-test`
- container: `cloud-qqcc-bot-test`
- profile: `qqcc-bot`
- token env: `QQCC_BOT_TOKEN_TEST`
- optional main Bot jump: `QQCC_MAIN_BOT_URL` 或 `QQCC_MAIN_BOT_USERNAME`

token 只允许放在 ignored env 文件，例如 `.env.cloud.prod` 或 `.env.cloud.test`。不得写入仓库、docs、日志、工单、`docker compose config` 输出或聊天记录。若 token 曾暴露，应在正式上线前轮换。

独立 QQCC Config Web 云正式 service：

- backend service/container: `qqcc-config-backend-prod` / `cloud-qqcc-config-backend-prod`，默认端口 `8045`
- frontend service/container: `qqcc-config-frontend-prod` / `cloud-qqcc-config-frontend-prod`，默认端口 `8088`

云测试现有专属 QQCC Config Web 前后端，分别使用测试 8045/8088；
`qqcc-config-backend` 与 `qqcc-config-frontend` 必须从完整 main SHA 构建，
分别以不可变 digest 部署并验收。
`https://qqcc-admin-test.aivison.it.com` 通过测试 Tunnel 回源 `100.82.124.91:8088`，属于共享测试发布事务管理的测试入口。公网必须先通过仅允许管理员邮箱的 Cloudflare Access，进入后仍需 QQCC Config 独立账号登录；当前可达只证明入口健康，验收还必须核对容器 digest/revision 与业务页面。

私有 Bot webhook worker 由同一 `Dockerfile.qqcc` 构建，但使用独立 profile 和入口：

- test: `qqcc-private-bot-worker-test` / `cloud-qqcc-private-bot-worker-test`
- prod: `qqcc-private-bot-worker-prod` / `cloud-qqcc-private-bot-worker-prod`
- profile: `qqcc-private-bots`
- command: `python -m qqcc_private_bot.worker`

worker 仍需注入环境对应的 `QQCC_BOT_TOKEN` / `QQCC_BOT_TOKEN_TEST`，但只用于上述官方频道会员 checker；它绝不能用该 token 启动 `getUpdates` 或官方 QQCC handler，租户 webhook 仍逐 Bot 从数据库解密各自 token。

该 profile 不随默认控制面启动，worker 自身也会在 `PRIVATE_QQCC_BOT_ENABLED` 非真时拒绝启动。2026-07-12 云正式已执行 migration `3e9c7a1b5d24`、设置 gate=`true`、启动 `cloud-qqcc-private-bot-worker-prod`，并启用生产 webhook 与 `private-bot.aivison.it.com` owner Host；后续发布仍须显式带上该 profile 并验证 worker heartbeat。

safe deploy 脚本调用 `scripts/validate_private_qqcc_bot_env.py --allow-disabled`：gate 缺失/`false` 时允许普通控制面在不填写私有 Bot activation secrets 的情况下完成 compose 校验；gate=`true` 时严格要求全部密钥、HTTPS/Host/R2 契约和环境对应的官方 QQCC token。直接运行 validator 且不加 `--allow-disabled` 是启用前严格检查，gate 非真也会失败。

QQCC Config Web 只面向 Tailscale/受控入口或 Cloudflare Access 保护入口，不得裸露公网。
测试私有 Bot gate 仍关闭时，不得仅因管理员后台上线就创建公开 Owner Host；`private-bot-test.aivison.it.com` 必须等独立测试 keyring/JWT/fingerprint、HTTPS webhook、owner URL/Host 和 private worker 严格门禁全部通过后再单独上线。

QQCC 跳转主 Bot 按钮优先读取 `QQCC_MAIN_BOT_URL`，可配置为 `https://t.me/<main-bot-username>` 或带 `start` 参数的 Telegram deeplink；未配置 URL 时会尝试 `QQCC_MAIN_BOT_USERNAME` 并自动拼成 `https://t.me/<username>`。两者都未配置时，菜单仍可显示 `前往主bot`，但点击后只提示主 Bot 入口暂未配置。

主业务 Bot 跳转 QQCC 懒人 Bot 使用独立反向配置：`MAIN_BOT_LAZY_BOT_ENABLED=false` 可隐藏新菜单并关闭旧入口；缺失或为真时菜单正常显示，优先读取 `MAIN_BOT_LAZY_BOT_URL`，未配置时读取 `MAIN_BOT_LAZY_BOT_USERNAME` 并自动生成 `https://t.me/<username>`。新命名空间任一键存在即整组优先，只有完全不存在时才回退旧 `QQCC_LAZY_BOT_*`；两组都没有目标时只提示入口暂未配置。正式配置固定指向 `@QQCC666_bot`，且这些 `MAIN_BOT_*` 键只进入 `main-bot` 投影，不得改变 QQCC、私有 Bot 或管理面配置 revision。

QQCC Bot 不启动 TON 轮询，不注册支付回调，不作为充值入口。compose 中必须显式设置 `TON_PAYMENT_POLLING_ENABLED=false`。

测试环境没有独立 `QQCC_BOT_TOKEN_TEST` 时，`qqcc-bot-test` 必须保持停止，避免和正式 token 或其它测试实例双 polling。

## 6. 维护与发布

QQCC 代码使用独立模块不可变发布。专用
`update_cloud_prod_qqcc_bot.sh` 已 fail closed；禁止源码同步、远端 build、
自由 Compose 或隐式扩大到其它模块。官方 Bot 的 main SHA 构建与测试部署：

```bash
python scripts/release.py build --module qqcc-bot --sha <40位main-sha>
python scripts/release.py deploy \
  --env test --module qqcc-bot \
  --artifact ghcr.io/giraffu/allbot-qqcc-bot@sha256:<digest>
```

没有独立 `QQCC_BOT_TOKEN_TEST` 时，`qqcc-bot-test` 必须保持停止，且不得对
test 执行 `qqcc-bot` deploy；不得为测试临时复用正式 token。

生产只部署同一精确 artifact，并逐模块确认：

```bash
python scripts/release.py deploy \
  --env prod --module qqcc-bot \
  --artifact ghcr.io/giraffu/allbot-qqcc-bot@sha256:<digest> \
  --confirm-prod
```

QQCC Config 前后端是两个独立 artifact，分别构建、部署和回滚：

```bash
python scripts/release.py build \
  --module qqcc-config-backend --module qqcc-config-frontend \
  --sha <40位main-sha>
python scripts/release.py deploy \
  --env prod --module qqcc-config-backend \
  --artifact ghcr.io/giraffu/allbot-qqcc-config-backend@sha256:<digest> \
  --confirm-prod
python scripts/release.py deploy \
  --env prod --module qqcc-config-frontend \
  --artifact ghcr.io/giraffu/allbot-qqcc-config-frontend@sha256:<digest> \
  --confirm-prod
```

多模块更新不得伪装成单一事务；按明确顺序逐一执行，任何模块失败即停止后续
模块。migration、配置契约和 Compose 契约必须作为 catalog 中的独立模块另行
授权。QQCC Bot 继续读取 `GENERATION_MAINTENANCE_FILE`，但模块发布器不隐式
开启或关闭全局维护。

## 7. 最小验证

代码变更至少跑：

```bash
pytest tests/qqcc_bot tests/dashboard -q
cd dashboard/frontend && npm run typecheck && npm run test && npm run build
python -m alembic heads
pytest tests/qqcc_bot/test_qqcc_bot_entrypoint.py \
  tests/services/test_task_service_flow.py \
  tests/services/test_recovery_service.py -q
pytest tests/ops/test_release_cli.py -q
```

涉及任务 registry 或 core 提交流程时，补跑：

```bash
pytest tests/core/test_task_core_submission.py tests/services/test_task_service_flow.py -q
```

涉及 quick image/video FSM 时，补跑相关 handler 回归：

```bash
pytest tests/handlers/test_fsm_state_priority.py -q
```

QQCC 快速入口至少覆盖：

- 主业务 Bot 主菜单展示 `懒人bot`、`图片换脸` 与 `视频生视频`，不展示旧 `修仙市集` 或 `视频创作`；点击 `懒人bot` 或旧 `修仙市集` 文本回复前往 QQCC 的 inline URL 按钮。
- 主业务 Bot `图片换脸` 二级菜单只展示 `快速换脸`、`随机换脸` 与返回主菜单；旧 `快速脱衣`、`快速自慰`、旧 `AI绘图` / `AI滤镜` / `AI动图` / `快速换脸` 文本入口、旧动图文本入口和主 Bot 上的 `qvid_*` callback 回复 QQCC 懒人 Bot inline 跳转或入口未配置提示，且不提交任务。
- `/start` 主菜单默认展示 `快速换脸`、`AI绘图`、`AI动图`，不展示旧 `快速脱衣`、`懒人P图` 或空场景 `AI滤镜`；配置有效 `filter_scenes` 后展示 `AI滤镜`，功能行顺序为 `AI绘图 / AI滤镜 / AI动图`。
- 官方 QQCC `/start` 只返回简化主菜单，不额外发送跳转消息；主菜单包含非生成入口 `修仙市集`、`前往主bot` 与 `私有bot`。私有实例使用相同生成/市集菜单，但必须隐藏 `私有bot`。
- 配置 `QQCC_MAIN_BOT_URL` 或 `QQCC_MAIN_BOT_USERNAME` 时，点击 `前往主bot` 回复 inline URL 跳转按钮；未配置时回复入口未配置提示。
- 点击主菜单 `快速换脸` 直接进入 quick image 单图随机换脸流程，发 1 张正脸图后自动匹配模板；不注册 `faceswap_fsm`。
- 旧配置迁移后默认带 `快速自慰` 和 `快速脱衣` 两个普通预设，主菜单展示 `AI绘图`；点击后按三个一行展示 inline 场景按钮，点击 `qdraw_scene:<id>` 进入 quick image 发送图片步骤并按场景 engine、场景 `prompt` / `negative_prompt`、绘图后处理或终止滤镜后处理链提交 `pornmaster_flux2_single_edit` / `edit` / `img2img_lora`，只发送最终图；场景删除后旧 callback 回复 `功能暂未开放` 且不提交任务。
- `AI滤镜` 默认无场景不展示；配置有效 `filter_scenes` 后点击主菜单回复滤镜 inline 场景按钮，点击 `qfilter_scene:<id>` 进入 quick image 发送图片步骤并按单步滤镜场景提交。场景删除、禁用或主开关关闭后旧 callback 回复 `功能暂未开放` 且不提交任务。
- 配置 Web 四类场景行均展示灵石消耗与输入/输出示范操作；上传后双栏预览。绘图/滤镜点击场景先发双图片，动图/视频先发图片+视频，随后才发文字提示。首次发送从 R2 获取并缓存 file_id，重复发送不再上传；缓存失效自动刷新，替换内容后旧 file_id 不复用。
- 点击主菜单 `AI动图` 后，Bot 回复下方展示当前后台配置的 inline 场景按钮，默认第一行 3 个、第二行 2 个；点击 `qvid_scene:<id>` 进入 quick video 发送图片步骤。旧 `qvid_mode:*` 已发按钮兼容到对应场景，场景删除后回复 `功能暂未开放` 且不提交任务。
- 点击主菜单 `修仙市集` 后展示 QQCC 专用类型菜单；浏览投稿时支持点赞、点踩、上一条/下一条、分类返回、一键应用或 Web 应用，不展示留言入口。
- `修仙市集` 二次查看已缓存作品时优先用 Telegram file_id，file_id 失效后从当前 R2/S3 URL resolver 刷新。
- Bot 原生应用必须传 `source_post_id` 且 `allow_contribute=False`，复杂模板必须跳 Web 深链，点击应用不直接增加 `applied_count`。
- QQCC 自己生成的快速换脸、AI绘图、AI滤镜和 AI动图结果不可投稿、不可公开；新结果不展示 `submit_gallery_*` / `public_share_request`，旧结果按钮也必须在 QQCC callback 入口拒绝。结果完成文案必须显示 `快速换脸` 或选中的 QQCC 绘图/滤镜/动图场景名，结果按钮必须展示 `重新生成` 并能从本人历史重建同一功能提交。
- 旧 `快速脱衣`、旧 `懒人P图` 与旧 P 图子按钮回复 `功能暂未开放`，不提交任务。
- 关闭任一 QQCC 配置开关后，新菜单隐藏对应按钮，旧按钮/旧 callback 回复 `功能暂未开放` 且不提交任务。
- QQCC 动态场景 prompt、按钮名、固定时长、engine、最多 5 个 LoRA/强度与尾帧来源配置生效时不影响主 Bot；Bot 发图后仍只展示画质选项和开始按钮，附加模型完全来自后台场景配置。
- AI动图配置尾帧来源后，用户仍只发 1 张图片；额度预检使用绘图/滤镜链加视频合计费用，尾帧链隐藏执行且不可投稿，任一步失败都不提交视频，最终视频使用首尾帧提交。关闭主菜单 `AI绘图` 只影响直接入口，不影响已被动图场景引用的有效 `draw_scenes`；关闭 `AI滤镜` 只影响直接滤镜入口，不影响有效滤镜模板被 AI绘图后处理引用。
- 链式 AI绘图/AI滤镜/AI动图只允许第一个真实子任务 pending 取消；后续 continuation 不展示取消按钮，用户取消入口返回不可取消，提交时使用 `base_priority=100`。
