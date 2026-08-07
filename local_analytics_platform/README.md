# Local Analytics Platform

独立的本地数据分析平台。它不复用、不修改现有 Dashboard 代码，只读连接本地 shadow PostgreSQL，并把本地分析页面暴露在单独端口。

## Scope

- 用户画像、灵石收支、充值情况、生成分析、历史生成、提示词洞察、提示词瘦身、提示词向量化、模板候选和媒体引用核验；用户画像以固定画像看板、人群透视分析、用户宽表和单用户详情抽屉为主，用户画像 Tab 使用开始/结束日期控件精确收敛周期范围。`/api/user-analytics` 返回固定 KPI、快照趋势、状态占比、转化漏斗和充值率对比；固定 KPI 覆盖总用户、周期活跃、从未活跃、沉睡、入宗门、生成、真实付费、低信任、豁免低信任和投稿封禁。`/api/user-analytics/groups` 继承用户宽表的日期、搜索和分层筛选后按同一套画像字段聚合人群，`/api/user-analytics/users` 支持按人群分桶下钻，`/api/user-analytics/users/{user_id}` 展示单用户画像；旧用户增长概览、旧分布图和排行榜不再作为用户画像 Tab 主入口；`/api/overview` 仅保留给侧栏状态和旧链接兼容。
- 用户画像人群规模趋势使用本地派生表 `analytics_user_profile_daily_snapshots`，由 `python -m app.refresh_user_profile_snapshots` 在每日 shadow 刷新后 upsert；快照记录周期活跃、从未活跃和沉睡用户等人群状态。`visualizations.trend` 会按用户画像 Tab 选择的日期范围合并每日数据与最近快照，表缺失时页面仍展示当前汇总，只是不显示快照趋势和环比。
- 用户画像、灵石收支、充值情况、生成分析继续使用本地静态 `ECharts 6.0.0` 呈现坐标轴、图例、tooltip、donut、漏斗、堆叠柱、累计折线、分时对比和风险散点；不复用 Dashboard Vue 构建链。
- 灵石收支接口返回 `daily_categories[]`；充值接口返回渠道折算 USDT 日字段，并提供 `/api/finance/hourly-comparison`、`/api/finance/hourly-cumulative`；生成接口提供 `/api/generation/hourly-comparison`、`/api/generation/hourly-cumulative`、`/api/generation/type-comparison`。
- 历史生成 Tab 读取 `GET /api/generation-history`，固定每页 10 条；支持 History/task/用户、任务类型、归档角色/状态和异常筛选。媒体详情读取 `/api/generation-history/{id}/media`，原件由 `/api/archive/assets/{id}/content` 从 NAS 流式返回并支持 Range；Cloudflare Tunnel 请求会在鉴权前被拒绝。`GET /api/archive/status` 展示归档进度、字节、吞吐、outbox 积压、来源异常、容量门禁和暂停原因；收藏数量表示单条记录是否收藏的 `0/1`。R2 治理 Tab 通过登录保护的 `GET /api/r2-governance/status` 读取 `R2_TEMP_CLEANUP_EVIDENCE_ROOT` 下私有 JSON，只展示 inventory、staging、候选/删除/阻断和 `web_uploads/` report-only 趋势，不返回对象 key 或 R2 地址；Compose 将宿主机 `data/r2-governance/` 只读挂载到该目录，受控同步到这里的 JSON 必须是脱敏摘要。若同步器写入 `central-result-storage-metrics.json`，同页还展示 Central 按稳定错误码聚合的持久化失败/拒绝计数。
- 页面顶部周期控件按当前 Tab 独立保存；用户画像 Tab 使用开始/结束日期，其他 Tab 使用统计周期下拉；切换周期或点击刷新只请求当前 Tab 对应接口，避免一次刷新扫描所有分析模块。
- 提示词洞察页通过 Prompt Mart 读取预清洗数据，不再在页面刷新时现场扫描 `history.prompt`；支持分页搜索、任务类型、来源范围、最少用户/次数和排序筛选，并可在详情面板懒加载同组原文变体；默认排除一键应用生成的衍生记录和 `prompts.ini` 内置默认模板，同时保留原始 Gallery 模板的点赞、应用、评论和解锁信号；内置模板可通过 `builtin_template` 来源范围单独查看。
- 数据库连接必须通过 `LOCAL_ANALYTICS_DATABASE_URL` 显式传入。
- API 查询使用本地 asyncpg 连接池，默认 `LOCAL_ANALYTICS_DB_POOL_MAX_SIZE=5`；灵石收支、生成分析、提示词洞察和提示词瘦身会在端点内部对独立统计 SQL 做限流并发，避免刷新时串行等待所有子查询，同时不把 PostgreSQL 临时空间打满。
- API 查询使用只读事务，不回写 shadow 业务库。
- 媒体预览 URL 可通过 `LOCAL_ANALYTICS_MEDIA_PUBLIC_BASE_URL` 配置；未配置时只展示对象 key。
- 内置模板识别默认读取仓库根目录 `prompts.ini`；Compose 会把该文件只读挂载到容器 `/app/prompts.ini`，也可用 `LOCAL_ANALYTICS_PROMPTS_INI` 指向其它 INI。

