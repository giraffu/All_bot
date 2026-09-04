import pytest
import asyncpg
import json

from local_analytics_platform.app.refresh_prompt_vectors import _is_closed_connection_error
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import (
    CREATE_PROMPT_VECTOR_SCHEMA_SQL,
    DEFAULT_VECTOR_MODEL_ID,
    PROMPT_TOKEN_OCCURRENCE_SCOPE_SQL,
    PROMPT_TOKEN_UNAVAILABLE_TASK,
    PROMPT_TOKEN_VERSION,
    PromptVectorConfig,
    apply_prompt_token_custom_terms,
    apply_prompt_token_aliases,
    build_prompt_token_custom_term_matcher,
    build_prompt_token_alias_map,
    config_from_args,
    embedding_from_bytes,
    embedding_to_bytes,
    extract_prompt_tokens,
    normalize_embedding,
    prompt_vector_arg_parser,
    prompt_token_scope_label,
    prompt_token_task_scope_key,
    prompt_token_cache_checksum,
    refresh_prompt_embeddings,
    refresh_prompt_token_stats,
    validate_prompt_token_alias_rules,
    validate_prompt_token_custom_terms,
)
from local_analytics_platform.app.prompt_token_rules import (
    build_prompt_token_rule_seed_rows,
    decompose_prompt_token,
)


def test_prompt_vector_schema_contains_persistent_tables_and_indexes():
    schema_sql = "\n".join(CREATE_PROMPT_VECTOR_SCHEMA_SQL).lower()

    assert "create table if not exists analytics_prompt_embeddings" in schema_sql
    assert "embedding_f16 bytea" in schema_sql
    assert "primary key (model_id, normalization_version, prompt_hash)" in schema_sql
    assert "create table if not exists analytics_prompt_vector_state" in schema_sql
    assert "create table if not exists analytics_prompt_token_stats" in schema_sql
    assert "create table if not exists analytics_prompt_token_prompts" in schema_sql
    assert "create table if not exists analytics_prompt_token_scope_summary" in schema_sql
    assert "create table if not exists analytics_prompt_token_alias_rules" in schema_sql
    assert "create table if not exists analytics_prompt_token_custom_terms" in schema_sql
    assert "category_key text not null default ''" in schema_sql
    assert "subcategory_key text not null default ''" in schema_sql
    assert "seed_batch text not null default ''" in schema_sql
    assert "notes text not null default ''" in schema_sql
    assert "create table if not exists analytics_prompt_token_extract_cache" in schema_sql
    assert "create table if not exists analytics_prompt_token_deleted_rules" in schema_sql
    assert "idx_prompt_token_alias_rules_enabled" in schema_sql
    assert "idx_prompt_token_custom_terms_enabled" in schema_sql
    assert "idx_prompt_token_extract_cache_updated" in schema_sql
    assert "idx_prompt_token_deleted_rules_updated" in schema_sql
    assert "scope_kind text not null default 'task'" in schema_sql
    assert "scopes text[] not null default '{}'" in schema_sql
    assert "scope_uses jsonb not null default '{}'::jsonb" in schema_sql
    assert "idx_prompt_token_stats_prompt_sort" in schema_sql
    assert "idx_prompt_token_stats_scope_options" in schema_sql
    assert "idx_prompt_token_prompts_score" in schema_sql
    assert "idx_prompt_token_stats_top" not in schema_sql
    assert "idx_prompt_token_stats_token" not in schema_sql
    assert "idx_prompt_token_stats_use_sort" not in schema_sql
    assert "idx_prompt_token_stats_user_sort" not in schema_sql
    assert "idx_prompt_token_prompts_tokens" not in schema_sql
    assert "idx_prompt_token_prompts_scopes" not in schema_sql
    assert "idx_prompt_embeddings_task" in schema_sql
    assert "analytics_prompt_similarity_edges" not in schema_sql
    assert "analytics_prompt_similarity_clusters" not in schema_sql
    assert "analytics_prompt_similarity_members" not in schema_sql


