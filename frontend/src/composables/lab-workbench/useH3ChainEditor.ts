import { computed, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import { stitchMiniMaxH3HistoryChain } from '@/api/gallery'
import type { UnifiedLabModeId } from '@/features/generation/labModeConfig'
import type { TaskRecord } from '@/types/gallery'
import { resolveMediaUrl } from '@/utils/mediaUrl'
import type { TranslateFn, UploadedReference } from './types'

const H3_IMAGE_TYPES = new Set([
  'minimax_h3_i2v',
  'minimax_h3_flf2v',
  'minimax_h3_ref2v',
])

type UseH3ChainEditorOptions = {
  currentModeId: Ref<UnifiedLabModeId>
  currentTask: Ref<any | null>
  minimaxH3Mode: Ref<'t2v' | 'i2v' | 'flf2v' | 'ref2v'>
  uploadedReferences: Ref<UploadedReference[]>
  prompt: Ref<string>
  clearReferences: () => void
  clearSlotAssets: () => void
  resetTemplateState: () => void
  resetWan22ChainState: () => void
  resetLtxExtensionState: () => void
  setSubmittedTaskId: (taskId: string | null) => void
  showDetailRecord: (record: TaskRecord) => void
  t: TranslateFn
}

export function useH3ChainEditor(options: UseH3ChainEditorOptions) {
  const h3PrevTaskId = ref<string | null>(null)
  const h3ExtensionNotice = ref('')
  const h3ChainStitching = ref(false)
  const h3IsExtension = computed(() => Boolean(h3PrevTaskId.value))
  const currentTaskIsH3ImageVideo = computed(() => H3_IMAGE_TYPES.has(
    String(options.currentTask.value?.type || ''),
  ))
  const h3CurrentTaskCanExtend = computed(() => (
    currentTaskIsH3ImageVideo.value
    && !options.currentTask.value?.resultMeta?.minimax_h3_is_stitched
    && Boolean(options.currentTask.value?.id && options.currentTask.value?.extraOutputs?.last_frame?.path)
  ))
  const h3CurrentTaskCanStitch = computed(() => (
    currentTaskIsH3ImageVideo.value
    && !options.currentTask.value?.resultMeta?.minimax_h3_is_stitched
    && Boolean(options.currentTask.value?.resultMeta?.minimax_h3_prev_task_id)
  ))

  const resetH3ExtensionState = () => {
    h3PrevTaskId.value = null
    h3ExtensionNotice.value = ''
  }

  const applyH3ExtensionPrefill = (
    path?: string | null,
    url?: string | null,
    previousTaskId?: string | null,
  ) => {
    const key = String(path || '').trim()
    const taskId = String(previousTaskId || '').trim()
    if (!key || !taskId) return false
    options.clearReferences()
    options.clearSlotAssets()
    options.resetTemplateState()
    options.resetWan22ChainState()
    options.resetLtxExtensionState()
    options.currentModeId.value = 'minimax_h3'
    options.minimaxH3Mode.value = 'i2v'
    options.uploadedReferences.value = [{
      key,
      preview: url || resolveMediaUrl(key),
      name: options.t('lab.workbench.minimax_h3_extension_start_frame_name'),
      locked: true,
      lockedLabel: options.t('lab.workbench.minimax_h3_locked_start_frame'),
    }]
    options.prompt.value = ''
    h3PrevTaskId.value = taskId
    h3ExtensionNotice.value = options.t('lab.workbench.minimax_h3_extension_notice')
    options.setSubmittedTaskId(null)
    return true
  }

  const openH3CurrentTaskEditor = () => {
    const lastFrame = options.currentTask.value?.extraOutputs?.last_frame
    if (!applyH3ExtensionPrefill(
      lastFrame?.path,
      lastFrame?.url,
      options.currentTask.value?.id,
    )) {
      message.warning(options.t('lab.workbench.minimax_h3_extend_missing_last_frame'))
      return
    }
    message.success(options.t('lab.workbench.minimax_h3_extension_loaded'))
  }

  const stitchCurrentH3Chain = async () => {
    const taskId = options.currentTask.value?.id
    if (!taskId) return
    h3ChainStitching.value = true
    const hide = message.loading(options.t('lab.workbench.minimax_h3_stitching'), 0)
    try {
      const record = await stitchMiniMaxH3HistoryChain(taskId)
      hide()
      message.success(options.t('lab.workbench.minimax_h3_stitch_success'))
      if (record.task_id && record.type) options.showDetailRecord(record as TaskRecord)
    } catch (error: any) {
      hide()
      message.error(error?.response?.data?.detail || options.t('lab.workbench.minimax_h3_stitch_failed'))
    } finally {
      h3ChainStitching.value = false
    }
  }

  return {
    h3PrevTaskId,
    h3ExtensionNotice,
    h3ChainStitching,
    h3IsExtension,
    currentTaskIsH3ImageVideo,
    h3CurrentTaskCanExtend,
    h3CurrentTaskCanStitch,
    resetH3ExtensionState,
    applyH3ExtensionPrefill,
    openH3CurrentTaskEditor,
    stitchCurrentH3Chain,
  }
}
