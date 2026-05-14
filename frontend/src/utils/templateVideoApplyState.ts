import {
  canLockTemplateVideoPromptControls,
  getTemplateVideoSettings,
  toPositiveInteger,
  type TemplateVideoContext
} from './templateVideoSettings.ts'

type SupportedVideoTaskType = 'custom_video' | 'video_lora' | 'ltx_video'

export type TemplateVideoApplyContext = TemplateVideoContext & {
  task_type?: unknown
  source_post_id?: unknown
  billing_resolution?: unknown
}

export type ResolvedTemplateVideoApplyState = {
  prompt: string | null
  loraName: string | null
  sourcePostId: number | null
  resolution: string | null
  duration: string | null
  isTemplateApplied: boolean
  isTemplateVideoSettingsLocked: boolean
  isTemplatePromptLocked: boolean
  templateApplyNotice: string
  templateSettingsWarning: string
}

const hasNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim() !== ''

const normalizeTierFromLongestSide = (longestSide: number | null): string | null => {
  if (longestSide === null || longestSide <= 0) {
    return null
  }
  if (longestSide >= 960) {
    return '1024'
  }
  if (longestSide >= 700) {
    return '720'
  }
  return '512'
}

const normalizePersistedTierBillingResolution = (value: unknown): string | null => {
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
      return normalizeTierFromLongestSide(Math.max(width, height))
    }
  }

  const numeric = Number(normalized)
  if (Number.isInteger(numeric) && numeric > 0) {
    return normalizeTierFromLongestSide(numeric)
  }

  return null
}

const resolveTierBillingResolution = (ctx: TemplateVideoApplyContext): string | null => {
  const normalizedPersisted = normalizePersistedTierBillingResolution(ctx.billing_resolution)
  if (normalizedPersisted !== null) {
    return normalizedPersisted
  }

  const width = toPositiveInteger(ctx.width)
  const height = toPositiveInteger(ctx.height)
  return normalizeTierFromLongestSide(Math.max(width ?? 0, height ?? 0) || null)
}

const getTemplateApplyNotice = (
  isTemplateVideoSettingsLocked: boolean,
  isTemplatePromptLocked: boolean
): string => {
  if (isTemplateVideoSettingsLocked && isTemplatePromptLocked) {
    return '已加载一键应用模板，原作品的提示词、分辨率与时长等参数已自动填入，您只需上传基础图片即可生成同款大片。'
  }

  if (isTemplateVideoSettingsLocked) {
    return '已加载一键应用模板，分辨率与时长已按原作品恢复；模板缺少完整的提示词或模型信息，您仍可手动调整相关参数。'
  }

  if (isTemplatePromptLocked) {
    return '已加载一键应用模板，原作品的提示词已自动填入；由于模板缺少完整画质信息，您仍可手动选择分辨率与时长。'
  }

  return '已加载一键应用模板，但模板信息不完整，您仍可手动调整提示词、模型、分辨率与时长。'
}

export const resolveTemplateVideoApplyState = (
  ctx: TemplateVideoApplyContext,
  taskType: SupportedVideoTaskType
): ResolvedTemplateVideoApplyState | null => {
  if (ctx?.task_type !== taskType) {
    return null
  }

  const warnings: string[] = []
  const isLtxVideo = taskType === 'ltx_video'
  const isTemplatePromptLocked = canLockTemplateVideoPromptControls(ctx, taskType)
  const templateVideoSettings = getTemplateVideoSettings(ctx, isLtxVideo)
  const isTemplateVideoSettingsLocked = templateVideoSettings !== null
  const tierBillingResolution = isLtxVideo ? null : resolveTierBillingResolution(ctx)

  if (!templateVideoSettings) {
    warnings.push('模板缺少完整的分辨率或时长信息，已保留当前画质设置供您手动调整。')
  }

  if (!isTemplatePromptLocked) {
    warnings.push('模板缺少完整的提示词或模型信息，相关输入项已保留供您手动调整。')
  }

  return {
    prompt: hasNonEmptyString(ctx.prompt) ? ctx.prompt : null,
    loraName: hasNonEmptyString(ctx.lora_name) ? ctx.lora_name : null,
    sourcePostId: toPositiveInteger(ctx.source_post_id),
    resolution: templateVideoSettings
      ? (isLtxVideo
          ? `${templateVideoSettings.width}x${templateVideoSettings.height}`
          : (tierBillingResolution ?? String(templateVideoSettings.width)))
      : null,
    duration: templateVideoSettings ? String(templateVideoSettings.duration) : null,
    isTemplateApplied: true,
    isTemplateVideoSettingsLocked,
    isTemplatePromptLocked,
    templateApplyNotice: getTemplateApplyNotice(
      isTemplateVideoSettingsLocked,
      isTemplatePromptLocked
    ),
    templateSettingsWarning: warnings.join(' ')
  }
}
