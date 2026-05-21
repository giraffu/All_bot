import { nextTick } from 'vue'
import type { ComputedRef, Ref } from 'vue'

type ScrollContainerRef = ComputedRef<HTMLElement | null> | Ref<HTMLElement | null>

interface UsePagedScrollNavigationOptions {
  contentRef: ScrollContainerRef
  goToPage: (pageNumber: number) => Promise<boolean>
  afterPageChange?: () => void | Promise<void>
}

export function usePagedScrollNavigation(options: UsePagedScrollNavigationOptions) {
  const scrollToTop = async () => {
    await nextTick()
    options.contentRef.value?.scrollTo({
      top: 0,
      behavior: 'smooth'
    })
  }

  const navigateToPage = async (pageNumber: number) => {
    const changed = await options.goToPage(pageNumber)
    if (!changed) return false

    await scrollToTop()
    await options.afterPageChange?.()
    return true
  }

  return {
    scrollToTop,
    navigateToPage
  }
}
