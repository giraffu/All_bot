<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { Waterfall } from 'vue-waterfall-plugin-next'
import 'vue-waterfall-plugin-next/dist/style.css'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import api from '@/api'
import MySubmissionsPanel from '@/components/MySubmissionsPanel.vue'
import FavoriteDetailActions from '@/components/FavoriteDetailActions.vue'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import HeaderPaginationBar from '@/components/HeaderPaginationBar.vue'
import OriginalInputBadge from '@/components/OriginalInputBadge.vue'
import PostCardMetricsBar from '@/components/PostCardMetricsBar.vue'
import PostBrowserShell from '@/components/PostBrowserShell.vue'
import PostTagPreview from '@/components/PostTagPreview.vue'
import SegmentedTabsRail from '@/components/SegmentedTabsRail.vue'
import StickyHeaderSection from '@/components/StickyHeaderSection.vue'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import { useMyLibraryPostBrowser } from '@/composables/useMyLibraryPostBrowser'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { useViewport } from '@/composables/useViewport'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { useGalleryDetailModalAdapter } from '@/composables/useGalleryDetailModalAdapter'
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useGalleryConfig } from '@/composables/useGalleryConfig'
import { useMyFavoritesFilters } from '@/composables/useMyFavoritesFilters'
import type { GalleryPost as Post } from '@/types/gallery'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const layoutContentRef = useMainLayoutContentRef()

const { isMobile } = useViewport()
const waterfallBreakpoints = {
  99999: { rowPerView: 5 },
  1024: { rowPerView: 4 },
  768: { rowPerView: 3 },
  640: { rowPerView: 2 },
}
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
  handleInteract,
  applying,
  handleApply,
  currentTemplateApplyDisabledReason,
  currentTemplateApplyDisabledMessage,
  currentDetailMedia,
  formatTag,
  copyPrompt,
  promptUnlockingPostId,
  handleUnlockPrompt,
  favoriteSupportsPostDetail,
} = useMyLibraryPostBrowser<Post>({
  pageSize,
  scope: () => (filterType.value === 'favorite' ? 'favorite' : filterType.value),
  taskType: () => selectedTaskType.value,
  t,
  templateApplySource: () => (filterType.value === 'favorite' ? 'favorites' : 'gallery'),
  detailItemId: (post) => (filterType.value === 'favorite' ? post.task_id : post.id),
  detailEntryEntityId: (post) => post.id,
  ignoreTemplateApplyNotFound: true,
  resolveCommentsPostId: (post) => {
    if (!post) {
      return null
    }

    const postId = Number(post.id)
    if (!Number.isFinite(postId) || postId <= 0) {
      return null
    }

    if (filterType.value === 'favorite' && post.is_active === false) {
      return null
    }

    return postId
  },
  resolveCardViewOptions: (scope) => ({
    fallbackToOriginalWithoutThumbnail: scope !== 'favorite',
  }),
  shouldIgnoreInteractionError: (error) => error.response?.status === 404,
  resolveInteractionSuccessMessage: (action, state) => {
    if (action === 'like') {
      return state === 'canceled' ? t('my_notes.like_removed') : t('my_notes.like_added')
    }
    return state === 'canceled' ? t('my_notes.dislike_removed') : t('my_notes.dislike_added')
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
const favoritesDetailStandardActions = computed(() => ({
  showDesktopReaction: filterType.value !== 'favorite',
  showDesktopApply: true,
  showDesktopCopy: filterType.value !== 'like' && currentPost.value?.prompt_unlocked === true,
  showMobileReaction: filterType.value !== 'favorite',
  showMobileApply: true,
  showMobileCopy: filterType.value !== 'like' && currentPost.value?.prompt_unlocked === true,
  showPromptPanelCopy: filterType.value !== 'like' && currentPost.value?.prompt_unlocked === true,
  showPromptPanelUnlock: !!currentPost.value?.prompt_unlockable,
  maskPromptText: currentPost.value?.prompt_unlocked === true
    ? false
    : currentPost.value?.prompt_is_masked === true
      ? false
      : filterType.value === 'like',
  promptVisibleRatio: 0.5,
  desktopApplyPlacement: 'after' as const,
  applyLabel: t('gallery.modal.apply_btn'),
  applyLoading: applying.value,
  applyDisabled: currentTemplateApplyDisabledReason.value !== null,
  applyLoadingLabel: t('my_notes.applying_template'),
  applyHint: currentTemplateApplyDisabledMessage.value || t('gallery.modal.apply_hint'),
  copyLabel: t('my_posts.copy_prompt'),
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
  onCopy: () => {
    if (currentPost.value) {
      void copyPrompt(currentPost.value)
    }
  },
  onUnlockPrompt: () => {
    void handleUnlockPrompt()
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
            active-class="bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]"
            inactive-class="bg-[var(--theme-pill-bg)] text-[var(--theme-text-secondary)] border border-[var(--theme-border)] hover:text-[var(--theme-tab-hover-text)] hover:border-[var(--theme-tab-active-border)]"
            @select="handleFilterTypeChange"
          />
        </div>

        <SegmentedTabsRail
          v-if="taskTypeTabs.length > 1"
          :items="taskTypeTabs"
          :selected-id="selectedTaskType"
          container-class="mt-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card-strong-bg)] px-2 py-2 shadow-[0_6px_18px_rgba(15,23,42,0.12)]"
          content-class="flex gap-1 bg-[var(--theme-pill-bg)] p-1 rounded-xl border border-[var(--theme-border)]"
          active-class="bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]"
          inactive-class="text-[var(--theme-text-secondary)] hover:text-[var(--theme-tab-hover-text)]"
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

    <Waterfall
      v-else
      :list="posts"
      row-key="id"
      :breakpoints="waterfallBreakpoints"
      :gutter="isMobile ? 12 : 24"
      :animation-duration="400"
      background-color="transparent"
      :has-around-gutter="false"
    >
      <template #default="{ item: post }">
        <GalleryMediaCard
          :item="post"
          media-container-class="favorites-media-pane relative w-full overflow-hidden aspect-auto min-h-[100px]"
          :media-container-style="post.width && post.height ? { aspectRatio: `${post.width}/${post.height}` } : { aspectRatio: '1/1' }"
          @card-click="openDetail(post)"
          @image-error="handleImageError($event, post)"
        >
          <template #top-left>
            <OriginalInputBadge :source="post" />
          </template>
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
      </template>
    </Waterfall>
  </PostBrowserShell>

    <GalleryDetailModal
      v-bind="favoritesDetailModalBindings"
      :show-comments-section="favoriteSupportsPostDetail"
      :show-comment-composer="favoriteSupportsPostDetail"
      v-on="favoritesDetailModalListeners"
    >
      <template v-if="filterType === 'favorite'" #before-comments-extra="{ post, openCommentInput }">
        <div class="hidden lg:flex space-x-2 mb-4 pt-4 border-t border-slate-700 lg:border-slate-400/30">
          <FavoriteDetailActions
            :comments-count="post.comments_count || 0"
            :unfavorite-label="t('my_notes.unfavorite_button')"
              :show-comment-button="favoriteSupportsPostDetail"
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
            :show-comment-button="favoriteSupportsPostDetail"
            @unfavorite="handleUnfavorite(post)"
            @comment="openCommentInput()"
          />
      </template>
    </GalleryDetailModal>
</template>

<style scoped>
.favorites-media-pane {
  background: var(--theme-card-strong-bg);
}
</style>
