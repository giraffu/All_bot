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

- 资产解析与内容寻址：`src/core/media_archive.py`
- outbox、租约和回执：`src/services/media_archive_service.py`
- 内部 API：`src/web_api/routers/media_archive.py`
- schema：`media_archive_outbox`、`media_archive_receipts`
- 历史目录：`analytics_media_asset_catalog`、`analytics_media_blobs`、
  `analytics_media_source_attempts`、`analytics_media_runs`
- Worker：`scripts/media_archive_worker.py`
- 历史来源探测：`scripts/media_archive_probe.py`
- 目录初始化/切片：`scripts/media_archive_catalog.py`
- reconciliation：`scripts/reconcile_media_archive_outbox.py`
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
  `extra:<name>/<ordinal>`。
- prompt、类型、用户、task ID、时间和可见性留在 History/目录映射中，不写入
  blob key；因此可按原引用恢复到 R2。

## 4. 历史盘点与丢失状态

先运行 `media_archive_catalog.py init`，再按月份对应的 History ID 范围运行
`seed --start-id ... --end-id ...`。来源优先级登记在
`analytics_media_sources`：生产 R2、旧 R2、旧 MinIO 两桶、冷 MinIO 两端点、
已知备份和遗留文件系统。`user-data-test` 不在默认来源表。

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
5. UGOS 防火墙只允许 `192.168.1.115` 到 9000；9001 只允许管理员网段。
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
直接拒绝，并使用 `ip route get` 校验 NAS 固定走 `eno1`/`192.168.1.115`；R2
拒绝 loopback、tun/wg 和 Tailscale exit-node 路径。旧来源可显式允许 Tailscale
点对点。每个对象流式计算 SHA-256、上传 NAS、完整回读复算；内容键已存在且大小/
摘要元数据一致时复用，只有完整验收才提交回执。

Worker 每 5 分钟调用 `/api/internal/media-archive/leases/renew`。成功回执记录实际
命中的来源和 candidate key，成功、失败和续租都必须携带当前 outbox revision，
因此过期 Worker 不能覆盖新清单。Worker 同步写本地 source attempts、blob 和
asset 状态；常驻服务与每日 reconciliation 模板位于 `ops/media_archive_worker/`。

R2 删除默认关闭。候选覆盖输入、主输出、附加输出和主输出派生缩略图；共享引用
按全部角色检查最新 8 条原始 History（再过滤可见）、收藏、公开和活跃投稿。
执行批次硬限制为 1–1000 个逻辑资产，同时要求
`R2_ARCHIVE_DELETE_ENABLED=true`、`R2_ARCHIVE_RESTORE_GATE_VERIFIED=true` 和
一次性确认值。第一次生产删除必须先生成对象/字节 dry-run 报告并再次取得用户
明确确认；实现和归档阶段不执行生产删除。

## 7. 本地浏览与安全

历史生成页提供目录筛选和“查看媒体”。原件接口支持 HTTP Range，浏览器只拿
分析平台 session cookie，NAS 只读凭据仅在服务端。原件路由在鉴权前识别并拒绝
Cloudflare 请求头，因此 Tunnel 只能访问统计与目录，不能读取完整文件。归档状态
卡片展示逻辑资产、验收数、字节、outbox 积压、吞吐、来源离线、校验错误、容量
和暂停原因；告警仅留在本地平台。三个归档 API 即使平台全局登录被关闭也会返回
503，必须显式启用并配置本地登录后才能访问。

## 8. 验证

```bash
pytest -q tests/core/test_media_archive.py tests/database/test_media_archive_schema.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
docker compose --env-file ops/media_archive_nas/.env.example -f ops/media_archive_nas/compose.yml config
python scripts/doc_quality_checker.py
```

部署后再做小批量真实对象验收、断点重跑、NAS 离线、校验错误、Range、容量告警
和两轮缺失确认演练。生产迁移必须按“热 → 最近冷 → 更早冷”逐批执行。
