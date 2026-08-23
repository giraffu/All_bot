import type { PromptTarget } from './buildGenerationTaskPayload'
import { getRuntimeFlag } from '@/config/runtime'
import {
  DEFAULT_WAN22_VIDEO_V2_COST,
  IMAGE_TO_VIDEO_LORA_OPTIONS,
  NO_IMAGE_TO_VIDEO_LORA,
} from './imageToVideo'

export type UnifiedLabModeId =
  | 'character_reference'
  | 'edit'
  | 'edit_v2_5'
  | 'edit_v3'
  | 'txt2img'
  | 'i2i_pro'
  | 'i2i_draw'
  | 'custom_video'
  | 'face_swap'
  | 'random_faceswap'
  | 'face_video'
  | 'ltx_video'
  | 'ltx_video_v2'
  | 'ltx_t2v'
  | 'minimax_h3'
  | 'wan22_video_v2'
  | 'scail2_action_transfer'
  | 'scail2_video_replacement'
  | 'scail2_face_swap_v2'

export type LabModeId = UnifiedLabModeId
export type LabUploadSlotId =
  | 'face_image'
  | 'target_image'
  | 'target_video'
  | 'reference_image'
  | 'motion_video'
export type LabUploadPreviewKind = 'image' | 'video'

export interface LabUploadSlotConfig {
  id: LabUploadSlotId
  labelKey: string
  hintKey: string
  buttonKey: string
  accept: string
  previewKind: LabUploadPreviewKind
  required: boolean
}

export interface LabModeConfig {
  id: LabModeId
  taskType: string
  titleKey: string
  descriptionKey: string
  kindKey: string
  baseCost: number
  promptPlaceholderKey: string
  promptTarget: PromptTarget
  submitLabelKey: string
  referenceTitleKey?: string
  maxImages: number
  supportsUpload: boolean
  supportsEditLora: boolean
  supportsVideoOptions: boolean
  supportsVideoLora?: boolean
  supportsLtxLoraItems?: boolean
  supportsDurationOptions?: boolean
  supportsNegativePrompt?: boolean
  supportsResolutionOptions?: boolean
  supportsWan22ResolutionPreset?: boolean
  supportsAdvancedOptions: boolean
  supportsPromptInput?: boolean
  promptRequired: boolean
  unified: boolean
  uploadSlots?: readonly LabUploadSlotConfig[]
}

export interface MiniMaxH3AddonItem {
  name: string
  strength: number
}

export type MiniMaxH3Mode = 't2v' | 'i2v' | 'flf2v' | 'ref2v'

export interface MiniMaxH3AddonOption {
  value: string
  labelKey: string
  defaultStrength: number
  supportedModes?: readonly MiniMaxH3Mode[]
}

export const MINIMAX_H3_ADDON_OPTIONS = [
  { value: 'naughty_times', labelKey: 'lab.workbench.minimax_h3_addon_options.naughty_times', defaultStrength: 1.0 },
  { value: 'sex_pose', labelKey: 'lab.workbench.minimax_h3_addon_options.sex_pose', defaultStrength: 0.5 },
  { value: 'motion_booster', labelKey: 'lab.workbench.minimax_h3_addon_options.motion_booster', defaultStrength: 0.7 },
  {
    value: 'motion_booster_ref2va',
    labelKey: 'lab.workbench.minimax_h3_addon_options.motion_booster_ref2va',
    defaultStrength: 0.7,
    supportedModes: ['ref2v'] as readonly MiniMaxH3Mode[],
  },
  { value: 'mystic_xxx', labelKey: 'lab.workbench.minimax_h3_addon_options.mystic_xxx', defaultStrength: 0.75 },
  { value: 'breast_play', labelKey: 'lab.workbench.minimax_h3_addon_options.breast_play', defaultStrength: 0.75 },
  { value: 'innie', labelKey: 'lab.workbench.minimax_h3_addon_options.innie', defaultStrength: 0.8 },
  { value: 'deepthroat', labelKey: 'lab.workbench.minimax_h3_addon_options.deepthroat', defaultStrength: 0.75 },
  { value: 'pov_missionary', labelKey: 'lab.workbench.minimax_h3_addon_options.pov_missionary', defaultStrength: 0.7 },
  { value: 'footjob', labelKey: 'lab.workbench.minimax_h3_addon_options.footjob', defaultStrength: 0.5 },
  { value: 'breasts', labelKey: 'lab.workbench.minimax_h3_addon_options.breasts', defaultStrength: 1.0 },
  { value: 'vagassist', labelKey: 'lab.workbench.minimax_h3_addon_options.vagassist', defaultStrength: 1.0 },
  { value: 'pussy', labelKey: 'lab.workbench.minimax_h3_addon_options.pussy', defaultStrength: 0.35 },
  { value: 'penis', labelKey: 'lab.workbench.minimax_h3_addon_options.penis', defaultStrength: 1.0 },
  { value: 'cumshot', labelKey: 'lab.workbench.minimax_h3_addon_options.cumshot', defaultStrength: 0.9 },
  { value: 'pussy_stills_v1', labelKey: 'lab.workbench.minimax_h3_addon_options.pussy_stills_v1', defaultStrength: 0.35 },
  { value: 'titjob', labelKey: 'lab.workbench.minimax_h3_addon_options.titjob', defaultStrength: 0.75 },
] as const satisfies readonly MiniMaxH3AddonOption[]

