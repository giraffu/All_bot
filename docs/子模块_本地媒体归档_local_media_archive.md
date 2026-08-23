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
NAS bind mount 必须设置 `NETWORK_SHARE_MODE=true`，避免 CWA 每导入一本都递归
`chown` 整个 Calibre Library；Calibre `metadata.db` 仍只允许 CWA 单写者，禁止以
多 ingest processor 并发换取吞吐。首次大批量建库可临时关闭自动转换、Kindle 修复、
导入备份、元数据强制处理和逐次重复扫描，完成后按需恢复非逐本任务。

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
python3 scripts/archive_owned_ebook_site.py \
  --config /受限路径/ebook-archive.json \
  --state /受限路径/ebook-archive.sqlite3 \
  --limit-books 1

python3 scripts/archive_owned_ebook_site.py \
  --config /受限路径/ebook-archive.json \
  --state /受限路径/ebook-archive.sqlite3 \
  --limit-books 1 --execute

python3 scripts/archive_owned_ebook_site.py \
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
是当前用户所有的普通 0600 文件。通用归档 Worker 启动清空代理变量，发现
`127.0.0.1:7890` 则
直接拒绝，并使用 `ip route get` 校验 NAS 直连 endpoint 固定走声明的物理接口和
源地址；默认部署使用 `eno1`、`10.250.150.1/30` 到 NAS
`10.250.150.2/30`，且不配置网关；R2
拒绝 loopback、tun/wg 和 Tailscale exit-node 路径。旧来源可显式允许 Tailscale
点对点。双栈 DNS 中内核明确不可达的地址族不阻断另一个可达地址族，但至少一个地址
必须可达，且所有可达地址都要通过上述物理路由门禁。每个对象流式计算 SHA-256、上传
NAS、完整回读复算；内容键已存在且大小/
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
在线新任务的 Web/Bot/QQCC 共享 `TaskApplication` 输入准备门禁：策略选中
的 `staging/user-uploads/` 对象必须在扣费和派发前复制验证到上述
`task-inputs/` key，后续 registry、Worker 和 History 只保存提升后引用。
这一前向门禁不会自动修复既有 History；既有 staging 引用仍需独立冻结
Copy/Switch 计划，在完成前不得缩短 staging 保留或删除对象。

`probe` 先检查标准目标，再按受限 0600 配置中启用的来源优先级尝试原引用、
`history/{registry_task_id}/{basename}` 和 basename。相同来源对象在进程内只完整读取
一次；跨 run 只有 HEAD 的大小与 LastModified 均未变化才复用完整 SHA-256 事实。
NAS、旧 MinIO 和文件系统恢复的最终结论必须来自完整 SHA-256。来源离线、
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
控制在 1–128。该模式只执行 HEAD，冻结 size、LastModified 和 ETag；不得 GET 媒体
正文。旧 key 命中后进入 `copy_required`；标准目标仅在它已经是 History 当前引用时
进入 `target_verified`，否则以 `TARGET_EXISTS_UNVERIFIED` 冲突收口，禁止覆盖。
未命中只写 `r2_checked_at` checkpoint 并保持 `pending_probe`，不会在未检查其它启用
来源时累计 missing round；该模式不得调用 ListObjects 或 MinIO。
标准目标检查完成后，`probe --receipt-only` 可只消费本地目录中已有
`archived_verified` SHA receipt 的资产：它不重复检查标准目标，也不访问离线的遗留
来源，而是对 receipt 指向的 NAS 对象执行 HEAD、大小和完整 SHA-256 复核。验证成功
的资产可进入 `copy_required`；receipt 缺失、变化或 NAS 查询失败必须 blocked/paused，
且该模式不会把没有 receipt 的资产累计为 missing round。其余资产仍需等待全部启用
来源恢复后运行完整 `probe`。

