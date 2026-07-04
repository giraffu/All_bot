import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { followUser, unfollowUser } from '@/api/social'
import { reportGalleryPost, type GalleryReportReason } from '@/api/gallery'
import api from '@/api'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { useGalleryConfig } from '@/composables/useGalleryConfig'
import { useGalleryDetailModalAdapter } from '@/composables/useGalleryDetailModalAdapter'
import { useGalleryFilters } from '@/composables/useGalleryFilters'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import { useDetailTemplateApply } from '@/composables/useDetailTemplateApply'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import { useGalleryPromptUnlock } from '@/composables/useGalleryPromptUnlock'
import { useRenderSettling } from '@/composables/useRenderSettling'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { GalleryPost } from '@/types/gallery'
import {
  buildGalleryTaskTypeTabs,
  GALLERY_LORA_MODEL_NONE,
} from '@/utils/galleryTaskTypeFilters'
import {
  formatGalleryTag,
  resolveGalleryTaskTypeLabel,
} from '@/utils/galleryPresentation'
import {
  resolveGalleryTemplateApplyDisabledMessage,
  resolveGalleryTemplateApplyDisabledReason,
} from '@/utils/galleryTemplateApply'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { useViewport } from '@/composables/useViewport'

const resolveGalleryApplyIdFromLocation = (): number | null => {
  if (typeof window === 'undefined') {
    return null
  }
  const params = new URLSearchParams(window.location.search)
  if (params.get('apply_source') !== 'gallery') {
    return null
  }
  const rawApplyId = params.get('apply_id')
  const applyId = Number(rawApplyId)
  return Number.isInteger(applyId) && applyId > 0 ? applyId : null
}

