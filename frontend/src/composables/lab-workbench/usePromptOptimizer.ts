import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import api from '@/api'
import { getLabModeConfig, type UnifiedLabModeId } from '@/features/generation/labModeConfig'
import { useTasksStore } from '@/stores/tasks'
import type {
  PromptOptimizationOriginDraft,
  Task,
} from '@/stores/taskStoreTypes'
import type { UploadedReference } from './types'

export type PromptOptimizerTemplate = {
  id: string
  version: number
  label: string
  description: string
  is_default: boolean
}

type PromptTextStreamCapability = {
  enabled: boolean
  schema_version: string
  events: string[]
  fields: string[]
}

type PromptOptimizerOptions = {
  currentModeId: Ref<UnifiedLabModeId>
  prompt: Ref<string>
  duration: Ref<string>
  uploadedReferences: Ref<UploadedReference[]>
  selectedCharacterIds: Ref<string[]>
  useT2VReferences?: Ref<boolean>
  environmentSource?: Ref<'official' | 'upload'>
  selectedEnvironmentId?: Ref<string>
  minimaxH3Mode?: Ref<'t2v' | 'i2v' | 'flf2v' | 'ref2v'>
  captureOriginDraft?: () => PromptOptimizationOriginDraft
  applyOriginDraft?: (draft: PromptOptimizationOriginDraft) => void | Promise<void>
}

