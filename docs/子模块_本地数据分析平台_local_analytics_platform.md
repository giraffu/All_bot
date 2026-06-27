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

- 用户画像: 用户增长、生成活跃、签到趋势、身份/修为/灵石/生成/活跃分布和用户排行。
- 灵石收支: 基于 `user_logs`、`users`、`orders` 只读聚合灵石收入、支出、净变化、来源组成、消耗去向、健康指标和可疑用户复核线索；风险判断只用于人工复核，不修改用户资产。
- 充值情况: 参考管理后台充值口径，只读聚合成功/处理中/失败订单、RMB / TON / Stars、USDT 估算、套餐发放灵石、分时充值、渠道/套餐/付费分层、受邀充值、Top 付费用户、最近订单和充值健康指标；真实收入仅统计 `RMB`、`TON`、`XTR` 成功订单，`manual_` / `GIFT:` 等内部赠送单单独展示。
- 生成分析: 合并原经营概览里的生成总览，按趋势、质量漏斗、来源组成、任务类型、灵石消耗效率、Worker 成功/失败和耗时、用户排行、近期高信号作品综合分析生成健康度。
- 经营概览: 不再作为可见 Tab；`/api/overview` 仅保留给侧栏 shadow 状态、数据源展示和旧 `#overview` 链接兼容。
- 时间周期: 顶栏只保留一个“统计周期”选择器，但该值按当前 Tab 独立保存。切换周期或点击刷新只加载当前 Tab 对应 API，不再全量请求用户画像、收支、充值、生成、提示词和媒体核验；提示词洞察不再有独立的 `Prompt 周期` 控件。
- 提示词洞察: 默认读取本地 Prompt Mart，不在页面刷新时现场扫描 `history.prompt`。Mart 先把 `history.prompt` 做 `v4-task-type-prefix-strip` 归一化和 hash 去重：Unicode NFKC、英文 casefold、清理零宽/控制字符、压缩空白，剥离 prompt 开头连续的任意 `[...]` 方括号元信息，去掉常见中英文标点两侧空格，并合并重复标点；SQL 与 Python `_normalize_prompt_text()` 保持同一规则。`prompt_hash` 使用 `task_type + 归一化 prompt` 生成，因此同一文本只在同任务类型内去重。Mart 写入 `analytics_prompt_occurrence`、`analytics_prompt_dim`、`analytics_prompt_group_stats` 与 `analytics_prompt_rollup_stats`，其中 occurrence 保留 `raw_prompt` 原文和 `history.rating` 生成结果反馈，group/rollup 记录 `variant_count`；页面常用的 7/30/90/180/240/360 天周期优先读取 rollup，提示词洞察的统计周期选择“所有”时优先读取 `analytics_prompt_group_stats` 全量聚合。默认排除 `allow_contribute=false` 的一键应用衍生记录和 `prompts.ini` 内置默认模板，展示提示词总览、字数/任务类型/复用分层、分页搜索、相同提示词使用次数、使用用户数、收藏、点赞、点踩、评论、应用、Prompt 解锁和 Gallery 投稿等价值信号；筛选支持搜索、任务类型、来源范围、最少用户/次数和排序，不提供内置类别或候选标签。详情面板可通过 `/api/prompts/{prompt_hash}/variants` 按当前 `days`、`task_type` 和 `template_scope` 懒加载同组原文变体，用于核对哪些 prompt 被归一化合并。原始 Gallery 模板仍作为可分析来源保留互动数据，内置模板可通过 `builtin_template` 来源范围单独查看。
- 提示词瘦身: 优秀提示词沉淀使用独立持久化宽表 `analytics_prompt_slim_candidates`，刷新命令为 `docker exec allbot-local-analytics-platform python -m app.refresh_prompt_slim_table --statement-timeout-ms 3600000`。该表只纳入自然输入和源模板，排除内置模板与一键应用衍生记录，以同任务类型内的 `prompt_hash` 为粒度保留归一化 prompt、代表原文、变体数、字数、使用次数/用户数组、任务类型/来源分布、生成后 `history.rating` 点赞点踩、Gallery 点赞点踩/评论/应用、提示词解锁及相关用户数组。当前 `slim-v3-task-type-prefix-strip` 规则会把剥离开头方括号元信息后少于 20 字的 prompt 以 `too_short` 自动剔除；短且一次性且无正信号、纯符号数字和明显测试/空值 prompt 也会写入 `low_quality_reasons`；刷新只自动更新 `auto_rejected/candidate`，不覆盖 `manual_keep`、`manual_reject`、`excellent`、`archived` 等人工阶段。前端“提示词瘦身”Tab 通过 `GET /api/prompt-slim` 直接读取该宽表，支持阶段、任务类型、来源、规则原因、关键词、最少用户/次数和排序筛选，展示阶段/原因/任务/来源/字数分布、分页行详情和用户 ID 样本；该接口不回源联查 `history`、`gallery_posts` 或 `user_interactions`。
- 向量相似: 语义相似审核使用独立持久化表，不修改 `analytics_prompt_slim_candidates`。刷新命令为 `docker exec allbot-local-analytics-platform python -m app.refresh_prompt_vectors --limit 1000 --batch-size 8 --statement-timeout-ms 3600000`，全量向量写入建议使用 `--embed-only` 去掉 `--limit` 断点续跑；向量完成后再用 `--similarity-only --task-type <任务类型>` 按任务类型分片生成相似边和簇。命令通过 LM Studio OpenAI-compatible `/v1/embeddings` 调用 `qwen3-embedding-8b`（模型 key `text-embedding-qwen3-embedding-8b`），将 L2 normalized float16 bytes 写入 `analytics_prompt_embeddings`，按同一 `task_type` 构建 USEARCH top-k 近邻并写入 `analytics_prompt_similarity_edges`；`similarity >= 0.86` 的边保留作相似邻居展示，`similarity >= 0.92` 的 duplicate 边只作为簇候选图。簇生成不再对 duplicate 边做传递闭包；它按质量/使用量选择代表提示词，只纳入与代表点以及当前簇内已有成员两两达到 duplicate 阈值的未分配提示词，避免 A 像 B、B 像 C 时把 A/C 这类桥接内容合成一个过大的语义族。USEARCH 索引落到 `/app/data/prompt_vectors`，Compose 挂载到 `local_analytics_platform/data/`；索引丢失可从 DB 向量重建，不需要重新 embedding。前端“向量相似”Tab 通过 `GET /api/prompt-vectors` 和 `GET /api/prompt-vectors/clusters/{cluster_id}` 展示模型状态、向量覆盖率、簇分布、分页簇列表和右侧成员详情；第一版只生成审核候选，不自动合并、不自动标记优秀。
- 模板候选: 从高分 prompt 样本中展示可人工沉淀的场景候选。
- 媒体核验: 从 `history.input_file`、`history.output_file`、`history.extra_outputs` 解析输入输出对象引用。

