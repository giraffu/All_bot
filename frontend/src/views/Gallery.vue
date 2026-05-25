<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
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
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useDetailTemplateApply } from '@/composables/useDetailTemplateApply'
import { useRenderSettling } from '@/composables/useRenderSettling'
import type { GalleryPost as Post } from '@/types/gallery'



const { t } = useI18n()
const { isMobile } = useViewport()
const templateApplyStore = useTemplateApplyStore()
const layoutContentRef = useMainLayoutContentRef()

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
const galleryDetailStandardActions = computed(() => ({
  showDesktopReaction: true,
  showDesktopApply: true,
  showMobileReaction: true,
  showMobileApply: true,
  desktopApplyPlacement: 'before' as const,
  applyLabel: t('gallery.modal.apply_btn'),
  applyLoading: applying.value,
  applyHint: t('gallery.modal.apply_hint'),
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
const taskTypeTabs = computed(() => [
  { id: 'all', name: t('gallery.tabs.all') },
  ...buildGalleryTaskTypeTabs(allowedTypes.value).map((tab) => ({
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
            @select="handleTaskTypeChange"
          />

          <OverflowScrollRail
            container-class="w-full xl:w-auto shrink-0 rounded-2xl border border-slate-700/50 bg-slate-950/55 px-2 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]"
            content-class="flex items-center gap-3"
          >
            <div class="flex bg-slate-500/50 p-1 rounded-xl border border-slate-400/50 shrink-0">
              <button
                v-for="time in [{k:'all', n: $t('gallery.filters.all')}, {k:'today', n: $t('gallery.filters.today')}, {k:'week', n: $t('gallery.filters.this_week')}, {k:'month', n: $t('gallery.filters.this_month')}]"
                :key="time.k"
                @click="handleTimeRangeChange(time.k)"
                class="px-2 py-1 sm:px-3 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm whitespace-nowrap shrink-0"
                :class="timeRange === time.k ? 'bg-indigo-500/20 text-indigo-400 shadow-[0_0_10px_rgba(129,140,248,0.2)]' : 'hover:text-indigo-300 text-slate-400'"
              >
                {{ time.n }}
              </button>
            </div>

            <div class="flex bg-slate-500/50 p-1 rounded-xl border border-slate-400/50 shrink-0">
              <button
                v-for="sort in [{k:'latest', n: $t('gallery.filters.latest'), i: Clock}, {k:'likes', n: $t('gallery.filters.most_liked'), i: Heart}, {k:'applied', n: $t('gallery.filters.most_used'), i: Flame}]"
                :key="sort.k"
                @click="handleSortChange(sort.k)"
                class="px-2 py-1 sm:px-3 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm flex items-center whitespace-nowrap shrink-0"
                :class="sortBy === sort.k ? 'bg-indigo-500/20 text-indigo-400 shadow-[0_0_10px_rgba(129,140,248,0.2)]' : 'hover:text-indigo-300 text-slate-400'"
              >
                <component :is="sort.i" :size="14" class="mr-1.5 hidden sm:block" />
                {{ sort.n }}
              </button>
            </div>
          </OverflowScrollRail>
        </div>

        <OverflowScrollRail
          v-if="hasAddonSubfilters"
          container-class="w-full shrink-0 px-1 rounded-2xl border border-slate-700/50 bg-slate-950/55 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]"
          content-class="flex items-center gap-2"
        >
          <span class="text-xs sm:text-sm text-slate-400 whitespace-nowrap shrink-0">{{ $t('gallery.choose_addon') }}</span>
          <div class="flex gap-2 shrink-0">
            <button
              @click="handleLoraModelChange('all')"
              class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
              :class="loraModel === 'all' ? 'bg-pink-500/20 border-pink-500/50 text-pink-400' : 'border-slate-400 hover:border-slate-500 text-slate-400'"
            >
              {{ $t('gallery.filters.all') }}
            </button>
            <button
              @click="handleLoraModelChange(GALLERY_LORA_MODEL_NONE)"
              class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
              :class="loraModel === GALLERY_LORA_MODEL_NONE ? 'bg-pink-500/20 border-pink-500/50 text-pink-400' : 'border-slate-400 hover:border-slate-500 text-slate-400'"
            >
              {{ $t('gallery.no_addon') }}
            </button>
            <button
              v-for="lora in currentLoraModels"
              :key="lora.id"
              @click="handleLoraModelChange(lora.id)"
              class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
              :class="loraModel === lora.id ? 'bg-pink-500/20 border-pink-500/50 text-pink-400' : 'border-slate-400 hover:border-slate-500 text-slate-400'"
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
        <div class="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-indigo-500 flex items-center justify-center text-white font-bold text-xs">
          {{ post.author_name ? post.author_name.charAt(0).toUpperCase() : '修' }}
        </div>
        <span class="text-slate-200 font-medium text-sm">{{ post.author_name || '匿名修士' }}</span>
      </template>
    </GalleryDetailModal>
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
  background-color: #0f172a !important;
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