全量 R2 目录迁移先使用 `plan-probe` 冻结当时全部 `pending_probe`。计划以每批
10,000 个逻辑资产保存低基数 batch、批次行集 SHA 和全局行集 SHA，不在生成计划时
给数百万账本行批量写 marker。`execute-probe` 只接受
`PROBE_HISTORY_MEDIA_<plan-sha>`，标准目标、原引用、
`history/{registry_task_id}/{basename}` 和 basename 全部只做 HEAD；不调用 GET、
ListObjects、PUT、CopyObject 或 DELETE。此前已记录 `R2_CANDIDATES_NOT_FOUND` 的
`pending_probe` 同样属于新冻结计划并重新 HEAD。每批先完成全部远端 HEAD，再把分类、
`probe_plan_sha256` 和批次完成状态写入同一本地事务；中断前没有提交的批次完整重探。
标准目标已是当前引用时进入 `target_verified`；目标存在但 History 不同进入
`target_conflict`；旧候选命中进入 `copy_required`；全部候选未命中继续保持
`pending_probe`。429、5xx、timeout 可在同一 SHA 内按 64→32→16→8 退避并在干净批次
回升到 128；鉴权和其它系统错误必须 paused，不能伪装成未命中。每次批次尝试必须用
当前自适应档位创建独立 `ThreadPoolExecutor`，不能依赖 asyncio 默认最多 32 worker 的
全局线程池；R2 HTTP 连接池至少覆盖最高 128，并在成功、异常或取消后关闭专用 executor。
批次日志只记录请求档位、实际峰值 worker、使用过的 worker 线程数、连接池大小和分类
计数，不输出 endpoint、对象 key 或凭据。

运行中的 Probe 需要切换到新 artifact 时，使用 `plan-probe-successor`，不得修改原计划
manifest。冻结事务锁定 predecessor 计划、批次和 run，只保留祖先链中
`status=completed` 的批次与现有 `probe_plan_sha256`/分类/source attempts；successor
只选择 predecessor 未完成批次内仍为 `pending_probe` 且 marker 为空的资产。冻结必须
证明 retained 与 successor 交集为 0，二者资产数等于 root Probe 总数，并分别记录
retained/successor rowset SHA 与 batches SHA；随后只把 predecessor 的非 completed
批次改为 `superseded`。在途批次若未提交，可由 successor 完整重探；批次提交会以
`status=pending` 做 CAS，已 supersede 时整批事务回滚。successor 绑定新 artifact
digest 与脚本 SHA，仍需新的 `PROBE_HISTORY_MEDIA_<successor-sha>` 才能执行。

Probe 全批完成后自动生成父计划限定的 `plan-copy`；普通 Probe 只包含当前计划，
successor 则聚合 manifest 证明的完整 predecessor/successor 链中全部 `copy_required`，
不得纳入 unresolved、blocked、target conflict、无关 Probe 或旧 Copy/Switch 批次。
Copy 冻结前必须证明祖先批次仅为 completed/superseded、链上 ledger 资产数等于 root
Probe 总数；冻结前若发现超过当前单次 CopyObject 上限的对象，
不得生成可授权的 Copy 计划。Copy manifest 绑定精确父计划、代码 SHA、artifact digest、
bucket、endpoint 指纹、候选算法版本和行集 SHA，不包含凭据或完整对象清单。
`execute-copy` 只接受 `COPY_HISTORY_MEDIA_<plan-sha>`。同一 R2 bucket 的旧 key 只能通过服务端
`CopyObject` 复制，不得 GET、落地临时文件或从执行器重新上传。执行前复验
size、LastModified、ETag，并使用 R2 目标不存在条件原子拒绝覆盖；目标通过
`MERGE` 元数据保留源 metadata 并写入精确 copy plan SHA。相同 target key 只有在
冻结来源身份完全一致时才合并为一次 CopyObject，成功后整组账本行一并收口；来源
身份冲突必须在任何对象写入前 fail closed。进程若在对象复制后、账本提交前退出，
重跑只接受 plan marker、大小和冻结来源身份全部匹配的目标，其余已存在目标仍拒绝。
`execute-copy` 的 `--copy-concurrency` 限定为 1–128，默认 1；
`--max-pool-connections` 可显式配置，不得小于 copy concurrency，省略时取并发的
1.5 倍并向上取整。直接执行入口的线程共享一个只执行 HEAD/CopyObject 的 boto3
client，数据库结果仍串行提交；每批报告 Copy-only 对象/秒、R2 对象操作延迟和数据库
提交延迟。`history_media_r2_copy_adaptive.py`
把所有 lane 的生产总并发固定在 16–32，默认从 32 起步：对象级瞬态错误先重试；
429/SlowDown 在对象尝试完成边界立即把共享 limiter 降至 16，并对全部 lane 开启
60 秒桶级冷却，新尝试在冷却结束前不得取得 slot；timeout、reset 和 5xx 统一进入
最近请求错误率，单个错误不降档。
观察已覆盖至少 200 个请求或 30 秒后，瞬态错误率超过 0.5% 才降档，低于 0.2% 可回升
一档；观察集最多保留最近 1,000 个请求和 60 秒，不要求恰好收集 1,000 个请求。每次
真实降档或回升后都清空错误率与延迟观察窗口，新档位必须使用新样本决策。R2 p95 和单对象
max 延迟只作观测，不独立改变全局并发，因此单个超长尾不会触发降档。最高为 32。这些阈值
属于 artifact 代码身份，不提供生产 CLI 热调参入口。非瞬态错误
直接暂停。SIGTERM/SIGINT 只登记
graceful pause，当前批次完成并
提交账本后退出；CPU 门禁把进程 CPU 时间除以当前进程 cpuset/可用逻辑 CPU 数，按
整机可用容量百分比判断，日志同时保留原始进程 CPU 百分比、容量百分比和 CPU 数。
连续三批容量 CPU 超过 70%、FD 超过软上限 50% 或数据库提交 p95 相对 canary 基线
显著恶化时，于当前批次提交后暂停。自适应入口以一个 supervisor 管理十条逻辑 lane，
新的 Copy successor 仍冻结为每批 1,000 个资产；执行器每条 lane 默认每次只领取
100 个资产，完成后便立即领取同余序列的下一批，不等待其它 lane 的长尾。所有 lane
共享一个动态总并发门禁，默认总并发 32 由 16 个 bulk worker 和 16 个 retry worker
共同组成，并非每条 lane 各自 32。总连接池按 lane 划分且总容量不低于总并发；每条
lane 每批使用独立 client 并在
批次成功、失败或取消后关闭，supervisor 退出时统一关闭 bulk/retry 线程池。首尝试与
瞬态重试分属独立有界线程池，SDK 在
该模式只执行一次网络尝试，外层重试负责 1、2、4、8、16 秒退避，避免 SDK 隐藏重试
长期占满 bulk worker。任一对象完成即提交其 `copied_verified`，一个慢对象只占对应
lane/retry 槽位，实际 HEAD/CopyObject 总数始终不超过当前动态档位。当前生产执行器在
冻结计划含超过单次 CopyObject 上限的对象时暂停，不能未经独立设计和 canary 临时
切入 multipart。非 R2、跨 endpoint、来源变化或 marker 不匹配均 fail closed，失败
资产保持旧 History 引用。

