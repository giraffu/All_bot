import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

interface UseRenderSettlingOptions<TItem> {
  loadingRef: Ref<boolean>
  itemsRef: Ref<TItem[]>
  fallbackDelayMs?: number
}

export function useRenderSettling<TItem>(
  options: UseRenderSettlingOptions<TItem>
) {
  const renderSettling = ref(false)
  let renderSettleTimer: ReturnType<typeof setTimeout> | null = null

  const clearRenderSettleTimer = () => {
    if (renderSettleTimer) {
      clearTimeout(renderSettleTimer)
      renderSettleTimer = null
    }
  }

  const releaseRenderSettling = () => {
    clearRenderSettleTimer()
    renderSettling.value = false
  }

  const scheduleRenderSettlingFallback = () => {
    clearRenderSettleTimer()
    renderSettleTimer = setTimeout(() => {
      renderSettling.value = false
    }, options.fallbackDelayMs ?? 3000)
  }

  const startRenderSettling = () => {
    renderSettling.value = true
  }

  const handleRenderSettled = () => {
    if (!renderSettling.value) {
      return
    }
    releaseRenderSettling()
  }

  watch(
    [options.loadingRef, options.itemsRef],
    ([isLoading, currentItems]) => {
      if (isLoading) {
        return
      }
      if (currentItems.length === 0) {
        releaseRenderSettling()
        return
      }
      if (renderSettling.value) {
        scheduleRenderSettlingFallback()
      }
    },
    { immediate: true }
  )

  onBeforeUnmount(() => {
    clearRenderSettleTimer()
  })

  return {
    renderSettling,
    startRenderSettling,
    handleRenderSettled,
  }
}
