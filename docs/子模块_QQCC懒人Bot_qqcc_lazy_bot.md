# 子模块: QQCC 懒人 Bot (QQCC Lazy Bot)

## 1. 范围与定位
QQCC 懒人 Bot 是主业务 Bot 的独立 Telegram polling 入口，代码位于仓库根目录 `qqcc_bot/`，正式名称为 `@QQCC666_bot`。它只提供简化生成入口，用户、灵石、会员、历史、并发锁、队列、对象存储、worker 与结果回流全部复用现有生产数据和任务链路。

它不是主 Bot 的完整副本，不承载充值、affiliate 菜单、gallery 浏览、Web 登录、支付回调或高级视频/高级图像入口。

## 2. 功能边界
主菜单只包含：
- `快速脱衣`
- `懒人P图`
- `视频创作`

`懒人P图` 只开放：
- 快速自慰
- 随机换脸

`快速脱衣` 必须放在主菜单，不放入 `懒人P图` 子菜单。它仍只走 `get_quick_image_fsm_handler()`；用户点击主菜单 `快速脱衣` 后进入两种懒人处理方式选择：
- `头像/半身补全`：复用原 `undress` 快速图生图流程，头像、半身照也可直接发图。
- `全身保脸重绘`：复用 Web 侧 `i2i_draw` / 局部重绘任务，建议上传全身照，质感更真实且更稳定保留面部。

明确不开放 `快速换脸` / `faceswap_fsm` 双图换脸入口。

`视频创作` 只开放五个懒人动图场景：
- 传教士
- 后入
- 口交
- 脱衣吐舌
- 近景口交

注册的 FSM 只允许：
- `get_quick_image_fsm_handler()`
- `get_quick_video_fsm_handler()`

不得注册 `faceswap_fsm`、`txt2img_fsm`、`edit_image_fsm`、`image_to_video_fsm`、`wan22_video_v2_fsm`、`ltx_video_fsm`、`scail2_video_fsm`、充值、affiliate redeem 或 gallery 浏览菜单入口。

## 3. 代码入口
- `qqcc_bot/main.py`：独立启动入口，读取 `QQCC_BOT_TOKEN` 或 `QQCC_BOT_TOKEN_TEST`，设置 `bot_client_type=bot:qqcc`，注册最小 handler 集。
- `qqcc_bot/keyboards.py`：QQCC 专用主菜单、P 图子菜单、视频子菜单。
- `qqcc_bot/commands.py`：QQCC `/start` 与 `/cancel`，复用用户创建和准入逻辑，返回简化菜单。
- `qqcc_bot/prompt_handlers.py`：只路由 `menu.photo_edit`、`menu.video_edit`、`menu.main_menu`、`menu.back_main`。
- `qqcc_bot/callback_handler.py`：只导入任务取消、结果评分、随机换脸再来一张等必要 callback 注册模块。
- `src/handlers/fsm/quick_image_fsm.py`：在 `bot_client_type=bot:qqcc` 时把主菜单 `快速脱衣` 转为两种处理方式选择；其它 Bot 仍保持原快速脱衣直达流程。

主 Bot 入口仍是 `src/bot_main.py`。不要在 `qqcc_bot/` 中导入 `src.bot_main`，否则会把主 Bot 的完整 handler 面一起注册进来。

## 4. 任务来源归属
Telegram Bot 任务默认来源为 `client_type="bot"`。QQCC Bot 在 `application.bot_data["bot_client_type"]` 写入 `bot:qqcc`，`run_bot_task_application(...)` 读取该值并透传到 `process_and_submit_task(client_type=...)`。

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

云测试 compose service：
- service: `qqcc-bot-test`
- container: `cloud-qqcc-bot-test`
- profile: `qqcc-bot`
- token env: `QQCC_BOT_TOKEN_TEST`

token 只允许放在 ignored env 文件，例如 `.env.cloud.prod` 或 `.env.cloud.test`。不得写入仓库、docs、日志、工单、`docker compose config` 输出或聊天记录。若 token 曾暴露，应在正式上线前轮换。

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

该脚本默认 dry-run；真实执行必须确认正式环境和全网单 polling。它只同步代码、按需同步 env、执行只读 preflight、重建并启动 `qqcc-bot-prod`，然后验证 `cloud-qqcc-bot-prod` 状态；不写生成维护标记、不等待队列 drain、不重建 Central/Web/Payment/Dashboard/主 Bot/Worker/RunPod、不操作 Cloudflare Pages/DNS/边缘路由。

完整云正式控制面更新仍默认不碰 QQCC Bot；若需要随控制面一起重建 QQCC Bot，必须显式传：

```bash
scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod --qqcc-bot-mode start
```

正式启动前必须确认全网没有第二个 `@QQCC666_bot` polling 实例，并确认生产 token 已在远端 `.env.cloud.prod` 配置。没有用户明确确认上线前，不要启动生产容器。

## 7. 最小验证
代码变更至少跑：

```bash
pytest tests/qqcc_bot/test_qqcc_bot_entrypoint.py \
  tests/services/test_task_service_flow.py \
  tests/services/test_recovery_service.py -q
bash -n scripts/update_cloud_test_with_maintenance.sh \
  scripts/update_cloud_prod_with_maintenance.sh \
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

QQCC 快速脱衣入口至少覆盖：
- `/start` 主菜单展示 `快速脱衣`，`懒人P图` 子菜单不再展示 `快速脱衣`。
- 点击主菜单 `快速脱衣` 先展示 `头像/半身补全` 与 `全身保脸重绘`。
- `头像/半身补全` 进入 `undress`，`全身保脸重绘` 进入 `i2i_draw`。
- 两个分支都保持“选择按钮后只发送 1 张图片即可提交”的懒人交互。