export const getMiniMaxH3AddonOptionsForMode = (mode: MiniMaxH3Mode) =>
  MINIMAX_H3_ADDON_OPTIONS.filter(option => (
    !('supportedModes' in option) || option.supportedModes.includes(mode)
  ))

export const EDIT_LORA_OPTIONS = [
  { value: '', label: '无' },
  { value: 'qwen/YARN_1.0.safetensors', label: '逼真' },
  { value: 'qwen/adjust_pussy_anus.safetensors', label: '菊花+内凹穴' },
  { value: 'qwen/realistic_texture.safetensors', label: '真实质感' },
  { value: 'qwen/flat_chest_hairless.safetensors', label: '平胸/无毛穴' },
  { value: 'qwen/penis.safetensors', label: '扶他(阴茎)' },
] as const

export const EDIT_LORA_DEFAULT_STRENGTHS: Record<string, number> = {
  'qwen/YARN_1.0.safetensors': 0.3,
  'qwen/adjust_pussy_anus.safetensors': 1.0,
  'qwen/realistic_texture.safetensors': 0.8,
  'qwen/flat_chest_hairless.safetensors': 0.8,
  'qwen/penis.safetensors': 0.7,
}

export const VIDEO_RESOLUTION_OPTIONS = [
  { value: '512', label: '512p' },
  { value: '720', label: '720p' },
  { value: '1024', label: '1024p' },
] as const

export const VIDEO_DURATION_OPTIONS = [
  { value: '5', label: '5 秒' },
  { value: '8', label: '8 秒' },
  { value: '10', label: '10 秒' },
] as const

export const LTX_VIDEO_RESOLUTION_OPTIONS = [
  { value: '1280x704', label: '1280x704' },
] as const

export const LTX_T2V_IC_RESOLUTION_OPTIONS = [
  { value: '768x448', label: '768x448' },
] as const

export const LTX_VIDEO_DURATION_OPTIONS = [
  { value: '5', label: '5 秒' },
  { value: '10', label: '10 秒' },
  { value: '15', label: '15 秒' },
  { value: '20', label: '20 秒' },
] as const

export const SCAIL2_VIDEO_DURATION_OPTIONS = [
  { value: '5', label: '5 秒' },
  { value: '8', label: '8 秒' },
  { value: '10', label: '10 秒' },
  { value: '15', label: '15 秒' },
  { value: '20', label: '20 秒' },
] as const

export const SCAIL2_SHORT_VIDEO_DURATION_OPTIONS = [
  { value: '5', label: '5 秒' },
  { value: '8', label: '8 秒' },
] as const

const SCAIL2_ACTION_TRANSFER_COST_BY_DURATION: Record<number, number> = {
  5: 40,
  8: 80,
  10: 120,
  15: 180,
  20: 260,
}

const isScail2ActionTransferModeId = (modeId?: string) => (
  !modeId
  || modeId === 'scail2_action_transfer'
  || modeId === 'scail2_action_transfer_long'
)

