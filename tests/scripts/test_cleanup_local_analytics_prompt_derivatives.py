from scripts import cleanup_local_analytics_prompt_derivatives as cleanup


def test_cleanup_targets_only_removed_prompt_derivative_tables():
    sql = cleanup.build_drop_sql()

    for table_name in cleanup.DERIVED_PROMPT_TABLES:
        assert table_name in sql

    for table_name in cleanup.PRESERVED_LOCAL_ANALYTICS_TABLES:
        assert table_name not in cleanup.DERIVED_PROMPT_TABLES
        assert table_name not in sql


def test_normalize_database_url_accepts_common_postgres_schemes():
    assert cleanup.normalize_database_url("postgres://u:p@host/db") == "postgresql://u:p@host/db"
    assert cleanup.normalize_database_url("postgresql+asyncpg://u:p@host/db") == "postgresql://u:p@host/db"
