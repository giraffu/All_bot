---
name: "allbot-qqcc-lazy-bot"
description: "处理官方 QQCC 懒人 Bot、用户私有 Bot 申请/配置、webhook worker、租户 client_type 归属与 polling/webhook 部署红线。"
---

# AllBot QQCC 懒人 Bot

本技能用于维护根目录 `qqcc_bot/` 官方 Telegram polling 服务及 `qqcc_private_bot/` 多租户 webhook worker。只要修改 QQCC Bot 菜单、私有 Bot 申请/凭据/管理、handler 注册、启动入口、任务 client_type、恢复过滤、compose 服务或 QQCC 部署脚本，就必须加载本技能，并按需叠加 `allbot-tg-fsm`、`allbot-task-engine`、`allbot-ops-deployment`、`allbot-cloudflare-ops`、`allbot-tdd`。

## 1. 当前入口
- 代码入口：`qqcc_bot/main.py`
- 正式 service：`qqcc-bot-prod` / `cloud-qqcc-bot-prod` / profile `qqcc-bot`
- 测试 service：`qqcc-bot-test` / `cloud-qqcc-bot-test` / profile `qqcc-bot`
- 正式日常发布入口：`scripts/release.py promote --modules qqcc-bot --confirm-prod`；Bot 与配置可在同一事务用 `--modules qqcc-bot,qqcc-config`
- 配置服务：`src/services/qqcc_config_service.py`
- 运行时上下文 helper：`src/services/qqcc_runtime_context.py`
- 独立配置 API 入口：`dashboard/backend/qqcc_config_main.py`
- 独立配置认证：`dashboard/backend/qqcc_config_auth.py`
- 配置 router：`dashboard/backend/routers/qqcc.py`
- 配置页组件：`dashboard/frontend/src/components/QqccBotSettings.vue`
- 独立配置 Web 入口：`dashboard/frontend/src/QqccConfigApp.vue` / `dashboard/frontend/index.qqcc-config.html`
- 领域文档：`docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`
- 私有 Bot 文档：`docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md`

### 1.1 用户私有 Bot 稳定入口

- 申请 FSM：`qqcc_bot/private_bot_fsm.py`，只在官方 QQCC 注册；私有实例必须设置 `include_private_bot_provisioning=false`。
- 凭据/lifecycle：`src/services/private_qqcc_bot_credentials.py`、`private_qqcc_bot_service.py`、`private_qqcc_bot_runtime.py`。
- Webhook ingress/queue：`src/web_api/routers/private_bots.py`、`src/services/private_qqcc_bot_webhook_queue.py`。
- Worker：`python -m qqcc_private_bot.worker`；Redis stream `${REDIS_PREFIX}private_qqcc_bot:webhook:updates`。
- 统一频道会员检查：`src/services/qqcc_channel_membership_service.py`；private worker 持有官方 QQCC checker，租户 Application 只拿 callable。
- 运行指标：`src/services/private_qqcc_bot_metrics.py`、管理员 `GET /api/private-bots/admin/metrics`。
- Owner/Admin API：`dashboard/backend/routers/private_bots.py`；Owner WebApp 与 Admin UI 共用 QQCC Config build，但必须按 Host 隔离。

## 2. 功能范围
用户私有 Bot 的生成任务必须经持久 submission ledger：确定性 task ID、owner fence、同事务 debit marker、统一 refund key 和 TaskRegistry concurrency acquisition mode 都不能省略。`concurrency_acquisition_key` 存在/缺失自动区分 keyed release 与旧任务一次 legacy DECR，不要求人工 drain。账本 retention 默认 90 天、最少 30 天，只删除无活跃 TaskRegistry 引用的安全终态，禁止清理任何待恢复或待补偿行。

主菜单业务入口只能有 `快速换脸`、`AI绘图`、`AI滤镜` 和 `AI动图`。`快速换脸` 是 QQCC 对现有单图随机换脸流程的专用主菜单入口，显示文案走 `qqcc.menu.quick_faceswap`，不接入主 Bot 双图 `faceswap_fsm`。`AI绘图` 是 QQCC 对 `qqcc.menu.ai_draw` 的专用显示文案；`AI滤镜` 是 QQCC 对 `qqcc.menu.ai_filter` 的专用显示文案；`AI动图` 是 QQCC 对 `menu.video_edit` 的专用显示文案。不要直接改共享 `menu.video_edit` 文案来实现 QQCC 菜单改名，以免破坏旧按钮兼容和 QQCC 动图路由。旧 `快速脱衣` 主菜单和 `懒人P图` 主菜单已退出；用户点击旧 reply keyboard / 旧 P 图子按钮时必须回复 `功能暂未开放` 并拒绝提交。主菜单可额外有 `修仙市集`、`前往主bot` 和仅官方 QQCC 展示的 `私有bot` 非生成入口；私有 Application 必须隐藏 `私有bot`。官方入口还受 `main_buttons.private_bot` 独立开关控制，该开关不停止 private worker、不禁用既有私有 Bot，也不取代 `PRIVATE_QQCC_BOT_ENABLED` 总 gate；关闭后旧 reply keyboard 必须回复 `功能暂未开放`，正在等待 token 的申请也必须先删除 token 消息再拒绝创建。Telegram reply keyboard 不能直接承载 URL，因此点击 `前往主bot` 后由 QQCC Bot 回复主 Bot 的 inline URL 跳转按钮。主业务 Bot 的旧 `修仙市集` 底部入口已改为 `懒人bot` 跳转，跳转目标由 `QQCC_LAZY_BOT_URL` 或 `QQCC_LAZY_BOT_USERNAME` 配置；QQCC 自己的 `修仙市集` 仍是专用轻量 Gallery。

QQCC `AI动图` 场景由独立 QQCC 配置 Web 的 `video_scenes` 动态配置。默认配置会一次性种子化旧五个懒人动图预设（传教士、后入、口交、脱衣吐舌、近景口交），种子化后它们和自定义场景结构一致，可编辑、删除、调整按钮名、提示词、负面提示词、固定时长、底层模型和尾帧来源。`image_to_video` 与 `wan22_video_v2` 都可按顺序配置最多 5 个附加模型和独立强度；切换 engine 不得清空选择。`end_frame_draw_scene_id` 只能引用归一化后的 `draw_scenes[].id`，空字符串保持单首帧旧行为；运行时若该绘图场景配置了后处理链，视频尾帧必须使用完整绘图链的最终图。绘图场景删除或引用非法时必须清空。二级场景菜单必须挂在 Bot 回复消息下方，用 inline button 展示，每行最多 3 个；新场景按钮 callback 前缀为 `qvid_scene:`，由 `get_quick_video_fsm_handler()` 直接承接并进入发送图片步骤。旧 `qvid_mode:<menu.video_edit_*>` callback 仅作已发消息兼容，若对应场景已删除必须回复 `功能暂未开放` 并拒绝提交。