def test_prompt_embedding_is_l2_normalized_float16_bytes():
    vector = normalize_embedding([3.0, 4.0])
    assert vector.dtype.name == "float16"
    restored = embedding_from_bytes(embedding_to_bytes(vector), 2)
    assert restored.dtype.name == "float16"
    assert float((restored.astype("float32") ** 2).sum()) == pytest.approx(1.0, abs=0.001)


def test_extract_prompt_tokens_handles_latin_and_cjk_prompt_terms():
    tokens = extract_prompt_tokens("[edit] cinematic portrait, soft-light, 仙侠少女高清画质")

    assert "edit" not in tokens
    assert "cinematic" in tokens
    assert "portrait" in tokens
    assert "soft" in tokens
    assert "light" in tokens
    assert "仙侠" in tokens
    assert "少女" in tokens
    assert "高清" in tokens
    assert "画质" in tokens


def test_extract_prompt_tokens_keeps_cjk_lexemes_without_cross_boundary_fragments():
    tokens = extract_prompt_tokens("背景不变，保持人物相貌特征的一致性，胸部自然，价格保持一致，女人的脸部特征")

    for expected in ("背景不变", "背景", "不变", "保持", "人物", "相貌", "特征", "一致性", "胸部", "自然", "脸部"):
        assert expected in tokens
    for fragment in ("格保", "部特", "人的", "的一", "女人的", "女人的脸部特征"):
        assert fragment not in tokens


def test_prompt_token_alias_rules_split_commas_and_reject_conflicts():
    rules = validate_prompt_token_alias_rules(
        [
            {"representative": "面部", "aliases_text": "脸部，面容, 面容"},
            {"representative": "光影", "aliases": ["光线", "光照"]},
        ]
    )

    assert rules[0].representative == "面部"
    assert rules[0].aliases == ("脸部", "面容")
    alias_map = build_prompt_token_alias_map(rules)
    assert apply_prompt_token_aliases(["脸部", "面容", "光照", "姿势"], alias_map) == ["面部", "光影", "姿势"]

    with pytest.raises(ValueError, match="同义词元重复映射"):
        validate_prompt_token_alias_rules(
            [
                {"representative": "面部", "aliases_text": "脸部"},
                {"representative": "相貌", "aliases_text": "脸部"},
            ]
        )
    with pytest.raises(ValueError, match="同义词元不能同时作为代表词元"):
        validate_prompt_token_alias_rules(
            [
                {"representative": "面部", "aliases_text": "相貌"},
                {"representative": "相貌", "aliases_text": "面容"},
            ]
        )


def test_prompt_token_custom_terms_split_commas_and_add_terms_from_prompt_text():
    rules = validate_prompt_token_custom_terms(
        [
            {"term": "高马尾，蓝紫渐变发色"},
            {"term": "character"},
            {"term": "高马尾"},
        ]
    )

    assert [rule.term for rule in rules] == ["高马尾", "蓝紫渐变发色", "character"]
    tokens = apply_prompt_token_custom_terms(
        ["portrait"],
        "一位蓝紫渐变发色的少女，扎着高马尾，character sheet",
        rules,
    )

    assert tokens == ["portrait", "高马尾", "蓝紫渐变发色", "character"]


def test_prompt_token_custom_term_matcher_preserves_custom_term_behavior():
    rules = validate_prompt_token_custom_terms(
        [
            {"term": "高马尾，蓝紫渐变发色"},
            {"term": "full body"},
            {"term": "body"},
            {"term": "character"},
        ]
    )
    prompt = "A full body character sheet, 一位蓝紫渐变发色的少女，扎着高马尾"
    raw_tokens = ["portrait", "body"]
    matcher = build_prompt_token_custom_term_matcher(rules)

    assert apply_prompt_token_custom_terms(raw_tokens, prompt, matcher) == apply_prompt_token_custom_terms(
        raw_tokens,
        prompt,
        rules,
    )
    assert apply_prompt_token_custom_terms(["portrait"], "halfbody character", matcher) == [
        "portrait",
        "character",
    ]


