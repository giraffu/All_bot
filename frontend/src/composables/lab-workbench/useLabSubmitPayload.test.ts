// @vitest-environment jsdom

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  type LtxVideoLoraItem,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import {
  getLabModeConfig,
  type LabModeConfig,
  type LabUploadSlotId,
  type MiniMaxH3AddonItem,
  type UnifiedLabModeId,
} from '@/features/generation/labModeConfig'
import type { LabAssetUploadSlot, UploadedReference, UploadedReferenceAudio, UploadedSlotAsset } from './types'
import { useLabSubmitPayload } from './useLabSubmitPayload'

const messageMock = vi.hoisted(() => ({
  warning: vi.fn(),
}))

vi.mock('ant-design-vue', () => ({
  message: messageMock,
}))

const t = (key: string) => key

type SubmitHarness = {
  modeId: Ref<UnifiedLabModeId>
  currentMode: ComputedRef<LabModeConfig>
  uploadedReferences: Ref<UploadedReference[]>
  uploadedSlotAssets: Ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>
  prompt: Ref<string>
  audioPrompt: Ref<string>
  selectedEditLora: Ref<string>
  customEditLoraStrength: Ref<number>
  selectedVideoLora: Ref<string>
  ltxLoraItems: Ref<LtxVideoLoraItem[]>
  negativePrompt: Ref<string>
  wan22ResolutionPreset: Ref<Wan22VideoV2ResolutionPreset>
  resolution: Ref<string>
  duration: Ref<string>
  selectedCharacterIds: Ref<string[]>
  minimaxH3Mode: Ref<'t2v' | 'i2v' | 'flf2v' | 'ref2v'>
  minimaxH3ResolutionPreset: Ref<'preview' | 'small' | 'standard' | 'hd'>
  minimaxH3AspectRatio: Ref<'16:9' | '9:16' | '1:1' | '4:3' | '3:4'>
  minimaxH3ReferenceDescriptions: Ref<string[]>
  minimaxH3AddonItems: Ref<MiniMaxH3AddonItem[]>
  minimaxH3ReferenceAudio: Ref<UploadedReferenceAudio | null>
  isTemplateApplied: Ref<boolean>
  isTemplatePromptLocked: Ref<boolean>
  templateSourcePostId: Ref<number | null>
  wan22PrevTaskId: Ref<string | null>
  wan22ChainTaskIds: Ref<string[]>
  ltxPrevTaskId: Ref<string | null>
  ltxChainTaskIds: Ref<string[]>
  h3PrevTaskId: Ref<string | null>
  submitTask: ReturnType<typeof vi.fn>
  setSubmittedTaskId: ReturnType<typeof vi.fn>
  handleSubmit: () => Promise<void>
}

const buildAssetSlots = (
  currentMode: ComputedRef<LabModeConfig>,
  uploadedSlotAssets: Ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>,
) => computed<LabAssetUploadSlot[]>(() => (
  currentMode.value.uploadSlots?.map(slot => ({
    id: slot.id,
    label: slot.labelKey,
    hint: slot.hintKey,
    buttonLabel: slot.buttonKey,
    accept: slot.accept,
    previewKind: slot.previewKind,
    required: slot.required,
    item: uploadedSlotAssets.value[slot.id]
      ? {
          ...uploadedSlotAssets.value[slot.id]!,
        }
      : null,
  })) ?? []
))

