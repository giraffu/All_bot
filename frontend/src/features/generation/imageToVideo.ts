export const NO_IMAGE_TO_VIDEO_LORA = '__none__'

export type UnifiedImageToVideoTaskType = 'custom_video' | 'video_lora'

export type ImageToVideoLoraOption = {
  value: string
  label: string
}

export const IMAGE_TO_VIDEO_LORA_OPTIONS: ImageToVideoLoraOption[] = [
  { value: NO_IMAGE_TO_VIDEO_LORA, label: '无' },
  { value: 'BreastGrow', label: '巨乳膨胀' },
  { value: 'BreastInsertion', label: '乳交' },
  { value: 'Cum', label: '颜射' },
  { value: 'Cunilingus', label: '舔阴' },
  { value: 'Flatchested', label: '平胸' },
  { value: 'Footjob', label: '足交' },
  { value: 'Insertion', label: '插入优化' },
]

const LEGACY_VIDEO_LORA_DEFAULT =
  IMAGE_TO_VIDEO_LORA_OPTIONS.find(option => option.value !== NO_IMAGE_TO_VIDEO_LORA)?.value
  ?? NO_IMAGE_TO_VIDEO_LORA

export const isUnifiedImageToVideoTaskType = (
  taskType: string,
): taskType is UnifiedImageToVideoTaskType =>
  taskType === 'custom_video' || taskType === 'video_lora'

export const getDefaultImageToVideoLoraSelection = (taskType: string): string =>
  taskType === 'video_lora' ? LEGACY_VIDEO_LORA_DEFAULT : NO_IMAGE_TO_VIDEO_LORA

export const normalizeImageToVideoLoraSelection = (loraName: string | null | undefined): string =>
  typeof loraName === 'string' && loraName.trim() !== ''
    ? loraName
    : NO_IMAGE_TO_VIDEO_LORA

export const getImageToVideoPayloadLoraName = (
  taskType: string,
  loraSelection: string,
): string | undefined => {
  if (!isUnifiedImageToVideoTaskType(taskType)) {
    return undefined
  }

  return loraSelection === NO_IMAGE_TO_VIDEO_LORA ? undefined : loraSelection
}

export const getImageToVideoRequestTaskType = (
  taskType: string,
  _loraSelection: string,
): string => {
  if (taskType === 'ltx_video') {
    return 'ltx_video'
  }

  return isUnifiedImageToVideoTaskType(taskType) ? 'custom_video' : taskType
}
