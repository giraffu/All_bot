from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from config import MINIO_BUCKET
from shared.character_reference_sheet import (
    CHARACTER_ASSET_MOSAIC_VERSION,
    INGREDIENTS_CHARACTER_PANEL_VERSION,
    compose_character_asset_mosaic,
)
from src.media_paths import normalize_owned_user_upload_key
from src.core.billing_core import get_concurrent_task_limit_for_identity
from src.core.task_application import TaskApplication
from src.core.task_core_types import (
    SubmissionReconciliationPending,
    TaskSubmissionCommand,
    TaskSubmissionPolicy,
    TaskSubmissionSideEffectPlan,
)
from src.database.models import CharacterReference, CharacterReferenceView
from src.domain_config.ltx_t2v import (
    CHARACTER_REFERENCE_BUILD_COST,
    CHARACTER_REFERENCE_BUILD_TASK_TYPE,
)
from src.quota import QuotaManager
from src.services.storage import storage
from src.services.task_web_submission_intent import WebSubmissionIntentJournal
from src.task_application_runtime import get_task_application
from src.web_api.common.utils import release_read_transaction
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.services.character_view_prompt_config_service import (
    BUILTIN_CHARACTER_VIEW_CONFIGS,
    DEFAULT_TAG_OPTIONS,
    get_builtin_character_view_config,
    list_character_view_configs,
    render_character_view_prompts,
)
from src.web_api.services.character_view_template_service import (
    get_active_character_view_template,
    list_character_view_templates,
)
from src.web_api.services.task_submission_service import submit_generation_task

logger = logging.getLogger(__name__)

ALLOWED_CHARACTER_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
CHARACTER_IMAGE_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
CHARACTER_READY_LIMIT = 20
CHARACTER_SOURCE_MAX_BYTES = 20 * 1024 * 1024
CHARACTER_VIEW_TASK_TYPES = {
    "free_edit": "edit",
    "free_edit_v2_5": "free_edit_v2_5",
    "free_edit_v3": "pornmaster_flux2_edit_bf16",
}

_CHARACTER_VIEW_META = (
    ("face_front", "正脸", True, False),
    ("body_front_nude", "正面全身裸体", True, False),
    ("body_front_clothed", "正面全身穿衣", True, False),
    ("torso_front", "胸部镜头", False, True),
    ("genitals_front", "正面私处", False, True),
    ("pelvis_back", "背面私处", False, True),
    ("custom_1", "扩展子图 1", False, False),
    ("custom_2", "扩展子图 2", False, False),
    ("custom_3", "扩展子图 3", False, False),
    ("custom_4", "扩展子图 4", False, False),
)

CHARACTER_VIEW_CATALOG = tuple(
    {
        "type": view_type,
        "label": label,
        "index": index,
        "required": False,
        "can_generate": can_generate,
        "has_templates": has_templates,
        "custom": view_type.startswith("custom_"),
        "default_prompt": (
            BUILTIN_CHARACTER_VIEW_CONFIGS[view_type]["prompt_templates"]["neutral"]
            if view_type in BUILTIN_CHARACTER_VIEW_CONFIGS
            else ""
        ),
    }
    for index, (view_type, label, can_generate, has_templates) in enumerate(
        _CHARACTER_VIEW_META,
        1,
    )
)


@dataclass(frozen=True, slots=True)
class ReadyCharacterIngredient:
    sheet_object_key: str
    description: str


CHARACTER_VIEW_BY_TYPE = {item["type"]: item for item in CHARACTER_VIEW_CATALOG}
CHARACTER_VIEW_ORDER = {
    item["type"]: int(item["index"]) for item in CHARACTER_VIEW_CATALOG
}
CHARACTER_REQUIRED_VIEW_TYPES = tuple(
    item["type"] for item in CHARACTER_VIEW_CATALOG if item["required"]
)
CHARACTER_GENERATABLE_VIEW_TYPES = tuple(
    item["type"] for item in CHARACTER_VIEW_CATALOG if item["can_generate"]
)
EXPLICIT_CHARACTER_VIEW_TYPES = {"genitals_front", "pelvis_back"}

FEMALE_PROMPT_TAGS = DEFAULT_TAG_OPTIONS