const createHarness = (initialModeId: UnifiedLabModeId): SubmitHarness => {
  const modeId = ref<UnifiedLabModeId>(initialModeId)
  const currentMode = computed<LabModeConfig>(() => getLabModeConfig(modeId.value))
  const uploadedReferences = ref<UploadedReference[]>([])
  const uploadedSlotAssets = ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>({})
  const prompt = ref('')
  const audioPrompt = ref('')
  const selectedEditLora = ref('')
  const customEditLoraStrength = ref(1)
  const selectedVideoLora = ref('__none__')
  const ltxLoraItems = ref<LtxVideoLoraItem[]>([])
  const negativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
  const wan22ResolutionPreset = ref<Wan22VideoV2ResolutionPreset>('preview')
  const resolution = ref('512')
  const duration = ref('5')
  const selectedCharacterIds = ref<string[]>([])
  const minimaxH3Mode = ref<'t2v' | 'i2v' | 'flf2v' | 'ref2v'>('t2v')
  const minimaxH3ResolutionPreset = ref<'preview' | 'small' | 'standard' | 'hd'>('preview')
  const minimaxH3AspectRatio = ref<'16:9' | '9:16' | '1:1' | '4:3' | '3:4'>('16:9')
  const minimaxH3ReferenceDescriptions = ref<string[]>(['', '', '', ''])
  const minimaxH3AddonItems = ref<MiniMaxH3AddonItem[]>([])
  const minimaxH3ReferenceAudio = ref<UploadedReferenceAudio | null>(null)
  const isTemplateApplied = ref(false)
  const isTemplatePromptLocked = ref(false)
  const templateSourcePostId = ref<number | null>(null)
  const wan22PrevTaskId = ref<string | null>(null)
  const wan22ChainTaskIds = ref<string[]>([])
  const ltxPrevTaskId = ref<string | null>(null)
  const ltxChainTaskIds = ref<string[]>([])
  const h3PrevTaskId = ref<string | null>(null)
  const submitTask = vi.fn(async () => 'submitted-1')
  const setSubmittedTaskId = vi.fn()
  const assetUploadSlots = buildAssetSlots(currentMode, uploadedSlotAssets)
  const hasStructuredUploadSlots = computed(() => (currentMode.value.uploadSlots?.length ?? 0) > 0)

  const { handleSubmit } = useLabSubmitPayload({
    currentMode,
    hasStructuredUploadSlots,
    assetUploadSlots,
    uploadedReferences,
    uploadedSlotAssets,
    prompt,
    audioPrompt,
    selectedEditLora,
    customEditLoraStrength,
    selectedVideoLora,
    ltxLoraItems,
    negativePrompt,
    wan22ResolutionPreset,
    resolution,
    duration,
    selectedCharacterIds,
    minimaxH3Mode,
    minimaxH3ResolutionPreset,
    minimaxH3AspectRatio,
    minimaxH3AddonItems,
    minimaxH3ReferenceAudio,
    isTemplateApplied,
    isTemplatePromptLocked,
    templateSourcePostId,
    wan22PrevTaskId,
    wan22ChainTaskIds,
    ltxPrevTaskId,
    ltxChainTaskIds,
    h3PrevTaskId,
    submitTask,
    setSubmittedTaskId,
    t,
  })

  return {
    modeId,
    currentMode,
    uploadedReferences,
    uploadedSlotAssets,
    prompt,
    audioPrompt,
    selectedEditLora,
    customEditLoraStrength,
    selectedVideoLora,
    ltxLoraItems,
    negativePrompt,
    wan22ResolutionPreset,
    resolution,
    duration,
    selectedCharacterIds,
    minimaxH3Mode,
    minimaxH3ResolutionPreset,
    minimaxH3AspectRatio,
    minimaxH3ReferenceDescriptions,
    minimaxH3AddonItems,
    minimaxH3ReferenceAudio,
    isTemplateApplied,
    isTemplatePromptLocked,
    templateSourcePostId,
    wan22PrevTaskId,
    wan22ChainTaskIds,
    ltxPrevTaskId,
    ltxChainTaskIds,
    h3PrevTaskId,
    submitTask,
    setSubmittedTaskId,
    handleSubmit,
  }
}

const refImage = (key: string): UploadedReference => ({
  key,
  preview: `https://cdn/${key}`,
  name: key,
})

const slotAsset = (key: string, previewKind: 'image' | 'video' = 'image'): UploadedSlotAsset => ({
  key,
  preview: `https://cdn/${key}`,
  name: key,
  previewKind,
})

