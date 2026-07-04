# 子模块: QQCC 懒人 Bot (QQCC Lazy Bot)

## 1. 范围与定位
QQCC 懒人 Bot 是主业务 Bot 的独立 Telegram polling 入口，代码位于仓库根目录 `qqcc_bot/`，正式名称为 `@QQCC666_bot`。它提供简化生成入口与 QQCC 专用轻量 `修仙市集`，用户、灵石、会员、历史、并发锁、队列、对象存储、worker 与结果回流全部复用现有生产数据和任务链路。主业务 Bot 底部的旧 `修仙市集` 入口已改为 `懒人bot` 跳转，目标由 `QQCC_LAZY_BOT_URL` 或 `QQCC_LAZY_BOT_USERNAME` 配置。

它不是主 Bot 的完整副本，不承载充值、affiliate 菜单、主 Bot 完整 gallery 浏览、Web 登录、支付回调或高级视频/高级图像入口。

主菜单可额外展示两个非生成入口：`修仙市集` 与 `前往主bot`。`修仙市集` 是 QQCC 专用轻量 Gallery 浏览/应用入口；`前往主bot` 用于把用户引回完整主 Bot。Telegram 底部菜单按钮不能直接承载 URL，因此用户点击 `前往主bot` 后，QQCC Bot 会回复一条带 inline URL 的跳转按钮。这两个入口不是生成业务入口，不改变“主菜单业务入口只来自 QQCC 配置”的约束。

## 2. 功能边界
主菜单业务入口只包含：
- `快速换脸`
- `AI绘图`
- `AI动图`

`AI动图` 是 QQCC Bot 的专用展示文案，对应共享兼容路由 `menu.video_edit`。不要直接修改共享 `menu.video_edit` 文案来实现 QQCC 菜单改名，否则会影响旧按钮兼容和 QQCC 动图路由。

`快速换脸` 是 QQCC Bot 的专用主菜单文案，对应 `qqcc.menu.quick_faceswap`，复用现有单图随机换脸流程，发送 1 张正脸图后自动匹配模板；它不是主 Bot 的双图 `faceswap_fsm`。

`AI绘图` 是 QQCC Bot 的专用展示文案，对应 `qqcc.menu.ai_draw` 专用路由。旧配置首次归一化时会通过 `scene_preset_version=1` 一次性种子化两个预设 `draw_scenes`：`快速自慰` 与 `快速脱衣`；种子化后它们和自定义场景没有结构差异，可编辑、删除、调整模型和后处理。关闭直接入口通过 `main_buttons.ai_draw=false`；管理员也可以清空 `draw_scenes` 删除所有直接 AI绘图场景。默认功能行按 `AI绘图 / AI动图` 排列。

主菜单非生成入口：
- `修仙市集`
- `前往主bot`

旧 `快速脱衣` 主菜单、旧 `懒人P图` 主菜单、旧 P 图子按钮和旧快速脱衣二级方式均不再作为 QQCC 用户入口。用户点到旧 reply keyboard 或旧 callback 时必须回复 `功能暂未开放`，不得提交任务。

`AI动图` 场景由管理后台动态配置。默认配置兼容旧五个懒人动图场景：
- 传教士
- 后入
- 口交
- 脱衣吐舌
- 近景口交

后台可增删场景、调整按钮名称、提示词、固定时长、底层模型和可选尾帧来源。旧五个默认动图也只是一次性种子化的普通预设，保存后与自定义场景一致。默认 engine 是旧 `image_to_video`，可选视频 LoRA；切到 `wan22_video_v2` 时不支持附加模型并自动清空 `lora_name`。尾帧来源通过 `end_frame_draw_scene_id` 引用当前有效 `draw_scenes[].id`，空字符串表示保持单首帧旧行为；引用不存在、绘图场景被删除或非法时自动清空。运行时若被引用绘图场景配置了后处理链，视频尾帧使用完整链路的最终图。用户点击主菜单 `AI动图` 后，QQCC Bot 回复 `system.video_edit_hint`，并把当前有效场景作为 inline button 挂在该回复消息下方展示；按钮按三个一行排布，callback 使用 `qvid_scene:<scene_id>`，由 `get_quick_video_fsm_handler()` 直接进入发送图片步骤。旧 `qvid_mode:<menu.video_edit_*>` callback 只作为已发消息兼容，若后台已删除对应场景必须回复 `功能暂未开放`。不要再把这些场景塞回 Telegram 底部 reply keyboard。

