---
name: "allbot-qqcc-lazy-bot"
description: "处理 QQCC 懒人 Telegram Bot 独立服务、简化菜单、quick image/video FSM 注册、bot:qqcc 任务来源归属与双 polling 部署红线。"
---

# AllBot QQCC 懒人 Bot

本技能用于维护根目录 `qqcc_bot/` 独立 Telegram polling 服务。只要修改 QQCC Bot 菜单、handler 注册、启动入口、任务 client_type、恢复过滤、compose 服务或 QQCC 部署脚本，就必须加载本技能，并按需叠加 `allbot-tg-fsm`、`allbot-task-engine`、`allbot-ops-deployment`、`allbot-tdd`。

## 1. 当前入口
- 代码入口：`qqcc_bot/main.py`
- 正式 service：`qqcc-bot-prod` / `cloud-qqcc-bot-prod` / profile `qqcc-bot`
- 测试 service：`qqcc-bot-test` / `cloud-qqcc-bot-test` / profile `qqcc-bot`
- 正式单独更新脚本：`scripts/update_cloud_prod_qqcc_bot.sh`
- 配置服务：`src/services/qqcc_config_service.py`
- 运行时上下文 helper：`src/services/qqcc_runtime_context.py`
- 独立配置 API 入口：`dashboard/backend/qqcc_config_main.py`
- 独立配置认证：`dashboard/backend/qqcc_config_auth.py`
- 配置 router：`dashboard/backend/routers/qqcc.py`
- 配置页组件：`dashboard/frontend/src/components/QqccBotSettings.vue`
- 独立配置 Web 入口：`dashboard/frontend/src/QqccConfigApp.vue` / `dashboard/frontend/index.qqcc-config.html`
- 领域文档：`docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`

## 2. 功能范围
主菜单业务入口只能有 `快速换脸`、`AI绘图` 和 `AI动图`。`快速换脸` 是 QQCC 对现有单图随机换脸流程的专用主菜单入口，显示文案走 `qqcc.menu.quick_faceswap`，不接入主 Bot 双图 `faceswap_fsm`。`AI绘图` 是 QQCC 对 `qqcc.menu.ai_draw` 的专用显示文案；`AI动图` 是 QQCC 对 `menu.video_edit` 的专用显示文案。不要直接改共享 `menu.video_edit` 文案来实现 QQCC 菜单改名，以免破坏旧按钮兼容和 QQCC 动图路由。旧 `快速脱衣` 主菜单和 `懒人P图` 主菜单已退出；用户点击旧 reply keyboard / 旧 P 图子按钮时必须回复 `功能暂未开放` 并拒绝提交。主菜单可额外有两个非生成入口：`修仙市集` 与 `前往主bot`；Telegram reply keyboard 不能直接承载 URL，因此点击 `前往主bot` 后由 QQCC Bot 回复主 Bot 的 inline URL 跳转按钮。主业务 Bot 的旧 `修仙市集` 底部入口已改为 `懒人bot` 跳转，跳转目标由 `QQCC_LAZY_BOT_URL` 或 `QQCC_LAZY_BOT_USERNAME` 配置；QQCC 自己的 `修仙市集` 仍是专用轻量 Gallery。

QQCC `AI动图` 场景由独立 QQCC 配置 Web 的 `video_scenes` 动态配置。默认配置会一次性种子化旧五个懒人动图预设（传教士、后入、口交、脱衣吐舌、近景口交），种子化后它们和自定义场景结构一致，可编辑、删除、调整按钮名、提示词、负面提示词、固定时长、底层模型和尾帧来源。默认 engine 是旧 `image_to_video`，可选附加模型；切到 `wan22_video_v2` 时必须清空附加模型。`end_frame_draw_scene_id` 只能引用归一化后的 `draw_scenes[].id`，空字符串保持单首帧旧行为；运行时若该绘图场景配置了后处理链，视频尾帧必须使用完整绘图链的最终图。绘图场景删除或引用非法时必须清空。二级场景菜单必须挂在 Bot 回复消息下方，用 inline button 展示，每行最多 3 个；新场景按钮 callback 前缀为 `qvid_scene:`，由 `get_quick_video_fsm_handler()` 直接承接并进入发送图片步骤。旧 `qvid_mode:<menu.video_edit_*>` callback 仅作已发消息兼容，若对应场景已删除必须回复 `功能暂未开放` 并拒绝提交。