通用归档 Worker 仍禁止 7890、环境代理和 tun/wg 路由。冻结的 History R2 Copy
只有在配置显式声明精确 `https_proxy` 传输且 URL 为
`http://127.0.0.1:7890` 时，才可使用这一窄例外。计划 runtime identity 保存传输
模式、端口和代理 URL 的 SHA-256，不保存明文 URL；缺省 transport 固定为 direct，
boto3 client 显式传入空代理表，因此 `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY`
均不能改变冻结路由。执行器必须先通过确认令牌、artifact digest、脚本、endpoint、
全局/批次行集和来源资格校验，再探测本机 listener 并创建只用于本批 HEAD/CopyObject
的代理 client；listener 不可达时 fail closed。代理切换不能热改运行中容器：须先构建
新 artifact，受控停止旧执行器，保留全部 `copied_verified`，冻结零交集 successor，
取得新 `COPY_HISTORY_MEDIA_<sha>` 后先运行 CopyObject canary。HEAD 延迟 A/B 只作为
候选依据，不能替代 CopyObject marker、来源保留、错误率、FD 和数据库提交验收。

需要避开本地主机到 R2 的异常链路时，Copy successor 可冻结
`copy_execution.mode=cloud_receipt`、协议版本和固定 `worker_id`。该模式仍使用同一
不可变 `database-migration` artifact，但拆成两个信任域：本地协调器是
`analytics_history_media_r2_migrations` 的唯一写者；云端 worker 不暴露服务端口，
不连接本地分析库或生产库，只读取 0600 R2 配置、执行 HEAD/CopyObject，并写回
原子替换的 HMAC-SHA256 签名回执。任务 bundle 通过既有 SSH 主机别名传输，绑定
plan SHA、artifact digest、worker identity、runtime identity、ledger IDs 与 canonical
rowset SHA；日志和标准输出只允许低基数计数、延迟、错误类别与 request ID 哈希，不能
输出 endpoint、对象 key、凭据或签名密钥。

本地 `export-copy-task` 在每个冻结计划首次导出前完整重算全局 rowset/batches SHA，
把结果写入低基数 plan session；之后每个最多 1,000 资产的任务只在事务内锁定当前
批次并重算批次身份。一个计划同时只能存在一个未过期任务租约。云端禁用 SDK 隐式
重试，由对象级外层重试负责退避；每个成功对象立即进入签名 checkpoint，进程中断时
本地只提交已证明的子集，其余仍为 `copy_required`。本地导入器重新验证 bundle、回执
签名及当前账本行集，以 CAS 写入 `copied_verified`；retryable 不改归属，fatal 隔离。
签名、计划、artifact、worker、来源身份、marker 或行集任一不符都不得提交。

