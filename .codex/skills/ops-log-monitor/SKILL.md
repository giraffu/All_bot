---
name: "ops-log-monitor"
description: "Monitors system logs across environments, analyzes exceptions, and generates incident reports. Invoke when user asks to monitor logs, check errors, or troubleshoot bugs."
---

# Ops Log Monitor & Bug Troubleshooter

This skill is designed to automatically execute system log monitoring, anomaly detection, and deep analysis without cluttering the conversation with raw logs.

## Workflow Instructions

When invoked to perform log monitoring or bug troubleshooting, strictly follow these steps:

### 1. 日志采集与监控（静默执行）
- **执行采集脚本**：优先在项目根目录运行预置脚本 `bash collect_logs.sh 15`（15 代表提取过去 15 分钟的日志，可根据用户要求的时长调整参数）。
- **脚本缺失时的等价采集**：若当前仓库没有 `collect_logs.sh`，不要停止排障；直接使用只读命令采集目标容器最近 15-30 分钟日志，并用 `grep`/Python 做脱敏聚合。云正式当前重点容器为 `cloud-central-api-prod`、`cloud-web-api-prod`、`cloud-tg-bot-prod`、`cloud-dashboard-backend-prod`、`cloud-payment-api-prod`、`cloud-imgproxy-prod`，本地 worker 为 `cloud-prod-worker-relay` 与 `cloud-prod-comfy-agent-1..7`。
- **读取过滤数据**：脚本会自动采集目标容器（如 `tg-bot`, `web-api` 等）的日志，并提取所有的 ERROR、WARN、Exception 等异常写入临时文件。若使用等价采集，请只保留聚合后的计数、类别、端点和脱敏示例，不要在对话或报告中输出原始 presigned URL、密钥、Token 或大段日志。
- **排查双边缘节点故障**：当涉及网络层、跨域（CORS）、文件上传失败（413 Payload Too Large）、或者请求根本未到达后端时，**必须**使用 SSH 检查以下两个边缘节点的日志：
  - **Web 前端与流量转发节点** (`100.88.57.122` / `154.17.30.113`)：执行指令 `ssh -i frontend/ssh_key/id_rsa.pem root@100.88.57.122 "df -h /; systemctl is-active nginx tailscaled; tail -n 100 /var/log/nginx/error.log"` 检查容量、Nginx 与代理报错。该节点根盘曾接近满盘，排障时必须先看磁盘。
  - **Telegram Local API 节点** (`69.63.220.115`)：当出现 `telegram.error.TimedOut`、大文件下载 404/403 等异常时，先执行 `nc -vz -w 5 69.63.220.115 8081` 与 `nc -vz -w 5 69.63.220.115 8082`。当前主服务器未配置该节点可用 SSH key；只有补齐 SSH 后，才执行 `ssh root@69.63.220.115 "docker logs --tail 100 tg-local-api"` 或检查 HTTP 文件服务器日志，不能在未登录时声称已检查容器日志。
- **排查后端数据库慢查询与连接池**：当出现 `110 Connection timed out` 且后端日志无明显应用报错时，**必须**排查 PostgreSQL 连接池是否被耗尽。使用 `docker exec -i postgres-server psql -U postgres -d bot_db -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"` 检查 `idle in transaction` 的数量。若发现大量卡死进程，可使用 `ALTER SYSTEM SET idle_in_transaction_session_timeout = '60000';` 进行熔断恢复，并配置 `log_min_duration_statement = '1000'` 追踪慢查询。
- **执行要求**：在此期间仅做观察与分析，**绝对不要修改任何代码**。请不要在对话窗口中打印原始的日志流。

#### 1.1 云正式 Web 卡顿与负载巡检顺序
当用户反馈正式 Web 卡顿、生成排队、Dashboard 卡顿或“云端负载高”时，按下面顺序拆解，不要只看单一容器 CPU：

1. **云控制面基础资源**：`ssh allbot-do-sgp1-control 'uptime; free -h; df -hT -x tmpfs -x devtmpfs /; docker ps; docker stats --no-stream ...'`。若云内 `100.107.220.127:8000/8003/8043` 毫秒级返回，而公网域名秒级返回，优先归因到边缘/公网链路而非应用 CPU。
2. **延迟分段**：正式 Web 已切 Cloudflare Pages；至少测三段：云机内部 `http://100.107.220.127:8000/api/health`、公网 API `https://api.aivison.it.com/api/health`、Pages 静态站 `https://web.aivison.it.com`。`https://web.aivison.it.com/api/health` 会返回 Pages SPA HTML，不再是 API 健康检查。历史 Web 边缘到云约 0.5s 的基线只适用于回滚、`web-test` 或 `assets` 排障；超过该量级时继续查 Cloudflare Tunnel、运营商链路、R2 公开域名/短签和前端串行请求。
3. **Central 队列事实**：用 `/system/status` 与 `/system/workers` 看 `queue_size`、`queue_by_type`、`healthy_workers`、`error_workers`、`quarantined_workers`、`workers_by_status`。同时从 Central Redis 聚合 `comfy:queue:pending`、`comfy:queue:running` 与 `comfy:task_heartbeat:*` TTL；pending 最老等待时间比单看 `queue_size` 更能解释用户体感。
4. **GPU 实际利用率**：逐台执行 `nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,temperature.gpu --format=csv,noheader,nounits`，并查 7 个 ComfyUI `/queue`。显存高但 GPU 利用率低可能是模型常驻、加载、等待、后处理或 IO，不等同于“卡死”。
5. **Web 结果和媒体链路**：统计 `cloud-web-api-prod` 中 `Timed out resolving web result R2 URL`、`Unexpected object_exists failure`，并抽样确认历史、Gallery、apply-context 响应不包含 `assets.aivison.it.com`。边缘 `assets` 的 `upstream prematurely closed` / `upstream timed out` 只应影响人工回滚、旧外链或迁移排障链路。
6. **Dashboard 卡顿**：统计 `cloud-dashboard-backend-prod` 的 `Circuit Breaker is OPEN`、外部余额接口失败和 stats 慢查询。Dashboard 卡顿不应直接等同于 Central 调度故障。
7. **边缘 499/5xx**：对 `/var/log/nginx/access.log` 做 tail/seek 采样，统计 499、500、502、504 以及高频端点。不要在线全量扫 4GB 级 access.log；大日志本身就是运维风险。
8. **数据库和 Redis**：PostgreSQL 看 `pg_stat_activity` 的 state、`idle in transaction`、`active > 30s`、未授予锁；Redis 看 `used_memory_human`、`connected_clients`、`blocked_clients`、`instantaneous_ops_per_sec` 与 keyspace。托管库/Valkey 不要输出真实连接串。

