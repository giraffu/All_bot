import type { PromptTarget } from './buildGenerationTaskPayload'
import { IMAGE_TO_VIDEO_LORA_OPTIONS, NO_IMAGE_TO_VIDEO_LORA } from './imageToVideo'

export type UnifiedLabModeId =
  | 'edit'
  | 'txt2img'
  | 'i2i_pro'
  | 'i2i_draw'
  | 'custom_video'

export type LegacyLabModeId =
  | 'face_swap'
  | 'face_video'
  | 'ltx_video'
  | 'wan22_video_v2'

export type LabModeId = UnifiedLabModeId | LegacyLabModeId

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
  supportsAdvancedOptions: boolean
  promptRequired: boolean
  unified: boolean
  legacyRouteName?: string
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

export const DEFAULT_VIDEO_RESOLUTION = '512'
export const DEFAULT_VIDEO_DURATION = '5'

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
    promptRequired: true,
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
    promptRequired: true,
    unified: true,
  },
  {
    id: 'custom_video',
    taskType: 'custom_video',
    titleKey: 'lab.cards.custom_video_title',
    descriptionKey: 'lab.cards.custom_video_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 6,
    promptPlaceholderKey: 'template_apply.image_to_video.prompt_placeholder_custom',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    referenceTitleKey: 'template_apply.common.base_image',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsAdvancedOptions: true,
    promptRequired: true,
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
    submitLabelKey: 'lab.workbench.submit_image',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: false,
    supportsAdvancedOptions: false,
    promptRequired: false,
    unified: false,
    legacyRouteName: 'FaceSwap',
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
    submitLabelKey: 'lab.workbench.submit_video',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsAdvancedOptions: false,
    promptRequired: false,
    unified: false,
    legacyRouteName: 'VideoSwap',
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
    supportsAdvancedOptions: true,
    promptRequired: true,
    unified: false,
    legacyRouteName: 'SingleImageToVideo',
  },
  {
    id: 'wan22_video_v2',
    taskType: 'wan22_video_v2',
    titleKey: 'lab.cards.wan22_video_v2_title',
    descriptionKey: 'lab.cards.wan22_video_v2_desc',
    kindKey: 'lab.workbench.mode_kinds.video',
    baseCost: 20,
    promptPlaceholderKey: 'template_apply.image_to_video.prompt_placeholder_custom',
    promptTarget: 'inputs',
    submitLabelKey: 'lab.workbench.submit_video',
    maxImages: 1,
    supportsUpload: true,
    supportsEditLora: false,
    supportsVideoOptions: true,
    supportsAdvancedOptions: true,
    promptRequired: true,
    unified: false,
    legacyRouteName: 'Wan22VideoV2',
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
    case 'img2img_lora':
    case 'edit':
    default:
      return DEFAULT_LAB_MODE_ID
  }
}

export const getDefaultVideoLoraSelection = () => NO_IMAGE_TO_VIDEO_LORA

export const getVideoLoraOptions = () => IMAGE_TO_VIDEO_LORA_OPTIONS