QQCC `AI绘图` 场景由独立 QQCC 配置 Web 的 `draw_scenes` 动态配置。旧配置第一次归一化时会写入 `scene_preset_version=1` 并一次性种子化两个预设场景：`快速自慰` 与 `快速脱衣`，底层 engine 均为旧 `free_edit`；种子化后它们和“小屁股”这类自定义场景没有结构差异，可编辑、删除、调整底层模型、`postprocess_draw_scene_id` 绘图后处理、`postprocess_filter_scene_id` 滤镜终止后处理和 `original_face_swap_enabled` 原图换脸。所有有效场景都必须有非空 `name` 与 `prompt`，`negative_prompt` 可选且缺省/非法归一为空字符串；QQCC 运行时只读取场景自身 `prompt` 与 `negative_prompt`，不再通过 `prompt_key` 或 `prompts.ini` 回退。默认新增场景 engine 是自由P图 v2 `free_edit_v2`，不支持附加模型；切到旧 `free_edit` 时才可选图片 LoRA。绘图后处理可引用其它有效 `draw_scenes[].id`，不能自引用；滤镜后处理可引用有效 `filter_scenes[].id`，且只能作为终止步骤。`postprocess_draw_scene_id` 与 `postprocess_filter_scene_id` 互斥，后端保存时若两者都有效，保留绘图后处理并清空滤镜引用；保存时还必须清空非法引用、自引用和绘图循环链路内引用，前端保存前也必须过滤/阻止循环。`original_face_swap_enabled` 缺省/非法时归一为 `false`；开启后每个场景先按自身 prompt/negative_prompt/engine/LoRA 绘图，再用用户最初上传的原图做人脸来源、用该步生成图做 body 提交内部 `face_swap_v2`，最后才继续后处理链，内部 V2 不传负面提示词。每个开启步骤额外计费 `2` 灵石，提交前额度检查和隐藏换脸任务实际扣费必须一致；直接 AI绘图和 AI动图尾帧引用同一绘图链语义。升级前私有 checkpoint 中只对该内部 stage 的旧 `face_swap` 做 V2 恢复归一，快速换脸仍是 V1。二级场景菜单必须挂在 Bot 回复消息下方，用 inline button 展示，每行最多 3 个；场景按钮 callback 前缀为 `qdraw_scene:`，由 `get_quick_image_fsm_handler()` 直接承接并进入发送图片步骤。收到 1 张图片后按该场景解析 `draw -> draw...` 或 `draw -> filter` 链串行提交，直接 AI绘图只把最终图发给用户；若最终可见任务是内部原图换脸，结果展示、完成文案和历史仍按原 AI绘图场景的 task type、prompt 与用户原始输入图归类，不暴露成 `快速换脸`。QQCC 生成结果不可投稿、不可公开。旧/删除后的场景 callback 必须回复 `功能暂未开放` 并拒绝提交。该能力复用 V2 执行面，不新增数据库表。

QQCC `AI滤镜` 场景由独立 QQCC 配置 Web 的 `filter_scenes` 动态配置。默认配置只新增 `main_buttons.ai_filter=true` 开关，不种子化任何滤镜场景；无有效滤镜场景或开关关闭时，QQCC 主菜单不展示 `AI滤镜`。滤镜场景结构与 AI绘图的模型字段一致：`id`、`name`、`prompt`、`negative_prompt`、`engine`、`lora_name`、`original_face_swap_enabled`，最多 20 个，`id` 使用短安全 callback 字符串；但滤镜场景自身不支持继续配置后处理链。用户点击 `AI滤镜` 后，Bot 回复 `system.ai_filter_hint` 并展示 `qfilter_scene:<id>` inline 场景按钮；该 callback 仍由 `get_quick_image_fsm_handler()` 承接，收到 1 张图片后按单步 `filter` 场景提交，费用、负面提示词、LoRA、原图换脸、continuation 不可取消和重生成 metadata 语义复用 AI绘图。关闭 `main_buttons.ai_filter` 只隐藏直接入口，不影响 AI绘图通过有效 `postprocess_filter_scene_id` 引用滤镜模板。

三类场景都支持 `demo_input_media` / `demo_output_media`。AI绘图、AI滤镜的输入和输出都只能是 JPEG/PNG，点击场景后先以双图片 media group 展示；AI动图输入只能是 JPEG/PNG、输出只能是 MP4，点击后先以图片+视频 media group 展示。示范媒体必须先于上传素材的文字提示发送，单边缺失时允许只发送已有示范，不得阻断后续 FSM。媒体存入 R2 确定性 key `qqcc/demo/<scene_kind>/<scene_id>/<input|output>`，替换时覆盖写；配置保存 `content_sha256` 作为缓存版本。Telegram 发送成功后按 Bot ID 把 `file_id` 写入 `telegram_file_ids`，后续优先秒发缓存；缓存失效时回退 R2 短签并刷新，内容哈希变化时不得继承旧 file_id。

QQCC Config Web 每个场景操作区支持从已上传的 input 示范直接生成 output 示范。提交使用 `POST /api/qqcc/demo-generation/{scene_kind}`，前端再轮询 `GET /api/qqcc/demo-generation/{scene_kind}/{scene_id}/{generation_id}`；生成服务直接复用场景 engine、prompt、negative prompt、LoRA 和动图 duration 向 Central 提交，不进入用户 task facade，因此不扣灵石、不占用户并发、不写 History。终态产物写入场景目录下带 generation ID 的唯一 output 草稿 key，不覆盖当前已生效 output；前端只更新本地配置草稿，管理员仍须手动点击“保存”才让 Bot 配置引用新媒体。私有 Bot 使用 owner 对应的 `qqcc/private/<id>/demo` namespace，禁止跨租户输入对象。

示范媒体 object key 允许集合属于 Config Backend 与 QQCC Bot 的共享运行时契约。新增 `generated/.../output` 等 key 形状时，必须同轮更新 `qqcc-config-backend` 与 `qqcc-bot`；Bot 的 `cache_qqcc_demo_telegram_file_ids()` 会归一化并回写整份配置，若 Bot 仍使用旧 allowlist，会在成功缓存 input file_id 时静默删除它不认识的 output。回归测试必须覆盖“缓存任一槽位 file_id 后保留其它 generated media”。已经生成但引用丢失时，优先从 R2 场景目录按 generation 对象恢复最新 output 描述，不得重新消耗 GPU。