export const getScail2VideoDurationOptionsForMotionVideo = (
  motionVideoDurationSeconds: number | null | undefined,
  modeId?: string,
) => {
  const options = isScail2ActionTransferModeId(modeId)
    ? SCAIL2_VIDEO_DURATION_OPTIONS
    : SCAIL2_SHORT_VIDEO_DURATION_OPTIONS

  if (
    typeof motionVideoDurationSeconds !== 'number'
    || !Number.isFinite(motionVideoDurationSeconds)
  ) {
    return options.filter(option => option.value === '5')
  }

  const availableOptions = options.filter(
    option => Number(option.value) <= motionVideoDurationSeconds,
  )
  return availableOptions.length > 0
    ? availableOptions
    : options.filter(option => option.value === '5')
}

export const getScail2VideoCost = (duration: string | number, modeId?: string) => {
  const normalizedDuration = Number(String(duration).replace(/s$/i, ''))
  if (!isScail2ActionTransferModeId(modeId)) {
    return normalizedDuration === 8 ? 80 : 40
  }
  return SCAIL2_ACTION_TRANSFER_COST_BY_DURATION[normalizedDuration] ?? 40
}

export const DEFAULT_VIDEO_RESOLUTION = '512'
export const DEFAULT_FACE_VIDEO_RESOLUTION = '720'
export const DEFAULT_LTX_VIDEO_RESOLUTION = '1280x704'
export const DEFAULT_VIDEO_DURATION = '5'

export const FACE_VIDEO_RESOLUTION_OPTIONS = [
  { value: '720', label: '720p' },
  { value: '1024', label: '1024p' },
] as const

export const FREE_EDIT_V2_5_MODE_ID = 'edit_v2_5' as const
export const FREE_EDIT_V3_MODE_ID = 'edit_v3' as const
export const FREE_EDIT_V3_ENABLED = getRuntimeFlag('enable_free_edit_v3', true)
export const FREE_EDIT_V2_5_ENABLED = FREE_EDIT_V3_ENABLED
export const WEB_I2I_DRAW_ENABLED = false
export const WEB_LTX_VIDEO_ENABLED = getRuntimeFlag('enable_ltx_video', true)
export const WEB_LTX_T2V_ENABLED = getRuntimeFlag('enable_ltx_t2v', false)
export const WEB_LTX_VIDEO_V2_ENABLED = getRuntimeFlag('enable_ltx_video_v2', false)
export const WEB_CHARACTER_ASSETS_ENABLED = getRuntimeFlag('enable_character_assets', false)
export const WEB_CHARACTER_ASSETS_ENTRY_ENABLED = getRuntimeFlag(
  'enable_character_assets_entry',
  WEB_CHARACTER_ASSETS_ENABLED,
)
export const WEB_CHARACTER_EXPLICIT_VIEWS_ENABLED = getRuntimeFlag('enable_character_explicit_views', false)
export const WEB_MINIMAX_H3_ENABLED = getRuntimeFlag('enable_minimax_h3', false)
export const WEB_MINIMAX_H3_ENTRY_ENABLED = getRuntimeFlag('enable_minimax_h3_entry', false)
export const WEB_MINIMAX_H3_REF2V_ENABLED = getRuntimeFlag('enable_minimax_h3_ref2v', false)
export const PORNMASTER_FLUX2_SINGLE_EDIT_TASK_TYPE = 'pornmaster_flux2_single_edit'
export const PORNMASTER_FLUX2_MULTI_EDIT_TASK_TYPE = 'pornmaster_flux2_multi_edit'
export const PORNMASTER_FLUX2_EDIT_BF16_TASK_TYPE = 'pornmaster_flux2_edit_bf16'
export const FREE_EDIT_V2_5_TASK_TYPE = 'free_edit_v2_5'

