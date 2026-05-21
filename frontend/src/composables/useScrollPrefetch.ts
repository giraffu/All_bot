import { onUnmounted, watch, type Ref } from 'vue'

interface UseScrollPrefetchOptions {
  threshold?: number
  isEnabled?: () => boolean
}

export function useScrollPrefetch(
  containerRef: Ref<HTMLElement | null | undefined>,
  onReachThreshold: () => void,
  options: UseScrollPrefetchOptions = {}
) {
  const threshold = options.threshold ?? 200

  const handleScroll = () => {
    if (options.isEnabled && !options.isEnabled()) {
      return
    }

    const container = containerRef.value
    if (!container) return

    const { scrollTop, scrollHeight, clientHeight } = container
    if (scrollHeight - scrollTop - clientHeight < threshold) {
      onReachThreshold()
    }
  }

  watch(
    containerRef,
    (container, previousContainer) => {
      previousContainer?.removeEventListener('scroll', handleScroll)
      container?.addEventListener('scroll', handleScroll)
    },
    { immediate: true }
  )

  onUnmounted(() => {
    containerRef.value?.removeEventListener('scroll', handleScroll)
  })

  return {
    handleScroll,
  }
}
