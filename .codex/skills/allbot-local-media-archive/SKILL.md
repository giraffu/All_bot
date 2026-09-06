---
name: "allbot-local-media-archive"
description: "维护 History 全量媒体目录、NAS/MinIO 归档、archive/restore outbox、来源丢失核验、冷媒体恢复、迁移 copy/probe/switch 和 R2 冷清理门禁。归档不新鲜、原件不可用、丢失/恢复、媒体归档容量或清理时使用。"
---

# AllBot 本地媒体归档

## 入口

1. `docs/子模块_本地媒体归档_local_media_archive.md`
2. 涉及 R2/Gallery 引用时叠加 `allbot-gallery-storage`
3. 涉及 History 成功持久化时叠加 `allbot-task-engine`
4. NAS/生产变更加 `allbot-ops-deployment`；`AllBotInfra` 改读
   `ops/lan_artifact_nas/README.md`

## 固定边界

- NAS 归档异步消费 outbox，禁止进入 GPU Worker/Central 完成同步链路。
- 冷恢复只写 restore outbox；Web 不直连 NAS。Worker 复验后只回填
  `task-inputs/`、`task-results/` 精确键及相邻缩略图；旧引用兼容回填，HEAD
  验证后提交 revision。
- 永久原件按 SHA-256 寻址；History/原 key 映射保存在回执。
- 归档 bucket 与 blob key 统一复用 `src/core/media_archive.py` 的
  `ARCHIVE_BUCKET` / `archive_blob_key(...)`，Worker 不复制寻址规则。
- 迁移使用冻结账本和父计划限定的 Probe→Copy→Switch；并发默认值和批次参数从
  当前脚本 `--help`/代码读取，不写成 Skill 快照。禁止正文下载式探测和无界全桶扫描。
- History R2 全量链路只接受精确 PROBE/COPY/SWITCH SHA；Probe 只 HEAD，Copy 写
  marker，Switch 重算行集和批次 CAS，旧源保留。
- `plan-switch-completed` 只冻结终止 predecessor/当前 completed 批次；一次一份计划，
  仍需精确 SWITCH 令牌。
- Bulk retirement 仅收精确 DELETE SHA；blocker deferred、source-is-target retained；
  删前 HEAD 源/目标，删后仅 HEAD 源，删除只重试失败 key。
- 换 artifact 须暂停 predecessor；successor 冻 remaining planned。按旧源哈希重查
  生产引用，命中 `LIVE_HISTORY_REFERENCE` 保留；marker/ETag 漂移以
  `TARGET_IDENTITY_DRIFT` 保留；其余重授权。
- Copy lane 共用 artifact 内的动态并发、epoch、429 冷却和低基数错误门禁。
- 云 Copy/Switch 仅凭 HMAC 任务/回执跨信任域；本地独占账本，云端只连必要的 R2
  或生产库。successor 绑定 artifact/worker/route/rowset/CAS，仍需新的精确令牌。
- 未在冻结计划与 runtime identity 中显式选择耐久性依据时，任何 R2 原件都不得删除；
  `r2-persistent-target` 不声称 NAS 已归档，后续 NAS 备份从持久目标另立计划。
- 最新 8 条先按用户原始 History 排名，再过滤不可见记录；Gallery 保护引用。
- 确认丢失要求全来源两轮 not-found，间隔至少 24 小时。
- R2 冷删走 `media_archive_r2_cleanup.py` Plan→Probe→Execute；绑定两份 SHA，
  复查引用/身份并要求确认。
- Worker 配置 0600；R2 Copy 路由冻结指纹，换 artifact 后重新授权。
- canary 最多领取 100 个 `history_ids`，不改全局优先级。
- 私有配置只输出来源/指纹；仅 `archived_verified` 提供原件。
- 租约每 5 分钟续期；revision 不匹配不得覆盖。
- restore/archive outbox 状态不得复用；热集触发只幂等 enqueue。
- TLS 必须验证包含 NAS IP SAN 的内部 CA；禁止 `verify=false`。
- PiGallery2 与归档隔离；容量和部署只属运行态。

## 最小验证

```bash
pytest -q tests/core/test_media_archive.py tests/database/test_media_archive_schema.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
python3 scripts/doc_quality_checker.py
```

真实部署还需验证 MinIO digest/TLS/权限/versioning/重启、直连路由、NAS 回读、
限速、自适应并发、暂存门禁和容量告警。
