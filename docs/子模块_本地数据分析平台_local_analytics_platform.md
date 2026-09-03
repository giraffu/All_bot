# 子模块：本地数据分析平台（Local Analytics Platform）

本文件只维护当前边界、事实源和运维入口。字段清单、提示词规则版本、一次刷新
结果和历史功能演进不在这里重复；分别以代码、专项文档和 archive 为准。

## 1. 定位与入口

本地分析平台是 `local_analytics_platform/` 下的独立 LAN 服务，不属于线上
Dashboard，也不复用 `dashboard/backend` 或 Dashboard Vue 应用。

| 责任 | 当前入口 |
| --- | --- |
| FastAPI 装配 | `local_analytics_platform/app/main.py` |
| 页面 | `local_analytics_platform/static/index.html` |
| 本地编排 | `local_analytics_platform/docker-compose.yml` |
| 模块说明和常用命令 | `local_analytics_platform/README.md` |
| Shadow 同步后刷新 | `scripts/run_local_analytics_shadow_pipeline.py` |
| 用户画像快照 | `local_analytics_platform/app/refresh_user_profile_snapshots.py` |
| Prompt Mart / slim / token / vector | 对应 `refresh_prompt_*.py` 入口 |
| R2 History 快照备份索引 | `scripts/refresh_r2_history_snapshot_analytics.py` |
| NAS 快照原件 loopback 网关 | `scripts/serve_r2_history_snapshot_nas.py` |

默认 LAN 端口和实时容器状态属于部署配置/运行态；操作前从 Compose、env 和 live
health 回读，不从本文复制历史快照。

## 2. 按任务路由

| 任务 | 必读事实源 / Skill |
| --- | --- |
| 页面、API、shadow 数据边界 | 本文 + `local_analytics_platform/README.md` |
| 词元、同义映射、删除规则、模板候选和自由 P 图拆解 | `allbot-local-analytics-prompt-semantics` + `docs/子模块_本地数据分析平台提示词词义分析_prompt_semantics.md` |
| History 媒体、NAS MinIO、归档状态 | `allbot-local-media-archive` + 归档专项文档 |
| R2 治理/媒体引用 | `allbot-gallery-storage`；需要删除或迁移时再加 `allbot-ops-deployment` |
| 登录、公网 hostname、Access/Tunnel | `allbot-cloudflare-ops` |
| Compose、重启、配置投影、数据库迁移 | `allbot-ops-deployment` |
| 慢查询、页面 5xx、刷新卡住、定时任务失败 | `ops-log-monitor` + `allbot-diagnosing-bugs` |

不要为了一个词元规则任务加载本平台全部 API，也不要把本文件当成提示词语义规则
清单。

## 3. 数据边界

- 业务事实来自显式配置的 shadow PostgreSQL。用户、订单、History、Gallery 和
  账本等线上镜像表只允许只读查询，禁止从本平台回写业务状态。
- `analytics_*` 是本地派生数据，不等于线上业务事实。刷新器可以在 shadow
  数据库内维护这些分析表；因此“业务表只读”不代表整个连接绝不写入。
- API 查询使用短事务、`statement_timeout` 和有界连接池/子查询并发。调整并发前
  先观测数据库临时空间、连接数和端点分段延迟，不用扩大池掩盖全表扫描。
- 用户画像趋势依赖 `analytics_user_profile_daily_snapshots`。业务表最新时间只能
  证明 shadow 已同步，不能证明画像快照或 Prompt 派生数据已刷新。
- NAS 归档原件只通过登录保护的本地 API 只读流式提供；浏览器不获得 MinIO
  凭据。R2 治理页面只消费脱敏摘要，不返回对象 key、预签 URL 或 secret。
- R2 History 快照备份与正式 `analytics_media_asset_catalog` 归档是两套独立事实源。
  `analytics_snapshot_backup_*` 只投影冻结 manifest、对象 inventory、下载 state 和
  NAS 批次 receipt；不得把“批次中出现”或“下载 completed”直接等同于已备份，只有
  对象完成且所属 NAS 批次为 `verified` 才是 `backed_up`。
- 快照备份状态固定区分 `backed_up`、`file_missing`、`not_backed_up`、
  `backing_up` 和 `backup_failed`。其中 inventory 不存在或终态 404 才显示文件缺失；
  inventory 存在但尚未处理显示未备份。冻结快照之外的新 History 不推测状态。

## 4. 当前模块地图