`AI绘图` 场景由管理后台 `draw_scenes` 动态配置，`快速自慰` 与 `快速脱衣` 两个默认项是一次性种子化的普通预设，底层 engine 均为旧 `free_edit`。每个场景包含按钮名称、提示词、底层模型和可选 `postprocess_draw_scene_id` 绘图后处理，`id` 使用短安全 callback 字符串；所有场景都必须有非空按钮名称和提示词，QQCC 运行时只读取场景自身 `prompt`，不再通过 `prompt_key` 或 `prompts.ini` 回退。新增自定义场景默认 engine 是自由P图 v2 `free_edit_v2`，不支持附加模型；切到旧 `free_edit` 时才可选图片 LoRA。后处理只能选择其它有效绘图场景；保存时后端清空非法引用、自引用和循环引用，前端也过滤会形成循环的选项。用户点击主菜单 `AI绘图` 后，QQCC Bot 回复 `system.ai_draw_hint`，并按三个一行展示 inline 场景按钮，callback 使用 `qdraw_scene:<scene_id>`。该 callback 由 `get_quick_image_fsm_handler()` 承接，进入发送 1 张图片步骤；收到图片后按 `scene_id -> postprocess_draw_scene_id -> ...` 串行提交绘图，只把最终图发给用户。旧消息中的已删除场景 callback 必须回复 `功能暂未开放`，不提交任务。本次默认场景只复用现有 `free_edit`/`img2img` 执行面，不新增 workflow、RunPod profile 或数据库表。

用户点击主菜单 `修仙市集` 后，QQCC Bot 使用专用 `qqcc_bot/gallery_market.py` 入口展示当前 Web Gallery 可见类型的投稿，不复用旧主 Bot 的 gallery 分类常量。callback 前缀为 `qg:`，支持分类、分页、点赞、点踩、一键应用和 Web 应用跳转；不提供留言入口。普通可应用投稿的卡片同时展示 `一键应用` 与 `Web应用`，视频换脸类模板只展示 `Web应用`，Wan22/LTX 多段拼接结果不展示任何应用入口；Bot caption 中的类型和 `#task.mode_*` 标签走当前语言翻译，不直接暴露内部变量名。分类对齐 Web 可见 tab：`all`、`i2i_pro`、`i2i_draw`、`edit_group`、`free_edit_v2_group`、`img2video_group`、`ltx_video`、`wan22_video_v2`、`scail2_action_transfer`、`scail2_video_replacement`、`scail2_face_swap_v2`，不展示 `txt2img`。

`修仙市集` 媒体发送优先使用 `GalleryPost.telegram_file_id`，失效或缺失时通过当前 Gallery R2/S3 URL resolver 下载当前作品并重新写回 Telegram file_id；测试 Bot 不持久化新 file_id。不得恢复旧 `storage.get_file_bytes(...)` / legacy MinIO public URL 作为浏览主路径。

QQCC 市集一键应用是轻量 Bot 流程：安全的单图模板在 Bot 内提示用户重新发送 1 张参考图，并以 `source_post_id`、`allow_contribute=False`、`client_type=bot:qqcc` 提交任务；复杂模板、SCAIL-2、多图/多视频复用与首尾帧复杂链路的 `一键应用` callback 只做 Web handoff，返回 `/gallery?apply_source=gallery&apply_id=<post_id>` 深链，不在 Bot 内强行复用视频或多素材。`apply` 次数仍只能在任务成功链路记账，不能在点击按钮时预增。