QQCC `AI绘图` 场景由独立 QQCC 配置 Web 的 `draw_scenes` 动态配置。旧配置第一次归一化时会写入 `scene_preset_version=1` 并一次性种子化两个预设场景：`快速自慰` 与 `快速脱衣`，底层 engine 均为旧 `free_edit`；种子化后它们和“小屁股”这类自定义场景没有结构差异，可编辑、删除、调整底层模型、`postprocess_draw_scene_id` 绘图后处理和 `original_face_swap_enabled` 原图换脸。所有有效场景都必须有非空 `name` 与 `prompt`，`negative_prompt` 可选且缺省/非法归一为空字符串；QQCC 运行时只读取场景自身 `prompt` 与 `negative_prompt`，不再通过 `prompt_key` 或 `prompts.ini` 回退。默认新增场景 engine 是自由P图 v2 `free_edit_v2`，不支持附加模型；切到旧 `free_edit` 时才可选图片 LoRA。后处理只能引用其它有效 `draw_scenes[].id`，不能自引用；后端保存时清空非法引用、自引用和循环链路内引用，前端保存前也必须过滤/阻止循环。`original_face_swap_enabled` 缺省/非法时归一为 `false`；开启后每个场景先按自身 prompt/negative_prompt/engine/LoRA 绘图，再用用户最初上传的原图做人脸来源、用该步生成图做 body 提交内部 `face_swap`，最后才继续后处理链，内部 `face_swap` 不传负面提示词。每个开启步骤额外计费 `2` 灵石，提交前额度检查和隐藏换脸任务实际扣费必须一致；直接 AI绘图和 AI动图尾帧引用同一绘图链语义。二级场景菜单必须挂在 Bot 回复消息下方，用 inline button 展示，每行最多 3 个；场景按钮 callback 前缀为 `qdraw_scene:`，由 `get_quick_image_fsm_handler()` 直接承接并进入发送图片步骤。收到 1 张图片后按该场景解析 `A -> B -> C` 链串行提交绘图，直接 AI绘图只把最终图发给用户；若最终可见任务是内部原图换脸，结果展示、历史和投稿仍按原 AI绘图场景的 task type、prompt 与用户原始输入图归类，不暴露成 `快速换脸`。旧/删除后的场景 callback 必须回复 `功能暂未开放` 并拒绝提交。本次默认场景只复用现有 `free_edit`/`img2img` 与 `face_swap` 执行面，不新增 workflow、RunPod profile 或数据库表。

独立 QQCC Config Web 的底部“提示词覆盖”只展示 `快速换脸`（`prompts.face_swap`）。`快速自慰` / `快速脱衣` 和默认动图预设的提示词都在各自场景行里编辑，不能留空；后端仍保留 `prompts.undress` / `prompts.masturbation` / 旧动图 prompt 字段用于旧配置迁移兼容。

`修仙市集` 是 QQCC 专用轻量 Gallery 入口，代码在 `qqcc_bot/gallery_market.py`，callback 前缀为 `qg:`。它只允许浏览 Web 当前可见分组投稿、点赞/点踩、一键应用和 Web 应用跳转，不提供留言，不复用旧主 Bot gallery 分类常量，不注册主 Bot 完整 gallery handler。普通可应用投稿的卡片应同时展示 `一键应用` 与 `Web应用`；视频换脸类模板只展示 `Web应用`；Wan22/LTX 多段拼接结果不展示任何应用入口。Bot caption 中的类型和 `#task.mode_*` 标签必须走当前语言的 task/tab 翻译，不能直接暴露内部变量名。媒体发送必须优先复用 `GalleryPost.telegram_file_id`，缺失/失效时走当前 Gallery R2/S3 URL resolver 下载当前作品并刷新 file_id；测试 Bot 不持久化新 file_id。

