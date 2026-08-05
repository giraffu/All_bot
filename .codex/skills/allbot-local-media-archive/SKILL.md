---
name: "allbot-local-media-archive"
description: "建设和维护 AllBot History 全量媒体目录、NAS MinIO 归档、异步 outbox、来源恢复、丢失确认、R2 冷清理门禁与本地归档浏览。"
---

# AllBot 本地媒体归档

## 必读入口

1. `docs/子模块_本地媒体归档_local_media_archive.md`
2. 涉及 R2/Gallery 引用时叠加 `allbot-gallery-storage`
3. 涉及 History 成功持久化时叠加 `allbot-task-engine`
4. 涉及 NAS/Compose 或生产变更时叠加 `allbot-ops-deployment`

## 固定边界

- NAS 归档异步消费 outbox，禁止进入 GPU Worker/Central 完成同步链路。
- 永久原件使用 SHA-256 内容寻址；History 和原 key 映射保存在目录/回执。
- 没有 NAS 完整回读校验回执，任何 R2 原件都不得删除。
- 最新 8 条必须先按用户对原始 History 排名，再过滤不可见记录；收藏、公开、
  活跃 Gallery 及其关系继续保护引用。
- 来源离线不是丢失。确认丢失要求全部登记来源两轮 not-found 且间隔至少 24 小时。
- R2 删除默认关闭；第一次生产删除需要 dry-run 报告和新的明确确认。
- Worker 配置必须为当前运行用户所有的普通 0600 文件；NAS 路由必须命中声明的
  物理接口和源地址，检测到本地 7890 代理时 fail closed。
- 租约每 5 分钟续期，成功/失败回执必须匹配当前 revision；陈旧 Worker 不得覆盖
  已变化的媒体清单。
- TLS 必须验证包含 NAS IP SAN 的内部 CA；禁止 `verify=false`。
- 个人 PiGallery2 与 AllBot Archive 不复用目录、账号、容器或数据生命周期。
- live 容量、IP、凭据、镜像 digest 和部署结果属于运行态，不写入本 Skill。

## 最小验证

```bash
pytest -q tests/core/test_media_archive.py tests/database/test_media_archive_schema.py
pytest -q tests/local_analytics tests/services/test_storage_web_history_r2_cache.py
python scripts/doc_quality_checker.py
```

真实部署还需验证 MinIO digest/TLS/权限/versioning/重启、物理直连路由、NAS 回读
摘要、50 MiB/s 总限速、8/16/32 自适应并发、100/90 GiB 暂存门禁和
75%/80%/90% 容量告警。
