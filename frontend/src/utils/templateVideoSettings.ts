export type TemplateVideoContext = {
  width?: unknown
  height?: unknown
  duration?: unknown
  prompt?: unknown
  lora_name?: unknown
}

export type TemplateVideoSettings = {
  width: number
  height: number | null
  duration: number
}

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

const hasNonEmptyString = (value: unknown): boolean =>
  typeof value === 'string' && value.trim() !== ''

export const getTemplateVideoSettings = (
  ctx: TemplateVideoContext,
  requiresHeight = false
): TemplateVideoSettings | null => {
  const width = toPositiveInteger(ctx?.width)
  const height = toPositiveInteger(ctx?.height)
  const duration = toPositiveInteger(ctx?.duration)

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
