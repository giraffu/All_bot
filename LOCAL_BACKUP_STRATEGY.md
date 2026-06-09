# 本地 MinIO 与 PostgreSQL 云正式备份方案

## 1. 目标

本文档用于规划一套本地备份体系：

- 将 Cloudflare R2 正式桶 `user-data-prod` 持续备份到本地 MinIO。
- 将云正式 PostgreSQL 持续备份到本地 PostgreSQL/本地归档目录。
- 在云正式控制面或云托管数据面整体异常时，为 `docs/子模块_本地正式灾备切换_local_prod_fallback.md` 提供可恢复的数据来源。

这套本地服务不是第二套长期生产，也不是新的业务写入面。正常生产事实源仍是：

- 正式数据库：云正式 PostgreSQL。
- 正式对象存储：Cloudflare R2 `user-data-prod`。
- 本地 MinIO：继续承担 legacy 历史媒体只读 fallback；新增的备份桶必须和 legacy fallback 桶隔离。
- 本地 PostgreSQL：只保存备份归档、恢复演练库和灾备窗口临时恢复库。

## 2. 总体架构

```text
云正式应用写入
  ├─ 云 PostgreSQL
  │    └─ 本地备份任务 pg_dump 拉取
  │         ├─ 本地 dump 归档目录
  │         └─ 本地 PostgreSQL restore_test 校验库
  │
  └─ R2 user-data-prod
       └─ 本地备份任务 rclone/mc 拉取
            └─ 本地 MinIO 独立备份桶
```

建议把本地数据分成三类，避免互相污染：

| 类型 | 建议位置 | 用途 |
| :--- | :--- | :--- |
| R2 备份桶 | `local-minio/r2-user-data-prod-backup` | R2 正式对象的本地备份副本 |
| DB dump 归档 | `/home/hfy/APP/All_bot/backups/cloud-prod-db/` 或独立大盘挂载 | 可追溯、可加密、可离线保存的 PostgreSQL dump |
| DB 恢复演练库 | `bot_db_prod_restore_test` / `bot_db_prod_restore_test_<ts>` | 每次备份后验证 dump 可恢复 |
| 本地灾备运行库 | `bot_db` 或本地正式 `.env` 指定库 | 只在本地正式灾备窗口恢复并接入业务 |

本地 MinIO 的 legacy fallback 桶和 R2 备份桶必须分开。不要把 R2 备份直接同步进旧 `bot-data`、`comfyui-temp`、`bot-template` 等 legacy 桶。

## 3. 推荐 RPO/RTO

先采用保守、容易维护的逻辑备份方案：

| 数据 | 推荐 RPO | 推荐 RTO | 说明 |
| :--- | :--- | :--- | :--- |
| R2 对象 | 1 小时内 | 取决于对象总量与本地 MinIO 状态 | 以增量 copy 为主，不把 R2 删除立即同步为本地删除 |
| PostgreSQL | 4 小时内 | 15-60 分钟 | 使用 `pg_dump -Fc`，每晚做恢复演练 |
| 订单/余额/会员关键表 | 跟随 DB RPO，事故后人工核对 | 视对账范围而定 | 灾备期间新增写入必须回切前对账 |

如果后续希望 DB RPO 缩短到 15 分钟以内，再评估 WAL 归档、托管库 PITR 或流复制。第一阶段不建议直接做本地热主从，因为网络抖动、权限、主从延迟和误切主风险都更高。

## 4. 工具选择

### 4.1 R2 到本地 MinIO

推荐优先使用 `rclone copy`：

- R2 和 MinIO 都是 S3 兼容对象存储，`rclone` 配置和校验相对直观。
- 日常任务默认只追加/覆盖有变化的对象，不删除本地备份中已经存在但 R2 后来删除的对象。
- 可通过 manifest 和 `rclone check` 做抽样或全量校验。

S3 兼容存储的大对象可能经过 multipart upload，不同后端的 ETag/checksum 语义未必完全一致。备份命令先采用 rclone 默认的 size/mtime 增量判断；如果实测两端 checksum 兼容，再加 `--checksum`。

可选工具是 MinIO Client `mc mirror`，但需要避免误用 `--remove`。只有在人工确认要做“本地镜像完全等于 R2 当前状态”时，才允许使用删除同步。

### 4.2 云 PostgreSQL 到本地 PostgreSQL

第一阶段使用逻辑备份：

