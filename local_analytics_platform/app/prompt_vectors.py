from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np

from .prompt_mart import PROMPT_NORMALIZATION_VERSION


DEFAULT_VECTOR_MODEL_KEY = "text-embedding-qwen3-embedding-8b"
DEFAULT_VECTOR_MODEL_ID = "qwen3-embedding-8b"
DEFAULT_LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_VECTOR_DATA_DIR = "/app/data/prompt_vectors"
EMBEDDING_DTYPE = "float16"
PROMPT_TOKEN_VERSION = "token-v6-available-task-scope-cjk-lexeme-derived"
PROMPT_TOKEN_ALL_TASK = "all"
PROMPT_TOKEN_UNAVAILABLE_TASK = "unavailable_task"
PROMPT_TOKEN_MODEL_SCOPE_PREFIX = "model|"
PROMPT_TOKEN_BATCH_SIZE = 5000
PROMPT_TOKEN_INSERT_BATCH_SIZE = 10000
PROMPT_TOKEN_TOP_PER_TASK = 200
PROMPT_TOKEN_MAX_PER_PROMPT = 120
PROMPT_TOKEN_INDEX_MAINTENANCE_WORK_MEM = os.getenv(
    "LOCAL_ANALYTICS_TOKEN_INDEX_MAINTENANCE_WORK_MEM",
    "1GB",
).strip()
PROMPT_TOKEN_INDEX_MAX_PARALLEL_WORKERS = os.getenv(
    "LOCAL_ANALYTICS_TOKEN_INDEX_MAX_PARALLEL_WORKERS",
    "4",
).strip()
PROMPT_TOKEN_STAT_COPY_COLUMNS = (
    "normalization_version",
    "token_version",
    "task_type",
    "token",
    "token_kind",
    "prompt_count",
    "use_count",
    "user_count",
    "scope_kind",
    "scope_label",
    "parent_task_type",
    "model_key",
    "model_label",
)
PROMPT_TOKEN_SCOPE_SUMMARY_COPY_COLUMNS = (
    "normalization_version",
    "token_version",
    "task_type",
    "candidate_count",
)
PROMPT_TOKEN_PROMPT_COPY_COLUMNS = (
    "normalization_version",
    "token_version",
    "prompt_hash",
    "prompt",
    "tokens",
    "task_types",
    "scopes",
    "scope_uses",
    "scope_users",
    "char_count",
    "uses",
    "users",
    "quality_score",
    "last_seen",
)
PROMPT_TOKEN_EXTRACT_CACHE_COLUMNS = (
    "normalization_version",
    "token_version",
    "prompt_hash",
    "prompt_checksum",
    "raw_tokens",
)