def test_manual_prompt_token_rules_allow_explicit_single_cjk_terms():
    alias_rules = validate_prompt_token_alias_rules(
        [
            {"representative": "门", "aliases_text": "door"},
            {"representative": "小", "aliases_text": "small"},
        ]
    )
    custom_terms = validate_prompt_token_custom_terms([{"term": "门，小，手肘撑地"}])

    assert [rule.term for rule in custom_terms] == ["门", "小", "手肘撑地"]
    alias_map = build_prompt_token_alias_map(alias_rules)
    assert apply_prompt_token_aliases(["door", "small", "门口"], alias_map) == ["门", "小", "门口"]

    tokens = apply_prompt_token_custom_terms([], "门边有一个小窗，左手手肘撑地", custom_terms)
    assert tokens == ["门", "小", "手肘撑地"]
    assert "门" not in extract_prompt_tokens("门")

    with pytest.raises(ValueError, match="指定词元无效: 的"):
        validate_prompt_token_custom_terms([{"term": "的"}])


def test_prompt_token_generated_rules_decompose_long_terms_and_alias_after_custom_scan():
    generated = build_prompt_token_rule_seed_rows(
        [
            {"token": "无毛小穴", "prompt_count": 120},
            {"token": "林子瑜的房子", "prompt_count": 90},
            {"token": "木瓜", "prompt_count": 80},
        ],
        seed_batch="test-seed",
    )
    custom_terms = validate_prompt_token_custom_terms(generated["custom_terms"])
    alias_rules = validate_prompt_token_alias_rules(generated["alias_rules"])
    custom_term_set = {rule.term for rule in custom_terms}

    assert {"无毛", "小穴", "房子"}.issubset(custom_term_set)
    assert "木瓜奶" in custom_term_set
    assert "木瓜" not in custom_term_set
    assert decompose_prompt_token("无毛小穴", custom_term_set) == ["无毛", "小穴"]
    assert decompose_prompt_token("林子瑜的房子", custom_term_set) == ["房子"]
    assert decompose_prompt_token("small", {"all"}) == []

    raw_tokens = apply_prompt_token_custom_terms(["无毛小穴"], "无毛小穴", custom_terms)
    assert "无毛小穴" not in raw_tokens
    alias_map = build_prompt_token_alias_map(alias_rules)
    assert set(apply_prompt_token_aliases(raw_tokens, alias_map)) == {"无毛", "阴道"}

    name_tokens = apply_prompt_token_custom_terms(["林子瑜的房子"], "林子瑜的房子", custom_terms)
    assert "房子" in name_tokens
    assert "林子瑜" not in name_tokens
    assert "林子瑜的房子" not in name_tokens


def test_prompt_token_generated_rules_include_category_metadata():
    generated = build_prompt_token_rule_seed_rows(
        [{"token": "深蹲姿势", "prompt_count": 55}],
        seed_batch="test-seed",
    )

    custom_rule = next(rule for rule in generated["custom_terms"] if rule.term == "深蹲")
    alias_rule = next(rule for rule in generated["alias_rules"] if rule.representative == "阴道")
    penis_rule = next(rule for rule in generated["alias_rules"] if rule.representative == "阴茎")
    bed_rule = next(rule for rule in generated["alias_rules"] if rule.representative == "床")
    doggy_rule = next(rule for rule in generated["alias_rules"] if rule.representative == "狗式")

    custom_terms = {rule.term for rule in generated["custom_terms"]}
    alias_representatives = {rule.representative for rule in generated["alias_rules"]}

    assert custom_rule.category_key == "pose_action"
    assert custom_rule.category_label == "动作姿势"
    assert alias_rule.category_key == "adult_anatomy"
    assert alias_rule.category_label == "身体部分"
    assert alias_rule.subcategory_key == "genital"
    assert "보지" in alias_rule.aliases
    assert "자지" in penis_rule.aliases
    assert bed_rule.category_label == "场景"
    assert "bed" in bed_rule.aliases
    assert doggy_rule.category_label == "动作姿势"
    assert "doggy" in doggy_rule.aliases
    assert {"背景", "人物", "头发", "镜头", "角度"}.isdisjoint(custom_terms)
    assert {"头发", "镜头", "角度", "焦点"}.isdisjoint(alias_representatives)
    assert generated["report"]["coverage"]["decomposed"] >= 1


