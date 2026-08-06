from scripts.backfill_visible_hotset_missing_r2_objects import build_argument_parser


def test_legacy_user_data_bucket_is_not_a_default_backfill_source():
    args = build_argument_parser().parse_args([])

    assert args.source_r2_buckets == "user-data-prod"
