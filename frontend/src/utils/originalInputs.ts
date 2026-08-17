import { getFileUrl, isVideoFile } from '@/utils/mediaFiles'

type Translate = (key: string, params?: Record<string, unknown>) => string

export interface OriginalInputSource {
  type?: string | null
  task_type?: string | null
  input_file?: string | null
  input_file_url?: string | null
  input_files?: string[] | null
  input_file_urls?: string[] | null
}

export interface OriginalInputPreview {
  key: string
  file: string | null
  url: string
  label: string
  mediaType: 'image' | 'video'
  index: number
}

const SPLIT_INPUT_RE = /\|/
const WAN22_TASK_TYPES = new Set(['wan22_video_v2', 'custom_video', 'video_lora'])
const LTX_TASK_TYPES = new Set(['ltx_video', 'ltx_video_flf2v'])
const MINIMAX_H3_IMAGE_TASK_TYPES = new Set(['minimax_h3_i2v', 'minimax_h3_flf2v'])
const SCAIL2_TASK_TYPES = new Set([
  'scail2_action_transfer',
  'scail2_action_transfer_long',
  'scail2_video_replacement',
  'scail2_face_swap_v2',
])

const normalizeStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map((item) => String(item || '').trim())
    .filter(Boolean)
}

const splitInputFile = (value: string | null | undefined): string[] => {
  if (!value) {
    return []
  }
  return String(value)
    .split(SPLIT_INPUT_RE)
    .map((item) => item.trim())
    .filter(Boolean)
}

const normalizeTaskType = (source: OriginalInputSource): string => (
  String(source.task_type || source.type || '').trim()
)

const resolveInputLabelKey = (
  taskType: string,
  index: number,
  total: number,
  file: string | null,
): string => {
  if (WAN22_TASK_TYPES.has(taskType) || MINIMAX_H3_IMAGE_TASK_TYPES.has(taskType)) {
    if (total > 1) {
      return index === 0 ? 'start_frame' : 'end_frame'
    }
    return 'start_frame'
  }

  if (SCAIL2_TASK_TYPES.has(taskType)) {
    return index === 0 ? 'reference_image' : 'motion_video'
  }

  if (taskType === 'face_swap') {
    return index === 0 ? 'target_image' : 'face_image'
  }

  if (taskType === 'face_video') {
    return index === 0 ? 'face_image' : 'target_video'
  }

  if ([
    'i2i_pro',
    'i2i_draw',
    'img2img_lora',
    'edit',
    'pornmaster_flux2_single_edit',
    'pornmaster_flux2_multi_edit',
    'pornmaster_flux2_edit_bf16',
  ].includes(taskType)) {
    return total === 1 ? 'reference_image' : 'input_n'
  }

  if (LTX_TASK_TYPES.has(taskType)) {
    if (total > 1) {
      return index === 0 ? 'start_frame' : 'end_frame'
    }
    return isVideoFile(file || '') ? 'target_video' : 'start_frame'
  }

  return 'input_n'
}

const resolvePreviewUrl = (
  file: string | null,
  url: string | null,
  source: OriginalInputSource,
  index: number,
): string => {
  if (url) {
    return url
  }
  if (!file) {
    return ''
  }
  return getFileUrl(file, `${source.task_type || source.type || 'input'}-${index}`)
}

export const resolveOriginalInputPreviews = (
  source: OriginalInputSource | null | undefined,
  t: Translate,
): OriginalInputPreview[] => {
  if (!source) {
    return []
  }

  const taskType = normalizeTaskType(source)
  if (taskType === 'txt2img') {
    return []
  }

  const inputFiles = normalizeStringList(source.input_files)
  const files = inputFiles.length ? inputFiles : splitInputFile(source.input_file)
  const inputUrls = normalizeStringList(source.input_file_urls)
  const urls = inputUrls.length
    ? inputUrls
    : normalizeStringList(source.input_file_url ? [source.input_file_url] : [])
  const total = Math.max(files.length, urls.length)

  if (!total) {
    return []
  }

  return Array.from({ length: total }, (_, index) => {
    const file = files[index] || null
    const url = resolvePreviewUrl(file, urls[index] || null, source, index)
    const labelKey = resolveInputLabelKey(taskType, index, total, file || urls[index] || null)
    const label = labelKey === 'input_n'
      ? t('original_inputs.input_n', { count: index + 1 })
      : t(`original_inputs.${labelKey}`)

    const mediaType: OriginalInputPreview['mediaType'] = isVideoFile(url || file || '')
      ? 'video'
      : 'image'

    return {
      key: `${file || url || 'input'}-${index}`,
      file,
      url,
      label,
      mediaType,
      index,
    }
  }).filter((preview) => Boolean(preview.url))
}