def test_prompt_token_attribute_split_and_fragment_cleanup_rules():
    generated = build_prompt_token_rule_seed_rows(
        [
            {"token": "门", "prompt_count": 32451},
            {"token": "字腿", "prompt_count": 12531},
            {"token": "便器", "prompt_count": 16815},
            {"token": "雙腿", "prompt_count": 14950},
            {"token": "大奶", "prompt_count": 4300},
            {"token": "巨乳", "prompt_count": 45044},
            {"token": "贫乳", "prompt_count": 5733},
            {"token": "陰毛濃密", "prompt_count": 210},
            {"token": "少量陰毛", "prompt_count": 67},
            {"token": "小鸡巴", "prompt_count": 43},
            {"token": "大鸡巴", "prompt_count": 58},
            {"token": "m型开腿", "prompt_count": 24},
            {"token": "m形开腿", "prompt_count": 18},
            {"token": "腿呈", "prompt_count": 7159},
            {"token": "雙腿呈", "prompt_count": 596},
            {"token": "张开双腿成", "prompt_count": 21},
            {"token": "字型腿", "prompt_count": 10},
        ],
        seed_batch="test-seed",
    )
    custom_terms = validate_prompt_token_custom_terms(generated["custom_terms"])
    alias_rules = validate_prompt_token_alias_rules(generated["alias_rules"])
    custom_term_set = {rule.term for rule in custom_terms}
    alias_map = build_prompt_token_alias_map(alias_rules)

    assert {"门", "字腿", "便器", "双腿", "雙腿"}.isdisjoint(custom_term_set)
    assert alias_map["雙腿張開"] == "双腿分开"
    assert alias_map["雙腿大幅打開"] == "双腿分开"
    assert alias_map["大奶"] == "大胸"
    assert alias_map["巨乳"] == "大胸"
    assert alias_map["爆乳"] == "大胸"
    assert alias_map["丰满胸部"] == "大胸"
    assert alias_map["小奶"] == "小胸"
    assert alias_map["贫乳"] == "小胸"
    assert alias_map["貧乳"] == "小胸"
    assert alias_map["无胸"] == "平胸"
    assert alias_map["陰毛濃密"] == "浓密阴毛"
    assert alias_map["少量陰毛"] == "稀疏阴毛"
    assert alias_map["無陰毛"] == "无阴毛"
    assert alias_map["小鸡巴"] == "小阴茎"
    assert alias_map["大鸡巴"] == "大阴茎"
    assert "小鸡巴" not in alias_map or alias_map["小鸡巴"] != "阴茎"
    assert alias_map["m型开腿"] == "m字开腿"
    assert alias_map["m形开腿"] == "m字开腿"

    tokens = extract_prompt_tokens(
        "左图女生坐在地上,摆m 字腿,m型开腿,m形开腿,雙腿大幅打開,双腿呈张开,"
        "雙腿呈m字型,腿呈M形,张开双腿成m型,大腿是m字型腿,露出肛门,腿成m形,高度彎腰"
    )
    assert "m字开腿" in tokens
    assert "双腿分开" in tokens
    assert "弯腰" in tokens
    assert "肛门" in tokens
    assert {
        "门",
        "字腿",
        "雙腿",
        "腿呈",
        "雙腿呈",
        "张开双腿成",
        "字型",
        "字型腿",
        "高度彎腰",
        "m型开腿",
        "m形开腿",
    }.isdisjoint(tokens)


