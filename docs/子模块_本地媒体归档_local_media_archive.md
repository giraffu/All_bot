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
- History 行驱动 R2 迁移账本：`scripts/history_media_r2_migration.py`
- reconciliation：`scripts/reconcile_media_archive_outbox.py`
- 热集恢复 reconciliation：`scripts/reconcile_media_archive_restore.py`
- R2 清理 dry-run/执行器：`scripts/media_archive_r2_cleanup.py`
- NAS Compose：`ops/media_archive_nas/`
- 主机路由与常驻服务：`ops/media_archive_worker/`
- 本地浏览 API：`local_analytics_platform/app/routes_archive.py`
- 自有电子书转 EPUB 与 Calibre 增量同步：
  `scripts/sync_minio_ebooks_to_calibre.py`；NAS CWA Compose 与本机常驻服务：
  `ops/calibre_web_nas/`

### Calibre-Web Automated 电子书派生库

MinIO `ebooks/diyibanzhu/<book_id>.txt/.json` 是原始事实源，Calibre 书库只是可重建
派生物。同步器每 30 秒列举前缀，只处理 TXT/JSON 配对且 JSON `book_id`、SHA-256
与 TXT 完整摘要一致的对象；随后生成带中文元数据的 EPUB，把大文本切为多个 XHTML，
先原子保存到 NAS `source-epub/`，再复制到 CWA `ingest/`。本地 SQLite 按书籍 ID
和源摘要断点续跑，内容未变不重复发布，源摘要变化时重新生成。

CWA 配置、ingest 和 Calibre library 分别使用
`/volume1/AllBotEbooks/{config,ingest,calibre-library}`，原始 MinIO bucket 不挂入
CWA，也不允许 ingest 删除原始 TXT。网页只绑定 NAS 管理 LAN 的 8083 端口，不接
Cloudflare 公网。CWA 镜像必须通过私有 0600 `.env` 的 `CWA_IMAGE` 使用已验证
amd64 manifest digest；NAS 无法访问 registry 时由可信主机验证 digest、拉取并
离线导入，再把实际导入的不可变 `sha256:<image-id>` 写入该变量，禁止改用 mutable tag。

同步器通过本机 SSH alias 原子写入 NAS，运行代码由
`~/.local/share/allbot/calibre-sync/current` 指向精确 Git SHA；用户级 systemd 服务
开机自启。单本失败只记录脱敏书籍 ID/错误并继续，后续轮询会重试未提交 state 的对象。
- 自有站点电子书归档：`scripts/archive_owned_ebook_site.py`；私有运行模板：
  `ops/ebook_site_archive/runtime-template.json`

### 自有电子书站点归档

`archive_owned_ebook_site.py` 只面向操作者确认拥有或已获完整归档授权的站点。
当前适配 `diyibanzhu` 的 `/book/`、`/list/`、`/view/` 页面结构，将每本书清洗为
UTF-8 TXT，并把同名 JSON 元数据写入 NAS MinIO 的私有前缀。它不会复用 History
媒体目录、outbox 或 R2 清理门禁，也不会把电子书暴露到公网。

运行配置必须为 0600，凭据通过 `env:NAME` 注入，TLS 必须使用包含 NAS IP SAN 的
内部 CA。命令默认只扫描目录并报告数量；只有显式 `--execute` 才抓取章节并上传。
本地 SQLite state 按书籍 ID 和正文 SHA-256 断点续跑，正文变化时覆盖同一对象 key；
MinIO bucket versioning 保留旧版本。先执行一本文字 canary，再扩大范围：

```bash
python scripts/archive_owned_ebook_site.py \
  --config /受限路径/ebook-archive.json \
  --state /受限路径/ebook-archive.sqlite3 \
  --limit-books 1

python scripts/archive_owned_ebook_site.py \
  --config /受限路径/ebook-archive.json \
  --state /受限路径/ebook-archive.sqlite3 \
  --limit-books 1 --execute

python scripts/archive_owned_ebook_site.py \
  --config /受限路径/ebook-archive.json \
  --state /受限路径/ebook-archive.sqlite3 \
  --concurrency 16 --skip-existing --execute
```