export const LAB_MODE_CONFIGS: LabModeConfig[] = [
  {
    id: 'character_reference',
    taskType: 'character_reference',
    titleKey: 'lab.cards.character_reference_title',
    descriptionKey: 'lab.cards.character_reference_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 3,
    promptPlaceholderKey: 'characters.view_prompt_placeholder',
    promptTarget: 'inputs',
    submitLabelKey: 'characters.generate_view',
    referenceTitleKey: 'lab.workbench.reference_titles.scene_background',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    supportsPromptInput: false,
    promptRequired: false,
    unified: true,
  },
  {
    id: 'edit',
    taskType: 'edit',
    titleKey: 'lab.cards.custom_edit_title',
    descriptionKey: 'lab.cards.custom_edit_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 2,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.edit',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_image',
    referenceTitleKey: 'template_apply.common.base_image',
    maxImages: 2,
    supportsUpload: true,
    supportsEditLora: true,
    supportsVideoOptions: false,
    supportsAdvancedOptions: true,
    promptRequired: true,
    unified: true,
  },
  {
    id: FREE_EDIT_V2_5_MODE_ID,
    taskType: FREE_EDIT_V2_5_TASK_TYPE,
    titleKey: 'lab.cards.custom_edit_v2_5_title',
    descriptionKey: 'lab.cards.custom_edit_v2_5_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 3,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.edit_v2_5',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_image',
    referenceTitleKey: 'template_apply.common.base_image',
    maxImages: 2,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    promptRequired: true,
    unified: true,
  },
  {
    id: FREE_EDIT_V3_MODE_ID,
    taskType: PORNMASTER_FLUX2_EDIT_BF16_TASK_TYPE,
    titleKey: 'lab.cards.custom_edit_v3_title',
    descriptionKey: 'lab.cards.custom_edit_v3_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 5,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.edit_v3',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_image',
    referenceTitleKey: 'template_apply.common.base_image',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    promptRequired: true,
    unified: true,
  },
  {
    id: 'txt2img',
    taskType: 'txt2img',
    titleKey: 'lab.cards.txt2img_title',
    descriptionKey: 'lab.cards.txt2img_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 2,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.txt2img',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_image',
    maxImages: 0,
    supportsUpload: false,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    promptRequired: true,
    unified: true,
  },
  {
    id: 'i2i_pro',
    taskType: 'i2i_pro',
    titleKey: 'lab.cards.i2i_pro_title',
    descriptionKey: 'lab.cards.i2i_pro_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 6,
    promptPlaceholderKey: 'template_apply.image_prompt.prompt_placeholder',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_image',
    referenceTitleKey: 'lab.workbench.reference_titles.portrait',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    promptRequired: false,
    unified: true,
  },
  {
    id: 'i2i_draw',
    taskType: 'i2i_draw',
    titleKey: 'lab.cards.i2i_draw_title',
    descriptionKey: 'lab.cards.i2i_draw_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 3,
    promptPlaceholderKey: 'template_apply.image_prompt.prompt_placeholder',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_image',
    referenceTitleKey: 'template_apply.common.base_image',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    promptRequired: false,
    unified: true,
  },
  {
    id: 'custom_video',
    taskType: 'custom_video',
    titleKey: 'lab.cards.custom_video_title',
    descriptionKey: 'lab.cards.custom_video_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: DEFAULT_WAN22_VIDEO_V2_COST,
    promptPlaceholderKey: 'template_apply.image_to_video.prompt_placeholder_custom',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    referenceTitleKey: 'lab.workbench.reference_titles.start_frame',
    maxImages: 2,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsDurationOptions: true,
    supportsNegativePrompt: true,
    supportsWan22ResolutionPreset: true,
    supportsAdvancedOptions: true,
    promptRequired: false,
    unified: true,
  },
  {
    id: 'face_swap',
    taskType: 'face_swap',
    titleKey: 'lab.cards.fast_face_swap_title',
    descriptionKey: 'lab.cards.fast_face_swap_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 2,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.edit',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_face_swap',
    maxImages: 0,
    supportsUpload: false,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    promptRequired: false,
    unified: true,
    uploadSlots: [
      {
        id: 'face_image',
        labelKey: 'lab.workbench.upload_slots.face_image',
        hintKey: 'lab.workbench.upload_slot_hints.face_image',
        buttonKey: 'lab.workbench.upload_slot_buttons.face_image',
        accept: 'image/png,image/jpeg,image/webp',
        previewKind: 'image',
        required: true,
      },
      {
        id: 'target_image',
        labelKey: 'lab.workbench.upload_slots.target_image',
        hintKey: 'lab.workbench.upload_slot_hints.target_image',
        buttonKey: 'lab.workbench.upload_slot_buttons.target_image',
        accept: 'image/png,image/jpeg,image/webp',
        previewKind: 'image',
        required: true,
      },
    ],
  },
  {
    id: 'random_faceswap',
    taskType: 'random_faceswap',
    titleKey: 'lab.cards.random_faceswap_title',
    descriptionKey: 'lab.cards.random_faceswap_desc',
    kindKey: 'lab.workbench.mode_kinds.image',
    baseCost: 2,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.edit',
    promptTarget: 'topLevel',
    submitLabelKey: 'lab.workbench.submit_image',
    referenceTitleKey: 'lab.workbench.reference_titles.portrait',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    supportsPromptInput: false,
    promptRequired: false,
    unified: true,
  },
  {
    id: 'face_video',
    taskType: 'face_video',
    titleKey: 'lab.cards.video_face_swap_title',
    descriptionKey: 'lab.cards.video_face_swap_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 18,
    promptPlaceholderKey: 'template_apply.image_to_video.prompt_placeholder_custom',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_face_swap',
    maxImages: 0,
    supportsUpload: false,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsDurationOptions: false,
    supportsAdvancedOptions: true,
    promptRequired: false,
    unified: true,
    uploadSlots: [
      {
        id: 'face_image',
        labelKey: 'lab.workbench.upload_slots.face_image',
        hintKey: 'lab.workbench.upload_slot_hints.face_image',
        buttonKey: 'lab.workbench.upload_slot_buttons.face_image',
        accept: 'image/png,image/jpeg,image/webp',
        previewKind: 'image',
        required: true,
      },
      {
        id: 'target_video',
        labelKey: 'lab.workbench.upload_slots.target_video',
        hintKey: 'lab.workbench.upload_slot_hints.target_video',
        buttonKey: 'lab.workbench.upload_slot_buttons.target_video',
        accept: 'video/mp4,video/quicktime,video/webm',
        previewKind: 'video',
        required: true,
      },
    ],
  },
  {
    id: 'scail2_action_transfer',
    taskType: 'scail2_action_transfer',
    titleKey: 'lab.cards.scail2_action_transfer_title',
    descriptionKey: 'lab.cards.scail2_action_transfer_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 40,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.scail2_action_transfer',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    maxImages: 0,
    supportsUpload: false,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsDurationOptions: true,
    supportsNegativePrompt: true,
    supportsResolutionOptions: false,
    supportsAdvancedOptions: true,
    promptRequired: false,
    unified: true,
    uploadSlots: [
      {
        id: 'reference_image',
        labelKey: 'lab.workbench.upload_slots.reference_image',
        hintKey: 'lab.workbench.upload_slot_hints.reference_image',
        buttonKey: 'lab.workbench.upload_slot_buttons.reference_image',
        accept: 'image/png,image/jpeg,image/webp',
        previewKind: 'image',
        required: true,
      },
      {
        id: 'motion_video',
        labelKey: 'lab.workbench.upload_slots.motion_video',
        hintKey: 'lab.workbench.upload_slot_hints.motion_video',
        buttonKey: 'lab.workbench.upload_slot_buttons.motion_video',
        accept: 'video/mp4,video/quicktime,video/webm',
        previewKind: 'video',
        required: true,
      },
    ],
  },
  {
    id: 'scail2_video_replacement',
    taskType: 'scail2_video_replacement',
    titleKey: 'lab.cards.scail2_video_replacement_title',
    descriptionKey: 'lab.cards.scail2_video_replacement_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 40,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.scail2_video_replacement',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    maxImages: 0,
    supportsUpload: false,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsDurationOptions: true,
    supportsNegativePrompt: true,
    supportsResolutionOptions: false,
    supportsAdvancedOptions: true,
    promptRequired: false,
    unified: true,
    uploadSlots: [
      {
        id: 'reference_image',
        labelKey: 'lab.workbench.upload_slots.reference_image',
        hintKey: 'lab.workbench.upload_slot_hints.reference_image',
        buttonKey: 'lab.workbench.upload_slot_buttons.reference_image',
        accept: 'image/png,image/jpeg,image/webp',
        previewKind: 'image',
        required: true,
      },
      {
        id: 'motion_video',
        labelKey: 'lab.workbench.upload_slots.motion_video',
        hintKey: 'lab.workbench.upload_slot_hints.motion_video',
        buttonKey: 'lab.workbench.upload_slot_buttons.motion_video',
        accept: 'video/mp4,video/quicktime,video/webm',
        previewKind: 'video',
        required: true,
      },
    ],
  },
  {
    id: 'scail2_face_swap_v2',
    taskType: 'scail2_face_swap_v2',
    titleKey: 'lab.cards.scail2_face_swap_v2_title',
    descriptionKey: 'lab.cards.scail2_face_swap_v2_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 40,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.scail2_face_swap_v2',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    maxImages: 0,
    supportsUpload: false,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsDurationOptions: true,
    supportsNegativePrompt: true,
    supportsResolutionOptions: false,
    supportsAdvancedOptions: true,
    promptRequired: false,
    unified: true,
    uploadSlots: [
      {
        id: 'reference_image',
        labelKey: 'lab.workbench.upload_slots.reference_image',
        hintKey: 'lab.workbench.upload_slot_hints.reference_image',
        buttonKey: 'lab.workbench.upload_slot_buttons.reference_image',
        accept: 'image/png,image/jpeg,image/webp',
        previewKind: 'image',
        required: true,
      },
      {
        id: 'motion_video',
        labelKey: 'lab.workbench.upload_slots.motion_video',
        hintKey: 'lab.workbench.upload_slot_hints.motion_video',
        buttonKey: 'lab.workbench.upload_slot_buttons.motion_video',
        accept: 'video/mp4,video/quicktime,video/webm',
        previewKind: 'video',
        required: true,
      },
    ],
  },
  {
    id: 'ltx_video',
    taskType: 'ltx_video',
    titleKey: 'lab.cards.high_res_video_title',
    descriptionKey: 'lab.cards.high_res_video_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 10,
    promptPlaceholderKey: 'template_apply.image_to_video.prompt_placeholder_custom',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    referenceTitleKey: 'lab.workbench.reference_titles.start_frame',
    maxImages: 2,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsLtxLoraItems: true,
    supportsNegativePrompt: true,
    supportsAdvancedOptions: true,
    promptRequired: false,
    unified: true,
  },
  {
    id: 'ltx_video_v2',
    taskType: 'ltx_video_v2',
    titleKey: 'lab.cards.high_res_video_v2_title',
    descriptionKey: 'lab.cards.high_res_video_v2_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 10,
    promptPlaceholderKey: 'template_apply.image_to_video.prompt_placeholder_custom',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    referenceTitleKey: 'lab.workbench.reference_titles.start_frame',
    maxImages: 2,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsLtxLoraItems: false,
    supportsNegativePrompt: true,
    supportsAdvancedOptions: true,
    promptRequired: false,
    unified: true,
  },
  {
    id: 'ltx_t2v',
    taskType: 'ltx_t2v',
    titleKey: 'lab.cards.ltx_t2v_title',
    descriptionKey: 'lab.cards.ltx_t2v_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 10,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.ltx_t2v',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsDurationOptions: true,
    supportsNegativePrompt: true,
    supportsAdvancedOptions: true,
    promptRequired: true,
    unified: true,
  },
  {
    id: 'minimax_h3',
    taskType: 'minimax_h3_t2v',
    titleKey: 'lab.cards.minimax_h3_title',
    descriptionKey: 'lab.cards.minimax_h3_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 10,
    promptPlaceholderKey: 'lab.workbench.prompt_placeholders.minimax_h3',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    referenceTitleKey: 'lab.workbench.minimax_h3_references',
    maxImages: 4,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsDurationOptions: true,
    supportsAdvancedOptions: false,
    promptRequired: true,
    unified: true,
  },
  {
    id: 'wan22_video_v2',
    taskType: 'wan22_video_v2',
    titleKey: 'lab.cards.wan22_video_v2_title',
    descriptionKey: 'lab.cards.wan22_video_v2_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: DEFAULT_WAN22_VIDEO_V2_COST,
    promptPlaceholderKey: 'template_apply.image_to_video.prompt_placeholder_custom',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    referenceTitleKey: 'lab.workbench.reference_titles.start_frame',
    maxImages: 2,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsDurationOptions: true,
    supportsNegativePrompt: true,
    supportsWan22ResolutionPreset: true,
    supportsAdvancedOptions: true,
    promptRequired: true,
    unified: true,
  },
]

