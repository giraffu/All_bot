---
name: "allbot-local-media-archive"
description: "维护 History 全量媒体目录、NAS/MinIO 归档、archive/restore outbox、来源丢失核验、冷媒体恢复、迁移 copy/probe/switch 和 R2 冷清理门禁。用户报告归档不新鲜、NAS 原件打不开、媒体丢失/待恢复、容量或清理问题时使用。"
---

# AllBot 本地媒体归档

## 入口

1. `docs/子模块_本地媒体归档_local_media_archive.md`
2. 涉及 R2/Gallery 引用时叠加 `allbot-gallery-storage`
3. 涉及 History 成功持久化时叠加 `allbot-task-engine`
4. 涉及 NAS/Compose 或生产变更时叠加 `allbot-ops-deployment`

## 固定边界

- NAS 归档异步消费 outbox，禁止进入 GPU Worker/Central 完成同步链路。
- 冷媒体恢复只写 restore outbox；Web 不直连 NAS。Worker 复验摘要、回填原件并
  重建输出缩略图后才提交当前 revision 回执。
- 永久原件按 SHA-256 寻址；History/原 key 映射保存在回执。
- 迁移使用冻结账本和父计划限定的 Probe→Copy→Switch；并发默认值和批次参数从
  当前脚本 `--help`/代码读取，不写成 Skill 快照。禁止正文下载式探测和无界全桶扫描。
- History R2 全量链路使用父计划限定的 Probe→Copy→Switch batches；只分别接受
  `PROBE_HISTORY_MEDIA_<sha>`、`COPY_HISTORY_MEDIA_<sha>`、
  `SWITCH_HISTORY_MEDIA_<sha>`。Probe 只 HEAD，Copy 必须写精确 marker，Switch
  必须重算行集和批次 CAS；旧源始终保留。
- `plan-switch-completed` 只冻结终止 predecessor/当前 completed 批次；一次一份计划，
  仍需精确 SWITCH 令牌。
- 旧源 retirement 显式冻结耐久性依据：默认 `nas-archive` 要求 NAS SHA 回读；
  `r2-persistent-target` 要求已完成 Copy/Switch、生产零引用、无迁移依赖及目标
  marker/size/ETag。两者都只接受 `DELETE_HISTORY_MEDIA_<sha>`。
- direct predecessor marker 仅由新 COPY 令牌的 frontier HEAD recovery 对账；停止计划的
  transient `failed` 仅 HEAD 对账后冻结 successor 并重新授权。
- Copy lane 共用 artifact 内的动态并发、epoch、429 冷却和低基数错误门禁。
- `cloud_receipt` Copy 中本地协调器是账本唯一写者；SSH 仅传 0600 HMAC 任务/回执，
  云端只做 HEAD/CopyObject 且不连数据库。身份或签名不符 fail closed，新 successor
  canary 仍需 COPY 令牌。
- 未在冻结计划与 runtime identity 中显式选择耐久性依据时，任何 R2 原件都不得删除；
  `r2-persistent-target` 不声称 NAS 已归档，后续 NAS 备份从持久目标另立计划。
- 最新 8 条先按用户原始 History 排名，再过滤不可见记录；Gallery 保护引用。
- 确认丢失要求全来源两轮 not-found，间隔至少 24 小时。
- R2 删除默认关闭；首次生产删除需要只读报告、冻结计划和新精确确认。
- Worker 使用 0600 配置并校验路由/filesystem，默认拒绝 7890；仅冻结 History R2 Copy
  可绑定 loopback 7890 指纹和 artifact/successor，须重新授权并 canary，禁止热改。
- canary 最多领取 100 个 `history_ids`，禁止改写全局优先级。
- 私有配置只输出来源/指纹；仅 `archived_verified` 提供原件。
- 租约每 5 分钟续期；revision 不匹配不得覆盖。
- restore/archive outbox 状态不得复用；所有热集触发只幂等 enqueue。
- TLS 必须验证包含 NAS IP SAN 的内部 CA；禁止 `verify=false`。
- PiGallery2 与归档隔离；容量、凭据、digest、部署只属运行态。

## 最小验证

```bash
pytest -q tests/core/test_media_archive.py tests/database/test_media_archive_schema.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
python3 scripts/doc_quality_checker.py
```

真实部署还需验证 MinIO digest/TLS/权限/versioning/重启、直连路由、NAS 回读、
限速、自适应并发、暂存门禁和容量告警。