独立 QQCC Config Web 的底部“提示词覆盖”只展示 `快速换脸`（`prompts.face_swap`）。`快速自慰` / `快速脱衣` 和默认动图预设的提示词都在各自场景行里编辑，不能留空；后端仍保留 `prompts.undress` / `prompts.masturbation` / 旧动图 prompt 字段用于旧配置迁移兼容。

`修仙市集` 是 QQCC 专用轻量 Gallery 入口，代码在 `qqcc_bot/gallery_market.py`，callback 前缀为 `qg:`。它只允许浏览 Web 当前可见分组投稿、点赞/点踩、一键应用和 Web 应用跳转，不提供留言，不复用旧主 Bot gallery 分类常量，不注册主 Bot 完整 gallery handler。普通可应用投稿的卡片应同时展示 `一键应用` 与 `Web应用`；视频换脸类模板只展示 `Web应用`；Wan22/LTX 多段拼接结果不展示任何应用入口。Bot caption 中的类型和 `#task.mode_*` 标签必须走当前语言的 task/tab 翻译，不能直接暴露内部变量名。媒体发送必须优先复用 `GalleryPost.telegram_file_id`，缺失/失效时走当前 Gallery R2/S3 URL resolver 下载当前作品并刷新 file_id；测试 Bot 不持久化新 file_id。

QQCC 市集 Bot 原生应用只承接安全的单图轻量模板，提交任务必须传 `source_post_id`、`allow_contribute=False` 并保持 `client_type=bot:qqcc`；复杂多图/多视频、SCAIL-2、LTX 首尾帧等模板的 `一键应用` callback 只能做 Web handoff，并给出 `/gallery?apply_source=gallery&apply_id=<post_id>` 深链，不得在 Bot 内强行复用视频/多素材。点击应用不得预增 `applied_count`。

注册的 FSM 只能是 `get_quick_image_fsm_handler()` 与 `get_quick_video_fsm_handler()`。不得注册 `faceswap_fsm`、高级图像、高级视频、充值、affiliate redeem 或主 Bot 完整 gallery 浏览入口。

## 2.1 独立配置 Web
自由P图 v3 的稳定配置值为 `free_edit_v3`，可用于 AI绘图与 AI滤镜场景；它不支持 LoRA，单图提交独立任务 `pornmaster_flux2_edit_bf16`，固定计费 `6` 灵石。新增场景默认值继续保持 `free_edit_v2`，已有 v2 配置不得被自动迁移。

QQCC 懒人 Bot 配置已从主 Dashboard 剥离为独立 QQCC Config Web。主 Dashboard 不再挂载 `懒人Bot配置` 导航，也不挂载 `/api/qqcc/config`。独立后端入口是 `dashboard.backend.qqcc_config_main:app`，只启动 DB 初始化、独立 `QQCC_CONFIG_*` 账号认证、`/api/health` 和 `/api/qqcc/config`，不得启动 Dashboard worker listener、余额监控或 RunPod autoscaler。配置存入 `runtime_checkpoints`，固定 key 为 `qqcc_lazy_bot_config:v1`，不新增数据库表。API：
- `GET /api/qqcc/config` 返回合并默认值后的有效配置，并带非持久化 `options`，供前端渲染 `scene_preset_version`、默认 engine、engine 选项与 LoRA catalog；前端不得内置默认场景或模型清单作为事实源。
- `PUT /api/qqcc/config` 规范化保存配置，未知 key 必须丢弃。
- `PUT /api/qqcc/demo-media-json/{scene_kind}/{scene_id}/{slot}` 以 Base64 JSON 上传示范媒体，规避 Cloudflare 对 multipart 文件请求的边缘拦截；旧 `/demo-media/...` POST/PUT 仅保留兼容。后端解码后仍统一校验场景/槽位对应媒体类型、文件签名与大小，并写入确定性 R2 key。

独立账号 env：
- `QQCC_CONFIG_ADMIN_USERNAME`
- `QQCC_CONFIG_ADMIN_PASSWORD_HASH`
- `QQCC_CONFIG_SECRET_KEY`

