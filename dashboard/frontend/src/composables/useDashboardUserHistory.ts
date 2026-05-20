import { ref } from 'vue'
import { fetchUserHistory } from '../api/api'

export function useDashboardUserHistory() {
  const showModal = ref(false)
  const selectedUser = ref<any | null>(null)
  const userHistory = ref<any[]>([])
  const historyLoading = ref(false)

  const viewHistory = async (user: any) => {
    selectedUser.value = user
    showModal.value = true
    historyLoading.value = true
    userHistory.value = []

    try {
      userHistory.value = await fetchUserHistory(user.id)
    } catch (error) {
      console.error('Error fetching history:', error)
    } finally {
      historyLoading.value = false
    }
  }

  const closeModal = () => {
    showModal.value = false
    selectedUser.value = null
    userHistory.value = []
  }

  return {
    showModal,
    selectedUser,
    userHistory,
    historyLoading,
    viewHistory,
    closeModal
  }
}
