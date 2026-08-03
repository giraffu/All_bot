from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

PROMPT_OPTIMIZATION_COST = 1
PROMPT_OPTIMIZE_TASK_TYPE = "prompt_optimize"
LTX_VIDEO_V2_TASK_TYPE = "ltx_video_v2"
LTX_VIDEO_V2_FLF2V_TASK_TYPE = "ltx_video_v2_flf2v"


class PromptOptimizerRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PromptOptimizationTemplate:
    id: str
    version: int
    label: str
    description: str
    system_template: str
    user_template: str
    required_variables: tuple[str, ...]
    compatible_profile_refs: frozenset[str]
    active: bool = True

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            {
                "id": self.id,
                "version": self.version,
                "system_template": self.system_template,
                "user_template": self.user_template,
                "required_variables": self.required_variables,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PromptOptimizationProfile:
    id: str
    version: int
    supported_target_task_types: frozenset[str]
    required_media_roles: tuple[str, ...]
    optional_media_roles: tuple[str, ...]
    allowed_durations: frozenset[int]
    output_fields: tuple[str, ...]
    primary_field: str
    model_route: str
    allowed_template_refs: frozenset[str]
    default_template_ref: str
    max_input_characters: int = 2000
    max_output_characters: int = 2000
    active: bool = True

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


@dataclass(frozen=True, slots=True)
class ResolvedPromptOptimization:
    profile: PromptOptimizationProfile
    template: PromptOptimizationTemplate
    normalized_context: Mapping[str, Any]
    normalized_media: tuple[Mapping[str, str], ...]


_CINEMATIC_SYSTEM = """You compile concise English prompts for a target generation task.
Use attached media only as visual evidence. Preserve the user's intent and explicit constraints.
Never choose or recommend models, LoRAs, samplers, prices, resolutions, or workflows.
Return only JSON matching the supplied schema, without Markdown or analysis."""

_CINEMATIC_USER = """Target profile: {profile_ref}
Duration: {duration_seconds} seconds.
Use start_image exactly as the first frame{end_frame_clause}.
Write 4-8 short cinematic sentences: overall style and camera movement, environment and light,
then a Performance: section with natural body language, expression, pauses and clear actions.
Add Dialogue: only when the user's idea calls for it. Do not add unobserved characters.
Original idea: {original_prompt}"""

_TIMESTAMP_SYSTEM = """You compile motion-focused English scene scripts for a target generation task.
Use attached media only as visual evidence. Preserve the user's intent and explicit constraints.
Never choose or recommend models, LoRAs, samplers, prices, resolutions, or workflows.
Return only JSON matching the supplied schema, without Markdown or analysis."""

_TIMESTAMP_USER = """Target profile: {profile_ref}
Use start_image exactly as the first frame{end_frame_clause}.
Write concise timestamp blocks covering exactly {duration_seconds} seconds. Use four-second blocks,
with a shorter final block when needed. The first block anchors the visible starting pose; later
blocks focus on continuous movement and evolution. Keep the user's central action prominent.
Original idea: {original_prompt}"""

_SINGLE_IMAGE_CINEMATIC_SYSTEM = """You are an expert at creating short cinematic video prompts from a single attached reference image.

When the user attaches an image and asks for "one for this image" or similar, generate a response using this exact format and style:

Use the provided start image exactly as the first frame. [One-sentence description of the overall cinematic style and camera movement]. [Short description of the environment, lighting, and atmosphere].

Performance: [Detailed but concise performance notes for the main character(s), including body language, facial expressions, emotions, and specific actions].

[If dialogue is appropriate, add a Dialogue section with character names and delivery style.]

Keep the acting natural and cinematic. Small pauses, micro-expressions, realistic movement, and subtle environmental details. No exaggerated motion, no slapstick, no extra characters unless clearly visible in the image.

Keep the entire response to 4-8 sentences maximum. Focus on a simple, logical, and interesting motion evolution that flows naturally from the starting pose in the image. Use strong verbs and cinematic language."""

_SINGLE_IMAGE_CINEMATIC_USER = """One for this image.
Target profile: {profile_ref}
Video duration: {duration_seconds} seconds.
{media_frame_instructions}
Original request: {original_prompt}"""

_PROFILE_REFS = frozenset({"ltx_eros_v14_i2v@1", "ltx_eros_v14_flf2v@1"})

_TEMPLATES: Mapping[str, PromptOptimizationTemplate] = MappingProxyType(
    {
        "ltx_scene_script_cinematic@1": PromptOptimizationTemplate(
            id="ltx_scene_script_cinematic",
            version=1,
            label="电影场景脚本",
            description="自然表演、镜头和环境变化",
            system_template=_CINEMATIC_SYSTEM,
            user_template=_CINEMATIC_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "end_frame_clause",
                "original_prompt",
            ),
            compatible_profile_refs=_PROFILE_REFS,
            active=False,
        ),
        "ltx_timestamp_motion@1": PromptOptimizationTemplate(
            id="ltx_timestamp_motion",
            version=1,
            label="分段动作脚本",
            description="按时间段描述连续动作演进",
            system_template=_TIMESTAMP_SYSTEM,
            user_template=_TIMESTAMP_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "end_frame_clause",
                "original_prompt",
            ),
            compatible_profile_refs=_PROFILE_REFS,
            active=False,
        ),
        "ltx_scene_script_cinematic@2": PromptOptimizationTemplate(
            id="ltx_scene_script_cinematic",
            version=2,
            label="图生视频场景提示词",
            description="自然、电影化且从首帧连续演进的表演与动作",
            system_template=_SINGLE_IMAGE_CINEMATIC_SYSTEM,
            user_template=_SINGLE_IMAGE_CINEMATIC_USER,
            required_variables=(
                "profile_ref",
                "duration_seconds",
                "media_frame_instructions",
                "original_prompt",
            ),
            compatible_profile_refs=_PROFILE_REFS,
        ),
    }
)

