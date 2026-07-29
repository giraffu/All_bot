import { ref } from 'vue'
import { fetchUserHistory } from '../api/api'

const DEFAULT_PAGE_SIZE = 20

export function useDashboardUserHistory() {
  const showModal = ref(false)
  const selectedUser = ref<any | null>(null)
  const userHistory = ref<any[]>([])
  const historyLoading = ref(false)
  const historyPage = ref(1)
  const historyPageSize = ref(DEFAULT_PAGE_SIZE)
  const historyTotal = ref(0)

  const loadHistory = async (user: any, page = 1) => {
    historyLoading.value = true

    try {
      const payload = await fetchUserHistory(user.id, page, historyPageSize.value)
      userHistory.value = payload.items || []
      historyPage.value = payload.page || page
      historyTotal.value = payload.total || 0
    } catch (error) {
      console.error('Error fetching history:', error)
    } finally {
      historyLoading.value = false
    }
  }

  const viewHistory = async (user: any) => {
    selectedUser.value = user
    showModal.value = true
    userHistory.value = []
    historyPage.value = 1
    historyTotal.value = 0
    await loadHistory(user, 1)
  }

  const changeHistoryPage = async (page: number) => {
    if (!selectedUser.value || historyLoading.value) return
    await loadHistory(selectedUser.value, page)
  }

  const closeModal = () => {
    showModal.value = false
    selectedUser.value = null
    userHistory.value = []
    historyPage.value = 1
    historyTotal.value = 0
  }

  return {
    showModal,
    selectedUser,
    userHistory,
    historyLoading,
    historyPage,
    historyPageSize,
    historyTotal,
    viewHistory,
    changeHistoryPage,
    closeModal
  }
}