云端路径启用前先用同一签名 HEAD bundle 对本机与目标云主机做只读 A/B；这一步不得
调用 GET、ListObjects、CopyObject、DELETE 或数据库写入。artifact、配置和签名密钥可
在新 COPY 授权前安全暂存，但不得导出或运行 Copy task。取得精确
`COPY_HISTORY_MEDIA_<cloud-successor-sha>` 后，先运行单个云端 canary，再连续领取同一
计划任务。`analytics_history_media_r2_cloud_copy_plan_sessions` 和
`analytics_history_media_r2_cloud_copy_tasks` 是本地迁移状态，必须与其它迁移表一起
跨 shadow 换库保留。

Copy successor 若在目标 HEAD 发现 direct predecessor marker，普通执行器仍必须立即
暂停，不能把 predecessor marker 当作当前计划成功。此状态可能来自 predecessor 已完成
CopyObject、但在账本提交前受控停机。修复入口分为独立的 `plan-copy-recovery` 与
`execute-copy-recovery`：计划只冻结 direct predecessor 的第一个 superseded frontier
批次内、当前计划尚未提交的资产，并绑定新 artifact、行集 SHA 与精确
`COPY_HISTORY_MEDIA_<recovery-plan-sha>`。执行只对该 frontier 做来源和目标 HEAD；只有
来源 size/Last-Modified/ETag 未变、目标 size/ETag 相同且 marker 精确属于当前计划或
direct predecessor 时，才在一个本地事务恢复账本归属。任意其它 marker、来源变化、
行集漂移或 CAS 变化整批失败关闭。对账完成后自动冻结新的 Copy successor；真正继续
Copy 仍需该 successor 的新 COPY 令牌。该协议不接受任意旧计划 marker，也不扩展历史
marker 例外，不调用 GET、ListObjects、CopyObject、DELETE 或生产 History 更新。

安全停止的当前 Copy 计划若只残留对象级瞬时 `failed`，使用
`reconcile-copy-failures` 做无额外阶段令牌的修复性对账；该入口不具备 Copy 权限，
只对精确计划仍为 `failed` 且错误文本可由当前 artifact 证明为瞬时异常的行执行来源与
目标 HEAD。`ProxyConnectionError`、urllib3 `ProxyError`、“无法连接冻结代理”以及
SDK 的 `Read timeout on endpoint URL`、TLS `UNEXPECTED_EOF_WHILE_READING` 文案
属于对象级瞬时错误，进入既有指数退避，不再直接终止整个执行器；证书校验错误仍为
fatal。对账冻结 failed
行集及错误详情摘要，复核原计划 bucket、endpoint 与 transport 指纹，同时把新代码和
artifact 身份写入 0600 回执；来源 size/Last-Modified/ETag 必须未变。目标缺失时仅把
行恢复为 `copy_required`，目标存在时只接受 size/ETag 相同且 marker 精确属于当前计划，
并恢复为 `copied_verified`；predecessor 或任意其它 marker 均失败关闭。远端 HEAD 全部
通过后才在一个本地事务锁行并重算摘要，随后自动用 `plan-copy --supersedes-plan-sha256`
冻结 successor。对账不调用 GET、ListObjects、CopyObject、DELETE，不更新生产 History；
successor 执行仍必须取得新的 `COPY_HISTORY_MEDIA_<successor-sha>`。

Copy 全批完成后自动生成 `plan-switch`。它只选择精确父 Copy 计划内、
`copied_verified`、`switch_completed_at is null` 且原路径不同于目标路径的资产，
因此不会再次纳入既有已完成 Switch、其它 Probe、unresolved 或 blocked。计划每
1,000 条 History 保存生产 CAS 状态 SHA，并冻结所有可证明的前序 Switch plan identity。
`execute-switch` 使用独立 `SWITCH_HISTORY_MEDIA_<plan-sha>`；任何生产更新前重算全局
资产行集，每批以 10 秒 lock timeout 锁定 History 后重算批次 CAS。所选坐标只能仍为
原路径，或在本计划提交后因账本回执失败而已是目标路径；非所选坐标只能是原路径，或
由 `switch_completed_at` 和精确前序 plan 共同证明的目标路径。其它值、坐标变化、父计划
变化或前序集合变化全部 fail closed。每批在单个生产事务内只更新 `input_file`、
`output_file` 和 `extra_outputs.*.path`，生产提交后才在本地事务写完成回执；重跑幂等。
复制与引用切换
是两个独立生产 mutation，必须分别取得精确计划 SHA 授权；旧源删除、flat-root、
数字目录和孤儿清理均不属于这条迁移链路。