PROMPT_ZERO_WIDTH_CHARS = "".join(
    chr(codepoint)
    for codepoint in (
        8203,
        8204,
        8205,
        8206,
        8207,
        8234,
        8235,
        8236,
        8237,
        8238,
        8288,
        65279,
    )
)
PROMPT_ZERO_WIDTH_TRANSLATION = str.maketrans("", "", PROMPT_ZERO_WIDTH_CHARS)
PROMPT_LEADING_METADATA_RE = re.compile(r"^(\s*\[[^\]]*\]\s*)+")
PROMPT_TOKEN_CHUNK_RE = re.compile(r"[a-z0-9][a-z0-9_+.-]{1,60}|[\u3400-\u9fff]{2,}")
PROMPT_TOKEN_SEPARATOR_RE = re.compile(r"[_+.-]+")
PROMPT_TOKEN_ALIAS_SPLIT_RE = re.compile(r"[，,]+")
PROMPT_TOKEN_STOPWORDS = {
    "prompt",
    "image",
    "picture",
    "photo",
    "style",
    "quality",
    "best",
    "high",
    "ultra",
    "very",
    "with",
    "and",
    "the",
    "for",
    "一个",
    "一张",
    "图片",
    "照片",
    "画面",
    "风格",
    "生成",
    "以及",
    "或者",
}
PROMPT_TOKEN_CJK_GRAMMAR_FRAGMENTS = {
    "的",
    "地",
    "得",
    "之",
    "人的",
    "的一",
    "的是",
    "他的",
    "她的",
    "它的",
    "我的",
    "你的",
    "这个",
    "那个",
    "这些",
    "那些",
}
PROMPT_TOKEN_DERIVED_CANONICAL_CJK_TOKENS = {
    "双腿分开",
    "双腿抬起",
    "双腿弯曲",
    "双腿并拢",
    "m字开腿",
}
PROMPT_TOKEN_CJK_FRAGMENT_NOISE_RE = re.compile(
    r"^(?:"
    r"字(?:型|形).*$"
    r"|[字型形度](?:腿|脚|腳|手|开腿|開腿|開腳|蹲|蹲着|蹲著|弯腰|彎腰|躬着|弓着|分开|分開|打开|打開|张开|張開|宽开|寬開).*$"
    r"|.*(?:腿|雙腿|双腿|两腿|兩腿|两条腿|兩條腿|女生腿|女生的腿|女人腿|小腿)(?:呈|成|呈现|呈現).*$"
    r"|(?:双腿|雙腿)(?:呈|大幅|被大大|向两侧|向兩側)?(?:打开|打開|张开|張開|分开|分開|叉开|叉開|抬起|弯曲|彎曲|并拢|並攏).*$"
    r"|(?:高度|[0-9一二三四五六七八九十]+度)(?:弯腰|彎腰|躬着|弓着).*$"
    r")"
)
PROMPT_TOKEN_COMPACT_CJK_OR_HANGUL_KANA_RE = re.compile(
    r"^[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]+$"
)
PROMPT_TOKEN_CJK_PERSON_COUNT_RE = re.compile(r"([一二两俩三四五六七八九十])(?:个|位)(?=[\u3400-\u9fff])")
PROMPT_TOKEN_CJK_COUNT_NORMALIZATION = {
    "一": "一人",
    "二": "两人",
    "两": "两人",
    "俩": "两人",
    "三": "三人",
    "四": "四人",
    "五": "五人",
    "六": "六人",
    "七": "七人",
    "八": "八人",
    "九": "九人",
    "十": "十人",
}
PROMPT_TOKEN_DERIVED_CJK_LEXEMES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?:m|ｍ)\s*(?:字|形|型)\s*(?:腿|开腿|開腿|開腳|打开|打開|张开|張開|姿势|姿勢|样子|樣子|形状|形狀)?"
        ),
        "m字开腿",
    ),
    (re.compile(r"(?:腿|双腿|雙腿|两腿|兩腿|两条腿|兩條腿|大腿与小腿|大腿與小腿)\s*(?:成|呈|呈现|呈現)\s*(?:m|ｍ)\s*(?:字|形|型)?"), "m字开腿"),
    (re.compile(r"字\s*(?:開腳|开腿|開腿)"), "m字开腿"),
    (re.compile(r"(?:双腿|雙腿)\s*(?:成|呈|呈现|呈現)\s*(?:打开|打開|张开|張開|分开|分開|叉开|叉開)"), "双腿分开"),
    (re.compile(r"雙腿(?:大幅|向兩側|被大大)?(?:打開|張開|分開|叉開)"), "双腿分开"),
    (re.compile(r"双腿(?:大幅|向两侧|被大大)?(?:打开|张开|分开|叉开)"), "双腿分开"),
    (re.compile(r"雙腿(?:高高)?抬起"), "双腿抬起"),
    (re.compile(r"双腿(?:高高)?抬起"), "双腿抬起"),
    (re.compile(r"雙腿(?:彎曲|弯曲)"), "双腿弯曲"),
    (re.compile(r"双腿弯曲"), "双腿弯曲"),
    (re.compile(r"雙腿(?:並攏|并拢)"), "双腿并拢"),
    (re.compile(r"双腿并拢"), "双腿并拢"),
    (re.compile(r"(?:高度|[0-9一二三四五六七八九十]+度)?(?:弯腰|彎腰|躬着|弓着)"), "弯腰"),
)
PROMPT_TOKEN_CJK_LEXEME_SOURCE = (
    "一人",
    "两人",
    "俩人",
    "双人",
    "多人",
    "三人",
    "四人",
    "五人",
    "一致",
    "一致性",
    "一致特征",
    "上半身",
    "下半身",
    "不变",
    "不改变",
    "丰满",
    "主体",
    "人物",
    "人物一致",
    "人物姿势",
    "人物相貌",
    "人物脸部",
    "人物轮廓",
    "仙侠",
    "仰视",
    "侧脸",
    "侧面",
    "保持",
    "保持一致",
    "保持不变",
    "保持人物",
    "保持原图",
    "保持发型",
    "保持姿势",
    "保持完整",
    "保持背景",
    "保持脸部",
    "保持角色",
    "全景",
    "全身",
    "全身镜头",
    "光影",
    "光线",
    "光照",
    "内衣",
    "写实",
    "动作",
    "动态",
    "半身",
    "半身照",
    "双手",
    "发丝",
    "发型",
    "发型不变",
    "发色",
    "古风",
    "可爱",
    "后背",
    "周围",
    "嘴唇",
    "四肢",
    "图中",
    "场景",
    "坐姿",
    "复杂",
    "多余",
    "夜景",
    "大腿",
    "头发",
    "头部",
    "女人",
    "女人全身",
    "女性",
    "女性面容",
    "女孩",
    "亚洲人",
    "黑人",
    "白人",
    "姿势",
    "姿势不变",
    "完整",
    "完整保留",
    "室内",
    "少女",
    "局部",
    "左侧",
    "布料",
    "平衡",
    "年轻",
    "开心",
    "微笑",
    "性感",
    "手臂",
    "手部",
    "手指",
    "拍摄",
    "换装",
    "木瓜奶",
    "描述",
    "插入",
    "整体",
    "整体不变",
    "效果",
    "斗篷",
    "方向",
    "无水印",
    "日系",
    "明亮",
    "暗部",
    "服装",
    "服饰",
    "构图",
    "柔和",
    "模糊",
    "正脸",
    "正面",
    "比例",
    "气质",
    "汉服",
    "清晰",
    "清晰度",
    "温柔",
    "漂亮",
    "灰度",
    "照明",
    "照片级",
    "特写",
    "特征",
    "特征一致",
    "环境",
    "现实",
    "真实",
    "眼睛",
    "眼神",
    "短发",
    "礼服",
    "神态",
    "稳定",
    "穿着",
    "站姿",
    "细节",
    "纹理",
    "背景",
    "背景不变",
    "背部",
    "脸型",
    "脸部",
    "脸部特征",
    "自然",
    "自然光",
    "色彩",
    "色调",
    "艺术",
    "视角",
    "角度",
    "角色",
    "设计",
    "轮廓",
    "近景",
    "远景",
    "连贯",
    "透视",
    "造型",
    "道具",
    "阴影",
    "肛门",
    "阴茎",
    "阴部",
    "阴道",
    "阴唇",
    "阴蒂",
    "阴毛",
    "雪景",
    "露出",
    "面容",
    "面部",
    "面部特征",
    "颜色",
    "高清",
    "高跟鞋",
    "高质量",
    "鼻子",
    "弯腰",
    "m字开腿",
    "双腿分开",
    "胸部",
    "胸部自然",
    "腰部",
    "腿部",
    "腹部",
    "臀部",
    "肩部",
    "乳头",
    "乳房",
    "相貌",
    "相貌一致",
    "相貌特征",
    "表情",
    "表情不变",
    "衣服",
    "衣着",
    "裙子",
    "袜子",
    "丝袜",
    "身体",
    "身体比例",
    "身体完整",
    "身材",
    "身材丰满",
    "躯干",
    "镜头",
    "长发",
    "风格",
    "画质",
    "画面真实",
    "原图",
    "原图人物",
    "原图背景",
    "原图构图",
    "原图相貌",
    "原图角色",
    "完全一致",
    "保持原样",
)
PROMPT_TOKEN_CJK_LEXEMES = tuple(
    sorted(set(PROMPT_TOKEN_CJK_LEXEME_SOURCE), key=lambda token: (-len(token), token))
)
PROMPT_TOKEN_MODEL_LABELS = {
    "qwen/YARN_1.0.safetensors": "逼真",
    "qwen/adjust_pussy_anus.safetensors": "菊花+内凹穴",
    "qwen/realistic_texture.safetensors": "真实质感",
    "qwen/flat_chest_hairless.safetensors": "平胸/无毛穴",
    "qwen/penis.safetensors": "扶他(阴茎)",
    "BreastGrow": "巨乳膨胀",
    "BreastInsertion": "乳交",
    "Cum": "颜射",
    "Cunilingus": "舔阴",
    "Flatchested": "平胸",
    "Footjob": "足交",
    "Insertion": "插入优化",
    "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors": "运动逻辑优化",
    "ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors": "全能姿势",
    "ltx2.3/SynthPussy_01_rank32.safetensors": "私处细节",
    "ltx2.3/LTX2.3TITFUCKE2000.safetensors": "乳交",
    "ltx2.3/ltxdeepthroat_v01.safetensors": "深喉/口交",
    "ltx2.3/penile-praxis-general-nsfw-ltx-2-t2v-i2v.safetensors": "男根/多姿势",
    "ltx2.3/pussyjob_v1.1_merged_ltx23.safetensors": "外阴摩擦",
    "ltx2.3/st0mach_bulge_ltx23_v1.1.safetensors": "腹部鼓起",
    "ltx2.3/sfbehind_LTX2_3_v0_1.safetensors": "后入",
    "ltx2.3/nsfw_anal_insertion_ltx23_v1.0.safetensors": "肛交插入",
}
PROMPT_TOKEN_MODEL_ALIASES = {
    "逼真": "qwen/YARN_1.0.safetensors",
    "菊花+内凹穴": "qwen/adjust_pussy_anus.safetensors",
    "真实质感": "qwen/realistic_texture.safetensors",
    "平胸/无毛穴": "qwen/flat_chest_hairless.safetensors",
    "扶他(阴茎)": "qwen/penis.safetensors",
}
PROMPT_TOKEN_TASK_SCOPE_LABELS = {
    "edit": "自由P图",
    "edit_v2": "自由P图 v2",
    "txt2img": "文生图",
    "i2i_pro": "幻想换脸",
    "face_swap": "快速换脸",
    "random_faceswap": "随机换脸",
    "custom_video": "图生视频",
    "wan22_video_v2": "图生视频 v2",
    "ltx_video": "高级图生视频",
    "scail2_action_transfer": "动作迁移",
    "scail2_video_replacement": "视频换人",
    "scail2_face_swap_v2": "视频换脸",
    PROMPT_TOKEN_UNAVAILABLE_TASK: "无可用任务",
}
PROMPT_TOKEN_TASK_SCOPE_ORDER = {
    task_type: index
    for index, task_type in enumerate(
        (
            "edit",
            "edit_v2",
            "txt2img",
            "i2i_pro",
            "face_swap",
            "random_faceswap",
            "custom_video",
            "wan22_video_v2",
            "ltx_video",
            "scail2_action_transfer",
            "scail2_video_replacement",
            "scail2_face_swap_v2",
            PROMPT_TOKEN_UNAVAILABLE_TASK,
        )
    )
}
PROMPT_TOKEN_TASK_SCOPE_ALIASES = {
    "image": "edit",
    "quick_image": "edit",
    "img2img": "edit",
    "img2img_lora": "edit",
    "edit": "edit",
    "pornmaster_flux2_single_edit": "edit_v2",
    "pornmaster_flux2_multi_edit": "edit_v2",
    "free_edit_v2": "edit_v2",
    "txt2img": "txt2img",
    "text_to_image": "txt2img",
    "t2i-pornmaster-turbo": "txt2img",
    "i2i_pro": "i2i_pro",
    "face_swap": "face_swap",
    "faceswap_step1": "face_swap",
    "faceswap_step2": "face_swap",
    "face_swap_step1": "face_swap",
    "face_swap_step2": "face_swap",
    "random_faceswap": "random_faceswap",
    "custom_video": "custom_video",
    "video_lora": "custom_video",
    "image_to_video": "custom_video",
    "image2video": "custom_video",
    "video_insert": "custom_video",
    "video_edit": "custom_video",
    "perfect_video_edit": "custom_video",
    "txt2video": "custom_video",
    "wan22_video_v2": "wan22_video_v2",
    "ltx_video": "ltx_video",
    "ltx_video_flf2v": "ltx_video",
    "ltx_video_v2v_audio": "ltx_video",
    "scail2_action_transfer": "scail2_action_transfer",
    "scail2_action_transfer_long": "scail2_action_transfer",
    "scail2_video_replacement": "scail2_video_replacement",
    "scail2_face_swap_v2": "scail2_face_swap_v2",
    "face_video": "scail2_face_swap_v2",
    "face_video_step1": "scail2_face_swap_v2",
    "face_video_step2": "scail2_face_swap_v2",
}
PROMPT_TOKEN_UNAVAILABLE_TASK_ALIASES = {
    "",
    "unknown",
    "none",
    "i2i_draw",
    "undress",
    "masturbation",
    "penetration",
    "penetration_step1",
    "penetration_step2",
    "perfect_video_insert",
    "doggy_style",
    "blowjob",
    "undress_tongue",
    "closeup_blowjob",
    "video_pro",
    "template_contribute",
}
PROMPT_TOKEN_REFRESH_DROP_INDEX_SQL = (
    "drop index if exists idx_prompt_token_stats_top",
    "drop index if exists idx_prompt_token_stats_token",
    "drop index if exists idx_prompt_token_stats_prompt_sort",
    "drop index if exists idx_prompt_token_stats_use_sort",
    "drop index if exists idx_prompt_token_stats_user_sort",
    "drop index if exists idx_prompt_token_prompts_tokens",
    "drop index if exists idx_prompt_token_prompts_scopes",
    "drop index if exists idx_prompt_token_stats_scope_options",
    "drop index if exists idx_prompt_token_prompts_score",
)
PROMPT_TOKEN_REFRESH_CREATE_INDEX_SQL = (
    (
        "create index if not exists idx_prompt_token_stats_scope_options "
        "on analytics_prompt_token_stats(normalization_version, token_version, scope_kind, parent_task_type, task_type)"
    ),
    (
        "create index if not exists idx_prompt_token_stats_prompt_sort "
        "on analytics_prompt_token_stats(normalization_version, token_version, task_type, prompt_count desc, use_count desc, token)"
    ),
    (
        "create index if not exists idx_prompt_token_prompts_score "
        "on analytics_prompt_token_prompts(normalization_version, token_version, quality_score desc, uses desc)"
    ),
)

