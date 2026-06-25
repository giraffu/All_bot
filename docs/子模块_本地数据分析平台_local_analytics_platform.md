# 子模块: 本地数据分析平台 (Local Analytics Platform)

## 1. 目标与范围

本模块是项目根目录下的独立本地分析服务，代码位于 `local_analytics_platform/`。它不挂载到现有 Dashboard 菜单，不导入 `dashboard/backend` 或 `dashboard/frontend` 模块，也不承担线上管理后台的用户、任务、RunPod 或系统管理功能。

当前入口:
- 前端页面: `local_analytics_platform/static/index.html`
- 后端 API: `local_analytics_platform/app/main.py`
- 容器编排: `local_analytics_platform/docker-compose.yml`
- 默认本地端口: `8095`

## 2. 数据边界

- 数据库必须通过 `LOCAL_ANALYTICS_DATABASE_URL` 显式配置，当前本地主服务器运行态指向 `127.0.0.1:5434/bot_db_prod_shadow`。
- 后端所有业务查询通过 PostgreSQL 只读事务执行，并设置短 `statement_timeout`；不得回写 shadow 业务表。
- 媒体桶默认显示为 `user-data-prod-shadow`。未配置 `LOCAL_ANALYTICS_MEDIA_PUBLIC_BASE_URL` 时只展示对象 key，不生成可访问媒体 URL。
- 本平台不要求冷热桶或 R2 全量合并；媒体数据只作为分析样本和引用核验辅助。

## 3. 当前功能

- 经营概览: 用户、生成、付费、Prompt 解锁和每日趋势。
- 充值分析: RMB / TON / Stars / 内部订单分开统计，包含首充和复购分层。
- 生成分析: 按任务类型、来源、结果记录、收藏、投稿、应用和灵石消耗聚合。
- 提示词洞察: 基于结果存在、收藏、投稿、点赞、应用和解锁等信号生成候选评分，并抽取轻量标签。
- 模板候选: 从高分 prompt 样本中展示可人工沉淀的场景候选。
- 媒体核验: 从 `history.input_file`、`history.output_file`、`history.extra_outputs` 解析输入输出对象引用。

## 4. 运维口径

- 启停只操作 `allbot-local-analytics-platform` 容器，不重建现有 Dashboard backend/frontend。
- 本地主服务器旧版 `docker-compose 1.29.2` recreate 可能触发 `ContainerConfig` 兼容问题；恢复时只删除 `local-analytics-platform` service 对应容器后再 `up -d --no-deps`。
- 该平台当前面向本地/LAN 分析使用；如需公网访问，必须先加 Cloudflare Access 或等价身份层保护。

## 5. 验证要求

- `GET /api/health` 返回 `bot_db_prod_shadow`。
- `GET /api/overview`、`/api/finance`、`/api/generation`、`/api/prompts`、`/api/media-audit` 均能返回基础数据。
- Playwright 桌面与窄屏检查应确认 `body[data-loaded="true"]`、无前端 console error、无整页水平溢出。
- 现有 Dashboard 后端路由表不得出现 `/api/local-analytics`。