配置结构固定包含：
- `scene_preset_version`: 当前为 `1`；缺失或小于 `1` 视为旧配置，保存时一次性补齐 QQCC 绘图/动图预设并迁移旧 prompt override；已有 `scene_preset_version>=1` 时尊重管理员删除后的空 `draw_scenes` / `video_scenes`
- `global_enabled`
- `main_buttons`: `quick_undress`, `quick_faceswap`, `photo_edit`, `ai_draw`, `ai_filter`, `video_edit`, `market`, `main_bot_link`, `private_bot`；`quick_undress` 与 `photo_edit` 仅保留旧配置兼容，QQCC 主菜单不再渲染；`private_bot` 只控制官方 QQCC 的申请/管理入口，默认开启且不跟随 `global_enabled`
- `main_menu_layout`: `{ buttons_per_row, button_order }`；`buttons_per_row=null` 时必须原样保留旧固定分行，只接受整数 `1..4` 启用统一分行。`button_order` 只允许 `quick_faceswap` / `ai_draw` / `ai_filter` / `video_edit` / `ai_video` / `market` / `private_bot` / `main_bot_link`，未知、重复与旧兼容 key 丢弃，缺失 key 按默认顺序追加。运行时必须先按开关/gate/场景/官方与私有上下文过滤，再按顺序分行；隐藏项不占位但保留配置位置。官方 checkpoint 与每个私有 Bot JSON 独立保存，不新增表
- `photo_buttons`: `masturbation`, `random_faceswap`；仅保留旧配置兼容
- `undress_methods`: `legacy`, `i2i_draw`；仅保留旧配置兼容
- `video_scenes`: `[{ id, name, prompt, negative_prompt, duration, engine, aspect_ratio, lora_items, lora_name, lora_strength, end_frame_draw_scene_id, next_scene_id }]`；`ai_video_scenes` 同样支持 `next_scene_id`。引用只能指向同数组场景，空值终止；配置 PUT 拒绝缺失目标、自环和任意间接循环，旧失效引用读取时清空。运行时迭代快照完整链，无业务深度上限；每段用上一段 `extra_outputs.last_frame` 作为首帧，最终按第一段画布居中裁剪并拼接。`aspect_ratio` 只允许 `source / 9:16 / 16:9 / 1:1`，缺失、空值或非法值归一为 `source`，无需提高 preset version；`lora_items` 是最多 5 个有序 `{name,strength}`。候选只展示 `wan22_explicit_lora_library/2026-07-18` 已下载并成对核验的 49 项，稳定键、中文标签、High/Low 路径和单滑杆保守推荐值来自 `src/wan22_explicit_lora_catalog.py`；强度按 `0.1..2.0`、步长 `0.05` 归一。旧七模型键自动迁移到对应新条目，保存继续镜像首项用于滚动兼容。
- `draw_scenes`: `[{ id, name, prompt, negative_prompt, engine, lora_name, postprocess_draw_scene_id, postprocess_filter_scene_id, original_face_swap_enabled }]`；所有场景 `prompt` 必填，`negative_prompt` 可选，缺失或非字符串归一为空，字符串保存前 trim；不设置应用层数量上限，前端 PUT 与后端归一化必须保留全部有效场景；`engine` 只能是 `free_edit` 或 `free_edit_v2`，缺省 `free_edit_v2`；`lora_name` 只允许在 `free_edit` 下来自 `IMAGE_LORA_MODELS`，v2 自动清空；`postprocess_draw_scene_id` 缺省 `""`，只能引用其它有效绘图场景，非法、自引用或循环引用必须清空；`postprocess_filter_scene_id` 缺省 `""`，只能引用有效 `filter_scenes[].id` 并作为终止后处理，若绘图和滤镜后处理同时有效则保留绘图后处理；`original_face_swap_enabled` 只能为布尔值 `true`，缺失或非法归一为 `false`；`id` 只能用于短安全 callback
- `filter_scenes`: `[{ id, name, prompt, negative_prompt, engine, lora_name, original_face_swap_enabled }]`；所有场景 `prompt` 必填，`negative_prompt` 可选，最多 20 个，engine/LoRA/原图换脸归一规则与 AI绘图一致；自身不支持后处理链，默认配置不种子化任何滤镜场景
- 三类 scene 可选字段 `demo_input_media` / `demo_output_media` 结构为 `{ object_key, media_type, mime_type, file_name, content_sha256, telegram_file_ids }`；`preview_url` 只在配置 GET/上传响应临时生成，不持久化。前端普通保存必须按相同 `content_sha256` 合并较新的 Bot file_id 缓存，替换内容时清空缓存。
- `video_buttons` 与 `video_settings` 仅保留旧配置兼容；AI 动图后台页面不再编辑画质或全局时长
- `prompts`: `undress`, `i2i_draw_quick_undress`, `masturbation`, `face_swap`, `perfect_video_insert`, `doggy_style`, `blowjob`, `undress_tongue`, `closeup_blowjob`

`video_scenes`、`draw_scenes`、`filter_scenes` 的数组顺序就是 QQCC Bot 对应二级场景菜单的展示顺序。独立配置 Web 将三类场景收拢到 AI动图/AI绘图/AI滤镜三个 Tab，每类独立按每页 5 条分页；分页只限制当前渲染行，保存仍必须提交完整数组。每行提供上移/下移操作并通过现有整份配置 PUT 保存新顺序；移动只交换数组位置，必须保留场景 `id` 和所有跨场景引用。首行上移、末行下移应禁用，新增、删除和跨页移动后必须把当前页校正到包含目标行的有效页。

关闭功能后，新菜单必须隐藏对应按钮；旧 reply keyboard / 旧 callback 必须回复 `功能暂未开放` 并拒绝提交任务。`quick_faceswap` 关闭后，旧 `random_faceswap_again` 也必须拒绝继续提交。AI 动图时长由场景配置固定，用户在 Bot 中只选择画质；画质只受用户权限过滤，仍保持 `1024p` 和 `10s` 互斥。QQCC draw/filter/video 场景正负提示词只来自场景自身 `prompt` / `negative_prompt`，只作用 QQCC，主 Bot 继续走原提示词。无尾帧来源时，动图 `image_to_video` 无模型提交 `custom_video`，带模型提交 `video_lora` 并透传 `lora_name`；动图 `wan22_video_v2` 提交 `wan22_video_v2`，使用视频场景提示词、负面提示词、固定时长和用户画质，负面提示词为空时保持 Wan22 现有默认负向归一。有尾帧来源时，用户仍只发 1 张图；Bot 先按引用 AI绘图场景的完整后处理链串行执行隐藏绘图任务，每步使用该绘图或滤镜场景自己的 `negative_prompt`，链上任何开启 `original_face_swap_enabled` 的步骤都必须插入 draw/filter -> 原图换脸，再把换脸后图片传给下一步，下载最终图作为尾帧后再提交首尾帧视频；最终视频仍只使用视频场景自己的 `negative_prompt`。旧图生视频传两张图并写 `use_end_frame=true`，v2 传 `images=[start,end]`；提交前按绘图链、每步原图换脸和视频做合计额度预检，任一尾帧绘图/换脸失败都不提交视频。上述 AI动图提交计划与执行 payload 的事实源是 `src/services/quick_video_submission_service.py`，FSM 只负责 Telegram 状态、额度检查和回复。QQCC AI绘图、AI滤镜与随机换脸提交计划的事实源是 `src/services/quick_image_submission_service.py`，`quick_image_fsm.py` 只负责 Telegram 状态、图片接收、额度检查和回复。QQCC 链式生成只允许第一个真实子任务按普通规则排队并在 pending 时可取消；第 2 个及以后子任务，包括 AI绘图后处理、`original_face_swap_enabled` 插入的内部换脸、AI动图尾帧链后续步骤和尾帧完成后的最终视频，都必须作为 continuation 提交：`base_priority=100`、不展示取消按钮、active task registry 写入 `user_cancel_allowed=false`，用户取消入口返回 `not_cancellable` 且不得触发 Central cancel 或退款。单任务快速换脸、无尾帧 AI动图、单步 AI绘图和单步 AI滤镜保持普通可取消。`free_edit_v2` 提交 `pornmaster_flux2_single_edit`，`free_edit` 无模型提交 `edit`，带模型提交 `img2img_lora` 并透传 catalog 默认强度；绘图/滤镜任务透传每步自身 `negative_prompt`，为空时保持空负向。QQCC 直接生成链路中，快速换脸、AI绘图、AI滤镜和 AI动图最终可见结果都提交 `allow_contribute=false`，结果按钮不展示投稿或公开入口；旧消息上的 `submit_gallery_*` / `public_share*` 在 QQCC callback 入口回复 `功能暂未开放`。最终可见结果的完成文案必须使用 QQCC 实际功能名或场景名，不使用嵌套链路最后一个底层任务名；直接 AI滤镜显示滤镜场景名，AI绘图套滤镜后处理的最终结果仍显示原 AI绘图场景名。结果 metadata 通过 `_qqcc_regenerate` 写入 History `extra_outputs`，展示层据此追加 `qqcc_regenerate:<task_id>` 的 `重新生成` 按钮；metadata 新增 `scene_kind=draw|filter`，旧历史缺失时按 `draw` 兼容。QQCC 重生成 callback 必须校验本人历史、下载原始用户输入、按当前配置重建 quick image/video 提交计划并重新做额度检查；若场景被禁用、删除或历史缺少原图，回复明确失败，不进入 worker。中间绘图、原图换脸和视频尾帧链路也均隐藏且不可投稿。关闭 `main_buttons.ai_draw` 只隐藏直接入口，不影响动图内部引用有效 `draw_scenes` 生成尾帧；关闭 `main_buttons.ai_filter` 只隐藏直接 AI滤镜入口，不影响 AI绘图引用有效滤镜模板。

