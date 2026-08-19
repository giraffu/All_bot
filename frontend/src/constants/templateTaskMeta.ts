import type { TemplateApplyTaskType, TemplateTaskMeta } from '@/types/templateApply'
import { isGenerationTaskTypeEnabled } from '@/config/generationFeatureAvailability'

const TEMPLATE_TASK_TYPE_ALIASES: Record<string, TemplateApplyTaskType> = {
  faceswap: 'face_swap',
  face_video: 'scail2_face_swap_v2',
  face_video_step1: 'scail2_face_swap_v2',
  face_video_step2: 'scail2_face_swap_v2',
  ltx_video_flf2v: 'ltx_video',
  scail2_action_transfer_long: 'scail2_action_transfer',
  pornmaster_flux2_single_edit: 'pornmaster_flux2_edit_bf16',
  pornmaster_flux2_multi_edit: 'pornmaster_flux2_edit_bf16'
}

const WEB_DISABLED_TEMPLATE_TASK_TYPES = new Set<string>(['i2i_draw'])

export const TEMPLATE_TASK_META_MAP: Record<TemplateApplyTaskType, TemplateTaskMeta> = {
  i2i_pro: {
    taskType: 'i2i_pro',
    panelKind: 'imagePrompt',
    titleKey: 'lab.cards.i2i_pro_title'
  },
  i2i_draw: {
    taskType: 'i2i_draw',
    panelKind: 'imagePrompt',
    titleKey: 'lab.cards.i2i_draw_title'
  },
  edit: {
    taskType: 'edit',
    panelKind: 'imagePrompt',
    titleKey: 'lab.cards.custom_edit_title'
  },
  img2img_lora: {
    taskType: 'img2img_lora',
    panelKind: 'imagePrompt',
    titleKey: 'lab.cards.custom_edit_title'
  },
  free_edit_v2_5: {
    taskType: 'free_edit_v2_5',
    panelKind: 'imagePrompt',
    titleKey: 'lab.cards.custom_edit_v2_5_title'
  },
  pornmaster_flux2_edit_bf16: {
    taskType: 'pornmaster_flux2_edit_bf16',
    panelKind: 'imagePrompt',
    titleKey: 'lab.cards.custom_edit_v3_title'
  },
  face_swap: {
    taskType: 'face_swap',
    panelKind: 'faceSwap',
    titleKey: 'lab.cards.fast_face_swap_title'
  },
  face_video: {
    taskType: 'face_video',
    panelKind: 'videoSwap',
    titleKey: 'lab.cards.video_face_swap_title'
  },
  custom_video: {
    taskType: 'custom_video',
    panelKind: 'imageToVideo',
    titleKey: 'lab.cards.custom_video_title'
  },
  video_lora: {
    taskType: 'video_lora',
    panelKind: 'imageToVideo',
    titleKey: 'lab.cards.custom_video_title'
  },
  wan22_video_v2: {
    taskType: 'wan22_video_v2',
    panelKind: 'imageToVideo',
    titleKey: 'lab.cards.wan22_video_v2_title'
  },
  ltx_video: {
    taskType: 'ltx_video',
    panelKind: 'imageToVideo',
    titleKey: 'lab.cards.high_res_video_title'
  },
  minimax_h3_i2v: {
    taskType: 'minimax_h3_i2v',
    panelKind: 'advancedVideoPro',
    titleKey: 'lab.cards.minimax_h3_title'
  },
  minimax_h3_flf2v: {
    taskType: 'minimax_h3_flf2v',
    panelKind: 'advancedVideoPro',
    titleKey: 'lab.cards.minimax_h3_title'
  },
  scail2_action_transfer: {
    taskType: 'scail2_action_transfer',
    panelKind: 'scail2Video',
    titleKey: 'lab.cards.scail2_action_transfer_title'
  },
  scail2_action_transfer_long: {
    taskType: 'scail2_action_transfer',
    panelKind: 'scail2Video',
    titleKey: 'lab.cards.scail2_action_transfer_title'
  },
  scail2_video_replacement: {
    taskType: 'scail2_video_replacement',
    panelKind: 'scail2Video',
    titleKey: 'lab.cards.scail2_video_replacement_title'
  },
  scail2_face_swap_v2: {
    taskType: 'scail2_face_swap_v2',
    panelKind: 'scail2Video',
    titleKey: 'lab.cards.scail2_face_swap_v2_title'
  }
}

export const getCanonicalTemplateTaskType = (taskType: string): TemplateApplyTaskType | null => {
  if (
    WEB_DISABLED_TEMPLATE_TASK_TYPES.has(taskType)
    || !isGenerationTaskTypeEnabled(taskType)
  ) {
    return null
  }

  const normalizedTaskType = TEMPLATE_TASK_TYPE_ALIASES[taskType] ?? taskType
  if (
    WEB_DISABLED_TEMPLATE_TASK_TYPES.has(normalizedTaskType)
    || !isGenerationTaskTypeEnabled(normalizedTaskType)
  ) {
    return null
  }

  return TEMPLATE_TASK_META_MAP[normalizedTaskType as TemplateApplyTaskType]
    ? (normalizedTaskType as TemplateApplyTaskType)
    : null
}

export const getTemplateTaskMeta = (taskType: string): TemplateTaskMeta | null =>
  (() => {
    const canonicalTaskType = getCanonicalTemplateTaskType(taskType)
    return canonicalTaskType ? TEMPLATE_TASK_META_MAP[canonicalTaskType] : null
  })()
