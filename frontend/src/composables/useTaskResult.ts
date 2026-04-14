import { ref, computed, watch } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import type { Task } from '@/stores/tasks'

export function useTaskResult() {
  const tasksStore = useTasksStore()
  const submittedTaskId = ref<string | null>(null)

  // Use a local ref to hold the current task state so it survives being removed from the store
  const localTask = ref<Task | null>(null)

  // Watch for changes in the active tasks to update our local copy
  watch(
    () => {
      if (!submittedTaskId.value) return null
      return tasksStore.activeTasks.find(t => t.id === submittedTaskId.value) || null
    },
    (newTask) => {
      if (newTask) {
        // Shallow copy to preserve state even if the original is removed
        localTask.value = { ...newTask }
      }
      // If newTask is null, it means it was removed from the store.
      // We DO NOT set localTask to null here, so the UI keeps showing the last state.
    },
    { immediate: true, deep: true }
  )

  const currentTask = computed(() => localTask.value)

  const setSubmittedTaskId = (id: string | null) => {
    submittedTaskId.value = id
    if (id === null) {
      localTask.value = null
    }
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