describe('useLabSubmitPayload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('switches LTX text-to-video payload by character selection', async () => {
    const harness = createHarness('ltx_t2v')
    harness.prompt.value = 'an adult character walks through a candlelit room'
    harness.audioPrompt.value = 'quiet dialogue and crackling candles'
    harness.duration.value = '15'
    harness.resolution.value = '1280x704'

    await harness.handleSubmit()
    expect(harness.submitTask).toHaveBeenLastCalledWith(expect.objectContaining({
      task_type: 'ltx_t2v',
      inputs: expect.objectContaining({
        duration: 15,
        resolution: '1280x704',
        audio_prompt: 'quiet dialogue and crackling candles',
      }),
    }), 'lab.cards.ltx_t2v_title')

    harness.selectedCharacterIds.value = ['character-1', 'character-2']
    harness.uploadedReferences.value = [refImage('web_uploads/7/bedroom.webp')]
    harness.duration.value = '20'
    await harness.handleSubmit()
    expect(harness.submitTask).toHaveBeenLastCalledWith(expect.objectContaining({
      task_type: 'ltx_t2v_ic',
      inputs: expect.objectContaining({
        character_refs: [
          { source: 'private', id: 'character-1' },
          { source: 'private', id: 'character-2' },
        ],
        environment_ref: { source: 'upload', object_key: 'web_uploads/7/bedroom.webp' },
        duration: 20,
        resolution: '768x448',
      }),
    }), 'lab.cards.ltx_t2v_title')
  })

  it('submits MiniMax H3 without user-controlled model choices', async () => {
    const harness = createHarness('minimax_h3')
    harness.prompt.value = 'cinematic character motion with dialogue'
    harness.duration.value = '15'
    harness.minimaxH3ResolutionPreset.value = 'hd'
    harness.minimaxH3AspectRatio.value = '9:16'

    await harness.handleSubmit()
    expect(harness.submitTask).toHaveBeenLastCalledWith(expect.objectContaining({
      task_type: 'minimax_h3_t2v',
      inputs: expect.objectContaining({
        images: [], duration: 15, resolution_preset: 'hd', aspect_ratio: '9:16',
      }),
    }), 'lab.cards.minimax_h3_title')

    harness.minimaxH3Mode.value = 'i2v'
    harness.uploadedReferences.value = [{ ...refImage('portrait.png'), width: 900, height: 1600 }]
    await harness.handleSubmit()
    expect(harness.submitTask).toHaveBeenLastCalledWith(expect.objectContaining({
      task_type: 'minimax_h3_i2v',
      inputs: expect.objectContaining({
        images: ['portrait.png'],
        aspect_ratio: 'source',
      }),
    }), 'lab.cards.minimax_h3_title')
    expect(harness.submitTask.mock.calls.at(-1)?.[0].inputs).not.toHaveProperty('lora_items')

    harness.minimaxH3AddonItems.value = [
      { name: 'naughty_times', strength: 0.7 },
      { name: 'pussy', strength: 0.3 },
    ]
    await harness.handleSubmit()
    expect(harness.submitTask.mock.calls.at(-1)?.[0].inputs).not.toHaveProperty('lora_items')
  })

  it('submits H3 continuation with only the new client end frame', async () => {
    const harness = createHarness('minimax_h3')
    harness.prompt.value = 'continue into a quiet close-up'
    harness.minimaxH3Mode.value = 'flf2v'
    harness.h3PrevTaskId.value = 'h3-parent'
    harness.uploadedReferences.value = [
      { ...refImage('trusted-tail.png'), locked: true, width: 1280, height: 720 },
      { ...refImage('new-end.png'), width: 1280, height: 720 },
    ]

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'minimax_h3_flf2v',
      inputs: expect.objectContaining({
        images: ['new-end.png'],
        minimax_h3_prev_task_id: 'h3-parent',
      }),
    }), 'lab.cards.minimax_h3_title')
  })

  it('submits ordered mixed typed references for H3 REF2V', async () => {
    const harness = createHarness('minimax_h3')
    harness.prompt.value = 'the two characters speak softly'
    harness.minimaxH3Mode.value = 'ref2v'
    harness.uploadedReferences.value = [
      {
        key: 'character:character-1:face_front',
        preview: 'https://cdn/face.png',
        name: 'A · Front Face',
        referenceRef: {
          source: 'private_character_view',
          character_id: 'character-1',
          view_type: 'face_front',
        },
      },
      refImage('web_uploads/7/scene.png'),
    ]
    harness.minimaxH3ReferenceAudio.value = {
      key: 'web_uploads/7/voice.m4a',
      preview: 'blob:voice',
      name: 'voice.m4a',
    }

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'minimax_h3_ref2v',
      inputs: expect.objectContaining({
        images: [],
        reference_refs: [
          {
            source: 'private_character_view',
            character_id: 'character-1',
            view_type: 'face_front',
          },
          { source: 'upload', object_key: 'web_uploads/7/scene.png' },
        ],
        reference_audio_ref: {
          source: 'upload',
          object_key: 'web_uploads/7/voice.m4a',
        },
        prompt: 'the two characters speak softly',
      }),
    }), 'lab.cards.minimax_h3_title')
    expect(harness.submitTask.mock.calls[0][0].inputs).not.toHaveProperty('reference_descriptions')
  })

  it('submits ordered MSR character ids with a required scene background', async () => {
    const harness = createHarness('ltx_t2v')
    harness.prompt.value = '图1与图2在客厅交谈'
    harness.selectedCharacterIds.value = ['wang', 'man']
    harness.uploadedReferences.value = [refImage('web_uploads/7/room.png')]

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'ltx_t2v_ic',
      inputs: expect.objectContaining({
        character_refs: [
          { source: 'private', id: 'wang' },
          { source: 'private', id: 'man' },
        ],
        environment_ref: { source: 'upload', object_key: 'web_uploads/7/room.png' },
        resolution: '768x448',
      }),
    }), 'lab.cards.ltx_t2v_title')
  })

  it('builds txt2img payloads with top-level prompts', async () => {
    const harness = createHarness('txt2img')
    harness.prompt.value = '  draw a castle  '

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith({
      task_type: 'txt2img',
      inputs: {
        images: [],
      },
      priority: 0,
      is_template: false,
      prompt: 'draw a castle',
    }, 'lab.cards.txt2img_title')
    expect(harness.setSubmittedTaskId).toHaveBeenCalledWith('submitted-1')
  })

  it('builds random face swap payloads from one uploaded reference', async () => {
    const harness = createHarness('random_faceswap')
    harness.uploadedReferences.value = [refImage('face.png')]

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith({
      task_type: 'random_faceswap',
      inputs: {
        images: ['face.png'],
      },
      priority: 0,
      is_template: false,
    }, 'lab.cards.random_faceswap_title')
  })

  it('normalizes edit LoRA submissions to img2img_lora', async () => {
    const harness = createHarness('edit')
    harness.uploadedReferences.value = [refImage('base.png')]
    harness.prompt.value = 'make it realistic'
    harness.selectedEditLora.value = 'qwen/YARN_1.0.safetensors'
    harness.customEditLoraStrength.value = 0.3

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'img2img_lora',
      inputs: expect.objectContaining({
        images: ['base.png'],
        lora_name: 'qwen/YARN_1.0.safetensors',
        lora_strength: 0.3,
      }),
      prompt: 'make it realistic',
    }), 'lab.cards.custom_edit_title')
  })

  it('submits free edit v3 through the BF16 single-image task type', async () => {
    const harness = createHarness('edit_v3')
    harness.uploadedReferences.value = [refImage('base.png')]
    harness.prompt.value = 'clean up details'

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenLastCalledWith(expect.objectContaining({
      task_type: 'pornmaster_flux2_edit_bf16',
      inputs: {
        images: ['base.png'],
      },
      prompt: 'clean up details',
    }), 'lab.cards.custom_edit_v3_title')
  })

  it('submits free edit v2.5 with its logical type and template provenance', async () => {
    const harness = createHarness('edit_v2_5')
    harness.uploadedReferences.value = [refImage('replacement.png')]
    harness.prompt.value = 'locked original prompt'
    harness.isTemplateApplied.value = true
    harness.isTemplatePromptLocked.value = true
    harness.templateSourcePostId.value = 25

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenLastCalledWith(expect.objectContaining({
      task_type: 'free_edit_v2_5',
      inputs: {
        images: ['replacement.png'],
      },
      prompt: 'locked original prompt',
      is_template: true,
      source_post_id: 25,
    }), 'lab.cards.custom_edit_v2_5_title')
  })

  it('builds custom video LoRA payloads with WAN22 chain metadata', async () => {
    const harness = createHarness('custom_video')
    harness.uploadedReferences.value = [refImage('start.png'), refImage('end.png')]
    harness.prompt.value = 'move forward'
    harness.selectedVideoLora.value = 'BreastGrow'
    harness.duration.value = '8'
    harness.wan22ResolutionPreset.value = 'small'
    harness.wan22PrevTaskId.value = 'prev-task'
    harness.wan22ChainTaskIds.value = ['task-1', 'prev-task']

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'video_lora',
      inputs: expect.objectContaining({
        images: ['start.png', 'end.png'],
        prompt: 'move forward',
        duration: 8,
        lora_name: 'BreastGrow',
        use_end_frame: true,
        resolution_preset: 'small',
        wan22_prev_task_id: 'prev-task',
        wan22_chain_task_ids: ['task-1', 'prev-task'],
      }),
    }), 'lab.cards.custom_video_title')
  })

  it('builds WAN22 v2 payloads without rewriting task type', async () => {
    const harness = createHarness('wan22_video_v2')
    harness.uploadedReferences.value = [refImage('start.png')]
    harness.prompt.value = 'camera pan'
    harness.duration.value = '10'
    harness.wan22ResolutionPreset.value = 'hd'

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'wan22_video_v2',
      inputs: expect.objectContaining({
        images: ['start.png'],
        prompt: 'camera pan',
        duration: 10,
        negative_prompt: DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
        use_end_frame: false,
        resolution_preset: 'hd',
      }),
    }), 'lab.cards.wan22_video_v2_title')
  })

  it('trims and forwards an optional LTX negative prompt', async () => {
    const harness = createHarness('ltx_video')
    harness.uploadedReferences.value = [refImage('start.png')]
    harness.prompt.value = 'camera orbit'
    harness.negativePrompt.value = '  blur, jitter  '
    harness.resolution.value = '1280x704'
    harness.duration.value = '10'

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith(expect.objectContaining({
      task_type: 'ltx_video',
      inputs: expect.objectContaining({
        prompt: 'camera orbit',
        negative_prompt: 'blur, jitter',
        ltx_mode: 'i2v',
      }),
    }), 'lab.cards.high_res_video_title')
  })

  it('omits a blank LTX negative prompt so the workflow default remains active', async () => {
    const harness = createHarness('ltx_video')
    harness.uploadedReferences.value = [refImage('start.png')]
    harness.prompt.value = 'camera orbit'
    harness.negativePrompt.value = '   '

    await harness.handleSubmit()

    expect(harness.submitTask.mock.calls[0]?.[0].inputs).not.toHaveProperty('negative_prompt')
  })

  it('builds SCAIL-2 payloads from structured slots', async () => {
    const harness = createHarness('scail2_face_swap_v2')
    harness.uploadedSlotAssets.value = {
      reference_image: slotAsset('reference.png'),
      motion_video: slotAsset('motion.mp4', 'video'),
    }
    harness.duration.value = '8'
    harness.prompt.value = 'keep identity'

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith({
      task_type: 'scail2_face_swap_v2',
      inputs: {
        images: ['reference.png', 'motion.mp4'],
        duration: 8,
        prompt: 'keep identity',
        negative_prompt: DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
      },
      priority: 0,
      is_template: false,
    }, 'lab.cards.scail2_face_swap_v2_title')
  })

  it('builds merged long SCAIL-2 action transfer payloads from structured slots', async () => {
    const harness = createHarness('scail2_action_transfer')
    harness.uploadedSlotAssets.value = {
      reference_image: slotAsset('reference.png'),
      motion_video: slotAsset('motion.mp4', 'video'),
    }
    harness.duration.value = '20'
    harness.prompt.value = 'follow the motion'

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith({
      task_type: 'scail2_action_transfer',
      inputs: {
        images: ['reference.png', 'motion.mp4'],
        duration: 20,
        prompt: 'follow the motion',
        negative_prompt: DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
      },
      priority: 0,
      is_template: false,
    }, 'lab.cards.scail2_action_transfer_title')
  })

  it('builds face video payloads from structured slots', async () => {
    const harness = createHarness('face_video')
    harness.uploadedSlotAssets.value = {
      face_image: slotAsset('face.png'),
      target_video: slotAsset('target.mp4', 'video'),
    }
    harness.resolution.value = '1024'
    harness.isTemplateApplied.value = true
    harness.templateSourcePostId.value = 42

    await harness.handleSubmit()

    expect(harness.submitTask).toHaveBeenCalledWith({
      task_type: 'face_video',
      inputs: {
        face_image: 'face.png',
        target_video: 'target.mp4',
        resolution: 1024,
      },
      priority: 0,
      is_template: true,
      source_post_id: 42,
    }, 'lab.cards.video_face_swap_title')
  })
})