export function useGalleryPageState() {
  const { t } = useI18n()
  const { isMobile } = useViewport()
  const templateApplyStore = useTemplateApplyStore()
  const layoutContentRef = useMainLayoutContentRef()
  const userProfileVisible = ref(false)
  const activeProfileUserId = ref<number | null>(null)
  const followLoadingUserId = ref<number | null>(null)
  const reportModalOpen = ref(false)
  const selectedReportReason = ref<GalleryReportReason>('children')
  const reportSubmitting = ref(false)
  const pendingDeepLinkApplyId = ref<number | null>(resolveGalleryApplyIdFromLocation())

  const breakpoints = {
    99999: { rowPerView: 6 },
    1280: { rowPerView: 5 },
    1024: { rowPerView: 4 },
    768: { rowPerView: 3 },
    640: { rowPerView: 2 },
  }

  const pageSize = computed(() => (isMobile.value ? 10 : 20))

  const {
    allowedTypes,
    videoLoraModels,
    img2imgLoraModels,
    loadConfig,
  } = useGalleryConfig({
    includeLoraModels: true,
    onError: (error) => {
      console.error('Failed to load gallery config:', error)
    },
  })

  const {
    posts,
    loading: browserLoading,
    errorMessage,
    currentPage,
    totalPages,
    detailVisible,
    currentPost,
    hasPrev,
    hasNext,
    goNext,
    goPrev,
    goToPage: browserGoToPage,
    loadPosts: loadBrowserPosts,
    openDetail,
    prefetchNextPage,
  } = usePagedPostBrowser<GalleryPost>({
    pageSize,
    fetchPageData: async (pageNumber) => {
      const res = await api.get('/gallery/posts', {
        params: {
          page: pageNumber,
          size: pageSize.value,
          media_type: mediaType.value,
          task_type: taskType.value,
          lora_model: requestLoraModel.value,
          sort_by: sortBy.value,
          time_range: timeRange.value,
        },
      })

      return {
        items: res.data.items.map((post: GalleryPost) => {
          const cardView = resolveMediaCardView(post, {
            normalizeGalleryThumbnail: true,
          })
          return {
            ...post,
            src: cardView.initialSrc,
            cardIsVideo: cardView.isVideo,
            cardPoster: cardView.posterSrc,
          }
        }),
        total: res.data.total,
        pages: res.data.pages,
      }
    },
    onFetchError: (error) => {
      console.error(error)
      message.error('获取广场数据失败')
    },
    getFetchErrorMessage: () => t('my_notes.load_failed'),
  })

  const {
    comments,
    commentsLoading,
    commentsError,
    commentsPage,
    commentsTotal,
    commentsHasMore,
    showCommentInput,
    newComment,
    submittingComment,
    loadComments,
    loadMoreComments,
    submitComment,
  } = useGalleryComments(currentPost, posts, detailVisible)

  const {
    renderSettling,
    startRenderSettling,
    handleRenderSettled,
  } = useRenderSettling({
    loadingRef: browserLoading,
    itemsRef: posts,
    fallbackDelayMs: 3000,
  })

  const loading = computed(() => browserLoading.value || renderSettling.value)

  const { handleInteract } = useGalleryPostInteractions<GalleryPost>({
    resolveSuccessMessage: (action, state) => {
      if (action === 'like') {
        return state === 'canceled' ? '已取消点赞' : '点赞成功'
      }
      return state === 'canceled' ? '已取消点踩' : '点踩成功'
    },
    onError: (error) => {
      console.error(error)
    },
  })
  const currentTemplateApplyDisabledReason = computed(() =>
    resolveGalleryTemplateApplyDisabledReason(currentPost.value)
  )
  const currentTemplateApplyDisabledMessage = computed(() =>
    currentTemplateApplyDisabledReason.value
      ? resolveGalleryTemplateApplyDisabledMessage(
          t,
          currentTemplateApplyDisabledReason.value
        )
      : ''
  )

  const { applying, handleApply } = useDetailTemplateApply<GalleryPost>({
    currentPost,
    detailVisible,
    itemId: (post) => post.id,
    source: 'gallery',
    templateApplyStore,
    t,
    isApplyDisabled: (post) => resolveGalleryTemplateApplyDisabledReason(post) !== null,
    getApplyDisabledMessage: (post) =>
      resolveGalleryTemplateApplyDisabledMessage(
        t,
        resolveGalleryTemplateApplyDisabledReason(post)
      ),
  })

  const currentDetailMedia = useCurrentDetailMedia(currentPost, {
    normalizeGalleryThumbnail: true,
  })
  const formatTag = (tag: string) => formatGalleryTag(tag, t)
  const { copyPrompt } = usePostPromptCopy(t)
  const { promptUnlockingPostId, handleUnlockPrompt } = useGalleryPromptUnlock({
    posts,
    currentPost,
    t,
  })

  const openReportModal = () => {
    if (!currentPost.value) {
      return
    }
    selectedReportReason.value = 'children'
    reportModalOpen.value = true
  }

  const submitReport = async () => {
    if (!currentPost.value) {
      return
    }

    reportSubmitting.value = true
    try {
      await reportGalleryPost(Number(currentPost.value.id), selectedReportReason.value)
      reportModalOpen.value = false
      message.success(t('gallery.report.submit_success'))
    } catch (error) {
      console.error(error)
    } finally {
      reportSubmitting.value = false
    }
  }

  const galleryDetailStandardActions = computed(() => ({
    showDesktopReaction: true,
    showDesktopApply: true,
    showDesktopCopy: false,
    showMobileReaction: true,
    showMobileApply: true,
    showMobileCopy: false,
    showDesktopReport: true,
    showMobileReport: true,
    showPromptPanelCopy: currentPost.value?.prompt_unlocked === true,
    showPromptPanelUnlock: !!currentPost.value?.prompt_unlockable,
    maskPromptText: currentPost.value?.prompt_unlocked === true
      ? false
      : currentPost.value?.prompt_is_masked === true
        ? false
        : true,
    promptVisibleRatio: 0.5,
    desktopApplyPlacement: 'before' as const,
    applyLabel: t('gallery.modal.apply_btn'),
    applyLoading: applying.value,
    applyDisabled: currentTemplateApplyDisabledReason.value !== null,
    applyHint: currentTemplateApplyDisabledMessage.value || t('gallery.modal.apply_hint'),
    copyLabel: t('my_posts.copy_prompt'),
    reportLabel: t('gallery.report.button'),
    reportLoading: reportSubmitting.value,
    unlockLabel: t('prompt_panel.unlock', {
      cost: currentPost.value?.prompt_unlock_price ?? 1,
    }),
    unlockLoading: currentPost.value
      ? promptUnlockingPostId.value === Number(currentPost.value.id)
      : false,
    onLike: () => {
      if (currentPost.value) {
        void handleInteract(currentPost.value, 'like')
      }
    },
    onDislike: () => {
      if (currentPost.value) {
        void handleInteract(currentPost.value, 'dislike')
      }
    },
    onComment: () => {
      showCommentInput.value = true
    },
    onApply: () => {
      void handleApply()
    },
    onCopy: () => {
      if (currentPost.value) {
        copyPrompt(currentPost.value)
      }
    },
    onReport: () => {
      openReportModal()
    },
    onUnlockPrompt: () => {
      void handleUnlockPrompt()
    },
  }))

  const {
    detailModalBindings: galleryDetailModalBindings,
    detailModalListeners: galleryDetailModalListeners,
  } = useGalleryDetailModalAdapter({
    open: detailVisible,
    commentInputOpen: showCommentInput,
    newComment,
    currentPost,
    currentDetailMedia,
    hasPrev,
    hasNext,
    isMobile,
    title: () => t('gallery.modal.title'),
    noTagsText: () => t('my_notes.no_tags'),
    formatTag,
    comments,
    commentsLoading,
    commentsError,
    commentsPage,
    commentsTotal,
    commentsHasMore,
    submittingComment,
    standardActions: galleryDetailStandardActions,
    loadComments,
    loadMoreComments,
    submitComment,
    goPrev,
    goNext,
  })

  const { navigateToPage } = usePagedScrollNavigation({
    contentRef: layoutContentRef,
    goToPage: browserGoToPage,
    afterPageChange: prefetchNextPage,
  })

  const {
    mediaType,
    taskType,
    loraModel,
    sortBy,
    timeRange,
    hasAddonSubfilters,
    currentLoraModels,
    requestLoraModel,
    handleTaskTypeChange,
    handleTimeRangeChange,
    handleSortChange,
    handleLoraModelChange,
  } = useGalleryFilters({
    videoLoraModels,
    img2imgLoraModels,
    onFiltersChange: () => {
      void loadPosts(true)
    },
  })

  const goToPage = async (pageNumber: number) => {
    await navigateToPage(pageNumber)
  }

  const loadPosts = async (reset = false) => {
    if (reset) {
      startRenderSettling()
    }
    await loadBrowserPosts(reset)
  }

  const clearGalleryApplyDeepLink = () => {
    if (typeof window === 'undefined') {
      return
    }
    const url = new URL(window.location.href)
    url.searchParams.delete('apply_source')
    url.searchParams.delete('apply_id')
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }

  const openDeepLinkApply = async () => {
    const applyId = pendingDeepLinkApplyId.value
    if (!applyId) {
      return
    }
    pendingDeepLinkApplyId.value = null
    clearGalleryApplyDeepLink()

    try {
      const response = await api.get(`/gallery/items/${applyId}/apply-context`)
      const result = await templateApplyStore.openFromRawContext({
        source: 'gallery',
        entryEntityId: applyId,
        rawContext: response.data,
      })

      if (result.status === 'opened') {
        message.success(t('template_apply.open_success'))
      } else if (result.status === 'legacy_fallback') {
        message.error(t('template_apply.open_failed'))
      } else if (result.status === 'invalid') {
        message.error(result.message)
      }
    } catch (error) {
      console.error(error)
      message.error(t('my_notes.template_load_failed'))
    }
  }

  const resolveTaskTypeLabel = (taskTypeId: string) =>
    resolveGalleryTaskTypeLabel(taskTypeId, t)

  const visibleAllowedTypes = computed(() =>
    allowedTypes.value.filter((taskTypeOption) => taskTypeOption.id !== 'txt2img'),
  )

  const taskTypeTabs = computed(() => [
    { id: 'all', name: t('gallery.tabs.all') },
    ...buildGalleryTaskTypeTabs(visibleAllowedTypes.value).map((tab) => ({
      id: tab.id,
      name: resolveTaskTypeLabel(tab.id),
    })),
  ])

  useScrollPrefetch(layoutContentRef, prefetchNextPage, {
    isEnabled: () => !templateApplyStore.visible,
  })

  const handleImageError = (event: Event, post: GalleryPost) => {
    handleMediaCardImageError(event, post)
  }

  const openUserProfile = (userId?: number | null) => {
    if (!userId) {
      return
    }
    activeProfileUserId.value = userId
    userProfileVisible.value = true
  }

  const syncFollowStateForAuthor = (userId: number, isFollowing: boolean) => {
    posts.value = posts.value.map((post) =>
      post.author_id === userId
        ? {
            ...post,
            is_following_author: isFollowing,
          }
        : post,
    )

    if (currentPost.value?.author_id === userId) {
      currentPost.value = {
        ...currentPost.value,
        is_following_author: isFollowing,
      }
    }
  }

  const handleAuthorFollow = async (post: GalleryPost) => {
    if (!post.author_id) {
      return
    }

    followLoadingUserId.value = post.author_id
    try {
      const response = post.is_following_author
        ? await unfollowUser(post.author_id)
        : await followUser(post.author_id)
      syncFollowStateForAuthor(post.author_id, response.is_following)
      message.success(
        response.is_following ? t('social.follow_success') : t('social.unfollow_success'),
      )
    } catch (error) {
      console.error(error)
      message.error(t('social.follow_action_failed'))
    } finally {
      followLoadingUserId.value = null
    }
  }

  const handleWaterfallAfterRender = () => {
    handleRenderSettled()
  }

  onMounted(() => {
    void loadConfig()
    void (async () => {
      await loadPosts(true)
      await openDeepLinkApply()
    })()
  })

  watch(pageSize, (nextSize, previousSize) => {
    if (nextSize !== previousSize) {
      void loadPosts(true)
    }
  })

  return {
    GALLERY_LORA_MODEL_NONE,
    breakpoints,
    posts,
    loading,
    errorMessage,
    currentPage,
    totalPages,
    taskTypeTabs,
    taskType,
    timeRange,
    sortBy,
    hasAddonSubfilters,
    currentLoraModels,
    loraModel,
    isMobile,
    galleryDetailModalBindings,
    galleryDetailModalListeners,
    reportModalOpen,
    selectedReportReason,
    reportSubmitting,
    userProfileVisible,
    activeProfileUserId,
    followLoadingUserId,
    handleTaskTypeChange,
    handleTimeRangeChange,
    handleSortChange,
    handleLoraModelChange,
    goToPage,
    loadPosts,
    openDetail,
    openUserProfile,
    handleAuthorFollow,
    syncFollowStateForAuthor,
    submitReport,
    handleImageError,
    handleInteract,
    handleWaterfallAfterRender,
    formatTag,
  }
}
