import type { LtxVideoLoraItem } from './imageToVideo'

export type PromptTarget = 'topLevel' | 'inputs'

export type BuildGenerationTaskPayloadOptions = {
  taskType: string
  images: string[]
  priority?: number
  isTemplate?: boolean
  sourcePostId?: number | null
  prompt?: string
  promptTarget?: PromptTarget
  resolution?: string | number
  duration?: number
  loraName?: string
  loraStrength?: number
  loraItems?: LtxVideoLoraItem[]
  normalizeEditLoraTask?: boolean
}

export type GenerationTaskPayload = {
  task_type: string
  inputs: Record<string, unknown>
  priority: number
  is_template: boolean
  source_post_id?: number
  prompt?: string
}

export function buildGenerationTaskPayload(
  options: BuildGenerationTaskPayloadOptions,
): GenerationTaskPayload {
  const {
    taskType,
    images,
    priority = 0,
    isTemplate = false,
    sourcePostId,
    prompt,
    promptTarget,
    resolution,
    duration,
    loraName,
    loraStrength,
    loraItems,
    normalizeEditLoraTask = false,
  } = options

  const normalizedPrompt = prompt?.trim()
  const normalizedTaskType =
    normalizeEditLoraTask && taskType === 'edit' && loraName ? 'img2img_lora' : taskType

  const payload: GenerationTaskPayload = {
    task_type: normalizedTaskType,
    inputs: {
      images,
    },
    priority,
    is_template: isTemplate,
  }

  if (sourcePostId != null) {
    payload.source_post_id = sourcePostId
  }

  if (normalizedPrompt) {
    if (promptTarget === 'topLevel') {
      payload.prompt = normalizedPrompt
    } else if (promptTarget === 'inputs') {
      payload.inputs.prompt = normalizedPrompt
    }
  }

  if (resolution !== undefined) {
    payload.inputs.resolution = resolution
  }

  if (duration !== undefined) {
    payload.inputs.duration = duration
  }

  if (loraName) {
    payload.inputs.lora_name = loraName
  }

  if (loraStrength !== undefined) {
    payload.inputs.lora_strength = loraStrength
  }

  if (loraItems && loraItems.length > 0) {
    payload.inputs.lora_items = loraItems
  }

  return payload
}
