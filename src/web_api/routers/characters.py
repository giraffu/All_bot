from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    QueueCapacityError,
)
from src.database.models import User
from src.web_api.dependencies import get_current_user, get_db
from src.web_api.schemas.character_schema import (
    CharacterBatchCapacityResponse,
    CharacterBuildRequest,
    CharacterBuildResponse,
    CharacterConfirmationRequest,
    CharacterDraftCreateRequest,
    CharacterPatchRequest,
    CharacterResponse,
    CharacterViewGenerateRequest,
    CharacterViewResponse,
    CharacterViewUploadRequest,
)
from src.web_api.services.character_reference_service import (
    build_character,
    character_features_enabled,
    create_character_draft,
    delete_character,
    generate_character_view,
    get_character_batch_capacity,
    list_characters,
    patch_character,
    save_character,
    upload_character_view,
    confirm_character_identity,
)


def _require_character_assets_enabled() -> None:
    if not character_features_enabled():
        raise HTTPException(status_code=404, detail="Not found")


router = APIRouter(dependencies=[Depends(_require_character_assets_enabled)])


@router.post("/build", response_model=CharacterBuildResponse)
async def create_character(
    payload: CharacterBuildRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_character(db=db, current_user=current_user, payload=payload)


@router.post("/drafts", response_model=CharacterResponse)
async def create_character_workspace(
    payload: CharacterDraftCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_character_draft(
        db=db,
        current_user=current_user,
        payload=payload,
    )


@router.post("/{character_id}/confirm", response_model=CharacterResponse)
async def confirm_character_workspace(
    character_id: str,
    payload: CharacterConfirmationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await confirm_character_identity(
        db=db,
        user_id=current_user.id,
        character_id=character_id,
        payload=payload,
    )


@router.get("", response_model=list[CharacterResponse])
async def get_characters(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await list_characters(db=db, user_id=current_user.id)


@router.get("/batch-capacity", response_model=CharacterBatchCapacityResponse)
async def get_batch_capacity(
    current_user: User = Depends(get_current_user),
):
    return await get_character_batch_capacity(current_user=current_user)


@router.post("/{character_id}/views/{view_type}/generate")
async def create_character_view(
    character_id: str,
    view_type: str,
    payload: CharacterViewGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await generate_character_view(
            db=db,
            current_user=current_user,
            character_id=character_id,
            view_type=view_type,
            payload=payload,
        )
    except QueueCapacityError as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "GENERATION_QUEUE_FULL", "detail": str(exc)},
        ) from exc
    except ConcurrencyLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except CoreDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{character_id}/views/{view_type}/upload",
    response_model=CharacterViewResponse,
)
async def upload_character_view_image(
    character_id: str,
    view_type: str,
    payload: CharacterViewUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await upload_character_view(
        db=db,
        current_user=current_user,
        character_id=character_id,
        view_type=view_type,
        payload=payload,
    )


@router.post("/{character_id}/save", response_model=CharacterResponse)
async def save_character_workspace(
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await save_character(
        db=db,
        user_id=current_user.id,
        character_id=character_id,
    )


@router.patch("/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: str,
    payload: CharacterPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await patch_character(
        db=db, user_id=current_user.id, character_id=character_id, payload=payload
    )


@router.delete("/{character_id}", status_code=204)
async def remove_character(
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_character(db=db, user_id=current_user.id, character_id=character_id)
    return Response(status_code=204)
