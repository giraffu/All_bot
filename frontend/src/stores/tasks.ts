import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'
import i18n from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import {
  shouldResumeTaskListening
} from '@/stores/taskResultState'
import {
  pollTaskResult,
  restoreTasksFromStorage,
  serializeTasksForStorage,
  touchTaskActivity
} from './tasksRuntime'

export interface Task {
  id: string
  type: string
  title: string
  progress: number
  status: 'pending' | 'running' | 'success' | 'failed'
  queuePos?: number
  resultUrl?: string
  error?: string
  eventSource?: EventSource
  retryCount?: number
  awaitingResult?: boolean
  updatedAt?: number
}

export const useTasksStore = defineStore('tasks', () => {
  const activeTasks = ref<Task[]>([])
  const detailModalVisible = ref(false)
  const currentDetailRecord = ref<any>(null)
  const authStore = useAuthStore()

  const refreshBalanceAfterCancel = async (previousCredits: number | null) => {
    const retryDelays = [300, 800, 1500]

    for (const delayMs of retryDelays) {
      await new Promise(resolve => setTimeout(resolve, delayMs))
      await authStore.fetchUser()

      const latestCredits = authStore.user?.credits ?? null
      if (previousCredits === null || latestCredits === null || latestCredits !== previousCredits) {
        return
      }
    }
  }

  const openDetailModal = async (taskId: string, fallbackRecord?: any) => {
    const hide = message.loading('正在加载详情...', 0)
    try {
      // 静默拉取最新历史记录（通常第一页即可覆盖最新生成的任务）
      const res = await api.get('/users/history', { params: { page: 1, size: 20 } })
      const record = res.data.items.find((item: any) => item.task_id === taskId)
      
      if (record) {
        currentDetailRecord.value = record
      } else if (fallbackRecord) {
        // 如果没找到，退退一步使用 mock / fallback 对象展示基础信息
        currentDetailRecord.value = {
          ...fallbackRecord,
          is_public: false,
          is_favorited: false,
          allow_contribute: false,
          created_at: new Date().toISOString()
        }
      } else {
        hide()
        message.warning('未找到对应的任务记录')
        return
      }
      
      detailModalVisible.value = true
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

  const startListening = (task: Task) => {
    const token = localStorage.getItem('token')
    const authUrl = `/api/tasks/${task.id}/stream?token=${token}`
    
    const source = new EventSource(authUrl)
    task.eventSource = source
    touchTaskActivity(task)
    
    source.addEventListener('progress', (e: any) => {
      try {
        const payload = JSON.parse(e.data)
        
        if (payload.status === 'pending' && payload.queue_pos != null) {
          task.queuePos = payload.queue_pos
          touchTaskActivity(task)
        }
        
        if (payload.progress !== undefined) {
          task.progress = payload.progress
          task.status = 'running'
          touchTaskActivity(task)
        }
        
        if (payload.status === 'success') {
          task.progress = 99
          task.awaitingResult = true
          touchTaskActivity(task)
          // Delay task.status = 'success' until resultUrl is fetched
          if (task.eventSource) {
            task.eventSource.close()
            task.eventSource = undefined
          }
          pollForResult(task)
        } else if (payload.status === 'failed') {
          task.status = 'failed'
          task.error = payload.error || '未知错误'
          touchTaskActivity(task)
          message.error(`任务 [${task.title}] 生成失败: ${task.error}`)
          if (task.eventSource) {
            task.eventSource.close()
            task.eventSource = undefined
          }
        }
      } catch (err) {
        console.error('Failed to parse SSE data', err)
      }
    })
    
    source.onerror = (err) => {
      console.error(`SSE Error for task ${task.id}`, err)
      if (task.eventSource) {
        task.eventSource.close()
        task.eventSource = undefined
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
        message.warning(`网络不稳定，任务 [${task.title}] 监听已断开，请稍后刷新页面查看结果`)
      }
    }
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
    if (activeTasks.value.length >= 3) {
      message.warning('最多只能同时进行 3 个任务')
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
      if (task.eventSource) {
        task.eventSource.close()
      }
      activeTasks.value.splice(index, 1)
    }
  }

  const clearCompleted = () => {
    const toRemove = activeTasks.value.filter(t => t.status === 'success' || t.status === 'failed')
    toRemove.forEach(t => removeTask(t.id))
  }

  const cancelActiveTask = async (taskId: string) => {
    try {
      const previousCredits = authStore.user?.credits ?? null
      await api.delete(`/tasks/cancel/${taskId}`)
      removeTask(taskId)
      message.success(i18n.global.t('task.cancel_success_refreshing_balance'))
      await refreshBalanceAfterCancel(previousCredits)
      return true
    } catch (e: any) {
      const errorMsg = e.response?.data?.detail || '撤销请求失败'
      message.error(`撤销失败: ${errorMsg}`)
      return false
    }
  }

  return { activeTasks, detailModalVisible, currentDetailRecord, addTask, removeTask, clearCompleted, cancelActiveTask, openDetailModal }
})
