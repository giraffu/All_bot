import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'
import { getRecentHistory } from '@/api/gallery'
import i18n from '@/i18n'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import {
  shouldResumeTaskStatusPolling
} from '@/stores/taskResultState'
import {
  probeDetachedTaskResult,
  pollTaskStatus,
  pollTaskResult,
  reconcileTasksAfterForeground,
  restoreTasksFromStorage,
  serializeTasksForStorage,
  touchTaskActivity
} from './tasksRuntime'
import {
  createPendingTask,
  clearCompletedTaskSessions,
  removeTaskSession,
  resetExistingTaskSession,
} from './taskSessionState'
import {
  closeTaskStream,
} from './taskStreamTransport'
import type { Task } from './taskStoreTypes'
import type { TaskRecord } from '@/types/gallery'
import {
  countBlockingFloatingTasks,
  getOldestTerminalFloatingTaskIdsForNewTask,
  MAX_FLOATING_TASKS,
} from './taskFloatingSlots'

export type { Task } from './taskStoreTypes'

export const useTasksStore = defineStore('tasks', () => {
  const activeTasks = ref<Task[]>([])
  const detailModalVisible = ref(false)
  const currentDetailRecord = ref<TaskRecord | null>(null)
  const authStore = useAuthStore()
  const detachedResultProbeTaskIds = new Set<string>()
  const resultPollingTaskIds = new Set<string>()
  const statusPollingTaskIds = new Set<string>()

  const dismissActiveTaskForDetailRecord = (record: TaskRecord) => {
    const taskId = record.task_id
    const task = activeTasks.value.find(item => item.id === taskId)
    if (!task) {
      return
    }

    closeTaskStream(task)
    removeTaskSession(activeTasks.value, taskId, closeTaskStream)
    detachedResultProbeTaskIds.delete(taskId)
    resultPollingTaskIds.delete(taskId)
    statusPollingTaskIds.delete(taskId)
  }

  const showDetailRecord = (record: TaskRecord) => {
    dismissActiveTaskForDetailRecord(record)
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

  const openDetailModal = async (
    taskId: string,
    fallbackRecord?: Partial<TaskRecord> & Record<string, unknown>,
  ) => {
    const hide = message.loading('正在加载详情...', 0)
    try {
      const recentHistory = await getRecentHistory()
      const record = recentHistory.items.find((item) => item.task_id === taskId)
      
      if (record?.task_id && record.type) {
        showDetailRecord(record as TaskRecord)
      } else if (fallbackRecord) {
        // 如果没找到，退退一步使用 mock / fallback 对象展示基础信息
        showDetailRecord({
          ...fallbackRecord,
          is_public: false,
          is_favorited: false,
          allow_contribute: false,
          created_at: new Date().toISOString()
        } as TaskRecord)
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

  // Result polling starts after the coarse status endpoint reports success.
  const pollForResult = async (task: Task, retryCount = 0) => {
    if (retryCount === 0 && resultPollingTaskIds.has(task.id)) {
      return
    }
    resultPollingTaskIds.add(task.id)
    await pollTaskResult(task, activeTasks.value, {
      apiGet: (url) => api.get(url),
      schedule: (callback, delayMs) => {
        setTimeout(callback, delayMs)
      },
      onSuccess: (currentTask) => {
        resultPollingTaskIds.delete(currentTask.id)
        touchTaskActivity(currentTask)
        message.success(`任务 [${currentTask.title}] 生成完成！`)
      },
      onTimeout: (currentTask) => {
        resultPollingTaskIds.delete(currentTask.id)
        touchTaskActivity(currentTask)
        message.warning(`获取任务 [${currentTask.title}] 结果超时，请稍后在历史记录中查看`)
      },
      onForbidden: (currentTask) => {
        resultPollingTaskIds.delete(currentTask.id)
        touchTaskActivity(currentTask)
        message.error(`获取任务 [${currentTask.title}] 结果失败: 任务不存在或无权限`)
      },
      onError: (currentTask) => {
        resultPollingTaskIds.delete(currentTask.id)
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
    statusPollingTaskIds.delete(task.id)
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

  const startStatusPolling = (task: Task) => {
    closeTaskStream(task)
    if (statusPollingTaskIds.has(task.id)) {
      return
    }
    statusPollingTaskIds.add(task.id)

    void pollTaskStatus(task, activeTasks.value, {
      apiGet: (url) => api.get(url),
      schedule: (callback, delayMs) => {
        setTimeout(callback, delayMs)
      },
      pollForResult: (pollTask) => {
        statusPollingTaskIds.delete(pollTask.id)
        void pollForResult(pollTask)
      },
      finalizeCancelledTask: (cancelledTask, cancelMessage) => {
        statusPollingTaskIds.delete(cancelledTask.id)
        void finalizeCancelledTask(cancelledTask, cancelMessage)
      },
      notifyTaskFailure: (failedTask) => {
        statusPollingTaskIds.delete(failedTask.id)
        message.error(`任务 [${failedTask.title}] 生成失败: ${failedTask.error}`)
      },
      handleUnauthorized: () => {
        statusPollingTaskIds.delete(task.id)
        authStore.logout()
        if (router.currentRoute.value.path !== '/login') {
          void router.push('/login')
        }
        message.error('登录状态已失效，请重新登录')
      },
      onRequestError: (err) => {
        console.error('Failed to poll task status:', err)
      },
    })
  }

  // Load from localStorage on initialization
  restoreTasksFromStorage(localStorage, activeTasks.value, {
    pollForResult: (task) => {
      void pollForResult(task)
    },
    startStatusPolling: (task) => {
      if (shouldResumeTaskStatusPolling(task)) {
        startStatusPolling(task)
      }
    },
    onParseError: (e) => {
      console.error('Failed to parse stored tasks', e)
    }
  })

  const reconcileForegroundTasks = () => {
    reconcileTasksAfterForeground(activeTasks.value, {
      pollForResult: (task) => {
        void pollForResult(task)
      },
      startStatusPolling,
    })
  }

  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    window.addEventListener('pageshow', reconcileForegroundTasks)
    window.addEventListener('online', reconcileForegroundTasks)
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        reconcileForegroundTasks()
      }
    })
  }

  // Persist to localStorage whenever tasks change
  watch(activeTasks, (newTasks) => {
    const serialized = serializeTasksForStorage(newTasks)
    localStorage.setItem('active_tasks', JSON.stringify(serialized))
  }, { deep: true })

  const addTask = (taskId: string, type: string, title: string) => {
    const existingTask = activeTasks.value.find(task => task.id === taskId)
    if (existingTask) {
      resetExistingTaskSession(existingTask, type, title)
      touchTaskActivity(existingTask)
      if (!existingTask.awaitingResult && (existingTask.status === 'pending' || existingTask.status === 'running')) {
        startStatusPolling(existingTask)
      }
      return true
    }

    if (activeTasks.value.length >= MAX_FLOATING_TASKS && !makeRoomForNewTask(true)) {
      message.warning(`最多只能同时进行 ${MAX_FLOATING_TASKS} 个任务`)
      return false
    }

    const newTask = createPendingTask(taskId, type, title)
    const newLength = activeTasks.value.push(newTask)
    const addedTask = activeTasks.value[newLength - 1]
    startStatusPolling(addedTask)
    return true
  }

  const removeTask = (taskId: string) => {
    statusPollingTaskIds.delete(taskId)
    detachedResultProbeTaskIds.delete(taskId)
    resultPollingTaskIds.delete(taskId)
    removeTaskSession(activeTasks.value, taskId, closeTaskStream)
  }

  const clearCompleted = () => {
    clearCompletedTaskSessions(activeTasks.value, removeTask)
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
