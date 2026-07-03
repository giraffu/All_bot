import { computed, ref } from 'vue'
import { getCurrentUserCreditLedger } from '@/api/creditLedger'
import type { CreditLedgerItem } from '@/types/creditLedger'

export function useCreditLedger(pageSize = 20) {
  const items = ref<CreditLedgerItem[]>([])
  const page = ref(1)
  const total = ref(0)
  const totalPages = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref<unknown | null>(null)

  const hasMore = computed(() => page.value < totalPages.value)

  const reset = () => {
    items.value = []
    page.value = 1
    total.value = 0
    totalPages.value = 0
    error.value = null
  }

  const loadLedger = async (options: { reset?: boolean } = {}) => {
    const shouldReset = options.reset ?? true
    const nextPage = shouldReset ? 1 : page.value + 1
    error.value = null

    if (shouldReset) {
      loading.value = true
    } else {
      loadingMore.value = true
    }

    try {
      const response = await getCurrentUserCreditLedger({
        page: nextPage,
        page_size: pageSize,
      })
      items.value = shouldReset
        ? response.items
        : [...items.value, ...response.items]
      page.value = response.page
      total.value = response.total
      totalPages.value = response.total_pages
    } catch (caughtError) {
      error.value = caughtError
      if (shouldReset) {
        items.value = []
      }
    } finally {
      loading.value = false
      loadingMore.value = false
    }
  }

  const loadMore = async () => {
    if (loading.value || loadingMore.value || !hasMore.value) {
      return
    }
    await loadLedger({ reset: false })
  }

  return {
    items,
    page,
    total,
    totalPages,
    loading,
    loadingMore,
    error,
    hasMore,
    reset,
    loadLedger,
    loadMore,
  }
}
