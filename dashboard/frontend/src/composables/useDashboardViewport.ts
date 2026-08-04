import { onMounted, onUnmounted, ref } from 'vue'

export const DASHBOARD_MOBILE_MEDIA_QUERY = '(max-width: 767px)'

export function useDashboardViewport() {
  const mediaQuery = typeof window === 'undefined' || typeof window.matchMedia !== 'function'
    ? null
    : window.matchMedia(DASHBOARD_MOBILE_MEDIA_QUERY)
  const isMobile = ref(mediaQuery?.matches ?? false)

  const syncViewport = (event: MediaQueryListEvent | MediaQueryList) => {
    isMobile.value = event.matches
  }

  onMounted(() => mediaQuery?.addEventListener('change', syncViewport))
  onUnmounted(() => mediaQuery?.removeEventListener('change', syncViewport))

  return { isMobile }
}