本地到生产 PostgreSQL 链路不适合长时间执行 Switch 时，不得把同时连接本地账本和
生产库的 `execute-switch` 原样搬到云主机，也不得在生产行锁期间通过反向隧道读取本地
账本。`scripts/history_media_r2_cloud_switch.py plan-successor` 只在旧执行器安全停止后，
保留 predecessor 全部已完成资产和批次，把尚未完成资产原子改绑到零交集 successor，
并将旧计划未完成批次标为 `superseded`。successor 冻结 artifact、worker、生产 DSN
非秘密路由指纹、全局/批次 rowset、每批 CAS 和 predecessor identity；生成计划不授权
生产更新，仍须新的 `SWITCH_HISTORY_MEDIA_<successor-sha>`。CAS 冻结以有界窗口一次
预取多个逻辑批次的生产 History，再逐个生成原有 1,000-History 批次 SHA，避免远程
PostgreSQL 为每个逻辑批次单独往返。冻结行集按 History 排序且窗口密集时，以有界
最小/最大 ID 范围做顺序主键扫描，再严格筛回冻结 ID；预取窗口和范围内额外读取均不得
改变批次边界、所选行集或 CAS 内容。规划查询只投影 CAS 所需的
`history_id/role/ordinal/path`，不得回传完整 `extra_outputs` 元数据。

取得精确令牌后，本地 `export-task` 首次完整重算全局行集和 predecessor，随后每次只
锁定并导出一个最多 1,000 个 History 的 HMAC-SHA256 任务。任务携带该批全部媒体坐标
证据，但不携带数据库凭据；云端 `run-task` 只连接 `PRODUCTION_DATABASE_URL`，以 10 秒
lock timeout 锁 History、重算冻结 CAS，并在单个事务更新引用。生产已是本计划目标值时
按幂等重试处理。云端提交后写 0600 签名回执；本地 `import-receipt` 再验证 plan、task、
artifact、worker、路由、批次 rowset/CAS 和账本归属，之后才写
`switch_completed_at`/批次完成。任务租约过期可另发新任务；旧任务变为 `expired`，不得
连接生产库或导入迟到回执。`analytics_history_media_r2_cloud_switch_plan_sessions` 和
`analytics_history_media_r2_cloud_switch_tasks` 必须随 shadow 本地表一起保留。

长时间运行的 Copy 不要求等待整个 successor 才开始切换。`plan-switch-completed`
冻结终止 predecessor 中已提交的对象，以及当前父 Copy 计划内状态为 `completed` 的
精确批次；当前 pending/running 批次、未提交对象和已有未完成 Switch 计划全部排除。
冻结器保存 completed batch identity SHA，并继续复用 `execute-switch` 的全局 rowset、
每批生产 CAS、前序 Switch identity 和 `SWITCH_HISTORY_MEDIA_<sha>` 门禁。一次只能存在
一份未完成的滚动 Switch 计划；后续新完成的 Copy 批次进入下一份新计划，不能追加或
热改既有 manifest。

已完成 Switch 的旧来源通过 `scripts/history_media_r2_retirement.py` 进入独立退役协议。
`report` 只读汇总父 Copy 计划的去重旧对象、字节、Copy/Switch/目标冲突和本地归档覆盖，
并可生成按可释放字节排序的最多 1,000 条 History 归档候选；报告不访问对象正文、不写
数据库。归档继续使用既有 outbox/Worker，精确 canary 每波最多 100 条 History，1,000
条阶段由十个有序波次组成。`plan-delete` 必须显式冻结耐久性依据，缺省
`nas-archive` 只接受这批 History 的生产 `archived_verified` 回执和 archived outbox，
逐对象要求所有共享资产均有同一 SHA-256 NAS 完整回读证据。操作者也可显式选择
`r2-persistent-target`：该模式不读取或声称 NAS 回执，只适用于已 Copy 到标准持久目标且
已完成 Switch 的对象，要求目标精确 Copy plan marker、size、ETag 均通过 HEAD 复核。
两种模式都要求生产 History 零引用、没有未完成 Copy/Switch 使用、旧 key 不属于任何
标准目标，并在 manifest、runtime identity 和 rowset SHA 中绑定所选模式；配置或模式
变化必须生成新计划。单范围 `plan-delete` 最多冻结 1,000 对象且为 0600，只保存 key
哈希和聚合，不在 manifest 保存明文对象 key。

