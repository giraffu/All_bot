import { computed, ref, watch, type Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import type { GalleryTaskTypeOption } from '@/composables/useGalleryConfig'
import { resolveGalleryTaskTypeLabel } from '@/utils/galleryPresentation'

export type FavoriteFilterTab = 'favorite' | 'like' | 'apply' | 'submissions'

function normalizeFilterType(tabValue: unknown): FavoriteFilterTab {
  const value = typeof tabValue === 'string' ? tabValue : ''
  if (value === 'like' || value === 'apply' || value === 'submissions') {
    return value
  }
  return 'favorite'
}

interface UseMyFavoritesFiltersOptions {
  route: RouteLocationNormalizedLoaded
  router: Router
  allowedTypes: Ref<GalleryTaskTypeOption[]>
  isMobile: Ref<boolean>
  t: (key: string) => string
  clearBrowserState: () => void
  reloadPosts: () => void
}

export function useMyFavoritesFilters(options: UseMyFavoritesFiltersOptions) {
  const filterType = ref<FavoriteFilterTab>(normalizeFilterType(options.route.query.tab))
  const selectedTaskType = ref('all')
  const isSubmissionTab = computed(() => filterType.value === 'submissions')

  const filterTabs = computed(() => [
    { id: 'favorite' as const, name: options.t('my_notes.tabs.favorite') },
    { id: 'like' as const, name: options.t('my_notes.tabs.like') },
    { id: 'apply' as const, name: options.t('my_notes.tabs.apply') },
    { id: 'submissions' as const, name: options.t('my_notes.tabs.submissions') },
  ])

  const taskTypeTabs = computed(() => [
    { id: 'all', name: options.t('gallery.tabs.all') },
    ...options.allowedTypes.value.map((taskType) => ({
      ...taskType,
      name: resolveGalleryTaskTypeLabel(taskType.id, options.t),
    })),
  ])

  const emptyStateText = computed(() => {
    if (filterType.value === 'like') return options.t('my_notes.empty_like')
    if (filterType.value === 'apply') return options.t('my_notes.empty_apply')
    return options.t('my_notes.empty_favorite')
  })

  const handleFilterTypeChange = (type: string) => {
    const nextType = normalizeFilterType(type)
    if (nextType === filterType.value) return
    filterType.value = nextType
  }

  const handleTaskTypeChange = (taskType: string) => {
    if (taskType === selectedTaskType.value) return
    selectedTaskType.value = taskType
  }

  watch(
    () => options.route.query.tab,
    (tabValue) => {
      const nextType = normalizeFilterType(tabValue)
      if (nextType !== filterType.value) {
        filterType.value = nextType
      }
    },
  )

  watch(
    filterType,
    (nextType) => {
      const currentTab = typeof options.route.query.tab === 'string'
        ? options.route.query.tab
        : undefined

      if (currentTab !== nextType) {
        void options.router.replace({
          name: 'MyFavorites',
          query: {
            ...options.route.query,
            tab: nextType,
          },
        })
      }

      if (nextType === 'submissions') {
        options.clearBrowserState()
        return
      }

      options.reloadPosts()
    },
  )

  watch(selectedTaskType, () => {
    if (isSubmissionTab.value) {
      return
    }
    options.reloadPosts()
  })

  watch(options.isMobile, (nextIsMobile, previousIsMobile) => {
    if (nextIsMobile === previousIsMobile) {
      return
    }
    if (filterType.value === 'favorite') {
      options.reloadPosts()
    }
  })

  return {
    filterType,
    selectedTaskType,
    isSubmissionTab,
    filterTabs,
    taskTypeTabs,
    emptyStateText,
    handleFilterTypeChange,
    handleTaskTypeChange,
  }
}