链式任务的排队展示与取消权限是两条独立契约。第一个真实子任务保持 `show_queue_status=true`；第 2 个及以后子任务（AI绘图后处理、内部原图换脸、AI动图/AI视频尾帧链及最终 Wan22/旧视频/LTX）必须传 `show_queue_status=false`。Bot 从 continuation 提交起持续复用现有图片/视频“生成中”文案，Central 返回 pending 或队列位置变化时也不得回退为排队或重新出现取消按钮；成功、失败、拒绝、退款和最终结果仍按真实终态展示。该参数默认 `true`，不得改变优先级、计费、退款、任务顺序或 Worker 协议。

### QQCC AI动图输入比例边界

`video_scenes[].aspect_ratio` 只作用 QQCC `AI动图`。`source` 原样直通；其它值由 `src/services/qqcc_video_frame_adapter.py` 在提交前做 JPEG/PNG 校验、EXIF 方向归一和最大内接精确整数比例居中裁剪，不拉伸、不补边、不扩图、不主动放大。单首帧旧/v2 提交适配后的首图；尾帧链先用适配首图绘制，再适配最终尾图。私有 durable continuation 将比例保存为 QQCC 内部 stage 参数，在最终 executor 对 `original/current` 应用后必须剥离；后台示例生成在上传 Central 临时输入前适配 R2 bytes。适配失败必须清理 FSM 临时文件、提示图片处理失败，并在调用任务入口和扣费前停止。

QQCC 视频模板串联属于 Bot 编排层，不是 Comfy workflow 嵌套或比例开关。全链费用在首段提交前汇总；第一段沿用普通队列/取消，后续段固定 continuation 优先级且不可单独取消。官方 Bot 在内存中收集已完成段并生成最终 History；私有 Bot checkpoint 保存场景快照、当前首帧和各段视频引用，最终 `delivery_pending` 拼接后投递。后续段失败时官方 Bot 返回已成功前缀，失败任务沿用现有退款幂等；拼接本身不扣费。后台示例用 24 小时 Redis checkpoint 执行同一完整链。

链式视频媒体处理的运行时依赖必须落在真实消费者镜像，不得只修改已退出模块化发布路径的 legacy Dockerfile。`qqcc-bot`、`private-bot-worker`、`qqcc-config-backend`、`dashboard-backend` 统一继承 `python-media-runtime-base`，full-validation 必须分别在四个最终 digest 中执行 `ffmpeg -version` 与 `ffprobe -version`。尾帧处理发生在某段成功之后；此处失败应提示“该段已生成，但尾帧处理失败”，不得误报为该段生成失败，也不得改变成功段计费或失败任务退款语义。

这不是 Comfy workflow 比例开关。不得修改主 Bot、固定 `1280x704` 的 `AI视频`、`Wan22AioV82.json`、workflow mapping、worker patcher、模型 profile、RunPod/LAN AIO、画质档位或计费；比例字段不得进入 Central/Worker payload。重新生成及 AI绘图结果的“生成动图”必须从当前场景重建同一 Quick Video plan，自然读取最新比例。

## 3. 任务归属红线
QQCC Bot 必须设置 `application.bot_data["bot_client_type"] = "bot:qqcc"`，Bot 任务提交必须透传该值到 `process_and_submit_task(client_type=...)` 并写入 active task registry。
`bot:qqcc` 常量、QQCC 上下文判断和按上下文加载运行时配置的通用逻辑集中在 `src/services/qqcc_runtime_context.py`；quick image/video FSM 与 callback helper 不要各自复制同一段判断/兜底加载逻辑。

恢复规则：
- 主 Bot 恢复 `bot` 和 legacy 任务。
- QQCC Bot 只恢复 `bot:qqcc` 任务。
- 私有 Bot 只恢复 `bot:qqcc-private:<private_bot_id>` exact match；worker 启动扫描不得把官方或其它租户任务交给当前 Application。

私有 Bot active registry 会在 `_bot_task_recovery` 中持久化结果展示契约，并通过 `_private_qqcc_continuation` 关联 Redis durable checkpoint。多步 `draw -> draw/filter`、`original_face_swap_enabled` 插入链和 AI动图尾帧链均可在私有实例执行：新原脸恢复 stage 必须写 `task_type=face_swap_v2`；恢复升级前 checkpoint 时，仅在私有 QQCC continuation 内把该 stage 的旧 `face_swap` 解释成 V2，不能影响快速/随机换脸。用户原始输入必须先上传持久存储，再创建包含完整 JSON stage plan、确定性 submission sequence/registry ID、当前输出和阶段状态的 checkpoint；阶段结果必须先 CAS 持久化再清理 active registry。最终可见阶段不得在 checkpoint 前直接发送，而要先进入 `delivery_pending`，由续跑租约 owner 发送后 CAS 标记 delivered；Telegram 自身没有幂等键，因此仍只允许 send 成功到 delivered CAS 之间的最小重复窗口。worker 启动及周期恢复即使 TaskRegistry 为空也要扫描 ready/delivery checkpoint；旧执行租约丢失会取消旧 owner，running orphan 仅在旧续跑锁失效后 rewind。owner/admin 暂停或禁用只阻止新 update，已接纳链可继续；永久解绑后停止。旧私有 active task 缺 recovery contract，或隐藏中间任务缺有效 continuation ref 时，仍只能拒绝发送半成品。

暂停/禁用后若租户 Application 仍挂有已扣费 monitor/continuation `bg_tasks`，后续 inactive update 不得触发 stop/shutdown，必须等后台投递结束后再按 idle TTL 回收。全局错误提示自身发送失败要把 private admission 标记为 failed，禁止 webhook entry 被误 ACK；通用或手工 `clean_zombies()` 必须跳过全部 private client type，私有僵尸任务只走 tenant-aware cleaner。

