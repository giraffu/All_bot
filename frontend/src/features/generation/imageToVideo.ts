export const NO_IMAGE_TO_VIDEO_LORA = '__none__'
export const NO_LTX_VIDEO_LORA = '__none__'
export const DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT =
  'censored, mosaic censoring, bar censor, pixelated, glowing, bloom, blurry, out of focus, low detail, bad anatomy, ugly, overexposed, underexposed, distorted face, extra limbs, cartoonish, 3d render artifacts, duplicate people, unnatural lighting, bad composition, missing shadows, low resolution, poorly textured, glitch, noise, grain, static, motionless, still frame, stylized, artwork, painting, illustration, many people in background, three legs, walking backward, unnatural skin tone, discolored eyelid, red eyelids, closed eyes, poorly drawn hands, extra fingers, fused fingers, poorly drawn face, deformed, disfigured, malformed limbs, fog, mist, voluminous eyelashes,'
export type Wan22VideoV2ResolutionPreset = 'preview' | 'small' | 'standard' | 'hd'
export type Wan22VideoV2DurationSeconds = '5' | '8' | '10'

export const DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET: Wan22VideoV2ResolutionPreset = 'preview'
export const DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS: Wan22VideoV2DurationSeconds = '5'

export const WAN22_VIDEO_V2_RESOLUTION_OPTIONS: Array<{
  value: Wan22VideoV2ResolutionPreset
  label: string
  description: string
  cost: number
}> = [
  { value: 'preview', label: '极速', description: '约 512p，最低价，生成更快', cost: 6 },
  { value: 'small', label: '清晰', description: '约 600p，清晰度提升', cost: 12 },
  { value: 'standard', label: '标准', description: '约 720p，平衡画质与速度', cost: 20 },
  { value: 'hd', label: '高清', description: '约 810p，更清晰，生成更慢', cost: 30 },
]

export const WAN22_VIDEO_V2_DURATION_OPTIONS: Array<{
  value: Wan22VideoV2DurationSeconds
  label: string
  frameCount: number
  multiplier: number
}> = [
  { value: '5', label: '5 秒', frameCount: 81, multiplier: 1 },
  { value: '8', label: '8 秒', frameCount: 129, multiplier: 2 },
  { value: '10', label: '10 秒', frameCount: 161, multiplier: 3 },
]

export const DEFAULT_WAN22_VIDEO_V2_COST =
  WAN22_VIDEO_V2_RESOLUTION_OPTIONS.find(option => option.value === DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET)?.cost ?? 6

export const normalizeWan22VideoV2ResolutionPreset = (
  value: string | null | undefined,
): Wan22VideoV2ResolutionPreset => {
  const normalized = String(value ?? '').trim()
  const normalizedLower = normalized.toLowerCase()
  if (
    normalizedLower === 'preview'
    || normalizedLower === 'fast'
    || normalizedLower === '512'
    || normalizedLower === '512p'
    || normalizedLower === '0.26 mp - preview'
  ) {
    return 'preview'
  }
  if (
    normalizedLower === 'small'
    || normalizedLower === '600'
    || normalizedLower === '600p'
    || normalizedLower === '0.36 mp - small'
  ) {
    return 'small'
  }
  if (
    normalizedLower === 'hd'
    || normalizedLower === '1024'
    || normalizedLower === '1024p'
    || normalizedLower === '0.65 mp - balanced'
  ) {
    return 'hd'
  }
  if (
    normalizedLower === 'standard'
    || normalizedLower === '720'
    || normalizedLower === '720p'
    || normalizedLower === '0.52 mp - sd'
  ) {
    return 'standard'
  }
  return DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
}

export const normalizeWan22VideoV2DurationSeconds = (
  value: string | number | null | undefined,
): Wan22VideoV2DurationSeconds => {
  const normalized = String(value ?? '').trim().replace(/s$/i, '')
  return normalized === '8' || normalized === '10'
    ? normalized
    : DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS
}

export const getWan22VideoV2Cost = (
  resolutionPreset: string | null | undefined,
  duration: string | number | null | undefined = DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS,
): number => {
  const resolution = normalizeWan22VideoV2ResolutionPreset(resolutionPreset)
  const durationSeconds = normalizeWan22VideoV2DurationSeconds(duration)
  const baseCost = WAN22_VIDEO_V2_RESOLUTION_OPTIONS.find(option => option.value === resolution)?.cost ?? DEFAULT_WAN22_VIDEO_V2_COST
  const multiplier = WAN22_VIDEO_V2_DURATION_OPTIONS.find(option => option.value === durationSeconds)?.multiplier ?? 1
  return baseCost * multiplier
}

export type UnifiedImageToVideoTaskType = 'custom_video' | 'video_lora'
export type Wan22TemplateVideoTaskType = UnifiedImageToVideoTaskType | 'wan22_video_v2'

export type ImageToVideoLoraOption = {
  value: string
  label: string
  defaultStrength?: number
}

