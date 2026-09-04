import { onMounted, ref, watch } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import api from '@/api'
import { getRecentHistory } from '@/api/gallery'
import type { HistoryItem } from '@/types/gallery'

interface TasksStoreLike {
  detailModalVisible: boolean
  currentDetailRecord: any
  showDetailRecord: (record: any) => void
  openDetailModal: (taskId: string) => Promise<void>
  closeDetailModal: () => void
}

interface UseHistoryRecordsOptions {
  route: RouteLocationNormalizedLoaded
  router: Router
  tasksStore: TasksStoreLike
}

export function useHistoryRecords(options: UseHistoryRecordsOptions) {
  const data = ref<HistoryItem[]>([])
  const loading = ref(false)
  const flashbackLimit = ref(8)

  const pagination = ref({
    current: 1,
    pageSize: 8,
    total: 0,
    hideOnSinglePage: true
  })

  const openDetail = (record: any) => {
    options.tasksStore.showDetailRecord(record)
  }

  const clearTaskIdQuery = () => {
    void options.router.replace({ query: {} })
  }

  const applyRecentHistoryPayload = (recentHistory: Awaited<ReturnType<typeof getRecentHistory>>) => {
    data.value = recentHistory.items
    pagination.value.total = recentHistory.total
    pagination.value.current = recentHistory.page
    pagination.value.pageSize = recentHistory.size
    flashbackLimit.value = recentHistory.size
  }

  const tryOpenTaskFromQuery = async (page: number) => {
    if (!options.route.query.task_id) {
      return
    }

    const targetId = options.route.query.task_id as string
    const targetRecord = data.value.find(item => item.task_id === targetId)
    if (targetRecord) {
      openDetail(targetRecord)
    } else if (page === 1) {
      await options.tasksStore.openDetailModal(targetId)
    }

    clearTaskIdQuery()
  }

  const fetchHistory = async (page = 1) => {
    loading.value = true
    try {
      const recentHistory = await getRecentHistory()
      applyRecentHistoryPayload(recentHistory)
      await tryOpenTaskFromQuery(page)
    } catch (error) {
      console.error('Failed to fetch history:', error)
    } finally {
      loading.value = false
    }
  }

  const handleDelete = async (record: any, event?: Event) => {
    if (event) event.stopPropagation()

    Modal.confirm({
      title: '确认删除',
      content: '确认删除该记录吗？（若已发布至广场也将同步下架）',
      okText: '确认',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.delete(`/users/history/${record.id}`)
          message.success('删除成功')
          data.value = data.value.filter(item => item.id !== record.id)
          if (
            options.tasksStore.detailModalVisible
            && options.tasksStore.currentDetailRecord?.id === record.id
          ) {
            options.tasksStore.closeDetailModal()
          }
        } catch (error: any) {
          console.error(error)
          message.error(error.response?.data?.detail || '删除失败，请稍后再试')
        }
      }
    })
  }

  onMounted(() => {
    void fetchHistory()
  })

  watch(() => options.route.query.task_id, async (newTaskId) => {
    if (!newTaskId) {
      return
    }

    const targetRecord = data.value.find(item => item.task_id === newTaskId)
    if (targetRecord) {
      openDetail(targetRecord)
      clearTaskIdQuery()
      return
    }

    try {
      const recentHistory = await getRecentHistory()
      applyRecentHistoryPayload(recentHistory)
      const refreshedRecord = recentHistory.items.find(item => item.task_id === newTaskId)
      if (refreshedRecord) {
        openDetail(refreshedRecord)
      } else {
        await options.tasksStore.openDetailModal(newTaskId as string)
      }
    } catch (error) {
      console.error('Failed to refresh history for task query:', error)
      await options.tasksStore.openDetailModal(newTaskId as string)
    }
    clearTaskIdQuery()
  })

  return {
    data,
    flashbackLimit,
    loading,
    pagination,
    openDetail,
    fetchHistory,
    handleDelete,
  }
}