多个已完成 Switch 范围统一退役使用 `plan-bulk-delete`。调用方必须逐个给出不可重复的
Switch plan SHA 及其预期资产坐标数；冻结器流式重算完整坐标集合，要求所有坐标已经
Switch、属于同一 migration run，并派生完整 Copy plan 集合。全局 manifest 同时绑定每个
Switch rowset、每 10,000 坐标分块聚合的资产 SHA、去重旧源 rowset、内部 batches SHA、artifact/runtime
identity 和 R2 持久目标耐久性；任一计数、来源事实、父链或身份漂移都生成不同计划或
fail closed。Bulk v2 把全部旧源冻结为三个不相混合的 disposition：`eligible` 先形成
100 个旧源 canary 和后续最多 1,000 对象批次；仍被其它 Copy/Switch 使用的来源进入
`deferred` 独立批次，每批执行前重检 blocker，未解除时安全暂停并可用同一计划续跑；
旧源 key 同时也是任一标准持久目标的对象进入 `retained_target` 审计批次，在冻结时以
`SOURCE_IS_TARGET` 终态保留，永不进入 HEAD/DELETE 执行集合。三个 disposition 的对象数
和资产坐标数都写入 manifest，三者之和必须等于完整 Switch 范围。一个
`DELETE_HISTORY_MEDIA_<global-plan-sha>` 同时授权 canary 和该 manifest 的全部内部批次，
canary 完整提交后同一执行器自动续跑，不再逐批请求令牌；重启仍只恢复同一冻结计划的
未完成批次。计划表记录全部 Switch 资产坐标覆盖，删除对象数则按旧来源去重，两者不得
混为同一计数。冻结阶段不下载媒体正文，也不调用 ListObjects 或任何删除；实际删除前
完整复核来源与全部标准目标，删除后以同一批次 rowset/目标存活证明只完整 HEAD 旧源。

Bulk v2 的旧源身份策略固定为 `etag-or-size-last-modified`：账本有 ETag 时仍要求 HEAD
精确匹配；历史账本 ETag 为空时，只能以冻结 size 加 R2 Last-Modified 的双重精确匹配
替代，缺任一项或时间漂移都停止。该兼容策略写入全局 manifest，不适用于旧的单范围
计划，也不能放宽目标对象的 Copy marker、size 或 ETag 门禁。

真实删除只接受新的 `DELETE_HISTORY_MEDIA_<retirement-plan-sha>`；不能复用 COPY、
SWITCH、临时清理或通用冷归档令牌。Bulk v4 把每批调度为三个阶段：删前 HEAD、批量
DELETE、删后源 HEAD。计划身份固定 `persistent-context-bulk-delete-v3`；只读 HEAD
默认及硬上限为 128，按 `128→64→32` 运行。DELETE 使用每块 250 个 key 的
`DeleteObjects`，默认最多 4 块并发，每个响应必须逐 key 被 `Deleted` 或 `Errors` 完整
覆盖；瞬时失败只重试失败 key，最多 5 次，未知错误或响应覆盖漂移 fail closed。每个 HEAD
请求最多尝试 5 次，只重试失败请求：429/SlowDown 立即降一档；至少
200 个当前档位样本中 timeout/5xx 错误率超过 0.5% 才降档，低于 0.2%
的两个健康窗口可回升，系统性错误率达到 10% 则打开 circuit breaker 并暂停
计划。单个长尾不单独触发降档。R2/NAS 连接池必须覆盖配置的 HEAD 最高并发。
删前仍重新扫描生产 History 与迁移账本并复核旧源身份和全部耐久目标；成功的删前
survivor proof 绑定批次 rowset，删后只 HEAD 计划内旧源并要求全部 404，不重复请求目标。
NAS 模式的目标和 NAS SHA 同样必须在删前通过。R2/NAS 客户端、连接池、HEAD controller
和专用线程池在一个 Bulk 计划内跨批次复用，退出时统一关闭；生产引用连接短暂断开时在
同一计划内限次重连，持续不可用仍暂停。每阶段输出对象数、请求数、实际/峰值并发和耗时
等低基数指标，不输出 key。系统性网络、数据库、身份或行集变化把
计划置为 paused；旧源已经因本计划提交窗口消失时，也只有冻结的耐久副本仍完整才可
幂等收口。R2 持久目标模式不等于完成 NAS 归档；待持久目录迁移验收后，从该目录到 NAS
的备份必须使用独立归档计划。退役 plans/batches/objects 与其它迁移事实表一起跨 shadow
换库保留。正在运行的 Copy 可以和零交集低并发退役并行，但任何仍作为 Copy 来源的对象
都必须留存。

