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
- 领域文档：`docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`

## 2. 功能范围
主菜单只能有 `懒人P图` 和 `视频创作`。

允许的 P 图入口：
- 快速脱衣
- 快速自慰
- 随机换脸

允许的视频入口：
- 传教士
- 后入
- 口交
- 脱衣吐舌
- 近景口交

注册的 FSM 只能是 `get_quick_image_fsm_handler()` 与 `get_quick_video_fsm_handler()`。不得注册 `faceswap_fsm`、高级图像、高级视频、充值、affiliate redeem 或 gallery 浏览入口。

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

不得把真实 token 写入仓库、docs、日志、工单或聊天记录。QQCC Bot 不启动 TON 轮询，不注册支付回调，不作为充值入口。测试环境没有独立 token 时，`qqcc-bot-test` 必须保持停止。

正式启动或重建前必须用户明确确认，并确认全网没有第二个 `@QQCC666_bot` polling 实例。只单独更新正式 QQCC Bot 时优先使用 `scripts/update_cloud_prod_qqcc_bot.sh`；真实执行必须传 `--execute --confirm-prod --confirm-single-polling`，该路径只 build/up `qqcc-bot-prod`，不重建其它正式服务。

## 5. 验证要求
至少覆盖：
- QQCC `/start` 只返回简化主菜单。
- P 图子菜单包含脱衣、自慰、随机换脸，不包含快速换脸。
- 视频子菜单包含五个懒人动图场景。
- QQCC main 只注册 quick image/video FSM。
- `bot:qqcc` 能进入 task submission、active registry 和 recovery filter。
- compose/script 语法检查通过。