async def _runtime_view_configs(db) -> list[dict]:
    # Lightweight service unit tests use deliberately tiny session doubles. Real
    # AsyncSession instances always expose get_bind and read dashboard overrides.
    if not hasattr(db, "get_bind"):
        return [
            get_builtin_character_view_config(view_type)
            for view_type in BUILTIN_CHARACTER_VIEW_CONFIGS
        ]
    return await list_character_view_configs(db)


def compose_character_view_prompts(
    profile: dict | None,
    configs: list[dict] | None = None,
) -> dict[str, str]:
    """Compose canonical prompts; legacy characters keep the neutral defaults."""
    return render_character_view_prompts(profile, configs)


def character_features_enabled() -> bool:
    return os.getenv("CHARACTER_ASSETS_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def character_explicit_views_enabled() -> bool:
    return os.getenv("CHARACTER_EXPLICIT_VIEWS_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalize_owned_upload_key(value: str, user_id: int) -> str:
    try:
        return normalize_owned_user_upload_key(
            value,
            user_id=user_id,
            allowed_extensions=ALLOWED_CHARACTER_EXTENSIONS,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="源图必须是当前用户上传的 PNG/JPEG/WebP。"
        ) from exc


def _presigned_object_url(value: str | None) -> str | None:
    if not value:
        return None
    object_key = value.removeprefix(f"{MINIO_BUCKET}/")
    return storage.get_presigned_url(object_key, bucket=MINIO_BUCKET) or None


def _view_response(
    row: CharacterReferenceView,
    default_prompts: dict[str, str] | None = None,
    view_configs: list[dict] | None = None,
) -> dict:
    runtime_config = next(
        (item for item in (view_configs or []) if item["view_type"] == row.view_type),
        None,
    )
    config = CHARACTER_VIEW_BY_TYPE.get(row.view_type) or {
        "label": {
            "body_front": "旧版全身正面图",
            "body_side": "旧版全身侧面图",
            "body_back": "旧版全身背面图",
        }.get(row.view_type, row.view_type),
        "default_prompt": "",
    }
    default_prompt = (default_prompts or {}).get(
        row.view_type, config["default_prompt"]
    )
    prompt = str(getattr(row, "prompt", None) or "").strip()
    previous_default = config["default_prompt"].replace("纯白背景", "纯黑背景")
    if prompt == previous_default:
        prompt = default_prompt
    return {
        "type": row.view_type,
        "label": (
            str(getattr(row, "display_name", None) or "").strip()
            or (runtime_config["display_name"] if runtime_config else config["label"])
        ),
        "description": str(getattr(row, "description", None) or "").strip() or None,
        "prompt": prompt,
        "default_prompt": default_prompt,
        "tag_groups": (
            list(runtime_config["tag_groups"])
            if runtime_config
            else list(
                BUILTIN_CHARACTER_VIEW_CONFIGS.get(row.view_type, {}).get(
                    "tag_groups", []
                )
            )
        ),
        "tag_options": (
            dict(runtime_config["tag_options"])
            if runtime_config
            else dict(
                BUILTIN_CHARACTER_VIEW_CONFIGS.get(row.view_type, {}).get(
                    "tag_options", {}
                )
            )
        ),
        "status": row.status,
        "task_id": getattr(row, "task_id", None),
        "object_key": row.object_key,
        "preview_url": _presigned_object_url(row.object_key),
    }


def _response(
    row: CharacterReference,
    views: list[CharacterReferenceView] | None = None,
    view_configs: list[dict] | None = None,
) -> dict:
    preview = None
    if row.sheet_object_key:
        preview = _presigned_object_url(row.sheet_object_key)
    resolved_views = list(views if views is not None else getattr(row, "views", []))
    resolved_views.sort(key=lambda item: CHARACTER_VIEW_ORDER.get(item.view_type, 99))
    prompt_profile = getattr(row, "prompt_profile", None)
    default_prompts = compose_character_view_prompts(prompt_profile, view_configs)
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "moderation_status": getattr(row, "moderation_status", "active"),
        "moderation_reason": getattr(row, "moderation_reason", None),
        "task_id": row.task_id,
        "source_object_key": row.source_object_key,
        "sheet_object_key": row.sheet_object_key,
        "preview_url": preview,
        "prompt_profile": prompt_profile,
        "adult_confirmed": bool(getattr(row, "adult_confirmed_at", None)),
        "usage_rights_confirmed": bool(
            getattr(row, "usage_rights_confirmed_at", None)
        ),
        "default_prompts": default_prompts,
        "view_configs": [
            {
                "type": item["type"],
                "label": (
                    next(
                        (
                            config["display_name"]
                            for config in (view_configs or [])
                            if config["view_type"] == item["type"]
                        ),
                        item["label"],
                    )
                ),
                "required": False,
                "can_generate": item["can_generate"],
                "has_templates": item["has_templates"],
                "custom": item["custom"],
                "tag_groups": list(
                    BUILTIN_CHARACTER_VIEW_CONFIGS.get(item["type"], {}).get(
                        "tag_groups", []
                    )
                ),
                "tag_options": dict(
                    BUILTIN_CHARACTER_VIEW_CONFIGS.get(item["type"], {}).get(
                        "tag_options", {}
                    )
                ),
            }
            for item in CHARACTER_VIEW_CATALOG
        ],
        "views": [
            _view_response(view, default_prompts, view_configs)
            for view in resolved_views
        ],
    }


async def list_characters(*, db, user_id: int) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(CharacterReference)
                .where(
                    CharacterReference.user_id == user_id,
                    CharacterReference.status != "deleted",
                )
                .order_by(CharacterReference.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        ready_types = {
            view.view_type
            for view in getattr(row, "views", [])
            if view.status == "ready" and view.object_key
        }
        if ready_types and not row.sheet_object_key:
            await _try_auto_materialize_character_sheet(db=db, character=row)
    view_configs = await _runtime_view_configs(db)
    return [_response(row, view_configs=view_configs) for row in rows]


async def get_character_batch_capacity(
    *,
    current_user,
    get_active_count_func=None,
    get_identity_func=None,
) -> dict[str, int]:
    if get_active_count_func is None:
        from src.services.redis_client import redis_client

        get_active_count_func = redis_client.get_user_concurrency
    if get_identity_func is None:
        from src.services.permission_service import permission_service

        get_identity_func = permission_service.get_user_identity
    identity = await get_identity_func(current_user.id)
    limit = get_concurrent_task_limit_for_identity(identity)
    active = max(int(await get_active_count_func(current_user.id)), 0)
    return {
        "limit": limit,
        "active": active,
        "available": max(limit - active, 0),
    }


async def _validate_character_source(*, user_id: int, source_object_key: str) -> str:
    object_key = _normalize_owned_upload_key(source_object_key, user_id)
    if not await storage.async_object_exists(MINIO_BUCKET, object_key):
        raise HTTPException(status_code=400, detail="源图不存在或上传尚未完成。")
    object_size = await storage.async_object_size(MINIO_BUCKET, object_key)
    if object_size is None:
        raise HTTPException(status_code=400, detail="无法校验源图大小，请重新上传。")
    if object_size > CHARACTER_SOURCE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="源图不能超过 20MB。")
    return object_key


async def _ensure_character_limit(*, db, user_id: int) -> None:
    ready_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(CharacterReference)
                .where(
                    CharacterReference.user_id == user_id,
                    CharacterReference.status.in_(("draft", "ready")),
                )
            )
        ).scalar_one()
    )
    if ready_count >= CHARACTER_READY_LIMIT:
        raise HTTPException(status_code=409, detail="每位用户最多保留 20 个人物。")


