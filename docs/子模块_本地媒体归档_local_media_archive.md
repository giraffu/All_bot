# AllBot 本地媒体归档

## 1. 目标与边界

归档系统把 History 的输入、主输出和 `extra_outputs.*.path` 保存到 NAS MinIO。
永久原件桶是 `allbot-media-archive-v1`，内容键固定为
`blobs/sha256/ab/cd/<sha256>.<ext>`。缩略图属于可重建派生物，进入
`allbot-media-derived-v1`；校验失败和未完成对象进入 quarantine。

NAS 不参与 GPU Worker 或 Central `/complete` 的同步成功链路。History 成功
持久化时只在同一数据库事务写 `media_archive_outbox`；本地 Worker 异步归档。
NAS 离线不会把已完成的用户任务改成失败，R2 原件继续保留。

个人 PiGallery2 备份图库与本归档完全独立，不复用目录、容器、账号、索引或
生命周期策略。归档内容不得通过 Cloudflare 公网公开。

## 2. 稳定入口

- 资产解析、内容寻址与无运行态依赖的恢复 key 规划：`src/core/media_archive.py`
- outbox、租约和回执：`src/services/media_archive_service.py`
- 内部 API：`src/web_api/routers/media_archive.py`
- schema：`media_archive_outbox`、`media_archive_receipts`、
  `media_archive_restore_outbox`
- 历史目录：`analytics_media_asset_catalog`、`analytics_media_blobs`、
  `analytics_media_source_attempts`、`analytics_media_runs`
- Worker：`scripts/media_archive_worker.py`
- 历史来源探测：`scripts/media_archive_probe.py`
- 目录初始化/切片：`scripts/media_archive_catalog.py`
- reconciliation：`scripts/reconcile_media_archive_outbox.py`
- 热集恢复 reconciliation：`scripts/reconcile_media_archive_restore.py`
- R2 清理 dry-run/执行器：`scripts/media_archive_r2_cleanup.py`
- NAS Compose：`ops/media_archive_nas/`
- 主机路由与常驻服务：`ops/media_archive_worker/`
- 本地浏览 API：`local_analytics_platform/app/routes_archive.py`

## 3. History 单条媒体内容

一条 History 的归档清单由以下逻辑资产组成：

- `input_file` 按 `|` 拆分，每段按原顺序形成 `input/<ordinal>`；相同引用仍是
  两个逻辑资产，最终由 SHA-256 blob 去重。
- `output_file` 形成 `output/0`。
- `extra_outputs` 递归提取所有 `path`，按顶层字段形成
  `extra:<name>/<ordinal>`；遗留数据中非 JSON object 的 `extra_outputs`
  不具备顶层字段语义，目录 seed 将其视为无附加输出并继续扫描。
- prompt、类型、用户、task ID、时间和可见性留在 History/目录映射中，不写入
  blob key；因此可按原引用恢复到 R2。

## 4. 历史盘点与丢失状态

先运行 `media_archive_catalog.py init`，再按月份对应的 History ID 范围运行
`seed --start-id ... --end-id ...`。来源优先级登记在
`analytics_media_sources`：生产 R2、旧 R2、旧 MinIO 两桶、冷 MinIO 两端点、
已知备份和遗留文件系统。`user-data-test` 不在默认来源表。
旧 `user-data` 退役后不得再作为热集回填的默认源；只允许在有退役证据的
受控取证命令中通过 `--source-r2-buckets` 显式指定。

状态仅使用：`pending_probe`、`source_offline`、`found`、
`archived_verified`、`provisional_missing`、`confirmed_lost`、
`checksum_error`、`external_unmanaged`。来源离线必须记录
`source_offline`，不得折算为不存在。只有一个 run 覆盖全部启用来源且全部返回
not-found，才累计一次 missing round；两轮相隔至少 24 小时才可确认丢失。
永久退役来源必须先在 `analytics_media_sources.retirement_evidence` 留证。

## 5. NAS 部署 SOP

1. 通过 UGOS 管理面确认实际存储池、文件系统、固件满足官方 Docker 应用的最低
   版本要求，并核对 Docker bind-mount 路径；固件升级和重启须单独确认。
2. 创建独占目录 `AllBotArchive/minio-data`、`minio-certs`、`ca`；永久数据达到
   80% 容量即停止迁移。`AllBotArchive` 必须是独立 Btrfs subvolume；安装
   `snapshot.sh` 和对应 systemd timer，每日只读快照并保留 7 份。