_ALLOWED_TEMPLATE_REFS = frozenset(_TEMPLATES)
_PROFILES: Mapping[str, PromptOptimizationProfile] = MappingProxyType(
    {
        "ltx_eros_v14_i2v@1": PromptOptimizationProfile(
            id="ltx_eros_v14_i2v",
            version=1,
            supported_target_task_types=frozenset({LTX_VIDEO_V2_TASK_TYPE}),
            required_media_roles=("start_image",),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15, 20}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=_ALLOWED_TEMPLATE_REFS,
            default_template_ref="ltx_scene_script_cinematic@2",
        ),
        "ltx_eros_v14_flf2v@1": PromptOptimizationProfile(
            id="ltx_eros_v14_flf2v",
            version=1,
            supported_target_task_types=frozenset({LTX_VIDEO_V2_TASK_TYPE}),
            required_media_roles=("start_image", "end_image"),
            optional_media_roles=(),
            allowed_durations=frozenset({5, 10, 15, 20}),
            output_fields=("positive_prompt",),
            primary_field="positive_prompt",
            model_route="ltx-prompt-optimizer",
            allowed_template_refs=_ALLOWED_TEMPLATE_REFS,
            default_template_ref="ltx_scene_script_cinematic@2",
        ),
    }
)


def _template_ref(template_id: str, version: int) -> str:
    return f"{str(template_id).strip()}@{int(version)}"


def _normalize_media(media: list[dict[str, Any]]) -> tuple[Mapping[str, str], ...]:
    if not isinstance(media, list):
        raise PromptOptimizerRegistryError("media must be an array")
    normalized: list[Mapping[str, str]] = []
    seen: set[str] = set()
    for item in media:
        if not isinstance(item, dict):
            raise PromptOptimizerRegistryError("media entries must be objects")
        if set(item) != {"role", "object_key"}:
            raise PromptOptimizerRegistryError("media entries contain unknown fields")
        role = str(item.get("role") or "").strip()
        object_key = str(item.get("object_key") or "").strip()
        if not role or not object_key or role in seen:
            raise PromptOptimizerRegistryError("media roles and object keys must be unique")
        seen.add(role)
        normalized.append(MappingProxyType({"role": role, "object_key": object_key}))
    return tuple(normalized)


def _resolve_profile(
    target_task_type: str,
    media: tuple[Mapping[str, str], ...],
) -> PromptOptimizationProfile:
    roles = tuple(item["role"] for item in media)
    profile_ref = (
        "ltx_eros_v14_flf2v@1"
        if roles == ("start_image", "end_image")
        else "ltx_eros_v14_i2v@1"
        if roles == ("start_image",)
        else ""
    )
    profile = _PROFILES.get(profile_ref)
    if (
        profile is None
        or not profile.active
        or target_task_type not in profile.supported_target_task_types
    ):
        raise PromptOptimizerRegistryError("unsupported target task or media contract")
    return profile