async def create_character_draft(*, db, current_user, payload) -> dict:
    if (
        payload.initial_view_type in EXPLICIT_CHARACTER_VIEW_TYPES
        and not character_explicit_views_enabled()
    ):
        raise HTTPException(status_code=404, detail="人物特写功能当前未开放。")
    await _ensure_character_limit(db=db, user_id=current_user.id)
    if payload.template_id:
        template = await get_active_character_view_template(db, payload.template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="人物子图模板不存在或已停用。")
        if template.view_type != payload.initial_view_type:
            raise HTTPException(status_code=400, detail="人物子图模板类型不匹配。")
        source_key = str(template.object_key).removeprefix(f"{MINIO_BUCKET}/")
        source_bytes = await asyncio.to_thread(
            storage.get_file_bytes,
            source_key,
            MINIO_BUCKET,
        )
        extension = source_key.rsplit(".", 1)[-1].lower()
    else:
        source_key = await _validate_character_source(
            user_id=current_user.id,
            source_object_key=str(payload.source_object_key),
        )
        source_bytes = await asyncio.to_thread(
            storage.get_file_bytes,
            source_key,
            MINIO_BUCKET,
        )
        extension = source_key.rsplit(".", 1)[-1].lower()
    if not source_bytes or extension not in CHARACTER_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="无法读取初始人物子图。")

    character_id = str(uuid.uuid4())
    durable_key = (
        f"character_references/{current_user.id}/{character_id}/views/"
        f"{payload.initial_view_type}-{uuid.uuid4().hex}.{extension}"
    )
    uploaded = await asyncio.to_thread(
        storage.upload_bytes,
        source_bytes,
        durable_key,
        CHARACTER_IMAGE_CONTENT_TYPES[extension],
        MINIO_BUCKET,
    )
    if not uploaded:
        raise HTTPException(status_code=503, detail="人物初始子图保存失败，请重试。")

    row = CharacterReference(
        id=character_id,
        user_id=current_user.id,
        name=payload.name.strip(),
        description=str(payload.description or "").strip() or None,
        prompt_profile=(payload.prompt_profile.model_dump() if payload.prompt_profile else None),
        # Consent/rights are enforced by the upstream account flow. These
        # timestamps remain populated for old readers without adding duplicate
        # confirmations to the character workspace.
        adult_confirmed_at=datetime.now(),
        usage_rights_confirmed_at=datetime.now(),
        source_object_key=f"{MINIO_BUCKET}/{durable_key}",
        task_id=str(uuid.uuid4()),
        status="draft",
    )
    prompts = compose_character_view_prompts(row.prompt_profile)
    view = CharacterReferenceView(
        id=str(uuid.uuid4()),
        character_id=character_id,
        view_type=payload.initial_view_type,
        display_name=(
            str(payload.initial_view_label or "").strip()
            or CHARACTER_VIEW_BY_TYPE[payload.initial_view_type]["label"]
        ),
        description=None,
        prompt=prompts.get(payload.initial_view_type, ""),
        object_key=f"{MINIO_BUCKET}/{durable_key}",
        task_id=None,
        status="ready",
    )
    db.add(row)
    db.add(view)
    await db.commit()
    view_configs = await _runtime_view_configs(db)
    return await _materialize_saved_character_sheet(
        db=db,
        character=row,
        views=[view],
        view_configs=view_configs,
    )


