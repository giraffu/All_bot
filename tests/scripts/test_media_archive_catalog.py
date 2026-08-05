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


def test_seed_exact_id_manifest_preserves_hot_ranking_contract(tmp_path):
    from scripts.media_archive_catalog import SEED_IDS_SQL, load_history_ids

    manifest = tmp_path / "ids.txt"
    manifest.write_text("10\n2\n10\n")
    assert load_history_ids(str(manifest)) == (2, 10)
    assert "id = any($3::int[])" in SEED_IDS_SQL
    assert "row_number() over(partition by h.user_id order by h.id desc)" in SEED_IDS_SQL
