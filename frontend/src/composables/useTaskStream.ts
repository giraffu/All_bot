import { ref } from 'vue'
import api from '@/api'
import { message } from 'ant-design-vue'
import { useTasksStore } from '@/stores/tasks'
import { useAuthStore } from '@/stores/auth'
import { MAX_FLOATING_TASKS } from '@/stores/taskFloatingSlots'

export function useTaskStream() {
  const isSubmitting = ref(false)
  const tasksStore = useTasksStore()
  const authStore = useAuthStore()

  const submitTask = async (payload: any, taskTitle: string): Promise<string | null> => {
    if (tasksStore.getBlockingTaskCount() >= MAX_FLOATING_TASKS) {
      message.warning(`您当前已有 ${MAX_FLOATING_TASKS} 个任务正在进行中，请等待完成后再提交新任务。`)
      return null
    }

    isSubmitting.value = true
    
    try {
      const response = await api.post('/tasks/generate', payload)
      const { task_id, balance_remaining } = response.data
      
      if (balance_remaining !== undefined) {
        authStore.updateBalance(balance_remaining)
      }
      
      message.success('任务已提交，开始排队生成...')
      tasksStore.addTask(task_id, payload.task_type, taskTitle)
      return task_id
      
    } catch (error: any) {
      // Error message is handled by axios interceptor
      console.error('Task submission error:', error)
      return null
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    isSubmitting,
    submitTask
  }
}
