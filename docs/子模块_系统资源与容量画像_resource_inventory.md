# 子模块：系统资源与容量画像

本文定义如何采集和解释 AllBot 的资源/容量现状，不保存某次 CPU、磁盘、容器、
队列、数据库大小或 Worker 数量。旧快照退出说明见
[资源画像快照退役说明](archive/resource-inventory-snapshot-retirement.md)。

## 1. 状态与证据等级

资源画像永远是时间敏感信息，本资料在审计矩阵中固定为
`runtime-verification-required`。结论必须标明采集时间、目标环境、证据来源和
未覆盖项。

证据等级：

1. **live**：本轮从目标主机/provider/API/数据库只读取得。
2. **ledger**：XDG/provider/release state 的 last-known identity。
3. **catalog**：Git 声明允许的节点、模块、slot 或 profile。
4. **historical**：archive、日志或旧报告，只用于趋势和事故追溯。

容量决策不能用 catalog 代替 live，也不能把历史快照写成当前值。无法探测的
目标明确标记 unknown，不用邻近环境或旧数字补齐。

## 2. 采集范围

| 责任域 | 最小证据 |
| --- | --- |
| 控制面主机 | CPU/load、内存/swap、磁盘/inode、Docker 容器与 image identity |
| PostgreSQL | 连接、数据库/大表/索引体积、长事务、锁和备份状态 |
| Redis/Valkey | memory、keyspace、eviction、连接、队列 DB 与持久化状态 |
| Web/API | health、请求错误/延迟、容器资源、外部依赖 |
| Central/队列 | pending/running、按 task type 分布、worker health/current task |
| RunPod | provider slot/profile、enabled/health、GPU 类型、operation 与计费状态 |
| LAN GPU | catalog、XDG current/cache、live GPU/container/ComfyUI/Central |
| R2/媒体 | bucket 生命周期、对象增长、公开/私有边界、失败与回填队列 |
| 本地分析/NAS | 快照新鲜度、挂载、只读/写入边界、容量与备份任务 |
| 公网 | DNS/Tunnel/Pages/Access 当次状态与 origin health |

秘密值、完整 env、token、数据库 URL、presigned URL 和用户媒体不得进入报告。
日期化 NAS 容量和部署证据写入 `logs/resource_inventory_nas_YYYYMMDD.md`；当前
规划值与待复核项见 `logs/resource_inventory_nas_20260805.md`，不得复制到稳定 Skill。

## 3. 只读采集原则

- 云主机通过已配置 SSH alias 执行明确只读命令；连接问题加载
  `allbot-cloud-ssh`。不要扫描未知网段或猜测账号。
- 容器只读取 `docker ps/inspect/stats`、health 和有界日志；不 restart、
  exec 修改、prune 或 pull。
- 数据库只执行只读统计；先设置 statement timeout，避免全表长扫描。
- Redis 使用 INFO/只读 keyspace 统计；不 FLUSH、DEL、迁移 key 或修改 config。
- RunPod/Cloudflare 使用只读 provider API；任何 mutation 仍需用户明确授权。
- LAN 通过 `allbot-lan-aio-operator` 的 status 与单目标 SSH 探测；不自由
  Compose 或跨槽批量。
- 本轮没有权限、网络或凭据时记录缺口，不降低安全边界换取“完整数字”。

## 4. 解释容量

不要用单一 CPU/内存百分比解释用户等待。至少拆成：

1. 入口延迟：浏览器/Bot → Pages/Tunnel/API。
2. 控制面延迟：鉴权、数据库、Redis、队列与任务提交。
3. 排队延迟：目标 task type 的 pending、enabled capacity 与公平性。
4. 执行延迟：模型加载、ComfyUI、GPU OOM/Xid、workflow。
5. 交付延迟：结果物化、上传、R2、History/Gallery 与通知。

平均值会掩盖 task type 和 profile 差异。报告同时给出 p50/p95 或有界分位、
峰值窗口、样本量和观测周期；无足够样本时只描述现象，不估算容量承诺。

资源“空闲”也不等于可接单：

- Worker 可能 disabled、unhealthy、task types 不匹配或模型未缓存。
- GPU 显存空闲可能是 ComfyUI 未启动、候选停机或节点隔离。
- 控制面主机低负载不能排除数据库锁、Redis 连接、外部 API 或 Tunnel 问题。
- R2 总容量足够不能排除单对象、CORS、签名、生命周期或公网域名故障。

## 5. 发布与容量的边界

代码发布只走 `scripts/release.py` 的完整 main SHA 构建与 exact-digest 单模块
部署。资源检查用于操作者决策，不是发布器自动门禁，也不授权：

- 整栈维护、自由 Compose 或源码同步。
- 数据库 migration、扩容或清理。
- RunPod/LAN rollout、slot 切换或模型缓存。
- Cloudflare/DNS/Tunnel 修改。
- prod mutation 或本地正式灾备。

构建 artifact、更新 catalog 或通过测试都不会自动增加 live capacity。

## 6. 报告格式

一次资源画像写入 `logs/` 或事故/容量专项 archive，至少包含：

- 采集开始/结束时间与时区。
- 环境和明确目标主机/provider/slot；不写秘密。
- 每个责任域的 evidence level、采集命令/API 与结果摘要。
- 当前瓶颈假设、支持/反驳证据和置信度。
- unknown、不可达、权限不足与运行态待核验项。
- 建议动作分为只读补证、代码变更、test mutation、prod mutation。
- 若建议 mutation，列出需要的新授权和精确目标，不直接执行。

稳定架构结论回写对应专题文档；数字、容器列表、任务量和事故现场不回写本文件。

## 7. 最小验证

知识库变更：

```bash
python scripts/doc_quality_checker.py
```

涉及具体子系统时再运行其 focused tests。资源报告自身应复核：

- 时间、环境、目标与证据等级齐全。
- 没有秘密、完整 URL 凭据或用户数据。
- catalog/ledger/live 没有混写。
- 所有“当前”结论都有本轮 live 证据。
- 未执行的远端、数据库、GPU 或 Cloudflare 检查标为 unknown/
  `runtime-verification-required`。
