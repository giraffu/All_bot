import { ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  fetchTaskImage,
  fetchTaskStatus,
  fetchTaskVideo
} from '../api/api'

export function useDashboardTaskSearch() {
  const searchQuery = ref('')
  const searchResult = ref<any | null>(null)
  const searchModalVisible = ref(false)
  const searchLoading = ref(false)

  const handleSearch = async () => {
    if (!searchQuery.value.trim()) {
      return
    }

    searchLoading.value = true
    try {
      const data = await fetchTaskStatus(searchQuery.value.trim())
      if (data) {
        searchResult.value = { ...data, id: searchQuery.value.trim() }
        searchModalVisible.value = true
      }
    } catch (error) {
      console.error('Search error:', error)
      message.error('未找到任务或查询失败')
    } finally {
      searchLoading.value = false
    }
  }

  const closeSearchModal = () => {
    searchModalVisible.value = false
    searchResult.value = null
  }

  const isImage = (filename: string) => /\.(png|jpg|jpeg|webp)$/i.test(filename || '')
  const isVideo = (filename: string) => /\.(mp4|mov|webm)$/i.test(filename || '')
  const getTaskImageUrl = (id: string) => fetchTaskImage(id)
  const getTaskVideoUrl = (id: string) => fetchTaskVideo(id)

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return 'orange'
      case 'running':
        return 'blue'
      case 'done':
        return 'success'
      case 'error':
        return 'error'
      default:
        return 'default'
    }
  }

  return {
    searchQuery,
    searchResult,
    searchModalVisible,
    searchLoading,
    handleSearch,
    closeSearchModal,
    isImage,
    isVideo,
    getTaskImageUrl,
    getTaskVideoUrl,
    getStatusColor
  }
}