运行中的 Bulk retirement 更换 artifact 时不得改写原 manifest，也不得让新 artifact
冒用旧 digest。先停止 predecessor 执行器；已完成批次、`deleted`/`SOURCE_IS_TARGET`
回执和对应批次 SHA 永久保留。`plan-bulk-delete-successor` 只冻结 predecessor 中仍为
`planned` 的对象，证明累计保留对象与 successor 对象等于 root 对象/资产坐标总数，
并把 predecessor 的非完成批次置为 paused。successor 沿用 predecessor 的 disposition，
但冻结 remaining 前必须把候选旧源计算为 32-byte SHA-256 集合，并对生产 History 三种
路径角色重新做一次集合半连接；命中者在 predecessor 中以 `LIVE_HISTORY_REFERENCE`
终态隔离保留，不进入 successor。Bulk v5 successor 绑定这批保留对象的对象数、资产
坐标数和 rowset SHA；累计已完成/继承保留、目标身份漂移隔离、实时引用隔离与 remaining
必须共同等于 root 范围。每个执行批次仍精确重检新增生产引用和本地 blocker。未提交的
在途删除可由 successor 以 source-already-missing 路径重新完成删后验证；两计划对象交集
按状态为零。successor 绑定新 artifact、请求调度策略、rowset/batches SHA，仍需新的
`DELETE_HISTORY_MEDIA_<successor-sha>`；旧 executor 必须保持停止，不能与 successor
竞争 paused 批次。

若 predecessor 因标准持久目标的 marker/ETag 身份漂移暂停，禁止重启原执行器、改写
原 manifest 或放宽目标门禁。操作者只向 successor 冻结器提供精确旧源身份哈希；冻结器
必须用当前不可变 artifact 重新 HEAD，证明旧源 size/ETag（或 size/Last-Modified）仍与
账本一致、目标仍存在且 size 一致，同时至少一个冻结 marker/ETag 确实漂移。通过后，该
旧源在 predecessor 账本中以 `TARGET_IDENTITY_DRIFT` 终态隔离并永久保留，不进入新计划
的 HEAD/DELETE 集合；其对象数、资产坐标数、对象行集 SHA 和低基数 HEAD 证据 SHA 都
写入 Bulk v4 successor manifest。隔离状态、新计划写入和 predecessor 暂停必须在同一
本地事务提交；任何哈希、状态或计数漂移全部回滚。守恒关系为“predecessor 已完成/继承
保留 + 本次身份漂移隔离 + successor remaining = root 范围”，successor 仍需新的精确
DELETE 令牌。

Bulk 冻结对生产 History 的零引用核对先把 `eligible` 来源在本地计算为固定 32-byte
SHA-256，再分块写入生产会话专属临时表；临时表建立唯一索引并 ANALYZE，查询会话关闭或
事务提交即清除。History 三种路径角色只与该摘要集合做一次哈希半连接；命中的摘要流式
回传本地并把对应 `eligible` 来源改冻为 `deferred`，随后才计算对象顺序、批次和全局 SHA。
摘要碰撞最多导致保守延后，不会漏掉真实引用；每个 deferred 批次执行前仍以明文精确 key
重检生产引用。查询关闭并行且以会话级 256 MB `work_mem` 约束单次哈希，避免把数百万条
长 key 的哈希表落盘；不得创建生产永久索引或持久辅助表。

Bulk 执行只把计划内 `eligible` 或已解除 blocker 的 `deferred` 旧来源放入批量 DELETE；
标准持久 `target_key` 和 `retained_target` 永远是生存
副本，不得进入删除集合，也不提供 bucket/prefix 清理入口。任一批次异常把全局计划及
运行中批次置为 `paused`，已完成批次和已删除对象回执保留；相同 artifact、runtime 和
全局令牌可幂等恢复。最后一个批次完成后仍需核对全部对象回执、资产坐标守恒、生产零
引用、目标存活及 Gallery/owner 读取链路。shadow pause guard 只能由外部操作者在最终
验收全部通过后解除，退役脚本不得调用 systemctl 或解锁。

大批退役前先运行 `prepare-delete-indexes`，以 `CREATE INDEX CONCURRENTLY` 准备并回读
pending/failed 来源、未完成 Switch 来源和 `target_key` 三项 blocker 索引。执行门禁把本批
来源一次性物化为低基数 `selected` 集合，通过三个集合 JOIN 的 `UNION ALL` 和
`EXISTS ... LIMIT 1` 早停；禁止恢复逐来源相关 `EXISTS`。查询固定 60 秒超时，并只输出
来源数、耗时和 blocker 布尔值等低基数指标。执行连接中断时必须另建账本连接重试写入
`paused`；若新连接仍不可用，外部 supervisor 仍按冻结计划和零删除回执 fail closed，不能
假定计划已暂停或复用其它计划的令牌。

