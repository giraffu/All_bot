# Legacy 正式执行面只读审计

审计时间：2026-07-15（Asia/Shanghai）

范围：Central Worker 列表/control/heartbeat/current task、主服务器 legacy agent/relay 容器、最近 relay 流量，以及 LAN AIO/RunPod 替代容量。全程只读，没有 stop/start/recreate/delete 或配置写入。

## 结果

- Central `/system/workers` 当次快照没有 fresh `cloud_prod_worker_*`；当前可接单执行面是 LAN AIO 与 RunPod。
- 主服务器仍保留 `cloud-prod-comfy-agent-1/5/7/4/6` 等 legacy 容器，其中部分 exited、部分 paused；它们不构成当前健康接单容量。
- `cloud-prod-worker-relay` 仍为 running，但最近 30 分钟日志筛选未发现对应 legacy agent 的新任务转发或错误流量。
- `scripts/lan_aio_fleet_prod_ops.py status --include-disabled` 显示声明式 LAN AIO active slots 可见；Central 同时存在健康 RunPod 容量。具体瞬时数量以发布/故障窗口重新读取为准，不在本报告写死。

## 迁移结论

传统 legacy Worker 当前没有接受新任务的证据，但 paused 容器与 Relay 仍是现有回滚态。因此：

- schema v2 正式控制面清单不声明测试 `worker-agent`、`worker-relay` 或 `python-worker-base`。
- 现有正式 Relay/legacy 容器继续 dormant 保留；本阶段不 down、不 delete、不改启动策略。
- 正式下线必须在未来独立变更窗口重新执行同一只读审计，并确认所有 legacy task type 都有健康 LAN AIO/RunPod 容量后单独授权。
