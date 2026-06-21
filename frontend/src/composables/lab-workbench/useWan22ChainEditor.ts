import { computed, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import { getWan22HistoryChain, stitchWan22HistoryChain } from '@/api/gallery'
import {
  normalizeImageToVideoLoraSelection,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import {
  buildWan22ChainPrefill,
  type Wan22ChainEditMode,
  type Wan22ChainPrefillAsset,
  type Wan22ChainPrefillErrorReason,
} from '@/features/generation/wan22Chain'
import type { UnifiedLabModeId } from '@/features/generation/labModeConfig'
import type { TaskRecord } from '@/types/gallery'
import type { TranslateFn, UploadedReference } from './types'

const WAN22_CHAIN_ERROR_KEYS: Record<Wan22ChainPrefillErrorReason, string> = {
  history_empty: 'lab.workbench.wan22_chain_errors.history_empty',
  record_not_found: 'lab.workbench.wan22_chain_errors.record_not_found',
  last_frame_missing: 'lab.workbench.wan22_chain_errors.last_frame_missing',
  previous_record_missing: 'lab.workbench.wan22_chain_errors.previous_record_missing',
  previous_last_frame_missing: 'lab.workbench.wan22_chain_errors.previous_last_frame_missing',
}

type UseWan22ChainEditorOptions = {
  currentModeId: Ref<UnifiedLabModeId>
  currentTask: Ref<any | null>
  uploadedReferences: Ref<UploadedReference[]>
  prompt: Ref<string>
  negativePrompt: Ref<string>
  wan22ResolutionPreset: Ref<Wan22VideoV2ResolutionPreset>
  duration: Ref<string>
  selectedVideoLora: Ref<string>
  resetFormState: (options?: { preserveMode?: boolean }) => void
  showDetailRecord: (record: TaskRecord) => void
  t: TranslateFn
}

export function useWan22ChainEditor({
  currentModeId,
  currentTask,
  uploadedReferences,
  prompt,
  negativePrompt,
  wan22ResolutionPreset,
  duration,
  selectedVideoLora,
  resetFormState,
  showDetailRecord,
  t,
}: UseWan22ChainEditorOptions) {
  const wan22ChainMode = ref<Wan22ChainEditMode | 'default'>('default')
  const wan22PrevTaskId = ref<string | null>(null)
  const wan22ChainTaskIds = ref<string[]>([])
  const wan22ChainBanner = ref('')
  const wan22ChainLoading = ref(false)
  const wan22ChainStitching = ref(false)
  let wan22HydrationSeq = 0

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

  const resetWan22ChainState = () => {
    wan22ChainMode.value = 'default'
    wan22PrevTaskId.value = null
    wan22ChainTaskIds.value = []
    wan22ChainBanner.value = ''
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
        showDetailRecord(stitchedRecord as TaskRecord)
      }
    } catch (error: any) {
      console.error(error)
      hide()
      message.error(error?.response?.data?.detail || t('lab.workbench.wan22_stitch_failed'))
    } finally {
      wan22ChainStitching.value = false
    }
  }

  return {
    wan22ChainMode,
    wan22PrevTaskId,
    wan22ChainTaskIds,
    wan22ChainBanner,
    wan22ChainLoading,
    wan22ChainStitching,
    currentTaskIsWan22VideoV2,
    wan22CurrentTaskCanExtend,
    wan22CurrentTaskCanStitch,
    resetWan22ChainState,
    applyWan22ChainPrefill,
    openWan22CurrentTaskEditor,
    stitchCurrentWan22Chain,
  }
}