3. 在可信机器运行 `generate_tls.sh`，安全复制 CA 与服务端证书。主服务器安装
   CA；禁止 `verify=false`。
4. 把 MinIO 和 mc 的已验证 OCI digest、随机凭据写入 NAS 私有 `.env`，执行
   `preflight.sh` 后再 `docker compose up -d`。
5. 优先使用 `eno1` 与 NAS `eth0` 的独立 `/30` 直连网段；S3 9000 同时绑定管理
   IP 和直连 IP，9001 只绑定管理 IP。可信单租户 LAN 可按用户决定不启用仓库内
   的可选 `ALLBOT_MEDIA_ARCHIVE` 防火墙；即使停用，TLS、最小权限账号和非公网
   暴露仍是强制边界。
6. 验证健康检查、三个桶、archive 桶 versioning、Worker 无 DeleteObject 权限、
   analytics 只读、容器重启恢复、日志轮转和磁盘满 fail-closed。

仓库不保存真实凭据或镜像占位 digest。没有 NAS 管理权限时只能准备部署包，
不得声称已部署。

UGOS 固件升级后必须重新核对归档目录、密钥和 `.env` 权限，不能假设原 mode 与
SSH home 保持不变。NAS 无法直连 registry 时，可在可信主服务器验证原 OCI
manifest digest、离线导入对应平台镜像，并在 `.env` 使用导入后的不可变
`sha256:<image-id>`；禁止退化到 `latest` 或其它可变 tag。证书目录自身包含
`CAs/allbot-archive-ca.crt`，禁止在只读证书目录下再叠加子路径 bind mount。

## 6. 传输与清理门禁

Worker 以 8 并发和全天 50 MiB/s 总上限启动，每 15 分钟按吞吐和错误率在
8/16/32 间调整；达不到上限不判失败。`.part` 总容量 100 GiB，已用和预留达到
90 GiB 即暂停新对象；下载前 HEAD 预检单对象大小，启动清理陈旧 part。配置必须
是当前用户所有的普通 0600 文件。启动清空代理变量，发现 `127.0.0.1:7890` 则
直接拒绝，并使用 `ip route get` 校验 NAS 直连 endpoint 固定走声明的物理接口和
源地址；默认部署使用 `eno1`、`10.250.150.1/30` 到 NAS
`10.250.150.2/30`，且不配置网关；R2
拒绝 loopback、tun/wg 和 Tailscale exit-node 路径。旧来源可显式允许 Tailscale
点对点。每个对象流式计算 SHA-256、上传 NAS、完整回读复算；内容键已存在且大小/
摘要元数据一致时复用，只有完整验收才提交回执。

Worker 每 5 分钟调用 `/api/internal/media-archive/leases/renew`。成功回执记录实际
命中的来源和 candidate key，成功、失败和续租都必须携带当前 outbox revision，
因此过期 Worker 不能覆盖新清单。Worker 同步写本地 source attempts、blob 和
asset 状态；常驻服务与每日 reconciliation 模板位于 `ops/media_archive_worker/`。

冷 History 重新变热使用独立 restore outbox。收藏、重新公开、活跃 Gallery 和
owner `/result` 的 R2 miss 在业务事务中只做幂等 enqueue；每日 reconciliation
补齐先按原始 History 排名的最新 8 条。LAN Worker 从已验证 receipt 读取 NAS blob，
复验大小、SHA-256 与元数据后回填原件兼容 key；输出角色另外重建缩略图。每个 R2
对象 HEAD 验证通过后才能提交 restore receipt。Web/API 不读取 NAS，也不因恢复
失败改变既有任务终态或同步响应。

`media_archive_catalog.py seed` 与 `reconcile_media_archive_outbox.py` 支持最多
10,000 行的 `--history-id-file`，用于确定性 canary；未提供时继续使用原有 ID
范围。reconciliation 默认 dry-run，正式 outbox 写入仍需显式 `--execute`。

R2 删除默认关闭。候选覆盖输入、主输出、附加输出和主输出派生缩略图；共享引用
按全部角色检查最新 8 条原始 History（再过滤可见）、收藏、公开和活跃投稿。
执行批次硬限制为 1–1000 个逻辑资产，同时要求
`R2_ARCHIVE_DELETE_ENABLED=true`、`R2_ARCHIVE_RESTORE_GATE_VERIFIED=true` 和
一次性确认值。第一次生产删除必须先生成对象/字节 dry-run 报告并再次取得用户
明确确认；实现和归档阶段不执行生产删除。

