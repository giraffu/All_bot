import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


def test_prompt_normalization_strips_leading_model_metadata():
    assert analytics_main._normalize_prompt_text("[模型:cum] 细腻真实的人像摄影") == "细腻真实的人像摄影"
    assert analytics_main._normalize_prompt_text("[512p|5s] [模型:qwen/flat_chest_hairless.safetensors] A soft light portrait") == "a soft light portrait"
    assert analytics_main._normalize_prompt_text("[任意元信息] [foo/bar] 正文内容") == "正文内容"
    assert analytics_main._normalize_prompt_text("保留中间的 [模型:cum] 标记") == "保留中间的[模型:cum]标记"


@pytest.mark.asyncio
async def test_prompts_returns_grouped_library_without_builtin_tags(monkeypatch, tmp_path):
    prompts_file = tmp_path / "prompts.ini"
    prompts_file.write_text("[prompts]\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_ANALYTICS_PROMPTS_INI", str(prompts_file))
    cache_clear = getattr(getattr(analytics_main, "_builtin_prompt_templates", None), "cache_clear", None)
    if cache_clear:
        cache_clear()

    calls = []
    expected_common_args = (
        30,
        "edit",
        "natural",
        "%cinematic%",
        2,
        3,
    )

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        if "to_regclass('public.analytics_prompt_group_stats')" in query:
            assert args == ()
            return {"ready": True}
        if "occurrence_count" in query and "analytics_prompt_mart_state" in query:
            assert args == ()
            return {
                "prompt_count": 45,
                "occurrence_count": 120,
                "group_stats_count": 90,
                "rollup_stats_count": 180,
                "stats_updated_at": "2026-06-26T03:00:00",
                "last_history_id": "300",
                "last_refresh_mode": "full",
                "normalization_version": analytics_main.PROMPT_NORMALIZATION_VERSION,
            }
        assert "prompt_summary" in query
        assert "analytics_prompt_occurrence" in query
        assert "from history h" not in query.lower()
        assert args == expected_common_args
        return {
            "prompt_records": 120,
            "distinct_prompts": 45,
            "repeated_prompts": 18,
            "multi_user_prompts": 9,
            "avg_chars": 88.5,
            "median_chars": 76,
            "derived_records_excluded": 30,
            "builtin_template_records_excluded": 0,
            "high_value_prompts": 6,
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "prompt_groups_page" in query:
            assert "analytics_prompt_occurrence" in query
            assert "from history h" not in query.lower()
            assert args == (*expected_common_args, "value_score", 20, 20)
            return [
                {
                    "prompt_hash": "abc123",
                    "prompt": "cinematic close-up portrait, soft camera movement",
                    "char_count": 47,
                    "uses": 12,
                    "users": 5,
                    "variant_count": 2,
                    "task_types": ["edit", "txt2img"],
                    "first_seen": "2026-06-01T00:00:00",
                    "last_seen": "2026-06-25T12:00:00",
                    "favorite_records": 3,
                    "public_records": 2,
                    "gallery_posts": 1,
                    "likes": 20,
                    "dislikes": 1,
                    "comments": 4,
                    "applies": 9,
                    "prompt_unlocks": 2,
                    "derived_uses": 0,
                    "builtin_template_uses": 0,
                    "builtin_template_keys": [],
                    "source_template_posts": 1,
                    "value_score": 140,
                }
            ]
        if "prompt_length_distribution" in query:
            assert args == expected_common_args
            return [{"label": "41-80 字", "count": 20}]
        if "prompt_task_type_distribution" in query:
            return [{"label": "edit", "count": 50}]
        if "prompt_reuse_distribution" in query:
            return [{"label": "多人复用", "count": 9}]
        if "prompt_template_scope_distribution" in query:
            return [{"label": "自然输入", "count": 90}]
        if "prompt_candidates_legacy" in query:
            assert "analytics_prompt_occurrence" in query
            assert "from history h" not in query.lower()
            assert args == (30, 20, 20000, "edit", "natural")
            return [
                {
                    "id": 1,
                    "task_id": "task_1",
                    "user_id": 101,
                    "task_type": "edit",
                    "prompt": "cinematic close-up portrait",
                    "input_file": None,
                    "output_file": None,
                    "extra_outputs": {},
                    "created_at": "2026-06-25T12:00:00",
                    "source": "web",
                    "is_favorited": True,
                    "width": 768,
                    "height": 1024,
                    "duration": None,
                    "post_id": 10,
                    "likes": 20,
                    "applies": 9,
                    "comments": 4,
                    "prompt_unlocks": 2,
                    "prompt_score": 99,
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/prompts?days=30&limit=20&page=2&task_type=edit"
            "&template_scope=natural&q=cinematic&min_users=2&min_uses=3&sort=value_score"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 30
    assert payload["limit"] == 20
    assert payload["page"] == 2
    assert payload["template_scope"] == "natural"
    assert payload["summary"]["distinct_prompts"] == 45
    assert payload["mart"]["occurrence_count"] == 120
    assert payload["distributions"]["length"][0] == {"label": "41-80 字", "count": 20}
    assert "category" not in payload
    assert "category" not in payload["distributions"]
    assert "tag_summary" not in payload
    assert payload["prompt_groups"][0]["prompt_hash"] == "abc123"
    assert payload["prompt_groups"][0]["variant_count"] == 2
    assert payload["prompt_groups"][0]["prompt_preview"] == "cinematic close-up portrait, soft camera movement"
    assert "tags" not in payload["prompt_groups"][0]
    assert "category" not in payload["prompt_groups"][0]
    assert payload["pagination"] == {"page": 2, "limit": 20, "total_groups": 45, "has_next": True}
    assert payload["candidates"][0]["prompt_score"] == 99
    assert any(call[0] == "fetch" and call[2][-3:] == ("value_score", 20, 20) for call in calls)


@pytest.mark.asyncio
async def test_prompts_identifies_builtin_prompt_templates(monkeypatch, tmp_path):
    prompt_text = "头身互换：以图片1为基准图像，保留其光照、环境及背景。"
    prompts_file = tmp_path / "prompts.ini"
    prompts_file.write_text(f"[prompts]\nface_swap = {prompt_text}\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_ANALYTICS_PROMPTS_INI", str(prompts_file))
    cache_clear = getattr(getattr(analytics_main, "_builtin_prompt_templates", None), "cache_clear", None)
    if cache_clear:
        cache_clear()

    calls = []
    expected_common_args = (
        30,
        None,
        "builtin_template",
        "%头身%",
        1,
        1,
    )

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        if "to_regclass('public.analytics_prompt_group_stats')" in query:
            assert args == ()
            return {"ready": True}
        if "occurrence_count" in query and "analytics_prompt_mart_state" in query:
            assert args == ()
            return {
                "prompt_count": 1,
                "occurrence_count": 70,
                "group_stats_count": 2,
                "rollup_stats_count": 4,
                "stats_updated_at": "2026-06-26T03:00:00",
                "last_history_id": "500",
                "last_refresh_mode": "full",
                "normalization_version": analytics_main.PROMPT_NORMALIZATION_VERSION,
            }
        assert "prompt_summary" in query
        assert "analytics_prompt_rollup_stats" in query
        assert "from history h" not in query.lower()
        assert args == expected_common_args
        return {
            "prompt_records": 70,
            "distinct_prompts": 1,
            "repeated_prompts": 1,
            "multi_user_prompts": 1,
            "avg_chars": 28,
            "median_chars": 28,
            "derived_records_excluded": 0,
            "builtin_template_records_excluded": 0,
            "high_value_prompts": 1,
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "prompt_groups_page" in query:
            assert "analytics_prompt_rollup_stats" in query
            assert "from history h" not in query.lower()
            assert args == (*expected_common_args, "uses", 10, 0)
            return [
                {
                    "prompt_hash": "builtin123",
                    "prompt": prompt_text,
                    "char_count": 28,
                    "uses": 70,
                    "users": 12,
                    "variant_count": 1,
                    "task_types": ["face_swap"],
                    "first_seen": "2026-06-01T00:00:00",
                    "last_seen": "2026-06-26T05:00:00",
                    "favorite_records": 0,
                    "public_records": 0,
                    "gallery_posts": 0,
                    "likes": 0,
                    "dislikes": 0,
                    "comments": 0,
                    "applies": 0,
                    "prompt_unlocks": 0,
                    "derived_uses": 0,
                    "builtin_template_uses": 70,
                    "builtin_template_keys": ["face_swap"],
                    "source_template_posts": 0,
                    "value_score": 88,
                }
            ]
        if "prompt_length_distribution" in query:
            assert args == expected_common_args
            return [{"label": "1-40 字", "count": 1}]
        if "prompt_task_type_distribution" in query:
            assert args == expected_common_args
            return [{"label": "face_swap", "count": 1}]
        if "prompt_reuse_distribution" in query:
            assert args == expected_common_args
            return [{"label": "多人复用", "count": 1}]
        if "prompt_template_scope_distribution" in query:
            assert args == expected_common_args
            return [{"label": "内置模板", "count": 1}]
        if "prompt_candidates_legacy" in query:
            assert "analytics_prompt_occurrence" in query
            assert "from history h" not in query.lower()
            assert args == (30, 10, 20000, None, "builtin_template")
            return [
                {
                    "id": 5,
                    "task_id": "task_builtin",
                    "user_id": 101,
                    "task_type": "face_swap",
                    "prompt": prompt_text,
                    "input_file": None,
                    "output_file": None,
                    "extra_outputs": {},
                    "created_at": "2026-06-26T05:00:00",
                    "source": "web",
                    "is_favorited": False,
                    "allow_contribute": True,
                    "builtin_template_key": "face_swap",
                    "width": 768,
                    "height": 1024,
                    "duration": None,
                    "post_id": None,
                    "likes": 0,
                    "applies": 0,
                    "comments": 0,
                    "prompt_unlocks": 0,
                    "prompt_score": 8,
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/prompts?days=30&limit=10&template_scope=builtin_template&q=头身&sort=uses"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["template_scope"] == "builtin_template"
    assert payload["prompt_groups"][0]["scope_label"] == "内置模板"
    assert payload["prompt_groups"][0]["builtin_template_keys"] == ["face_swap"]
    assert payload["distributions"]["template_scope"][0] == {"label": "内置模板", "count": 1}
    assert any(call[0] == "fetch" and "prompt_candidates_legacy" in call[1] for call in calls)


@pytest.mark.asyncio
async def test_prompts_zero_days_uses_alltime_group_stats(monkeypatch, tmp_path):
    prompts_file = tmp_path / "prompts.ini"
    prompts_file.write_text("[prompts]\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_ANALYTICS_PROMPTS_INI", str(prompts_file))
    cache_clear = getattr(getattr(analytics_main, "_builtin_prompt_templates", None), "cache_clear", None)
    if cache_clear:
        cache_clear()

    calls = []
    expected_common_args = (0, None, "natural", None, 1, 1)

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        if "to_regclass('public.analytics_prompt_group_stats')" in query:
            return {"ready": True}
        if "occurrence_count" in query and "analytics_prompt_mart_state" in query:
            return {
                "prompt_count": 3,
                "occurrence_count": 10,
                "group_stats_count": 3,
                "rollup_stats_count": 12,
                "stats_updated_at": "2026-06-26T03:00:00",
                "last_history_id": "10",
                "last_refresh_mode": "full",
                "normalization_version": analytics_main.PROMPT_NORMALIZATION_VERSION,
            }
        assert "prompt_summary" in query
        assert "analytics_prompt_group_stats" in query
        assert "analytics_prompt_rollup_stats" not in query
        assert "analytics_prompt_occurrence" not in query
        assert args == expected_common_args
        return {
            "prompt_records": 10,
            "distinct_prompts": 3,
            "repeated_prompts": 1,
            "multi_user_prompts": 1,
            "avg_chars": 50,
            "median_chars": 48,
            "derived_records_excluded": 2,
            "builtin_template_records_excluded": 0,
            "high_value_prompts": 1,
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "prompt_candidates_legacy" in query:
            assert "analytics_prompt_occurrence" in query
            assert args == (analytics_main.ALL_TIME_QUERY_DAYS, 5, 20000, None, "natural")
            return []
        assert "analytics_prompt_group_stats" in query
        assert "analytics_prompt_rollup_stats" not in query
        assert "analytics_prompt_occurrence" not in query
        if "prompt_groups_page" in query:
            assert args == (*expected_common_args, "value_score", 5, 0)
        else:
            assert args == expected_common_args
        return []

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/prompts?days=0&limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 0
    assert payload["summary"]["distinct_prompts"] == 3
    assert any("analytics_prompt_group_stats" in call[1] for call in calls)


@pytest.mark.asyncio
async def test_prompts_uses_rollup_for_360_day_period(monkeypatch, tmp_path):
    prompts_file = tmp_path / "prompts.ini"
    prompts_file.write_text("[prompts]\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_ANALYTICS_PROMPTS_INI", str(prompts_file))
    cache_clear = getattr(getattr(analytics_main, "_builtin_prompt_templates", None), "cache_clear", None)
    if cache_clear:
        cache_clear()

    expected_common_args = (360, None, "natural", None, 1, 1)

    async def fake_fetchrow(query, *args):
        if "to_regclass('public.analytics_prompt_group_stats')" in query:
            return {"ready": True}
        if "occurrence_count" in query and "analytics_prompt_mart_state" in query:
            return {
                "prompt_count": 3,
                "occurrence_count": 10,
                "group_stats_count": 3,
                "rollup_stats_count": 12,
                "stats_updated_at": "2026-06-26T03:00:00",
                "last_history_id": "10",
                "last_refresh_mode": "full",
                "normalization_version": analytics_main.PROMPT_NORMALIZATION_VERSION,
            }
        assert "prompt_summary" in query
        assert "analytics_prompt_rollup_stats" in query
        assert args == expected_common_args
        return {
            "prompt_records": 10,
            "distinct_prompts": 3,
            "repeated_prompts": 1,
            "multi_user_prompts": 1,
            "avg_chars": 50,
            "median_chars": 48,
            "derived_records_excluded": 2,
            "builtin_template_records_excluded": 0,
            "high_value_prompts": 1,
        }

    async def fake_fetch(query, *args):
        if "prompt_candidates_legacy" in query:
            assert args == (360, 5, 20000, None, "natural")
            return []
        assert "analytics_prompt_rollup_stats" in query
        if "prompt_groups_page" in query:
            assert args == (*expected_common_args, "value_score", 5, 0)
        else:
            assert args == expected_common_args
        return []

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/prompts?days=360&limit=5")

    assert response.status_code == 200
    assert response.json()["days"] == 360


@pytest.mark.asyncio
async def test_prompts_rejects_mismatched_normalization_version(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "to_regclass('public.analytics_prompt_group_stats')" in query:
            return {"ready": True}
        if "occurrence_count" in query and "analytics_prompt_mart_state" in query:
            return {
                "prompt_count": 1,
                "occurrence_count": 1,
                "group_stats_count": 1,
                "rollup_stats_count": 1,
                "stats_updated_at": "2026-06-26T03:00:00",
                "last_history_id": "1",
                "last_refresh_mode": "full",
                "normalization_version": "v1",
            }
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected fetch: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/prompts?days=30")

    assert response.status_code == 503
    assert "normalization version mismatch" in response.json()["detail"]


@pytest.mark.asyncio
async def test_prompt_variants_returns_raw_prompt_variants(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "to_regclass('public.analytics_prompt_group_stats')" in query:
            return {"ready": True}
        if "occurrence_count" in query and "analytics_prompt_mart_state" in query:
            return {
                "prompt_count": 2,
                "occurrence_count": 4,
                "group_stats_count": 2,
                "rollup_stats_count": 4,
                "stats_updated_at": "2026-06-26T03:00:00",
                "last_history_id": "10",
                "last_refresh_mode": "full",
                "normalization_version": analytics_main.PROMPT_NORMALIZATION_VERSION,
            }
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        assert "analytics_prompt_occurrence" in query
        assert "variants as" in query
        assert args == ("abc123", 30, "edit", "natural", 3)
        return [
            {
                "raw_prompt": "Cinematic close-up portrait",
                "uses": 3,
                "users": 2,
                "task_types": ["edit"],
                "first_seen": "2026-06-01T00:00:00",
                "last_seen": "2026-06-25T12:00:00",
            },
            {
                "raw_prompt": "cinematic   close-up portrait",
                "uses": 1,
                "users": 1,
                "task_types": ["edit"],
                "first_seen": "2026-06-03T00:00:00",
                "last_seen": "2026-06-03T00:00:00",
            },
        ]

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/prompts/abc123/variants?days=30&task_type=edit&template_scope=natural&limit=3"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prompt_hash"] == "abc123"
    assert payload["variants"][0]["raw_prompt"] == "Cinematic close-up portrait"
    assert payload["variants"][0]["raw_preview"] == "Cinematic close-up portrait"
    assert payload["variants"][1]["uses"] == 1


@pytest.mark.asyncio
async def test_prompt_slim_returns_wide_table_inspection_data(monkeypatch):
    calls = []
    expected_common_args = (
        "candidate",
        "edit",
        "source_template",
        "short_oneoff",
        "%live portrait%",
        2,
        3,
    )

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        if "to_regclass('public.analytics_prompt_slim_candidates')" in query:
            assert args == ()
            return {"ready": True}
        assert "slim_summary" in query
        assert "analytics_prompt_slim_candidates" in query
        lowered = query.lower()
        assert " from history " not in lowered
        assert " join gallery_posts " not in lowered
        assert " join user_interactions " not in lowered
        assert args == expected_common_args
        return {
            "row_type": "slim_summary",
            "slim_prompts": 12,
            "candidate_prompts": 12,
            "auto_rejected_prompts": 0,
            "manual_keep_prompts": 0,
            "manual_reject_prompts": 0,
            "excellent_prompts": 0,
            "archived_prompts": 0,
            "uses": 42,
            "user_refs": 25,
            "avg_chars": 64.5,
            "median_chars": 58,
            "result_likes": 7,
            "result_dislikes": 1,
            "gallery_likes": 9,
            "gallery_dislikes": 0,
            "gallery_applies": 15,
            "prompt_unlocks": 3,
            "latest_refreshed_at": "2026-06-26T09:00:00",
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        assert "analytics_prompt_slim_candidates" in query
        lowered = query.lower()
        assert " from history " not in lowered
        assert " join gallery_posts " not in lowered
        assert " join user_interactions " not in lowered
        if "prompt_slim_rows" in query:
            assert args == (*expected_common_args, "gallery_applies", 10, 10)
            return [
                {
                    "row_type": "prompt_slim_rows",
                    "prompt_hash": "slim123",
                    "normalization_version": analytics_main.PROMPT_NORMALIZATION_VERSION,
                    "prompt": "live portrait cinematic light",
                    "raw_prompt_representative": "Live portrait, cinematic light",
                    "variant_count": 2,
                    "char_count": 29,
                    "uses": 8,
                    "users": 3,
                    "using_user_count": 3,
                    "using_user_ids_sample": [101, 102, 103],
                    "first_seen": "2026-06-01T00:00:00",
                    "last_seen": "2026-06-25T12:00:00",
                    "task_types": ["edit"],
                    "task_type_counts": '{"edit": 8}',
                    "source_scopes": ["source_template"],
                    "source_counts": {"source_template": 8},
                    "result_likes": 4,
                    "result_dislikes": 1,
                    "result_like_user_count": 4,
                    "result_like_user_ids_sample": [101, 102],
                    "result_dislike_user_count": 1,
                    "result_dislike_user_ids_sample": [103],
                    "gallery_posts": 2,
                    "gallery_likes": 9,
                    "gallery_dislikes": 0,
                    "gallery_comments": 1,
                    "gallery_applies": 15,
                    "gallery_apply_user_count": 5,
                    "gallery_apply_user_ids_sample": [201, 202],
                    "prompt_unlocks": 3,
                    "prompt_unlock_user_count": 2,
                    "prompt_unlock_user_ids_sample": [301, 302],
                    "quality_score": 88.5,
                    "positive_signal_score": 91,
                    "negative_signal_score": 2.5,
                    "quality_stage": "candidate",
                    "low_quality_reasons": ["short_oneoff"],
                    "rule_version": "slim-v1-medium",
                    "review_note": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "refreshed_at": "2026-06-26T09:00:00",
                }
            ]
        if "prompt_slim_stage_distribution" in query:
            assert args == expected_common_args
            return [{"label": "candidate", "count": 12}]
        if "prompt_slim_reason_distribution" in query:
            assert args == expected_common_args
            return [{"label": "short_oneoff", "count": 12}]
        if "prompt_slim_task_type_distribution" in query:
            assert args == expected_common_args
            return [{"label": "edit", "count": 12}]
        if "prompt_slim_source_distribution" in query:
            assert args == expected_common_args
            return [{"label": "source_template", "count": 12}]
        if "prompt_slim_length_distribution" in query:
            assert args == expected_common_args
            return [{"label": "21-40 字", "count": 12}]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/prompt-slim?quality_stage=candidate&task_type=edit"
            "&source_scope=source_template&reason=short_oneoff&q=Live%20portrait"
            "&min_users=2&min_uses=3&sort=gallery_applies&limit=10&page=2"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_stage"] == "candidate"
    assert payload["summary"]["slim_prompts"] == 12
    assert payload["distributions"]["stage"] == [{"label": "candidate", "count": 12}]
    assert payload["distributions"]["reason"] == [{"label": "short_oneoff", "count": 12}]
    assert payload["rows"][0]["prompt_hash"] == "slim123"
    assert payload["rows"][0]["prompt_preview"] == "live portrait cinematic light"
    assert payload["rows"][0]["raw_prompt_preview"] == "Live portrait, cinematic light"
    assert payload["rows"][0]["task_type_counts"] == {"edit": 8}
    assert payload["pagination"] == {"page": 2, "limit": 10, "total": 12, "has_next": False}
    assert any(call[0] == "fetch" and call[2][-3:] == ("gallery_applies", 10, 10) for call in calls)


@pytest.mark.asyncio
async def test_prompt_slim_rejects_invalid_filters(monkeypatch):
    async def fake_fetchrow(query, *args):
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected fetch: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        bad_stage = await client.get("/api/prompt-slim?quality_stage=bad")
        bad_sort = await client.get("/api/prompt-slim?sort=bad")
        bad_source = await client.get("/api/prompt-slim?source_scope=builtin_template")

    assert bad_stage.status_code == 400
    assert bad_sort.status_code == 400
    assert bad_source.status_code == 400
