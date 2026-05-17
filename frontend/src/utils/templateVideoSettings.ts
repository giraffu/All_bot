export type TemplateVideoContext = {
  billing_resolution?: unknown
  width?: unknown
  height?: unknown
  duration?: unknown
  requested_duration?: unknown
  prompt?: unknown
  lora_name?: unknown
}

export type TemplateVideoSettings = {
  width: number
  height: number | null
  duration: number
}

const LTX_ALLOWED_DURATIONS = new Set([5, 10, 15, 20])
const LTX_ALLOWED_DURATION_VALUES = [5, 10, 15, 20]
const MAX_LEGACY_LTX_DURATION_DRIFT = 2
const TIER_VIDEO_ALLOWED_DURATIONS = new Set([5, 8, 10])
const TIER_VIDEO_ALLOWED_DURATION_VALUES = [5, 8, 10]
const MAX_LEGACY_TIER_VIDEO_DURATION_DRIFT = 2

export const toPositiveInteger = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const normalized = typeof value === 'string' ? value.trim() : value
  if (normalized === '') {
    return null
  }

  const parsed = Number(normalized)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null
  }

  return parsed
}

export const inferLegacyLtxRequestedDuration = (value: unknown): number | null => {
  const normalized = toPositiveInteger(value)
  if (normalized === null || normalized < LTX_ALLOWED_DURATION_VALUES[0]) {
    return null
  }

  const nearest = LTX_ALLOWED_DURATION_VALUES.reduce((closest, candidate) =>
    Math.abs(candidate - normalized) < Math.abs(closest - normalized) ? candidate : closest
  )

  return Math.abs(nearest - normalized) <= MAX_LEGACY_LTX_DURATION_DRIFT ? nearest : null
}

export const inferLegacyTierVideoRequestedDuration = (value: unknown): number | null => {
  const normalized = toPositiveInteger(value)
  if (normalized === null || normalized < TIER_VIDEO_ALLOWED_DURATION_VALUES[0]) {
    return null
  }

  const nearest = TIER_VIDEO_ALLOWED_DURATION_VALUES.reduce((closest, candidate) =>
    Math.abs(candidate - normalized) < Math.abs(closest - normalized) ? candidate : closest
  )

  return Math.abs(nearest - normalized) <= MAX_LEGACY_TIER_VIDEO_DURATION_DRIFT ? nearest : null
}

const hasNonEmptyString = (value: unknown): boolean =>
  typeof value === 'string' && value.trim() !== ''

const normalizeTierFromVideoSide = (side: number | null): string | null => {
  if (side === null || side <= 0) {
    return null
  }

  if (side >= 960) {
    return '1024'
  }

  if (side >= 700) {
    return '720'
  }

  return '512'
}

export const normalizePersistedTierBillingResolution = (value: unknown): string | null => {
  if (typeof value !== 'string') {
    return null
  }

  let normalized = value.trim().toLowerCase()
  if (normalized === '') {
    return null
  }

  if (normalized.endsWith('p')) {
    normalized = normalized.slice(0, -1)
  }

  if (normalized === '512' || normalized === '720' || normalized === '1024') {
    return normalized
  }

  const explicitResolution = /^(\d+)x(\d+)$/.exec(normalized)
  if (explicitResolution) {
    const width = Number(explicitResolution[1])
    const height = Number(explicitResolution[2])
    if (Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0) {
      return normalizeTierFromVideoSide(Math.min(width, height))
    }
  }

  const numeric = Number(normalized)
  if (Number.isInteger(numeric) && numeric > 0) {
    return normalizeTierFromVideoSide(numeric)
  }

  return null
}

export const resolveTierBillingResolution = (
  ctx: Pick<TemplateVideoContext, 'billing_resolution' | 'width' | 'height'>
): string | null => {
  const normalizedPersisted = normalizePersistedTierBillingResolution(ctx.billing_resolution)
  if (normalizedPersisted !== null) {
    return normalizedPersisted
  }

  const width = toPositiveInteger(ctx.width)
  const height = toPositiveInteger(ctx.height)
  const inferredSide =
    width !== null && height !== null ? Math.min(width, height) : (width ?? height)
  return normalizeTierFromVideoSide(inferredSide)
}

export const getTemplateVideoSettings = (
  ctx: TemplateVideoContext,
  requiresHeight = false,
  taskType?: string
): TemplateVideoSettings | null => {
  const width = toPositiveInteger(ctx?.width)
  const height = toPositiveInteger(ctx?.height)
  const requestedDuration = toPositiveInteger(ctx?.requested_duration)
  const mediaDuration = toPositiveInteger(ctx?.duration)
  const legacyCompatibleLtxDuration = inferLegacyLtxRequestedDuration(ctx?.duration)
  const legacyCompatibleTierDuration = inferLegacyTierVideoRequestedDuration(ctx?.duration)
  const duration =
    taskType === 'ltx_video'
      ? (requestedDuration && LTX_ALLOWED_DURATIONS.has(requestedDuration)
          ? requestedDuration
          : (mediaDuration && LTX_ALLOWED_DURATIONS.has(mediaDuration)
              ? mediaDuration
              : legacyCompatibleLtxDuration))
      : ((taskType === 'custom_video' || taskType === 'video_lora')
          ? (requestedDuration && TIER_VIDEO_ALLOWED_DURATIONS.has(requestedDuration)
              ? requestedDuration
              : (mediaDuration && TIER_VIDEO_ALLOWED_DURATIONS.has(mediaDuration)
                  ? mediaDuration
                  : legacyCompatibleTierDuration))
          : (requestedDuration ?? mediaDuration))

  if (width === null || duration === null) {
    return null
  }

  if (requiresHeight && height === null) {
    return null
  }

  return {
    width,
    height,
    duration
  }
}

export const canLockTemplateVideoPromptControls = (
  ctx: TemplateVideoContext,
  taskType: string
): boolean => {
  if (taskType === 'video_lora') {
    return hasNonEmptyString(ctx?.prompt) && hasNonEmptyString(ctx?.lora_name)
  }

  if (taskType === 'custom_video' || taskType === 'ltx_video') {
    return hasNonEmptyString(ctx?.prompt)
  }

  return false
}