QQCC 市集 Bot 原生应用只承接安全的单图轻量模板，提交任务必须传 `source_post_id`、`allow_contribute=False` 并保持 `client_type=bot:qqcc`；复杂多图/多视频、SCAIL-2、LTX 首尾帧等模板的 `一键应用` callback 只能做 Web handoff，并给出 `/gallery?apply_source=gallery&apply_id=<post_id>` 深链，不得在 Bot 内强行复用视频/多素材。点击应用不得预增 `applied_count`。

注册的 FSM 只能是 `get_quick_image_fsm_handler()` 与 `get_quick_video_fsm_handler()`。不得注册 `faceswap_fsm`、高级图像、高级视频、充值、affiliate redeem 或主 Bot 完整 gallery 浏览入口。

## 2.1 独立配置 Web
QQCC 懒人 Bot 配置已从主 Dashboard 剥离为独立 QQCC Config Web。主 Dashboard 不再挂载 `懒人Bot配置` 导航，也不挂载 `/api/qqcc/config`。独立后端入口是 `dashboard.backend.qqcc_config_main:app`，只启动 DB 初始化、独立 `QQCC_CONFIG_*` 账号认证、`/api/health` 和 `/api/qqcc/config`，不得启动 Dashboard worker listener、余额监控或 RunPod autoscaler。配置存入 `runtime_checkpoints`，固定 key 为 `qqcc_lazy_bot_config:v1`，不新增数据库表。API：
- `GET /api/qqcc/config` 返回合并默认值后的有效配置，并带非持久化 `options`，供前端渲染 `scene_preset_version`、默认 engine、engine 选项与 LoRA catalog；前端不得内置默认场景或模型清单作为事实源。
- `PUT /api/qqcc/config` 规范化保存配置，未知 key 必须丢弃。

独立账号 env：
- `QQCC_CONFIG_ADMIN_USERNAME`
- `QQCC_CONFIG_ADMIN_PASSWORD_HASH`
- `QQCC_CONFIG_SECRET_KEY`

配置结构固定包含：
- `scene_preset_version`: 当前为 `1`；缺失或小于 `1` 视为旧配置，保存时一次性补齐 QQCC 绘图/动图预设并迁移旧 prompt override；已有 `scene_preset_version>=1` 时尊重管理员删除后的空 `draw_scenes` / `video_scenes`
- `global_enabled`
- `main_buttons`: `quick_undress`, `quick_faceswap`, `photo_edit`, `ai_draw`, `video_edit`, `market`, `main_bot_link`；`quick_undress` 与 `photo_edit` 仅保留旧配置兼容，QQCC 主菜单不再渲染
- `photo_buttons`: `masturbation`, `random_faceswap`；仅保留旧配置兼容
- `undress_methods`: `legacy`, `i2i_draw`；仅保留旧配置兼容
- `video_scenes`: `[{ id, name, prompt, negative_prompt, duration, engine, lora_name, end_frame_draw_scene_id }]`；所有场景 `prompt` 必填，`negative_prompt` 可选，缺失或非字符串归一为空，字符串保存前 trim；`engine` 只能是 `image_to_video` 或 `wan22_video_v2`，缺省 `image_to_video`；`lora_name` 只允许在 `image_to_video` 下来自 `VIDEO_LORA_MODELS`，v2 自动清空；`end_frame_draw_scene_id` 只能引用归一化后的 `draw_scenes[].id`，缺省 `""`；`duration` 只能是 `5s`、`8s`、`10s`，`id` 只能用于短安全 callback
- `draw_scenes`: `[{ id, name, prompt, negative_prompt, engine, lora_name, postprocess_draw_scene_id, original_face_swap_enabled }]`；所有场景 `prompt` 必填，`negative_prompt` 可选，缺失或非字符串归一为空，字符串保存前 trim；最多 20 个，`engine` 只能是 `free_edit` 或 `free_edit_v2`，缺省 `free_edit_v2`；`lora_name` 只允许在 `free_edit` 下来自 `IMAGE_LORA_MODELS`，v2 自动清空；`postprocess_draw_scene_id` 缺省 `""`，只能引用其它有效绘图场景，非法、自引用或循环引用必须清空；`original_face_swap_enabled` 只能为布尔值 `true`，缺失或非法归一为 `false`；`id` 只能用于短安全 callback
- `video_buttons` 与 `video_settings` 仅保留旧配置兼容；AI 动图后台页面不再编辑画质或全局时长
- `prompts`: `undress`, `i2i_draw_quick_undress`, `masturbation`, `face_swap`, `perfect_video_insert`, `doggy_style`, `blowjob`, `undress_tongue`, `closeup_blowjob`

