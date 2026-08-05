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
   80% 容量即停止迁移。若 Btrfs 可用，开启每日快照、保留 7 天。
3. 在可信机器运行 `generate_tls.sh`，安全复制 CA 与服务端证书。主服务器安装
   CA；禁止 `verify=false`。
4. 把 MinIO 和 mc 的已验证 OCI digest、随机凭据写入 NAS 私有 `.env`，执行
   `preflight.sh` 后再 `docker compose up -d`。
5. UGOS 防火墙只允许 `192.168.1.115` 到 9000；9001 只允许管理员网段。
6. 验证健康检查、三个桶、archive 桶 versioning、Worker 无 DeleteObject 权限、
   analytics 只读、容器重启恢复、日志轮转和磁盘满 fail-closed。

仓库不保存真实凭据或镜像占位 digest。没有 NAS 管理权限时只能准备部署包，
不得声称已部署。

## 6. 传输与清理门禁

Worker 以 8 并发和 20 MiB/s 总限速启动，`.part` 暂存最多 100 GiB。启动会清空
代理变量并使用 `ip route get` 拒绝 loopback、Tailscale、tun/wg 路由。每个对象
流式计算 SHA-256、上传 NAS、完整回读复算；只有大小和摘要一致才提交回执。

R2 删除默认关闭。运行时需要同时设置 `R2_ARCHIVE_DELETE_ENABLED=true` 和一次性
确认值，且代码仍会检查 outbox 已归档、主输出回执已验收、相同引用无最新 8 条
原始 History（再过滤可见）、收藏、公开或活跃投稿引用。第一次生产删除必须先
生成对象/字节 dry-run 报告并再次取得用户明确确认；本方案的实现和验证阶段不
执行生产删除。

## 7. 本地浏览与安全

历史生成页提供目录筛选和“查看媒体”。原件接口支持 HTTP Range，浏览器只拿
分析平台 session cookie，NAS 只读凭据仅在服务端。三个归档 API 即使平台全局
登录被关闭也会返回 503，必须显式启用并配置本地登录后才能访问。

## 8. 验证

```bash
pytest -q tests/core/test_media_archive.py tests/database/test_media_archive_schema.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
docker compose --env-file ops/media_archive_nas/.env.example -f ops/media_archive_nas/compose.yml config
python scripts/doc_quality_checker.py
```

部署后再做小批量真实对象验收、断点重跑、NAS 离线、校验错误、Range、容量告警
和两轮缺失确认演练。生产迁移必须按“热 → 最近冷 → 更早冷”逐批执行。
