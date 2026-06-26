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
- Dashboard 配置 API：`dashboard/backend/routers/qqcc.py`
- Dashboard 配置页：`dashboard/frontend/src/components/QqccBotSettings.vue`
- 领域文档：`docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`

## 2. 功能范围
主菜单业务入口只能有 `快速脱衣`、`懒人P图` 和 `AI动图`。`AI动图` 是 QQCC 对 `menu.video_edit` 的专用显示文案，不要直接改共享 `menu.video_edit` 以免影响主 Bot。`快速脱衣` 必须位于主菜单，不再放入 `懒人P图` 子菜单。主菜单可额外有一个非生成入口 `前往主bot`；Telegram reply keyboard 不能直接承载 URL，因此点击该菜单项后由 QQCC Bot 回复主 Bot 的 inline URL 跳转按钮。

允许的 P 图入口：
- 快速自慰
- 随机换脸

`快速脱衣` 仍由 `get_quick_image_fsm_handler()` 承接。用户点击主菜单 `快速脱衣` 后进入两种懒人处理方式选择：
- `头像/半身补全`：复用原 `undress` 快速图生图流程，适合头像、半身照补全全身。
- `全身保脸重绘`：复用 Web 侧 `i2i_draw` / 局部重绘任务，适合全身照，强调真实质感与面部稳定。

允许的视频入口：
- 传教士
- 后入
- 口交
- 脱衣吐舌
- 近景口交

QQCC `AI动图` 的二级场景菜单必须挂在 Bot 回复消息下方，用 inline button 展示，每行最多 3 个；场景按钮 callback 前缀为 `qvid_mode:`，由 `get_quick_video_fsm_handler()` 直接承接并进入发送图片步骤。

注册的 FSM 只能是 `get_quick_image_fsm_handler()` 与 `get_quick_video_fsm_handler()`。不得注册 `faceswap_fsm`、高级图像、高级视频、充值、affiliate redeem 或 gallery 浏览入口。

## 2.1 管理后台配置
管理后台有 `懒人Bot配置` 页，配置存入 `runtime_checkpoints`，固定 key 为 `qqcc_lazy_bot_config:v1`，不新增数据库表。API：
- `GET /api/qqcc/config` 返回合并默认值后的有效配置。
- `PUT /api/qqcc/config` 规范化保存配置，未知 key 必须丢弃。

配置结构固定包含：
- `global_enabled`
- `main_buttons`: `quick_undress`, `photo_edit`, `video_edit`, `main_bot_link`
- `photo_buttons`: `masturbation`, `random_faceswap`
- `undress_methods`: `legacy`, `i2i_draw`
- `video_buttons`: `missionary`, `doggy`, `blowjob`, `undress_tongue`, `closeup_blowjob`
- `video_settings.resolutions`: `512p`, `720p`, `1024p`
- `video_settings.durations`: `5s`, `8s`, `10s`
- `prompts`: `undress`, `i2i_draw_quick_undress`, `masturbation`, `face_swap`, `perfect_video_insert`, `doggy_style`, `blowjob`, `undress_tongue`, `closeup_blowjob`

关闭功能后，新菜单必须隐藏对应按钮；旧 reply keyboard / 旧 callback 必须回复 `功能暂未开放` 并拒绝提交任务。画质/时长按钮同时受用户权限与 QQCC 配置过滤，仍保持 `1024p` 和 `10s` 互斥。`prompts` 空字符串表示回退当前 `prompts.ini`；非空覆盖只作用 QQCC，主 Bot 继续走原提示词。

## 3. 任务归属红线
QQCC Bot 必须设置 `application.bot_data["bot_client_type"] = "bot:qqcc"`，Bot 任务提交必须透传该值到 `process_and_submit_task(client_type=...)` 并写入 active task registry。

恢复规则：
- 主 Bot 恢复 `bot` 和 legacy 任务。
- QQCC Bot 只恢复 `bot:qqcc` 任务。

不得让 QQCC Bot 恢复或通知主 Bot 的任务，也不得让主 Bot 抢恢复 QQCC 任务。

## 4. 部署与密钥
token 只允许放在 ignored env 文件：
- 正式：`QQCC_BOT_TOKEN`
- 测试：`QQCC_BOT_TOKEN_TEST`
- 可选主 Bot 跳转：`QQCC_MAIN_BOT_URL` 或 `QQCC_MAIN_BOT_USERNAME`

不得把真实 token 写入仓库、docs、日志、工单或聊天记录。QQCC Bot 不启动 TON 轮询，不注册支付回调，不作为充值入口。测试环境没有独立 token 时，`qqcc-bot-test` 必须保持停止。

主 Bot 跳转按钮优先使用 `QQCC_MAIN_BOT_URL`，未配置时可用 `QQCC_MAIN_BOT_USERNAME` 自动生成 `https://t.me/<username>`；两者均未配置时不得硬编码主 Bot 地址。菜单项是否展示只受 QQCC `main_bot_link` 配置控制，用户点击后应回复“主 Bot 入口暂未配置”类提示，而不是提交生成任务。

正式启动或重建前必须有用户明确要求进入 QQCC 正式单服务更新。只单独更新正式 QQCC Bot 时优先使用 `scripts/update_cloud_prod_qqcc_bot.sh`；真实执行必须传 `--execute --confirm-prod --confirm-single-polling`，该路径只 build/up `qqcc-bot-prod`，不重建其它正式服务。用户已经明确说“QQCC 单服务更新/走单服务更新/单独更新 QQCC Bot”时，可视为当次正式与单 polling 操作确认，不要再要求逐字复述“没有第二个 polling 实例”；但若发现目标容器状态异常、疑似多实例、token/远端 env 异常、不是专用脚本路径，或要启动一个当前停止的新正式 QQCC 实例，必须停下并追问确认。

只更新管理后台 QQCC 配置页与 QQCC Bot 代码时，Dashboard 使用 `scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod --scope services --services "dashboard-backend-prod dashboard-frontend-prod" --skip-generation-maintenance`，QQCC 使用 `scripts/update_cloud_prod_qqcc_bot.sh --execute --confirm-prod --confirm-single-polling`。全程不得开启 `GENERATION_MAINTENANCE`，不得重建 Central/Web/Payment/主 Bot/Worker/RunPod。

## 5. 验证要求
至少覆盖：
- QQCC `/start` 只返回简化主菜单，且主菜单包含 `快速脱衣`、`懒人P图`、`AI动图`。
- QQCC `/start` 只返回简化主菜单，不额外发送主 Bot 跳转消息；配置主 Bot 跳转 env 时，点击菜单里的 `前往主bot` 后回复 inline URL 跳转按钮。
- P 图子菜单包含自慰、随机换脸，不包含快速脱衣和快速换脸。
- QQCC 点击快速脱衣后出现 `头像/半身补全` 与 `全身保脸重绘` 两个懒人选择，选择后只需发送图片。
- `AI动图` 点击后回复 inline 场景按钮，三个一行，包含五个懒人动图场景；点击场景 callback 不转圈并进入 quick video 发送图片步骤。
- QQCC main 只注册 quick image/video FSM。
- `bot:qqcc` 能进入 task submission、active registry 和 recovery filter。
- 默认配置下现有菜单不变；关闭配置后按钮隐藏，旧按钮/旧 callback 回复 `功能暂未开放` 且不提交任务。
- QQCC 专用提示词覆盖不影响主 Bot。
- Dashboard `懒人Bot配置` 导航、加载、开关切换和保存 payload 有前端测试。
- compose/script 语法检查通过。