- `pg_dump -Fc --no-owner --no-acl` 生成自定义格式 dump。
- `pg_restore` 恢复到本地临时库验证。
- 归档 dump 加密保存，并按保留策略清理。

注意：

- `pg_dump` 客户端版本应与云 PostgreSQL 主版本一致，或至少不能低于云端版本。
- 备份连接只走 Tailscale、SSH tunnel、托管库安全白名单或云内堡垒路径，不直接把云数据库暴露给公网。
- dump 和日志不得输出数据库密码、连接串、R2 Secret、Bot token。

## 5. 本地准备

### 5.1 目录与密钥文件

建议创建本地只读运维配置文件，文件不提交 Git：

```bash
cd /home/hfy/APP/All_bot
install -m 700 -d backups/cloud-prod-db backups/r2-manifests logs/backups
touch .env.backup.local
chmod 600 .env.backup.local
```

`.env.backup.local` 只保留占位字段，真实值只在本机维护：

```bash
# R2 正式桶
R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<r2-readonly-or-backup-key>
R2_SECRET_ACCESS_KEY=<r2-secret>
R2_BUCKET=user-data-prod

# 本地 MinIO 备份桶
LOCAL_MINIO_ENDPOINT=http://127.0.0.1:9000
LOCAL_MINIO_ACCESS_KEY=<local-minio-key>
LOCAL_MINIO_SECRET_KEY=<local-minio-secret>
LOCAL_MINIO_R2_BACKUP_BUCKET=r2-user-data-prod-backup

# 云正式 PostgreSQL
CLOUD_PROD_DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db>

# 本地 PostgreSQL
LOCAL_POSTGRES_URL=postgresql://postgres:<password>@127.0.0.1:5432/postgres
LOCAL_RESTORE_DB_PREFIX=bot_db_prod_restore_test
```

建议确认 `.env.backup.local` 已被 `.gitignore` 忽略；若没有忽略，应先补充忽略规则再写入真实值。

### 5.2 本地 MinIO 桶

初始化一个独立备份桶：

```bash
mc alias set local http://127.0.0.1:9000 "$LOCAL_MINIO_ACCESS_KEY" "$LOCAL_MINIO_SECRET_KEY"
mc mb --ignore-existing "local/$LOCAL_MINIO_R2_BACKUP_BUCKET"
```

建议开启本地 MinIO 桶版本化或至少保留多期 manifest。若本地磁盘容量有限，优先保留关键业务路径：

- `history/`
- 用户上传输入文件路径
- Gallery/apply-context 依赖的输入与缩略图
- 模板相关对象

但正式落地前最好完成一次全桶基线备份，避免“只备热集”导致灾备时历史链路缺对象。

### 5.3 本地 PostgreSQL

本地 PostgreSQL 至少需要两个用途分离：

- `bot_db_prod_restore_test*`：自动恢复演练库，可随任务重建。
- `bot_db`：本地正式灾备运行库，只在灾备切换窗口恢复最新已验证 dump。

日常备份任务不得直接覆盖 `bot_db`。只有确认要执行本地正式灾备切换时，才允许把最新已验证 dump 恢复到本地正式运行库。

## 6. R2 备份流程

### 6.1 rclone remote

示例 remote 名称：

- `r2_prod`：Cloudflare R2 正式桶所在账号。
- `local_minio_backup`：本地 MinIO。

推荐将 R2 凭据设置为最小权限：能 `ListBucket`、`GetObject` 即可。除非要做人工回填，不给备份任务 `PutObject` 到 R2 的权限。

### 6.2 首次基线备份

```bash
set -euo pipefail
TS="$(date +%Y%m%d_%H%M%S)"
LOG="logs/backups/r2_backup_${TS}.log"
MANIFEST="backups/r2-manifests/r2_user_data_prod_${TS}.txt"

rclone copy \
  "r2_prod:user-data-prod" \
  "local_minio_backup:r2-user-data-prod-backup/current" \
  --transfers 16 \
  --checkers 32 \
  --fast-list \
  --log-file "$LOG" \
  --log-level INFO

rclone lsf -R "local_minio_backup:r2-user-data-prod-backup/current" \
  | sort > "$MANIFEST"
```

说明：

- 使用 `copy` 而不是 `sync`，避免 R2 误删或生命周期删除立即传播到本地备份。
- 目标路径使用 `current/`，便于灾备时按原 key 读取。
- manifest 用于比对、审计和恢复前确认。

### 6.3 增量备份