def test_prompt_token_generated_rules_include_demographic_and_variant_rules():
    generated = build_prompt_token_rule_seed_rows(
        [
            {"token": "亚洲小男孩", "prompt_count": 3020},
            {"token": "亚洲女生", "prompt_count": 467},
            {"token": "台灣女生", "prompt_count": 24},
            {"token": "老年男生", "prompt_count": 54},
            {"token": "12岁女孩", "prompt_count": 391},
            {"token": "台灣", "prompt_count": 1},
            {"token": "陰茎", "prompt_count": 47},
        ],
        seed_batch="test-seed",
    )
    custom_terms = validate_prompt_token_custom_terms(generated["custom_terms"])
    alias_rules = validate_prompt_token_alias_rules(generated["alias_rules"])
    custom_by_term = {rule.term: rule for rule in custom_terms}
    alias_map = build_prompt_token_alias_map(alias_rules)

    assert alias_map["陰茎"] == "阴茎"
    assert alias_map["陰莖"] == "阴茎"
    assert alias_map["台灣"] == "台湾"
    assert alias_map["臺灣"] == "台湾"
    assert alias_map["老年男生"] == "老年男性"
    assert alias_map["亞洲"] == "亚洲人"
    assert alias_map["亚裔"] == "亚洲人"
    assert alias_map["亚洲女生"] == "亚洲女性"
    assert alias_map["亞洲女生"] == "亚洲女性"
    assert alias_map["台灣女生"] == "台湾女性"
    assert alias_map["台湾男生"] == "台湾男性"
    assert "亚洲小男孩" in custom_by_term
    assert custom_by_term["亚洲小男孩"].subcategory_label == "族裔年龄性别"
    assert "12岁女孩" in custom_by_term
    assert custom_by_term["12岁女孩"].subcategory_label == "数字年龄"
    assert alias_map.get("亚洲小男孩") is None
    assert generated["report"]["coverage"]["observed_demographic"] >= 2


def test_prompt_token_generated_rules_do_not_auto_seed_unknown_observed_terms():
    generated = build_prompt_token_rule_seed_rows(
        [{"token": "随机高频词", "prompt_count": 9999}],
        seed_batch="test-seed",
    )

    custom_term_set = {rule.term for rule in generated["custom_terms"]}
    assert "随机高频词" not in custom_term_set
    assert all(rule.category_label != "观测高频词" for rule in generated["custom_terms"])
    assert generated["report"]["coverage"]["retained_independent"] >= 1


def test_prompt_token_v2_people_counts_and_phrase_terms_are_preserved():
    alias_rules = validate_prompt_token_alias_rules(
        [
            {"representative": "单男", "aliases_text": "1boy"},
            {"representative": "双人", "aliases_text": "两人，俩人"},
        ]
    )
    custom_terms = validate_prompt_token_custom_terms(
        [
            {"term": "单男，双人，五人，黑人，木瓜奶"},
        ]
    )

    tokens = extract_prompt_tokens("五个黑人站在旁边，1boy，胸前是木瓜奶")
    assert "五人" in tokens
    assert "黑人" in tokens
    assert "木瓜奶" in tokens
    assert "木瓜" not in tokens

    enriched = apply_prompt_token_custom_terms(tokens, "五个黑人站在旁边，1boy，胸前是木瓜奶", custom_terms)
    alias_map = build_prompt_token_alias_map(alias_rules)
    mapped = apply_prompt_token_aliases(enriched, alias_map)
    assert {"五人", "黑人", "单男", "木瓜奶"}.issubset(set(mapped))


def test_prompt_token_task_scope_maps_history_types_to_current_available_tasks():
    assert prompt_token_task_scope_key("img2img_lora") == "edit"
    assert prompt_token_task_scope_key("image") == "edit"
    assert prompt_token_task_scope_key("pornmaster_flux2_multi_edit") == "edit_v2"
    assert prompt_token_task_scope_key("text_to_image") == "txt2img"
    assert prompt_token_task_scope_key("ltx_video_flf2v") == "ltx_video"
    assert prompt_token_task_scope_key("minimax_h3_t2v") == "minimax_h3"
    assert prompt_token_task_scope_key("minimax_h3_i2v") == "minimax_h3"
    assert prompt_token_task_scope_key("minimax_h3_flf2v") == "minimax_h3"
    assert prompt_token_task_scope_key("minimax_h3_ref2v") == "minimax_h3"
    assert prompt_token_task_scope_key("scail2_action_transfer_long") == "scail2_action_transfer"
    assert prompt_token_task_scope_key("i2i_draw") == PROMPT_TOKEN_UNAVAILABLE_TASK
    assert prompt_token_task_scope_key("legacy_removed_mode") == PROMPT_TOKEN_UNAVAILABLE_TASK
    assert prompt_token_scope_label("edit") == "自由P图"
    assert prompt_token_scope_label("minimax_h3") == "高级图生视频 Pro"
    assert prompt_token_scope_label(PROMPT_TOKEN_UNAVAILABLE_TASK) == "无可用任务"


