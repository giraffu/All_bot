# ADR 0002: QQCC 用户私有 Bot 使用多租户 Webhook 运行时

日期：2026-07-12

## Status

Accepted

## Context

官方 QQCC 懒人 Bot 是单 token、单 Application 的 Telegram long polling 服务。用户私有 Bot 需要在 50–500 个租户规模下复用同一业务功能，同时保证每个 owner 只有一个绑定、配置/任务/结果严格隔离、管理员可禁用、token 永不明文暴露。为每个 token 常驻一个 polling 进程会放大连接、内存、部署和双 polling 风险，也不利于统一接入、去重和恢复。

## Decision

- 官方 QQCC Bot 保持 long polling；所有用户私有 Bot 统一使用 Telegram HTTPS webhook，两者互斥。
- Web API 只负责校验 public ID、secret header、Bot 状态和 update 结构，再通过 Redis Lua 原子去重并写 stream，快速返回 2xx/503。
- 独立 private worker 通过 consumer group 消费 update，使用共享 QQCC Application factory 按租户注入独立配置和 `client_type=bot:qqcc-private:<id>`；不同 Bot 并发，同一 Bot 顺序处理。
- 凭据使用版本化 AES-GCM 保存，webhook secret 与 token 指纹只保存不可逆 hash/HMAC；管理接口不暴露 ciphertext 或任何可复原凭据。
- owner 与 Telegram Bot ID 使用数据库唯一约束；管理员禁用是高优先级状态，不能被 owner token 轮换或恢复覆盖。
- Owner WebApp 使用短期一次性 ticket 换独立 JWT，并通过单独公开 Host 暴露；管理员 Host 继续由 Cloudflare Access 保护，Nginx 按 Host 拒绝公开域名上的管理员 API。

## Alternatives Considered

- 每个私有 Bot 独立 polling 容器：隔离直观，但 50–500 个租户会产生大量常驻进程/连接，扩容和单 token 双 polling 风险高。
- 所有 Bot 在一个进程内直接处理 webhook：减少组件，但 Web API 请求会承担 Telegram FSM/任务提交延迟，无法可靠快速响应或用 stream 承接突发流量。
- 保存 token 明文或只依赖数据库磁盘加密：实现简单，但管理、备份和误日志泄漏边界不足，无法满足管理员永远不可查看 token 的约束。
- 为私有 Bot 建立独立余额：隔离强，但会改变 AllBot 统一用户/账本语义，且访客无法自然按自己的会员与余额使用。

## Consequences

- 正向：一个 worker 池可承接大量租户；Webhook 可去重、背压和重试；官方/私有任务恢复按 exact client type 隔离；配置与凭据边界可审计。
- 代价：Redis stream、consumer pending 回收、Application 生命周期、keyring 轮换、Webhook/Host 运维成为新增长期职责。
- 风险：Redis 故障会让 webhook 返回 503 并由 Telegram 重试；keyring 丢失会使 token 不可恢复；公开 owner Host 必须严格限制路由并防 ticket 重放。
- Rollout：必须先通过 Alembic 单 head 与云测试验证；正式 migration、worker 启用、生产 webhook 和 Cloudflare public hostname 都需要明确生产发布确认。

## References

- `docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md`
- `docs/子模块_QQCC懒人Bot_qqcc_lazy_bot.md`
- `docs/子模块_生成任务全链路_task_full_chain.md`
- `.codex/skills/allbot-qqcc-lazy-bot/SKILL.md`
- `.codex/skills/allbot-ops-deployment/SKILL.md`