临时对象治理与冷归档删除是两条独立门禁。`scripts/r2_temp_cleanup.py`
默认 dry-run，只允许清理超过 24 小时、不被 History 全角色引用、且已有
完整 SHA-256 相同持久副本的已知临时类型。未知 key、`temps/`、单份内容、
活跃任务、模板投稿、归档回执、角色/官方资产及其视图/渲染对象均独立阻断；
Gallery、收藏和公开记录由其关联的 History 全角色阻断。HEAD/SHA/数据库失败均
fail closed。双份 SHA 读取默认最多 8 路并发，可用
`--verification-concurrency` 在 1–16 之间收紧；并发只影响读取吞吐，不跳过
对象级摘要或执行前的重新校验。执行只认
`R2_TEMP_CLEANUP_ENABLED` 和精确生产桶确认，不复用
`R2_ARCHIVE_DELETE_ENABLED` 或恢复门禁。
完成 100/1000/10000 对象 canary 后可安装 `ops/r2_temp_cleanup/` 的每日任务；
单批同时受 10000 对象与 50 GiB 上限约束，使用当前 inventory，运行报告写入
受限 state 目录。`staging/` 对象数、字节和最老时间随报告输出；任一引用、数据库
或摘要探测失败仍整批 fail closed。

模板投稿新写 `template-submissions/`，旧 `temps/` 只在迁移兼容期双读且永不进入
通用临时清理。`scripts/r2_template_submission_migration.py` 在同一生产桶按原相对 key
复制并对源/目标完整 SHA-256 验证，使用 0600 SQLite 断点状态；真实迁移使用独立
精确确认值，不能借用临时清理或冷归档删除门禁。

`scripts/r2_legacy_bucket_retirement.py` 只允许固定的 `user-data` →
`user-data-prod` 合并，用受限运行态 SQLite 保存 cursor、HEAD、复制和全量
SHA 证据。服务端复制默认最多 16 路并发，可用 `copy --workers` 在 1–32
之间收紧；SQLite 状态更新仍由单线程提交，失败 key 保留为可断点重试。
已存在 key 不覆盖，只有旧桶全对象在新桶逐项摘要一致、
未验证/冲突/失败均为 0 时才能生成退役清单。真实删除旧桶前必须再次
展示精确对象数和字节并取得明确确认；`user-data-test` 和
`allbot-model-cache` 永远不在该脚本目标集。

## 7. 本地浏览与安全

历史生成页提供目录筛选和“查看媒体”。列表按 input 与 output（含 `extra:*`）分别
展示本地可用数；`GET /api/generation-history/{id}/media` 使用
`role_group=input|output|all` 懒加载，并只为 `archived_verified` 返回本地
`content_url`。原件接口支持 HTTP Range，浏览器只拿
分析平台 session cookie，NAS 只读凭据仅在服务端。原件路由在鉴权前识别并拒绝
Cloudflare 请求头，因此 Tunnel 只能访问统计与目录，不能读取完整文件。归档状态
卡片展示逻辑资产、验收数、字节、outbox 积压、吞吐、来源离线、校验错误、容量
和暂停原因；告警仅留在本地平台。三个归档 API 即使平台全局登录被关闭也会返回
503，必须显式启用并配置本地登录后才能访问。

Worker 私有配置由 `render_media_archive_worker_config.py` 从 `env:NAME` 模板生成，
只输出来源名和配置指纹，实际 JSON 原子写为 0600；配置校验拒绝把已退役
`user-data` 重新登记为启用来源。`media_archive_source_health.py` 每日只读探测六个
来源和 NAS，离线统一输出 `source_offline`，不等价于 not-found。首个 canary 对象
完成 NAS 上传及完整回读并写入 `archived_verified` 后，本地容量和历史页才开始出现
实际归档数据。

## 8. 验证

```bash
pytest -q tests/core/test_media_archive.py tests/database/test_media_archive_schema.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
docker compose --env-file ops/media_archive_nas/.env.example -f ops/media_archive_nas/compose.yml config
python scripts/doc_quality_checker.py
```

部署后再做小批量真实对象验收、断点重跑、NAS 离线、校验错误、Range、容量告警
和两轮缺失确认演练。生产迁移必须按“热 → 最近冷 → 更早冷”逐批执行。