def test_prompt_token_scopes_read_structured_minimax_h3_addons_without_double_counting_tasks():
    sql = PROMPT_TOKEN_OCCURRENCE_SCOPE_SQL.lower()

    assert "_minimax_h3_context" in sql
    assert "lora_items" in sql
    assert "task_scopes as" in sql
    assert "model_scopes as" in sql
    assert "select distinct" in sql


def test_refresh_prompt_vectors_treats_asyncpg_connection_errors_as_retryable():
    assert _is_closed_connection_error(asyncpg.ConnectionDoesNotExistError("server closed"))
    assert _is_closed_connection_error(asyncpg.InterfaceError("connection is closed"))


class FakeEmbeddingConn:
    def __init__(self):
        self.executed = []
        self.executemany_calls = []

    async def fetch(self, query, *args):
        self.executed.append((query, args))
        assert "not exists" in query.lower()
        assert args[0] == PROMPT_NORMALIZATION_VERSION
        assert args[2] == DEFAULT_VECTOR_MODEL_ID
        return [
            {"prompt_hash": "a" * 32, "task_type": "edit", "prompt": "cinematic portrait"},
            {"prompt_hash": "b" * 32, "task_type": "edit", "prompt": "cinematic portrait, soft light"},
        ]

    async def executemany(self, query, rows):
        self.executemany_calls.append((query, rows))

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "OK"


class FakeEmbeddingClient:
    def embed(self, texts):
        assert texts == ["cinematic portrait", "cinematic portrait, soft light"]
        return [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]]


class FakeTokenConn:
    def __init__(self, alias_rows=None, cache_rows=None, custom_term_rows=None):
        self.fetch_calls = 0
        self.executed = []
        self.executemany_calls = []
        self.alias_rows = alias_rows or []
        self.cache_rows = cache_rows or []
        self.custom_term_rows = custom_term_rows or []

    async def fetch(self, query, *args):
        if "analytics_prompt_token_alias_rules" in query:
            return self.alias_rows
        if "analytics_prompt_token_custom_terms" in query:
            return self.custom_term_rows
        if "analytics_prompt_token_extract_cache" in query:
            return self.cache_rows
        self.fetch_calls += 1
        if "analytics_prompt_occurrence" in query:
            assert args[0] == ["a" * 32, "b" * 32]
            return [
                {
                    "prompt_hash": "a" * 32,
                    "task_type": "img2img_lora",
                    "model_tag": None,
                    "task_scope": True,
                    "uses": 2,
                    "users": 1,
                },
                {
                    "prompt_hash": "a" * 32,
                    "task_type": "img2img_lora",
                    "model_tag": "qwen/YARN_1.0.safetensors",
                    "task_scope": False,
                    "uses": 2,
                    "users": 1,
                },
                {
                    "prompt_hash": "b" * 32,
                    "task_type": "image",
                    "model_tag": None,
                    "task_scope": True,
                    "uses": 3,
                    "users": 2,
                },
            ]
        assert "analytics_prompt_slim_candidates" in query
        if self.fetch_calls > 2:
            return []
        assert args[0] == PROMPT_NORMALIZATION_VERSION
        return [
            {
                "prompt_hash": "a" * 32,
                "prompt": "cinematic portrait, soft light",
                "char_count": 30,
                "uses": 2,
                "users": 1,
                "task_types": ["img2img_lora"],
                "quality_score": 82.5,
                "last_seen": "2026-07-04T12:00:00",
            },
            {
                "prompt_hash": "b" * 32,
                "prompt": "cinematic portrait, 仙侠少女",
                "char_count": 28,
                "uses": 3,
                "users": 2,
                "task_types": ["image"],
                "quality_score": 90,
                "last_seen": "2026-07-04T13:00:00",
            },
        ]

    async def executemany(self, query, rows):
        self.executemany_calls.append((query, rows))

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "OK"


def _executemany_for_table(conn, table_name):
    for query, rows in conn.executemany_calls:
        if table_name in query:
            return query, rows
    raise AssertionError(f"missing executemany for {table_name}")