export const LAB_MODE_CONFIG_MAP = Object.fromEntries(
  LAB_MODE_CONFIGS.map((mode) => [mode.id, mode]),
) as Record<LabModeId, LabModeConfig>

export const DEFAULT_LAB_MODE_ID: UnifiedLabModeId = 'edit'

export const UNIFIED_LAB_MODES = LAB_MODE_CONFIGS.filter(mode => (
  mode.unified
  && mode.id !== 'face_video'
  && (mode.id !== FREE_EDIT_V2_5_MODE_ID || FREE_EDIT_V2_5_ENABLED)
  && (mode.id !== FREE_EDIT_V3_MODE_ID || FREE_EDIT_V3_ENABLED)
  && (mode.id !== 'i2i_draw' || WEB_I2I_DRAW_ENABLED)
  && (mode.id !== 'character_reference' || (
    WEB_CHARACTER_ASSETS_ENABLED && WEB_CHARACTER_ASSETS_ENTRY_ENABLED
  ))
  && (mode.id !== 'ltx_video' || WEB_LTX_VIDEO_ENABLED)
  && (mode.id !== 'ltx_t2v' || WEB_LTX_T2V_ENABLED)
  && (mode.id !== 'ltx_video_v2' || WEB_LTX_VIDEO_V2_ENABLED)
  && (mode.id !== 'minimax_h3' || (WEB_MINIMAX_H3_ENABLED && WEB_MINIMAX_H3_ENTRY_ENABLED))
)) as LabModeConfig[]

