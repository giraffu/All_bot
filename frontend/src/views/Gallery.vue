<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { followUser, unfollowUser } from '@/api/social'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { Heart, Flame, Clock } from 'lucide-vue-next'
import { Waterfall } from 'vue-waterfall-plugin-next'
import 'vue-waterfall-plugin-next/dist/style.css'
import api from '@/api'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import {
  useTemplateApplyStore
} from '@/stores/templateApply'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { useGalleryDetailModalAdapter } from '@/composables/useGalleryDetailModalAdapter'
import { getFileUrl } from '@/utils/mediaFiles'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import {
  formatGalleryTag,
  resolveGalleryTaskTypeLabel
} from '@/utils/galleryPresentation'
import {
  buildGalleryTaskTypeTabs,
  GALLERY_LORA_MODEL_NONE,
} from '@/utils/galleryTaskTypeFilters'
import { useGalleryConfig } from '@/composables/useGalleryConfig'
import { useGalleryFilters } from '@/composables/useGalleryFilters'
import { useViewport } from '@/composables/useViewport'
import LazyVideo from '@/components/LazyVideo.vue'
import OverflowScrollRail from '@/components/OverflowScrollRail.vue'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import HeaderPaginationBar from '@/components/HeaderPaginationBar.vue'
import PostCardMetricsBar from '@/components/PostCardMetricsBar.vue'
import PostBrowserShell from '@/components/PostBrowserShell.vue'
import PostTagPreview from '@/components/PostTagPreview.vue'
import SegmentedTabsRail from '@/components/SegmentedTabsRail.vue'
import StickyHeaderSection from '@/components/StickyHeaderSection.vue'
import UserProfileModal from '@/components/UserProfileModal.vue'
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useDetailTemplateApply } from '@/composables/useDetailTemplateApply'
import { useRenderSettling } from '@/composables/useRenderSettling'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import type { GalleryPost as Post } from '@/types/gallery'



const { t } = useI18n()
const { isMobile } = useViewport()
const templateApplyStore = useTemplateApplyStore()
const layoutContentRef = useMainLayoutContentRef()
const userProfileVisible = ref(false)
const activeProfileUserId = ref<number | null>(null)
const followLoadingUserId = ref<number | null>(null)