@pytest.mark.asyncio
async def test_refresh_prompt_embeddings_batches_and_stores_float16_vectors():
    conn = FakeEmbeddingConn()
    config = PromptVectorConfig(model_id=DEFAULT_VECTOR_MODEL_ID, batch_size=2, limit=2, skip_lm_check=True)

    status = await refresh_prompt_embeddings(conn, FakeEmbeddingClient(), config)

    assert status["selected"] == 2
    assert status["embedded"] == 2
    assert status["embedding_dim"] == 3
    query, rows = conn.executemany_calls[0]
    assert "analytics_prompt_embeddings" in query
    assert rows[0][0] == "a" * 32
    assert rows[0][6] == 3
    assert rows[0][7] == "float16"
    assert embedding_from_bytes(rows[0][8], 3).dtype.name == "float16"


@pytest.mark.asyncio
async def test_refresh_prompt_token_stats_materializes_top_prompt_terms():
    conn = FakeTokenConn()

    status = await refresh_prompt_token_stats(conn, top_per_task=10, batch_size=10)

    assert status["prompt_count"] == 2
    assert status["token_count"] >= 4
    prompt_query, prompt_rows = _executemany_for_table(conn, "analytics_prompt_token_prompts")
    assert "analytics_prompt_token_prompts" in prompt_query
    assert prompt_rows[0][2] == "a" * 32
    assert "cinematic" in prompt_rows[0][4]
    assert "all" in prompt_rows[0][6]
    assert "edit" in prompt_rows[0][6]
    assert "model|edit|qwen/YARN_1.0.safetensors" in prompt_rows[0][6]
    assert "img2img_lora" not in prompt_rows[0][6]
    assert json.loads(prompt_rows[0][7])["edit"] == 2
    query, rows = _executemany_for_table(conn, "analytics_prompt_token_stats")
    assert "analytics_prompt_token_stats" in query
    all_rows = {row[3]: row for row in rows if row[2] == "all"}
    task_rows = {row[3]: row for row in rows if row[2] == "edit"}
    model_rows = {row[3]: row for row in rows if row[2] == "model|edit|qwen/YARN_1.0.safetensors"}
    assert all_rows["cinematic"][5] == 2
    assert all_rows["cinematic"][6] == 5
    assert all_rows["portrait"][5] == 2
    assert task_rows["cinematic"][5] == 2
    assert task_rows["cinematic"][8] == "task"
    assert task_rows["cinematic"][9] == "自由P图"
    assert model_rows["cinematic"][5] == 1
    assert model_rows["cinematic"][8] == "model"
    assert model_rows["cinematic"][10] == "edit"
    assert model_rows["cinematic"][11] == "qwen/YARN_1.0.safetensors"
    assert "少女" in all_rows
    assert status["token_version"] == PROMPT_TOKEN_VERSION
    cache_query, cache_rows = _executemany_for_table(conn, "analytics_prompt_token_extract_cache")
    assert "on conflict" in cache_query.lower()
    assert cache_rows[0][2] == "a" * 32
    assert "cinematic" in cache_rows[0][4]
    _summary_query, summary_rows = _executemany_for_table(conn, "analytics_prompt_token_scope_summary")
    summary_counts = {row[2]: row[3] for row in summary_rows}
    assert summary_counts["all"] == 2
    assert summary_counts["edit"] == 2
    assert summary_counts["model|edit|qwen/YARN_1.0.safetensors"] == 1
    assert status["cache_hits"] == 0
    assert status["cache_misses"] == 2
    assert "phase_seconds" in status
    index_seconds = status["phase_seconds"]["create_index_seconds"]
    assert set(index_seconds) == {
        "idx_prompt_token_stats_scope_options",
        "idx_prompt_token_stats_prompt_sort",
        "idx_prompt_token_prompts_score",
    }
    assert any("maintenance_work_mem" in query for query, _args in conn.executed)
    assert any("max_parallel_maintenance_workers" in query for query, _args in conn.executed)