关闭功能后，新菜单必须隐藏对应按钮；旧 reply keyboard / 旧 callback 必须回复 `功能暂未开放` 并拒绝提交任务。`quick_faceswap` 关闭后，旧 `random_faceswap_again` 也必须拒绝继续提交。AI 动图时长由场景配置固定，用户在 Bot 中只选择画质；画质只受用户权限过滤，仍保持 `1024p` 和 `10s` 互斥。QQCC draw/video 场景正负提示词只来自场景自身 `prompt` / `negative_prompt`，只作用 QQCC，主 Bot 继续走原提示词。无尾帧来源时，动图 `image_to_video` 无模型提交 `custom_video`，带模型提交 `video_lora` 并透传 `lora_name`；动图 `wan22_video_v2` 提交 `wan22_video_v2`，使用视频场景提示词、负面提示词、固定时长和用户画质，负面提示词为空时保持 Wan22 现有默认负向归一。有尾帧来源时，用户仍只发 1 张图；Bot 先按引用 AI绘图场景的完整后处理链串行执行隐藏绘图任务，每步使用该绘图场景自己的 `negative_prompt`，链上任何开启 `original_face_swap_enabled` 的步骤都必须插入 draw -> 原图换脸，再把换脸后图片传给下一步，下载最终图作为尾帧后再提交首尾帧视频；最终视频仍只使用视频场景自己的 `negative_prompt`。旧图生视频传两张图并写 `use_end_frame=true`，v2 传 `images=[start,end]`；提交前按绘图链、每步原图换脸和视频做合计额度预检，任一尾帧绘图/换脸失败都不提交视频。上述 AI动图提交计划与执行 payload 的事实源是 `src/services/quick_video_submission_service.py`，FSM 只负责 Telegram 状态、额度检查和回复。QQCC AI绘图与随机换脸提交计划的事实源是 `src/services/quick_image_submission_service.py`，`quick_image_fsm.py` 只负责 Telegram 状态、图片接收、额度检查和回复。`free_edit_v2` 提交 `pornmaster_flux2_single_edit`，`free_edit` 无模型提交 `edit`，带模型提交 `img2img_lora` 并透传 catalog 默认强度；绘图任务透传每步自身 `negative_prompt`，为空时保持空负向。直接 AI绘图链路时，中间绘图 `send_result=false`、`allow_contribute=false`，最终绘图才按直接入口发送并允许投稿；若最终可见输出来自原图换脸，内部 `face_swap` 使用受信任 `cost_override=2`，但 Bot 结果语义覆盖回原 AI绘图场景。视频尾帧链路所有绘图/原图换脸都隐藏且不可投稿。关闭 `main_buttons.ai_draw` 只隐藏直接入口，不影响动图内部引用有效 `draw_scenes` 生成尾帧。

## 3. 任务归属红线
QQCC Bot 必须设置 `application.bot_data["bot_client_type"] = "bot:qqcc"`，Bot 任务提交必须透传该值到 `process_and_submit_task(client_type=...)` 并写入 active task registry。
`bot:qqcc` 常量、QQCC 上下文判断和按上下文加载运行时配置的通用逻辑集中在 `src/services/qqcc_runtime_context.py`；quick image/video FSM 与 callback helper 不要各自复制同一段判断/兜底加载逻辑。

恢复规则：
- 主 Bot 恢复 `bot` 和 legacy 任务。
- QQCC Bot 只恢复 `bot:qqcc` 任务。