export type LtxVideoLoraItem = {
  name: string
  strength: number
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

export const LTX_VIDEO_LORA_OPTIONS: ImageToVideoLoraOption[] = [
  { value: NO_LTX_VIDEO_LORA, label: '无' },
  { value: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors', label: '运动逻辑优化', defaultStrength: 0.8 },
  { value: 'ltx2.3/DR34ML4Y_LTXXX_PREVIEW_RC1.safetensors', label: '全能姿势', defaultStrength: 0.6 },
  { value: 'ltx2.3/SynthPussy_01_rank32.safetensors', label: '私处细节', defaultStrength: 0.8 },
  { value: 'ltx2.3/LTX2.3TITFUCKE2000.safetensors', label: '乳交', defaultStrength: 1.0 },
  { value: 'ltx2.3/ltxdeepthroat_v01.safetensors', label: '深喉/口交', defaultStrength: 1.0 },
  { value: 'ltx2.3/penile-praxis-general-nsfw-ltx-2-t2v-i2v.safetensors', label: '男根/多姿势', defaultStrength: 1.0 },
  { value: 'ltx2.3/pussyjob_v1.1_merged_ltx23.safetensors', label: '外阴摩擦', defaultStrength: 0.8 },
  { value: 'ltx2.3/st0mach_bulge_ltx23_v1.1.safetensors', label: '腹部鼓起', defaultStrength: 0.8 },
  { value: 'ltx2.3/sfbehind_LTX2_3_v0_1.safetensors', label: '后入', defaultStrength: 1.0 },
  { value: 'ltx2.3/nsfw_anal_insertion_ltx23_v1.0.safetensors', label: '肛交插入', defaultStrength: 0.8 },
]

const LEGACY_VIDEO_LORA_DEFAULT =
  IMAGE_TO_VIDEO_LORA_OPTIONS.find(option => option.value !== NO_IMAGE_TO_VIDEO_LORA)?.value
  ?? NO_IMAGE_TO_VIDEO_LORA

export const isUnifiedImageToVideoTaskType = (
  taskType: string,
): taskType is UnifiedImageToVideoTaskType =>
  taskType === 'custom_video' || taskType === 'video_lora'

export const isWan22TemplateVideoTaskType = (
  taskType: string,
): taskType is Wan22TemplateVideoTaskType =>
  taskType === 'wan22_video_v2' || isUnifiedImageToVideoTaskType(taskType)

export const getDefaultImageToVideoLoraSelection = (taskType: string): string =>
  taskType === 'video_lora'
    ? LEGACY_VIDEO_LORA_DEFAULT
    : taskType === 'ltx_video'
      ? NO_LTX_VIDEO_LORA
      : NO_IMAGE_TO_VIDEO_LORA

export const normalizeImageToVideoLoraSelection = (loraName: string | null | undefined): string =>
  typeof loraName === 'string' && loraName.trim() !== ''
    ? loraName
    : NO_IMAGE_TO_VIDEO_LORA

export const getImageToVideoPayloadLoraName = (
  taskType: string,
  loraSelection: string,
): string | undefined => {
  if (taskType === 'ltx_video') {
    return loraSelection === NO_LTX_VIDEO_LORA ? undefined : loraSelection
  }

  if (!isUnifiedImageToVideoTaskType(taskType)) {
    return undefined
  }

  return loraSelection === NO_IMAGE_TO_VIDEO_LORA ? undefined : loraSelection
}

export const getImageToVideoPayloadLoraStrength = (
  taskType: string,
  loraSelection: string,
): number | undefined => {
  if (taskType !== 'ltx_video') {
    return undefined
  }

  const selectedOption = LTX_VIDEO_LORA_OPTIONS.find(option => option.value === loraSelection)
  return selectedOption?.defaultStrength
}

export const getLtxVideoLoraOption = (
  loraName: string,
): ImageToVideoLoraOption | undefined =>
  LTX_VIDEO_LORA_OPTIONS.find(option => option.value === loraName)

export const buildDefaultLtxVideoLoraItem = (
  loraName: string,
): LtxVideoLoraItem | null => {
  const option = getLtxVideoLoraOption(loraName)
  if (!option || option.value === NO_LTX_VIDEO_LORA) {
    return null
  }

  return {
    name: option.value,
    strength: option.defaultStrength ?? 1.0,
  }
}

export const normalizeLtxVideoLoraItems = (
  loraItems: Array<Partial<LtxVideoLoraItem> | null | undefined> | null | undefined,
): LtxVideoLoraItem[] => {
  const normalized: LtxVideoLoraItem[] = []
  const seen = new Set<string>()

  for (const rawItem of loraItems ?? []) {
    const rawName = typeof rawItem?.name === 'string' ? rawItem.name.trim() : ''
    const item = buildDefaultLtxVideoLoraItem(rawName)
    if (!item || seen.has(item.name)) {
      continue
    }

    const rawStrength = typeof rawItem?.strength === 'number' ? rawItem.strength : item.strength
    item.strength = Number.isFinite(rawStrength)
      ? Math.min(2.0, Math.max(0.1, Number(rawStrength.toFixed(2))))
      : item.strength
    normalized.push(item)
    seen.add(item.name)
  }

  return normalized.slice(0, 3)
}

export const getImageToVideoRequestTaskType = (
  taskType: string,
  loraSelection: string,
): string => {
  if (taskType === 'ltx_video') {
    return 'ltx_video'
  }

  if (taskType === 'wan22_video_v2') {
    return 'wan22_video_v2'
  }

  if (!isUnifiedImageToVideoTaskType(taskType)) {
    return taskType
  }

  return loraSelection === NO_IMAGE_TO_VIDEO_LORA ? 'custom_video' : 'video_lora'
}
