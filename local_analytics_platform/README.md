# Local Analytics Platform

独立的本地数据分析平台。它不复用、不修改现有 Dashboard 代码，只读连接本地 shadow PostgreSQL，并把本地分析页面暴露在单独端口。

## Scope

- 经营概览、充值分析、生成分析、提示词洞察、模板候选和媒体引用核验。
- 数据库连接必须通过 `LOCAL_ANALYTICS_DATABASE_URL` 显式传入。
- API 查询使用只读事务，不回写 shadow 业务库。
- 媒体预览 URL 可通过 `LOCAL_ANALYTICS_MEDIA_PUBLIC_BASE_URL` 配置；未配置时只展示对象 key。

## Run

```bash
LOCAL_ANALYTICS_DATABASE_URL="postgresql://user:password@127.0.0.1:5434/bot_db_prod_shadow" \
docker-compose -f local_analytics_platform/docker-compose.yml up -d --build
```

默认监听 `8095`。如果需要改端口，设置 `LOCAL_ANALYTICS_PORT`。