export const getLabModeConfig = (modeId: LabModeId): LabModeConfig =>
  LAB_MODE_CONFIG_MAP[modeId]

export const resolveLabModeIdFromTaskType = (taskType: string | null | undefined): UnifiedLabModeId => {
  switch (taskType) {
    case 'character_reference':
      return WEB_CHARACTER_ASSETS_ENABLED ? 'character_reference' : DEFAULT_LAB_MODE_ID
    case 'txt2img':
      return 'txt2img'
    case FREE_EDIT_V2_5_TASK_TYPE:
      return FREE_EDIT_V2_5_MODE_ID
    case PORNMASTER_FLUX2_EDIT_BF16_TASK_TYPE:
    case PORNMASTER_FLUX2_SINGLE_EDIT_TASK_TYPE:
    case PORNMASTER_FLUX2_MULTI_EDIT_TASK_TYPE:
      return FREE_EDIT_V3_MODE_ID
    case 'i2i_pro':
      return 'i2i_pro'
    case 'i2i_draw':
      return WEB_I2I_DRAW_ENABLED ? 'i2i_draw' : DEFAULT_LAB_MODE_ID
    case 'custom_video':
    case 'video_lora':
    case 'image2video':
    case 'image_to_video':
      return 'custom_video'
    case 'face_swap':
      return 'face_swap'
    case 'random_faceswap':
      return 'random_faceswap'
    case 'face_video':
      return 'scail2_face_swap_v2'
    case 'ltx_video':
      return 'ltx_video'
    case 'ltx_video_v2':
    case 'ltx_video_v2_flf2v':
      return WEB_LTX_VIDEO_V2_ENABLED ? 'ltx_video_v2' : DEFAULT_LAB_MODE_ID
    case 'ltx_t2v':
    case 'ltx_t2v_ic':
      return 'ltx_t2v'
    case 'minimax_h3_t2v':
    case 'minimax_h3_i2v':
    case 'minimax_h3_flf2v':
      return WEB_MINIMAX_H3_ENABLED ? 'minimax_h3' : DEFAULT_LAB_MODE_ID
    case 'minimax_h3_ref2v':
      return WEB_MINIMAX_H3_ENABLED && WEB_MINIMAX_H3_REF2V_ENABLED
        ? 'minimax_h3'
        : DEFAULT_LAB_MODE_ID
    case 'scail2_action_transfer_long':
      return 'scail2_action_transfer'
    case 'wan22_video_v2':
      return 'wan22_video_v2'
    case 'scail2_action_transfer':
      return 'scail2_action_transfer'
    case 'scail2_video_replacement':
      return 'scail2_video_replacement'
    case 'scail2_face_swap_v2':
      return 'scail2_face_swap_v2'
    case 'img2img_lora':
    case 'edit':
    default:
      return DEFAULT_LAB_MODE_ID
  }
}

export const getDefaultVideoLoraSelection = () => NO_IMAGE_TO_VIDEO_LORA

export const getVideoLoraOptions = () => IMAGE_TO_VIDEO_LORA_OPTIONS