async def confirm_character_identity(
    *, db, user_id: int, character_id: str, payload
) -> dict:
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    existing_profile = getattr(character, "prompt_profile", None)
    requested_profile = (
        payload.prompt_profile.model_dump() if payload.prompt_profile else None
    )
    if existing_profile is None:
        if requested_profile is None:
            raise HTTPException(status_code=409, detail="请先设置人物性别。")
        character.prompt_profile = requested_profile
    elif requested_profile is not None and requested_profile != existing_profile:
        raise HTTPException(status_code=409, detail="人物性别和身体标签不能再次修改。")
    now = datetime.now()
    character.adult_confirmed_at = now
    character.usage_rights_confirmed_at = now
    character.updated_at = now
    await db.commit()
    view_configs = await _runtime_view_configs(db)
    return _response(character, view_configs=view_configs)


async def generate_character_view(
    *, db, current_user, character_id: str, view_type: str, payload
) -> dict:
    if view_type not in CHARACTER_VIEW_BY_TYPE:
        raise HTTPException(status_code=404, detail="未知的人物子图类型。")
    if view_type not in CHARACTER_GENERATABLE_VIEW_TYPES:
        raise HTTPException(
            status_code=405,
            detail="该子图只支持选择模板或上传替换，不能调用提示词生成。",
        )
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == current_user.id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    view = (
        await db.execute(
            select(CharacterReferenceView).where(
                CharacterReferenceView.character_id == character_id,
                CharacterReferenceView.view_type == view_type,
            )
        )
    ).scalar_one_or_none()
    if view is not None and view.status == "pending":
        raise HTTPException(status_code=409, detail="该子图正在生成，请稍候。")

    source_object_key = character.source_object_key

    task_id = str(uuid.uuid4())
    if view is None:
        view = CharacterReferenceView(
            id=str(uuid.uuid4()),
            character_id=character_id,
            view_type=view_type,
            display_name=CHARACTER_VIEW_BY_TYPE[view_type]["label"],
            description=None,
            prompt=payload.prompt.strip(),
            task_id=task_id,
            status="pending",
        )
        db.add(view)
    else:
        view.prompt = payload.prompt.strip()
        view.task_id = task_id
        view.status = "pending"
        view.updated_at = datetime.now()
    await db.commit()
    try:
        task_type = CHARACTER_VIEW_TASK_TYPES[payload.engine]
        result = await submit_generation_task(
            req=TaskGenerateRequest(
                task_type=task_type,
                inputs={
                    "images": [source_object_key],
                    "record_history": False,
                },
                prompt=payload.prompt.strip(),
            ),
            current_user=current_user,
            get_balance=QuotaManager().get_credits,
            task_id_override=task_id,
            registry_metadata_extra={
                "_character_reference_view": {
                    "version": 1,
                    "character_id": character_id,
                    "view_type": view_type,
                },
                "record_history": False,
            },
            allow_contribute_override=False,
        )
    except Exception:
        view.status = "failed"
        view.updated_at = datetime.now()
        await db.commit()
        raise
    return {
        "character_id": character_id,
        "view_type": view_type,
        "task_id": result.task_id,
        "task_type": task_type,
        "status": "pending",
        "cost": result.cost,
        "balance_remaining": result.balance_remaining,
    }