PROMPT_TOKEN_ALIAS_SCHEMA_SQL = (
    """
    create table if not exists analytics_prompt_vector_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_token_alias_rules (
        id bigserial primary key,
        representative_token text not null,
        alias_tokens text[] not null default '{}',
        aliases_text text not null default '',
        category_key text not null default '',
        category_label text not null default '',
        subcategory_key text not null default '',
        subcategory_label text not null default '',
        source text not null default '',
        seed_batch text not null default '',
        enabled boolean not null default true,
        sort_order integer not null default 0,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
    )
    """,
    "alter table analytics_prompt_token_alias_rules add column if not exists representative_token text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists alias_tokens text[] not null default '{}'",
    "alter table analytics_prompt_token_alias_rules add column if not exists aliases_text text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists category_key text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists category_label text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists subcategory_key text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists subcategory_label text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists source text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists seed_batch text not null default ''",
    "alter table analytics_prompt_token_alias_rules add column if not exists enabled boolean not null default true",
    "alter table analytics_prompt_token_alias_rules add column if not exists sort_order integer not null default 0",
    "alter table analytics_prompt_token_alias_rules add column if not exists created_at timestamptz not null default now()",
    "alter table analytics_prompt_token_alias_rules add column if not exists updated_at timestamptz not null default now()",
    (
        "create index if not exists idx_prompt_token_alias_rules_enabled "
        "on analytics_prompt_token_alias_rules(enabled, sort_order, id)"
    ),
)

PROMPT_TOKEN_CUSTOM_TERM_SCHEMA_SQL = (
    """
    create table if not exists analytics_prompt_token_custom_terms (
        id bigserial primary key,
        term text not null,
        category_key text not null default '',
        category_label text not null default '',
        subcategory_key text not null default '',
        subcategory_label text not null default '',
        source text not null default '',
        seed_batch text not null default '',
        notes text not null default '',
        enabled boolean not null default true,
        sort_order integer not null default 0,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
    )
    """,
    "alter table analytics_prompt_token_custom_terms add column if not exists term text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists category_key text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists category_label text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists subcategory_key text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists subcategory_label text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists source text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists seed_batch text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists notes text not null default ''",
    "alter table analytics_prompt_token_custom_terms add column if not exists enabled boolean not null default true",
    "alter table analytics_prompt_token_custom_terms add column if not exists sort_order integer not null default 0",
    "alter table analytics_prompt_token_custom_terms add column if not exists created_at timestamptz not null default now()",
    "alter table analytics_prompt_token_custom_terms add column if not exists updated_at timestamptz not null default now()",
    (
        "create index if not exists idx_prompt_token_custom_terms_enabled "
        "on analytics_prompt_token_custom_terms(enabled, sort_order, id)"
    ),
)

PROMPT_TOKEN_EXTRACT_CACHE_SCHEMA_SQL = (
    """
    create table if not exists analytics_prompt_token_extract_cache (
        normalization_version text not null,
        token_version text not null,
        prompt_hash text not null,
        prompt_checksum text not null,
        raw_tokens text[] not null default '{}',
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        primary key (normalization_version, token_version, prompt_hash)
    )
    """,
    "alter table analytics_prompt_token_extract_cache add column if not exists prompt_checksum text not null default ''",
    "alter table analytics_prompt_token_extract_cache add column if not exists raw_tokens text[] not null default '{}'",
    "alter table analytics_prompt_token_extract_cache add column if not exists created_at timestamptz not null default now()",
    "alter table analytics_prompt_token_extract_cache add column if not exists updated_at timestamptz not null default now()",
    (
        "create index if not exists idx_prompt_token_extract_cache_updated "
        "on analytics_prompt_token_extract_cache(updated_at desc)"
    ),
)

PROMPT_TOKEN_DELETION_SCHEMA_SQL = (
    """
    create table if not exists analytics_prompt_token_deleted_rules (
        token text primary key,
        deleted_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
    )
    """,
    "alter table analytics_prompt_token_deleted_rules add column if not exists deleted_at timestamptz not null default now()",
    "alter table analytics_prompt_token_deleted_rules add column if not exists updated_at timestamptz not null default now()",
    (
        "create index if not exists idx_prompt_token_deleted_rules_updated "
        "on analytics_prompt_token_deleted_rules(updated_at desc)"
    ),
)


