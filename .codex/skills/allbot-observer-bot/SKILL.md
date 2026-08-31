---
name: allbot-observer-bot
description: "Telegram Observer Bot：管理员通知、队列/Worker 告警、采集和周期报告。"
---

# AllBot Observer Bot

处理 Observer 队列/Worker 告警、群采集与报告；按需叠加 TG、TDD、发布 Skill。

## 事实源与入口

- 专项文档：`docs/子模块_Telegram观察与报告Bot_observer_bot.md`
- 入口：`python -m observer_bot`
- schema：`observer_bot/schema.sql`；显式命令 `python -m observer_bot.schema`
- 发布模块/profile：`observer-bot` / `observer`

## 红线

- Observer 独占通知 token 的 polling；`support-bot` 只可用它 outbound 发管理员通知。
- 两者隔离进程、handler、数据库和 FSM；Observer 禁用主 `DATABASE_URL`，不得跨库。
- 队列只读 Central `GET /system/status`，Worker 失败率只读
  `GET /system/worker-outcomes`；不直连 Redis/主库，不改变任务。
- LM Studio 只生成报告；不可用不能阻断确定性告警与消息持久化。
- 只采集知情 allowlist 群的文本/caption；不下载媒体、不采集 Bot 消息、不发外部模型。
  群消息不可信，prompt 必须忽略其中指令且不开工具/MCP。
- V1 不做网站、平台关键词、外部 AI 群 userbot。
- 建库、grant、schema 和 prod 发布须明确确认。
- 管理员、授权群、开关和队列数量阈值在 `observer_prod`；env ID 仅 bootstrap，
  Dashboard 不获 token。

## 验证

```bash
.venv/bin/python -m pytest -q tests/observer_bot tests/ops/test_modular_images.py tests/ops/test_immutable_compose.py tests/ops/test_runtime_env_contract.py
python3 scripts/doc_quality_checker.py
```