async def upload_character_view(
    *, db, current_user, character_id: str, view_type: str, payload
) -> dict:
    config = CHARACTER_VIEW_BY_TYPE.get(view_type)
    if config is None:
        raise HTTPException(status_code=404, detail="未知的人物子图类型。")
    if view_type in EXPLICIT_CHARACTER_VIEW_TYPES and not character_explicit_views_enabled():
        raise HTTPException(status_code=404, detail="人物特写功能当前未开放。")
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == current_user.id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    view = (
        await db.execute(
            select(CharacterReferenceView).where(
                CharacterReferenceView.character_id == character_id,
                CharacterReferenceView.view_type == view_type,
            )
        )
    ).scalar_one_or_none()
    if view is not None and view.status == "pending":
        raise HTTPException(status_code=409, detail="该子图正在生成，不能上传替换。")

    source_key = await _validate_character_source(
        user_id=current_user.id,
        source_object_key=payload.source_object_key,
    )
    image_bytes = await asyncio.to_thread(
        storage.get_file_bytes,
        source_key,
        MINIO_BUCKET,
    )
    if not image_bytes:
        raise HTTPException(status_code=400, detail="无法读取上传图片，请重新上传。")
    extension = source_key.rsplit(".", 1)[-1].lower()
    durable_key = (
        f"character_references/{current_user.id}/{character_id}/views/"
        f"{view_type}-{uuid.uuid4().hex}.{extension}"
    )
    uploaded = await asyncio.to_thread(
        storage.upload_bytes,
        image_bytes,
        durable_key,
        CHARACTER_IMAGE_CONTENT_TYPES[extension],
        MINIO_BUCKET,
    )
    if not uploaded:
        raise HTTPException(status_code=503, detail="人物子图保存失败，请重试。")

    view_configs = await _runtime_view_configs(db)
    prompts = compose_character_view_prompts(
        getattr(character, "prompt_profile", None), view_configs
    )
    if view is None:
        view = CharacterReferenceView(
            id=str(uuid.uuid4()),
            character_id=character_id,
            view_type=view_type,
            display_name=config["label"],
            description=None,
            prompt=prompts.get(view_type, ""),
            task_id=None,
            object_key=f"{MINIO_BUCKET}/{durable_key}",
            status="ready",
        )
        db.add(view)
    else:
        view.prompt = prompts.get(view_type, "")
        view.task_id = None
        view.object_key = f"{MINIO_BUCKET}/{durable_key}"
        view.status = "ready"
        view.updated_at = datetime.now()
    await db.commit()
    await _try_auto_materialize_character_sheet(db=db, character=character)
    return _view_response(view, prompts, view_configs)


async def list_available_character_view_templates(*, db) -> list[dict]:
    templates = await list_character_view_templates(db, include_disabled=False)
    if character_explicit_views_enabled():
        return templates
    return [
        item
        for item in templates
        if item["view_type"] not in EXPLICIT_CHARACTER_VIEW_TYPES
    ]