## 4. 运维口径

- 启停只操作 `allbot-local-analytics-platform` 容器，不重建现有 Dashboard backend/frontend。
- 本地分析 Compose 会把仓库根目录 `prompts.ini` 只读挂载到容器 `/app/prompts.ini`，作为内置模板识别依据；如需对照其它模板文件，可通过 `LOCAL_ANALYTICS_PROMPTS_INI` 指向指定 INI。
- Shadow 数据同步会默认保留旧 `bot_db_prod_shadow` 中的 `analytics_prompt_*` 本地分析表，避免每日 05:00 云端 dump 恢复覆盖 Prompt Mart、提示词瘦身和向量相似数据；对应开关为 `.env.cloud-prod-shadow-sync.local` 的 `LOCAL_ANALYTICS_PRESERVE_ON_SHADOW_SYNC=true`。
- Shadow 同步后的自动链路入口为 `scripts/run_local_analytics_shadow_pipeline.py`，默认 dry-run；真实执行使用 `--execute`。一次性恢复旧分析表可执行 `python scripts/run_local_analytics_shadow_pipeline.py --execute --restore-from-db bot_db_prod_shadow_previous_20260627_050741 --batch-size 128`。该脚本会先等待 cloud-prod shadow sync 锁释放，再检测 `/app/data/prompt_vectors/.refresh_prompt_vectors.lock` 对应的宿主锁；若上一轮向量刷新仍在运行，整轮输出 `skipped_vector_lock_held` 并退出，不再刷新 Mart/slim 或启动第二条 embedding 流。无向量锁时固定顺序为：按需复制 `analytics_prompt_*` -> 增量 `refresh_prompt_mart` -> `refresh_prompt_slim_table` -> LM Studio 可用时 `refresh_prompt_vectors --embed-only` 续跑缺失向量 -> 向量覆盖后按 `task_type` 生成相似边和簇。增量 Mart 先用 `last_history_id` 和近 N 天 history 找出受影响 `prompt_hash`，只删除/重算这些 prompt 的 dim/group/rollup 行，保留其他旧统计；只有需要人工重建整个 Mart 时才追加 `--full-mart`。
- systemd 自动刷新为 `allbot-local-analytics-refresh.timer`，默认每日 Asia/Shanghai 05:45；脚本用 `.local-analytics-refresh.lock` 防止同一 pipeline 并发，并用 `.refresh_prompt_vectors.lock` 防止已有长向量刷新期间重复启动分析链路。05:00 shadow 切库导致 asyncpg 连接断开时，向量刷新会重连并按缺失 embedding 断点续跑。
- 向量相似刷新前应确认 LM Studio Server 已启动并加载模型：`lms server start`，然后 `lms load text-embedding-qwen3-embedding-8b --identifier qwen3-embedding-8b --gpu max -y`。若自动链路发现 LM Studio 不可用，会保留 Mart/瘦身刷新结果并跳过 embedding，不让本地分析平台整体失败。
- 本地主服务器旧版 `docker-compose 1.29.2` recreate 可能触发 `ContainerConfig` 兼容问题；恢复时只删除 `local-analytics-platform` service 对应容器后再 `up -d --no-deps`。
- 该平台当前面向本地/LAN 分析使用；如需公网访问，必须先加 Cloudflare Access 或等价身份层保护。