QQCC 功能开关与 QQCC 专用提示词覆盖由独立 QQCC Config Web 维护，主 Dashboard 不再显示 `懒人Bot配置` 导航，也不挂载 `/api/qqcc/config`。配置存入 `runtime_checkpoints`，固定 key 为 `qqcc_lazy_bot_config:v1`，不新增表。独立配置后端 `dashboard.backend.qqcc_config_main:app` 暴露：
- `GET /api/qqcc/config`：返回合并默认值后的有效配置，并附带非持久化 `options`，包含 `scene_preset_version`、默认动图/绘图 engine、engine 选项与 LoRA catalog，前端不得手写模型清单或默认场景。
- `PUT /api/qqcc/config`：规范化并保存配置，只保留已知 key。

独立配置页底部“提示词覆盖”只展示 `快速换脸`（`prompts.face_swap`）。`快速自慰`、`快速脱衣` 和默认动图预设都在各自场景行填写提示词，不能留空；后端仍保留 `prompts.undress` / `prompts.masturbation` / 旧动图 prompt 字段用于旧配置迁移兼容。

QQCC Config Web 使用独立后台账号，不复用 Dashboard 管理员 token：
- `QQCC_CONFIG_ADMIN_USERNAME`
- `QQCC_CONFIG_ADMIN_PASSWORD_HASH`
- `QQCC_CONFIG_SECRET_KEY`

配置结构固定包含：
- `scene_preset_version`: 当前为 `1`；缺失或小于 `1` 视为旧配置，保存时一次性补齐 QQCC 绘图/动图预设并迁移旧 prompt override；已有 `scene_preset_version>=1` 时尊重管理员删除后的空 `draw_scenes` / `video_scenes`
- `global_enabled`
- `main_buttons`: `quick_undress`, `quick_faceswap`, `photo_edit`, `ai_draw`, `video_edit`, `market`, `main_bot_link`；`quick_undress` 与 `photo_edit` 仅保留旧配置兼容，QQCC 主菜单不再渲染
- `photo_buttons`: `masturbation`, `random_faceswap`；仅保留旧配置兼容
- `undress_methods`: `legacy`, `i2i_draw`；仅保留旧配置兼容
- `video_scenes`: `[{ id, name, prompt, duration, engine, lora_name, end_frame_draw_scene_id }]`；所有场景 `prompt` 必填；`engine` 只能是 `image_to_video` 或 `wan22_video_v2`，缺省 `image_to_video`；`lora_name` 只允许在 `image_to_video` 下来自 `VIDEO_LORA_MODELS`，v2 自动清空；`end_frame_draw_scene_id` 只能引用归一化后的 `draw_scenes[].id`，缺省 `""`；`duration` 只能是 `5s`、`8s`、`10s`，`id` 只能用于短安全 callback
- `draw_scenes`: `[{ id, name, prompt, engine, lora_name, postprocess_draw_scene_id }]`；所有场景 `prompt` 必填，最多 20 个，`engine` 只能是 `free_edit` 或 `free_edit_v2`，缺省 `free_edit_v2`；`lora_name` 只允许在 `free_edit` 下来自 `IMAGE_LORA_MODELS`，v2 自动清空；`postprocess_draw_scene_id` 缺省 `""`，只能引用其它有效绘图场景，非法、自引用和循环引用必须清空；`id` 只能用于短安全 callback
- `video_buttons` 与 `video_settings` 仅保留旧配置兼容；管理后台不再编辑 AI 动图画质或全局时长
- `prompts`: `undress`, `i2i_draw_quick_undress`, `masturbation`, `face_swap`, `perfect_video_insert`, `doggy_style`, `blowjob`, `undress_tongue`, `closeup_blowjob`

