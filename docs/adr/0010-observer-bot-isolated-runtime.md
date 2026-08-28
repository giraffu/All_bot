# ADR 0010：Observer Bot 使用独立运行时与逻辑数据库

日期：2026-08-29

## Status

Accepted。

## Context

管理员通知、AllBot 队列观测、授权群采集和本地 LLM 报告都属于 Telegram 生态，
但生命周期、故障模式和数据保留策略不同于客服工单。可选方案包括继续扩展客服
Bot、拆成多个微服务，或用一个独立 Observer 进程承载 V1。

现有云主机和 managed PostgreSQL 集群容量充裕，本地 LM Studio 需要保持在本地
GPU 机器上。目标是减少新基础设施，同时避免报告或本地网络故障影响客服链路。

## Decision

- 保持客服 Bot 不变；V1 新增一个独立 `observer-bot` token、进程和发布模块。
- Observer 与其它服务共用现有云主机和 PostgreSQL 集群，但使用独立逻辑数据库、
  runtime role 和三张自有表，不跨库读取业务表。
- 队列状态只从 Central `GET /system/status` 读取；不直连 Redis 和任务表。
- 一个进程同时处理 polling、确定性队列告警、授权群采集和报告调度，不引入
  Redis/Celery/消息总线。
- LM Studio 通过 Tailscale 上的 OpenAI-compatible HTTP 调用，只是报告依赖；
  不参与队列告警，也不公网暴露。
- V1 不做网站或外部平台监听。

## Alternatives

- 扩展客服 Bot：容器更少，但报告、群隐私和本地 LLM 故障会扩大客服链路影响面。
- 每项能力一个子 Bot/worker：隔离更细，但 V1 需要额外调度、队列和部署治理，
  复杂度与当前规模不匹配。
- 新增独立服务器或 PostgreSQL 集群：物理隔离更强，但当前容量没有必要，成本和
  运维面更大。

## Consequences

客服链路与 Observer 故障相互隔离，并保留后续拆分报告 worker 的 seam；同时仍
共享云主机和数据库集群的物理故障域。Observer 的数据库创建、role/grant、schema
和生产部署成为独立 mutation，需要单独备份、监控和明确授权。
