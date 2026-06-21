import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { useUpload } from '@/composables/useUpload'
import { getWan22HistoryChain, stitchLtxHistoryChain, stitchWan22HistoryChain } from '@/api/gallery'
import type { TaskRecord } from '@/types/gallery'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import { buildSwapTaskPayload } from '@/features/generation/buildSwapTaskPayload'
import { useTasksStore } from '@/stores/tasks'
import {
  DEFAULT_FACE_VIDEO_RESOLUTION,
  DEFAULT_LAB_MODE_ID,
  DEFAULT_LTX_VIDEO_RESOLUTION,
  DEFAULT_VIDEO_DURATION,
  DEFAULT_VIDEO_RESOLUTION,
  EDIT_LORA_DEFAULT_STRENGTHS,
  EDIT_LORA_OPTIONS,
  FACE_VIDEO_RESOLUTION_OPTIONS,
  LEGACY_LAB_MODES,
  LTX_VIDEO_DURATION_OPTIONS,
  LTX_VIDEO_RESOLUTION_OPTIONS,
  type LabUploadPreviewKind,
  type LabUploadSlotId,
  type LabModeConfig,
  type UnifiedLabModeId,
  UNIFIED_LAB_MODES,
  VIDEO_DURATION_OPTIONS,
  VIDEO_RESOLUTION_OPTIONS,
  getDefaultVideoLoraSelection,
  getScail2VideoDurationOptionsForMotionVideo,
  getScail2VideoCost,
  getLabModeConfig,
  getVideoLoraOptions,
  resolveLabModeIdFromTaskType,
} from '@/features/generation/labModeConfig'
import {
  buildDefaultLtxVideoLoraItem,
  DEFAULT_WAN22_VIDEO_V2_COST,
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET,
  getWan22VideoV2Cost,
  getImageToVideoRequestTaskType,
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
  LTX_VIDEO_LORA_OPTIONS,
  normalizeImageToVideoLoraSelection,
  normalizeLtxVideoLoraItems,
  normalizeWan22VideoV2DurationSeconds,
  normalizeWan22VideoV2ResolutionPreset,
  WAN22_VIDEO_V2_RESOLUTION_OPTIONS,
  type LtxVideoLoraItem,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import {
  buildWan22ChainPrefill,
  type Wan22ChainEditMode,
  type Wan22ChainPrefillAsset,
  type Wan22ChainPrefillErrorReason,
} from '@/features/generation/wan22Chain'
import { resolveTemplateVideoApplyState } from '@/utils/templateVideoApplyState'
import { buildStorageFileUrl } from '@/utils/storageUrl'

type UploadedReference = {
  key: string
  preview: string
  name: string
  locked?: boolean
  lockedLabel?: string
}

type PendingReferenceUpload = UploadedReference & {
  uploading: true
}

type UploadedSlotAsset = UploadedReference & {
  previewKind: LabUploadPreviewKind
  uploading?: true
}

type LabAssetUploadSlot = {
  id: LabUploadSlotId
  label: string
  hint: string
  buttonLabel: string
  accept: string
  previewKind: LabUploadPreviewKind
  required: boolean
  item: (UploadedSlotAsset & { progress?: number }) | null
}

type HydratedTemplateState = {
  notice: string
  warning: string
  promptLocked: boolean
  editSettingsLocked: boolean
  videoSettingsLocked: boolean
  applied: boolean
  sourcePostId: number | null
}

const DEFAULT_EDIT_LORA_STRENGTH = 1
export const SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES = 40 * 1024 * 1024
export const SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL = '40MB'
const isScail2ModeId = (modeId: UnifiedLabModeId) => (
  modeId === 'scail2_action_transfer'
  || modeId === 'scail2_video_replacement'
  || modeId === 'scail2_face_swap_v2'
)
const isLtxLabModeId = (modeId: UnifiedLabModeId) => (
  modeId === 'ltx_video' || modeId === 'ltx_video_audio'
)
const reusableOutputPrefixes = ['comfyui-temp/', 'bot-data/', 'bot-data-test/', 'history/', 'template:']
const WAN22_CHAIN_ERROR_KEYS: Record<Wan22ChainPrefillErrorReason, string> = {
  history_empty: 'lab.workbench.wan22_chain_errors.history_empty',
  record_not_found: 'lab.workbench.wan22_chain_errors.record_not_found',
  last_frame_missing: 'lab.workbench.wan22_chain_errors.last_frame_missing',
  previous_record_missing: 'lab.workbench.wan22_chain_errors.previous_record_missing',
  previous_last_frame_missing: 'lab.workbench.wan22_chain_errors.previous_last_frame_missing',
}

const toPositiveNumber = (value: unknown): number | null => {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

const resolveReusableOutputKey = (path?: string | null) => {
  const normalizedPath = String(path || '').trim()
  if (!normalizedPath) return ''
  if (reusableOutputPrefixes.some(prefix => normalizedPath.startsWith(prefix))) {
    return normalizedPath
  }
  return `comfyui-temp/${normalizedPath}`
}

const normalizeTaskIdList = (value: unknown): string[] => {
  const rawItems = (() => {
    if (Array.isArray(value)) return value
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (!trimmed) return []
      if (trimmed.startsWith('[')) {
        try {
          const parsed = JSON.parse(trimmed)
          return Array.isArray(parsed) ? parsed : []
        } catch {
          return trimmed.split(',')
        }
      }
      return trimmed.split(',')
    }
    return []
  })()
  const ordered: string[] = []
  rawItems.forEach((item) => {
    const normalized = String(item || '').trim()
    if (normalized && !ordered.includes(normalized)) {
      ordered.push(normalized)
    }
  })
  return ordered
}

export function useLabWorkbench() {
  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const { loadApplyContext, clearApplyContext } = useGalleryApplyContext()
  const { uploading, progress: uploadProgress, uploadFile } = useUpload()
  const { isSubmitting, submitTask } = useTaskStream()
  const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
  const tasksStore = useTasksStore()

  const currentModeId = ref<UnifiedLabModeId>(DEFAULT_LAB_MODE_ID)
  const prompt = ref('')
  const uploadedReferences = ref<UploadedReference[]>([])
  const pendingReferenceUploads = ref<PendingReferenceUpload[]>([])
  const uploadedSlotAssets = ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>({})
  const pendingUploads = ref(0)

  const selectedEditLora = ref('')
  const customEditLoraStrength = ref(DEFAULT_EDIT_LORA_STRENGTH)
  const selectedVideoLora = ref(getDefaultVideoLoraSelection())
  const ltxLoraItems = ref<LtxVideoLoraItem[]>([])
  const selectedLtxLoraNames = ref<string[]>([])
  const negativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
  const wan22ResolutionPreset = ref<Wan22VideoV2ResolutionPreset>(DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET)
  const resolution = ref(DEFAULT_VIDEO_RESOLUTION)
  const duration = ref(DEFAULT_VIDEO_DURATION)
  const wan22ChainMode = ref<Wan22ChainEditMode | 'default'>('default')
  const wan22PrevTaskId = ref<string | null>(null)
  const wan22ChainTaskIds = ref<string[]>([])
  const wan22ChainBanner = ref('')
  const wan22ChainLoading = ref(false)
  const wan22ChainStitching = ref(false)
  const ltxExtensionNotice = ref('')
  const ltxPrevTaskId = ref<string | null>(null)
  const ltxChainTaskIds = ref<string[]>([])
  const ltxChainStitching = ref(false)
  const scail2MotionVideoDurationSeconds = ref<number | null>(null)

  const templateNotice = ref('')
  const templateWarning = ref('')
  const isTemplateApplied = ref(false)
  const isTemplatePromptLocked = ref(false)
  const isTemplateEditSettingsLocked = ref(false)
  const isTemplateVideoSettingsLocked = ref(false)
  const templateSourcePostId = ref<number | null>(null)

  const currentMode = computed<LabModeConfig>(() => getLabModeConfig(currentModeId.value))
  const unifiedModes = UNIFIED_LAB_MODES
  const legacyModes = LEGACY_LAB_MODES
  const editLoraOptions = EDIT_LORA_OPTIONS
  const videoLoraOptions = getVideoLoraOptions()
  const videoResolutionOptions = computed(() => (
    currentMode.value.id === 'face_video'
      ? FACE_VIDEO_RESOLUTION_OPTIONS
      : isLtxLabModeId(currentMode.value.id)
        ? LTX_VIDEO_RESOLUTION_OPTIONS
        : VIDEO_RESOLUTION_OPTIONS
  ))
  const videoDurationOptions = computed(() => (
    isLtxLabModeId(currentMode.value.id)
      ? LTX_VIDEO_DURATION_OPTIONS
      : isScail2ModeId(currentMode.value.id)
        ? getScail2VideoDurationOptionsForMotionVideo(scail2MotionVideoDurationSeconds.value)
        : VIDEO_DURATION_OPTIONS
  ))
  const ltxLoraOptions = LTX_VIDEO_LORA_OPTIONS
  const wan22ResolutionOptions = WAN22_VIDEO_V2_RESOLUTION_OPTIONS
  let wan22HydrationSeq = 0

  const hasReferences = computed(() => uploadedReferences.value.length > 0)
  const hasAdvancedOptions = computed(() => currentMode.value.supportsAdvancedOptions)
  const hasStructuredUploadSlots = computed(() => (currentMode.value.uploadSlots?.length ?? 0) > 0)
  const displayedReferences = computed(() => [
    ...uploadedReferences.value,
    ...pendingReferenceUploads.value.map(item => ({
      ...item,
      progress: uploadProgress.value,
    })),
  ])
  const canUploadReference = computed(() => (
    currentMode.value.supportsUpload
    && uploadedReferences.value.length + pendingReferenceUploads.value.length < currentMode.value.maxImages
  ))

  const assetUploadSlots = computed<LabAssetUploadSlot[]>(() => (
    currentMode.value.uploadSlots?.map((slot) => {
      const item = uploadedSlotAssets.value[slot.id] ?? null
      return {
        id: slot.id,
        label: t(slot.labelKey),
        hint: t(slot.hintKey),
        buttonLabel: t(slot.buttonKey),
        accept: slot.accept,
        previewKind: slot.previewKind,
        required: slot.required,
        item: item
          ? {
              ...item,
              progress: item.uploading ? uploadProgress.value : undefined,
            }
          : null,
      }
    }) ?? []
  ))

  const referenceTitle = computed(() =>
    currentMode.value.referenceTitleKey ? t(currentMode.value.referenceTitleKey) : '',
  )
  const promptPlaceholder = computed(() => t(currentMode.value.promptPlaceholderKey))
  const showStructuredPromptInput = computed(() => (
    isScail2ModeId(currentMode.value.id) || currentMode.value.id === 'ltx_video_audio'
  ))
  const composerNotice = computed(() => wan22ChainBanner.value || ltxExtensionNotice.value || templateNotice.value)
  const composerWarning = computed(() => templateWarning.value)
  const currentTaskIsWan22VideoV2 = computed(() => (
    currentTask.value?.type === 'wan22_video_v2'
    || currentTask.value?.type === 'custom_video'
    || currentTask.value?.type === 'video_lora'
  ))
  const wan22CurrentTaskCanExtend = computed(() => (
    currentTaskIsWan22VideoV2.value
    && Boolean(currentTask.value?.id && currentTask.value?.extraOutputs?.last_frame?.path)
  ))
  const wan22CurrentTaskCanStitch = computed(() => (
    currentTaskIsWan22VideoV2.value
    && Boolean(currentTask.value?.id && currentTask.value?.resultMeta?.wan22_prev_task_id)
  ))
  const currentTaskIsLtxVideo = computed(() => currentTask.value?.type === 'ltx_video')
  const ltxCurrentTaskCanExtend = computed(() => (
    currentTaskIsLtxVideo.value
    && Boolean(currentTask.value?.id && currentTask.value?.extraOutputs?.last_frame?.path)
  ))
  const ltxCurrentTaskCanStitch = computed(() => (
    currentTaskIsLtxVideo.value
    && !currentTask.value?.resultMeta?.ltx_is_stitched
    && Boolean(currentTask.value?.id && currentTask.value?.resultMeta?.ltx_prev_task_id)
  ))

  const uploadButtonLabel = computed(() => (
    (currentMode.value.id === 'wan22_video_v2' || currentMode.value.id === 'custom_video' || currentMode.value.id === 'ltx_video') && uploadedReferences.value.length === 0
      ? t('lab.workbench.add_start_frame')
      : (currentMode.value.id === 'wan22_video_v2' || currentMode.value.id === 'custom_video' || currentMode.value.id === 'ltx_video') && uploadedReferences.value.length === 1
        ? t('lab.workbench.add_end_frame')
        : currentMode.value.maxImages > 1 && uploadedReferences.value.length === 1
      ? t('lab.workbench.add_second_reference')
      : t('lab.workbench.add_reference')
  ))

  const getDefaultResolutionForMode = (modeId: UnifiedLabModeId) => (
    modeId === 'face_video'
      ? DEFAULT_FACE_VIDEO_RESOLUTION
      : isLtxLabModeId(modeId)
        ? DEFAULT_LTX_VIDEO_RESOLUTION
        : DEFAULT_VIDEO_RESOLUTION
  )

  const cost = computed(() => {
    if (currentMode.value.id === 'edit') {
      return uploadedReferences.value.length >= 2 ? 6 : 2
    }

    if (currentMode.value.id === 'custom_video') {
      return getWan22VideoV2Cost(wan22ResolutionPreset.value, duration.value)
    }

    if (currentMode.value.id === 'face_video') {
      return resolution.value === '1024' ? 36 : 18
    }

    if (isLtxLabModeId(currentMode.value.id)) {
      let multiplier = 1
      if (duration.value === '10') multiplier = 2
      else if (duration.value === '15') multiplier = 3
      else if (duration.value === '20') multiplier = 4
      return 10 * multiplier
    }

    if (isScail2ModeId(currentMode.value.id)) {
      return getScail2VideoCost(duration.value)
    }

    if (currentMode.value.id === 'wan22_video_v2') {
      return getWan22VideoV2Cost(wan22ResolutionPreset.value, duration.value)
    }

    return currentMode.value.baseCost
  })

  const costHint = computed(() => {
    if (currentMode.value.id === 'edit') {
      return t('lab.workbench.cost_hints.edit')
    }

    if (currentMode.value.id === 'custom_video') {
      return t('lab.workbench.cost_hints.custom_video')
    }

    if (currentMode.value.id === 'face_video') {
      return t('lab.workbench.cost_hints.face_video')
    }

    if (isLtxLabModeId(currentMode.value.id)) {
      return currentMode.value.id === 'ltx_video_audio'
        ? t('lab.workbench.cost_hints.ltx_video_audio')
        : t('lab.workbench.cost_hints.ltx_video')
    }

    if (currentMode.value.id === 'wan22_video_v2') {
      return t('lab.workbench.cost_hints.wan22_video_v2')
    }

    if (isScail2ModeId(currentMode.value.id)) {
      return t('lab.workbench.cost_hints.scail2_video')
    }

    return ''
  })

  const canSubmit = computed(() => {
    const hasPrompt = !currentMode.value.promptRequired || isTemplatePromptLocked.value || prompt.value.trim().length > 0
    const hasRequiredUpload = !currentMode.value.supportsUpload || uploadedReferences.value.length > 0
    const hasRequiredSlots = assetUploadSlots.value.every(slot => !slot.required || !!slot.item?.key)
    return hasPrompt && hasRequiredUpload && hasRequiredSlots && pendingUploads.value === 0 && !uploading.value
  })

  const isDirty = computed(() => (
    prompt.value.trim().length > 0
    || uploadedReferences.value.length > 0
    || Object.keys(uploadedSlotAssets.value).length > 0
    || selectedEditLora.value !== ''
    || selectedVideoLora.value !== getDefaultVideoLoraSelection()
    || selectedLtxLoraNames.value.length > 0
    || negativePrompt.value !== DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    || wan22ResolutionPreset.value !== DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
    || wan22ChainMode.value !== 'default'
    || resolution.value !== getDefaultResolutionForMode(currentModeId.value)
    || duration.value !== DEFAULT_VIDEO_DURATION
    || isTemplateApplied.value
  ))

  const revokeReferencePreview = (previewUrl: string | null | undefined) => {
    if (previewUrl?.startsWith('blob:')) {
      URL.revokeObjectURL(previewUrl)
    }
  }

  const clearReferences = () => {
    uploadedReferences.value.forEach(item => revokeReferencePreview(item.preview))
    pendingReferenceUploads.value.forEach(item => revokeReferencePreview(item.preview))
    uploadedReferences.value = []
    pendingReferenceUploads.value = []
  }

  const clearSlotAssets = () => {
    Object.values(uploadedSlotAssets.value).forEach(item => revokeReferencePreview(item?.preview))
    uploadedSlotAssets.value = {}
    scail2MotionVideoDurationSeconds.value = null
  }

  const resetTemplateState = () => {
    templateNotice.value = ''
    templateWarning.value = ''
    isTemplateApplied.value = false
    isTemplatePromptLocked.value = false
    isTemplateEditSettingsLocked.value = false
    isTemplateVideoSettingsLocked.value = false
    templateSourcePostId.value = null
  }

  const resetWan22ChainState = () => {
    wan22ChainMode.value = 'default'
    wan22PrevTaskId.value = null
    wan22ChainTaskIds.value = []
    wan22ChainBanner.value = ''
  }

  const resetLtxExtensionState = () => {
    ltxExtensionNotice.value = ''
    ltxPrevTaskId.value = null
    ltxChainTaskIds.value = []
  }

  const resetFormState = (options?: { preserveMode?: boolean }) => {
    clearReferences()
    clearSlotAssets()
    prompt.value = ''
    selectedEditLora.value = ''
    customEditLoraStrength.value = DEFAULT_EDIT_LORA_STRENGTH
    selectedVideoLora.value = getDefaultVideoLoraSelection()
    ltxLoraItems.value = []
    selectedLtxLoraNames.value = []
    negativePrompt.value = DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    wan22ResolutionPreset.value = DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
    resolution.value = getDefaultResolutionForMode(options?.preserveMode ? currentModeId.value : DEFAULT_LAB_MODE_ID)
    duration.value = DEFAULT_VIDEO_DURATION
    resetTemplateState()
    resetWan22ChainState()
    resetLtxExtensionState()

    if (!options?.preserveMode) {
      currentModeId.value = DEFAULT_LAB_MODE_ID
    }

    setSubmittedTaskId(null)
  }

  const handleRemoveReference = (index: number) => {
    const target = uploadedReferences.value[index]
    if (target?.locked) {
      message.info(target.lockedLabel || t('lab.workbench.wan22_locked_start_frame'))
      return
    }
    revokeReferencePreview(target?.preview)
    uploadedReferences.value.splice(index, 1)
  }

  const applyWan22PrefillAssets = (
    startFrame: Wan22ChainPrefillAsset | null,
    endFrame: Wan22ChainPrefillAsset | null,
  ) => {
    uploadedReferences.value = [startFrame, endFrame]
      .filter((item): item is Wan22ChainPrefillAsset => Boolean(item))
      .map(item => ({ ...item }))
  }

  const resolveWan22ChainErrorMessage = (reason: Wan22ChainPrefillErrorReason) =>
    t(WAN22_CHAIN_ERROR_KEYS[reason])

  const applyWan22ChainPrefill = async (
    mode: Wan22ChainEditMode,
    taskId: string,
  ) => {
    const requestSeq = ++wan22HydrationSeq
    wan22ChainLoading.value = true
    try {
      const chain = await getWan22HistoryChain(taskId)
      if (requestSeq !== wan22HydrationSeq) {
        return false
      }

      const prefill = buildWan22ChainPrefill(mode, taskId, chain.items)
      if (prefill.status === 'error') {
        message.warning(resolveWan22ChainErrorMessage(prefill.reason))
        return false
      }

      resetFormState({ preserveMode: true })
      currentModeId.value = prefill.taskType === 'wan22_video_v2' ? 'wan22_video_v2' : 'custom_video'

      if (prefill.status === 'blank') {
        wan22ChainBanner.value = t('lab.workbench.wan22_first_regenerate_notice')
        return true
      }

      wan22ChainMode.value = prefill.mode
      wan22PrevTaskId.value = prefill.prevTaskId
      wan22ChainTaskIds.value = [...prefill.chainTaskIds]
      applyWan22PrefillAssets(prefill.startFrame, prefill.endFrame)
      prompt.value = prefill.prompt
      negativePrompt.value = prefill.negativePrompt
      wan22ResolutionPreset.value = prefill.resolutionPreset
      duration.value = prefill.duration
      selectedVideoLora.value = normalizeImageToVideoLoraSelection(prefill.loraName)
      wan22ChainBanner.value = prefill.mode === 'extend'
        ? t('lab.workbench.wan22_extend_notice', {
            count: prefill.segmentIndex,
            context: prefill.contextCount,
          })
        : t('lab.workbench.wan22_regenerate_notice', {
            count: prefill.segmentIndex,
            context: prefill.contextCount,
          })
      return true
    } catch (error: any) {
      console.error(error)
      message.error(error?.response?.data?.detail || t('lab.workbench.wan22_chain_errors.load_failed'))
      return false
    } finally {
      if (requestSeq === wan22HydrationSeq) {
        wan22ChainLoading.value = false
      }
    }
  }

  const openWan22CurrentTaskEditor = async (mode: Wan22ChainEditMode) => {
    const taskId = currentTask.value?.id
    if (!taskId) {
      message.warning(t('lab.workbench.wan22_chain_errors.missing_task_id'))
      return
    }
    await applyWan22ChainPrefill(mode, taskId)
  }

  const stitchCurrentWan22Chain = async () => {
    const taskId = currentTask.value?.id
    if (!taskId) {
      message.warning(t('lab.workbench.wan22_chain_errors.missing_task_id'))
      return
    }
    wan22ChainStitching.value = true
    const hide = message.loading(t('lab.workbench.wan22_stitching'), 0)
    try {
      const stitchedRecord = await stitchWan22HistoryChain(taskId)
      hide()
      message.success(t('lab.workbench.wan22_stitch_success'))
      if (stitchedRecord.task_id && stitchedRecord.type) {
        tasksStore.showDetailRecord(stitchedRecord as TaskRecord)
      }
    } catch (error: any) {
      console.error(error)
      hide()
      message.error(error?.response?.data?.detail || t('lab.workbench.wan22_stitch_failed'))
    } finally {
      wan22ChainStitching.value = false
    }
  }

  const applyLtxExtensionPrefill = (
    path?: string | null,
    url?: string | null,
    options?: {
      previousTaskId?: string | null
      chainTaskIds?: unknown
    },
  ) => {
    const key = resolveReusableOutputKey(path)
    if (!key) {
      return false
    }

    clearReferences()
    clearSlotAssets()
    resetTemplateState()
    resetWan22ChainState()
    currentModeId.value = 'ltx_video'
    uploadedReferences.value = [{
      key,
      preview: url || buildStorageFileUrl(key),
      name: t('lab.workbench.ltx_extension_start_frame_name'),
      locked: true,
      lockedLabel: t('lab.workbench.ltx_locked_start_frame'),
    }]
    prompt.value = ''
    setSubmittedTaskId(null)
    const previousTaskId = String(options?.previousTaskId || '').trim()
    const chainTaskIds = normalizeTaskIdList(options?.chainTaskIds)
    ltxPrevTaskId.value = previousTaskId || null
    ltxChainTaskIds.value = previousTaskId
      ? normalizeTaskIdList([...chainTaskIds, previousTaskId])
      : chainTaskIds
    ltxExtensionNotice.value = t('lab.workbench.ltx_extension_notice')
    return true
  }

  const openLtxCurrentTaskEditor = () => {
    const lastFrame = currentTask.value?.extraOutputs?.last_frame
    const taskId = currentTask.value?.id
    const chainTaskIds = currentTask.value?.resultMeta?.ltx_chain_task_ids
      ?? (currentTask.value?.resultMeta?.ltx_prev_task_id
        ? [currentTask.value.resultMeta.ltx_prev_task_id]
        : [])
    if (!applyLtxExtensionPrefill(lastFrame?.path, lastFrame?.url, {
      previousTaskId: taskId,
      chainTaskIds,
    })) {
      message.warning(t('lab.workbench.ltx_extend_missing_last_frame'))
      return
    }
    message.success(t('lab.workbench.ltx_extension_loaded'))
  }

  const stitchCurrentLtxChain = async () => {
    const taskId = currentTask.value?.id
    if (!taskId) {
      message.warning(t('lab.workbench.ltx_chain_errors.missing_task_id'))
      return
    }
    ltxChainStitching.value = true
    const hide = message.loading(t('lab.workbench.ltx_stitching'), 0)
    try {
      const stitchedRecord = await stitchLtxHistoryChain(taskId)
      hide()
      message.success(t('lab.workbench.ltx_stitch_success'))
      if (stitchedRecord.task_id && stitchedRecord.type) {
        tasksStore.showDetailRecord(stitchedRecord as TaskRecord)
      }
    } catch (error: any) {
      console.error(error)
      hide()
      message.error(error?.response?.data?.detail || t('lab.workbench.ltx_stitch_failed'))
    } finally {
      ltxChainStitching.value = false
    }
  }

  const handleRemoveUploadSlot = (slotId: LabUploadSlotId) => {
    const target = uploadedSlotAssets.value[slotId]
    revokeReferencePreview(target?.preview)
    delete uploadedSlotAssets.value[slotId]
    if (slotId === 'motion_video') {
      scail2MotionVideoDurationSeconds.value = null
    }
  }

  const handleAssetVideoMetadata = (slotId: LabUploadSlotId, durationSeconds: number | null) => {
    if (!isScail2ModeId(currentMode.value.id) || slotId !== 'motion_video') {
      return
    }
    scail2MotionVideoDurationSeconds.value = durationSeconds
  }

  const shouldLimitStructuredVideoUpload = (slotId: LabUploadSlotId) => (
    (isScail2ModeId(currentMode.value.id) && slotId === 'motion_video')
    || (currentMode.value.id === 'ltx_video_audio' && slotId === 'input_video')
  )

  watch(selectedEditLora, (nextValue) => {
    if (isTemplateEditSettingsLocked.value) {
      return
    }

    customEditLoraStrength.value = nextValue
      ? (EDIT_LORA_DEFAULT_STRENGTHS[nextValue] ?? DEFAULT_EDIT_LORA_STRENGTH)
      : DEFAULT_EDIT_LORA_STRENGTH
  })

  watch(videoDurationOptions, (options) => {
    if (!isScail2ModeId(currentMode.value.id)) {
      return
    }
    if (!options.some(option => option.value === duration.value)) {
      duration.value = options[0]?.value ?? DEFAULT_VIDEO_DURATION
    }
  }, { immediate: true })

  const syncLtxLoraItems = (names: string[]) => {
    const uniqueNames = Array.from(new Set(names.filter(value => value && value !== '__none__'))).slice(0, 3)
    if (uniqueNames.length < names.filter(value => value && value !== '__none__').length) {
      message.warning(t('lab.workbench.validation.ltx_lora_limit'))
    }
    selectedLtxLoraNames.value = uniqueNames
    ltxLoraItems.value = uniqueNames
      .map((name) => {
        const existing = ltxLoraItems.value.find(item => item.name === name)
        return existing ?? buildDefaultLtxVideoLoraItem(name)
      })
      .filter((item): item is LtxVideoLoraItem => Boolean(item))
  }

  const removeLtxLoraItem = (name: string) => {
    syncLtxLoraItems(selectedLtxLoraNames.value.filter(item => item !== name))
  }

  const updateLtxLoraStrength = (name: string, strength: number | null) => {
    if (typeof strength !== 'number' || !Number.isFinite(strength)) {
      return
    }
    const nextStrength = Math.min(2, Math.max(0.1, Number(strength.toFixed(2))))
    ltxLoraItems.value = ltxLoraItems.value.map(item => (
      item.name === name
        ? { ...item, strength: nextStrength }
        : item
    ))
  }

  const beforeUpload = async (file: File) => {
    if (uploadedReferences.value.length + pendingReferenceUploads.value.length >= currentMode.value.maxImages) {
      message.warning(
        t('template_apply.image_prompt.max_images_warning', {
          count: currentMode.value.maxImages,
        }),
      )
      return false
    }

    pendingUploads.value += 1
    const pendingKey = `pending-${Date.now()}-${file.name}`
    const preview = URL.createObjectURL(file)
    let objectKey: string | null = null
    pendingReferenceUploads.value.push({
      key: pendingKey,
      preview,
      name: file.name,
      uploading: true,
    })

    try {
      objectKey = await uploadFile(file)
      if (!objectKey) {
        return false
      }

      uploadedReferences.value.push({
        key: objectKey,
        preview,
        name: file.name,
      })
      return false
    } finally {
      pendingReferenceUploads.value = pendingReferenceUploads.value.filter(item => item.key !== pendingKey)
      if (!objectKey) {
        revokeReferencePreview(preview)
      }
      pendingUploads.value -= 1
    }
  }

  const beforeUploadSlot = async (slotId: LabUploadSlotId, file: File) => {
    const slot = currentMode.value.uploadSlots?.find(item => item.id === slotId)
    if (!slot) {
      return false
    }

    pendingUploads.value += 1
    const preview = URL.createObjectURL(file)
    const pendingKey = `pending-${slotId}-${Date.now()}-${file.name}`
    let objectKey: string | null = null
    handleRemoveUploadSlot(slotId)
    uploadedSlotAssets.value[slotId] = {
      key: pendingKey,
      preview,
      name: file.name,
      previewKind: slot.previewKind,
      uploading: true,
    }

    try {
      objectKey = await uploadFile(
        file,
        slot.previewKind === 'video' && shouldLimitStructuredVideoUpload(slotId)
          ? {
              maxSizeBytes: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
              maxSizeLabel: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
            }
          : undefined,
      )
      if (!objectKey) {
        return false
      }

      uploadedSlotAssets.value[slotId] = {
        key: objectKey,
        preview,
        name: file.name,
        previewKind: slot.previewKind,
      }
      return false
    } finally {
      if (!objectKey && uploadedSlotAssets.value[slotId]?.key === pendingKey) {
        delete uploadedSlotAssets.value[slotId]
        revokeReferencePreview(preview)
      }
      pendingUploads.value -= 1
    }
  }

  const applySlotTemplateTarget = (
    slotId: LabUploadSlotId,
    target: { objectKey: string; previewUrl?: string | null; name: string; previewKind: LabUploadPreviewKind },
  ) => {
    handleRemoveUploadSlot(slotId)
    uploadedSlotAssets.value[slotId] = {
      key: target.objectKey,
      preview: target.previewUrl ?? '',
      name: target.name,
      previewKind: target.previewKind,
    }
  }

  const buildImageTemplateState = (modeId: UnifiedLabModeId): HydratedTemplateState | null => {
    const ctx = loadApplyContext()
    if (!ctx || route.query.apply !== 'true') {
      return null
    }

    const rawTaskType = String(ctx.task_type ?? '')
    const sourcePostId = toPositiveNumber(ctx.source_post_id)
    const promptValue = typeof ctx.prompt === 'string' ? ctx.prompt : ''

    if (modeId === 'edit' && (rawTaskType === 'edit' || rawTaskType === 'img2img_lora')) {
      prompt.value = promptValue
      selectedEditLora.value = typeof ctx.lora_name === 'string' ? ctx.lora_name : ''
      customEditLoraStrength.value = toPositiveNumber(ctx.lora_strength)
        ?? (selectedEditLora.value ? (EDIT_LORA_DEFAULT_STRENGTHS[selectedEditLora.value] ?? 1) : 1)

      return {
        applied: true,
        promptLocked: promptValue.trim().length > 0,
        editSettingsLocked: !!selectedEditLora.value,
        videoSettingsLocked: false,
        notice: selectedEditLora.value
          ? t('template_apply.image_prompt.template_notice_lora')
          : t('template_apply.image_prompt.template_notice_image'),
        warning: '',
        sourcePostId,
      }
    }

    if (modeId === 'i2i_pro' && rawTaskType === 'i2i_pro') {
      prompt.value = promptValue
      return {
        applied: true,
        promptLocked: promptValue.trim().length > 0,
        editSettingsLocked: false,
        videoSettingsLocked: false,
        notice: t('template_apply.image_prompt.template_notice_i2i'),
        warning: '',
        sourcePostId,
      }
    }

    if (modeId === 'i2i_draw' && rawTaskType === 'i2i_draw') {
      prompt.value = promptValue
      return {
        applied: true,
        promptLocked: promptValue.trim().length > 0,
        editSettingsLocked: false,
        videoSettingsLocked: false,
        notice: t('template_apply.image_prompt.template_notice_image'),
        warning: '',
        sourcePostId,
      }
    }

    return null
  }

  const resolveWan22RouteMode = (value: unknown): Wan22ChainEditMode | null => (
    value === 'extend' || value === 'regenerate' ? value : null
  )

  const hydrateFromRoute = () => {
    resetFormState({ preserveMode: true })

    const templateContext = route.query.apply === 'true' ? loadApplyContext() : null
    const nextModeId = resolveLabModeIdFromTaskType(
      templateContext ? String(templateContext.task_type ?? '') : String(route.query.type ?? ''),
    )

    currentModeId.value = nextModeId
    resolution.value = getDefaultResolutionForMode(nextModeId)

    if (nextModeId === 'wan22_video_v2' || nextModeId === 'custom_video') {
      const wan22Mode = resolveWan22RouteMode(route.query.wan22_mode)
      const wan22TaskId = typeof route.query.wan22_task_id === 'string'
        ? route.query.wan22_task_id
        : ''
      if (wan22Mode && wan22TaskId) {
        void applyWan22ChainPrefill(wan22Mode, wan22TaskId)
        return
      }
      if (nextModeId === 'wan22_video_v2' && !templateContext) {
        return
      }
    }

    if ((nextModeId === 'custom_video' || nextModeId === 'wan22_video_v2') && templateContext) {
      const rawTemplateTaskType = String(templateContext.task_type ?? '')
      const templateTaskType: 'custom_video' | 'video_lora' | 'wan22_video_v2' = nextModeId === 'wan22_video_v2'
        ? 'wan22_video_v2'
        : rawTemplateTaskType === 'video_lora' ? 'video_lora' : 'custom_video'
      const templateState = resolveTemplateVideoApplyState(templateContext, templateTaskType)
      if (templateState) {
        prompt.value = templateState.prompt ?? ''
        if (nextModeId === 'wan22_video_v2') {
          negativePrompt.value = templateState.negativePrompt || DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
        }
        selectedVideoLora.value = templateState.loraName ?? getDefaultVideoLoraSelection()
        wan22ResolutionPreset.value = normalizeWan22VideoV2ResolutionPreset(templateState.resolution)
        duration.value = normalizeWan22VideoV2DurationSeconds(templateState.duration)
        templateNotice.value = templateState.templateApplyNotice
        templateWarning.value = templateState.templateSettingsWarning
        isTemplateApplied.value = templateState.isTemplateApplied
        isTemplatePromptLocked.value = templateState.isTemplatePromptLocked
        isTemplateVideoSettingsLocked.value = templateState.isTemplateVideoSettingsLocked
        templateSourcePostId.value = templateState.sourcePostId
      }
      return
    }

    if (nextModeId === 'ltx_video' && templateContext) {
      const templateState = resolveTemplateVideoApplyState(templateContext, 'ltx_video')
      if (templateState) {
        prompt.value = templateState.prompt ?? ''
        selectedVideoLora.value = normalizeImageToVideoLoraSelection(templateState.loraName)
        ltxLoraItems.value = normalizeLtxVideoLoraItems(templateState.loraItems)
        selectedLtxLoraNames.value = ltxLoraItems.value.map(item => item.name)
        resolution.value = templateState.resolution ?? DEFAULT_LTX_VIDEO_RESOLUTION
        duration.value = templateState.duration ?? DEFAULT_VIDEO_DURATION
        templateNotice.value = templateState.templateApplyNotice
        templateWarning.value = templateState.templateSettingsWarning
        isTemplateApplied.value = templateState.isTemplateApplied
        isTemplatePromptLocked.value = templateState.isTemplatePromptLocked
        isTemplateVideoSettingsLocked.value = templateState.isTemplateVideoSettingsLocked
        templateSourcePostId.value = templateState.sourcePostId
      }
      return
    }

    if (nextModeId === 'ltx_video') {
      const ltxExtensionKey = typeof route.query.ltx_extend_key === 'string'
        ? route.query.ltx_extend_key
        : ''
      if (ltxExtensionKey) {
        const ltxExtensionUrl = typeof route.query.ltx_extend_url === 'string'
          ? route.query.ltx_extend_url
          : ''
        const ltxExtensionTaskId = typeof route.query.ltx_extend_task_id === 'string'
          ? route.query.ltx_extend_task_id
          : ''
        if (applyLtxExtensionPrefill(ltxExtensionKey, ltxExtensionUrl, {
          previousTaskId: ltxExtensionTaskId,
          chainTaskIds: route.query.ltx_chain_task_ids,
        })) {
          message.success(t('lab.workbench.ltx_extension_loaded'))
        }
        return
      }
    }

    if ((nextModeId === 'face_swap' || nextModeId === 'face_video') && templateContext) {
      const rawTaskType = String(templateContext.task_type ?? '')
      const targetSlotId = nextModeId === 'face_video' ? 'target_video' : 'target_image'
      if (rawTaskType === nextModeId && templateContext.input_file) {
        applySlotTemplateTarget(targetSlotId, {
          objectKey: String(templateContext.input_file),
          previewUrl: typeof templateContext.input_file_url === 'string'
            ? templateContext.input_file_url
            : null,
          name: t(nextModeId === 'face_video'
            ? 'lab.workbench.upload_slots.target_video'
            : 'lab.workbench.upload_slots.target_image'),
          previewKind: nextModeId === 'face_video' ? 'video' : 'image',
        })
        isTemplateApplied.value = true
        templateNotice.value = t(nextModeId === 'face_video'
          ? 'lab.workbench.template_notices.face_video'
          : 'lab.workbench.template_notices.face_swap')
        templateSourcePostId.value = toPositiveNumber(templateContext.source_post_id)
        if (nextModeId === 'face_video' && templateContext.width != null) {
          resolution.value = String(templateContext.width) === '1024' ? '1024' : DEFAULT_FACE_VIDEO_RESOLUTION
        }
      }
      return
    }

    const imageTemplateState = buildImageTemplateState(nextModeId)
    if (imageTemplateState) {
      templateNotice.value = imageTemplateState.notice
      templateWarning.value = imageTemplateState.warning
      isTemplateApplied.value = imageTemplateState.applied
      isTemplatePromptLocked.value = imageTemplateState.promptLocked
      isTemplateEditSettingsLocked.value = imageTemplateState.editSettingsLocked
      isTemplateVideoSettingsLocked.value = imageTemplateState.videoSettingsLocked
      templateSourcePostId.value = imageTemplateState.sourcePostId
    }
  }

  watch(
    () => [
      route.query.type,
      route.query.apply,
      route.query.wan22_mode,
      route.query.wan22_task_id,
      route.query.ltx_extend_key,
      route.query.ltx_extend_url,
      route.query.ltx_extend_task_id,
      route.query.ltx_chain_task_ids,
    ],
    hydrateFromRoute,
    { immediate: true },
  )

  const confirmSwitchIfNeeded = async () => {
    if (!isDirty.value) {
      return true
    }

    return new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: t('lab.workbench.switch_confirm_title'),
        content: t('lab.workbench.switch_confirm_content'),
        okText: t('lab.workbench.switch_confirm_ok'),
        cancelText: t('lab.workbench.switch_confirm_cancel'),
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  }

  const selectMode = async (nextModeId: UnifiedLabModeId) => {
    if (nextModeId === currentModeId.value) {
      return
    }

    const confirmed = await confirmSwitchIfNeeded()
    if (!confirmed) {
      return
    }

    clearApplyContext()
    const targetRouteName = route.name === 'LabPreview' ? 'LabPreview' : 'CustomFeatures'
    await router.replace({
      name: targetRouteName,
      query: {
        type: getLabModeConfig(nextModeId).taskType,
      },
    })
  }

  const openLegacyMode = async (modeId: typeof LEGACY_LAB_MODES[number]['id']) => {
    const mode = getLabModeConfig(modeId)
    if (!mode.legacyRouteName) {
      return
    }

    await router.push({
      name: mode.legacyRouteName,
      query: {
        type: mode.taskType,
        title: t(mode.titleKey),
        cost: String(mode.baseCost),
      },
    })
  }

  const handleSubmit = async () => {
    if (hasStructuredUploadSlots.value && !assetUploadSlots.value.every(slot => !slot.required || !!slot.item?.key)) {
      message.warning(t('lab.workbench.validation.upload_slots_required'))
      return
    }

    if (currentMode.value.supportsUpload && uploadedReferences.value.length === 0) {
      message.warning(t('lab.workbench.validation.upload_first'))
      return
    }

    if (currentMode.value.promptRequired && !isTemplatePromptLocked.value && prompt.value.trim().length === 0) {
      message.warning(t('lab.workbench.validation.prompt_required'))
      return
    }

    if (isScail2ModeId(currentMode.value.id)) {
      const referenceImage = uploadedSlotAssets.value.reference_image?.key
      const motionVideo = uploadedSlotAssets.value.motion_video?.key

      if (!referenceImage || !motionVideo) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }

      const payload = buildGenerationTaskPayload({
        taskType: currentMode.value.taskType,
        images: [referenceImage, motionVideo],
        duration: Number(duration.value),
        prompt: prompt.value,
        negativePrompt: negativePrompt.value,
        promptTarget: 'inputs',
        isTemplate: false,
      })

      const taskId = await submitTask(payload, t(currentMode.value.titleKey))
      if (taskId) {
        setSubmittedTaskId(taskId)
      }
      return
    }

    if (currentMode.value.id === 'ltx_video_audio') {
      const inputVideo = uploadedSlotAssets.value.input_video?.key

      if (!inputVideo) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }

      const payload = buildGenerationTaskPayload({
        taskType: 'ltx_video',
        images: [inputVideo],
        prompt: prompt.value,
        promptTarget: 'inputs',
        resolution: resolution.value,
        duration: Number(duration.value),
        loraItems: ltxLoraItems.value,
        extraInputs: {
          ltx_mode: 'v2v_audio',
          video: inputVideo,
          extract_last_frame: true,
        },
        isTemplate: isTemplateApplied.value,
        sourcePostId: templateSourcePostId.value,
      })

      const taskId = await submitTask(payload, t(currentMode.value.titleKey))
      if (taskId) {
        setSubmittedTaskId(taskId)
      }
      return
    }

    if (currentMode.value.id === 'face_swap' || currentMode.value.id === 'face_video') {
      const faceImage = uploadedSlotAssets.value.face_image?.key
      const targetSlot = currentMode.value.id === 'face_video' ? 'target_video' : 'target_image'
      const targetAsset = uploadedSlotAssets.value[targetSlot]?.key

      if (!faceImage || !targetAsset) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }

      const payload = buildSwapTaskPayload({
        taskType: currentMode.value.id,
        faceImage,
        targetField: currentMode.value.id === 'face_video' ? 'target_video' : 'target_image',
        targetAsset,
        resolution: currentMode.value.id === 'face_video' ? Number(resolution.value) : undefined,
        isTemplate: isTemplateApplied.value,
        sourcePostId: templateSourcePostId.value,
      })

      const taskId = await submitTask(payload, t(currentMode.value.titleKey))
      if (taskId) {
        setSubmittedTaskId(taskId)
      }
      return
    }

    if (currentMode.value.id === 'custom_video' || currentMode.value.id === 'wan22_video_v2') {
      const taskType = currentMode.value.id === 'wan22_video_v2'
        ? 'wan22_video_v2'
        : getImageToVideoRequestTaskType(currentMode.value.taskType, selectedVideoLora.value)
      const payload = buildGenerationTaskPayload({
        taskType,
        images: uploadedReferences.value.map(item => item.key),
        duration: Number(normalizeWan22VideoV2DurationSeconds(duration.value)),
        prompt: prompt.value,
        negativePrompt: negativePrompt.value,
        promptTarget: 'inputs',
        loraName: currentMode.value.id === 'custom_video'
          ? getImageToVideoPayloadLoraName(currentMode.value.taskType, selectedVideoLora.value)
          : undefined,
        extraInputs: {
          use_end_frame: uploadedReferences.value.length >= 2,
          resolution_preset: wan22ResolutionPreset.value,
          wan22_prev_task_id: wan22PrevTaskId.value,
          wan22_chain_task_ids: wan22ChainTaskIds.value,
        },
        isTemplate: isTemplateApplied.value,
        sourcePostId: templateSourcePostId.value,
      })

      const taskId = await submitTask(payload, t(currentMode.value.titleKey))
      if (taskId) {
        setSubmittedTaskId(taskId)
      }
      return
    }

    const payload = buildGenerationTaskPayload({
      taskType: currentMode.value.taskType,
      images: uploadedReferences.value.map(item => item.key),
      prompt: prompt.value,
      promptTarget: currentMode.value.promptTarget,
      loraName: currentMode.value.id === 'edit'
        ? (selectedEditLora.value || undefined)
        : getImageToVideoPayloadLoraName(currentMode.value.taskType, selectedVideoLora.value),
      loraStrength: currentMode.value.id === 'edit' && selectedEditLora.value
        ? Number(customEditLoraStrength.value)
        : currentMode.value.id === 'ltx_video'
          ? getImageToVideoPayloadLoraStrength(currentMode.value.taskType, selectedVideoLora.value)
        : undefined,
      resolution: currentMode.value.id === 'ltx_video'
          ? resolution.value
          : undefined,
      duration: currentMode.value.id === 'ltx_video'
        ? Number(duration.value)
        : undefined,
      loraItems: currentMode.value.id === 'ltx_video' ? ltxLoraItems.value : undefined,
      extraInputs: currentMode.value.id === 'ltx_video'
        ? {
            ltx_mode: uploadedReferences.value.length >= 2 ? 'flf2v' : 'i2v',
            use_end_frame: uploadedReferences.value.length >= 2,
            extract_last_frame: true,
            ltx_prev_task_id: ltxPrevTaskId.value || undefined,
            ltx_chain_task_ids: ltxChainTaskIds.value.length > 0 ? ltxChainTaskIds.value : undefined,
          }
        : undefined,
      normalizeEditLoraTask: currentMode.value.id === 'edit',
      isTemplate: isTemplateApplied.value,
      sourcePostId: templateSourcePostId.value,
    })

    const taskId = await submitTask(payload, t(currentMode.value.titleKey))
    if (taskId) {
      setSubmittedTaskId(taskId)
    }
  }

  const resetAfterResult = () => {
    resetFormState({ preserveMode: true })
  }

  onBeforeUnmount(() => {
    clearReferences()
    clearSlotAssets()
  })

  return {
    unifiedModes,
    legacyModes,
    currentMode,
    currentModeId,
    prompt,
    uploadedReferences,
    displayedReferences,
    assetUploadSlots,
    canUploadReference,
    promptPlaceholder,
    showStructuredPromptInput,
    isSubmitting,
    currentTask,
    isImageUrl,
    downloadResult,
    selectMode,
    openLegacyMode,
    beforeUpload,
    beforeUploadSlot,
    handleAssetVideoMetadata,
    handleRemoveReference,
    handleRemoveUploadSlot,
    handleSubmit,
    resetAfterResult,
    cost,
    costHint,
    canSubmit,
    hasReferences,
    hasAdvancedOptions,
    referenceTitle,
    uploadButtonLabel,
    editLoraOptions,
    selectedEditLora,
    customEditLoraStrength,
    videoLoraOptions,
    selectedVideoLora,
    ltxLoraOptions,
    selectedLtxLoraNames,
    ltxLoraItems,
    syncLtxLoraItems,
    removeLtxLoraItem,
    updateLtxLoraStrength,
    negativePrompt,
    wan22ResolutionOptions,
    wan22ResolutionPreset,
    videoResolutionOptions,
    resolution,
    videoDurationOptions,
    duration,
    templateNotice,
    templateWarning,
    composerNotice,
    composerWarning,
    isTemplateApplied,
    isTemplatePromptLocked,
    isTemplateEditSettingsLocked,
    isTemplateVideoSettingsLocked,
    currentTaskIsWan22VideoV2,
    wan22CurrentTaskCanExtend,
    wan22CurrentTaskCanStitch,
    currentTaskIsLtxVideo,
    ltxCurrentTaskCanExtend,
    ltxCurrentTaskCanStitch,
    wan22ChainLoading,
    wan22ChainStitching,
    ltxChainStitching,
    openWan22CurrentTaskEditor,
    openLtxCurrentTaskEditor,
    stitchCurrentWan22Chain,
    stitchCurrentLtxChain,
  }
}