Copy 计划的全局 rowset 与内部批次都按迁移账本 `id` 顺序冻结和重算，不能在执行端
改用 History 坐标排序。successor 的每个 1,000 资产批次在领取时重算自己的 rowset
SHA；supervisor 启动时只做一次全局行集、父链、来源资格和 multipart 预检，避免十条
lane 重复扫描数百万行。每个对象最多做 5 次瞬时错误重试，默认退避为
1、2、4、8、16 秒并加入随机抖动；bulk lane 持续补充新对象，完成结果独立提交
`copied_verified`，不会因一个慢请求等待整组。执行器按最近 1,000 次请求且不超过
60 秒的窗口控制全局并发：429/SlowDown 立即降档，timeout/reset/5xx 等错误率在至少
200 个请求或 30 秒观察后超过 0.5% 才降档，低于 0.2% 可升一档。档位改变立即清空观察窗口；
健康事件在每次请求完成时汇入 supervisor 的跨 lane 全局窗口，不能等单个 lane 收口后
再用该 lane 的尾部样本代替全局流量。每个事件保存取得并发 slot 时的实际档位；档位改变后，
仍在收口的旧 epoch 事件只用于对象回执和观测，不得进入新窗口或连续触发多次降档。
延迟长尾只记录不降档。连续系统性高错误窗口由 circuit breaker 暂停；单个瞬态错误不触发
全局降速。任一 lane 捕获 429/SlowDown 时无需等待这 100 个资产收口：共享 limiter
立即降到 16，并以最后一次限流事件为起点延长 60 秒桶冷却；已经在途的请求允许收口，
所有尚未取得 slot 的 bulk/retry worker 一起等待。事件和日志不得保存对象 key、endpoint
或原始 provider request ID，只记录 `source_head_before`、`target_head_before`、
`copy_object`、`source_head_after`、`target_head_after` 等低基数阶段、错误类别、HTTP
状态和 request ID SHA-256 样本，供 R2 支持工单关联。

旧 manifest、marker 与确认值永远不可热改或跨 artifact 复用。`plan-copy` 显式提供
`--supersedes-plan-sha256` 时分两类：未执行计划可整体替换；已有进度的计划必须先让
旧执行器 graceful stop，要求没有 `failed` 或在途批次，再保留全部
`copied_verified` 及其旧 marker，只冻结仍为 `copy_required` 的零交集 successor。
事务同时插入绑定新 artifact 的计划、保留 completed 批次、把其余旧批次置为
superseded，并以计划所有权 CAS 重绑剩余账本；迟到的旧执行器提交会失败关闭。
manifest 必须证明“Copy 链已完成资产 + successor 资产 = 根 Copy 计划资产数”，保存
successor rowset/batches SHA 和 predecessor 链 SHA。最终目标/旧源/marker 验收与
Switch 计划聚合完整 Copy 链，marker 仍按每个对象实际所属计划验证。替代计划必须展示
新 SHA 并重新取得 `COPY_HISTORY_MEDIA_<new-sha>`。
冻结全量链路不允许 `--allow-incomplete` 绕过未完成 Probe 批次。plan/report 与执行前
rowset 复核使用数据库 cursor 增量计算 canonical JSON SHA，不把完整账本载入内存；
Copy 和 Switch 通过 batch 表断点续跑。阶段为 `plan-probe`、`execute-probe`、
`plan-copy`、`execute-copy`、`plan-switch`、`execute-switch`、`report`，其中计划生成、
只读核对、监控、重试和后续计划生成连续进行，只在 PROBE/COPY/SWITCH 三个精确令牌
暂停。三个计划都绑定创建它们的精确 artifact digest；旧 artifact 不得消费新计划。

最终验收必须完整核对计划引用、目标 HEAD/size/Copy marker 和旧来源 HEAD，并确定性
抽查至少 32 个活跃 Gallery 与 64 个 History/owner，覆盖角色和媒体类型；
apply-context 的既有不支持场景继续按契约返回 400。只有这些验收和收据全部通过，才能
解除 shadow pause guard、清理旧 failed unit 状态并手动跑一次 shadow sync。核心
Probe→Copy→Switch 验收本身不自动删除旧 R2 对象；只有另行冻结并取得精确 DELETE
授权的退役计划可以删除其证明为零引用且已归档的对象。迁移 plans/batches、云 Copy 和
retirement 事实表必须随 shadow 换库保留。

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
python3 scripts/doc_quality_checker.py
```

部署后再做小批量真实对象验收、断点重跑、NAS 离线、校验错误、Range、容量告警
和两轮缺失确认演练。生产迁移必须按“热 → 最近冷 → 更早冷”逐批执行。