| 能力 | 主要代码 |
| --- | --- |
| 健康与总览兼容 | `routes_health.py`、`routes_overview.py` |
| 用户画像与人群下钻 | `routes_users.py`、`user_profile_analytics.py` |
| 灵石和充值 | `routes_credit_flow.py`、`routes_finance.py` |
| 生成分析与 History 明细 | `routes_generation.py`、`routes_generation_history.py` |
| Prompt Mart、瘦身、向量、词元、模板和拆解 | `routes_prompts.py` 及 `prompt_*.py` |
| 归档媒体 | `routes_archive.py` |
| R2 治理摘要 | `routes_r2_governance.py` |
| 登录/session | `auth.py` |

`/api/overview` 只保留状态摘要和旧链接兼容，不是业务首页事实源。已退役的“近似
代表、近似图、语义场景、语义图谱”不再作为公开 Tab/API；旧派生表只有在
`scripts/cleanup_local_analytics_prompt_derivatives.py` dry-run 明确命中后，才能
经新的删除授权执行。

## 5. 刷新与新鲜度

稳定顺序是：

1. 云正式数据只读同步到本地 shadow；
2. 刷新/补齐当天用户画像快照；
3. 按需要刷新 Prompt Mart、slim、tokens、embedding 和模板候选；
4. 分别检查业务 shadow、画像快照和 Prompt state 的时间/版本；
5. 再通过目标 API/页面验证，不用“容器运行中”代替数据新鲜度。

`scripts/run_local_analytics_shadow_pipeline.py` 是同步后编排入口，默认 dry-run；
命令参数和当前阶段组合从 `--help`、代码和 focused tests 获取。向量锁被占用时，
允许画像快照已更新而 Prompt 链跳过；报告必须区分这两层结果。

规则或 normalization version 变化时，增量刷新可以拒绝旧版本。只有代码明确要求
时才做 full rebuild；不要为一次小规则调整反复全量扫描。

快照备份索引首次从 immutable manifest 与 inventory 流式构建，之后只按短事务读取
下载 SQLite 中新增的已验收批次和当前活动批次，避免长读事务阻塞下载器。索引保存在
本机 shadow PostgreSQL 的派生表中；媒体正文仍只在 NAS 批次目录，不迁入 PostgreSQL。
对象状态同时汇总到每个 History 一行的 `analytics_snapshot_backup_history_status`，
列表计数和状态筛选只读该表；每次新批次仅重算受影响的 History，禁止在页面请求中
关联扫描全部 manifest 引用。
页面用 opaque ref ID 请求原件，FastAPI 只向绑定 loopback、带域隔离 token 的网关代理；
网关通过只读 SSH 路径打开 NAS 普通文件并支持 Range。Cloudflare 请求仍在内容读取前
拒绝，公网只能查看状态，不能读取原件。

## 6. 安全与运维门禁

- LAN 使用也要保留 bind/Trusted Host/Origin/登录边界；公网访问必须同时启用
  应用登录和 Cloudflare Access，不能暴露数据库、MinIO 或服务端口。
- 密码只保存 hash；session secret、数据库 URL、MinIO/R2 凭据、媒体 URL 和
  用户提示词不得进入 Git、日志或报告。
- 查慢、5xx、磁盘/临时空间不足时先只读采集 health、release/config 身份、
  PostgreSQL 活动和目标端点延迟；日志检查不授权 restart、清表或重建。
- shadow 同步、派生表重建、旧表清理、Compose 重启和公网入口变更都是 mutation。
  生产/Cloudflare/数据库 mutation 仍需用户明确授权。
- 当前功能清单以实际路由注册和静态页面 Tab 为准；不要从 archive changelog 恢复
  已退役 API。

## 7. 最小验证

```bash
.venv/bin/python -m pytest -q tests/local_analytics
python3 scripts/doc_quality_checker.py
```

运行态变更还需验证：

- `/api/health`、登录/session 和目标 Tab API；
- shadow 业务表时间、画像 `snapshot_date/captured_at` 与 Prompt state 分层新鲜度；
- 只读业务事务、派生表写入范围和数据库资源占用；
- NAS/R2 页面不泄露凭据、对象 key 或私密媒体；
- 快照 `backed_up` 必须可追溯到 verified batch，缺失/未备份筛选与明细一致；
- Cloudflare 入口未登录/已授权行为与本地应用登录均成立。

历史功能演进已归档到
`docs/archive/knowledge-base-changelog/local_analytics_platform_history_through_20260818.md`，
只用于追溯，不作为当前 SOP。