不得让 QQCC Bot 恢复或通知主 Bot 的任务，也不得让主 Bot 抢恢复 QQCC 任务。

私有 Bot 公开访客仍使用自己的 `internal_user_id`、余额、会员与并发权限；owner 只拥有配置和启停权限，不替访客付费。不同租户必须注入独立配置 loader、private ID 与 client type，示范媒体限定 `qqcc/private/<id>/demo/...`。

频道会员检查不得改用租户 Bot。private worker 按 `BOT_TYPE` 用 `QQCC_BOT_TOKEN` / `QQCC_BOT_TOKEN_TEST` 构造一个进程共享的官方 QQCC checker，只做频道成员查询、不启动 polling；租户只注入 callable，进程内按用户 singleflight，Redis 在租户间共享正向 60 秒、负向 5 秒缓存。

## 4. 部署与密钥
官方 QQCC token 只允许放在 ignored env 文件：
- 正式：`QQCC_BOT_TOKEN`
- 测试：`QQCC_BOT_TOKEN_TEST`
- 可选主 Bot 跳转：`QQCC_MAIN_BOT_URL` 或 `QQCC_MAIN_BOT_USERNAME`
- 主 Bot 跳转 QQCC：`QQCC_LAZY_BOT_ENABLED` 控制是否显示/解析入口，URL 使用 `QQCC_LAZY_BOT_URL` 或 `QQCC_LAZY_BOT_USERNAME`

官方 QQCC 服务用对应 token polling；private worker 只用同一个环境对应 token 做统一频道会员检查，绝不能由此启动第二个 polling。用户私有 token 仍逐租户从数据库解密。

用户私有 Bot token 不进入 compose env：数据库只保存版本化 AES-GCM ciphertext、key version 与 HMAC 指纹；管理员永远不能读取明文。运行环境必须通过 ignored env/secret store 提供 `PRIVATE_QQCC_BOT_TOKEN_KEYRING`、`PRIVATE_QQCC_BOT_TOKEN_ACTIVE_KEY_VERSION`、`PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY`、`PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS`、`PRIVATE_QQCC_BOT_OWNER_JWT_SECRET`、`PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL`、`PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL`、`PRIVATE_QQCC_BOT_OWNER_HOST` 与 `QQCC_CONFIG_ADMIN_HOST`。AES/JWT/fingerprint 必须是独立 32-byte Base64URL key，owner JWT 也不得复用 QQCC/主 JWT/Dashboard secret；用 `scripts/validate_private_qqcc_bot_env.py` 做发布前检查。forbidden ID 列表缺失/非法必须 fail closed，管理后端不得通过接收官方 token 来替代显式 ID 列表。官方 QQCC 容器必须同时注入 owner WebApp URL 与 owner Host，ticket 只追加到 URL fragment。

同一 `telegram_bot_id` 的新 token 即使存在已扣费/active task 也必须允许救援轮换；轮换先在 admission fence 内进入 `provisioning`，worker 按指纹关闭旧 Application 并重建。不同 Bot ID 不是轮换，必须管理员永久解绑；永久解绑仍等待 active task 清空。管理员禁用不得被轮换清除。

私有 token 的 Bot API 传输必须使用 `PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL` / `PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL` 独立 HTTPS 契约，默认官方 `api.telegram.org`。不得继承现有公网 HTTP Local Bot API，因为 token 位于 URL path；自建 HTTPS 端点只能通过 `PRIVATE_QQCC_BOT_TELEGRAM_TRUSTED_HOSTS` 明确允许。Owner/Admin/unknown Host 分别由 Nginx 显式匹配并由 backend 再校验，unknown/跨 Host API 必须 404，不能依赖 Tunnel 的 source IP allowlist 做管理员隔离。owner 页 CSP 的 `connect-src` 只能 `'self'`，仅 `frame-ancestors` 允许 Telegram WebView，且不发送 XFO；admin/unknown 仍使用 `DENY` + `frame-ancestors 'none'`。owner ticket exchange 使用独立 `50r/s`、`burst=500` limiter，不复用 admin login 的 `2r/s`、`burst=5` 窄桶。

私有 Bot 使用 `qqcc-private-bots` profile 的独立 worker，不使用 long polling。worker 内存必须保持全局 inflight、单 Bot prefetch、deferred ID 三层有界（默认 `64/8/1024`）；启动先完整追平旧 PEL，catch-up 完成前不读新 `>` update。Webhook counters 与 worker heartbeat 通过管理员 metrics API 暴露，不得加入 token/update JSON/高基数敏感标签。

`private-bot-worker` 薄镜像必须同时包含 `qqcc_private_bot/` 与 `qqcc_bot/`：worker 复用 `qqcc_bot.main.build_application` 创建租户 Application。`deploy/release-artifacts-v2.json` 的同名 artifact inputs 也必须覆盖两者，避免官方 Application factory 变化后漏建镜像。

`PRIVATE_QQCC_BOT_ENABLED` 是总 gate。safe deploy 使用 validator `--allow-disabled`，gate 缺失/`false` 时 activation secrets 非必填；gate=`true` 时 validator 必须严格校验全部 activation secrets 和环境对应官方 QQCC token，worker 在 gate 非真时拒绝启动。2026-07-12 云正式已完成 migration、启用 gate、启动 private worker，并上线生产 webhook 与 owner public Host；后续关闭、迁移、密钥轮换或 Cloudflare mutation仍需明确生产确认。worker 镜像使用 Python 3.10，所有 `asyncio.wait_for(...)` 周期循环必须捕获 `asyncio.TimeoutError`，不能用裸 `TimeoutError`，否则 heartbeat/sweeper 会在首次 timeout 后退出。

不得把真实 token 写入仓库、docs、日志、工单或聊天记录。QQCC Bot 不启动 TON 轮询，不注册支付回调，不作为充值入口。测试环境没有独立 token 时，`qqcc-bot-test` 必须保持停止。

主 Bot 跳转按钮优先使用 `QQCC_MAIN_BOT_URL`，未配置时可用 `QQCC_MAIN_BOT_USERNAME` 自动生成 `https://t.me/<username>`；两者均未配置时不得硬编码主 Bot 地址。菜单项是否展示只受 QQCC `main_bot_link` 配置控制，用户点击后应回复“主 Bot 入口暂未配置”类提示，而不是提交生成任务。

