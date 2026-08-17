---
name: "allbot-local-media-archive"
description: "维护 History 媒体归档、来源恢复与 R2 清理门禁。"
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
- 永久原件使用 SHA-256 寻址；History 和原 key 映射保存在回执。
- R2 迁移用冻结账本；Probe 专用 HEAD 池只走零交集 successor，Copy 聚合计划链；
  正文不经执行器，禁止全桶扫描。
- History R2 全量链路使用父计划限定的 Probe→Copy→Switch batches；只分别接受
  `PROBE_HISTORY_MEDIA_<sha>`、`COPY_HISTORY_MEDIA_<sha>`、
  `SWITCH_HISTORY_MEDIA_<sha>`。Probe 只 HEAD，Copy 必须写精确 marker，Switch
  必须重算行集和批次 CAS；旧源始终保留。
- direct predecessor marker 仅可用新 COPY 令牌的 frontier recovery HEAD 对账；
  普通 Copy 失败关闭。
- 没有 NAS 完整回读校验回执，任何 R2 原件都不得删除。
- 最新 8 条先按用户对原始 History 排名，再过滤不可见记录；Gallery 关系保护引用。
- 来源离线不是丢失。确认丢失要求全部登记来源两轮 not-found 且间隔至少 24 小时。
- R2 删除默认关闭；第一次生产删除需要 dry-run 报告和新的明确确认。
- Worker 配置须为当前用户的 0600 文件；校验网络物理路由和 filesystem 根目录，
  检测到本地 7890 代理时 fail closed。
- canary 最多精确领取 100 个 `history_ids`，禁止改写全局优先级。
- 私有配置只输出来源名/指纹；只有 `archived_verified` 提供原件。
- 租约每 5 分钟续期；回执必须匹配 revision，陈旧 Worker 不得覆盖新清单。
- restore/archive outbox 状态不得复用；所有热集触发只幂等 enqueue。
- TLS 必须验证包含 NAS IP SAN 的内部 CA；禁止 `verify=false`。
- PiGallery2 与归档完全隔离；live 容量、凭据、digest 和部署结果只属运行态。

## 最小验证

```bash
pytest -q tests/core/test_media_archive.py tests/database/test_media_archive_schema.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
python scripts/doc_quality_checker.py
```

真实部署还需验证 MinIO digest/TLS/权限/versioning/重启、直连路由、NAS 回读、
限速、自适应并发、暂存门禁和容量告警。