不得让 QQCC Bot 恢复或通知主 Bot 的任务，也不得让主 Bot 抢恢复 QQCC 任务。

## 4. 部署与密钥
token 只允许放在 ignored env 文件：
- 正式：`QQCC_BOT_TOKEN`
- 测试：`QQCC_BOT_TOKEN_TEST`
- 可选主 Bot 跳转：`QQCC_MAIN_BOT_URL` 或 `QQCC_MAIN_BOT_USERNAME`
- 主 Bot 跳转 QQCC：`QQCC_LAZY_BOT_URL` 或 `QQCC_LAZY_BOT_USERNAME`

不得把真实 token 写入仓库、docs、日志、工单或聊天记录。QQCC Bot 不启动 TON 轮询，不注册支付回调，不作为充值入口。测试环境没有独立 token 时，`qqcc-bot-test` 必须保持停止。

主 Bot 跳转按钮优先使用 `QQCC_MAIN_BOT_URL`，未配置时可用 `QQCC_MAIN_BOT_USERNAME` 自动生成 `https://t.me/<username>`；两者均未配置时不得硬编码主 Bot 地址。菜单项是否展示只受 QQCC `main_bot_link` 配置控制，用户点击后应回复“主 Bot 入口暂未配置”类提示，而不是提交生成任务。

主业务 Bot 的 `懒人bot` 菜单跳转 QQCC 时优先使用 `QQCC_LAZY_BOT_URL`，未配置时可用 `QQCC_LAZY_BOT_USERNAME` 自动生成 `https://t.me/<username>`；两者均未配置时只提示“懒人bot入口暂未配置”，不得硬编码 QQCC Bot 地址。主 Bot 的 `图片换脸` 二级菜单只保留 `快速换脸` 与 `随机换脸`；旧 `快速脱衣`、`快速自慰`、旧 `menu.video_edit_*`、旧 `AI绘图` / `AI动图` / `快速换脸` 文本和主 Bot 上的 `qvid_*` callback 必须回复 QQCC 懒人 Bot inline URL 跳转或入口未配置提示，且不得提交任务。QQCC 的 `qdraw_scene:*`、`qvid_scene:*` 和旧 `qvid_mode:*` 兼容不受影响。

正式启动或重建前必须有用户明确要求进入 QQCC 正式单服务更新。只单独更新正式 QQCC Bot 时优先使用 `scripts/update_cloud_prod_qqcc_bot.sh`；真实执行必须传 `--execute --confirm-prod --confirm-single-polling`，该路径只 build/up `qqcc-bot-prod`，不重建其它正式服务。脚本整仓 rsync 时必须排除 `local_analytics_platform/`、`backups/`、`logs/`、前端构建产物和密钥文件，避免把本地分析数据或运行产物同步到云正式。用户已经明确说“QQCC 单服务更新/走单服务更新/单独更新 QQCC Bot”时，可视为当次正式与单 polling 操作确认，不要再要求逐字复述“没有第二个 polling 实例”；但若发现目标容器状态异常、疑似多实例、token/远端 env 异常、不是专用脚本路径，或要启动一个当前停止的新正式 QQCC 实例，必须停下并追问确认。

只更新独立 QQCC 配置 Web 时，使用 `scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod --scope services --services "qqcc-config-backend-prod qqcc-config-frontend-prod" --skip-generation-maintenance`。若同时更新 QQCC Bot 代码，Bot 仍单独使用 `scripts/update_cloud_prod_qqcc_bot.sh --execute --confirm-prod --confirm-single-polling`。全程不得开启 `GENERATION_MAINTENANCE`，不得重建 Central/Web/Payment/主 Bot/Worker/RunPod。

