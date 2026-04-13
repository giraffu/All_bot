import { ref, computed, watch, onUnmounted } from 'vue'
import { useTasksStore } from '@/stores/tasks'

export function useTaskResult() {
  const tasksStore = useTasksStore()
  const submittedTaskId = ref<string | null>(null)

  const currentTask = computed(() => {
    if (!submittedTaskId.value) return null
    return tasksStore.activeTasks.find(t => t.id === submittedTaskId.value) || null
  })

  const setSubmittedTaskId = (id: string | null) => {
    submittedTaskId.value = id
  }

  const isVideoUrl = (url: string) => {
    if (!url) return false
    const lowerUrl = url.toLowerCase()
    return lowerUrl.endsWith('.mp4') || lowerUrl.endsWith('.mov') || lowerUrl.includes('.mp4?') || lowerUrl.includes('.mov?')
  }

  const isImageUrl = (url: string) => {
    if (!url) return false
    const lowerUrl = url.toLowerCase()
    return lowerUrl.endsWith('.png') || lowerUrl.endsWith('.jpg') || lowerUrl.endsWith('.jpeg') || lowerUrl.endsWith('.webp') || lowerUrl.includes('.png?') || lowerUrl.includes('.jpg?') || lowerUrl.includes('.jpeg?') || lowerUrl.includes('.webp?')
  }

  const downloadResult = (url: string, filename: string = 'result') => {
    if (!url) return
    const a = document.createElement('a')
    a.href = url
    // Try to extract extension from URL
    let ext = ''
    if (isVideoUrl(url)) ext = '.mp4'
    else if (isImageUrl(url)) ext = '.png'
    
    a.download = `${filename}${ext}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  return {
    submittedTaskId,
    currentTask,
    setSubmittedTaskId,
    isVideoUrl,
    isImageUrl,
    downloadResult
  }
}
