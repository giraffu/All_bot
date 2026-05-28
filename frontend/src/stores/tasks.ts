import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'
import { getRecentHistory } from '@/api/gallery'
import i18n from '@/i18n'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import {
  shouldResumeTaskListening
} from '@/stores/taskResultState'
import {
  probeDetachedTaskResult,
  pollTaskResult,
  restoreTasksFromStorage,
  serializeTasksForStorage,
  touchTaskActivity
} from './tasksRuntime'
import {
  countBlockingFloatingTasks,
  getOldestTerminalFloatingTaskIdsForNewTask,
  MAX_FLOATING_TASKS,
} from './taskFloatingSlots'

export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
export type TaskRefundStatus = 'pending' | 'refunded' | 'unconfirmed'

export interface Task {
  id: string
  type: string
  title: string
  progress: number
  status: TaskStatus
  queuePos?: number
  resultUrl?: string
  error?: string
  eventSource?: { close: () => void }
  retryCount?: number
  awaitingResult?: boolean
  updatedAt?: number
  cancelRequested?: boolean
  cancelMessage?: string
  cancelCreditBaseline?: number | null
  refundStatus?: TaskRefundStatus
  refundMessage?: string
}

export const useTasksStore = defineStore('tasks', () => {
  const activeTasks = ref<Task[]>([])
  const detailModalVisible = ref(false)
  const currentDetailRecord = ref<any>(null)
  const authStore = useAuthStore()
  const detachedResultProbeTaskIds = new Set<string>()

  const showDetailRecord = (record: any) => {
    currentDetailRecord.value = record
    detailModalVisible.value = true
  }

  const closeDetailModal = () => {
    detailModalVisible.value = false
  }

  const refreshBalanceAfterCancel = async (previousCredits: number | null) => {
    const retryDelays = [0, 300, 800, 1500]
    let latestCredits = authStore.user?.credits ?? null

    for (const delayMs of retryDelays) {
      if (delayMs > 0) {
        await new Promise(resolve => setTimeout(resolve, delayMs))
      }
      await authStore.fetchUser()

      latestCredits = authStore.user?.credits ?? null
      if (previousCredits === null || latestCredits === null || latestCredits !== previousCredits) {
        return {
          latestCredits,
          refundedCredits: previousCredits !== null && latestCredits !== null
            ? Math.max(latestCredits - previousCredits, 0)
            : null,
          changed: previousCredits !== null && latestCredits !== null && latestCredits !== previousCredits
        }
      }
    }

    return {
      latestCredits,
      refundedCredits: previousCredits !== null && latestCredits !== null
        ? Math.max(latestCredits - previousCredits, 0)
        : null,
      changed: false
    }
  }

  const openDetailModal = async (taskId: string, fallbackRecord?: any) => {
    const hide = message.loading('正在加载详情...', 0)
    try {
      const recentHistory = await getRecentHistory()
      const record = recentHistory.items.find((item: any) => item.task_id === taskId)
      
      if (record) {
        showDetailRecord(record)
      } else if (fallbackRecord) {
        // 如果没找到，退退一步使用 mock / fallback 对象展示基础信息
        showDetailRecord({
          ...fallbackRecord,
          is_public: false,
          is_favorited: false,
          allow_contribute: false,
          created_at: new Date().toISOString()
        })
      } else {
        hide()
        message.warning('未找到对应的任务记录')
        return
      }
    } catch (error) {
      console.error('Failed to fetch detail record:', error)
      message.error('加载详情失败，请稍后重试')
    } finally {
      hide()
    }
  }

  // Forward declaration of startListening
  const pollForResult = async (task: Task, retryCount = 0) => {
    await pollTaskResult(task, activeTasks.value, {
      apiGet: (url) => api.get(url),
      schedule: (callback, delayMs) => {
        setTimeout(callback, delayMs)
      },
      onSuccess: (currentTask) => {
        touchTaskActivity(currentTask)
        message.success(`任务 [${currentTask.title}] 生成完成！`)
      },
      onTimeout: (currentTask) => {
        touchTaskActivity(currentTask)
        message.warning(`获取任务 [${currentTask.title}] 结果超时，请稍后在历史记录中查看`)
      },
      onForbidden: (currentTask) => {
        touchTaskActivity(currentTask)
        message.error(`获取任务 [${currentTask.title}] 结果失败: 任务不存在或无权限`)
      },
      onError: (currentTask) => {
        touchTaskActivity(currentTask)
        message.error(`获取任务 [${currentTask.title}] 结果失败`)
      },
      onRequestError: (err) => {
        console.error('Failed to fetch task result:', err)
      }
    }, retryCount)
  }

  const startDetachedResultProbe = async (task: Task, retryCount = 0) => {
    if (retryCount === 0 && detachedResultProbeTaskIds.has(task.id)) {
      return
    }

    detachedResultProbeTaskIds.add(task.id)
    await probeDetachedTaskResult(task, activeTasks.value, {
      apiGet: (url) => api.get(url),
      schedule: (callback, delayMs) => {
        setTimeout(callback, delayMs)
      },
      onResolved: (currentTask) => {
        detachedResultProbeTaskIds.delete(currentTask.id)
        currentTask.cancelRequested = false
        currentTask.refundStatus = undefined
        currentTask.refundMessage = undefined
        currentTask.queuePos = undefined
        touchTaskActivity(currentTask)
        message.success(`任务 [${currentTask.title}] 生成完成！`)
      },
      onPending: (currentTask) => {
        touchTaskActivity(currentTask)
      },
      onForbidden: (currentTask) => {
        detachedResultProbeTaskIds.delete(currentTask.id)
        touchTaskActivity(currentTask)
        message.error(`获取任务 [${currentTask.title}] 结果失败: 任务不存在或无权限`)
      },
      onExhausted: (currentTask) => {
        detachedResultProbeTaskIds.delete(currentTask.id)
        touchTaskActivity(currentTask)
        message.warning(`任务 [${currentTask.title}] 实时监听已断开，请稍后在历史记录中查看结果`)
      },
      onRequestError: (err) => {
        console.error('Failed to probe detached task result:', err)
      }
    }, retryCount)
  }

  const buildTaskStreamUrl = (taskId: string) => {
    const baseURL = String(api.defaults.baseURL || '/api').replace(/\/$/, '')
    return `${baseURL}/tasks/${taskId}/stream`
  }

  const closeTaskStream = (task: Task) => {
    if (task.eventSource) {
      task.eventSource.close()
      task.eventSource = undefined
    }
  }

  const getBlockingTaskCount = () => countBlockingFloatingTasks(activeTasks.value)

  const makeRoomForNewTask = (notify = false) => {
    const taskIdsToRemove = getOldestTerminalFloatingTaskIdsForNewTask(activeTasks.value)
    if (taskIdsToRemove.length === 0) {
      return activeTasks.value.length < MAX_FLOATING_TASKS
    }

    taskIdsToRemove.forEach(taskId => removeTask(taskId))

    if (notify) {
      message.info('已自动收起最早完成的任务圆球，为新任务腾出位置')
    }

    return activeTasks.value.length < MAX_FLOATING_TASKS
  }

  const finalizeCancelledTask = async (task: Task, cancelMessage?: string) => {
    closeTaskStream(task)
    task.status = 'cancelled'
    task.awaitingResult = false
    task.cancelRequested = false
    task.queuePos = undefined
    task.error = undefined
    task.cancelMessage = cancelMessage || task.cancelMessage || '任务已取消'
    touchTaskActivity(task)

    if (task.refundStatus === 'pending' || task.refundStatus === 'refunded' || task.refundStatus === 'unconfirmed') {
      return
    }

    task.refundStatus = 'pending'
    task.refundMessage = '正在刷新灵石余额...'
    touchTaskActivity(task)

    const balance = await refreshBalanceAfterCancel(task.cancelCreditBaseline ?? authStore.user?.credits ?? null)
    const currentTask = activeTasks.value.find(t => t.id === task.id)
    if (!currentTask) {
      return
    }

    if (balance.refundedCredits && balance.refundedCredits > 0) {
      currentTask.refundStatus = 'refunded'
      currentTask.refundMessage = `已退回 ${balance.refundedCredits} 灵石`
      message.success(`任务 [${currentTask.title}] 已取消，已退回 ${balance.refundedCredits} 灵石`)
    } else {
      currentTask.refundStatus = 'unconfirmed'
      currentTask.refundMessage = '任务已取消，灵石将自动退回，请稍后在余额中查看'
      message.success(`任务 [${currentTask.title}] 已取消`)
    }
    touchTaskActivity(currentTask)
  }

  const handleTaskProgressPayload = (task: Task, payload: Record<string, any>) => {
    if (payload.status === 'pending' && payload.queue_pos != null) {
      task.queuePos = payload.queue_pos
      touchTaskActivity(task)
    }

    if (payload.progress !== undefined) {
      task.progress = payload.progress
      if (task.status !== 'cancelled') {
        task.status = 'running'
      }
      touchTaskActivity(task)
    }

    if (payload.status === 'success') {
      task.progress = 99
      task.cancelRequested = false
      task.refundStatus = undefined
      task.refundMessage = undefined
      task.awaitingResult = true
      touchTaskActivity(task)
      closeTaskStream(task)
      void pollForResult(task)
    } else if (
      payload.status === 'cancelled'
      || (payload.status === 'failed' && task.cancelRequested && String(payload.error || '').includes('取消'))
    ) {
      task.cancelMessage = payload.message || payload.error || '任务已取消'
      void finalizeCancelledTask(task, task.cancelMessage)
    } else if (payload.status === 'failed') {
      task.status = 'failed'
      task.cancelRequested = false
      task.refundStatus = undefined
      task.refundMessage = undefined
      task.error = payload.error || '未知错误'
      touchTaskActivity(task)
      message.error(`任务 [${task.title}] 生成失败: ${task.error}`)
      closeTaskStream(task)
    }
  }

  const startListening = (task: Task) => {
    closeTaskStream(task)

    const token = authStore.token || localStorage.getItem('token')
    if (!token) {
      message.error('登录状态已失效，请重新登录')
      return
    }

    const controller = new AbortController()
    const streamHandle = {
      close: () => controller.abort()
    }
    task.eventSource = streamHandle
    touchTaskActivity(task)

    const consumeStream = async () => {
      try {
        const response = await fetch(buildTaskStreamUrl(task.id), {
          method: 'GET',
          headers: {
            Accept: 'text/event-stream',
            Authorization: `Bearer ${token}`
          },
          signal: controller.signal,
          credentials: 'same-origin'
        })

        if (!response.ok) {
          const error: Error & { status?: number } = new Error(`SSE request failed: ${response.status}`)
          error.status = response.status
          throw error
        }

        if (!response.body) {
          throw new Error('SSE response body is empty')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        const processChunk = (chunk: string) => {
          const normalizedChunk = chunk.trim()
          if (!normalizedChunk) {
            return
          }

          let eventName = 'message'
          const dataLines: string[] = []

          normalizedChunk.split('\n').forEach((line) => {
            if (line.startsWith('event:')) {
              eventName = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trimStart())
            }
          })

          if (eventName !== 'progress') {
            return
          }

          const eventData = dataLines.join('\n')
          if (!eventData) {
            return
          }

          try {
            const payload = JSON.parse(eventData)
            handleTaskProgressPayload(task, payload)
          } catch (parseError) {
            console.warn('Skipping malformed SSE payload', parseError, eventData)
          }
        }

        while (true) {
          const { value, done } = await reader.read()
          if (done) {
            break
          }

          buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r/g, '')
          let boundaryIndex = buffer.indexOf('\n\n')
          while (boundaryIndex !== -1) {
            const chunk = buffer.slice(0, boundaryIndex)
            buffer = buffer.slice(boundaryIndex + 2)
            processChunk(chunk)
            boundaryIndex = buffer.indexOf('\n\n')
          }
        }

        if (buffer) {
          processChunk(buffer)
        }

        if (
          task.eventSource === streamHandle
          && !controller.signal.aborted
          && (task.status === 'pending' || task.status === 'running')
        ) {
          throw new Error('SSE connection closed unexpectedly')
        }
      } catch (err) {
        if (controller.signal.aborted) {
          return
        }

        console.error('Failed to parse SSE data', err)
        closeTaskStream(task)

        if ((err as { status?: number })?.status === 401) {
          authStore.logout()
          if (router.currentRoute.value.path !== '/login') {
            void router.push('/login')
          }
          message.error('登录状态已失效，请重新登录')
          return
        }

        if (!task.retryCount) task.retryCount = 0
        if (task.retryCount < 3) {
          task.retryCount++
          touchTaskActivity(task)
          setTimeout(() => {
            const currentTask = activeTasks.value.find(t => t.id === task.id)
            if (currentTask && (currentTask.status === 'pending' || currentTask.status === 'running')) {
              startListening(currentTask)
            }
          }, 5000 * task.retryCount)
        } else {
          touchTaskActivity(task)
          message.warning(`网络不稳定，任务 [${task.title}] 实时监听已断开，正在后台检查结果`)
          void startDetachedResultProbe(task)
        }
      }
    }

    void consumeStream()
  }

  // Load from localStorage on initialization
  restoreTasksFromStorage(localStorage, activeTasks.value, {
    pollForResult: (task) => {
      void pollForResult(task)
    },
    startListening: (task) => {
      if (shouldResumeTaskListening(task)) {
        startListening(task)
      }
    },
    onParseError: (e) => {
      console.error('Failed to parse stored tasks', e)
    }
  })

  // Persist to localStorage whenever tasks change
  watch(activeTasks, (newTasks) => {
    const serialized = serializeTasksForStorage(newTasks)
    localStorage.setItem('active_tasks', JSON.stringify(serialized))
  }, { deep: true })

  const addTask = (taskId: string, type: string, title: string) => {
    const existingTask = activeTasks.value.find(task => task.id === taskId)
    if (existingTask) {
      existingTask.type = type
      existingTask.title = title
      existingTask.status = existingTask.status === 'failed' || existingTask.status === 'cancelled'
        ? 'pending'
        : existingTask.status
      existingTask.cancelRequested = false
      existingTask.cancelMessage = undefined
      existingTask.refundStatus = undefined
      existingTask.refundMessage = undefined
      touchTaskActivity(existingTask)
      if (!existingTask.awaitingResult && (existingTask.status === 'pending' || existingTask.status === 'running')) {
        startListening(existingTask)
      }
      return true
    }

    if (activeTasks.value.length >= MAX_FLOATING_TASKS && !makeRoomForNewTask(true)) {
      message.warning(`最多只能同时进行 ${MAX_FLOATING_TASKS} 个任务`)
      return false
    }
    
    const newTask: Task = {
      id: taskId,
      type,
      title,
      progress: 0,
      status: 'pending',
      updatedAt: Date.now()
    }
    
    const newLength = activeTasks.value.push(newTask)
    const addedTask = activeTasks.value[newLength - 1]
    startListening(addedTask)
    return true
  }

  const removeTask = (taskId: string) => {
    const index = activeTasks.value.findIndex(t => t.id === taskId)
    if (index !== -1) {
      const task = activeTasks.value[index]
      closeTaskStream(task)
      activeTasks.value.splice(index, 1)
    }
  }

  const clearCompleted = () => {
    const toRemove = activeTasks.value.filter(
      t => t.status === 'success' || t.status === 'failed' || t.status === 'cancelled'
    )
    toRemove.forEach(t => removeTask(t.id))
  }

  const cancelActiveTask = async (taskId: string) => {
    try {
      const previousCredits = authStore.user?.credits ?? null
      const response = await api.delete(`/tasks/cancel/${taskId}`)
      const task = activeTasks.value.find(item => item.id === taskId)
      if (task) {
        task.cancelCreditBaseline = previousCredits
        task.cancelMessage = response.data?.message || i18n.global.t('task.cancel_success_refreshing_balance')
        task.error = undefined
        task.queuePos = undefined

        if (response.data?.cancel_state === 'cancelled') {
          await finalizeCancelledTask(task, task.cancelMessage)
        } else {
          task.cancelRequested = true
          task.refundStatus = 'pending'
          task.refundMessage = '等待执行端确认后自动退回灵石'
          touchTaskActivity(task)
          message.success(task.cancelMessage)
        }
      } else {
        message.success(response.data?.message || i18n.global.t('task.cancel_success_refreshing_balance'))
        await refreshBalanceAfterCancel(previousCredits)
      }
      return true
    } catch (e: any) {
      const errorMsg = e.response?.data?.detail || '撤销请求失败'
      message.error(`撤销失败: ${errorMsg}`)
      return false
    }
  }

  return {
    activeTasks,
    detailModalVisible,
    currentDetailRecord,
    getBlockingTaskCount,
    addTask,
    removeTask,
    clearCompleted,
    cancelActiveTask,
    openDetailModal,
    showDetailRecord,
    closeDetailModal,
  }
})
