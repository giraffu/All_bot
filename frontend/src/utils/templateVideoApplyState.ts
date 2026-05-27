import { normalizeLtxVideoLoraItems, type LtxVideoLoraItem } from '@/features/generation/imageToVideo'
import {
  canLockTemplateVideoPromptControls,
  getTemplateVideoSettings,
  resolveTierBillingResolution,
  toPositiveInteger,
  type TemplateVideoContext
} from './templateVideoSettings.ts'
import i18n from '@/i18n'

type SupportedVideoTaskType = 'custom_video' | 'video_lora' | 'ltx_video'

export type TemplateVideoApplyContext = TemplateVideoContext & {
  task_type?: unknown
  source_post_id?: unknown
  billing_resolution?: unknown
}

export type ResolvedTemplateVideoApplyState = {
  prompt: string | null
  loraName: string | null
  loraItems: LtxVideoLoraItem[]
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

const t = (key: string) => i18n.global.t(key)

const getTemplateApplyNotice = (
  isTemplateVideoSettingsLocked: boolean,
  isTemplatePromptLocked: boolean
): string => {
  if (isTemplateVideoSettingsLocked && isTemplatePromptLocked) {
    return t('template_apply.image_to_video.template_notice_complete')
  }

  if (isTemplateVideoSettingsLocked) {
    return t('template_apply.image_to_video.template_notice_settings_only')
  }

  if (isTemplatePromptLocked) {
    return t('template_apply.image_to_video.template_notice_prompt_only')
  }

  return t('template_apply.image_to_video.template_notice_partial')
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
  const templateVideoSettings = getTemplateVideoSettings(ctx, isLtxVideo, taskType)
  const isTemplateVideoSettingsLocked = templateVideoSettings !== null
  const tierBillingResolution = isLtxVideo ? null : resolveTierBillingResolution(ctx)

  if (!templateVideoSettings) {
    warnings.push(t('template_apply.image_to_video.settings_missing'))
  }

  if (!isTemplatePromptLocked) {
    warnings.push(t('template_apply.image_to_video.prompt_missing'))
  }

  return {
    prompt: hasNonEmptyString(ctx.prompt) ? ctx.prompt : null,
    loraName: hasNonEmptyString(ctx.lora_name) ? ctx.lora_name : null,
    loraItems: taskType === 'ltx_video'
      ? normalizeLtxVideoLoraItems(
          Array.isArray((ctx as { lora_items?: unknown }).lora_items)
            ? ((ctx as { lora_items?: Array<{ name?: string; strength?: number }> }).lora_items ?? [])
            : hasNonEmptyString((ctx as { lora_name?: unknown }).lora_name)
              ? [{
                  name: String((ctx as { lora_name?: unknown }).lora_name),
                  strength: typeof (ctx as { lora_strength?: unknown }).lora_strength === 'number'
                    ? (ctx as { lora_strength?: number }).lora_strength
                    : undefined
                }]
              : []
        )
      : [],
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