全量执行仍属于 NAS 写入，必须由用户明确要求；脚本逐书失败后继续并输出脱敏错误，
可使用同一 state 重跑。站点结构变化导致正文或章节无法识别时 fail closed，不上传
空书。并发范围固定为 1–16；`--skip-existing` 在 worker 调度前按 state 的书籍 ID
过滤已完成对象，最多 16 路只处理待归档书籍，上传后仍由主线程串行提交 SQLite
state。提升并发前先用 8 路观测 HTTP 限流、超时和 NAS 回读校验；没有基础设施错误
时再切换到 16 路，源书无章节属于内容错误，不作为并发降级信号。

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
   NAS 专线 systemd unit 必须通过 `RequiresMountsFor` 等待
   `/volume1/AllBotArchive/deploy` 挂载完成，再于 Docker 启动前配置直连 IP，
   避免因脚本路径尚不存在导致 MinIO 端口绑定失败。
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
当生产 backlog 已存在时，canary Worker 配置另用 `history_ids` 固定本轮最多 100
条 History；`GET /api/internal/media-archive/jobs` 以逗号分隔 query 参数接收该集合并
只租用集合内任务。该过滤仍受 agent token、优先级、租约和 revision 门禁约束，
不得通过临时改写其它 outbox 的优先级或 `available_at` 达成确定性领取。
领取后必须先确认本地目录完整覆盖该 job 的全部角色/序号，再开始任何 NAS 上传；
目录未 seed 或清单不一致时先提交可重试失败，不得留下无目录映射的孤儿 blob。

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
每日服务先用 `refresh_r2_temp_cleanup_inventory.py` 在受限 state 目录生成新
SQLite，完成 integrity、对象数、字节和 SHA 验收后原子切换 `current.sqlite3`。
runner 始终先生成冻结计划，再把同一计划 SHA 交给 execute；自动删除还必须同时
开启独立 `R2_TEMP_CLEANUP_AUTOMATION_ENABLED` 与删除门禁，任一关闭时不执行删除。
自动化还要求 0600 `R2_TEMP_CLEANUP_CANARY_EVIDENCE` 明确登记 100、1000、10000
三阶段 completed 及各自执行回执 SHA-256；缺失或不完整时 fail closed。
本地分析 `/api/r2-governance/status` 只读取同步到本地的私有 evidence 并返回批次
汇总，不返回对象 key、R2 endpoint 或凭据。

临时清理采用冻结计划协议。dry-run 报告带 `batch_id`、inventory 完整摘要、精确
候选集合和 `plan_sha256`；execute 必须显式传入 `--approved-plan` 与
`--plan-sha256`，确认值同时绑定生产桶和计划摘要。执行前重新查询全部引用并重做
双对象 SHA，inventory 或计划被修改时拒绝执行；删除后还需确认临时 key 已消失且
持久副本摘要未变化。每日 runner 也先保存独立 plan，再在总开关和基础确认均有效
时消费该 plan，未生成回执不得视为成功。

一次性全量临时治理使用独立入口
`scripts/r2_temp_cleanup_campaign.py`，不改变每日 canary/cleanup 协议。`plan`
只从固定 inventory 快照选择超过 24 小时的
`staging/user-uploads/` 与 `staging/worker-results/`，并分别要求存在
`task-inputs/` 或 `task-results/` durable twin；inventory 的 size/ETag 只作候选
预筛，进入冻结 campaign 前必须逐对象完成双 HEAD、大小和完整 SHA-256 验证，且
History 全角色、Gallery、收藏、公开、模板/归档/角色资产和活跃任务引用均为空。
未知 staging、`web_uploads/`、`temps/`、`template-submissions/`、flat-root 和单份
内容只进入排除摘要，不进入 `objects`。逐对象 404、HEAD/大小/SHA 状态变化进入
`blocked_objects` 并计入 blocked 对象数/字节；数据库、Redis、R2 鉴权/网络等系统性
探测错误直接 fail closed，不得生成看似成功的不完整计划。冻结文件记录完整对象清单、
campaign/batch ID、inventory SHA、对象数、字节和 `plan_sha256`；快照之后新增对象
天然不属于该 campaign。