CREATE_PROMPT_VECTOR_SCHEMA_SQL = [
    """
    create table if not exists analytics_prompt_vector_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    *PROMPT_TOKEN_ALIAS_SCHEMA_SQL,
    *PROMPT_TOKEN_CUSTOM_TERM_SCHEMA_SQL,
    *PROMPT_TOKEN_EXTRACT_CACHE_SCHEMA_SQL,
    *PROMPT_TOKEN_DELETION_SCHEMA_SQL,
    """
    create table if not exists analytics_prompt_embeddings (
        prompt_hash text not null,
        task_type text not null,
        model_id text not null,
        normalization_version text not null,
        prompt text not null,
        prompt_checksum text not null,
        embedding_dim integer not null,
        embedding_dtype text not null default 'float16',
        embedding_f16 bytea,
        status text not null default 'embedded',
        error text,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        embedded_at timestamptz,
        primary key (model_id, normalization_version, prompt_hash)
    )
    """,
    """
    create table if not exists analytics_prompt_token_stats (
        normalization_version text not null,
        token_version text not null,
        task_type text not null,
        token text not null,
        token_kind text not null,
        prompt_count bigint not null default 0,
        use_count bigint not null default 0,
        user_count bigint not null default 0,
        scope_kind text not null default 'task',
        scope_label text,
        parent_task_type text,
        model_key text,
        model_label text,
        refreshed_at timestamptz not null default now(),
        primary key (normalization_version, token_version, task_type, token)
    )
    """,
    """
    create table if not exists analytics_prompt_token_prompts (
        normalization_version text not null,
        token_version text not null,
        prompt_hash text not null,
        prompt text not null,
        tokens text[] not null default '{}',
        task_types text[] not null default '{}',
        scopes text[] not null default '{}',
        scope_uses jsonb not null default '{}'::jsonb,
        scope_users jsonb not null default '{}'::jsonb,
        char_count integer not null default 0,
        uses bigint not null default 0,
        users bigint not null default 0,
        quality_score numeric(20, 2) not null default 0,
        last_seen timestamp,
        refreshed_at timestamptz not null default now(),
        primary key (normalization_version, token_version, prompt_hash)
    )
    """,
    """
    create table if not exists analytics_prompt_token_scope_summary (
        normalization_version text not null,
        token_version text not null,
        task_type text not null,
        candidate_count bigint not null default 0,
        refreshed_at timestamptz not null default now(),
        primary key (normalization_version, token_version, task_type)
    )
    """,
    "create index if not exists idx_prompt_embeddings_task on analytics_prompt_embeddings(model_id, normalization_version, task_type)",
    "create index if not exists idx_prompt_embeddings_status on analytics_prompt_embeddings(status, updated_at desc)",
    (
        "create index if not exists idx_prompt_token_prompts_score "
        "on analytics_prompt_token_prompts(normalization_version, token_version, quality_score desc, uses desc)"
    ),
    "alter table analytics_prompt_embeddings add column if not exists prompt_checksum text not null default ''",
    "alter table analytics_prompt_embeddings add column if not exists embedding_f16 bytea",
    "alter table analytics_prompt_embeddings add column if not exists error text",
    "alter table analytics_prompt_embeddings add column if not exists embedded_at timestamptz",
    "alter table analytics_prompt_token_prompts add column if not exists tokens text[] not null default '{}'",
    "alter table analytics_prompt_token_prompts add column if not exists task_types text[] not null default '{}'",
    "alter table analytics_prompt_token_prompts add column if not exists scopes text[] not null default '{}'",
    "alter table analytics_prompt_token_prompts add column if not exists scope_uses jsonb not null default '{}'::jsonb",
    "alter table analytics_prompt_token_prompts add column if not exists scope_users jsonb not null default '{}'::jsonb",
    "alter table analytics_prompt_token_prompts add column if not exists char_count integer not null default 0",
    "alter table analytics_prompt_token_prompts add column if not exists uses bigint not null default 0",
    "alter table analytics_prompt_token_prompts add column if not exists users bigint not null default 0",
    "alter table analytics_prompt_token_prompts add column if not exists quality_score numeric(20, 2) not null default 0",
    "alter table analytics_prompt_token_prompts add column if not exists last_seen timestamp",
    "alter table analytics_prompt_token_stats add column if not exists scope_kind text not null default 'task'",
    "alter table analytics_prompt_token_stats add column if not exists scope_label text",
    "alter table analytics_prompt_token_stats add column if not exists parent_task_type text",
    "alter table analytics_prompt_token_stats add column if not exists model_key text",
    "alter table analytics_prompt_token_stats add column if not exists model_label text",
    (
        "create index if not exists idx_prompt_token_stats_scope_options "
        "on analytics_prompt_token_stats(normalization_version, token_version, scope_kind, parent_task_type, task_type)"
    ),
    (
        "create index if not exists idx_prompt_token_stats_prompt_sort "
        "on analytics_prompt_token_stats(normalization_version, token_version, task_type, prompt_count desc, use_count desc, token)"
    ),
]


PROMPT_VECTOR_READY_SQL = """
select
    to_regclass('public.analytics_prompt_vector_state') is not null
    and to_regclass('public.analytics_prompt_embeddings') is not null
    as ready
"""


@dataclass(frozen=True)
class PromptVectorConfig:
    model_id: str = DEFAULT_VECTOR_MODEL_ID
    model_key: str = DEFAULT_VECTOR_MODEL_KEY
    base_url: str = DEFAULT_LM_STUDIO_BASE_URL
    batch_size: int = 8
    limit: int | None = None
    task_type: str | None = None
    data_dir: str = DEFAULT_VECTOR_DATA_DIR
    embed_only: bool = False
    tokens_only: bool = False
    skip_token_refresh: bool = False
    skip_lm_check: bool = False


@dataclass(frozen=True)
class CandidatePrompt:
    prompt_hash: str
    task_type: str
    prompt: str


@dataclass(frozen=True)
class PromptTokenAliasRule:
    representative: str
    aliases: tuple[str, ...]
    enabled: bool = True
    sort_order: int = 0
    category_key: str = ""
    category_label: str = ""
    subcategory_key: str = ""
    subcategory_label: str = ""
    source: str = ""
    seed_batch: str = ""


@dataclass(frozen=True)
class PromptTokenCustomTermRule:
    term: str
    enabled: bool = True
    sort_order: int = 0
    category_key: str = ""
    category_label: str = ""
    subcategory_key: str = ""
    subcategory_label: str = ""
    source: str = ""
    seed_batch: str = ""
    notes: str = ""


class LMStudioEmbeddingClient:
    def __init__(self, base_url: str, model_id: str, model_key: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.model_key = model_key
        self.timeout = timeout

    def check_ready(self) -> None:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(_lm_studio_help("LM Studio Server is not reachable")) from exc

        models = payload.get("data") or []
        model_ids = {str(model.get("id") or "") for model in models if isinstance(model, dict)}
        if self.model_id not in model_ids and self.model_key not in model_ids:
            raise RuntimeError(_lm_studio_help(f"embedding model is not loaded: {self.model_id}"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model_id, "input": texts}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LM Studio embedding request failed: HTTP {exc.code} {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(_lm_studio_help("LM Studio embedding request failed")) from exc

        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise RuntimeError("LM Studio embedding response shape is invalid")
        vectors = []
        for item in sorted(data, key=lambda row: row.get("index", 0)):
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise RuntimeError("LM Studio embedding response contains an empty vector")
            vectors.append(vector)
        return vectors


def _lm_studio_help(reason: str) -> str:
    return (
        f"{reason}; start and load the local embedding model first: "
        "lms server start && "
        f"lms load {DEFAULT_VECTOR_MODEL_KEY} --identifier {DEFAULT_VECTOR_MODEL_ID} --gpu max -y"
    )


def _vector_state_key(model_id: str, normalization_version: str, key: str) -> str:
    return f"{model_id}:{normalization_version}:{key}"


def prompt_token_vector_state_key(key: str) -> str:
    return _vector_state_key(DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION, key)


def prompt_token_cache_checksum(prompt: str | None) -> str:
    return hashlib.md5((prompt or "").encode("utf-8")).hexdigest()


def _normalize_prompt_for_tokens(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.translate(PROMPT_ZERO_WIDTH_TRANSLATION)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc")
    text = PROMPT_LEADING_METADATA_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_cjk_token(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def _is_hangul_or_kana_token(value: str) -> bool:
    return any(
        ("\u3040" <= char <= "\u30ff")
        or ("\uac00" <= char <= "\ud7af")
        for char in value
    )


def _token_kind(value: str) -> str:
    if _is_cjk_token(value):
        return "cjk"
    if _is_hangul_or_kana_token(value):
        return "unicode"
    if any(char.isalpha() for char in value) and any(char.isdigit() for char in value):
        return "mixed"
    return "latin"


def prompt_token_task_scope_key(task_type: str | None) -> str:
    normalized = (task_type or "").strip()
    if normalized in PROMPT_TOKEN_TASK_SCOPE_LABELS:
        return normalized
    if normalized in PROMPT_TOKEN_TASK_SCOPE_ALIASES:
        return PROMPT_TOKEN_TASK_SCOPE_ALIASES[normalized]
    if normalized in PROMPT_TOKEN_UNAVAILABLE_TASK_ALIASES:
        return PROMPT_TOKEN_UNAVAILABLE_TASK
    return PROMPT_TOKEN_UNAVAILABLE_TASK


def prompt_token_task_label(task_type: str | None) -> str:
    scope_key = prompt_token_task_scope_key(task_type)
    return PROMPT_TOKEN_TASK_SCOPE_LABELS.get(scope_key, scope_key)


def prompt_token_task_sort_order(task_type: str | None) -> int:
    scope_key = prompt_token_task_scope_key(task_type)
    return PROMPT_TOKEN_TASK_SCOPE_ORDER.get(scope_key, 10_000)


def prompt_token_model_scope_key(task_type: str, model_key: str) -> str:
    return f"{PROMPT_TOKEN_MODEL_SCOPE_PREFIX}{prompt_token_task_scope_key(task_type)}|{model_key}"


def prompt_token_normalize_model_key(model_tag: str | None) -> str | None:
    normalized = (model_tag or "").strip()
    if not normalized:
        return None
    return PROMPT_TOKEN_MODEL_ALIASES.get(normalized, normalized)


def prompt_token_model_label(model_key: str | None) -> str:
    normalized = (model_key or "").strip()
    if not normalized:
        return ""
    return PROMPT_TOKEN_MODEL_LABELS.get(normalized, normalized)


def prompt_token_scope_label(scope_key: str, *, task_type: str | None = None, model_key: str | None = None) -> str:
    if scope_key == PROMPT_TOKEN_ALL_TASK:
        return "全部词元"
    if model_key:
        task_label = prompt_token_task_label(task_type)
        model_label = prompt_token_model_label(model_key)
        return f"{task_label} / {model_label}" if task_label else model_label
    return prompt_token_task_label(task_type or scope_key)


def prompt_token_stat_scope_metadata(scope_key: str) -> tuple[str, str, str | None, str | None, str | None]:
    if scope_key == PROMPT_TOKEN_ALL_TASK:
        return ("all", "全部词元", None, None, None)
    if scope_key.startswith(PROMPT_TOKEN_MODEL_SCOPE_PREFIX):
        rest = scope_key[len(PROMPT_TOKEN_MODEL_SCOPE_PREFIX) :]
        task_type, separator, model_key = rest.partition("|")
        if separator and task_type and model_key:
            model_label = prompt_token_model_label(model_key)
            return ("model", model_label, task_type, model_key, model_label)
    scope_label = prompt_token_task_label(scope_key)
    return ("task", scope_label, prompt_token_task_scope_key(scope_key), None, None)


def _valid_cjk_prompt_token(value: str) -> bool:
    if value in PROMPT_TOKEN_CJK_GRAMMAR_FRAGMENTS:
        return False
    if value in PROMPT_TOKEN_DERIVED_CANONICAL_CJK_TOKENS:
        return True
    if PROMPT_TOKEN_CJK_FRAGMENT_NOISE_RE.match(value):
        return False
    if len(value) <= 4 and value.endswith(("的", "地", "得")):
        return False
    if len(value) <= 4 and value.startswith(("的", "之")):
        return False
    if "的" in value and len(value) <= 4:
        return False
    return True


def _valid_prompt_token(value: str) -> bool:
    token = value.strip("_+.-")
    if token != value or not token:
        return False
    if token in PROMPT_TOKEN_STOPWORDS:
        return False
    if token.isdigit():
        return False
    if _is_cjk_token(token):
        return len(token) >= 2 and _valid_cjk_prompt_token(token)
    if _is_hangul_or_kana_token(token):
        return len(token) >= 2
    return len(token) >= 3


def _valid_manual_prompt_token(value: str) -> bool:
    token = value.strip("_+.-")
    if token != value or not token:
        return False
    if token in PROMPT_TOKEN_STOPWORDS:
        return False
    if token.isdigit():
        return False
    if _is_cjk_token(token):
        return token not in PROMPT_TOKEN_CJK_GRAMMAR_FRAGMENTS
    if _is_hangul_or_kana_token(token):
        return len(token) >= 2
    return len(token) >= 3


def normalize_prompt_token_alias_value(value: str | None) -> str:
    token = _normalize_prompt_for_tokens(value).strip("_+.-")
    return token.strip()


def split_prompt_token_aliases(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        parts: Iterable[str] = ()
    elif isinstance(value, str):
        parts = PROMPT_TOKEN_ALIAS_SPLIT_RE.split(value)
    else:
        parts = value
    aliases: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = normalize_prompt_token_alias_value(str(part))
        if not token or token in seen:
            continue
        seen.add(token)
        aliases.append(token)
    return aliases


def _alias_row_value(row: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = _record_get(row, key, default)
        if value is not default:
            return value
    return default


def _rule_metadata_value(row: Any, key: str) -> str:
    return str(_alias_row_value(row, key, default="") or "").strip()


def validate_prompt_token_alias_rules(rows: Iterable[Any]) -> list[PromptTokenAliasRule]:
    rules: list[PromptTokenAliasRule] = []
    representatives: dict[str, int] = {}
    for index, row in enumerate(rows):
        representative = normalize_prompt_token_alias_value(
            _alias_row_value(row, "representative", "representative_token", default="")
        )
        aliases_value = _alias_row_value(row, "aliases", "alias_tokens", default=None)
        aliases_text = _alias_row_value(row, "aliases_text", default="")
        aliases = split_prompt_token_aliases(aliases_value if aliases_value is not None else aliases_text)
        if not representative and not aliases:
            continue
        if not representative:
            raise ValueError(f"第 {index + 1} 行缺少代表词元")
        if not _valid_manual_prompt_token(representative):
            raise ValueError(f"代表词元无效: {representative}")
        if representative in representatives:
            raise ValueError(f"代表词元重复: {representative}")
        representatives[representative] = index + 1
        clean_aliases: list[str] = []
        for alias in aliases:
            if alias == representative:
                continue
            if not _valid_manual_prompt_token(alias):
                raise ValueError(f"同义词元无效: {alias}")
            clean_aliases.append(alias)
        rules.append(
            PromptTokenAliasRule(
                representative=representative,
                aliases=tuple(clean_aliases),
                enabled=bool(_alias_row_value(row, "enabled", default=True)),
                sort_order=int(_alias_row_value(row, "sort_order", default=len(rules))),
                category_key=_rule_metadata_value(row, "category_key"),
                category_label=_rule_metadata_value(row, "category_label"),
                subcategory_key=_rule_metadata_value(row, "subcategory_key"),
                subcategory_label=_rule_metadata_value(row, "subcategory_label"),
                source=_rule_metadata_value(row, "source"),
                seed_batch=_rule_metadata_value(row, "seed_batch"),
            )
        )

    alias_owner: dict[str, str] = {}
    representative_set = set(representatives)
    for rule in rules:
        if not rule.enabled:
            continue
        for alias in rule.aliases:
            if alias in representative_set:
                raise ValueError(f"同义词元不能同时作为代表词元: {alias}")
            owner = alias_owner.get(alias)
            if owner and owner != rule.representative:
                raise ValueError(f"同义词元重复映射: {alias}")
            alias_owner[alias] = rule.representative
    return rules


def build_prompt_token_alias_map(rules: Iterable[PromptTokenAliasRule]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for rule in rules:
        if not rule.enabled:
            continue
        for alias in rule.aliases:
            alias_map[alias] = rule.representative
    return alias_map


def apply_prompt_token_aliases(tokens: Iterable[str], alias_map: dict[str, str]) -> list[str]:
    mapped_tokens: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        mapped = alias_map.get(token, token)
        if mapped in seen:
            continue
        seen.add(mapped)
        mapped_tokens.append(mapped)
    return mapped_tokens


def validate_prompt_token_custom_terms(rows: Iterable[Any]) -> list[PromptTokenCustomTermRule]:
    rules: list[PromptTokenCustomTermRule] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        raw_term = _alias_row_value(row, "term", "token", "custom_term", default="")
        terms = split_prompt_token_aliases(raw_term)
        if not terms:
            continue
        for term in terms:
            if not _valid_manual_prompt_token(term):
                raise ValueError(f"指定词元无效: {term}")
            if term in seen:
                continue
            seen.add(term)
            rules.append(
                PromptTokenCustomTermRule(
                    term=term,
                    enabled=bool(_alias_row_value(row, "enabled", default=True)),
                    sort_order=int(_alias_row_value(row, "sort_order", default=index)),
                    category_key=_rule_metadata_value(row, "category_key"),
                    category_label=_rule_metadata_value(row, "category_label"),
                    subcategory_key=_rule_metadata_value(row, "subcategory_key"),
                    subcategory_label=_rule_metadata_value(row, "subcategory_label"),
                    source=_rule_metadata_value(row, "source"),
                    seed_batch=_rule_metadata_value(row, "seed_batch"),
                    notes=_rule_metadata_value(row, "notes"),
                )
            )
    return rules


def _prompt_contains_custom_term(normalized_prompt: str, term: str) -> bool:
    if _is_cjk_token(term):
        return term in normalized_prompt
    pattern = rf"(?<![a-z0-9_+.-]){re.escape(term)}(?![a-z0-9_+.-])"
    return re.search(pattern, normalized_prompt) is not None


@dataclass(frozen=True)
class PromptTokenCustomTermMatcher:
    rules: tuple[PromptTokenCustomTermRule, ...]
    term_set: frozenset[str]
    cjk_buckets: dict[str, tuple[tuple[int, str], ...]]
    latin_rules: tuple[tuple[int, str, re.Pattern[str]], ...]

    @classmethod
    def from_rules(cls, custom_terms: Iterable[PromptTokenCustomTermRule]) -> "PromptTokenCustomTermMatcher":
        rules = tuple(rule for rule in custom_terms if rule.enabled)
        cjk_buckets: dict[str, list[tuple[int, str]]] = {}
        latin_rules: list[tuple[int, str, re.Pattern[str]]] = []
        for index, rule in enumerate(rules):
            term = rule.term
            if _is_cjk_token(term) or _is_hangul_or_kana_token(term):
                cjk_buckets.setdefault(term[0], []).append((index, term))
                continue
            pattern = re.compile(rf"(?<![a-z0-9_+.-]){re.escape(term)}(?![a-z0-9_+.-])")
            latin_rules.append((index, term, pattern))
        return cls(
            rules=rules,
            term_set=frozenset(rule.term for rule in rules),
            cjk_buckets={key: tuple(value) for key, value in cjk_buckets.items()},
            latin_rules=tuple(latin_rules),
        )

    def matching_terms(self, normalized_prompt: str, seen: set[str], limit: int) -> list[str]:
        if limit <= 0 or not normalized_prompt:
            return []
        matched: list[tuple[int, str]] = []
        cjk_candidates: dict[int, str] = {}
        for char in set(normalized_prompt):
            for index, term in self.cjk_buckets.get(char, ()):
                cjk_candidates[index] = term
        for index, term in cjk_candidates.items():
            if term in seen or term not in normalized_prompt:
                continue
            matched.append((index, term))
        for index, term, pattern in self.latin_rules:
            if term in seen or term not in normalized_prompt:
                continue
            if pattern.search(normalized_prompt) is not None:
                matched.append((index, term))
        matched.sort(key=lambda item: item[0])
        return [term for _index, term in matched[:limit]]


def build_prompt_token_custom_term_matcher(
    custom_terms: Iterable[PromptTokenCustomTermRule],
) -> PromptTokenCustomTermMatcher:
    return PromptTokenCustomTermMatcher.from_rules(custom_terms)


def _prompt_token_decomposes_to_terms(token: str, available_terms: set[str], explicit_terms: set[str]) -> bool:
    if token in explicit_terms:
        return False
    if not PROMPT_TOKEN_COMPACT_CJK_OR_HANGUL_KANA_RE.match(token):
        return False
    for term in available_terms:
        if term == token or len(term) < 2:
            continue
        if not PROMPT_TOKEN_COMPACT_CJK_OR_HANGUL_KANA_RE.match(term):
            continue
        if term in token:
            return True
    return False


def _drop_decomposed_prompt_tokens(
    tokens: Iterable[str],
    *,
    explicit_terms: set[str],
) -> list[str]:
    token_list = list(tokens)
    available_terms = set(token_list)
    return [
        token
        for token in token_list
        if not _prompt_token_decomposes_to_terms(token, available_terms, explicit_terms)
    ]


def apply_prompt_token_custom_terms(
    tokens: Iterable[str],
    prompt: str | None,
    custom_terms: Iterable[PromptTokenCustomTermRule] | PromptTokenCustomTermMatcher,
    *,
    max_tokens: int = PROMPT_TOKEN_MAX_PER_PROMPT,
) -> list[str]:
    matcher = (
        custom_terms
        if isinstance(custom_terms, PromptTokenCustomTermMatcher)
        else build_prompt_token_custom_term_matcher(custom_terms)
    )
    custom_term_set = set(matcher.term_set)
    merged: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        merged.append(token)
    if len(merged) >= max_tokens:
        return _drop_decomposed_prompt_tokens(merged[:max_tokens], explicit_terms=custom_term_set)

    normalized_prompt = _normalize_prompt_for_tokens(prompt)
    for term in matcher.matching_terms(normalized_prompt, seen, max_tokens - len(merged)):
        seen.add(term)
        merged.append(term)
        if len(merged) >= max_tokens:
            break
    return _drop_decomposed_prompt_tokens(merged, explicit_terms=custom_term_set)


def _extract_cjk_lexeme_tokens(chunk: str) -> list[str]:
    matches: list[tuple[int, int, str]] = []
    for match in PROMPT_TOKEN_CJK_PERSON_COUNT_RE.finditer(chunk):
        count_token = PROMPT_TOKEN_CJK_COUNT_NORMALIZATION.get(match.group(1))
        if count_token:
            matches.append((match.start(), -len(count_token), count_token))
    for lexeme in PROMPT_TOKEN_CJK_LEXEMES:
        start = chunk.find(lexeme)
        if start >= 0:
            matches.append((start, -len(lexeme), lexeme))
    matches.sort()
    return [token for _start, _negative_length, token in matches]


def extract_prompt_tokens(prompt: str | None, *, max_tokens: int = PROMPT_TOKEN_MAX_PER_PROMPT) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        if len(tokens) >= max_tokens:
            return
        if not _valid_prompt_token(token) or token in seen:
            return
        seen.add(token)
        tokens.append(token)

    text = _normalize_prompt_for_tokens(prompt)
    for pattern, token in PROMPT_TOKEN_DERIVED_CJK_LEXEMES:
        if pattern.search(text):
            add(token)
    for match in PROMPT_TOKEN_CHUNK_RE.finditer(text):
        chunk = match.group(0)
        if _is_cjk_token(chunk):
            lexeme_tokens = _extract_cjk_lexeme_tokens(chunk)
            if len(chunk) <= 8 and not lexeme_tokens:
                add(chunk)
            for token in lexeme_tokens:
                add(token)
        else:
            for part in PROMPT_TOKEN_SEPARATOR_RE.split(chunk):
                add(part)
    return tokens


async def ensure_prompt_vector_schema(conn: Any) -> None:
    for statement in CREATE_PROMPT_VECTOR_SCHEMA_SQL:
        await conn.execute(statement)


async def set_vector_state(conn: Any, model_id: str, normalization_version: str, values: dict[str, Any]) -> None:
    for key, value in values.items():
        await conn.execute(
            """
            insert into analytics_prompt_vector_state (key, value, updated_at)
            values ($1::text, $2::text, now())
            on conflict (key) do update set value = excluded.value, updated_at = now()
            """,
            _vector_state_key(model_id, normalization_version, key),
            json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value,
        )


def normalize_embedding(vector: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(vector), dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("embedding norm is zero")
    return (array / norm).astype(np.float16)


def embedding_to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float16).tobytes()


def embedding_from_bytes(raw: bytes | memoryview, dim: int) -> np.ndarray:
    vector = np.frombuffer(bytes(raw), dtype=np.float16)
    if vector.size != dim:
        raise ValueError(f"embedding dimension mismatch: expected {dim}, got {vector.size}")
    return vector


async def _candidate_count(conn: Any, task_type: str | None = None) -> int:
    return int(
        await conn.fetchval(
            """
            select count(*)::bigint
            from analytics_prompt_slim_candidates
            where quality_stage = 'candidate'
              and normalization_version = $1::text
              and ($2::text is null or $2::text = any(task_types))
            """,
            PROMPT_NORMALIZATION_VERSION,
            task_type,
        )
        or 0
    )


async def _embedded_count(conn: Any, model_id: str, task_type: str | None = None) -> int:
    return int(
        await conn.fetchval(
            """
            select count(*)::bigint
            from analytics_prompt_embeddings
            where model_id = $1::text
              and normalization_version = $2::text
              and status = 'embedded'
              and ($3::text is null or task_type = $3::text)
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            task_type,
        )
        or 0
    )


