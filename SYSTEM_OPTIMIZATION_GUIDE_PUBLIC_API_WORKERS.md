# Telegram Bot 系统优化指南（公网 API + 局域网 Worker 约束版）

本文档基于当前实际代码与新的网络前提重新梳理优化方向：

- 部分 Worker 部署在局域网或异地机器上
- 这些 Worker 只能主动访问公网暴露的 Central API / MinIO
- Central API 不能主动回连 Worker
- 本文只讨论后续优化方案，不涉及立即改代码

---

## 1. 先回答核心问题：这种网络条件下，能不能做长轮询？

**可以做。**

原因是长轮询并不要求 API 主动连接 Worker，也不要求 Worker 暴露公网端口。它的本质是：

1. Worker 主动向公网 API 发起一个 HTTP 请求
2. 如果暂时没有任务，API 不立即返回，而是把这个请求挂住一小段时间
3. 一旦有任务可分配，就立刻在这条请求上返回任务
4. 如果等待超时仍没有任务，再返回空结果，Worker 立即发起下一次请求

也就是说，**连接方向始终是 Worker -> 公网 API 的出站连接**，这与当前“Worker 只能访问公网 API”的前提并不冲突。

### 1.1 真正需要关注的不是“能不能连”，而是“公网链路能挂多久”

在当前代码里，Worker 发往 Master API 的客户端超时是 30 秒，见：