`execute` 只接受与精确 `plan_sha256` 绑定的一次性确认，并将断点写入 0600 SQLite。
一次授权后可内部连续处理，每个内部批次最多 10,000 个且最多 50 GiB；每个对象
删除前重新查询全部引用并重做双 HEAD/大小/SHA。新增引用、缺失或摘要变化转为
`blocked` 并继续，删除后确认 staging key 消失且 durable SHA 不变。数据库、Redis、
R2 网络、删除后复核等系统性错误把 campaign 写为 `paused` 并立即退出；恢复时只消费
同一 campaign、plan SHA 与 inventory SHA 的 pending 记录，不重新全量枚举，也不
扩大到快照后的对象。本入口默认不执行，生产执行仍需单独取得精确 SHA 授权。

`user-data-prod` 历史媒体迁移以 History 行为事实源，不再以 bucket numeric/flat-root
分类构造全桶工作集。`scripts/history_media_r2_migration.py seed` 首先冻结
`max(history.id)`，再以 `(history_id, role, ordinal)` 流式写入本地分析库的独立
迁移账本；每批只做一次双 ID/目录查询并通过 PostgreSQL COPY staging 落账，续跑
必须绑定同一个 run 与 watermark。它只探测账本中的引用和明确候选
key，不枚举桶，也没有对象删除操作。旧 `r2_media_governance.py` 仅保留为历史治理
实现，不得用于本轮迁移或启动新的 numeric/flat-root planner。
`analytics_history_media_%` 迁移 run、对象账本、plan 和 SHA 事实表属于必须保留的
本地分析数据；cloud production shadow 换库和从 previous shadow 恢复分析表时都必须
携带这些表，不能因刷新 History 快照而丢失迁移 cursor 或精确 plan identity。

输入目标使用 `task-inputs/{registry_task_id}/{ordinal}.{ext}`；主输出和附加输出
使用 `task-results/{backend_task_id}/primary.{ext}` 与
`task-results/{backend_task_id}/extras/<role>-<ordinal>.{ext}`。输出缺少持久账本中的
明确 backend task ID、双 ID 映射冲突、角色/序号异常一律 `unresolved`；外部 URL
或无法确定属于受管存储的引用一律 `blocked`，不得以文件名猜测。

`probe` 先检查标准目标，再按受限 0600 配置中启用的来源优先级尝试原引用、
`history/{registry_task_id}/{basename}` 和 basename。相同来源对象在进程内只完整读取
一次；跨 run 只有 HEAD 的大小与 LastModified 均未变化才复用完整 SHA-256 事实。
ETag 和 size 只作预筛，源与已存在目标的最终结论必须来自完整 SHA-256。来源离线、
鉴权或系统性查询失败不等于丢失；达到系统错误阈值时 run 立即 paused。只有全部启用
来源明确 not-found 才累计 missing round，两轮至少间隔 24 小时才在本地目录标记
`confirmed_lost`，生产 History 不写“丢失”且保留原引用。
首次 probe 只消费 `pending_probe`，不会被较早的 missing/offline 行饿死；这些延迟
状态仅在显式 `--recheck-deferred` 且达到最短 24 小时后重新探测。
遗留来源系统性离线时可先用 `probe --target-only` 对标准目标做完整 SHA 验证；目标
不存在的行只记录已检查时间并保留待恢复状态，不能借此形成 missing 结论。完整来源
恢复仍在系统错误阈值处暂停。target-only 在单批内按 target key 去重，并以
`--target-concurrency` 控制 1–128 路 HEAD/完整读取；数据库结果仍串行持久化。
当迁移明确以 `user-data-prod` 中的旧目录、临时路径和原 History key 为主要恢复源时，
可用 `probe --r2-only` 同批去重并发检查标准目标、原引用、
`history/{registry_task_id}/{basename}` 与 basename；并发由 `--source-concurrency`
控制在 1–128。命中对象必须完整读取 SHA-256 后才进入 `target_verified` 或
`copy_required`。未命中只写 `r2_checked_at` checkpoint 并保持 `pending_probe`，不会
在未检查其它启用来源时累计 missing round；该模式不得调用 ListObjects 或 MinIO。
标准目标检查完成后，`probe --receipt-only` 可只消费本地目录中已有
`archived_verified` SHA receipt 的资产：它不重复检查标准目标，也不访问离线的遗留
来源，而是对 receipt 指向的 NAS 对象执行 HEAD、大小和完整 SHA-256 复核。验证成功
的资产可进入 `copy_required`；receipt 缺失、变化或 NAS 查询失败必须 blocked/paused，
且该模式不会把没有 receipt 的资产累计为 missing round。其余资产仍需等待全部启用
来源恢复后运行完整 `probe`。

