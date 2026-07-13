import { computed, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import { stitchLtxHistoryChain } from '@/api/gallery'
import type { UnifiedLabModeId } from '@/features/generation/labModeConfig'
import type { TaskRecord } from '@/types/gallery'
import { buildStorageFileUrl } from '@/utils/storageUrl'
import type { TranslateFn, UploadedReference } from './types'

const reusableOutputPrefixes = ['comfyui-temp/', 'bot-data/', 'bot-data-test/', 'history/', 'template:']

export const resolveReusableOutputKey = (path?: string | null) => {
  const normalizedPath = String(path || '').trim()
  if (!normalizedPath) return ''
  if (reusableOutputPrefixes.some(prefix => normalizedPath.startsWith(prefix))) {
    return normalizedPath
  }
  return `comfyui-temp/${normalizedPath}`
}

export const normalizeTaskIdList = (value: unknown): string[] => {
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

type UseLtxChainEditorOptions = {
  currentModeId: Ref<UnifiedLabModeId>
  currentTask: Ref<any | null>
  uploadedReferences: Ref<UploadedReference[]>
  prompt: Ref<string>
  clearReferences: () => void
  clearSlotAssets: () => void
  resetTemplateState: () => void
  resetWan22ChainState: () => void
  setSubmittedTaskId: (taskId: string | null) => void
  showDetailRecord: (record: TaskRecord) => void
  t: TranslateFn
}

export function useLtxChainEditor({
  currentModeId,
  currentTask,
  uploadedReferences,
  prompt,
  clearReferences,
  clearSlotAssets,
  resetTemplateState,
  resetWan22ChainState,
  setSubmittedTaskId,
  showDetailRecord,
  t,
}: UseLtxChainEditorOptions) {
  const ltxExtensionNotice = ref('')
  const ltxPrevTaskId = ref<string | null>(null)
  const ltxChainTaskIds = ref<string[]>([])
  const ltxChainStitching = ref(false)

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

  const resetLtxExtensionState = () => {
    ltxExtensionNotice.value = ''
    ltxPrevTaskId.value = null
    ltxChainTaskIds.value = []
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
        showDetailRecord(stitchedRecord as TaskRecord)
      }
    } catch (error: any) {
      console.error(error)
      hide()
      message.error(error?.response?.data?.detail || t('lab.workbench.ltx_stitch_failed'))
    } finally {
      ltxChainStitching.value = false
    }
  }

  return {
    ltxExtensionNotice,
    ltxPrevTaskId,
    ltxChainTaskIds,
    ltxChainStitching,
    currentTaskIsLtxVideo,
    ltxCurrentTaskCanExtend,
    ltxCurrentTaskCanStitch,
    resetLtxExtensionState,
    applyLtxExtensionPrefill,
    openLtxCurrentTaskEditor,
    stitchCurrentLtxChain,
  }
}