- [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent1/agent_main.py#L52-L56)

这意味着如果后续引入长轮询，就不能无脑把请求挂到 60 秒、120 秒，而要同时考虑：

- Worker 侧 `httpx.AsyncClient(timeout=30.0)` 的读超时
- 公网 Nginx / 反向代理 / CDN / WAF 的空闲连接超时
- 公网链路抖动带来的偶发断连
- Worker 数量增加后，API 持有大量挂起请求时的连接数与内存占用

### 1.2 结论不是“不能长轮询”，而是“不能做无限制长轮询”

在当前部署前提下，更合理的方案是：

- 使用 **有边界的短长轮询**
- 单次等待时间建议控制在 **15~20 秒**
- 超时后返回空结果，由 Worker 立即重连
- 由 API 或网关明确配置更长一点的读超时，例如 30~60 秒

这样既保留长轮询降低空转请求的收益，又不会过度依赖公网链路的超长连接稳定性。

---

## 2. 当前代码现状与这项约束的关系

结合现有实现，当前系统的关键事实如下：

### 2.1 Worker 当前仍是固定 2 秒短轮询

Worker 在 `poll_loop()` 中固定请求 `/api/agent/task/pop`，没任务就 sleep 2 秒：

- [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent1/agent_main.py#L423-L448)

这套模式在公网部署下有两个问题：

- 空闲时会持续制造无效公网请求
- 新任务入队后的接单延迟受轮询间隔影响，最坏接近 2 秒

### 2.2 API 当前仍是单一 pending 队列 + 类型扫描

当前队列管理器仍使用一个全局 `comfy:queue:pending`，按类型拉任务时采用：

- `ZRANGE` 批量取出任务
- 逐个 `HGET task.type`
- 命中后 `ZREM`

见：

- [queue_manager.py](file:///home/hfy/APP/All_bot/backend/app/queue_manager.py#L55-L92)

这意味着即使你把轮询从短轮询改成长轮询，**任务匹配效率低**这个根问题仍然存在。长轮询只能减少空请求，不能解决类型扫描带来的 O(N) 退化。

### 2.3 Dashboard 侧仍有跨服务 N+1

Dashboard 活跃任务页先读 Bot Redis 的 `active_tasks`，再逐个请求 API `/status/{id}` 补状态：

- [system.py](file:///home/hfy/APP/All_bot/dashboard/backend/routers/system.py#L96-L160)

而且当前只补查前 20 个 `backend_task_id`：

- [system.py](file:///home/hfy/APP/All_bot/dashboard/backend/routers/system.py#L115-L126)

这说明后续即使优化 Worker 拉单链路，Dashboard 的可扩展性问题仍然需要单独处理。

### 2.4 Worker 资源上报仍然过于粗糙

当前 heartbeat 只上报：

- `agent_id`
- `types`
- `status`

见：

- [agent.py](file:///home/hfy/APP/All_bot/backend/app/routers/agent.py#L40-L44)
- [queue_manager.py](file:///home/hfy/APP/All_bot/backend/app/queue_manager.py#L208-L217)

没有显存、系统负载、内存、GPU 利用率等指标，因此 API 无法做资源感知调度。

### 2.5 Worker 的输入输出链路仍有明显 I/O 冗余

当前 Worker 处理输入素材时，会：

1. 从 MinIO 下载到本地
2. 再整文件读入内存
3. 再通过 ComfyUI HTTP 上传一次

见：

- [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent1/agent_main.py#L263-L277)

输出结果时，又会：

1. 从 ComfyUI `/view` 拉取整个文件
2. 放入 `BytesIO`
3. 再上传到 MinIO

见：

- [agent_main.py](file:///home/hfy/APP/All_bot/workers/comfy_agent1/agent_main.py#L365-L406)

这部分与“公网 API / 异地 Worker”约束无直接冲突，但对大文件任务和弱机器更敏感。

---

## 3. 在“只能访问公网 API”的前提下，长轮询应该怎么设计

### 3.1 推荐方案：公网 HTTPS 上的短长轮询

推荐把当前 `/api/agent/task/pop` 改造成：

- 有任务：立即返回 `200`
- 暂时无任务：等待最多 `15~20 秒`
- 超时仍无任务：返回空结果，建议使用 `204` 或显式 JSON 空包
- Worker 收到空结果后立即重新发起下一次请求

### 3.2 为什么推荐 15~20 秒，而不是更长

因为当前链路不是内网直连，而是公网链路，通常还会经过：

- Nginx
- 反向代理
- 可能存在的 CDN / 网关 / 云负载均衡

在这种环境下：

- 5 秒太短，收益不明显
- 60 秒以上对代理超时、链路稳定性更敏感
- 15~20 秒通常是兼顾“减少空请求”和“控制失败恢复时间”的稳妥区间

### 3.3 对当前系统需要同步调整的点

如果上长轮询，至少要一起调整下面这些地方：

- Worker `master_client` 的 timeout 不能小于长轮询等待时间
- Nginx `proxy_read_timeout` / `proxy_send_timeout` 要高于长轮询等待时间
- API 侧要限制挂起请求数，避免空闲 Worker 太多时把连接池拖满
- Worker 在重连时增加轻微随机抖动，避免同时超时同时重连形成尖峰

### 3.4 不建议的做法

- 不建议把长轮询做成无上限等待
- 不建议仍然使用当前的“空队列直接 404”语义
- 不建议在公网链路上直接把等待时间拉到非常长

---

## 4. 如果公网链路对长轮询不友好，有哪些替代方案？

如果后续发现某些公网网关、CDN 或安全设备对长连接支持不好，那么推荐降级到以下方案，而不是完全回退到固定 2 秒短轮询。

### 4.1 方案 A：自适应轮询

Worker 在空闲时逐步扩大间隔，例如：

- 连续空 3 次：2 秒
- 连续空 10 次：5 秒
- 连续空 30 次：10 秒
- 有任务后立即恢复到快速模式

优点：

- 无需依赖长连接稳定性
- 实现简单

缺点：

- 峰值任务到来时仍有接单延迟

### 4.2 方案 B：短长轮询 + 自适应退避混合

这是更推荐的公网方案：

- 默认做 15~20 秒短长轮询
- 如果连续出现超时、代理断连、429 或 5xx
- Worker 临时退回到 3~5 秒轮询
- 稳定后再恢复短长轮询

优点：

- 对公网环境更稳
- 比纯短轮询省请求
- 比纯长轮询更抗代理异常

### 4.3 方案 C：WebSocket 常连

理论上也可行，因为仍然是 Worker 主动连公网 API。

但在当前项目阶段并不推荐优先做，原因是：

- 需要新增连接管理、断线重连、状态同步逻辑
- 对现有 API 代码侵入更大
- 真正的主瓶颈目前不在“协议类型”，而在“单队列 + 类型扫描”

结论：**先做短长轮询，不要优先切 WebSocket。**

---

## 5. 基于新约束的优化路线图

下面按优先级重新梳理。

### P0：先补正确性与状态一致性

这部分优先级最高，因为不先保证正确性，后续优化会放大错误。

#### 5.1 统一“双向取消”语义

当前 Bot 的僵尸清理脚本会调用 API 取消后端任务：

- [clean_zombies.py](file:///home/hfy/APP/All_bot/clean_zombies.py#L8-L18)
- [clean_zombies.py](file:///home/hfy/APP/All_bot/clean_zombies.py#L45-L50)

但 Dashboard 的管理员退款接口只删 Bot 侧活跃任务并退款，没有同步取消 API 队列中的任务：

- [system.py](file:///home/hfy/APP/All_bot/dashboard/backend/routers/system.py#L21-L53)

这会导致：

- Bot 侧显示任务没了
- API/Worker 侧任务仍可能继续执行
- 出现幽灵任务和算力浪费

后续第一件事应当是把所有“人工取消 / 清理 / 退款”入口统一到同一套双向取消逻辑。

#### 5.2 增加“任务类型无人消费”检测

当前 API 支持的任务类型包括：

- `img2img`
- `face_swap`
- `video_insert`
- `video_edit`
- `t2i-pornmaster-turbo`

见：

- [models.py](file:///home/hfy/APP/All_bot/backend/app/models.py#L12-L18)

但 Worker 是否真的声明支持这些类型，完全依赖各自配置。建议后续增加：

- 任务入队前校验是否存在在线可消费 Worker
- 或至少在监控中明确标注“该类型当前无人接单”

#### 5.3 统一状态枚举与监控语义

后续应统一：

- pending
- running
- done
- error
- cancelled

避免 Dashboard 把未知状态误判为 generating，导致运维误读。

---

### P1：上线“适配公网环境”的短长轮询

这是第一批值得落地的性能优化。

#### 5.4 目标

- 减少空闲 Worker 对公网 API 的无效请求
- 缩短任务突发到来时的平均接单延迟
- 保持与现有“Worker 主动拉任务”的模型兼容

#### 5.5 推荐设计

- `/api/agent/task/pop` 支持最长 15~20 秒挂起
- 请求结束后立即重连
- 使用连接级轻微随机抖动，避免同一时刻集体重连
- 保留超时后的快速恢复能力

#### 5.6 需要同步改造的配置

- Worker HTTP 超时
- 公网 API 网关超时
- API 进程的连接上限与并发承载
- 日志级别与空请求日志噪音控制

#### 5.7 预期收益

- 公网空请求显著下降
- Worker 空闲期更安静
- 新任务更快被领取

---

### P2：把单队列改为分型队列

这是调度层的关键结构升级。

#### 5.8 当前问题

当前 `dequeue_task()` 在按类型取单时仍需扫描全局队列：

- [queue_manager.py](file:///home/hfy/APP/All_bot/backend/app/queue_manager.py#L66-L92)

当某一类任务大量积压时，会拖慢其他类型 Worker 的匹配速度。

#### 5.9 推荐方案

按类型拆分 pending 队列，例如：

- `comfy:queue:pending:img2img`
- `comfy:queue:pending:face_swap`
- `comfy:queue:pending:video_insert`
- `comfy:queue:pending:video_edit`
- `comfy:queue:pending:t2i-pornmaster-turbo`

Worker 只在自己支持的队列集合中取任务。

#### 5.10 分型队列在公网场景下的额外价值

因为远程 Worker 访问的是公网 API，所以每一次无效匹配都更贵。分型队列能让：

- API 更快找到合适任务
- Worker 更少收到“空等待后仍无可执行任务”的结果
- 后续更容易做按类型容量管理和告警

---

### P3：为异构 Worker 增加资源感知调度

局域网、异地、公网访问、不同显卡型号混跑时，资源感知调度比纯类型调度更重要。

#### 5.11 heartbeat 需要新增的字段

建议在后续 heartbeat 中补充：

- GPU 总显存
- GPU 可用显存
- GPU 利用率
- 系统内存可用量
- 当前负载
- 本节点支持的模型或能力标签

#### 5.12 API 调度决策建议

调度顺序建议变成：

1. 先按任务类型过滤可执行节点
2. 再按资源门槛过滤
3. 最后按负载、空闲度、历史稳定性排序

#### 5.13 目标

- 避免弱卡连续接重任务
- 降低 OOM 风险
- 提高整体稳定性

---

### P4：优化 Worker 的输入输出 I/O 链路

这部分属于中期收益项，尤其对视频任务有价值。

#### 5.14 输入侧优化

如果 Worker 与本地 ComfyUI 共享输入目录，优先考虑：

- 直接把 MinIO 文件下载到 ComfyUI input 目录
- 工作流中只传文件名
- 尽量避免再次通过 ComfyUI `/upload/image` 上传

#### 5.15 输出侧优化

优先考虑：

- 从 ComfyUI 结果接口做流式读取
- 流式写入 MinIO
- 避免 `bytes -> BytesIO -> put_object` 的双副本模式

#### 5.16 API 结果下发优化

当前 `/image/{task_id}`、`/video/{task_id}` 仍会先从 MinIO 拉到临时文件再返回：

- [main.py](file:///home/hfy/APP/All_bot/backend/app/main.py#L252-L320)

后续可以考虑：

- 流式代理
- 或签名 URL
- 或让 Bot 直接从可信下载入口取文件

---

### P5：优化 Dashboard 的聚合查询

这是运维体验和系统可观测性的关键项。

#### 5.17 当前问题

Dashboard 当前依赖逐个查 `/status/{id}`，存在跨服务 N+1，而且只查前 20 个：

- [system.py](file:///home/hfy/APP/All_bot/dashboard/backend/routers/system.py#L115-L126)

#### 5.18 推荐方案

优先在 API 侧增加：

- `/status/batch`

或更进一步直接提供：

- 面向 Dashboard 的聚合状态接口

这样 Dashboard 一次请求即可获取：

- 批量任务状态
- queue_pos
- progress
- worker_id

#### 5.19 为什么这项在公网 Worker 体系里更重要

因为 Worker 分布更分散后，运维更依赖 Dashboard 判断：

- 哪类任务没人接
- 哪个 Worker 掉线
- 哪个任务卡在 pending
- 哪个任务 running 但无进度

所以 Dashboard 不能长期依赖当前这种拼装式补查模式。

---

## 6. 新版优先级排序

基于“部分 Worker 只能访问公网 API”的前提，推荐优先级如下：

### 第一梯队

1. 统一双向取消与状态一致性
2. 短长轮询替代固定 2 秒短轮询
3. Dashboard 批量状态接口

### 第二梯队

4. 分型队列
5. 无消费者任务类型检测
6. 监控状态枚举统一

### 第三梯队

7. 资源感知 heartbeat 与调度
8. Worker 输入输出链路流式化
9. API 结果下载链路优化

---

## 7. 最终结论

在“Worker 只能主动访问公网 API”的前提下：

- **长轮询仍然可行**
- 但应做成 **有边界的短长轮询**
- 真正不适合的是“无限制长轮询”，而不是长轮询本身

同时要明确：

- 长轮询只能解决“空转请求过多”和“接单延迟”问题
- 它**不能替代**分型队列、批量状态接口、资源感知调度这些结构性优化

因此后续最合理的路线是：

1. 先补正确性和双向取消
2. 再上适配公网环境的短长轮询
3. 然后推进分型队列与 Dashboard 批量状态接口
4. 最后再做资源感知与 I/O 深度优化

这条路线既兼容你现在的公网 / 局域网混合 Worker 形态，也能尽量避免一次性做太重的架构改造。