关闭功能后，QQCC Bot 会隐藏新菜单按钮，并在旧 reply keyboard / 旧 callback 入口回复 `功能暂未开放`，不提交新任务。`quick_faceswap` 关闭后，旧 `random_faceswap_again` 也必须拒绝继续提交。AI 动图每个场景的时长由后台固定，用户在 Bot 中只选择画质；画质只受用户权限过滤，仍保持 `1024p` 与 `10s` 不能同时选择。QQCC draw/video 场景提示词只来自场景自身 `prompt`，只作用于 QQCC Bot，主 Bot 不受影响。无尾帧来源时，动图 `image_to_video` 无模型提交 `custom_video`，带模型提交 `video_lora` 并透传 `lora_name`；动图 `wan22_video_v2` 提交 `wan22_video_v2`，使用场景提示词、固定时长和用户画质，负向提示词留空走现有默认归一。配置尾帧来源时，用户仍只发送 1 张图；Bot 会先按被引用 AI绘图场景的完整后处理链串行提交隐藏绘图任务，成功后下载最终图作为尾帧，再以用户原图和生成尾帧提交首尾帧视频。旧 `custom_video` / `video_lora` 传两张图并写入 `use_end_frame=true`；`wan22_video_v2` 传 `images=[start,end]`。提交前按“绘图链 + 视频”做合计额度预检，尾帧链任一步失败都不提交视频，视频失败只按视频任务现有退款策略处理，已成功生成的尾帧历史不回滚且不可投稿。`free_edit_v2` 提交 `pornmaster_flux2_single_edit`，旧 `free_edit` 无模型提交 `edit`，带模型提交 `img2img_lora` 并透传 catalog 默认强度。直接 AI绘图链路中，中间绘图 `send_result=false`、`allow_contribute=false`，最终绘图才发给用户并允许投稿；作为视频尾帧时全链路绘图均隐藏且不可投稿。新增配置仍复用 `runtime_checkpoints` 的 `qqcc_lazy_bot_config:v1`，不新增 workflow、RunPod profile 或数据库表。

注册的 FSM 只允许：
- `get_quick_image_fsm_handler()`
- `get_quick_video_fsm_handler()`

不得注册 `faceswap_fsm`、`txt2img_fsm`、`edit_image_fsm`、`image_to_video_fsm`、`wan22_video_v2_fsm`、`ltx_video_fsm`、`scail2_video_fsm`、充值、affiliate redeem 或主 Bot 完整 gallery 菜单入口。`修仙市集` 只能通过 QQCC 专用 handler 与 `qg:` callback 实现轻量浏览/应用。