定时执行同一条 `rclone copy` 即可。对象量很大时，可以按前缀分片：

```bash
rclone copy "r2_prod:user-data-prod/history" "local_minio_backup:r2-user-data-prod-backup/current/history"
rclone copy "r2_prod:user-data-prod/templates" "local_minio_backup:r2-user-data-prod-backup/current/templates"
```

若 R2 当前没有统一顶层前缀，不要为了美观改写 key。备份必须保持原 object key，否则现有媒体 URL 策略和历史 fallback 候选会变复杂。

### 6.4 校验

每日做一次 manifest 和抽样对象校验：

```bash
rclone lsf -R "r2_prod:user-data-prod" | sort > "backups/r2-manifests/r2_remote_latest.txt"
rclone lsf -R "local_minio_backup:r2-user-data-prod-backup/current" | sort > "backups/r2-manifests/r2_local_latest.txt"
comm -23 "backups/r2-manifests/r2_remote_latest.txt" "backups/r2-manifests/r2_local_latest.txt" > "backups/r2-manifests/r2_missing_local.txt"
```

关键对象可以抽样 `HEAD` 或 `cat`：

```bash
rclone check "r2_prod:user-data-prod/history" "local_minio_backup:r2-user-data-prod-backup/current/history" --one-way --size-only
```

`rclone check` 对大桶可能耗时较长，建议夜间执行或按前缀分批执行。

## 7. PostgreSQL 备份流程

### 7.1 备份

```bash
set -euo pipefail
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="/home/hfy/APP/All_bot/backups/cloud-prod-db"
DUMP="$BACKUP_DIR/cloud_prod_${TS}.dump"
LOG="/home/hfy/APP/All_bot/logs/backups/db_backup_${TS}.log"

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG")"

pg_dump "$CLOUD_PROD_DATABASE_URL" \
  -Fc \
  --no-owner \
  --no-acl \
  --file "$DUMP" \
  >"$LOG" 2>&1

sha256sum "$DUMP" > "${DUMP}.sha256"
```

如本地有 `age` 或 GPG，建议加密归档：

```bash
age -r "<backup-recipient>" -o "${DUMP}.age" "$DUMP"
shred -u "$DUMP"
sha256sum "${DUMP}.age" > "${DUMP}.age.sha256"
```

若暂不做加密，至少保证备份目录权限只允许本机运维用户访问。

### 7.2 恢复演练

每次 DB 备份完成后，至少恢复到本地测试库验证 dump 可用：

```bash
TS="$(date +%Y%m%d_%H%M%S)"
RESTORE_DB="bot_db_prod_restore_test_${TS}"

createdb "$RESTORE_DB"
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --dbname "$RESTORE_DB" \
  "$DUMP"
```

如果恢复库需要经过 Alembic 校验，可以在应用环境里执行只读检查：

```bash
DATABASE_URL="postgresql+asyncpg://postgres:<password>@127.0.0.1:5432/${RESTORE_DB}" alembic current
```

建议增加关键表行数快照，作为备份是否异常缩水的快速信号：

```sql
select 'users' as table_name, count(*) from users
union all select 'history', count(*) from history
union all select 'orders', count(*) from orders
union all select 'gallery_posts', count(*) from gallery_posts
union all select 'user_interactions', count(*) from user_interactions;
```

实际表名以当前 schema 为准；若某张表不存在，不要为了备份脚本在主业务代码中增加兼容空表或假字段。

### 7.3 保留策略

第一阶段建议：

- 最近 7 天：保留每 4 小时一份 DB dump。
- 最近 4 周：保留每日 1 份夜间 dump。
- 最近 3 个月：保留每周 1 份 dump。
- 每次正式发布或重大迁移前：额外保留一份人工标记 dump。

清理脚本只能删除本地 `backups/cloud-prod-db/` 下的归档，不得连接云数据库做任何删除操作。

## 8. 定时任务建议

建议先用 systemd timer，便于统一看日志与失败状态。

后续可落三个脚本：

| 脚本 | 用途 |
| :--- | :--- |
| `scripts/backup_r2_to_local_minio.sh` | 拉取 R2 `user-data-prod` 到本地 MinIO 备份桶 |
| `scripts/backup_cloud_prod_db_to_local.sh` | dump 云正式 PostgreSQL 并生成校验和 |
| `scripts/verify_local_backup_restore.sh` | 恢复最新 DB dump 到本地测试库，并抽样校验 R2 对象 |

