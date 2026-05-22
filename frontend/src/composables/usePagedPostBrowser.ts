import { computed, ref, type Ref } from 'vue'

interface PagedResult<T> {
  items: T[]
  total?: number
  pages?: number
}

interface FetchPageOptions {
  activate?: boolean
  force?: boolean
}

interface UsePagedPostBrowserOptions<T extends { id: number | string }> {
  pageSize: Ref<number>
  fetchPageData: (pageNumber: number) => Promise<PagedResult<T>>
  onFetchError?: (error: unknown) => void
  getFetchErrorMessage?: (error: unknown) => string | undefined
}

export const usePagedPostBrowser = <T extends { id: number | string }>(
  options: UsePagedPostBrowserOptions<T>
) => {
  const posts = ref<T[]>([]) as Ref<T[]>
  const loading = ref(false)
  const currentPage = ref(1)
  const pageCache = ref<Record<number, T[]>>({})
  const total = ref(0)
  const totalPages = ref(0)
  const errorMessage = ref('')
  const detailVisible = ref(false)
  const currentPost = ref<T | null>(null)
  const pendingPages = new Set<number>()

  let currentVisibleRequestId = 0
  let currentQueryVersion = 0

  const currentIndex = computed(() => {
    if (!currentPost.value) return -1
    return posts.value.findIndex((post) => post.id === currentPost.value?.id)
  })

  const hasPrev = computed(() => currentIndex.value > 0 || currentPage.value > 1)
  const hasNext = computed(
    () => currentIndex.value >= 0 && (
      currentIndex.value < posts.value.length - 1 || currentPage.value < totalPages.value
    ),
  )

  const resetPaginationState = () => {
    currentPage.value = 1
    posts.value = []
    pageCache.value = {}
    total.value = 0
    totalPages.value = 0
    errorMessage.value = ''
    loading.value = false
  }

  const clearBrowserState = () => {
    currentQueryVersion += 1
    resetPaginationState()
  }

  const syncPageResult = (pageNumber: number, result: PagedResult<T>) => {
    pageCache.value = {
      ...pageCache.value,
      [pageNumber]: result.items,
    }
    total.value = typeof result.total === 'number' ? result.total : total.value
    totalPages.value = typeof result.pages === 'number' && result.pages > 0
      ? result.pages
      : Math.max(1, Math.ceil((total.value || result.items.length) / options.pageSize.value))
  }

  const fetchPostsPage = async (
    pageNumber: number,
    fetchOptions: FetchPageOptions = {}
  ) => {
    const { activate = false, force = false } = fetchOptions
    const cachedItems = pageCache.value[pageNumber]

    if (!force && cachedItems) {
      if (activate) {
        currentPage.value = pageNumber
        posts.value = cachedItems
      }
      return true
    }

    if (pendingPages.has(pageNumber)) {
      return false
    }

    const requestVersion = currentQueryVersion
    const visibleRequestId = activate ? ++currentVisibleRequestId : currentVisibleRequestId
    pendingPages.add(pageNumber)

    if (activate) {
      loading.value = true
    }

    try {
      const result = await options.fetchPageData(pageNumber)
      if (requestVersion !== currentQueryVersion) {
        return false
      }

      syncPageResult(pageNumber, result)
      errorMessage.value = ''
      if (activate && visibleRequestId === currentVisibleRequestId) {
        currentPage.value = pageNumber
        posts.value = result.items
      }
      return true
    } catch (error) {
      if (requestVersion !== currentQueryVersion) {
        return false
      }
      errorMessage.value = options.getFetchErrorMessage?.(error) ?? ''
      options.onFetchError?.(error)
      return false
    } finally {
      pendingPages.delete(pageNumber)
      if (
        activate
        && visibleRequestId === currentVisibleRequestId
      ) {
        loading.value = false
      }
    }
  }

  const prefetchNextPage = () => {
    if (!totalPages.value || currentPage.value >= totalPages.value) {
      return
    }
    void fetchPostsPage(currentPage.value + 1)
  }

  const loadPosts = async (reset = false) => {
    if (!reset) {
      prefetchNextPage()
      return
    }

    currentQueryVersion += 1
    resetPaginationState()
    const loaded = await fetchPostsPage(1, { activate: true, force: true })
    if (loaded) {
      prefetchNextPage()
    }
  }

  const goToPage = async (pageNumber: number) => {
    if (pageNumber < 1 || (totalPages.value > 0 && pageNumber > totalPages.value)) {
      return false
    }

    const changed = await fetchPostsPage(pageNumber, { activate: true })
    if (changed) {
      prefetchNextPage()
    }
    return changed
  }

  const goPrev = async () => {
    if (currentIndex.value > 0) {
      currentPost.value = posts.value[currentIndex.value - 1]
      return true
    }

    if (currentPage.value <= 1) return false
    const changed = await fetchPostsPage(currentPage.value - 1, { activate: true })
    if (changed) {
      currentPost.value = posts.value[posts.value.length - 1] ?? null
    }
    return changed
  }

  const goNext = async () => {
    if (currentIndex.value >= 0 && currentIndex.value < posts.value.length - 1) {
      currentPost.value = posts.value[currentIndex.value + 1]
      if (currentIndex.value >= posts.value.length - 3) {
        prefetchNextPage()
      }
      return true
    }

    if (currentPage.value >= totalPages.value) return false
    const changed = await fetchPostsPage(currentPage.value + 1, { activate: true })
    if (changed) {
      currentPost.value = posts.value[0] ?? null
    }
    return changed
  }

  const openDetail = (post: T) => {
    currentPost.value = post
    detailVisible.value = true
  }

  return {
    posts,
    loading,
    currentPage,
    total,
    totalPages,
    errorMessage,
    detailVisible,
    currentPost,
    currentIndex,
    hasPrev,
    hasNext,
    clearBrowserState,
    fetchPostsPage,
    goNext,
    goPrev,
    goToPage,
    loadPosts,
    openDetail,
    prefetchNextPage,
  }
}