## 3. 代码入口
- `qqcc_bot/main.py`：独立启动入口，读取 `QQCC_BOT_TOKEN` 或 `QQCC_BOT_TOKEN_TEST`，设置 `bot_client_type=bot:qqcc`，注册最小 handler 集。
- `qqcc_bot/keyboards.py`：QQCC 专用主菜单、旧 P 图兼容键盘、`AI绘图` / `AI动图` inline 场景菜单。
- `qqcc_bot/commands.py`：QQCC `/start` 与 `/cancel`，复用用户创建和准入逻辑，返回简化菜单。
- `qqcc_bot/prompt_handlers.py`：只路由旧 `menu.photo_edit` 禁用提示、`qqcc.menu.ai_draw`、`menu.video_edit`、`qqcc.menu.market`、`menu.main_menu`、`menu.back_main` 与 `menu.open_main_bot`。
- `qqcc_bot/gallery_market.py`：QQCC 专用修仙市集，负责 `qg:` callback、Gallery file_id 缓存发送、点赞/点踩和轻量一键应用 session。
- `qqcc_bot/callback_handler.py`：只导入任务取消、结果评分、随机换脸再来一张、公开分享互动和 QQCC 市集等必要 callback 注册模块。
- `src/handlers/fsm/quick_image_fsm.py`：在 `bot_client_type=bot:qqcc` 时承接 `qqcc.menu.quick_faceswap` 进入单图随机换脸，并承接 `qdraw_scene:<id>` 进入 AI绘图单图提交流程；按场景 engine、场景 `prompt` 与后处理链路路由到 `pornmaster_flux2_single_edit` / `edit` / `img2img_lora`。主 Bot 的旧 `快速脱衣` / `快速自慰` 文本入口只回复功能未开放，不提交任务。
- `src/handlers/fsm/quick_video_fsm.py`：在 `bot_client_type=bot:qqcc` 时承接 `qvid_scene:<id>`，按场景 engine 提交旧图生视频或 `wan22_video_v2`；配置 `end_frame_draw_scene_id` 时先复用对应 AI绘图场景的完整后处理链生成隐藏尾帧，再提交首尾帧视频。主 Bot 的旧 `menu.video_edit_*` 文本入口和 `qvid_*` callback 只回复功能未开放。
- `src/services/qqcc_draw_chain_service.py`：QQCC AI绘图链共享 helper，负责解析无环链、计算链路费用、串行执行绘图并复用中间产物。
- `src/services/qqcc_config_service.py`：QQCC 配置默认值、normalize、runtime checkpoint 读写与 QQCC prompt override 解析。
- `src/services/qqcc_runtime_context.py`：集中维护 `bot:qqcc` 常量、QQCC Bot 上下文判断和按上下文加载运行时配置的兜底逻辑，供 quick image/video FSM 与 callback helper 复用。
- `dashboard/backend/qqcc_config_main.py`：独立 QQCC Config API 入口，只做 DB 初始化、独立认证、健康检查与 QQCC 配置 router，不启动 Dashboard 后台循环。
- `dashboard/backend/qqcc_config_auth.py`：独立 QQCC Config 账号与 JWT。
- `dashboard/backend/routers/qqcc.py`：QQCC 配置 router，被独立配置后端挂载。
- `dashboard/frontend/src/QqccConfigApp.vue` / `dashboard/frontend/index.qqcc-config.html`：独立 QQCC Config Web 入口。
- `dashboard/frontend/src/components/QqccBotSettings.vue`：QQCC 配置页主体组件，供独立 Web 复用；通过 props 接收独立配置 API handler，只渲染后端返回的 config/options，不在组件内合成默认场景。

主 Bot 入口仍是 `src/bot_main.py`。不要在 `qqcc_bot/` 中导入 `src.bot_main`，否则会把主 Bot 的完整 handler 面一起注册进来。

## 4. 任务来源归属
Telegram Bot 任务默认来源为 `client_type="bot"`。QQCC Bot 在 `application.bot_data["bot_client_type"]` 写入 `bot:qqcc`，`run_bot_task_application(...)` 读取该值并透传到 `process_and_submit_task(client_type=...)`。
`bot:qqcc` 常量与上下文判断统一来自 `src/services/qqcc_runtime_context.py`，避免 QQCC main、quick image/video FSM 和 callback 侧各自复制来源判断。

active task registry 必须持久化 `client_type`：
- 主 Bot 恢复 `client_type=bot` 与缺失 `client_type` 的 legacy 任务。
- QQCC Bot 只恢复 `client_type=bot:qqcc` 的任务。

新增 Bot 入口或任务提交 seam 时，不得让两个 polling 进程交叉恢复或发送彼此的任务恢复消息。

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

独立 QQCC Config Web 云测试 service：
- backend service/container: `qqcc-config-backend-test` / `cloud-qqcc-config-backend-test`，默认端口 `8045`
- frontend service/container: `qqcc-config-frontend-test` / `cloud-qqcc-config-frontend-test`，默认端口 `8088`

QQCC Config Web 只面向 Tailscale/受控入口或 Cloudflare Access 保护入口，不得裸露公网。

QQCC 跳转主 Bot 按钮优先读取 `QQCC_MAIN_BOT_URL`，可配置为 `https://t.me/<main-bot-username>` 或带 `start` 参数的 Telegram deeplink；未配置 URL 时会尝试 `QQCC_MAIN_BOT_USERNAME` 并自动拼成 `https://t.me/<username>`。两者都未配置时，菜单仍可显示 `前往主bot`，但点击后只提示主 Bot 入口暂未配置。