主业务 Bot 的 `懒人bot` 菜单入口缺省显示；`QQCC_LAZY_BOT_ENABLED=false` 时隐藏新菜单并让旧文本/旧 callback fail closed。入口可用时优先读取 `QQCC_LAZY_BOT_URL`，未配置时可用 `QQCC_LAZY_BOT_USERNAME` 自动生成 `https://t.me/<username>`；两者均未配置时保留菜单但只提示“懒人bot入口暂未配置”，不得硬编码 QQCC Bot 地址。2026-07-12 正式环境按用户要求采用“菜单可见、URL/username 未配置”的不可跳转状态。主 Bot 的 `图片换脸` 二级菜单只保留 `快速换脸` 与 `随机换脸`；旧 `快速脱衣`、`快速自慰`、旧 `menu.video_edit_*`、旧 `AI绘图` / `AI滤镜` / `AI动图` / `快速换脸` 文本和主 Bot 上的 `qvid_*` callback 必须回复 QQCC 懒人 Bot inline URL 跳转或入口未配置提示，且不得提交任务。QQCC 的 `qdraw_scene:*`、`qfilter_scene:*`、`qvid_scene:*` 和旧 `qvid_mode:*` 兼容不受影响。

正式启动或重建前必须有用户明确要求进入 QQCC 正式发布。日常先运行 `release.py promote --modules qqcc-bot` 查看无 mutation 预览，确认后只增加一次 `--confirm-prod`；用户同时明确决定跳过 Bot 默认生成维护时，operator 使用 `--no-maintenance` 记录该决定并直接 rolling，不再追加确认。该选项不能豁免 migration、首次切换、共享 Compose/env、blocker、未知契约或异常 polling 门禁，失败补偿仍可启用维护。发布器从 Bot 自己的正式 digest/source/config revision 计算变化与回滚，只选择目标服务，并在启动窗口内核对唯一目标容器、已知 legacy 实例停止和 Telegram polling conflict。目标配置缺失或漂移会在 pull/up 前阻断，发布器不得自动暂存；只有用户另行要求配置收敛时才用 `config-plan/config-apply --module qqcc-bot`。

只更新独立 QQCC 配置 Web 时用 `release.py promote --modules qqcc-config`；发布器固定展开 backend/frontend 两个 artifact。需要同步更新官方 Bot 时可一次选择 `qqcc-bot,qqcc-config`，配置闭包取并集、blocker 按两个模块分别匹配，事务与失败回滚保持原子。Bot 与配置平台存在共享契约变化时 `promote` 直接阻断；唯一例外是 `deploy/release-policy.yml` 中内容 SHA256 精确固定的已审计 snapshot。当前 QQCC 后台独占 LTX 目录只在 `src/qqcc_ltx_lora_catalog.py` 与 `src/services/qqcc_config_service.py` 两份 snapshot 内容完全匹配时允许独立晋级，任一文件后续变化立即重新 fail closed，禁止复用旧哈希。QQCC Config 是 standard artifact，必须具有 main-channel exact-digest 测试证据；Dashboard 仍固定 direct/waived。维护模式遵循 `allbot-ops-deployment`。不得使用已 fail-closed 的 legacy 脚本，也不得 rsync、现场 build 或手工 compose；正式发布后只验证目标 8045/8088、QQCC Bot single polling、必要共享依赖及 AllBot 非目标容器不变。

