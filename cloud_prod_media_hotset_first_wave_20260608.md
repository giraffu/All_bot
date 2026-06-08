# 云正式媒体热集首批处理报告（2026-06-08）

## 结论

已按“非全量迁移、不中断正式服务”的方式完成首批 500 条热集对象处理。

- 未重建、未重启、未进入修改 `cloud-web-api-prod` / Bot / Central API 正式服务容器。
- 未修改生产数据库记录。
- 未删除 legacy MinIO 数据。
- 只向正式 R2 桶写入缺失的原文件与缩略图。
- 最终复查：首批 500 条热集的原文件 R2 命中 `500/500`，缩略图 R2 命中 `500/500`，失败 `0`。

## 执行方式

本机直连正式数据库失败，原因是当前机器无法访问 DigitalOcean 托管 Postgres `25060` 端口。随后改为在云控制面主机运行一次性维护容器：

- 使用正式 `cloud-web-api-prod` 当前镜像。
- 只挂载当前工作区新版脚本到容器 `/app/scripts/backfill_history_r2_objects.py`。
- 只挂载 logs 目录用于报告输出。
- 不更新正式服务镜像，不重启正式容器。

正式服务容器复查状态：

- `cloud-web-api-prod`: `Up 4 hours (healthy)`
- `cloud-central-api-prod`: `Up 8 hours (healthy)`
- `cloud-tg-bot-prod`: `Up 22 hours`

## Baseline Dry-Run

报告：

- `/home/deploy/APP/All_bot/logs/cloud-prod-media-hotset-dryrun/media_hotset_backfill_cloud-prod-lag-fix_20260608_141659.json`
- `/home/deploy/APP/All_bot/logs/cloud-prod-media-hotset-dryrun/media_hotset_backfill_cloud-prod-lag-fix_20260608_141659.md`

汇总：

| 指标 | 数量 |
| --- | ---: |
| scanned | 500 |
| media_exists | 223 |
| media_would_upload | 275 |
| media_missing_on_source | 2 |
| media_failed | 0 |
| thumbnail_exists | 223 |
| thumbnail_would_copy | 247 |
| thumbnail_missing_on_source | 30 |
| thumbnail_failed | 0 |

判断：安全门槛通过。原文件源缺失 `2/500 = 0.4%`，低于 10%；无 R2/storage 异常。

## Apply 1：原文件写入

报告：

- `/home/deploy/APP/All_bot/logs/cloud-prod-media-hotset-apply/media_hotset_backfill_cloud-prod-lag-fix_20260608_143431.json`

汇总：

| 指标 | 数量 |
| --- | ---: |
| scanned | 500 |
| media_exists | 224 |
| media_uploaded | 274 |
| media_missing_on_source | 2 |
| media_failed | 0 |
| thumbnail_skipped | 500 |

## Apply 2：legacy 缩略图复制

报告：

- `/home/deploy/APP/All_bot/logs/cloud-prod-media-hotset-apply/media_hotset_backfill_cloud-prod-lag-fix_20260608_144005.json`

汇总：

| 指标 | 数量 |
| --- | ---: |
| scanned | 500 |
| media_exists | 498 |
| media_failed | 0 |
| thumbnail_exists | 231 |
| thumbnail_copied | 239 |
| thumbnail_missing_on_source | 30 |
| thumbnail_failed | 0 |

## 缩略图生成 Dry-Run

报告：

- `/home/deploy/APP/All_bot/logs/cloud-prod-media-hotset-thumb-gen-dryrun/media_hotset_backfill_cloud-prod-lag-fix_20260608_144403.json`

汇总：

| 指标 | 数量 |
| --- | ---: |
| scanned | 500 |
| media_exists | 498 |
| media_would_upload | 2 |
| media_failed | 0 |
| thumbnail_exists | 470 |
| thumbnail_would_copy | 2 |
| thumbnail_would_generate | 28 |
| thumbnail_failed | 0 |

## Apply 3：缺失缩略图生成

报告：

- `/home/deploy/APP/All_bot/logs/cloud-prod-media-hotset-apply/media_hotset_backfill_cloud-prod-lag-fix_20260608_144846.json`

汇总：

| 指标 | 数量 |
| --- | ---: |
| scanned | 500 |
| media_exists | 499 |
| media_uploaded | 1 |
| media_failed | 0 |
| thumbnail_exists | 471 |
| thumbnail_copied | 1 |
| thumbnail_generated | 28 |
| thumbnail_failed | 0 |

## 最终复查

报告：

- `/home/deploy/APP/All_bot/logs/cloud-prod-media-hotset-verify/media_hotset_backfill_cloud-prod-lag-fix_20260608_145140.json`

汇总：

| 指标 | 数量 |
| --- | ---: |
| scanned | 500 |
| media_exists | 500 |
| media_would_upload | 0 |
| media_missing_on_source | 0 |
| media_failed | 0 |
| thumbnail_exists | 500 |
| thumbnail_would_copy | 0 |
| thumbnail_would_generate | 0 |
| thumbnail_missing_on_source | 0 |
| thumbnail_failed | 0 |

## 判断

首批热集卡顿原因在 dry-run 中得到验证：处理前只有 `223/500` 原文件和 `223/500` 缩略图已在 R2，超过一半热内容需要走 legacy 回源或缺少缩略图。处理后首批 500 条热集对象已全部进入 R2 标准路径。

建议先观察线上“修仙市集”最新/最多点赞/最多应用第一页，以及近期“修仙笔记”的响应时间和 legacy assets 请求量。若仍有明显慢请求，再按同样方式继续下一批 500；暂不建议直接扩大到全量或大批量。