主业务 Bot 跳转 QQCC 懒人 Bot 使用独立反向配置：优先读取 `QQCC_LAZY_BOT_URL`，未配置时读取 `QQCC_LAZY_BOT_USERNAME` 并自动生成 `https://t.me/<username>`。两者都未配置时，主 Bot 的 `懒人bot` 菜单只提示入口暂未配置。

QQCC Bot 不启动 TON 轮询，不注册支付回调，不作为充值入口。compose 中必须显式设置 `TON_PAYMENT_POLLING_ENABLED=false`。

测试环境没有独立 `QQCC_BOT_TOKEN_TEST` 时，`qqcc-bot-test` 必须保持停止，避免和正式 token 或其它测试实例双 polling。

## 6. 维护与发布
QQCC Bot 读取同一个 `GENERATION_MAINTENANCE_FILE`。云测试和云正式维护脚本写入/清理生成维护标记时，应同时覆盖正在运行的 `cloud-qqcc-bot-test` / `cloud-qqcc-bot-prod`。

云测试更新使用：

```bash
scripts/update_cloud_test_with_maintenance.sh --execute
```

默认 `--qqcc-bot-mode auto`，只在 `qqcc-bot-test` 原本运行且远端 env 配置了 `QQCC_BOT_TOKEN_TEST` 时重建启动。

只更新云正式 QQCC Bot 时，优先使用专用窄入口：

```bash
scripts/update_cloud_prod_qqcc_bot.sh
scripts/update_cloud_prod_qqcc_bot.sh --execute --confirm-prod --confirm-single-polling
```

该脚本默认 dry-run；真实执行必须传 `--execute --confirm-prod --confirm-single-polling`。当用户已经明确要求“QQCC 单服务更新/走单服务更新/单独更新 QQCC Bot”时，这句话本身可作为当次正式与单 polling 操作确认，不需要再额外逐字复述；若发现目标容器状态异常、疑似多实例、token/远端 env 异常、不是专用脚本路径，或要启动一个当前停止的新正式 QQCC 实例，必须停下并追问确认。它只同步代码、按需同步 env、执行只读 preflight、重建并启动 `qqcc-bot-prod`，然后验证 `cloud-qqcc-bot-prod` 状态；整仓 rsync 会排除 `local_analytics_platform/`、`backups/`、`logs/`、前端构建产物和密钥文件，避免把本地分析数据或运行产物同步到云正式；不写生成维护标记、不等待队列 drain、不重建 Central/Web/Payment/Dashboard/主 Bot/Worker/RunPod、不操作 Cloudflare Pages/DNS/边缘路由。

只更新正式 QQCC Config Web 时，走 services scope 单服务更新：

```bash
scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod --scope services --services "qqcc-config-backend-prod qqcc-config-frontend-prod" --skip-generation-maintenance
```

该路径不得开启 `GENERATION_MAINTENANCE`，不得重建 Central/Web/Payment/主 Bot/QQCC Bot/Worker/RunPod。发布后确认 `cloud-qqcc-config-backend-prod`、`cloud-qqcc-config-frontend-prod` running/healthy，并确认非目标服务启动时间未变化。

完整云正式控制面更新仍默认不碰 QQCC Bot；若需要随控制面一起重建 QQCC Bot，必须显式传：

```bash
scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod --qqcc-bot-mode start
```

正式启动新实例前必须确认全网没有第二个 `@QQCC666_bot` polling 实例，并确认生产 token 已在远端 `.env.cloud.prod` 配置。日常对正在运行的 `cloud-qqcc-bot-prod` 走专用单服务脚本更新时，不再要求用户每次逐字确认单 polling；用户明确要求该单服务更新即可。

## 7. 最小验证
代码变更至少跑：