## 5. 验证要求
至少覆盖：
- 主业务 Bot 主菜单展示 `懒人bot`、`图片换脸`、`视频生视频`，不展示旧 `修仙市集` 或 `视频创作`；点击 `懒人bot` 或旧 `修仙市集` 文本回复前往 QQCC 的 inline URL 按钮。
- 主业务 Bot `图片换脸` 二级菜单只展示 `快速换脸`、`随机换脸` 和返回主菜单；旧 `快速脱衣`、`快速自慰`、旧动图文本入口、旧 `AI绘图` / `AI动图` / `快速换脸` 文本和主 Bot 上的 `qvid_*` callback 回复前往 QQCC 懒人 Bot inline URL 按钮或入口未配置提示，且不提交任务。
- QQCC `/start` 只返回简化主菜单，默认包含 `快速换脸`、`AI绘图`、`AI动图`、`修仙市集` 与 `前往主bot`，不包含旧 `快速脱衣` 或 `懒人P图`。
- QQCC `/start` 只返回简化主菜单，不额外发送主 Bot 跳转消息；主菜单包含非生成入口 `修仙市集` 与 `前往主bot`。配置主 Bot 跳转 env 时，点击菜单里的 `前往主bot` 后回复 inline URL 跳转按钮。
- 点击主菜单 `快速换脸` 直接进入现有单图随机换脸流程，发送 1 张正脸图后自动匹配模板；不注册或调用 `faceswap_fsm`。
- 旧 `快速脱衣`、旧 `懒人P图` 与旧 P 图子按钮回复 `功能暂未开放` 且不提交任务。
- `AI绘图` 点击后，默认迁移配置会回复 `快速自慰`、`快速脱衣` 两个 inline 场景按钮，三个一行；管理员删除预设后旧 callback 回复 `功能暂未开放`。点击 `qdraw_scene:<id>` 不转圈并进入 quick image 发送图片步骤，发 1 张图片后按场景 engine、场景 `prompt` / `negative_prompt` 与 `postprocess_draw_scene_id` 链提交 `pornmaster_flux2_single_edit` / `edit` / `img2img_lora`；中间绘图隐藏且不可投稿，最终只发送链路最后一张图。删除/禁用后的 callback 回复 `功能暂未开放` 且不提交任务。
- `AI动图` 点击后回复 inline 场景按钮，三个一行，默认包含兼容迁移的五个懒人动图场景；后台改为自定义场景后 Bot 展示自定义按钮名。点击 `qvid_scene:<id>` 不转圈并进入 quick video 发送图片步骤；旧 `qvid_mode:*` 已发按钮兼容到对应场景，场景删除后回复 `功能暂未开放`。
- `修仙市集` 点击后展示 QQCC 专用类型菜单；投稿浏览支持点赞、点踩、分页、分类返回，普通可应用投稿同时展示一键应用与 Web 应用，视频换脸仅展示 Web 应用，拼接视频不展示应用入口，且不展示留言入口。
- `修仙市集` 已缓存媒体优先用 Telegram file_id，file_id 失效后通过当前 R2/S3 URL resolver 刷新，不走旧 legacy MinIO bytes 主路径。
- `修仙市集` Bot 原生应用必须传 `source_post_id` 且 `allow_contribute=False`，复杂模板的一键应用必须 Web handoff，点击应用不直接增加 `applied_count`。
- QQCC main 只注册 quick image/video FSM；`快速换脸` 和 `AI绘图` 都必须复用 quick image FSM，不注册主 Bot `faceswap_fsm` 或 `edit_image_fsm`。
- `bot:qqcc` 能进入 task submission、active registry 和 recovery filter。
- 默认配置下现有菜单不变；关闭配置后按钮隐藏，旧按钮/旧 callback 回复 `功能暂未开放` 且不提交任务。
- QQCC 动图动态场景按 engine 提交：旧 `image_to_video` 无 LoRA 为 `custom_video`、带 LoRA 为 `video_lora`，`wan22_video_v2` 为 `wan22_video_v2`；v2 不支持附加模型。配置尾帧来源时先按被引用绘图场景的完整后处理链隐藏生成尾帧，再按首尾帧提交；额度预检覆盖绘图链加视频总费用，尾帧链任一步失败都不提交视频。场景提示词和展示名只作用 QQCC，不影响主 Bot。
- 主 Dashboard 不再出现 `懒人Bot配置` 导航；独立 QQCC Config Web 登录、加载、开关切换和保存 payload 有前端测试。
- compose/script 语法检查通过。