async def apply_character_view_template(
    *, db, current_user, character_id: str, view_type: str, payload
) -> dict:
    config = CHARACTER_VIEW_BY_TYPE.get(view_type)
    if config is None or not config["has_templates"]:
        raise HTTPException(status_code=404, detail="该人物子图不支持图片模板。")
    if view_type in EXPLICIT_CHARACTER_VIEW_TYPES and not character_explicit_views_enabled():
        raise HTTPException(status_code=404, detail="人物特写功能当前未开放。")
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == current_user.id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    template = await get_active_character_view_template(db, payload.template_id)
    if template is None or template.view_type != view_type:
        raise HTTPException(status_code=404, detail="人物子图模板不存在、已停用或类型不匹配。")
    template_key = str(template.object_key).removeprefix(f"{MINIO_BUCKET}/")
    image_bytes = await asyncio.to_thread(
        storage.get_file_bytes,
        template_key,
        MINIO_BUCKET,
    )
    if not image_bytes:
        raise HTTPException(status_code=409, detail="人物子图模板文件已失效。")
    extension = template_key.rsplit(".", 1)[-1].lower()
    if extension not in CHARACTER_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=409, detail="人物子图模板格式无效。")
    durable_key = (
        f"character_references/{current_user.id}/{character_id}/views/"
        f"{view_type}-{uuid.uuid4().hex}.{extension}"
    )
    uploaded = await asyncio.to_thread(
        storage.upload_bytes,
        image_bytes,
        durable_key,
        CHARACTER_IMAGE_CONTENT_TYPES[extension],
        MINIO_BUCKET,
    )
    if not uploaded:
        raise HTTPException(status_code=503, detail="人物模板保存失败，请重试。")
    view = (
        await db.execute(
            select(CharacterReferenceView).where(
                CharacterReferenceView.character_id == character_id,
                CharacterReferenceView.view_type == view_type,
            )
        )
    ).scalar_one_or_none()
    if view is None:
        view = CharacterReferenceView(
            id=str(uuid.uuid4()),
            character_id=character_id,
            view_type=view_type,
            display_name=config["label"],
            description=None,
            prompt="",
            object_key=f"{MINIO_BUCKET}/{durable_key}",
            task_id=None,
            status="ready",
        )
        db.add(view)
    else:
        if view.status == "pending":
            raise HTTPException(status_code=409, detail="该子图正在生成，不能应用模板。")
        view.object_key = f"{MINIO_BUCKET}/{durable_key}"
        view.task_id = None
        view.status = "ready"
        view.updated_at = datetime.now()
    await db.commit()
    await _try_auto_materialize_character_sheet(db=db, character=character)
    view_configs = await _runtime_view_configs(db)
    return _view_response(view, compose_character_view_prompts(character.prompt_profile), view_configs)