## Run

```bash
LOCAL_ANALYTICS_DATABASE_URL="postgresql://user:password@127.0.0.1:5434/bot_db_prod_shadow" \
docker-compose -f local_analytics_platform/docker-compose.yml up -d --build
```

默认监听 `8098`。如果需要改端口，设置 `LOCAL_ANALYTICS_PORT`。

## Login Protection

本地分析平台默认不启用登录，便于 LAN 内只读排障。若要公网访问，必须显式开启应用登录，并在 Cloudflare 侧再套 Access：

```bash
python -m local_analytics_platform.app.auth hash-password 'replace-with-strong-password'
# 或在容器内:
docker exec allbot-local-analytics-platform python -m app.auth hash-password 'replace-with-strong-password'
```

```bash
export LOCAL_ANALYTICS_AUTH_ENABLED=true
export LOCAL_ANALYTICS_AUTH_USERNAME='admin'
export LOCAL_ANALYTICS_AUTH_PASSWORD_HASH='pbkdf2_sha256$...'
export LOCAL_ANALYTICS_AUTH_SESSION_SECRET="$(openssl rand -hex 32)"
export LOCAL_ANALYTICS_AUTH_COOKIE_SECURE=true
```

`LOCAL_ANALYTICS_AUTH_PASSWORD` 仅用于临时本地调试；公网入口应使用 `LOCAL_ANALYTICS_AUTH_PASSWORD_HASH`。登录成功后平台写入签名 HttpOnly cookie，默认有效期 12 小时，可用 `LOCAL_ANALYTICS_AUTH_SESSION_TTL_SECONDS` 调整。

归档媒体 API 无条件要求上述登录已启用且配置完整；全局登录关闭时它们返回
503。服务端还需只读配置 `NAS_MINIO_ENDPOINT`、
`NAS_MINIO_ANALYTICS_ACCESS_KEY`、`NAS_MINIO_ANALYTICS_SECRET_KEY` 和
`NAS_MINIO_CA_FILE`。浏览器不会获得 MinIO 凭据，禁止把私有归档发布到公网。

Cloudflare 公网入口建议使用独立 hostname，例如 `analytics.aivison.it.com`，Tunnel 回源本地主服务器 `http://127.0.0.1:8098`。Public hostname 发布前必须先创建 Cloudflare Access self-hosted app，限制管理员邮箱/身份组并启用 MFA；不要把 `8098` 或 shadow 数据库端口直接暴露到公网。

## Prompt Mart

首次使用或 shadow 数据同步后刷新提示词分析缓存：

```bash
docker exec allbot-local-analytics-platform \
  python -m app.refresh_prompt_mart --full --statement-timeout-ms 3600000
```

当前 Prompt Mart 使用 `v4-task-type-prefix-strip` 归一化：Unicode NFKC、英文 casefold、清理零宽/控制字符、压缩空白，剥离 prompt 开头连续的任意 `[...]` 方括号元信息，去掉常见中英文标点两侧空格，并合并重复标点。`prompt_hash` 使用 `task_type + 归一化 prompt` 生成，同一文本只在同任务类型内去重。版本写入 `analytics_prompt_mart_state.normalization_version`；代码版本和 Mart 版本不一致时 `/api/prompts` 会返回 503，必须执行一次全量刷新，避免新旧 hash 混用。

日常增量刷新可省略 `--full`，默认会重读最近 7 天以捕捉收藏/公开等可变字段；若归一化版本变化，增量刷新会拒绝执行并提示先全量刷新。Mart 表包括：

