# Local Analytics Platform

独立的本地数据分析平台。它不复用、不修改现有 Dashboard 代码，只读连接本地 shadow PostgreSQL，并把本地分析页面暴露在单独端口。

## Scope

- 用户画像、灵石收支、充值情况、生成分析、提示词洞察、提示词瘦身、向量相似、语义场景、模板候选和媒体引用核验；用户画像每日趋势包含新增用户、新增入宗门、新增生成用户、活跃用户和签到；`/api/overview` 仅保留给侧栏状态和旧链接兼容。
- 页面顶部只保留一个统计周期，下拉值按当前 Tab 独立保存；切换周期或点击刷新只请求当前 Tab 对应接口，避免一次刷新扫描所有分析模块。
- 提示词洞察页通过 Prompt Mart 读取预清洗数据，不再在页面刷新时现场扫描 `history.prompt`；支持分页搜索、任务类型、来源范围、最少用户/次数和排序筛选，并可在详情面板懒加载同组原文变体；默认排除一键应用生成的衍生记录和 `prompts.ini` 内置默认模板，同时保留原始 Gallery 模板的点赞、应用、评论和解锁信号；内置模板可通过 `builtin_template` 来源范围单独查看。
- 数据库连接必须通过 `LOCAL_ANALYTICS_DATABASE_URL` 显式传入。
- API 查询使用只读事务，不回写 shadow 业务库。
- 媒体预览 URL 可通过 `LOCAL_ANALYTICS_MEDIA_PUBLIC_BASE_URL` 配置；未配置时只展示对象 key。
- 内置模板识别默认读取仓库根目录 `prompts.ini`；Compose 会把该文件只读挂载到容器 `/app/prompts.ini`，也可用 `LOCAL_ANALYTICS_PROMPTS_INI` 指向其它 INI。

## Run

```bash
LOCAL_ANALYTICS_DATABASE_URL="postgresql://user:password@127.0.0.1:5434/bot_db_prod_shadow" \
docker-compose -f local_analytics_platform/docker-compose.yml up -d --build
```

默认监听 `8095`。如果需要改端口，设置 `LOCAL_ANALYTICS_PORT`。

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

## Prompt Vector Similarity

提示词语义相似审核使用独立持久化表，不修改 `analytics_prompt_slim_candidates`。第一版只处理 `quality_stage='candidate'` 的提示词，并且只在同一 `task_type` 内生成近邻边和审核簇。

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

确认 `/api/prompt-vectors` 和“向量相似”Tab 正常后，可用 `--embed-only` 去掉 `--limit` 全量断点写入向量；全量向量完成后，建议用 `--similarity-only --task-type <任务类型>` 按任务类型分片生成相似边和簇。刷新命令会把 L2 normalized float16 向量写入 `analytics_prompt_embeddings`，把同任务类型 top-k 近邻写入 `analytics_prompt_similarity_edges`，再按 `similarity >= 0.92` 的 duplicate 边聚成 `analytics_prompt_similarity_clusters` / `analytics_prompt_similarity_members`。`similarity >= 0.86` 的边只作为相似邻居保留。USEARCH 索引文件写入容器 `/app/data/prompt_vectors`，Compose 挂载到 `local_analytics_platform/data/`；索引丢失时可从 PostgreSQL 中的向量重建，不需要重新跑 embedding。

新增 API：

- `GET /api/prompt-vectors`：返回模型状态、向量覆盖率、相似边/簇统计、任务/规模/边类型分布和分页簇列表。
- `GET /api/prompt-vectors/clusters/{cluster_id}`：返回代表 prompt 与簇成员的相似度、使用/用户/反馈信号。
- `POST /api/prompt-vectors/resume`：后台启动 `python -m app.refresh_prompt_vectors --embed-only` 续跑缺失 embedding；如果 `.refresh_prompt_vectors.lock` 已被占用，则只返回运行中状态，不启动第二条向量化。

## Prompt Semantic Scenes

语义场景用于把已向量化的候选 prompt 按 `task_type` 提炼成约 1000 个可运营审核场景，独立于相似边/近重复族，不依赖 top-k 相似边：

```bash
docker exec allbot-local-analytics-platform \
  python -m app.refresh_prompt_scenes --statement-timeout-ms 3600000
```

刷新只读取 `analytics_prompt_embeddings` + `analytics_prompt_slim_candidates` 中 `quality_stage='candidate'` 且 `status='embedded'` 的数据。目标场景数按任务类型候选量的平方根分配，单类型默认最多 220 个；每个场景保留 Top 30 高价值候选 prompt，`manual_label` 预留给人工命名，稳定 `scene_id` 的人工标签会在刷新中保留。

新增 API：

- `GET /api/prompt-scenes`：返回场景 summary、任务/规模/置信度分布和分页场景列表，支持任务类型、关键词、最小成员数、置信度和排序筛选。
- `GET /api/prompt-scenes/{scene_id}`：只返回该场景的 Top 候选 prompt，不拉取全部成员。
