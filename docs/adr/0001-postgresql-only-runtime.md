# ADR 0001: PostgreSQL-Only Runtime Database

日期：2026-07-06

## Status

Accepted

## Context

AllBot 当前正式生产运行在云控制面 + 托管 PostgreSQL / Valkey / R2 的架构上，云测试控制面也使用 PostgreSQL 容器。业务账本、订单、会员、Gallery、任务历史、运行态 checkpoint 与本地 shadow 分析都围绕 PostgreSQL 工具链、SQL 语义和运维 SOP 展开。

代码和迁移中已经存在 PostgreSQL 语义，例如 JSON server default 的 `::json`、partial index 的 `postgresql_where`、序列校准 `setval(pg_get_serial_sequence(...))` 和 Alembic baseline 中的 PostgreSQL timestamp 类型。把这些路径改成跨数据库兼容会扩大迁移面，并削弱当前生产/测试/分析环境的一致性。

## Decision

AllBot 后端运行时数据库明确以 PostgreSQL 为唯一支持方言。`src/database`、Alembic migration、seed/sync SQL 和本地 shadow 同步脚本可以使用 PostgreSQL 专有能力。

后端重构仍应避免不必要的 raw SQL；能用 SQLAlchemy 表达式表达的查询优先用 SQLAlchemy 表达式。但 PostgreSQL-only DDL、JSON default、partial index、sequence maintenance 和运维脚本不再作为跨数据库兼容缺陷处理。

## Alternatives Considered

- 继续追求 PostgreSQL / MySQL / SQLite 可移植性：需要重写现有 schema default、partial index、baseline migration、seed SQL 与 shadow 同步脚本，收益与当前部署事实不匹配。
- 仅在新代码中避免 PostgreSQL 专有语义：会造成新旧 schema 口径混杂，仍无法承诺真实跨数据库运行。

## Consequences

- 正向影响：数据库层事实源与生产、云测试、本地 shadow 分析一致；后端审查不再反复把既有 PostgreSQL DDL 误判为待修兼容问题。
- 代价和风险：未来若要支持其他数据库，需要单独立项迁移 schema、migrations、seed SQL、测试数据库和运维脚本。
- 同步更新：系统架构报告、知识库矩阵与后端整改回归记录需引用本 ADR；本轮不新增 Alembic migration。

## References

- `docs/system_architecture_report.md`
- `src/database/core.py`
- `src/database/models.py`
- `migrations/versions/`