## 5. 验证要求
至少覆盖：
- 主业务 Bot 主菜单展示 `懒人bot`、`图片换脸`、`视频生视频`，不展示旧 `修仙市集` 或 `视频创作`；点击 `懒人bot` 或旧 `修仙市集` 文本回复前往 QQCC 的 inline URL 按钮。
- 主业务 Bot `图片换脸` 二级菜单只展示 `快速换脸`、`随机换脸` 和返回主菜单；旧 `快速脱衣`、`快速自慰`、旧动图文本入口、旧 `AI绘图` / `AI滤镜` / `AI动图` / `快速换脸` 文本和主 Bot 上的 `qvid_*` callback 回复前往 QQCC 懒人 Bot inline URL 按钮或入口未配置提示，且不提交任务。
- 官方 QQCC `/start` 只返回简化主菜单，默认包含 `快速换脸`、`AI绘图`、`AI动图`、`修仙市集`、`前往主bot` 与 `私有bot`，不包含旧 `快速脱衣`、`懒人P图` 或空场景 `AI滤镜`；管理后台关闭 `main_buttons.private_bot` 后官方菜单隐藏该入口且旧入口拒绝申请，私有实例始终隐藏 `私有bot`。管理员配置有效滤镜场景后，功能行顺序为 `AI绘图` / `AI滤镜` / `AI动图`。
- QQCC `/start` 不额外发送主 Bot 跳转消息；配置主 Bot 跳转 env 时，点击菜单里的 `前往主bot` 后回复 inline URL 跳转按钮。
- 点击主菜单 `快速换脸` 直接进入现有单图随机换脸流程，发送 1 张正脸图后自动匹配模板；不注册或调用 `faceswap_fsm`。
- QQCC 快速换脸继续提交 `face_swap` V1、扣 1 灵石且不读取场景价格；AI绘图/AI滤镜的 `original_face_swap_enabled` 内部原脸恢复提交 `face_swap_v2`。根场景 `credit_cost=null` 时每个启用步骤额外 2 灵石；配置固定总价后内部换脸包含在根价内，最终 History/文案仍按原场景显示。
- 四类场景的 `credit_cost` 只允许 `null` 或大于等于 1 的整数；缺失按 `null` 兼容。固定价只读取用户点击的根场景，不叠加后处理、尾帧或 `next_scene_id` 子场景价格；首个真实任务 `cost_override=credit_cost`，后续任务 `deduct_quota=false`。后续阶段或最终投递失败按根价全额幂等退款；私有 continuation 必须持久化计费锚点并防重扣/重退。新增场景默认价只能读配置 options：AI动图 6、AI视频 10、AI绘图/滤镜 2。
- 旧 `快速脱衣`、旧 `懒人P图` 与旧 P 图子按钮回复 `功能暂未开放` 且不提交任务。
- `AI绘图` 点击后，默认迁移配置会回复 `快速自慰`、`快速脱衣` 两个 inline 场景按钮，三个一行；管理员删除预设后旧 callback 回复 `功能暂未开放`。点击 `qdraw_scene:<id>` 不转圈并进入 quick image 发送图片步骤，发 1 张图片后按场景 engine、场景 `prompt` / `negative_prompt`、`postprocess_draw_scene_id` 或终止 `postprocess_filter_scene_id` 链提交 `pornmaster_flux2_single_edit` / `edit` / `img2img_lora`；中间绘图隐藏且不可投稿，最终只发送链路最后一张图。删除/禁用后的 callback 回复 `功能暂未开放` 且不提交任务。
- `AI滤镜` 默认无场景时不展示；配置有效 `filter_scenes` 后点击主菜单会回复滤镜 inline 场景按钮。点击 `qfilter_scene:<id>` 不转圈并进入 quick image 发送图片步骤，发 1 张图片后按单步滤镜场景提交；场景删除、禁用或主开关关闭后回复 `功能暂未开放` 且不提交任务。
- `AI动图` 点击后回复 inline 场景按钮，三个一行，默认包含兼容迁移的五个懒人动图场景；后台改为自定义场景后 Bot 展示自定义按钮名。点击 `qvid_scene:<id>` 不转圈并进入 quick video 发送图片步骤；旧 `qvid_mode:*` 已发按钮兼容到对应场景，场景删除后回复 `功能暂未开放`。
- `AI视频` 默认场景为空且不展示；配置有效 `ai_video_scenes` 且开启 `main_buttons.ai_video` 后，入口紧随 `AI动图`。`qaivid_scene:<id>` 复用 quick video FSM，用户只上传一张图；固定以 `ltx_video`、`1280x704`、场景时长和最多 3 个 `{path,strength}` LoRA 提交。无尾帧时 I2V，有尾帧引用时完整执行绘图链后 FLF2V；空负面提示词必须省略以保留 workflow 默认。QQCC 控制面可独立复用现有 LTX GPU runtime，不能因该入口发布去重建 GPU 容器或创建 RunPod canary；非空 LTX 负面提示词在 Worker mapping 独立发布验收前不得宣称已生效。
- `AI视频` 的后台专用 LoRA 目录位于 `src/qqcc_ltx_lora_catalog.py`，只允许 `qqcc_config_service` 用于认证配置页选项、保存白名单和推荐强度；主 Bot 与公共 Web 继续只读公开 `src/lora_catalog.py`。专用目录当前覆盖本机 2026-07-17 校验库 32 项（26 项为公开目录外新增）。代码接入不代表目标 GPU 已有权重；RunPod/LAN AIO manifest 同步与 smoke 必须作为独立 GPU 发布处理。
- `修仙市集` 点击后展示 QQCC 专用类型菜单；投稿浏览支持点赞、点踩、分页、分类返回，普通可应用投稿同时展示一键应用与 Web 应用，视频换脸仅展示 Web 应用，拼接视频不展示应用入口，且不展示留言入口。
- `修仙市集` 已缓存媒体优先用 Telegram file_id，file_id 失效后通过当前 R2/S3 URL resolver 刷新，不走旧 legacy MinIO bytes 主路径。
- `修仙市集` Bot 原生应用必须传 `source_post_id` 且 `allow_contribute=False`，复杂模板的一键应用必须 Web handoff，点击应用不直接增加 `applied_count`。
- QQCC 自己生成的快速换脸、AI绘图、AI滤镜和 AI动图结果不得投稿或公开；新结果不展示 `submit_gallery_*` / `public_share_request` 按钮，旧结果按钮也必须在 QQCC callback 入口拒绝。结果完成文案必须显示 `快速换脸` 或选中的 QQCC 绘图/滤镜/动图场景名，结果按钮必须展示 `重新生成` 并能从本人历史重建同一功能提交。
- QQCC 链式生成只有第一个真实子任务可显示 pending 队列并取消；后续 continuation 任务必须 `base_priority=100`、`show_queue_status=false`、不展示取消按钮、`user_cancel_allowed=false`，pending/running 都持续显示现有“生成中”；用户取消旧按钮时返回不可取消，不调用 Central cancel，不退款，终态仍真实展示。
- QQCC main 只注册 quick image/video FSM；`快速换脸`、`AI绘图` 和 `AI滤镜` 都必须复用 quick image FSM，不注册主 Bot `faceswap_fsm` 或 `edit_image_fsm`。
- `bot:qqcc` 能进入 task submission、active registry 和 recovery filter。
- 私有 Bot 单任务重启恢复会还原原始结果展示 contract；私有多阶段绘图/原图换脸/尾帧视频必须通过 durable continuation checkpoint 跨重启续跑，结果先落 checkpoint，最终投递后再标记 delivered，不能发送半成品。
- 私有 Bot 同 ID token 在 active task 存在时可救援轮换，管理员禁用不被清除；不同 ID 必须管理员永久解绑，且 active task 未清空时解绑失败。
- private worker 的官方 QQCC membership checker 只做频道成员查询、无 polling，并覆盖正/负缓存与并发 singleflight；租户 Bot 不得被用于官方频道资格判断。
- worker 覆盖全局 inflight/单 Bot prefetch/deferred ID 上限、单 Bot顺序、startup PEL catch-up barrier、inflight ID 防重复，以及 admin metrics 的 backlog/pending/counters/heartbeat。
- gate=`false`/缺失配合 `--allow-disabled` 不要求 activation secrets且 worker 不启动；gate=`true` 必须严格校验环境对应官方 token、密钥、HTTPS 与 Host 契约。
- 默认配置下现有菜单不变；关闭配置后按钮隐藏，旧按钮/旧 callback 回复 `功能暂未开放` 且不提交任务。
- 主菜单布局覆盖无布局字段时的旧分行不变、`1..4` 统一分行、任意排序、隐藏项先过滤且重新开启恢复位置、私有 Bot 去除 `private_bot` 后无空位、生成全局关闭时仍按顺序保留独立入口，以及全部隐藏后的主菜单兜底。
- QQCC 动图动态场景按 engine 提交：旧 `image_to_video` 无 LoRA 为 `custom_video`、带 LoRA 为 `video_lora`，`wan22_video_v2` 为 `wan22_video_v2`；两者都把最多 5 个有序 `{name,strength}` 透传到 Wan22 高/低噪 LoRA 槽。配置尾帧来源时同一列表必须进入官方、私有 durable continuation 与最终视频任务。场景提示词、展示名与多选 UI 只作用 QQCC，不给主 Bot 增加入口。
- QQCC AI视频结果只展示场景名与 `重新生成`，不得展示 LTX 扩展/拼接按钮；重生成必须读取最新 `ai_video_scenes` 并重新核费。私有 Bot 尾帧链用 durable continuation 的 `ltx_video` executor 保存原图、当前尾帧和阶段状态后续跑。
- 主 Dashboard 不再出现 `懒人Bot配置` 导航；独立 QQCC Config Web 登录、加载、开关切换和保存 payload 有前端测试。
- compose/script 语法检查通过。
