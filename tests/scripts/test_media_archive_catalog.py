from scripts.media_archive_catalog import CATALOG_DDL, CONFIRM_MISSING_SQL, SEED_SQL


def test_missing_confirmation_requires_two_rounds_and_24_hours():
    assert "missing_rounds + 1 >= 2" in CONFIRM_MISSING_SQL
    assert "first_missing_at <= now() - interval '24 hours'" in CONFIRM_MISSING_SQL
    assert "bool_and(x.status = 'not_found')" in CONFIRM_MISSING_SQL


def test_source_retirement_requires_evidence_and_offline_is_distinct():
    assert "retirement_evidence" in CATALOG_DDL
    assert "source_offline" in CATALOG_DDL
    assert (
        "retired_at is null or nullif(btrim(retirement_evidence), '') is not null"
        in CATALOG_DDL
    )


def test_seed_ranks_raw_history_before_visibility_filter():
    assert "row_number() over(partition by h.user_id order by h.id desc)" in SEED_SQL
    assert "r.rn <= 8 and h.is_visible is true" in SEED_SQL