```bash
pytest tests/qqcc_bot tests/dashboard -q
cd dashboard/frontend && npm run typecheck && npm run test && npm run build
python -m alembic heads
pytest tests/qqcc_bot/test_qqcc_bot_entrypoint.py \
  tests/services/test_task_service_flow.py \
  tests/services/test_recovery_service.py -q
bash -n scripts/update_cloud_test_with_maintenance.sh \
  scripts/update_cloud_prod_with_maintenance.sh \
  scripts/safe_deploy_cloud_test.sh \
  scripts/safe_deploy_cloud_prod.sh \
  scripts/update_cloud_prod_qqcc_bot.sh
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
- 主业务 Bot `图片换脸` 二级菜单只展示 `快速换脸`、`随机换脸` 与返回主菜单；旧 `快速脱衣`、`快速自慰`、旧动图文本入口和主 Bot 上的 `qvid_*` callback 回复功能未开放且不提交任务。
- `/start` 主菜单默认展示 `快速换脸`、`AI绘图`、`AI动图`，不展示旧 `快速脱衣` 或 `懒人P图`。
- `/start` 只返回简化主菜单，不额外发送跳转消息；主菜单包含非生成入口 `修仙市集` 与 `前往主bot`。
- 配置 `QQCC_MAIN_BOT_URL` 或 `QQCC_MAIN_BOT_USERNAME` 时，点击 `前往主bot` 回复 inline URL 跳转按钮；未配置时回复入口未配置提示。
- 点击主菜单 `快速换脸` 直接进入 quick image 单图随机换脸流程，发 1 张正脸图后自动匹配模板；不注册 `faceswap_fsm`。
- 旧配置迁移后默认带 `快速自慰` 和 `快速脱衣` 两个普通预设，主菜单展示 `AI绘图`；点击后按三个一行展示 inline 场景按钮，点击 `qdraw_scene:<id>` 进入 quick image 发送图片步骤并按场景 engine、场景 `prompt` 与后处理链提交 `pornmaster_flux2_single_edit` / `edit` / `img2img_lora`，只发送最终图；场景删除后旧 callback 回复 `功能暂未开放` 且不提交任务。
- 点击主菜单 `AI动图` 后，Bot 回复下方展示当前后台配置的 inline 场景按钮，默认第一行 3 个、第二行 2 个；点击 `qvid_scene:<id>` 进入 quick video 发送图片步骤。旧 `qvid_mode:*` 已发按钮兼容到对应场景，场景删除后回复 `功能暂未开放` 且不提交任务。
- 点击主菜单 `修仙市集` 后展示 QQCC 专用类型菜单；浏览投稿时支持点赞、点踩、上一条/下一条、分类返回、一键应用或 Web 应用，不展示留言入口。
- `修仙市集` 二次查看已缓存作品时优先用 Telegram file_id，file_id 失效后从当前 R2/S3 URL resolver 刷新；不能回退旧 legacy MinIO bytes 主路径。
- Bot 原生应用必须传 `source_post_id` 且 `allow_contribute=False`，复杂模板必须跳 Web 深链，点击应用不直接增加 `applied_count`。
- 旧 `快速脱衣`、旧 `懒人P图` 与旧 P 图子按钮回复 `功能暂未开放`，不提交任务。
- 关闭任一 QQCC 配置开关后，新菜单隐藏对应按钮，旧按钮/旧 callback 回复 `功能暂未开放` 且不提交任务。
- QQCC 动态场景 prompt、按钮名、固定时长、engine、LoRA 与尾帧来源配置生效时不影响主 Bot；Bot 发图后动图只展示画质选项和开始按钮，v2 系列不展示也不透传附加模型。
- AI动图配置尾帧来源后，用户仍只发 1 张图片；额度预检使用绘图链加视频合计费用，尾帧绘图链隐藏执行且不可投稿，任一步失败都不提交视频，最终视频使用首尾帧提交。关闭主菜单 `AI绘图` 只影响直接入口，不影响已被动图场景引用的有效 `draw_scenes`。