`plan-copy` 和 `plan-switch` 分别生成 0600 小型 manifest，包含冻结 watermark、
分类对象数/字节、实际 SHA 读取量、最多 100 条脱敏诊断、账本行集 SHA 与精确 plan
SHA，不包含完整对象清单。`execute-copy` 只接受
`COPY_HISTORY_MEDIA_<plan-sha>`，复制前复验源，上传后完整回读目标；失败资产保持旧
History 引用。`execute-switch` 使用独立 `SWITCH_HISTORY_MEDIA_<plan-sha>`，并在
事务行锁内用 History media manifest SHA 做 CAS，只替换已验证资产。复制与引用切换
是两个独立生产 mutation，必须分别取得精确计划 SHA 授权；旧源删除、flat-root、
数字目录和孤儿清理均不属于这条迁移链路。
默认 `plan-copy` 在任何 `pending_probe` 或 paused run 上继续 fail-closed。若启用来源
长期离线，但已有一部分资产通过标准目标或 NAS receipt 得到完整 SHA 事实，可显式用
`plan-copy --allow-incomplete` 冻结部分复制计划；manifest 必须记录
`partial_scope=true`、`pending_at_freeze` 和 `run_status_at_freeze`，同时 rowset SHA 仍绑定
该 run 的全部账本行。冻结后到复制完成前不得继续 probe；执行器仍只消费带同一精确
plan SHA 的 `copy_required` 行，未解析行不进入复制或 missing 结论。paused run 不能使用
该模式。
plan/report 与执行前 rowset 复核都使用数据库 cursor 增量计算 canonical JSON SHA，
不把完整账本载入内存；copy 执行每次还受显式 limit 约束，重启只继续未完成行。

各阶段固定为 `seed`、`probe`、`plan-copy`、`execute-copy`、`plan-switch`、
`execute-switch`、`report`；除首次 `seed` 外均显式传 run ID 或 plan SHA。
`LOCAL_ANALYTICS_DATABASE_URL` 只指向本地分析库，`execute-switch` 才额外要求
`PRODUCTION_DATABASE_URL`。probe/copy 的 0600 JSON 配置包含固定
`target.bucket=user-data-prod`、与 `analytics_media_sources` 同名的全部启用来源，
以及可选的 `nas_archive`；S3 来源提供 endpoint/bucket 凭据，filesystem 来源只提供
受限 root。缺任一启用来源配置时暂停，不能把未探测来源折算成 not-found。

模板投稿新写 `template-submissions/`，旧 `temps/` 只在迁移兼容期双读且永不进入
通用临时清理。`scripts/r2_template_submission_migration.py` 在同一生产桶按原相对 key
复制并对源/目标完整 SHA-256 验证，使用 0600 SQLite 断点状态；真实迁移使用独立
精确确认值，不能借用临时清理或冷归档删除门禁。
状态库分别保存源/目标摘要和关联 contribution ID。只有全量对象 verified 后才能用
独立 `--switch-db-references` 门禁锁定并切换旧数据库引用；审批同样持有行锁，已审核
记录幂等返回，复制或事务失败不得重复发奖。

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
pytest -q tests/scripts/test_history_media_r2_migration.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
docker compose --env-file ops/media_archive_nas/.env.example -f ops/media_archive_nas/compose.yml config
python scripts/doc_quality_checker.py
```

部署后再做小批量真实对象验收、断点重跑、NAS 离线、校验错误、Range、容量告警
和两轮缺失确认演练。生产迁移必须按“热 → 最近冷 → 更早冷”逐批执行。
