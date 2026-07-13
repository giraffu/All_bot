---
name: allbot-local-analytics-prompt-semantics
description: "处理本地数据分析平台的提示词词义分析、词元治理、指定词元、同义映射、删除表、自由P图提示词拆解、tokens-only 重建前后校验和模板候选槽位口径。用户要求审查/合并/删除/分类提示词词元、处理高频未覆盖词元、年龄人群发现标签、自由P图拆解筛选或提示词模板候选语义槽位时必须使用。"
---

# Local Analytics Prompt Semantics

## When To Use

Use this skill for local analytics prompt semantics work:

- 审查或治理提示词词元、词元分类、指定词元、词元映射表、词元删除表。
- 判断词元是否过宽、无标签价值、误分类、可合并、应拆解或应保留为独立标签。
- 处理高频未覆盖词元、长词元拆解、繁简/多语言归一、人群年龄发现标签。
- 设计或校准“自由P图拆解”页的一级/二级筛选组、提示词分解展示和优秀模板沉淀口径。
- 评估 tokens-only 重建前后状态，或解释低频阈值、raw token cache、物化统计的关系。
- 调整模板候选的词元槽位口径。

This skill is local analytics only. It must not change original prompts, production prompt behavior, or cloud production services.

## Required Reference

Before doing non-trivial rule decisions, read:

- `docs/子模块_本地数据分析平台提示词词义分析_prompt_semantics.md`

Use `docs/子模块_本地数据分析平台_local_analytics_platform.md` only when you also need API/table/frontend implementation details.

## Workflow

1. Snapshot first.
   - Export the visible token scope being reviewed, usually global `min_prompt_count=20`.
   - Include prompt samples when deciding whether a token is meaningful.
   - For write work, back up `analytics_prompt_token_custom_terms`, `analytics_prompt_token_alias_rules`, `analytics_prompt_token_deleted_rules`, and relevant state rows.

2. Classify each candidate into exactly one action.
   - `delete`: broad/noisy/technical/process/fragments with no label value.
   - `alias`: same concept, spelling variant, traditional/simplified, multilingual, or stable euphemism.
   - `custom_term`: real meaningful term that should be extracted.
   - `split_or_rescue`: long or broken token should produce smaller meaningful labels.
   - `move_category`: useful token in the wrong category.
   - `keep`: current rule is correct.
   - `review_needed`: low confidence or context-dependent.

3. Keep semantic boundaries strict.
   - Base body-part labels and attribute labels stay separate.
   - Broad category words do not become tags merely because they are frequent.
   - Concrete age/person-risk tokens stay discoverable for audit; do not hide them just to reduce noise.
   - New rules must come from current stats or real prompt samples. Do not invent terms.

4. Apply only high-confidence mutations.
   - User-facing reports come before broad DB writes unless the user explicitly approved a prepared report.
   - Use transactions for rule-table writes.
   - Mark rules pending rebuild by updating the vector state when materialization is stale.

5. Validate after writes.
   - No active alias may belong to multiple representatives.
   - No active representative may appear as another active representative's alias.
   - No active custom/alias rule may remain unclassified.
   - Deleted terms should not appear in visible token APIs after rebuild.

6. Rebuild only when requested or necessary.
   - Rule edits do not affect visible token stats until tokens-only rebuild materializes them.
   - Do not run template candidate refresh unless requested or the task explicitly includes template-candidate verification.

## Core Categories

Use these as the stable prompt semantic slots:

- `保持口径`
- `人物主体`
- `身体部分`
- `动作姿势`
- `成人主题`
- `服饰配件`
- `场景`
- `镜头构图`
- `风格质量`
- `表情情绪`
- `外观特征`

For `自由P图拆解`, prefer the same semantic slots but present them as browsing facets:

- 一级分组：`保持口径`、`场景`、`物品`、`表情`、`成人主题`、`动作姿势`、`画面风格构图`、`身体细节`、`外观特征`、`服饰配件`、`人物主体`
- 二级分组：来自指定词元/映射表的 `category + subcategory`
- 数据范围：优先固定在 `edit`（自由P图）scope，并只展示 `prompt_count >= 20` 的已分类标签

Avoid reintroducing retired buckets such as `观测高频词`, `技术参数`, and broad `生成编辑` as active semantic categories.

## Validation Commands

Typical local rebuild command when the user asks to materialize token rules:

```bash
docker exec allbot-local-analytics-platform python -m app.refresh_prompt_vectors --tokens-only --statement-timeout-ms 3600000
```

Typical tests when code changes are involved:

```bash
pytest tests/local_analytics/test_prompt_vectors_refresh.py tests/local_analytics/test_prompt_vector_api.py tests/local_analytics/test_prompt_template_candidates.py -q
```

If the task changes docs or skills, also use `allbot-kb-auto-updater` and update the knowledge-base matrix.
