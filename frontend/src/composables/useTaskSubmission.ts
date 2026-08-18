import { ref } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'
import i18n from '@/i18n'
import { useTasksStore } from '@/stores/tasks'
import { useAuthStore } from '@/stores/auth'

export interface TaskSubmissionPayload {
  task_type: string
  [key: string]: unknown
}

interface TaskSubmissionResponse {
  task_id: string
  balance_remaining?: number
  submission_state?: 'accepted' | 'reconciling'
}

export function useTaskSubmission() {
  const isSubmitting = ref(false)
  const tasksStore = useTasksStore()
  const authStore = useAuthStore()

  const submitTask = async (
    payload: TaskSubmissionPayload,
    taskTitle: string,
  ): Promise<string | null> => {
    isSubmitting.value = true
    try {
      const response = await api.post<TaskSubmissionResponse>('/tasks/generate', payload)
      const { task_id: taskId, balance_remaining: balanceRemaining } = response.data
      if (balanceRemaining !== undefined) {
        authStore.updateBalance(balanceRemaining)
      }
      message.success(i18n.global.t('task.submission_queued'))
      tasksStore.addTask(taskId, payload.task_type, taskTitle)
      return taskId
    } catch (error: unknown) {
      console.error('Task submission error:', error)
      return null
    } finally {
      isSubmitting.value = false
    }
  }

  return { isSubmitting, submitTask }
}
