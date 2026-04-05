# 实施优先级表（公网 API + 局域网 Worker）

本文档是 [SYSTEM_OPTIMIZATION_GUIDE_PUBLIC_API_WORKERS.md](file:///home/hfy/APP/All_bot/SYSTEM_OPTIMIZATION_GUIDE_PUBLIC_API_WORKERS.md) 的压缩版，目标是把后续优化事项整理成一张可执行的优先级表，便于按阶段推进。

## 实施优先级总表

| 优先级 | 事项 | 目标 | 主要问题 | 预期收益 | 依赖关系 |
| --- | --- | --- | --- | --- | --- |
| P0 | 双向取消统一 | 保证 Bot / API / Worker 状态一致 | Dashboard 强制退款未同步取消后端任务，存在幽灵任务 | 先止损，避免算力浪费和状态错乱 | 无 |
| P0 | 任务类型可消费性检测 | 避免任务入队后无人接单 | API 不校验某类型当前是否有在线 Worker 支持 | 降低挂死单与误报 | 无 |
| P0 | 监控状态语义统一 | 保证 Dashboard 展示可信 | pending/running/cancelled 等状态映射不统一 | 运维判断更准确 | 无 |
| P1 | 短长轮询替代固定 2 秒轮询 | 降低公网空请求、缩短接单延迟 | Worker 当前固定 2 秒轮询 `/pop` | 减少无效请求，提升接单实时性 | 建议先完成 P0 |
| P1 | Dashboard 批量状态接口 | 消除跨服务 N+1 | Dashboard 逐个补查 `/status/{id}` 且只查前 20 个 | 降低 API 压力，监控更完整 | 建议先完成 P0 |
| P2 | 分型队列 | 消除按类型抢单时的全队列扫描 | 当前单一 pending 队列靠 `ZRANGE + HGET + ZREM` 匹配 | 提升调度效率，减少异构任务相互拖累 | 建议在 P1 后实施 |
| P2 | Worker 拉单退避策略 | 提升公网环境稳定性 | 长轮询在公网链路下仍可能受超时或代理限制影响 | 避免同时重连尖峰，增强容错 | 可与 P1 一起做 |
| P3 | 资源感知 heartbeat | 让调度知道节点真实负载 | 当前只上报 types/status/last_seen | 降低 OOM 风险，优化重任务分配 | 依赖 P2 效果更好 |
| P3 | 资源感知调度 | 把重任务优先派给强节点 | 当前只按类型是否匹配分发 | 提升吞吐与稳定性 | 依赖资源 heartbeat |
| P4 | Worker 输入链路瘦身 | 减少下载后再上传的冗余 | MinIO -> 本地 -> 内存 -> ComfyUI 上传 | 降低 I/O 与内存占用 | 独立推进 |
| P4 | Worker 输出链路流式化 | 减少结果双副本驻留 | ComfyUI `/view` -> bytes -> `BytesIO` -> MinIO | 对大图/视频收益明显 | 独立推进 |
| P4 | API 结果分发优化 | 降低下载临时文件成本 | API `/image` `/video` 先落本地临时文件 | 改善大文件分发效率 | 独立推进 |

## 每阶段建议

| 阶段 | 建议先做什么 | 原因 |
| --- | --- | --- |
| 第一阶段 | 双向取消统一、类型可消费性检测、监控状态语义统一 | 先保证系统正确性，不让优化建立在错误状态之上 |
| 第二阶段 | 短长轮询、Dashboard 批量状态接口 | 这两项改动成本相对可控，收益直接 |
| 第三阶段 | 分型队列、拉单退避策略 | 这是调度层的结构升级，适合在 P1 稳定后推进 |
| 第四阶段 | 资源 heartbeat、资源感知调度 | 适合异构显卡和公网混合 Worker 环境 |
| 第五阶段 | Worker/API I/O 流式化 | 中期优化项，对大图与视频任务收益更大 |

## 当前代码对应位置

| 事项 | 关键代码位置 |
| --- | --- |
| Worker 固定 2 秒轮询 | [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent1/agent_main.py#L423-L448) |
| API 单队列与类型扫描 | [queue_manager.py](file:///home/hfy/APP/All_bot/backend/app/queue_manager.py#L55-L92) |
| Dashboard 活跃任务逐个补查状态 | [system.py](file:///home/hfy/APP/All_bot/dashboard/backend/routers/system.py#L96-L160) |
| Dashboard 强制退款未双向取消 | [system.py](file:///home/hfy/APP/All_bot/dashboard/backend/routers/system.py#L21-L53) |
| Bot 僵尸任务会同步取消后端 | [clean_zombies.py](file:///home/hfy/APP/All_bot/clean_zombies.py#L8-L18) |
| Worker heartbeat 字段较少 | [agent.py](file:///home/hfy/APP/All_bot/backend/app/routers/agent.py#L40-L44) |
| Worker 输入输出 I/O 冗余 | [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent1/agent_main.py#L263-L277), [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent1/agent_main.py#L365-L406) |

## 一句话排序

1. 先修正确性
2. 再降公网空转请求
3. 再重构调度队列
4. 然后做资源感知
5. 最后优化大文件 I/O
