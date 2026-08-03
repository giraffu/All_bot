import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import api from '@/api'
import type { UnifiedLabModeId } from '@/features/generation/labModeConfig'
import type { UploadedReference } from './types'

export type PromptOptimizerTemplate = {
  id: string
  version: number
  label: string
  description: string
  is_default: boolean
}

type PendingOptimizerTask = {
  taskId: string
  clientRequestId: string
  originalPrompt: string
  templateRef: { id: string; version: number }
  contextFingerprint: string
}

const STORAGE_KEY = 'allbot.prompt-optimizer.pending.v1'

export function usePromptOptimizer(options: {
  currentModeId: Ref<UnifiedLabModeId>
  prompt: Ref<string>
  duration: Ref<string>
  uploadedReferences: Ref<UploadedReference[]>
}) {
  const templates = ref<PromptOptimizerTemplate[]>([])
  const selectedTemplateRef = ref('')
  const isOptimizing = ref(false)
  const originalPrompt = ref<string | null>(null)
  let stopped = false

  const isAvailable = computed(() => options.currentModeId.value === 'ltx_video_v2')
  const mediaFingerprint = () => JSON.stringify({
    duration: Number(options.duration.value),
    media: options.uploadedReferences.value.map(item => item.key),
  })
  const canOptimize = computed(() => (
    isAvailable.value
    && !isOptimizing.value
    && options.prompt.value.trim().length > 0
    && options.uploadedReferences.value.length >= 1
    && templates.value.length > 0
  ))
  const canRestore = computed(() => originalPrompt.value !== null)

  const loadCapabilities = async () => {
    if (!isAvailable.value) return
    const response = await api.get('/prompt-optimizations/capabilities', {
      params: { target_task_type: 'ltx_video_v2' },
    })
    templates.value = response.data.templates ?? []
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

  const pollResult = async (pending: PendingOptimizerTask) => {
    while (!stopped) {
      const response = await api.get(`/tasks/${pending.taskId}/result`)
      if (response.data.status === 'success') {
        if (
          mediaFingerprint() === pending.contextFingerprint
          && options.prompt.value === pending.originalPrompt
        ) {
          originalPrompt.value = pending.originalPrompt
          options.prompt.value = String(response.data.result_text ?? '')
        } else {
          message.info('提示词优化已完成，但当前输入已变化，未自动替换。')
        }
        sessionStorage.removeItem(STORAGE_KEY)
        isOptimizing.value = false
        return
      }
      if (['failed', 'error', 'cancelled'].includes(response.data.status)) {
        throw new Error(response.data.message || response.data.error || 'optimizer failed')
      }
      await new Promise(resolve => window.setTimeout(resolve, 1200))
    }
  }

  const optimizePrompt = async () => {
    if (!canOptimize.value) return
    const original = options.prompt.value
    const templateRef = parseSelectedTemplate()
    const clientRequestId = crypto.randomUUID()
    const pendingBase = {
      clientRequestId,
      originalPrompt: original,
      templateRef,
      contextFingerprint: mediaFingerprint(),
    }
    isOptimizing.value = true
    try {
      const response = await api.post('/prompt-optimizations/tasks', {
        client_request_id: clientRequestId,
        target_task_type: 'ltx_video_v2',
        template: templateRef,
        prompt: original,
        context: { duration_seconds: Number(options.duration.value) },
        media: options.uploadedReferences.value.map((item, index) => ({
          role: index === 0 ? 'start_image' : 'end_image',
          object_key: item.key,
        })),
      })
      const pending: PendingOptimizerTask = {
        ...pendingBase,
        taskId: response.data.task_id,
      }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(pending))
      await pollResult(pending)
    } catch (error) {
      isOptimizing.value = false
      message.error('提示词优化失败，已自动退款或不会重复扣费。')
      throw error
    }
  }

  const restoreOriginalPrompt = () => {
    if (originalPrompt.value === null) return
    options.prompt.value = originalPrompt.value
    originalPrompt.value = null
  }

  const resumePending = async () => {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw || !isAvailable.value || isOptimizing.value) return
    try {
      const pending = JSON.parse(raw) as PendingOptimizerTask
      isOptimizing.value = true
      selectedTemplateRef.value = `${pending.templateRef.id}@${pending.templateRef.version}`
      await pollResult(pending)
    } catch {
      sessionStorage.removeItem(STORAGE_KEY)
      isOptimizing.value = false
    }
  }

  watch(
    isAvailable,
    async available => {
      if (!available) return
      try {
        await loadCapabilities()
        await resumePending()
      } catch {
        templates.value = []
      }
    },
    { immediate: true },
  )

  onBeforeUnmount(() => { stopped = true })

  return {
    isPromptOptimizerAvailable: isAvailable,
    canOptimizePrompt: canOptimize,
    canRestoreOriginalPrompt: canRestore,
    isOptimizingPrompt: isOptimizing,
    optimizePrompt,
    restoreOriginalPrompt,
  }
}