async def _insert_records(
    conn: Any,
    *,
    table_name: str,
    columns: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> None:
    if not rows:
        return
    records = list(rows)
    copy_records = getattr(conn, "copy_records_to_table", None)
    if copy_records is not None:
        await copy_records(table_name, records=records, columns=columns)
        return
    placeholders = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
    await conn.executemany(
        f"""
        insert into {table_name} ({", ".join(columns)}, refreshed_at)
        values ({placeholders}, now())
        """,
        records,
    )


async def _upsert_prompt_token_extract_cache(conn: Any, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    await conn.executemany(
        f"""
        insert into analytics_prompt_token_extract_cache ({", ".join(PROMPT_TOKEN_EXTRACT_CACHE_COLUMNS)})
        values ($1, $2, $3, $4, $5)
        on conflict (normalization_version, token_version, prompt_hash) do update set
            prompt_checksum = excluded.prompt_checksum,
            raw_tokens = excluded.raw_tokens,
            updated_at = now()
        """,
        rows,
    )


def _record_get(record: Any, key: str, default: Any = None) -> Any:
    getter = getattr(record, "get", None)
    if getter is not None:
        return getter(key, default)
    if hasattr(record, key):
        return getattr(record, key)
    try:
        return record[key]
    except (KeyError, TypeError):
        return default


async def fetch_prompt_token_alias_rules(conn: Any) -> list[PromptTokenAliasRule]:
    rows = await conn.fetch(
        """
        select
            representative_token,
            alias_tokens,
            enabled,
            sort_order,
            category_key,
            category_label,
            subcategory_key,
            subcategory_label,
            source,
            seed_batch
        from analytics_prompt_token_alias_rules
        where enabled is true
        order by sort_order, id
        """
    )
    return validate_prompt_token_alias_rules(rows)


async def fetch_prompt_token_custom_terms(conn: Any) -> list[PromptTokenCustomTermRule]:
    rows = await conn.fetch(
        """
        select
            term,
            enabled,
            sort_order,
            category_key,
            category_label,
            subcategory_key,
            subcategory_label,
            source,
            seed_batch,
            notes
        from analytics_prompt_token_custom_terms
        where enabled is true
        order by sort_order, id
        """
    )
    return validate_prompt_token_custom_terms(rows)


async def _refresh_prompt_token_stats_unindexed(
    conn: Any,
    *,
    top_per_task: int = PROMPT_TOKEN_TOP_PER_TASK,
    batch_size: int = PROMPT_TOKEN_BATCH_SIZE,
) -> dict[str, Any]:
    started = time.monotonic()
    phase_seconds: dict[str, Any] = {}
    prompt_counts: Counter[tuple[str, str]] = Counter()
    use_counts: Counter[tuple[str, str]] = Counter()
    user_counts: Counter[tuple[str, str]] = Counter()
    scope_prompt_counts: Counter[str] = Counter()
    token_kind: dict[str, str] = {}
    scanned = 0
    last_prompt_hash = ""
    prompt_rows: list[tuple[Any, ...]] = []
    _ = top_per_task
    phase_started = time.monotonic()
    alias_rules = await fetch_prompt_token_alias_rules(conn)
    alias_map = build_prompt_token_alias_map(alias_rules)
    custom_terms = await fetch_prompt_token_custom_terms(conn)
    custom_term_matcher = build_prompt_token_custom_term_matcher(custom_terms)
    phase_seconds["load_rules"] = round(time.monotonic() - phase_started, 2)
    cache_hits = 0
    cache_misses = 0

    phase_started = time.monotonic()
    await conn.execute(
        """
        delete from analytics_prompt_token_prompts
        where normalization_version = $1::text
          and token_version = $2::text
        """,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
    )
    phase_seconds["delete_prompt_rows"] = round(time.monotonic() - phase_started, 2)

    phase_started = time.monotonic()
    while True:
        rows = await conn.fetch(
            """
            select prompt_hash, prompt, char_count, uses, users, task_types, quality_score, last_seen
            from analytics_prompt_slim_candidates
            where quality_stage = 'candidate'
              and normalization_version = $1::text
              and prompt_hash > $2::text
            order by prompt_hash
            limit $3::int
            """,
            PROMPT_NORMALIZATION_VERSION,
            last_prompt_hash,
            max(1, int(batch_size)),
        )
        if not rows:
            break
        prompt_hashes = [str(row["prompt_hash"]) for row in rows]
        prompt_checksums = {
            str(row["prompt_hash"]): prompt_token_cache_checksum(row["prompt"] or "")
            for row in rows
        }
        cache_rows = await conn.fetch(
            """
            select prompt_hash, prompt_checksum, raw_tokens
            from analytics_prompt_token_extract_cache
            where normalization_version = $1::text
              and token_version = $2::text
              and prompt_hash = any($3::text[])
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            prompt_hashes,
        )
        raw_tokens_by_prompt: dict[str, list[str]] = {}
        for cache_row in cache_rows:
            prompt_hash = str(cache_row["prompt_hash"])
            if str(cache_row["prompt_checksum"] or "") != prompt_checksums.get(prompt_hash):
                continue
            raw_tokens_by_prompt[prompt_hash] = [str(token) for token in (cache_row["raw_tokens"] or [])]
        occurrence_scope_rows = await conn.fetch(
            """
            with occurrence_scopes as (
                select
                    prompt_hash,
                    coalesce(task_type, 'unknown') as task_type,
                    nullif(
                        btrim(
                            substring(
                                coalesce(raw_prompt, prompt, '')
                                from '^\\[模型:\\s*([^\\]]+)\\]'
                            )
                        ),
                        ''
                    ) as model_tag,
                    user_id
                from analytics_prompt_occurrence
                where prompt_hash = any($1::text[])
                  and allow_contribute is distinct from false
                  and builtin_template_key is null
            )
            select
                prompt_hash,
                task_type,
                case when grouping(model_tag) = 1 then null else model_tag end as model_tag,
                (grouping(model_tag) = 1) as task_scope,
                count(*)::bigint as uses,
                count(distinct user_id)::bigint as users
            from occurrence_scopes
            group by grouping sets (
                (prompt_hash, task_type),
                (prompt_hash, task_type, model_tag)
            )
            """,
            prompt_hashes,
        )
        scope_data_by_prompt: dict[str, dict[str, Any]] = {
            prompt_hash: {"scopes": set(), "uses": Counter(), "users": Counter()}
            for prompt_hash in prompt_hashes
        }
        for scope_row in occurrence_scope_rows:
            prompt_hash = str(scope_row["prompt_hash"])
            task_type = prompt_token_task_scope_key(str(scope_row["task_type"] or "unknown"))
            data = scope_data_by_prompt.setdefault(prompt_hash, {"scopes": set(), "uses": Counter(), "users": Counter()})
            uses = int(scope_row["uses"] or 0)
            users = int(scope_row["users"] or 0)
            if bool(_record_get(scope_row, "task_scope")):
                scope_key = task_type
            else:
                model_key = prompt_token_normalize_model_key(_record_get(scope_row, "model_tag"))
                if not model_key:
                    continue
                scope_key = prompt_token_model_scope_key(task_type, model_key)
            data["scopes"].add(scope_key)
            data["uses"][scope_key] += uses
            data["users"][scope_key] += users
        cache_upsert_rows: list[tuple[Any, ...]] = []
        for row in rows:
            scanned += 1
            last_prompt_hash = str(row["prompt_hash"])
            raw_tokens = raw_tokens_by_prompt.get(last_prompt_hash)
            if raw_tokens is None:
                cache_misses += 1
                raw_tokens = extract_prompt_tokens(row["prompt"])
                cache_upsert_rows.append(
                    (
                        PROMPT_NORMALIZATION_VERSION,
                        PROMPT_TOKEN_VERSION,
                        last_prompt_hash,
                        prompt_checksums[last_prompt_hash],
                        raw_tokens,
                    )
                )
            else:
                cache_hits += 1
            raw_tokens = apply_prompt_token_custom_terms(raw_tokens, row["prompt"], custom_term_matcher)
            tokens = apply_prompt_token_aliases(raw_tokens, alias_map)
            if not tokens:
                continue
            task_types = [str(task) for task in (row["task_types"] or []) if str(task or "").strip()]
            uses = int(row["uses"] or 0)
            users = int(row["users"] or 0)
            prompt_scope_data = scope_data_by_prompt.get(last_prompt_hash) or {
                "scopes": set(),
                "uses": Counter(),
                "users": Counter(),
            }
            prompt_scopes: set[str] = set(prompt_scope_data["scopes"])
            scope_uses: Counter[str] = Counter(prompt_scope_data["uses"])
            scope_users: Counter[str] = Counter(prompt_scope_data["users"])
            prompt_scopes.add(PROMPT_TOKEN_ALL_TASK)
            scope_uses[PROMPT_TOKEN_ALL_TASK] = uses
            scope_users[PROMPT_TOKEN_ALL_TASK] = users
            for task_type in task_types or ["unknown"]:
                task_scope_key = prompt_token_task_scope_key(task_type)
                prompt_scopes.add(task_scope_key)
                if task_scope_key not in scope_uses:
                    scope_uses[task_scope_key] = uses
                if task_scope_key not in scope_users:
                    scope_users[task_scope_key] = users
            ordered_scopes = [
                PROMPT_TOKEN_ALL_TASK,
                *sorted(scope for scope in prompt_scopes if scope != PROMPT_TOKEN_ALL_TASK),
            ]
            scope_prompt_counts.update(ordered_scopes)
            prompt_rows.append(
                (
                    PROMPT_NORMALIZATION_VERSION,
                    PROMPT_TOKEN_VERSION,
                    str(row["prompt_hash"]),
                    row["prompt"] or "",
                    tokens,
                    task_types,
                    ordered_scopes,
                    json.dumps({scope: int(scope_uses.get(scope, 0)) for scope in ordered_scopes}, ensure_ascii=False),
                    json.dumps({scope: int(scope_users.get(scope, 0)) for scope in ordered_scopes}, ensure_ascii=False),
                    int(row["char_count"] or 0),
                    uses,
                    users,
                    row["quality_score"] or 0,
                    row["last_seen"],
                )
            )
            if len(prompt_rows) >= PROMPT_TOKEN_INSERT_BATCH_SIZE:
                await _insert_records(
                    conn,
                    table_name="analytics_prompt_token_prompts",
                    columns=PROMPT_TOKEN_PROMPT_COPY_COLUMNS,
                    rows=prompt_rows,
                )
                prompt_rows.clear()
            for token in tokens:
                token_kind.setdefault(token, _token_kind(token))
                for scope in ordered_scopes:
                    key = (scope, token)
                    prompt_counts[key] += 1
                    use_counts[key] += int(scope_uses.get(scope, 0))
                    user_counts[key] += int(scope_users.get(scope, 0))
        await _upsert_prompt_token_extract_cache(conn, cache_upsert_rows)
    if prompt_rows:
        await _insert_records(
            conn,
            table_name="analytics_prompt_token_prompts",
            columns=PROMPT_TOKEN_PROMPT_COPY_COLUMNS,
            rows=prompt_rows,
        )
        prompt_rows.clear()
    phase_seconds["scan_prompts"] = round(time.monotonic() - phase_started, 2)

    selected_keys = sorted(prompt_counts.keys())

    phase_started = time.monotonic()
    await conn.execute(
        """
        delete from analytics_prompt_token_stats
        where normalization_version = $1::text
          and token_version = $2::text
        """,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
    )
    await conn.execute(
        """
        delete from analytics_prompt_token_scope_summary
        where normalization_version = $1::text
          and token_version = $2::text
        """,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
    )
    inserted_stats = 0
    stat_rows: list[tuple[Any, ...]] = []
    for scope, token in selected_keys:
        scope_kind, scope_label, parent_task_type, model_key, model_label = prompt_token_stat_scope_metadata(scope)
        stat_rows.append(
            (
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_TOKEN_VERSION,
                scope,
                token,
                token_kind.get(token, "latin"),
                int(prompt_counts[(scope, token)]),
                int(use_counts[(scope, token)]),
                int(user_counts[(scope, token)]),
                scope_kind,
                scope_label,
                parent_task_type,
                model_key,
                model_label,
            )
        )
        if len(stat_rows) >= PROMPT_TOKEN_INSERT_BATCH_SIZE:
            await _insert_records(
                conn,
                table_name="analytics_prompt_token_stats",
                columns=PROMPT_TOKEN_STAT_COPY_COLUMNS,
                rows=stat_rows,
            )
            inserted_stats += len(stat_rows)
            stat_rows.clear()
    if stat_rows:
        await _insert_records(
            conn,
            table_name="analytics_prompt_token_stats",
            columns=PROMPT_TOKEN_STAT_COPY_COLUMNS,
            rows=stat_rows,
        )
        inserted_stats += len(stat_rows)
    summary_rows = [
        (
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope,
            int(count),
        )
        for scope, count in sorted(scope_prompt_counts.items())
    ]
    await _insert_records(
        conn,
        table_name="analytics_prompt_token_scope_summary",
        columns=PROMPT_TOKEN_SCOPE_SUMMARY_COPY_COLUMNS,
        rows=summary_rows,
    )
    phase_seconds["write_stats"] = round(time.monotonic() - phase_started, 2)
    phase_started = time.monotonic()
    await conn.execute("analyze analytics_prompt_token_stats")
    await conn.execute("analyze analytics_prompt_token_prompts")
    await conn.execute("analyze analytics_prompt_token_scope_summary")
    phase_seconds["analyze"] = round(time.monotonic() - phase_started, 2)
    await set_vector_state(
        conn,
        DEFAULT_VECTOR_MODEL_ID,
        PROMPT_NORMALIZATION_VERSION,
        {
            "prompt_token_alias_applied_at": datetime.now(timezone.utc).isoformat(),
            "prompt_token_alias_rule_count": len(alias_rules),
            "prompt_token_alias_map_count": len(alias_map),
            "prompt_token_custom_terms_applied_at": datetime.now(timezone.utc).isoformat(),
            "prompt_token_custom_term_count": len(custom_terms),
            "prompt_token_extract_cache_hits": cache_hits,
            "prompt_token_extract_cache_misses": cache_misses,
        },
    )
    return {
        "prompt_count": scanned,
        "token_count": len({token for _scope, token in prompt_counts.keys()}),
        "stored_rows": inserted_stats,
        "token_version": PROMPT_TOKEN_VERSION,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "phase_seconds": phase_seconds,
        "seconds": round(time.monotonic() - started, 2),
    }


def _index_name_from_create_statement(statement: str) -> str:
    match = re.search(r"create\s+index\s+(?:if\s+not\s+exists\s+)?([^\s]+)", statement, re.IGNORECASE)
    if match:
        return match.group(1)
    return statement.strip().split(maxsplit=4)[-1][:80]


async def _apply_prompt_token_index_build_settings(conn: Any) -> None:
    if PROMPT_TOKEN_INDEX_MAINTENANCE_WORK_MEM:
        await conn.execute(
            "select set_config('maintenance_work_mem', $1::text, false)",
            PROMPT_TOKEN_INDEX_MAINTENANCE_WORK_MEM,
        )
    if PROMPT_TOKEN_INDEX_MAX_PARALLEL_WORKERS:
        await conn.execute(
            "select set_config('max_parallel_maintenance_workers', $1::text, false)",
            PROMPT_TOKEN_INDEX_MAX_PARALLEL_WORKERS,
        )


async def refresh_prompt_token_stats(
    conn: Any,
    *,
    top_per_task: int = PROMPT_TOKEN_TOP_PER_TASK,
    batch_size: int = PROMPT_TOKEN_BATCH_SIZE,
) -> dict[str, Any]:
    started = time.monotonic()
    drop_started = time.monotonic()
    for statement in PROMPT_TOKEN_REFRESH_DROP_INDEX_SQL:
        await conn.execute(statement)
    drop_index_seconds = round(time.monotonic() - drop_started, 2)
    status: dict[str, Any] | None = None
    try:
        status = await _refresh_prompt_token_stats_unindexed(
            conn,
            top_per_task=top_per_task,
            batch_size=batch_size,
        )
        return status
    finally:
        create_started = time.monotonic()
        index_seconds: dict[str, float] = {}
        await _apply_prompt_token_index_build_settings(conn)
        for statement in PROMPT_TOKEN_REFRESH_CREATE_INDEX_SQL:
            index_name = _index_name_from_create_statement(statement)
            index_started = time.monotonic()
            await conn.execute(statement)
            index_seconds[index_name] = round(time.monotonic() - index_started, 2)
        if status is not None:
            phase_seconds = dict(status.get("phase_seconds") or {})
            phase_seconds["drop_indexes"] = drop_index_seconds
            phase_seconds["create_indexes"] = round(time.monotonic() - create_started, 2)
            phase_seconds["create_index_seconds"] = index_seconds
            status["phase_seconds"] = phase_seconds
            status["total_seconds"] = round(time.monotonic() - started, 2)


async def fetch_embedding_candidates(
    conn: Any,
    config: PromptVectorConfig,
    limit: int | None = None,
) -> list[CandidatePrompt]:
    rows = await conn.fetch(
        """
        select
            s.prompt_hash,
            coalesce(s.task_types[1], 'unknown') as task_type,
            s.prompt
        from analytics_prompt_slim_candidates s
        where s.quality_stage = 'candidate'
          and s.normalization_version = $1::text
          and ($2::text is null or $2::text = any(s.task_types))
          and not exists (
              select 1
              from analytics_prompt_embeddings e
              where e.model_id = $3::text
                and e.normalization_version = $1::text
                and e.prompt_hash = s.prompt_hash
                and e.status = 'embedded'
          )
        order by coalesce(s.task_types[1], 'unknown'), s.quality_score desc, s.uses desc, s.prompt_hash
        limit $4::int
        """,
        PROMPT_NORMALIZATION_VERSION,
        config.task_type,
        config.model_id,
        limit or config.limit or config.batch_size,
    )
    return [
        CandidatePrompt(
            prompt_hash=row["prompt_hash"],
            task_type=row["task_type"] or "unknown",
            prompt=row["prompt"] or "",
        )
        for row in rows
    ]


async def _upsert_embedding_batch(
    conn: Any,
    model_id: str,
    candidates: list[CandidatePrompt],
    vectors: list[np.ndarray],
) -> None:
    rows = []
    for candidate, vector in zip(candidates, vectors, strict=True):
        rows.append(
            (
                candidate.prompt_hash,
                candidate.task_type,
                model_id,
                PROMPT_NORMALIZATION_VERSION,
                candidate.prompt,
                hashlib.md5(candidate.prompt.encode("utf-8")).hexdigest(),
                int(vector.size),
                EMBEDDING_DTYPE,
                embedding_to_bytes(vector),
            )
        )
    await conn.executemany(
        """
        insert into analytics_prompt_embeddings (
            prompt_hash,
            task_type,
            model_id,
            normalization_version,
            prompt,
            prompt_checksum,
            embedding_dim,
            embedding_dtype,
            embedding_f16,
            status,
            error,
            created_at,
            updated_at,
            embedded_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'embedded', null, now(), now(), now())
        on conflict (model_id, normalization_version, prompt_hash) do update set
            task_type = excluded.task_type,
            prompt = excluded.prompt,
            prompt_checksum = excluded.prompt_checksum,
            embedding_dim = excluded.embedding_dim,
            embedding_dtype = excluded.embedding_dtype,
            embedding_f16 = excluded.embedding_f16,
            status = 'embedded',
            error = null,
            updated_at = now(),
            embedded_at = now()
        """,
        rows,
    )


async def _mark_embedding_errors(
    conn: Any,
    model_id: str,
    candidates: list[CandidatePrompt],
    error: str,
) -> None:
    rows = [
        (
            candidate.prompt_hash,
            candidate.task_type,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            candidate.prompt,
            hashlib.md5(candidate.prompt.encode("utf-8")).hexdigest(),
            0,
            EMBEDDING_DTYPE,
            error[:1000],
        )
        for candidate in candidates
    ]
    await conn.executemany(
        """
        insert into analytics_prompt_embeddings (
            prompt_hash,
            task_type,
            model_id,
            normalization_version,
            prompt,
            prompt_checksum,
            embedding_dim,
            embedding_dtype,
            status,
            error,
            created_at,
            updated_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, 'error', $9, now(), now())
        on conflict (model_id, normalization_version, prompt_hash) do update set
            task_type = excluded.task_type,
            prompt = excluded.prompt,
            prompt_checksum = excluded.prompt_checksum,
            status = 'error',
            error = excluded.error,
            updated_at = now()
        """,
        rows,
    )


async def refresh_prompt_embeddings(
    conn: Any,
    client: LMStudioEmbeddingClient,
    config: PromptVectorConfig,
) -> dict[str, Any]:
    selected = 0
    embedded = 0
    embedding_dim: int | None = None
    started = time.monotonic()
    while config.limit is None or selected < config.limit:
        remaining = None if config.limit is None else max(0, config.limit - selected)
        if remaining == 0:
            break
        batch_limit = config.batch_size if remaining is None else min(config.batch_size, remaining)
        batch = await fetch_embedding_candidates(conn, config, batch_limit)
        if not batch:
            break
        selected += len(batch)
        try:
            raw_vectors = await asyncio.to_thread(client.embed, [item.prompt for item in batch])
            vectors = [normalize_embedding(vector) for vector in raw_vectors]
            dims = {int(vector.size) for vector in vectors}
            if len(dims) != 1:
                raise RuntimeError(f"embedding dimensions are inconsistent: {sorted(dims)}")
            embedding_dim = dims.pop()
            await _upsert_embedding_batch(conn, config.model_id, batch, vectors)
            embedded += len(batch)
            await set_vector_state(
                conn,
                config.model_id,
                PROMPT_NORMALIZATION_VERSION,
                {
                    "embedding_dim": embedding_dim,
                    "embedded_in_run": embedded,
                    "last_embedding_batch_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            await _mark_embedding_errors(conn, config.model_id, batch, str(exc))
            await set_vector_state(
                conn,
                config.model_id,
                PROMPT_NORMALIZATION_VERSION,
                {"last_error": str(exc), "last_error_at": datetime.now(timezone.utc).isoformat()},
            )
            raise

    return {
        "selected": selected,
        "embedded": embedded,
        "embedding_dim": embedding_dim,
        "seconds": round(time.monotonic() - started, 2),
    }


async def refresh_prompt_vectors(conn: Any, config: PromptVectorConfig) -> dict[str, Any]:
    await ensure_prompt_vector_schema(conn)
    candidate_count = await _candidate_count(conn, config.task_type)
    status: dict[str, Any] = {
        "model_id": config.model_id,
        "model_key": config.model_key,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "candidate_count": candidate_count,
    }
    await set_vector_state(
        conn,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        {
            "model_id": config.model_id,
            "model_key": config.model_key,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "candidate_count": candidate_count,
        },
    )

    if not config.skip_token_refresh:
        status["tokens"] = await refresh_prompt_token_stats(conn)
        await set_vector_state(
            conn,
            config.model_id,
            PROMPT_NORMALIZATION_VERSION,
            {
                "token_version": PROMPT_TOKEN_VERSION,
                "token_count": status["tokens"]["token_count"],
                "token_stats_refreshed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    if config.tokens_only:
        return status

    client = LMStudioEmbeddingClient(config.base_url, config.model_id, config.model_key)
    if not config.skip_lm_check:
        await asyncio.to_thread(client.check_ready)
    status["embedding"] = await refresh_prompt_embeddings(conn, client, config)

    embedded_count = await _embedded_count(conn, config.model_id, config.task_type)
    status.update({"embedded_count": embedded_count})
    await set_vector_state(
        conn,
        config.model_id,
        PROMPT_NORMALIZATION_VERSION,
        {
            "embedded_count": embedded_count,
            "last_success_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return status


def prompt_vector_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh prompt embeddings.")
    parser.add_argument("--model-id", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_ID", DEFAULT_VECTOR_MODEL_ID))
    parser.add_argument("--model-key", default=os.getenv("LOCAL_ANALYTICS_EMBEDDING_MODEL_KEY", DEFAULT_VECTOR_MODEL_KEY))
    parser.add_argument("--base-url", default=os.getenv("LOCAL_ANALYTICS_LMSTUDIO_BASE_URL", DEFAULT_LM_STUDIO_BASE_URL))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--task-type")
    parser.add_argument("--data-dir", default=os.getenv("LOCAL_ANALYTICS_VECTOR_DATA_DIR", DEFAULT_VECTOR_DATA_DIR))
    parser.add_argument("--embed-only", action="store_true", help="compatibility no-op; embeddings are the only mode")
    parser.add_argument("--tokens-only", action="store_true", help="refresh prompt token statistics without embeddings")
    parser.add_argument("--skip-token-refresh", action="store_true", help="skip prompt token statistics during embedding resume")
    parser.add_argument("--skip-lm-check", action="store_true")
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    return parser


def config_from_args(args: argparse.Namespace) -> PromptVectorConfig:
    return PromptVectorConfig(
        model_id=args.model_id,
        model_key=args.model_key,
        base_url=args.base_url,
        batch_size=max(1, int(args.batch_size)),
        limit=args.limit,
        task_type=(args.task_type or "").strip() or None,
        data_dir=args.data_dir,
        embed_only=bool(args.embed_only),
        tokens_only=bool(args.tokens_only),
        skip_token_refresh=bool(args.skip_token_refresh),
        skip_lm_check=bool(args.skip_lm_check),
    )
