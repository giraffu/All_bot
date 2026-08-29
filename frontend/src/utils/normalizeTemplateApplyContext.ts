import { getCanonicalTemplateTaskType } from '@/constants/templateTaskMeta'
import { normalizeLtxVideoLoraItems } from '@/features/generation/imageToVideo'
import { MINIMAX_H3_ADDON_OPTIONS } from '@/features/generation/labModeConfig'
import type {
  NormalizeContextOptions,
  RawApplyContextResponse,
  TemplateApplyContext
} from '@/types/templateApply'

const asNonEmptyString = (value: unknown): string | null =>
  typeof value === 'string' && value.trim() !== '' ? value.trim() : null

const asNullableNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  return null
}

const asPositiveInteger = (value: unknown): number | null => {
  const parsed = asNullableNumber(value)
  if (parsed === null) {
    return null
  }

  const normalized = Math.trunc(parsed)
  return normalized > 0 ? normalized : null
}

const asStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }

  return value
    .map(item => asNonEmptyString(item))
    .filter((item): item is string => Boolean(item))
}

const normalizeMinimaxH3LoraItems = (value: unknown) => {
  if (!Array.isArray(value)) return []
  const allowed = new Set(MINIMAX_H3_ADDON_OPTIONS.map(option => option.value))
  const seen = new Set<string>()
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const name = asNonEmptyString((item as { name?: unknown }).name)
    const strength = asNullableNumber((item as { strength?: unknown }).strength)
    if (!name || !allowed.has(name as any) || seen.has(name) || strength === null || strength < 0.1 || strength > 2) {
      return []
    }
    seen.add(name)
    return [{ name, strength }]
  })
}

const normalizeGalleryReferenceAudioRef = (
  value: unknown,
): { source: 'gallery_post'; post_id: number } | null => {
  if (!value || typeof value !== 'object') return null
  const source = (value as { source?: unknown }).source
  const postId = asPositiveInteger((value as { post_id?: unknown }).post_id)
  return source === 'gallery_post' && postId !== null
    ? { source: 'gallery_post', post_id: postId }
    : null
}

export const normalizeTemplateApplyContext = (
  rawContext: RawApplyContextResponse | null | undefined,
  options: NormalizeContextOptions
): TemplateApplyContext | null => {
  if (!rawContext) {
    return null
  }

  const rawTaskType = asNonEmptyString(rawContext.task_type)
  if (!rawTaskType) {
    return null
  }

  const taskType = getCanonicalTemplateTaskType(rawTaskType)
  const inputFiles = asStringList(rawContext.input_files)
  const inputFileUrls = asStringList(rawContext.input_file_urls)

  const normalizedRaw: RawApplyContextResponse = {
    post_id: rawContext.post_id,
    source_post_id: rawContext.source_post_id ?? null,
    billing_resolution: rawContext.billing_resolution ?? null,
    requested_duration: rawContext.requested_duration ?? null,
    required_image_count: rawContext.required_image_count ?? null,
    resolution_preset: rawContext.resolution_preset ?? null,
    aspect_ratio: rawContext.aspect_ratio ?? null,
    task_id: rawContext.task_id ?? null,
    media_type: rawContext.media_type ?? null,
    prompt: rawContext.prompt ?? null,
    negative_prompt: rawContext.negative_prompt ?? null,
    lora_name: rawContext.lora_name ?? null,
    lora_strength: rawContext.lora_strength ?? null,
    lora_items: rawContext.lora_items ?? null,
    reference_audio_ref: rawContext.reference_audio_ref ?? null,
    reference_audio_url: rawContext.reference_audio_url ?? null,
    input_file: rawContext.input_file ?? null,
    input_file_url: rawContext.input_file_url ?? null,
    input_files: rawContext.input_files ?? null,
    input_file_urls: rawContext.input_file_urls ?? null,
    width: rawContext.width ?? null,
    height: rawContext.height ?? null,
    duration: rawContext.duration ?? null,
    task_type: rawTaskType
  }

  return {
    raw: normalizedRaw,
    source: options.source,
    entryEntityId: options.entryEntityId,
    rawEntityId: asPositiveInteger(rawContext.post_id),
    rawTaskType,
    taskType,
    sourcePostId: asPositiveInteger(rawContext.source_post_id),
    prompt: asNonEmptyString(rawContext.prompt),
    negativePrompt: asNonEmptyString(rawContext.negative_prompt),
    loraName: asNonEmptyString(rawContext.lora_name),
    loraStrength: asNullableNumber(rawContext.lora_strength),
    loraItems: rawTaskType.startsWith('minimax_h3_')
      ? normalizeMinimaxH3LoraItems(rawContext.lora_items)
      : normalizeLtxVideoLoraItems(
          Array.isArray(rawContext.lora_items) ? rawContext.lora_items as Array<{ name?: string; strength?: number }> : [],
        ),
    referenceAudioRef: normalizeGalleryReferenceAudioRef(rawContext.reference_audio_ref),
    referenceAudioUrl: asNonEmptyString(rawContext.reference_audio_url),
    inputFile: asNonEmptyString(rawContext.input_file) ?? inputFiles[0] ?? null,
    inputFileUrl: asNonEmptyString(rawContext.input_file_url) ?? inputFileUrls[0] ?? null,
    inputFiles,
    inputFileUrls,
    width: asPositiveInteger(rawContext.width),
    height: asPositiveInteger(rawContext.height),
    duration: asPositiveInteger(rawContext.duration),
    requestedDuration: asPositiveInteger(rawContext.requested_duration),
    requiredImageCount: asPositiveInteger(rawContext.required_image_count),
    resolutionPreset: asNonEmptyString(rawContext.resolution_preset),
    aspectRatio: asNonEmptyString(rawContext.aspect_ratio),
    billingResolution: asNonEmptyString(rawContext.billing_resolution)
  }
}