async def patch_character_view(
    *, db, user_id: int, character_id: str, view_type: str, payload
) -> dict:
    if view_type not in CHARACTER_VIEW_BY_TYPE:
        raise HTTPException(status_code=404, detail="未知的人物子图类型。")
    view = (
        await db.execute(
            select(CharacterReferenceView)
            .join(CharacterReference)
            .where(
                CharacterReferenceView.character_id == character_id,
                CharacterReferenceView.view_type == view_type,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if view is None:
        raise HTTPException(status_code=404, detail="人物子图不存在。")
    if payload.display_name is not None:
        view.display_name = payload.display_name.strip()
    if payload.description is not None:
        view.description = payload.description.strip() or None
    view.updated_at = datetime.now()
    await db.commit()
    return _view_response(view)


def _read_character_view_bytes(
    views: list[CharacterReferenceView],
) -> list[tuple[int, bytes]]:
    payloads: list[tuple[int, bytes]] = []
    for view in views:
        if not view.object_key:
            continue
        object_key = view.object_key.removeprefix(f"{MINIO_BUCKET}/")
        payload = storage.get_file_bytes(object_key, bucket=MINIO_BUCKET)
        if not payload:
            raise RuntimeError(
                f"character view object is unavailable: {view.view_type}"
            )
        payloads.append((CHARACTER_VIEW_ORDER[view.view_type] - 1, payload))
    return payloads


def _compose_character_sheet(payloads: list[tuple[int, bytes]]) -> bytes:
    return compose_character_asset_mosaic(payloads)


async def _materialize_saved_character_sheet(
    *,
    db,
    character: CharacterReference,
    views: list[CharacterReferenceView],
    view_configs: list[dict] | None = None,
) -> dict:
    ready_views = sorted(
        (
            view
            for view in views
            if view.status == "ready"
            and view.object_key
            and view.view_type in CHARACTER_VIEW_BY_TYPE
        ),
        key=lambda view: CHARACTER_VIEW_ORDER[view.view_type],
    )
    if not ready_views:
        raise HTTPException(
            status_code=409,
            detail="人物至少需要一张已完成的子图。",
        )
    payloads = await asyncio.to_thread(_read_character_view_bytes, ready_views)
    sheet = await asyncio.to_thread(_compose_character_sheet, payloads)
    object_key = (
        f"character_references/{character.user_id}/{character.id}/"
        f"{CHARACTER_ASSET_MOSAIC_VERSION}.png"
    )
    uploaded = await asyncio.to_thread(
        storage.upload_bytes,
        sheet,
        object_key,
        "image/png",
        MINIO_BUCKET,
    )
    if not uploaded:
        raise HTTPException(status_code=503, detail="人物参考图保存失败，请重试。")
    character.sheet_object_key = f"{MINIO_BUCKET}/{object_key}"
    character.status = "ready"
    character.updated_at = datetime.now()
    await db.commit()
    if view_configs is None:
        view_configs = await _runtime_view_configs(db)
    return _response(character, views, view_configs)


async def _try_auto_materialize_character_sheet(
    *, db, character: CharacterReference
) -> bool:
    """Promote a persisted draft once all required child slots are ready.

    A child result must remain usable even when sheet composition or storage has a
    transient failure. The next child upload, finalizer, or explicit save retries it.
    """
    views = list(
        (
            await db.execute(
                select(CharacterReferenceView).where(
                    CharacterReferenceView.character_id == character.id
                )
            )
        )
        .scalars()
        .all()
    )
    if not any(
        view.status == "ready"
        and view.object_key
        and view.view_type in CHARACTER_VIEW_BY_TYPE
        for view in views
    ):
        return False
    try:
        await _materialize_saved_character_sheet(
            db=db,
            character=character,
            views=views,
        )
    except Exception:
        logger.exception(
            "character sheet auto materialization failed character_id=%s",
            character.id,
        )
        return False
    return True


async def save_character(*, db, user_id: int, character_id: str) -> dict:
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    views = (
        (
            await db.execute(
                select(CharacterReferenceView).where(
                    CharacterReferenceView.character_id == character_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return await _materialize_saved_character_sheet(
        db=db,
        character=character,
        views=list(views),
    )


async def resolve_ready_character_sheet(
    *, db, user_id: int, character_id: str
) -> ReadyCharacterIngredient:
    row = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if (
        row is None
        or row.status != "ready"
        or getattr(row, "moderation_status", "active") != "active"
        or not row.sheet_object_key
    ):
        raise HTTPException(status_code=400, detail="人物不存在、未就绪或已删除。")
    # The legacy two-character LTX workflow only accepts its original four-view
    # panel. New flexible mosaics are intentionally consumed through H3 typed refs.
    if not row.sheet_object_key.endswith(f"/{INGREDIENTS_CHARACTER_PANEL_VERSION}.png"):
        raise HTTPException(
            status_code=400,
            detail="人物参考图版本已失效，请重新保存人物。",
        )
    description = str(row.description or "").strip()
    sheet = row.sheet_object_key
    await release_read_transaction(db)
    return ReadyCharacterIngredient(
        sheet_object_key=sheet,
        description=description,
    )


async def build_character(
    *, db, current_user, payload, task_application: TaskApplication | None = None
) -> dict:
    object_key = _normalize_owned_upload_key(payload.source_object_key, current_user.id)
    if not await storage.async_object_exists(MINIO_BUCKET, object_key):
        raise HTTPException(status_code=400, detail="源图不存在或上传尚未完成。")
    object_size = await storage.async_object_size(MINIO_BUCKET, object_key)
    if object_size is None:
        raise HTTPException(status_code=400, detail="无法校验源图大小，请重新上传。")
    if object_size > CHARACTER_SOURCE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="源图不能超过 20MB。")
    ready_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(CharacterReference)
                .where(
                    CharacterReference.user_id == current_user.id,
                    CharacterReference.status == "ready",
                )
            )
        ).scalar_one()
    )
    if ready_count >= CHARACTER_READY_LIMIT:
        raise HTTPException(
            status_code=409, detail="每位用户最多保留 20 个已就绪人物。"
        )

    character_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
    row = CharacterReference(
        id=character_id,
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        prompt_profile=payload.prompt_profile.model_dump(),
        adult_confirmed_at=datetime.now(),
        usage_rights_confirmed_at=datetime.now(),
        source_object_key=f"{MINIO_BUCKET}/{object_key}",
        task_id=task_id,
        status="pending",
    )
    db.add(row)
    await db.commit()
    submission_journal = WebSubmissionIntentJournal(
        internal_user_id=current_user.id,
        username=current_user.username,
        task_id=task_id,
    )
    try:
        application = task_application or get_task_application()
        result = await application.submit(
            TaskSubmissionCommand(
                internal_user_id=current_user.id,
                username=current_user.username,
                task_type=CHARACTER_REFERENCE_BUILD_TASK_TYPE,
                inputs={
                    "images": [f"{MINIO_BUCKET}/{object_key}"],
                    "character_id": character_id,
                    "record_history": False,
                    "prompt": "Generate six separate consistent adult character reference views on pure black backgrounds: front close-up face, three-quarter face, front waist-up, front full body, side full body, back full body. Preserve identity, face, hairstyle, skin tone, body, clothing and accessories. No text, labels, borders or collage.",
                },
                task_id=task_id,
                registry_metadata={
                    "character_id": character_id,
                    "record_history": False,
                },
            ),
            TaskSubmissionPolicy(
                side_effect_plan=TaskSubmissionSideEffectPlan(
                    attach_web_monitor=True
                ),
                cost_override=CHARACTER_REFERENCE_BUILD_COST,
                user_cancel_allowed=True,
                allow_contribute_override=False,
                refund_idempotency_key=(
                    submission_journal.refund_idempotency_key
                ),
            ),
            submission_journal,
        )
    except SubmissionReconciliationPending as exc:
        result = {"task_id": exc.registry_task_id, "cost": exc.cost}
    except Exception:
        row.status = "failed"
        row.updated_at = datetime.now()
        await db.commit()
        raise
    balance = await QuotaManager().get_credits(current_user.id)
    return {
        "character_id": character_id,
        "task_id": result["task_id"],
        "status": "pending",
        "cost": result["cost"],
        "balance_remaining": balance,
    }


async def patch_character(*, db, user_id: int, character_id: str, payload) -> dict:
    row = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description.strip() or None
    if payload.prompt_profile is not None:
        current_profile = getattr(row, "prompt_profile", None) or {}
        next_profile = payload.prompt_profile.model_dump()
        if current_profile.get("gender") not in {None, next_profile["gender"]}:
            raise HTTPException(status_code=409, detail="人物性别不能再次修改。")
        row.prompt_profile = next_profile
    row.updated_at = datetime.now()
    await db.commit()
    view_configs = await _runtime_view_configs(db)
    return _response(row, view_configs=view_configs)


async def delete_character(*, db, user_id: int, character_id: str) -> None:
    row = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    if row.status == "pending":
        raise HTTPException(status_code=409, detail="人物仍在构建，请先取消任务。")
    row.status = "deleted"
    row.deleted_at = datetime.now()
    row.updated_at = datetime.now()
    await db.commit()


async def finalize_character_reference(
    *, task_id: str, status: str, result_path: str | None
) -> None:
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        candidate = (
            await db.execute(
                select(CharacterReferenceView).where(
                    CharacterReferenceView.task_id == task_id
                )
            )
        ).scalar_one_or_none()
        if candidate is not None and hasattr(candidate, "view_type"):
            if candidate.status == "ready" and candidate.object_key:
                return
            candidate.status = "ready" if status == "done" and result_path else "failed"
            if candidate.status == "ready":
                candidate.object_key = result_path
            candidate.updated_at = datetime.now()
            await db.commit()
            character_id = getattr(candidate, "character_id", None)
            if candidate.status == "ready" and character_id and hasattr(db, "get"):
                character = await db.get(CharacterReference, character_id)
                if character is not None and character.status != "deleted":
                    await _try_auto_materialize_character_sheet(
                        db=db,
                        character=character,
                    )
            return

        # Legacy all-at-once builds stored the task directly on the character row.
        row = candidate
        if row is None:
            row = (
                await db.execute(
                    select(CharacterReference).where(
                        CharacterReference.task_id == task_id
                    )
                )
            ).scalar_one_or_none()
        if row is None or row.status in {"ready", "deleted"}:
            return
        row.status = "ready" if status == "done" and result_path else "failed"
        if row.status == "ready":
            row.sheet_object_key = result_path
        row.updated_at = datetime.now()
        await db.commit()