- `analytics_prompt_occurrence`：按 `history_id` 保存已归一化 prompt 使用记录，同时保留 `raw_prompt` 原文和 `history.rating` 生成结果反馈。
- `analytics_prompt_dim`：按 `task_type + prompt` 粒度的 `prompt_hash` 保存去重 prompt，后续向量化只需要处理这一层。
- `analytics_prompt_group_stats`：全量 scope 聚合，包含 `variant_count`，提示词洞察的统计周期选择“所有”时优先读取这里。
- `analytics_prompt_rollup_stats`：7/30/90/180/240/360 天周期聚合，包含 `variant_count`，默认页面刷新优先读取这里。

`GET /api/prompts/{prompt_hash}/variants` 可按当前提示词页的 `days`、`task_type` 和 `template_scope` 懒加载同一任务类型归一化组下的原文写法，用于核对哪些 prompt 被 v4 规则合并。

## Prompt Slim Candidates

优秀提示词沉淀使用独立宽表，不挂到 Prompt Mart 默认刷新里，避免拖慢提示词洞察页缓存：

```bash
docker exec allbot-local-analytics-platform \
  python -m app.refresh_prompt_slim_table --statement-timeout-ms 3600000
```

`analytics_prompt_slim_candidates` 只纳入自然输入和源模板，排除内置模板与一键应用衍生记录。表粒度是同任务类型内的 `prompt_hash`，保留归一化 prompt、代表原文、变体数、使用次数/用户数组、任务类型/来源分布、生成后 `history.rating` 点赞点踩、Gallery 点赞点踩/评论/应用、提示词解锁和相关用户数组。`quality_stage` 支持 `auto_rejected`、`candidate`、`manual_keep`、`manual_reject`、`excellent`、`archived`；刷新只自动更新 `auto_rejected/candidate`，不覆盖人工阶段。

本地页面新增“提示词瘦身”Tab，直接读取 `GET /api/prompt-slim`。该接口只查瘦身宽表，支持按阶段、任务类型、来源、低质原因、关键词、最少用户/次数和排序筛选，并返回阶段/原因/任务/来源/字数分布、分页宽表行和详情所需的用户 ID 样本。

当前规则版本为 `slim-v3-task-type-prefix-strip`：剥离开头方括号元信息后少于 20 字的 prompt 以 `too_short` 自动剔除；短且一次性且无正信号、纯符号数字和明显测试/空值 prompt 也会写入 `low_quality_reasons`。

## Prompt Vector Embeddings

提示词向量化只维护 embedding 覆盖和续跑状态，不再生成相似边、审核簇、近似族、语义场景或语义图谱。它不修改 `analytics_prompt_slim_candidates`，只处理 `quality_stage='candidate'` 的提示词，并写入基础向量表：

- `analytics_prompt_embeddings`
- `analytics_prompt_vector_state`

启动 LM Studio Server 并加载本地 embedding 模型：

```bash
lms server start
lms load text-embedding-qwen3-embedding-8b --identifier qwen3-embedding-8b --gpu max -y
```

先跑小批量 pilot：

```bash
docker exec allbot-local-analytics-platform \
  python -m app.refresh_prompt_vectors --limit 1000 --batch-size 8 --statement-timeout-ms 3600000
```

确认 `/api/prompt-vectors` 和“提示词向量化”Tab 正常后，可去掉 `--limit` 全量断点写入向量。`--embed-only` 仍保留为兼容参数，但现在是 no-op；`--similarity-only` 与 `--cluster-only` 已禁用。刷新命令会把 L2 normalized float16 向量写入 `analytics_prompt_embeddings`，并把模型、维度、覆盖和刷新状态写入 `analytics_prompt_vector_state`。

API：

- `GET /api/prompt-vectors`：返回 `ready`、`model`、`summary`、`distributions.task_type`、`distributions.status` 和 `resume`。
- `POST /api/prompt-vectors/resume`：后台启动 `python -m app.refresh_prompt_vectors --embed-only` 续跑缺失 embedding；如果 `.refresh_prompt_vectors.lock` 已被占用，则只返回运行中状态，不启动第二条向量化。

## Retired Prompt Derivatives

“近似代表”“近似图”“语义场景”“语义图谱”四个 Tab、API 和刷新入口已下线。历史派生表不会在启动或测试中自动删除；如需清理本地 shadow 中的旧表，先 dry-run：

```bash
python scripts/cleanup_local_analytics_prompt_derivatives.py
```

确认后显式执行：

```bash
python scripts/cleanup_local_analytics_prompt_derivatives.py --execute
```

清理脚本只处理旧派生表，不删除 Prompt Mart、`analytics_prompt_slim_candidates`、`analytics_prompt_embeddings`、`analytics_prompt_vector_state` 或 `analytics_user_profile_daily_snapshots`。
