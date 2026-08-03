import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import api from '@/api'
import { getRuntimeConfig } from '@/config/runtime'
import type { UnifiedLabModeId } from '@/features/generation/labModeConfig'
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

type PendingOptimizerTask = {
  taskId: string
  clientRequestId: string
  originalPrompt: string
  templateRef: { id: string; version: number }
  contextFingerprint: string
  streamAttemptId?: string
  lastSequence?: number
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
  const streamPreview = ref('')
  const failedPartial = ref('')
  const refundStatus = ref<'pending' | 'refunded' | ''>('')
  const originalPrompt = ref<string | null>(null)
  const textStreamCapability = ref<PromptTextStreamCapability | null>(null)
  let streamController: AbortController | null = null
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
    textStreamCapability.value = response.data.text_stream ?? null
    const defaultTemplate = templates.value.find(item => item.is_default) ?? templates.value[0]
    if (!templates.value.some(item => `${item.id}@${item.version}` === selectedTemplateRef.value)) {
      selectedTemplateRef.value = defaultTemplate
        ? `${defaultTemplate.id}@${defaultTemplate.version}`
        : ''
    }
  }

  const persistPending = (pending: PendingOptimizerTask) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(pending))
  }

  const primaryStreamField = () => textStreamCapability.value?.fields[0] ?? ''

  const processStreamEvent = (
    eventName: string,
    eventData: string,
    pending: PendingOptimizerTask,
  ) => {
    if (!['text_snapshot', 'text_delta'].includes(eventName) || !eventData) return
    const payload = JSON.parse(eventData) as {
      attempt_id?: string
      sequence?: number
      field?: string
      delta?: string
      fields?: Record<string, string>
    }
    const attemptId = String(payload.attempt_id ?? '')
    const sequence = Number(payload.sequence ?? 0)
    if (!attemptId || !Number.isInteger(sequence)) return
    if (eventName === 'text_snapshot') {
      pending.streamAttemptId = attemptId
      pending.lastSequence = sequence
      streamPreview.value = String(payload.fields?.[primaryStreamField()] ?? '')
      persistPending(pending)
      return
    }
    if (pending.streamAttemptId && pending.streamAttemptId !== attemptId) return
    const lastSequence = pending.lastSequence ?? 0
    if (sequence <= lastSequence) return
    if (sequence !== lastSequence + 1 || payload.field !== primaryStreamField()) {
      streamController?.abort()
      return
    }
    pending.streamAttemptId = attemptId
    pending.lastSequence = sequence
    streamPreview.value += String(payload.delta ?? '')
    persistPending(pending)
  }

  const streamTask = async (pending: PendingOptimizerTask) => {
    if (!textStreamCapability.value?.enabled) return
    const delays = [1000, 2000, 4000, 8000, 10000]
    let retry = 0
    while (!stopped && isOptimizing.value) {
      const controller = new AbortController()
      streamController = controller
      try {
        const apiBase = String(getRuntimeConfig('api_base_url', '/api')).replace(/\/$/, '')
        const response = await fetch(`${apiBase}/tasks/${pending.taskId}/stream`, {
          headers: {
            Accept: 'text/event-stream',
            Authorization: `Bearer ${localStorage.getItem('token') ?? ''}`,
            ...(pending.streamAttemptId && pending.lastSequence
              ? { 'Last-Event-ID': `${pending.streamAttemptId}:${pending.lastSequence}` }
              : {}),
          },
          signal: controller.signal,
          credentials: 'same-origin',
        })
        if (!response.ok || !response.body) throw new Error(`stream_http_${response.status}`)
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        retry = 0
        while (isOptimizing.value) {
          const { value, done } = await reader.read()
          if (done) break
          buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r/g, '')
          let boundary = buffer.indexOf('\n\n')
          while (boundary >= 0) {
            const block = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + 2)
            let eventName = 'message'
            const data: string[] = []
            block.split('\n').forEach(line => {
              if (line.startsWith('event:')) eventName = line.slice(6).trim()
              if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
            })
            processStreamEvent(eventName, data.join('\n'), pending)
            boundary = buffer.indexOf('\n\n')
          }
        }
      } catch (error) {
        if (controller.signal.aborted && !isOptimizing.value) return
      }
      if (!isOptimizing.value || stopped) return
      await new Promise(resolve => window.setTimeout(resolve, delays[Math.min(retry, delays.length - 1)]))
      retry += 1
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
        streamPreview.value = ''
        isOptimizing.value = false
        streamController?.abort()
        return
      }
      if (['failed', 'error', 'cancelled'].includes(response.data.status)) {
        failedPartial.value = String(response.data.partial_result_text || streamPreview.value || '')
        refundStatus.value = response.data.refund_status === 'refunded' ? 'refunded' : 'pending'
        throw new Error(response.data.message || response.data.error || 'optimizer failed')
      }
      await new Promise(resolve => window.setTimeout(resolve, 1200))
    }
  }

  const optimizePrompt = async () => {
    if (!canOptimize.value) return
    const original = options.prompt.value
    failedPartial.value = ''
    refundStatus.value = ''
    streamPreview.value = ''
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
      persistPending(pending)
      void streamTask(pending)
      await pollResult(pending)
    } catch (error) {
      isOptimizing.value = false
      streamController?.abort()
      const refundConfirmed = String(refundStatus.value) === 'refunded'
      message.error(refundConfirmed ? '提示词优化失败，1 灵石已退回。' : '提示词优化失败，退款处理中。')
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
      void streamTask(pending)
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

  onBeforeUnmount(() => {
    stopped = true
    streamController?.abort()
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