@pytest.mark.asyncio
async def test_refresh_prompt_token_stats_applies_alias_rules_before_materializing():
    conn = FakeTokenConn(
        alias_rows=[
            {
                "representative_token": "portrait",
                "alias_tokens": ["cinematic"],
                "enabled": True,
                "sort_order": 0,
            }
        ]
    )

    await refresh_prompt_token_stats(conn, top_per_task=10, batch_size=10)

    _prompt_query, prompt_rows = _executemany_for_table(conn, "analytics_prompt_token_prompts")
    assert prompt_rows[0][4].count("portrait") == 1
    assert "cinematic" not in prompt_rows[0][4]
    _stat_query, stat_rows = _executemany_for_table(conn, "analytics_prompt_token_stats")
    all_rows = {row[3]: row for row in stat_rows if row[2] == "all"}
    assert "cinematic" not in all_rows
    assert all_rows["portrait"][5] == 2


@pytest.mark.asyncio
async def test_refresh_prompt_token_stats_reuses_raw_token_extract_cache_before_aliasing():
    first_prompt = "cinematic portrait, soft light"
    second_prompt = "cinematic portrait, 仙侠少女"
    conn = FakeTokenConn(
        alias_rows=[
            {
                "representative_token": "portrait",
                "alias_tokens": ["cinematic"],
                "enabled": True,
                "sort_order": 0,
            }
        ],
        cache_rows=[
            {
                "prompt_hash": "a" * 32,
                "prompt_checksum": prompt_token_cache_checksum(first_prompt),
                "raw_tokens": ["cinematic", "portrait", "soft", "light"],
            },
            {
                "prompt_hash": "b" * 32,
                "prompt_checksum": prompt_token_cache_checksum(second_prompt),
                "raw_tokens": ["cinematic", "portrait", "少女"],
            },
        ],
    )

    status = await refresh_prompt_token_stats(conn, top_per_task=10, batch_size=10)

    assert status["cache_hits"] == 2
    assert status["cache_misses"] == 0
    assert all("analytics_prompt_token_extract_cache" not in query for query, _rows in conn.executemany_calls)
    _prompt_query, prompt_rows = _executemany_for_table(conn, "analytics_prompt_token_prompts")
    assert prompt_rows[0][4] == ["portrait", "soft", "light"]
    _stat_query, stat_rows = _executemany_for_table(conn, "analytics_prompt_token_stats")
    all_rows = {row[3]: row for row in stat_rows if row[2] == "all"}
    assert "cinematic" not in all_rows
    assert all_rows["portrait"][5] == 2


@pytest.mark.asyncio
async def test_refresh_prompt_token_stats_adds_custom_terms_from_prompt_before_aliasing():
    second_prompt = "cinematic portrait, 仙侠少女"
    conn = FakeTokenConn(
        alias_rows=[
            {
                "representative_token": "仙侠",
                "alias_tokens": ["仙侠少女"],
                "enabled": True,
                "sort_order": 0,
            }
        ],
        custom_term_rows=[
            {
                "term": "仙侠少女",
                "enabled": True,
                "sort_order": 0,
            }
        ],
        cache_rows=[
            {
                "prompt_hash": "b" * 32,
                "prompt_checksum": prompt_token_cache_checksum(second_prompt),
                "raw_tokens": ["cinematic", "portrait", "少女"],
            },
        ],
    )

    status = await refresh_prompt_token_stats(conn, top_per_task=10, batch_size=10)

    assert status["cache_hits"] == 1
    _prompt_query, prompt_rows = _executemany_for_table(conn, "analytics_prompt_token_prompts")
    second_row = next(row for row in prompt_rows if row[2] == "b" * 32)
    assert "仙侠" in second_row[4]
    assert "仙侠少女" not in second_row[4]
    _stat_query, stat_rows = _executemany_for_table(conn, "analytics_prompt_token_stats")
    all_rows = {row[3]: row for row in stat_rows if row[2] == "all"}
    assert "仙侠" in all_rows
    assert "仙侠少女" not in all_rows


def test_prompt_vector_cli_keeps_embed_only_compatibility_and_rejects_similarity_modes():
    parser = prompt_vector_arg_parser()

    config = config_from_args(parser.parse_args(["--embed-only"]))
    assert config.embed_only is True
    token_config = config_from_args(parser.parse_args(["--tokens-only", "--skip-token-refresh"]))
    assert token_config.tokens_only is True
    assert token_config.skip_token_refresh is True

    with pytest.raises(SystemExit):
        parser.parse_args(["--similarity-only"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--cluster-only"])