systemd timer 建议：

| 任务 | 频率 | 说明 |
| :--- | :--- | :--- |
| R2 增量 copy | 每小时 | 不删除本地对象 |
| DB dump | 每 4 小时 | 生成校验和，可选加密 |
| DB restore test | 每晚 | 恢复最新 dump 到临时库 |
| R2 manifest/check | 每晚 | 大桶按前缀分批 |

失败处理：

- 任一备份任务连续失败 2 次，需要人工查看日志。
- DB 备份成功但恢复演练失败，视为不可用备份，不允许作为灾备恢复源。
- R2 copy 成功但 manifest 缺失关键前缀，视为降级备份，需要补跑。

## 9. 与本地正式灾备切换的衔接

当云正式整体不可用，需要切本地正式灾备时，按以下顺序接入备份数据：

1. 冻结或确认云端写入已经停止。若云端仍能登录，先停止 `cloud-tg-bot-prod`，避免同 token 双实例。
2. 选择最近一份“DB dump 成功 + restore test 成功”的备份。
3. 把该 dump 恢复到本地正式灾备运行库，例如本地 `.env` 指向的 `bot_db`。
4. 不把本地 MinIO R2 备份桶直接改成 legacy 桶；业务读路径仍优先 R2，R2 不可用时再评估是否临时把本地备份桶作为只读媒体源。
5. 启动本地正式灾备服务，按 `docs/子模块_本地正式灾备切换_local_prod_fallback.md` 验证 Bot/Web/Payment/Dashboard。
6. 灾备期间所有新增订单、余额、会员、任务历史和对象写入都需要单独记录，云端恢复后先对账再回切。

如果 R2 也不可用，但本地 MinIO 备份桶可用，建议采用“只读媒体恢复”策略：

- 历史页、Gallery、apply-context 可以从本地 MinIO 备份桶回源。
- 新生成任务是否允许继续写本地 MinIO，需要人工确认。允许写入意味着回切云正式时还要把灾备期间新增对象补传回 R2。
- 不建议在没有补传脚本和对账清单的情况下，把本地 MinIO 备份桶直接作为长期写入事实源。

## 10. 风险与控制

| 风险 | 影响 | 控制措施 |
| :--- | :--- | :--- |
| 误用 `rclone sync --delete` | R2 误删会传播到本地备份 | 日常只用 `copy`；删除同步必须人工审批 |
| 备份桶和 legacy 桶混用 | 历史 fallback、R2 镜像、灾备恢复 key 混乱 | 独立 bucket，保持原 key，不改写前缀 |
| 本地 restore test 直接覆盖正式灾备库 | 本地灾备库被日常任务污染 | 自动演练只用 `bot_db_prod_restore_test*` |
| 备份凭据权限过大 | 备份机泄漏后可改云数据 | R2 凭据只读；DB 凭据优先只读 dump 权限 |
| 未校验 dump | 灾备时才发现备份不可恢复 | 每晚恢复演练，失败备份不可作为恢复源 |
| 灾备期间产生新写入 | 回切云正式时数据分叉 | 冻结、记录、对账、补传对象后再回切 |

## 11. 禁止事项

- 禁止把本地 MinIO 备份桶配置为云正式 worker 的写入目标。
- 禁止把本地 PostgreSQL restore test 库配置为任何生产 API 的 `DATABASE_URL`。
- 禁止将 `.env.backup.local`、数据库 dump、R2 Secret、云数据库连接串提交到 Git 或贴到聊天/文档。
- 禁止日常备份任务执行 `safe_deploy.sh`、`safe_deploy_cloud_prod.sh` 或重启生产容器。
- 禁止未经过恢复演练的 DB dump 作为本地正式灾备恢复源。
- 禁止未对账就把本地灾备期间的数据简单覆盖回云正式库。

## 12. 落地优先级

1. 建立 `.env.backup.local`、本地 MinIO 独立备份桶、DB dump 归档目录。
2. 手工完成一次 R2 全桶基线 `copy`，生成 manifest。
3. 手工完成一次云正式 DB `pg_dump`，恢复到本地测试库，并记录关键表行数。
4. 编写并 dry-run 三个脚本：R2 backup、DB backup、restore verify。
5. 接入 systemd timer 和失败告警。
6. 将本方案验证后的最终操作细节同步到 `docs/子模块_本地正式灾备切换_local_prod_fallback.md` 或新增正式备份 runbook。