const breakpoints = {
  99999: { rowPerView: 6 },
  1280: { rowPerView: 5 },
  1024: { rowPerView: 4 },
  768:  { rowPerView: 3 },
  640:  { rowPerView: 2 }
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
} = usePagedPostBrowser<Post>({
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
        time_range: timeRange.value
      }
    })

    return {
      items: res.data.items.map((post: Post) => {
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
  submitComment
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
const { handleInteract } = useGalleryPostInteractions<Post>({
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
const { applying, handleApply } = useDetailTemplateApply<Post>({
  currentPost,
  detailVisible,
  itemId: (post) => post.id,
  source: 'gallery',
  templateApplyStore,
  t,
})

const currentDetailMedia = useCurrentDetailMedia(currentPost, {
  normalizeGalleryThumbnail: true,
})
const formatTag = (tag: string) => formatGalleryTag(tag, t)
const { copyPrompt } = usePostPromptCopy(t)
const galleryDetailStandardActions = computed(() => ({
  showDesktopReaction: true,
  showDesktopApply: true,
  showDesktopCopy: false,
  showMobileReaction: true,
  showMobileApply: true,
  showMobileCopy: false,
  showPromptPanelCopy: false,
  maskPromptText: true,
  promptVisibleRatio: 0.5,
  desktopApplyPlacement: 'before' as const,
  applyLabel: t('gallery.modal.apply_btn'),
  applyLoading: applying.value,
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
  onApply: () => {
    void handleApply()
  },
  onCopy: () => {
    if (currentPost.value) {
      copyPrompt(currentPost.value)
    }
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
  afterPageChange: prefetchNextPage
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
const resolveTaskTypeLabel = (taskTypeId: string) =>
  resolveGalleryTaskTypeLabel(taskTypeId, t)
const visibleAllowedTypes = computed(() =>
  allowedTypes.value.filter((taskTypeOption) => taskTypeOption.id !== 'txt2img')
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

const handleImageError = (event: Event, post: Post) => {
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

const handleAuthorFollow = async (post: Post) => {
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
  loadConfig()
  loadPosts(true)
})

watch(pageSize, (nextSize, previousSize) => {
  if (nextSize !== previousSize) {
    void loadPosts(true)
  }
})

</script>

<template>
  <PostBrowserShell
    :loading="loading"
    :error-text="posts.length === 0 ? errorMessage : ''"
    :show-retry="posts.length === 0 && !!errorMessage"
    :empty="posts.length === 0"
    :empty-text="$t('gallery.no_posts')"
    :retry-text="$t('gallery.comments.retry')"
    @retry="loadPosts(true)"
  >
    <template #header>
      <StickyHeaderSection class-name="-mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <div class="flex flex-col xl:flex-row justify-between xl:items-center gap-4">
          <SegmentedTabsRail
            :items="taskTypeTabs"
            :selected-id="taskType"
            container-class="w-full xl:w-auto shrink-0"
            content-class="flex gap-1 bg-[var(--theme-pill-bg)] p-1 rounded-xl border border-[var(--theme-border)]"
            active-class="bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]"
            inactive-class="text-[var(--theme-text-secondary)] hover:text-[var(--theme-tab-hover-text)]"
            @select="handleTaskTypeChange"
          />

          <OverflowScrollRail
            container-class="w-full xl:w-auto shrink-0 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card-strong-bg)] px-2 py-2 shadow-[0_6px_18px_rgba(15,23,42,0.12)]"
            content-class="flex items-center gap-3"
          >
            <div class="flex bg-[var(--theme-pill-bg)] p-1 rounded-xl border border-[var(--theme-border)] shrink-0">
              <button
                v-for="time in [{k:'all', n: $t('gallery.filters.all')}, {k:'today', n: $t('gallery.filters.today')}, {k:'week', n: $t('gallery.filters.this_week')}, {k:'month', n: $t('gallery.filters.this_month')}]"
                :key="time.k"
                @click="handleTimeRangeChange(time.k)"
                class="px-2 py-1 sm:px-3 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm whitespace-nowrap shrink-0"
                :class="timeRange === time.k ? 'bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]' : 'text-[var(--theme-text-secondary)] hover:text-[var(--theme-tab-hover-text)]'"
              >
                {{ time.n }}
              </button>
            </div>

            <div class="flex bg-[var(--theme-pill-bg)] p-1 rounded-xl border border-[var(--theme-border)] shrink-0">
              <button
                v-for="sort in [{k:'latest', n: $t('gallery.filters.latest'), i: Clock}, {k:'likes', n: $t('gallery.filters.most_liked'), i: Heart}, {k:'applied', n: $t('gallery.filters.most_used'), i: Flame}]"
                :key="sort.k"
                @click="handleSortChange(sort.k)"
                class="px-2 py-1 sm:px-3 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm flex items-center whitespace-nowrap shrink-0"
                :class="sortBy === sort.k ? 'bg-[var(--theme-tab-active-bg)] text-[var(--theme-tab-active-text)] border border-[var(--theme-tab-active-border)] shadow-[var(--theme-tab-active-shadow)]' : 'text-[var(--theme-text-secondary)] hover:text-[var(--theme-tab-hover-text)]'"
              >
                <component :is="sort.i" :size="14" class="mr-1.5 hidden sm:block" />
                {{ sort.n }}
              </button>
            </div>
          </OverflowScrollRail>
        </div>

        <OverflowScrollRail
          v-if="hasAddonSubfilters"
          container-class="w-full shrink-0 px-1 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card-strong-bg)] py-2 shadow-[0_6px_18px_rgba(15,23,42,0.12)]"
          content-class="flex items-center gap-2"
        >
          <span class="text-xs sm:text-sm text-[var(--theme-text-secondary)] whitespace-nowrap shrink-0">{{ $t('gallery.choose_addon') }}</span>
          <div class="flex gap-2 shrink-0">
            <button
              @click="handleLoraModelChange('all')"
              class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
              :class="loraModel === 'all' ? 'bg-pink-500/20 border-pink-500/50 text-pink-500' : 'border-[var(--theme-border)] hover:border-pink-400 text-[var(--theme-text-secondary)]'"
            >
              {{ $t('gallery.filters.all') }}
            </button>
            <button
              @click="handleLoraModelChange(GALLERY_LORA_MODEL_NONE)"
              class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
              :class="loraModel === GALLERY_LORA_MODEL_NONE ? 'bg-pink-500/20 border-pink-500/50 text-pink-500' : 'border-[var(--theme-border)] hover:border-pink-400 text-[var(--theme-text-secondary)]'"
            >
              {{ $t('gallery.no_addon') }}
            </button>
            <button
              v-for="lora in currentLoraModels"
              :key="lora.id"
              @click="handleLoraModelChange(lora.id)"
              class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
              :class="loraModel === lora.id ? 'bg-pink-500/20 border-pink-500/50 text-pink-500' : 'border-[var(--theme-border)] hover:border-pink-400 text-[var(--theme-text-secondary)]'"
            >
              {{ lora.name }}
            </button>
          </div>
        </OverflowScrollRail>

        <HeaderPaginationBar
          wrapper-class="-mt-1 flex justify-center"
          :current-page="currentPage"
          :total-pages="totalPages"
          :disabled="loading"
          :compact="isMobile"
          @change="goToPage"
        />
      </StickyHeaderSection>
    </template>

    <Waterfall
      :list="posts"
      rowKey="id"
      :breakpoints="breakpoints"
      :gutter="isMobile ? 12 : 24"
      :animationDuration="400"
      backgroundColor="transparent"
      :hasAroundGutter="false"
      @afterRender="handleWaterfallAfterRender"
    >
      <template #default="{ item: post }">
        <GalleryMediaCard
          :item="post"
          media-container-class="gallery-media-pane relative w-full overflow-hidden"
          :media-container-style="post.width && post.height ? { aspectRatio: `${post.width}/${post.height}` } : { aspectRatio: '1/1' }"
          overlay-visibility-class="opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity duration-300"
          @card-click="openDetail(post)"
        >
          <template #media>
            <img
              v-show="!post.cardIsVideo"
              :src="post.src"
              @error="handleImageError($event, post)"
              class="w-full object-cover transition-opacity duration-300 absolute inset-0 h-full"
              loading="lazy"
            />
            <LazyVideo
              v-show="post.cardIsVideo"
              :src="getFileUrl(post.media_url, post.id)"
              :poster="post.cardPoster || post.src"
              className="w-full object-cover absolute inset-0 h-full"
            />
          </template>
          <template #overlay>
            <div class="flex flex-col justify-end h-full">
              <PostTagPreview :tags="post.tags" :format-tag="formatTag" />
            </div>
          </template>
          <template #bottom>
            <PostCardMetricsBar
              :likes-count="post.likes_count"
              :dislikes-count="post.dislikes_count"
              :applied-count="post.applied_count"
              :comments-count="post.comments_count"
              :has-liked="post.has_liked"
              :has-disliked="post.has_disliked"
              show-comments
              @like="handleInteract(post, 'like')"
              @dislike="handleInteract(post, 'dislike')"
              @comment="openDetail(post)"
            />
          </template>
        </GalleryMediaCard>
      </template>
    </Waterfall>
  </PostBrowserShell>

    <GalleryDetailModal
      v-bind="galleryDetailModalBindings"
      v-on="galleryDetailModalListeners"
    >
      <template #mobile-header="{ post }">
        <div class="gallery-author-mobile flex items-center justify-between gap-3 w-full">
          <button
            type="button"
            class="gallery-author-mobile__identity flex items-center gap-2 min-w-0"
            @click.stop="openUserProfile(post.author_id)"
          >
            <div class="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-indigo-500 flex items-center justify-center text-white font-bold text-xs shrink-0">
              {{ post.author_name ? post.author_name.charAt(0).toUpperCase() : '修' }}
            </div>
            <span class="gallery-author-mobile__name font-semibold text-sm truncate">
              {{ post.author_name || t('social.anonymous_user') }}
            </span>
          </button>
          <a-button
            v-if="post.author_id"
            type="primary"
            size="small"
            class="gallery-author-mobile__follow-btn shrink-0"
            :loading="followLoadingUserId === post.author_id"
            @click.stop="handleAuthorFollow(post)"
          >
            {{ post.is_following_author ? t('social.unfollow') : t('social.follow') }}
          </a-button>
        </div>
      </template>

      <template #before-comments-extra="{ post }">
        <div class="gallery-author-card rounded-2xl p-4 mb-4">
          <div class="flex items-center justify-between gap-3">
            <button
              type="button"
              class="gallery-author-card__identity flex items-center gap-3 min-w-0"
              @click.stop="openUserProfile(post.author_id)"
            >
              <div class="gallery-author-card__avatar w-11 h-11 rounded-2xl flex items-center justify-center text-white font-bold shrink-0">
                {{ post.author_name ? post.author_name.charAt(0).toUpperCase() : '修' }}
              </div>
              <div class="min-w-0 text-left">
                <div class="gallery-author-card__name text-sm font-semibold truncate">
                  {{ post.author_name || t('social.anonymous_user') }}
                </div>
                <div v-if="post.author_username" class="gallery-author-card__meta text-xs truncate">
                  @{{ post.author_username }}
                </div>
              </div>
            </button>

            <a-button
              v-if="post.author_id"
              type="primary"
              class="gallery-author-card__follow-btn"
              :loading="followLoadingUserId === post.author_id"
              @click.stop="handleAuthorFollow(post)"
            >
              {{ post.is_following_author ? t('social.unfollow') : t('social.follow') }}
            </a-button>
          </div>
        </div>
      </template>
    </GalleryDetailModal>

    <UserProfileModal
      v-model:open="userProfileVisible"
      :user-id="activeProfileUserId"
      @follow-updated="syncFollowStateForAuthor($event.userId, $event.isFollowing)"
    />
</template>

<style>
/* Hide scrollbar for horizontal scrolling areas */
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}
.scrollbar-hide {
  -ms-overflow-style: none;  /* IE and Edge */
  scrollbar-width: none;  /* Firefox */
}

/* Mobile full screen modal override */
.mobile-full-modal {
  padding: 0 !important;
  margin: 0 !important;
}
.mobile-full-modal .ant-modal {
  top: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  height: 100vh !important;
  max-width: 100% !important;
}
.mobile-full-modal .ant-modal-content {
  border-radius: 0 !important;
  height: 100vh !important;
  overflow-y: auto !important;
  background-color: var(--detail-modal-shell-bg, var(--theme-card-strong-bg)) !important;
}
.mobile-full-modal .ant-modal-body {
  height: 100% !important;
}

/* Safe area support for iOS */
@supports (padding-bottom: env(safe-area-inset-bottom)) {
  .safe-area-bottom {
    padding-bottom: calc(0.75rem + env(safe-area-inset-bottom));
  }
}
</style>

<style scoped>
.gallery-media-pane {
  background: var(--theme-card-strong-bg);
}

.gallery-author-mobile__identity,
.gallery-author-card__identity {
  background: transparent;
  border: none;
  padding: 0;
}

.gallery-author-mobile__name,
.gallery-author-card__name {
  color: var(--theme-text-primary);
}

.gallery-author-card {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
}

.gallery-author-card__avatar {
  background: linear-gradient(135deg, #06b6d4, #4f46e5);
  box-shadow: 0 10px 20px rgba(79, 70, 229, 0.24);
}

.gallery-author-card__meta {
  color: var(--theme-text-secondary);
}

.gallery-author-mobile__follow-btn,
.gallery-author-card__follow-btn {
  background: linear-gradient(90deg, #2563eb, #4f46e5) !important;
  border: none !important;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}
</style>
