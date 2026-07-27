---
name: ops-log-monitor
description: "监控多环境日志、分析异常并生成 incident 报告。用户要求查日志、监控错误或排障线上问题时使用。"
---

# AllBot 日志监控与排障

日志采集只读、最小范围、全程脱敏。容器名、主机/IP、worker 集合、域名和 SSH
可用性属于运行态：先由部署文档、release state、Central/provider 和只读发现
得到，不能依赖 Skill 中的历史快照。

同时加载 `allbot-diagnosing-bugs` 建立可复现反馈环；涉及 test/prod、容器或
远端环境时加载 `allbot-ops-deployment`。日志分析本身不授权修复、重启、部署、
改数据库或清理队列。

## 1. 按需阅读

| 故障面 | 先读 |
| --- | --- |
| 云 test/prod 控制面 | 对应云控制面文档 |
| Compose、发布、回滚 | `docs/子模块_运维指南与容器管理_ops_deployment.md` |
| 任务、Central、Worker | `docs/子模块_生成任务全链路_task_full_chain.md` |
| GPU/RunPod/LAN | `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` |
| Telegram 文件/API | `docs/子模块_Telegram本地API与文件代理_tg_local_api.md` |
| 媒体/R2/Gallery | `docs/子模块_社区与存储_gallery_storage.md` |

只读命中的一行，再用部署声明和实时发现确定实际目标集合。

## 2. 反馈环

1. 定义症状、环境、时间窗、用户影响、预期/实际结果和可观察成功条件。
2. 取得 release SHA/config revision、trace/task/user 的脱敏关联键。
3. 先复现或测量一个窄路径，记录基线；无法复现时明确证据限制。
4. 按请求入口 → core/service → Central/queue → Worker/provider → storage/result
   顺序关联，避免只盯最后一条异常。
5. 每次只验证一个假设，保留可重复命令和前后对照。

## 3. 采集规则

- 优先现有 structured logs、trace ID、metrics、health、Central worker/status、
  release state 和只读 DB/Redis 查询。
- 先取 15–30 分钟或用户给定窗口；只有证据表明需要时扩大。避免全量
  `docker logs`、journal 或数据库 dump。
- 发现目标集合：从 compose/release manifest、`docker ps`、service manager、
  Central/provider 获取；不要写死 worker 数或只检查本地 compose。
- 延迟按客户端/边缘 → origin/API → DB/Redis → Central/Worker → object
  storage 分段测量，分别记录 DNS/TLS/TTFB/总时长。
- Telegram 文件故障先验证 API/file endpoint 连通与响应；SSH 不可用时只能
  报告未检查远端容器，不能猜测。
- 命令输出进入临时目录或内存，只保留聚合、时间、计数、错误类与脱敏样本。

## 4. 脱敏与授权红线

- 不输出 env、compose 展开、Authorization、JWT、Bot token、agent secret、
  DB/Redis URL、R2 key、预签 URL、cookie 或请求正文中的私密媒体/提示词。
- 用户 ID、task ID、IP、邮箱等只保留定位所需最短形式；报告不复制大段原始
  日志。
- 只读排障不得执行 restart、scale、delete、retry、cancel、queue cleanup、
  数据修复、Cloudflare/GPU mutation 或发布。
- 不长期启用 debug 日志，不在高频循环加入无界打印，不把现场秘密写入测试或
  Git。
- 若需要插桩或修复，先报告假设与证据，再按用户授权进入代码任务和相应 Skill。

## 5. 分析与报告

按 `Critical/High/Medium/Low` 汇总：

- 时间范围、环境、release/config 身份和实际采集源；
- 症状时间线、影响面、关键计数/延迟分位数；
- 已证实根因、支持/反证、仍待验证的假设；
- 安全的修复建议、回归 seam、回滚条件和需要额外授权的 mutation。

报告保存到 `logs/incident_report_<yyyyMMdd_HHmm>.md`，不提交 Git。成功写入后
删除原始日志、临时脚本、切片和缓存；最终只给报告路径、关键指标和 Critical
风险，不在对话贴长日志。

## 6. 最小验证

- 实际采集目标与当前 release/compose/Central 发现一致。
- 时间窗、时区、trace/task 关联和日志丢失范围清楚。
- secret 扫描通过，报告样本已脱敏，临时产物已删除。
- 根因有可重复反馈环；只有相关性时明确标为假设。
- 未授权期间没有任何外部 mutation；建议的修复与回归测试尚未被描述成已执行。
