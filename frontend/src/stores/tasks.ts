import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'

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
}

export const useTasksStore = defineStore('tasks', () => {
  const activeTasks = ref<Task[]>([])
  const detailModalVisible = ref(false)
  const currentDetailRecord = ref<any>(null)

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
  const startListening = (task: Task) => {
    const token = localStorage.getItem('token')
    const authUrl = `/api/tasks/${task.id}/stream?token=${token}`
    
    const source = new EventSource(authUrl)
    task.eventSource = source
    
    source.addEventListener('progress', (e: any) => {
      try {
        const payload = JSON.parse(e.data)
        
        if (payload.status === 'pending' && payload.queue_pos != null) {
          task.queuePos = payload.queue_pos
        }
        
        if (payload.progress !== undefined) {
          task.progress = payload.progress
          task.status = 'running'
        }
        
        if (payload.status === 'success') {
          task.progress = 100
          task.status = 'success'
          task.resultUrl = payload.result
          message.success(`任务 [${task.title}] 生成完成！`)
          if (task.eventSource) {
            task.eventSource.close()
            task.eventSource = undefined
          }
        } else if (payload.status === 'failed') {
          task.status = 'failed'
          task.error = payload.error || '未知错误'
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
      // source.close() 
    }
  }

  // Load from localStorage on initialization
  const storedTasks = localStorage.getItem('active_tasks')
  if (storedTasks) {
    try {
      const parsed = JSON.parse(storedTasks)
      activeTasks.value = parsed
      // Re-establish connections for unfinished tasks
      activeTasks.value.forEach(task => {
        if (task.status === 'pending' || task.status === 'running') {
          startListening(task)
        }
      })
    } catch (e) {
      console.error('Failed to parse stored tasks', e)
    }
  }

  // Persist to localStorage whenever tasks change
  watch(activeTasks, (newTasks) => {
    const serialized = newTasks.map(t => ({
      ...t,
      eventSource: undefined // Do not serialize EventSource object
    }))
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
      status: 'pending'
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
      await api.delete(`/tasks/cancel/${taskId}`)
      removeTask(taskId)
      message.success('✅ 任务已撤销，灵石已退回')
      // Delay before returning to allow backend refund propagation
      await new Promise(resolve => setTimeout(resolve, 1500))
      return true
    } catch (e: any) {
      const errorMsg = e.response?.data?.detail || '撤销请求失败'
      message.error(`撤销失败: ${errorMsg}`)
      return false
    }
  }

  return { activeTasks, detailModalVisible, currentDetailRecord, addTask, removeTask, clearCompleted, cancelActiveTask, openDetailModal }
})
