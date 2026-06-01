---
name: "ops-log-monitor"
description: "Monitors system logs across environments, analyzes exceptions, and generates incident reports. Invoke when user asks to monitor logs, check errors, or troubleshoot bugs."
---

# Ops Log Monitor & Bug Troubleshooter

This skill is designed to automatically execute system log monitoring, anomaly detection, and deep analysis without cluttering the conversation with raw logs.

## Workflow Instructions

When invoked to perform log monitoring or bug troubleshooting, strictly follow these steps:

### 1. 日志采集与监控（静默执行）
- **执行采集脚本**：直接在项目根目录运行预置脚本 `bash collect_logs.sh 15`（15 代表提取过去 15 分钟的日志，可根据用户要求的时长调整参数）。
- **读取过滤数据**：脚本会自动采集目标容器（如 `tg-bot`, `web-api` 等）的日志，并提取所有的 ERROR、WARN、Exception 等异常写入临时文件。请直接使用工具读取 `logs_temp/errors.log` 来分析报错。
- **排查双边缘节点故障**：当涉及网络层、跨域（CORS）、文件上传失败（413 Payload Too Large）、或者请求根本未到达后端时，**必须**使用 SSH 检查以下两个边缘节点的日志：
  - **Web 前端与流量转发节点** (`100.88.57.122` / `154.17.30.113`)：执行指令 `ssh -i frontend/ssh_key/id_rsa.pem root@100.88.57.122 "tail -n 100 /var/log/nginx/error.log"` 检查 Nginx 代理报错。
  - **Telegram Local API 节点** (`69.63.220.115`)：当出现 `telegram.error.TimedOut`、大文件下载 404/403 等异常时，执行指令 `ssh root@69.63.220.115 "docker logs --tail 100 tg-local-api"` 或检查 HTTP 文件服务器日志。
- **排查后端数据库慢查询与连接池**：当出现 `110 Connection timed out` 且后端日志无明显应用报错时，**必须**排查 PostgreSQL 连接池是否被耗尽。使用 `docker exec -i postgres-server psql -U postgres -d bot_db -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"` 检查 `idle in transaction` 的数量。若发现大量卡死进程，可使用 `ALTER SYSTEM SET idle_in_transaction_session_timeout = '60000';` 进行熔断恢复，并配置 `log_min_duration_statement = '1000'` 追踪慢查询。
- **执行要求**：在此期间仅做观察与分析，**绝对不要修改任何代码**。请不要在对话窗口中打印原始的日志流。

### 2. 日志综合分析
采集结束后，基于临时日志数据进行以下多维分析：
1. **异常检测**：精准识别所有 ERROR、WARN、Exception、StackTrace、超时、重试、状态码非200等异常信号。
2. **频率统计**：按分钟粒度统计各类异常的出现次数，为趋势折线图准备数据。
3. **链路追踪**：利用 TraceId 等标识，对同一请求在 `bot → web api → 后端中控api` 之间的调用链进行关联，定位首次出错的节点。
4. **根因归类**：将发现的问题按“配置错误、依赖服务故障、代码逻辑缺陷、资源瓶颈、网络抖动、权限/鉴权失败”六大类进行归档。
5. **影响评估**：评估并定级每类问题对线上用户、测试流程、系统稳定性的影响级别（P0/P1/P2）。
6. **解决方案**：针对每类根因提供可执行的修复或缓解措施（包括：参数调优、降级策略、重试机制、告警阈值调整、代码后续改动建议）。**注：此处仅做文字描述，禁止直接实施代码修改。**

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
- **最终输出**：向用户回复时，仅需提示“报告已生成完毕”，给出文件的绝对路径，并简要总结报告中的 P0/P1 级核心结论即可。**严禁输出任何监控过程的中间产物或大段原始日志。**