#### 1.2 云正式常见判读口径
- `active_workers=7` 且 `healthy_workers=7`、`error_workers=0`、`quarantined_workers=0`：worker 总体在线；若 pending 增长，多半是容量/耗时或任务类型分布问题。
- `running_scard` 大于 7 不一定异常：pipeline 允许 worker 同时处于 ComfyUI running/queued/finalizing；需要结合 heartbeat TTL 判断是否僵尸。
- `Task result not set via WS, checking history` 通常是 worker 的 ComfyUI history 补偿路径，不应按 ERROR 处理。
- Web API 大量 R2 result timeout + 边缘 499：用户结果页可能等不及断开，优先优化结果探测超时、缓存和 `pending_result` 快速返回。
- `assets.aivison.it.com` 回源异常集中出现：优先确认正式 Web/Dashboard 响应是否误返回 `assets` URL；若只是旧外链/人工回滚链路，再排查边缘 Nginx cache/log 磁盘、Tailscale 到本地 MinIO、真实 object URL，而不是只测 `/minio/health/live`。
- 边缘根盘低于 10% 可用时是 P1 运维风险；不要发布新静态资源、扩大 cache 或开启大日志调试。

### 2. 日志综合分析
采集结束后，基于临时日志数据进行以下多维分析：
1. **异常检测**：精准识别所有 ERROR、WARN、Exception、StackTrace、超时、重试、状态码非200等异常信号。
2. **频率统计**：按分钟粒度统计各类异常的出现次数，为趋势折线图准备数据。
3. **链路追踪**：利用 TraceId 等标识，对同一请求在 `bot → web api → 后端中控api` 之间的调用链进行关联，定位首次出错的节点。
4. **根因归类**：将发现的问题按“配置错误、依赖服务故障、代码逻辑缺陷、资源瓶颈、网络抖动、权限/鉴权失败”六大类进行归档。
5. **影响评估**：评估并定级每类问题对线上用户、测试流程、系统稳定性的影响级别（P0/P1/P2）。
6. **解决方案**：针对每类根因提供可执行的修复或缓解措施（包括：参数调优、降级策略、重试机制、告警阈值调整、代码后续改动建议）。**注：此处仅做文字描述，禁止直接实施代码修改。**
7. **延迟拆段**：Web 卡顿报告必须区分云内处理耗时、边缘到云耗时、用户公网域名耗时、R2 媒体/短签耗时、是否误返回 legacy `assets` URL 和 GPU 队列等待，不要把所有慢都归为“服务器负载高”。

### 3. 报告生成与无痕清理（核心要求）
- **生成报告**：输出一份 Markdown 格式的分析报告，必须包含以下模块：
  - 监控时间范围与日志源列表
  - 异常总览表（异常类型、出现次数、首次/末次时间、影响接口）
  - 趋势图（必须使用 inline Mermaid 语法绘制折线图）
  - 调用链追踪示例（以文本形式粘贴关键 TraceId 与各节点耗时截图/片段）
  - 根因与解决方案对照表
  - 后续行动清单（责任人、优先级、截止时间）
- **保存文件**：将报告命名为 `log_analysis_report_<yyyyMMdd_HHmm>.md`，使用 UTF-8 编码，写入到项目根目录的 `logs/` 文件夹下（若目录不存在请自动创建）。此文件无需提交 Git。
- **清理中间产物**：**强制要求**在报告成功写入磁盘后，立即通过 shell 命令彻底删除步骤1中产生的所有临时日志文件、数据切片或缓存记录。
- **安全检查**：报告写入后必须检查是否包含 `X-Amz`、`Signature`、`Credential`、真实数据库密码、Bot token、JWT secret 或 `.env.cloud.prod` 内容；发现则立即重写为脱敏聚合。
- **最终输出**：向用户回复时，仅需提示“报告已生成完毕”，给出文件的绝对路径，并简要总结报告中的 P0/P1 级核心结论即可。**严禁输出任何监控过程的中间产物或大段原始日志。**
