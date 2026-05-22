<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import api from '@/api'
import MySubmissionsPanel from '@/components/MySubmissionsPanel.vue'
import FavoriteDetailActions from '@/components/FavoriteDetailActions.vue'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import HeaderPaginationBar from '@/components/HeaderPaginationBar.vue'
import PostCardMetricsBar from '@/components/PostCardMetricsBar.vue'
import PostBrowserShell from '@/components/PostBrowserShell.vue'
import PostTagPreview from '@/components/PostTagPreview.vue'
import SegmentedTabsRail from '@/components/SegmentedTabsRail.vue'
import StickyHeaderSection from '@/components/StickyHeaderSection.vue'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import { useTemplateApplyStore } from '@/stores/templateApply'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { useViewport } from '@/composables/useViewport'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { useDetailTemplateApply } from '@/composables/useDetailTemplateApply'
import { useGalleryDetailModalAdapter } from '@/composables/useGalleryDetailModalAdapter'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import { useGalleryConfig } from '@/composables/useGalleryConfig'
import { useMyFavoritesFilters } from '@/composables/useMyFavoritesFilters'
import {
  formatGalleryTag,
} from '@/utils/galleryPresentation'

interface Post {
  id: number
  task_id: string
  media_type: string
  width: number
  height: number
  duration: number
  tags: string[]
  likes_count: number
  dislikes_count: number
  applied_count: number
  comments_count: number
  thumbnail_url: string
  media_url: string
  created_at: string
  has_liked: boolean
  has_disliked: boolean
  is_active: boolean
  prompt: string
  src?: string
  cardIsVideo?: boolean
  cardPoster?: string
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const layoutContentRef = useMainLayoutContentRef()
const templateApplyStore = useTemplateApplyStore()

const { isMobile } = useViewport()
const { allowedTypes, loadConfig } = useGalleryConfig({
  onError: (error) => {
    console.error('Failed to load note filters config:', error)
  }
})
const pageSize = computed(() => {
  if (filterType.value === 'favorite' && isMobile.value) {
    return 5
  }
  return 20
})

const {
  posts,
  loading,
  errorMessage,
  currentPage,
  totalPages,
  detailVisible,
  currentPost,
  hasPrev,
  hasNext,
  clearBrowserState,
  goNext,
  goPrev,
  goToPage: browserGoToPage,
  loadPosts: loadBrowserPosts,
  openDetail,
  prefetchNextPage: prefetchBrowserNextPage,
} = usePagedPostBrowser<Post>({
  pageSize,
  fetchPageData: async (pageNumber) => {
    const endpoint = filterType.value === 'favorite' ? '/users/my-favorites' : '/gallery/my-favorites'
    const res = await api.get(endpoint, {
      params: {
        page: pageNumber,
        size: pageSize.value,
        filter_type: filterType.value === 'favorite' ? 'all' : filterType.value,
        task_type: selectedTaskType.value === 'all' ? undefined : selectedTaskType.value,
      }
    })

    return {
      items: res.data.items.map((post: Post) => {
        const cardView = resolveMediaCardView(post, {
          fallbackToOriginalWithoutThumbnail: filterType.value !== 'favorite',
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
    message.error(t('my_notes.load_failed'))
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
  submitComment
} = useGalleryComments(currentPost, posts, detailVisible)
const { handleInteract } = useGalleryPostInteractions<Post>({
  resolveSuccessMessage: (action, state) => {
    if (action === 'like') {
      return state === 'canceled' ? t('my_notes.like_removed') : t('my_notes.like_added')
    }
    return state === 'canceled' ? t('my_notes.dislike_removed') : t('my_notes.dislike_added')
  },
  shouldIgnoreError: (error) => error.response?.status === 404,
  onError: (error) => {
    console.error(error)
  },
})
const {
  filterType,
  selectedTaskType,
  isSubmissionTab,
  filterTabs,
  taskTypeTabs,
  emptyStateText,
  handleFilterTypeChange,
  handleTaskTypeChange,
} = useMyFavoritesFilters({
  route,
  router,
  allowedTypes,
  isMobile,
  t,
  clearBrowserState,
  reloadPosts: () => {
    void loadBrowserPosts(true)
  },
})
const currentDetailMedia = useCurrentDetailMedia(currentPost)
const formatTag = (tag: string) => formatGalleryTag(tag, t)
const { copyPrompt } = usePostPromptCopy(t)
const { applying, handleApply, cancelPendingApply } = useDetailTemplateApply<Post>({
  currentPost,
  detailVisible,
  endpoint: (post) => (
    filterType.value === 'favorite'
      ? `/users/history/${post.task_id}/apply-context`
      : `/gallery/posts/${post.id}/apply-context`
  ),
  source: () => (filterType.value === 'favorite' ? 'favorites' : 'gallery'),
  entryEntityId: (post) => post.id,
  templateApplyStore,
  t,
  ignoreNotFound: true
})
const favoritesDetailStandardActions = computed(() => ({
  showDesktopReaction: filterType.value !== 'favorite',
  showDesktopApply: true,
  showDesktopCopy: true,
  showMobileReaction: filterType.value !== 'favorite',
  showMobileApply: true,
  showMobileCopy: true,
  desktopApplyPlacement: 'after' as const,
  applyLabel: t('gallery.modal.apply_btn'),
  applyLoading: applying.value,
  applyLoadingLabel: t('my_notes.applying_template'),
  applyHint: t('gallery.modal.apply_hint'),
  copyLabel: t('my_posts.copy_prompt'),
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
  onCopy: () => {
    if (currentPost.value) {
      void copyPrompt(currentPost.value)
    }
  },
  onApply: () => {
    void handleApply()
  },
}))
const {
  detailModalBindings: favoritesDetailModalBindings,
  detailModalListeners: favoritesDetailModalListeners,
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
  standardActions: favoritesDetailStandardActions,
  loadComments,
  loadMoreComments,
  submitComment,
  goPrev,
  goNext,
  infoContentClass:
    'p-4 lg:p-6 flex-1 flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent',
  desktopCloseButtonClass: 'z-10',
})

const prefetchNextPage = () => {
  if (isSubmissionTab.value) {
    return
  }
  prefetchBrowserNextPage()
}
const { navigateToPage } = usePagedScrollNavigation({
  contentRef: layoutContentRef,
  goToPage: async (pageNumber) => {
    if (isSubmissionTab.value) {
      return false
    }
    return browserGoToPage(pageNumber)
  },
  afterPageChange: prefetchNextPage
})

const goToPage = async (pageNumber: number) => {
  await navigateToPage(pageNumber)
}
const loadPosts = async (reset = false) => {
  if (isSubmissionTab.value) return
  await loadBrowserPosts(reset)
}

const handleUnfavorite = async (post: Post) => {
  if (!post) return
  
  try {
    await api.delete(`/users/history/${post.task_id}/favorite`)
    message.success(t('my_notes.favorite_removed'))
    detailVisible.value = false
    void loadPosts(true)
  } catch (error: any) {
    if (error.response?.status === 404) {
      return
    }
    console.error(error)
    message.error(error.response?.data?.detail || t('my_notes.action_failed'))
  }
}

useScrollPrefetch(layoutContentRef, prefetchNextPage)

const handleImageError = (event: Event, post: Post) => {
  handleMediaCardImageError(event, post, {
    requireThumbnailForOriginalFallback: true,
  })
}

onMounted(() => {
  void loadConfig()
  void loadPosts(true)
})

watch(
  detailVisible,
  (visible, previousVisible) => {
    if (!visible && previousVisible) {
      cancelPendingApply()
    }
  },
  { flush: 'sync' }
)
</script>

<template>
  <PostBrowserShell
    :show-state="!isSubmissionTab"
    :loading="loading"
    :error-text="posts.length === 0 ? errorMessage : ''"
    :show-retry="posts.length === 0 && !!errorMessage"
    :empty="posts.length === 0"
    :empty-text="emptyStateText"
    :retry-text="t('gallery.comments.retry')"
    @retry="loadPosts(true)"
  >
    <template #header>
      <StickyHeaderSection class-name="-mx-3 px-3 md:-mx-6 md:px-6 pb-2">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <SegmentedTabsRail
            :items="filterTabs"
            :selected-id="filterType"
            container-class="pb-2 md:pb-0"
            content-class="flex items-center space-x-2"
            button-class="px-4 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap"
            active-class="bg-cyan-500 text-white shadow-[0_0_10px_rgba(56,189,248,0.4)]"
            inactive-class="bg-slate-500 text-slate-400 hover:bg-slate-500 hover:text-slate-200"
            @select="handleFilterTypeChange"
          />
        </div>

        <SegmentedTabsRail
          v-if="taskTypeTabs.length > 1"
          :items="taskTypeTabs"
          :selected-id="selectedTaskType"
          container-class="mt-3 rounded-2xl border border-slate-700/50 bg-slate-950/55 px-2 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]"
          @select="handleTaskTypeChange"
        />

        <HeaderPaginationBar
          v-if="!isSubmissionTab"
          wrapper-class="mt-3 flex justify-center"
          :current-page="currentPage"
          :total-pages="totalPages"
          :disabled="loading"
          :compact="isMobile"
          @change="goToPage"
        />
      </StickyHeaderSection>
    </template>

    <MySubmissionsPanel v-if="isSubmissionTab" :task-type="selectedTaskType" />

    <div v-else class="columns-2 sm:columns-3 md:columns-4 lg:columns-5 gap-3 sm:gap-6">
      <GalleryMediaCard
        v-for="post in posts"
        :key="post.id"
        :item="post"
        class="mb-3 sm:mb-6 break-inside-avoid"
        media-container-class="relative w-full overflow-hidden bg-slate-500 aspect-auto min-h-[100px]"
        :media-container-style="post.width && post.height ? { aspectRatio: `${post.width}/${post.height}` } : { aspectRatio: '1/1' }"
        @card-click="openDetail(post)"
        @image-error="handleImageError($event, post)"
      >
        <template #overlay>
          <div class="flex flex-col justify-between h-full">
            <PostTagPreview :tags="post.tags" :format-tag="formatTag" />
          </div>
        </template>
        <template #bottom>
          <PostCardMetricsBar
            v-if="filterType !== 'favorite'"
            :likes-count="post.likes_count"
            :dislikes-count="post.dislikes_count"
            :applied-count="post.applied_count"
            :has-liked="post.has_liked"
            :has-disliked="post.has_disliked"
            @like="handleInteract(post, 'like')"
            @dislike="handleInteract(post, 'dislike')"
          />
        </template>
      </GalleryMediaCard>
    </div>
  </PostBrowserShell>

    <GalleryDetailModal
      v-bind="favoritesDetailModalBindings"
      v-on="favoritesDetailModalListeners"
    >
      <template v-if="filterType === 'favorite'" #before-comments-extra="{ post, openCommentInput }">
        <div class="hidden lg:flex space-x-2 mb-4 pt-4 border-t border-slate-700 lg:border-slate-400/30">
          <FavoriteDetailActions
            :comments-count="post.comments_count || 0"
            :unfavorite-label="t('my_notes.unfavorite_button')"
            @unfavorite="handleUnfavorite(post)"
            @comment="openCommentInput()"
          />
        </div>
      </template>

      <template v-if="filterType === 'favorite'" #mobile-left-extra="{ post, openCommentInput }">
          <FavoriteDetailActions
            compact
            :comments-count="post.comments_count || 0"
            :unfavorite-label="t('my_notes.unfavorite_button')"
            @unfavorite="handleUnfavorite(post)"
            @comment="openCommentInput()"
          />
      </template>
    </GalleryDetailModal>
</template>