export function usePromptOptimizer(options: PromptOptimizerOptions) {
  const tasksStore = useTasksStore()
  const templates = ref<PromptOptimizerTemplate[]>([])
  const selectedTemplateRef = ref('')
  const originalPrompt = ref<string | null>(null)
  const currentTaskId = ref<string | null>(null)
  const streamPreview = ref('')
  const textStreamCapability = ref<PromptTextStreamCapability | null>(null)
  let stopped = false

  const isSupportedMode = computed(() => ['ltx_video_v2', 'ltx_t2v', 'minimax_h3'].includes(options.currentModeId.value))
  const isAvailable = computed(() => isSupportedMode.value && templates.value.length > 0)
  const targetTaskType = computed(() => (
    options.currentModeId.value === 'minimax_h3'
      ? `minimax_h3_${options.minimaxH3Mode?.value ?? 't2v'}`
      : options.currentModeId.value === 'ltx_t2v'
      ? (options.useT2VReferences?.value ?? options.selectedCharacterIds.value.length > 0) ? 'ltx_t2v_ic' : 'ltx_t2v'
      : 'ltx_video_v2'
  ))
  const mediaFingerprint = () => JSON.stringify({
    mode: options.currentModeId.value,
    duration: Number(options.duration.value),
    media: options.uploadedReferences.value.map(item => item.referenceRef ?? item.key),
    characters: options.selectedCharacterIds.value,
    environmentSource: options.environmentSource?.value ?? 'upload',
    environmentId: options.selectedEnvironmentId?.value ?? '',
    minimaxH3Mode: options.minimaxH3Mode?.value ?? '',
  })
  const mediaContractReady = computed(() => {
    if (options.currentModeId.value === 'minimax_h3') {
      if (options.minimaxH3Mode?.value === 'ref2v') {
        return options.uploadedReferences.value.length >= 1
          && options.uploadedReferences.value.length <= 4
      }
      const expected = options.minimaxH3Mode?.value === 'flf2v'
        ? 2
        : options.minimaxH3Mode?.value === 'i2v' ? 1 : 0
      return options.uploadedReferences.value.length === expected
    }
    if (options.currentModeId.value === 'ltx_video_v2') {
      return options.uploadedReferences.value.length >= 1
    }
    if (targetTaskType.value === 'ltx_t2v') {
      return !(options.useT2VReferences?.value ?? false)
        && options.uploadedReferences.value.length === 0
    }
    return options.selectedCharacterIds.value.length === 2
      && ((options.environmentSource?.value ?? 'upload') === 'official'
        ? Boolean(options.selectedEnvironmentId?.value) && options.uploadedReferences.value.length === 0
        : options.uploadedReferences.value.length === 1)
  })
  const activeOptimizerTask = computed(() => tasksStore.activeTasks.find(task => (
    task.kind === 'prompt_optimization'
    && (task.status === 'pending' || task.status === 'running')
  )))
  const currentTask = computed(() => tasksStore.activeTasks.find(task => task.id === currentTaskId.value))
  const isOptimizing = computed(() => Boolean(activeOptimizerTask.value))
  const canOptimize = computed(() => (
    isAvailable.value
    && !isOptimizing.value
    && options.prompt.value.trim().length > 0
    && mediaContractReady.value
  ))
  const canRestore = computed(() => originalPrompt.value !== null)
  const failedPartial = computed(() => currentTask.value?.error ? streamPreview.value : '')
  const refundStatus = computed<'pending' | 'refunded' | ''>(() => (
    currentTask.value?.refundStatus === 'refunded'
      ? 'refunded'
      : currentTask.value?.status === 'failed' ? 'pending' : ''
  ))

  const loadCapabilities = async () => {
    if (!isSupportedMode.value) return
    const response = await api.get('/prompt-optimizations/capabilities', {
      params: { target_task_type: targetTaskType.value },
    })
    templates.value = response.data.templates ?? []
    textStreamCapability.value = response.data.text_stream ?? null
    const defaultTemplate = templates.value.find(item => item.is_default) ?? templates.value[0]
    if (!templates.value.some(item => `${item.id}@${item.version}` === selectedTemplateRef.value)) {
      selectedTemplateRef.value = defaultTemplate
        ? `${defaultTemplate.id}@${defaultTemplate.version}`
        : ''
    }
  }

  const parseSelectedTemplate = () => {
    const [id, rawVersion] = selectedTemplateRef.value.split('@')
    const version = Number(rawVersion)
    if (!id || !Number.isInteger(version)) throw new Error('invalid template selection')
    return { id, version }
  }

  const defaultOriginDraft = (original: string): PromptOptimizationOriginDraft => ({
    modeId: options.currentModeId.value,
    routeType: getLabModeConfig(options.currentModeId.value).taskType,
    prompt: original,
    duration: options.duration.value,
    uploadedReferences: options.uploadedReferences.value.map(item => ({ ...item })),
    settings: {
      selectedCharacterIds: [...options.selectedCharacterIds.value],
      useT2VReferences: options.useT2VReferences?.value ?? false,
      environmentSource: options.environmentSource?.value ?? 'upload',
      selectedEnvironmentId: options.selectedEnvironmentId?.value ?? '',
      minimaxH3Mode: options.minimaxH3Mode?.value ?? 't2v',
    },
  })

  const optimizePrompt = async () => {
    if (!canOptimize.value) return
    const original = options.prompt.value
    const templateRef = parseSelectedTemplate()
    const clientRequestId = crypto.randomUUID()
    try {
      const isT2vIc = targetTaskType.value === 'ltx_t2v_ic'
      const isH3Ref2v = targetTaskType.value === 'minimax_h3_ref2v'
      const response = await api.post('/prompt-optimizations/tasks', {
        client_request_id: clientRequestId,
        target_task_type: targetTaskType.value,
        template: templateRef,
        prompt: original,
        context: { duration_seconds: Number(options.duration.value) },
        media: isT2vIc || isH3Ref2v ? []
          : targetTaskType.value === 'ltx_t2v'
            ? []
            : options.uploadedReferences.value.map((item, index) => ({
                role: index === 0 ? 'start_image' : 'end_image',
                object_key: item.key,
              })),
        reference_refs: isH3Ref2v
          ? options.uploadedReferences.value.map(item => item.referenceRef ?? ({
              source: 'upload' as const,
              object_key: item.key,
            }))
          : undefined,
        character_refs: isT2vIc ? options.selectedCharacterIds.value.map((value) => {
          const [source, id] = value.includes(':') ? value.split(':', 2) : ['private', value]
          return { source, id }
        }) : undefined,
        environment_ref: isT2vIc
          ? (options.environmentSource?.value ?? 'upload') === 'official'
            ? { source: 'official', id: options.selectedEnvironmentId?.value }
            : { source: 'upload', object_key: options.uploadedReferences.value[0].key }
          : undefined,
      })
      const taskId = String(response.data.task_id)
      const originDraft = options.captureOriginDraft?.() ?? defaultOriginDraft(original)
      tasksStore.addPromptOptimizationTask(taskId, '提示词优化', {
        clientRequestId,
        originalPrompt: original,
        contextFingerprint: mediaFingerprint(),
        templateRef,
        originDraft,
      })
      currentTaskId.value = taskId
      streamPreview.value = ''
      message.success('提示词优化已进入后台，可切换到其他页面。')
    } catch {
      message.error('提示词优化提交失败，请稍后重试。')
    }
  }

  const applyTaskResult = async (task: Task) => {
    if (!task.resultText || !task.promptOptimization) return
    await options.applyOriginDraft?.(task.promptOptimization.originDraft)
    originalPrompt.value = task.promptOptimization.originalPrompt
    options.prompt.value = task.resultText
    tasksStore.markPromptTaskApplied(task.id)
    currentTaskId.value = task.id
  }

  const restoreOriginalPrompt = () => {
    if (originalPrompt.value === null) return
    options.prompt.value = originalPrompt.value
    originalPrompt.value = null
  }

  watch(
    [isSupportedMode, targetTaskType],
    async ([supported]) => {
      templates.value = []
      if (!supported) return
      try {
        await loadCapabilities()
      } catch {
        templates.value = []
      }
    },
    { immediate: true },
  )

  watch(
    () => tasksStore.activeTasks.map(task => ({
      id: task.id,
      status: task.status,
      resultText: task.resultText,
      autoApplied: task.promptOptimization?.autoApplied,
    })),
    () => {
      if (stopped) return
      const task = tasksStore.activeTasks.find(item => (
        item.kind === 'prompt_optimization'
        && item.status === 'success'
        && item.resultText
        && !item.promptOptimization?.autoApplied
      ))
      if (!task?.promptOptimization) return
      const unchanged = mediaFingerprint() === task.promptOptimization.contextFingerprint
        && options.prompt.value === task.promptOptimization.originalPrompt
      if (unchanged) {
        void applyTaskResult(task)
      }
    },
    { deep: true },
  )

  watch(
    [options.currentModeId, () => tasksStore.pendingPromptApplyTaskId],
    ([modeId]) => {
      tasksStore.consumePromptTaskApply(modeId, applyTaskResult)
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    stopped = true
  })

  return {
    isPromptOptimizerAvailable: isAvailable,
    canOptimizePrompt: canOptimize,
    canRestoreOriginalPrompt: canRestore,
    isOptimizingPrompt: isOptimizing,
    promptOptimizerStreamPreview: streamPreview,
    promptOptimizerFailedPartial: failedPartial,
    promptOptimizerRefundStatus: refundStatus,
    optimizePrompt,
    restoreOriginalPrompt,
  }
}