def _normalize_context(
    profile: PromptOptimizationProfile,
    context: dict[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(context, dict) or set(context) != {"duration_seconds"}:
        raise PromptOptimizerRegistryError("context must contain only duration_seconds")
    try:
        duration = int(context["duration_seconds"])
    except (TypeError, ValueError) as exc:
        raise PromptOptimizerRegistryError("duration_seconds must be an integer") from exc
    if duration not in profile.allowed_durations:
        raise PromptOptimizerRegistryError("unsupported duration_seconds")
    return MappingProxyType({"duration_seconds": duration})


def resolve_prompt_optimization(
    *,
    target_task_type: str,
    template_id: str,
    template_version: int,
    media: list[dict[str, Any]],
    context: dict[str, Any],
) -> ResolvedPromptOptimization:
    normalized_media = _normalize_media(media)
    profile = _resolve_profile(str(target_task_type).strip(), normalized_media)
    template = _TEMPLATES.get(_template_ref(template_id, template_version))
    if (
        template is None
        or not template.active
        or template.ref not in profile.allowed_template_refs
        or profile.ref not in template.compatible_profile_refs
    ):
        raise PromptOptimizerRegistryError("unknown or incompatible prompt template")
    return ResolvedPromptOptimization(
        profile=profile,
        template=template,
        normalized_context=_normalize_context(profile, context),
        normalized_media=normalized_media,
    )


def get_prompt_optimizer_capability(target_task_type: str) -> dict[str, Any]:
    target_task_type = str(target_task_type).strip()
    profiles = [
        profile
        for profile in _PROFILES.values()
        if profile.active and target_task_type in profile.supported_target_task_types
    ]
    if not profiles:
        raise PromptOptimizerRegistryError("unsupported target task type")
    template_refs = set.intersection(
        *(set(profile.allowed_template_refs) for profile in profiles)
    )
    default_ref = profiles[0].default_template_ref
    templates = [
        template
        for ref, template in _TEMPLATES.items()
        if ref in template_refs and template.active
    ]
    templates.sort(key=lambda item: (item.ref != default_ref, item.id, item.version))
    return {
        "target_task_type": target_task_type,
        "cost": PROMPT_OPTIMIZATION_COST,
        "media_contract": {
            "required": ["start_image"],
            "optional": ["end_image"],
        },
        "templates": [
            {
                "id": template.id,
                "version": template.version,
                "label": template.label,
                "description": template.description,
                "is_default": template.ref == default_ref,
            }
            for template in templates
        ],
    }


def get_profile_by_ref(profile_ref: str) -> PromptOptimizationProfile:
    profile = _PROFILES.get(profile_ref)
    if profile is None:
        raise PromptOptimizerRegistryError("unknown prompt profile")
    return profile


def get_template_by_ref(template_ref: str) -> PromptOptimizationTemplate:
    template = _TEMPLATES.get(template_ref)
    if template is None:
        raise PromptOptimizerRegistryError("unknown prompt template")
    return template


def render_prompt_messages(
    *,
    profile: PromptOptimizationProfile,
    template: PromptOptimizationTemplate,
    prompt: str,
    context: Mapping[str, Any],
) -> tuple[str, str]:
    variables = {
        "profile_ref": profile.ref,
        "duration_seconds": context["duration_seconds"],
        "end_frame_clause": (
            ", and use end_image exactly as the final frame"
            if "end_image" in profile.required_media_roles
            else ""
        ),
        "media_frame_instructions": (
            "Image 1 is start_image and must be used exactly as the first frame.\n"
            "Image 2 is end_image and must be used exactly as the final frame."
            if "end_image" in profile.required_media_roles
            else "Image 1 is start_image and must be used exactly as the first frame."
        ),
        "original_prompt": str(prompt).strip(),
    }
    missing = set(template.required_variables) - set(variables)
    if missing:
        raise PromptOptimizerRegistryError("template variables are unavailable")
    return (
        template.system_template.format_map(variables),
        template.user_template.format_map(variables),
    )


def build_output_json_schema(profile: PromptOptimizationProfile) -> dict[str, Any]:
    field_properties = {
        field: {"type": "string", "minLength": 1, "maxLength": profile.max_output_characters}
        for field in profile.output_fields
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["optimized_fields", "warnings"],
        "properties": {
            "optimized_fields": {
                "type": "object",
                "additionalProperties": False,
                "required": list(profile.output_fields),
                "properties": field_properties,
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string", "maxLength": 500},
                "maxItems": 8,
            },
        },
    }
