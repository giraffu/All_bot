import type { PromptTarget } from './buildGenerationTaskPayload'
import {
  DEFAULT_WAN22_VIDEO_V2_COST,
  IMAGE_TO_VIDEO_LORA_OPTIONS,
  NO_IMAGE_TO_VIDEO_LORA,
} from './imageToVideo'

export type UnifiedLabModeId =
  | 'edit'
  | 'txt2img'
  | 'i2i_pro'
  | 'i2i_draw'
  | 'custom_video'
  | 'face_swap'
  | 'face_video'
  | 'ltx_video'
  | 'wan22_video_v2'
  | 'scail2_action_transfer'
  | 'scail2_video_replacement'
  | 'scail2_face_swap_v2'

export type LegacyLabModeId = never

export type LabModeId = UnifiedLabModeId | LegacyLabModeId
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
  promptRequired: boolean
  unified: boolean
  legacyRouteName?: string
  uploadSlots?: readonly LabUploadSlotConfig[]
}

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

export const LTX_VIDEO_DURATION_OPTIONS = [
  { value: '5', label: '5 秒' },
  { value: '10', label: '10 秒' },
  { value: '15', label: '15 秒' },
  { value: '20', label: '20 秒' },
] as const

export const SCAIL2_VIDEO_DURATION_OPTIONS = [
  { value: '5', label: '5 秒' },
  { value: '8', label: '8 秒' },
] as const

export const SCAIL2_EIGHT_SECOND_MIN_TEMPLATE_DURATION_SECONDS = 8

export const getScail2VideoDurationOptionsForMotionVideo = (
  motionVideoDurationSeconds: number | null | undefined
) => {
  const canUseEightSecondDuration =
    typeof motionVideoDurationSeconds === 'number'
    && Number.isFinite(motionVideoDurationSeconds)
    && motionVideoDurationSeconds >= SCAIL2_EIGHT_SECOND_MIN_TEMPLATE_DURATION_SECONDS

  return canUseEightSecondDuration
    ? SCAIL2_VIDEO_DURATION_OPTIONS
    : SCAIL2_VIDEO_DURATION_OPTIONS.filter(option => option.value === '5')
}

export const getScail2VideoCost = (duration: string | number) => (
  String(duration).replace(/s$/i, '') === '8' ? 80 : 40
)

export const DEFAULT_VIDEO_RESOLUTION = '512'
export const DEFAULT_FACE_VIDEO_RESOLUTION = '720'
export const DEFAULT_LTX_VIDEO_RESOLUTION = '1280x704'
export const DEFAULT_VIDEO_DURATION = '5'

export const FACE_VIDEO_RESOLUTION_OPTIONS = [
  { value: '720', label: '720p' },
  { value: '1024', label: '1024p' },
] as const

export const LAB_MODE_CONFIGS: LabModeConfig[] = [
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
    baseCost: 1,
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
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsVideoLora: false,
    supportsLtxLoraItems: true,
    supportsAdvancedOptions: true,
    promptRequired: false,
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

export const UNIFIED_LAB_MODES = LAB_MODE_CONFIGS.filter(mode => mode.unified) as LabModeConfig[]
export const LEGACY_LAB_MODES = LAB_MODE_CONFIGS.filter(mode => !mode.unified) as LabModeConfig[]

export const getLabModeConfig = (modeId: LabModeId): LabModeConfig =>
  LAB_MODE_CONFIG_MAP[modeId]

export const resolveLabModeIdFromTaskType = (taskType: string | null | undefined): UnifiedLabModeId => {
  switch (taskType) {
    case 'txt2img':
      return 'txt2img'
    case 'i2i_pro':
      return 'i2i_pro'
    case 'i2i_draw':
      return 'i2i_draw'
    case 'custom_video':
    case 'video_lora':
      return 'custom_video'
    case 'face_swap':
      return 'face_swap'
    case 'face_video':
      return 'face_video'
    case 'ltx_video':
      return 'ltx_video'
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