## 5. 验证要求

- `GET /api/health` 返回 `bot_db_prod_shadow`。
- `GET /api/user-analytics`、`/api/credit-flow-analytics`、`/api/overview`、`/api/finance`、`/api/generation`、`/api/prompts`、`/api/prompt-slim`、`/api/prompt-vectors`、`/api/media-audit` 均能返回基础数据；`/api/prompts` 应至少包含 `summary/distributions/prompt_groups/pagination/mart/candidates`，不返回内置 `tag_summary` 或 `distributions.category`，`prompt_groups[]` 应包含 `variant_count`，其中 `mart.rollup_stats_count` 应大于 0；`GET /api/prompts/{prompt_hash}/variants` 应能返回同组 `raw_prompt` 变体。`/api/prompt-slim` 应至少包含 `summary/distributions/rows/pagination`，且 SQL 不需要 join 原始业务表。`/api/prompt-vectors` 在表未构建时应返回稳定空状态，构建后应包含 `summary/distributions/clusters/pagination/model`；`/api/prompt-vectors/clusters/{cluster_id}` 应返回代表 prompt 和成员列表。
- `analytics_prompt_slim_candidates` 刷新后应有 `candidate/auto_rejected` 分布，且 `quality_stage='candidate' order by quality_score desc limit 100` 不需要 join 原始业务表。
- Playwright 桌面与窄屏检查应确认 `body[data-loaded="true"]`、无前端 console error、无整页水平溢出。
- 现有 Dashboard 后端路由表不得出现 `/api/local-analytics`。

## 6. Changelog

- 2026-06-26: 新增提示词候选向量化与“向量相似”审核 Tab；新增 `analytics_prompt_embeddings`、`analytics_prompt_similarity_edges`、`analytics_prompt_similarity_clusters`、`analytics_prompt_similarity_members` 和 `analytics_prompt_vector_state`，使用 LM Studio `text-embedding-qwen3-embedding-8b` + USEARCH 同任务类型内聚类，仅生成审核候选。
- 2026-06-27: cloud-prod shadow sync 默认保留 `analytics_prompt_*` 本地分析表；新增 `scripts/run_local_analytics_shadow_pipeline.py` 与 `allbot-local-analytics-refresh.timer`，形成每日 05:45 的 Mart 增量刷新、瘦身与向量断点续跑链路。
