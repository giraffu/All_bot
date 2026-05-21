<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { Heart, ThumbsDown, Wand2, Flame, Clock, MessageCircle } from 'lucide-vue-next'
import { Waterfall } from 'vue-waterfall-plugin-next'
import 'vue-waterfall-plugin-next/dist/style.css'
import api from '@/api'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import {
  useTemplateApplyStore
} from '@/stores/templateApply'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { getFileUrl } from '@/utils/mediaFiles'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import {
  formatGalleryTag,
  resolveGalleryTaskTypeLabel
} from '@/utils/galleryPresentation'
import { useGalleryConfig } from '@/composables/useGalleryConfig'
import { useGalleryFilters } from '@/composables/useGalleryFilters'
import { useViewport } from '@/composables/useViewport'
import LazyVideo from '@/components/LazyVideo.vue'
import OverflowScrollRail from '@/components/OverflowScrollRail.vue'
import DetailDesktopActions from '@/components/DetailDesktopActions.vue'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import HeaderPaginationBar from '@/components/HeaderPaginationBar.vue'
import ListStateBlock from '@/components/ListStateBlock.vue'
import SegmentedTabsRail from '@/components/SegmentedTabsRail.vue'
import StickyHeaderSection from '@/components/StickyHeaderSection.vue'
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useGalleryTemplateApply } from '@/composables/useGalleryTemplateApply'
import { useRenderSettling } from '@/composables/useRenderSettling'

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
  author_name?: string
  src?: string
  cardIsVideo?: boolean
  cardPoster?: string
  imgLoaded?: boolean
}



const { t } = useI18n()
const { isMobile } = useViewport()
const templateApplyStore = useTemplateApplyStore()
const layoutContentRef = useMainLayoutContentRef()
const { saveApplyContext } = useGalleryApplyContext()

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
        lora_model: loraModel.value === 'all' ? undefined : loraModel.value,
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
const { applying, handleApply, cancelPendingApply } = useGalleryTemplateApply<Post>({
  currentPost,
  detailVisible,
  templateApplyStore,
  saveApplyContext,
  t,
})

const currentDetailMedia = useCurrentDetailMedia(currentPost, {
  normalizeGalleryThumbnail: true,
})

const formatTag = (tag: string) => formatGalleryTag(tag, t)

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
  isLoraTaskType,
  currentLoraModels,
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
  <div class="gallery-container text-slate-200">
    <!-- Header Controls -->
    <StickyHeaderSection class-name="-mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
      <div class="flex flex-col xl:flex-row justify-between xl:items-center gap-4">
        <!-- Task Types -->
        <SegmentedTabsRail
          :items="[{ id: 'all', name: $t('gallery.tabs.all') }, ...allowedTypes.map((tab) => ({ id: tab.id, name: resolveTaskTypeLabel(tab.id) }))]"
          :selected-id="taskType"
          container-class="w-full xl:w-auto shrink-0"
          @select="handleTaskTypeChange"
        />
        
        <OverflowScrollRail
          container-class="w-full xl:w-auto shrink-0 rounded-2xl border border-slate-700/50 bg-slate-950/55 px-2 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]"
          content-class="flex items-center gap-3"
        >
          <!-- Time Range -->
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
          
          <!-- Sort By -->
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
      
      <!-- Secondary Filter for LoRA Models -->
      <OverflowScrollRail
        v-if="isLoraTaskType"
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
            {{ $t('gallery.all_models') }}
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

    <!-- Masonry Grid -->
    <Waterfall 
      :list="posts" 
      rowKey="id"
      :breakpoints="breakpoints" 
      :gutter="isMobile ? 12 : 24" 
      :animationDuration="400"
      backgroundColor="transparent"
      @afterRender="handleWaterfallAfterRender"
      :hasAroundGutter="false"
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
              <div class="flex flex-wrap gap-1.5 mb-8">
                <span v-for="tag in post.tags.slice(0, 4)" :key="tag" class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md">
                  {{ formatTag(tag) }}
                </span>
                <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
              </div>
            </div>
          </template>
          <template #bottom>
            <div class="absolute bottom-0 left-0 right-0 p-3 bg-black/60 backdrop-blur-md border-t border-white/10 flex justify-between items-center z-10 translate-y-0">
              <div class="flex items-center space-x-3">
                <div class="flex items-center text-slate-300 hover:text-pink-400 transition-colors" @click.stop="handleInteract(post, 'like')">
                  <Heart :size="14" class="mr-1" :class="{'fill-pink-500 text-pink-500': post.has_liked}" />
                  <span class="text-xs font-medium">{{ post.likes_count }}</span>
                </div>
                <div class="flex items-center text-slate-300 hover:text-slate-100 transition-colors" @click.stop="handleInteract(post, 'dislike')">
                  <ThumbsDown :size="14" class="mr-1" :class="{'fill-slate-400 text-slate-400': post.has_disliked}" />
                  <span class="text-xs font-medium">{{ post.dislikes_count }}</span>
                </div>
                <div class="flex items-center text-slate-300 hover:text-blue-400 transition-colors" @click.stop="openDetail(post)">
                  <MessageCircle :size="14" class="mr-1" />
                  <span class="text-xs font-medium">{{ post.comments_count }}</span>
                </div>
              </div>
              <div class="flex items-center text-indigo-300">
                <Wand2 :size="14" class="mr-1" />
                <span class="text-xs font-medium">{{ post.applied_count }}</span>
              </div>
            </div>
          </template>
        </GalleryMediaCard>
      </template>
    </Waterfall>
    
    <ListStateBlock
      :loading="loading"
      :empty="posts.length === 0"
      :empty-text="$t('gallery.no_posts')"
    />

    <GalleryDetailModal
      v-model:open="detailVisible"
      v-model:comment-input-open="showCommentInput"
      v-model:new-comment="newComment"
      :current-post="currentPost"
      :current-detail-media="currentDetailMedia"
      :has-prev="hasPrev"
      :has-next="hasNext"
      :is-mobile="isMobile"
      :title="$t('gallery.modal.title')"
      :no-tags-text="t('my_notes.no_tags')"
      :format-tag="formatTag"
      :comments="comments"
      :comments-loading="commentsLoading"
      :comments-error="commentsError"
      :comments-page="commentsPage"
      :comments-total="commentsTotal"
      :comments-has-more="commentsHasMore"
      :submitting-comment="submittingComment"
      @prev="goPrev"
      @next="goNext"
      @retry-initial="currentPost && loadComments(currentPost.id, { page: 1, append: false })"
      @retry-more="loadMoreComments"
      @load-more="loadMoreComments"
      @submit-comment="submitComment"
    >
      <template #mobile-header="{ post }">
        <div class="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-indigo-500 flex items-center justify-center text-white font-bold text-xs">
          {{ post.author_name ? post.author_name.charAt(0).toUpperCase() : '修' }}
        </div>
        <span class="text-slate-200 font-medium text-sm">{{ post.author_name || '匿名修士' }}</span>
      </template>

      <template #before-comments="{ post, openCommentInput }">
        <DetailDesktopActions top-class="space-x-2 mb-4 pt-4" bottom-class="mt-8">
          <template #top>
            <div class="flex space-x-2">
              <button @click="handleInteract(post, 'like')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <Heart :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="post.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'" />
                <span class="font-medium" :class="post.has_liked ? 'text-pink-400' : 'text-slate-300'">{{ post.likes_count }}</span>
              </button>
              <button @click="handleInteract(post, 'dislike')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <ThumbsDown :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="post.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'" />
                <span class="font-medium" :class="post.has_disliked ? 'text-slate-400' : 'text-slate-300'">{{ post.dislikes_count }}</span>
              </button>
              <button @click="openCommentInput()" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <MessageCircle :size="20" class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400" />
                <span class="font-medium text-slate-300">{{ post.comments_count }}</span>
              </button>
            </div>
          </template>
          <template #bottom>
            <button
              @click="handleApply"
              :disabled="applying"
              class="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-bold text-lg shadow-[0_0_20px_rgba(56,189,248,0.4)] transition-all transform hover:scale-[1.02] flex items-center justify-center relative overflow-hidden group"
            >
              <div class="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
              <Wand2 v-if="!applying" :size="22" class="mr-2 relative z-10" />
              <div v-else class="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2 relative z-10"></div>
              <span class="relative z-10">{{ applying ? '...' : $t('gallery.modal.apply_btn') }}</span>
            </button>
            <p class="text-center text-xs text-slate-500 mt-3">{{ $t('gallery.modal.apply_hint') }}</p>
          </template>
        </DetailDesktopActions>
      </template>

      <template #mobile-left="{ post, openCommentInput }">
        <button @click="handleInteract(post, 'like')" class="flex items-center gap-1.5 transition-all" :class="post.has_liked ? 'text-pink-500' : 'text-slate-300'">
          <Heart :size="22" :class="{'fill-pink-500': post.has_liked}" />
          <span class="text-sm font-medium">{{ post.likes_count }}</span>
        </button>
        <button @click="handleInteract(post, 'dislike')" class="flex items-center gap-1.5 transition-all" :class="post.has_disliked ? 'text-slate-400' : 'text-slate-300'">
          <ThumbsDown :size="22" :class="{'fill-slate-400': post.has_disliked}" />
          <span class="text-sm font-medium">{{ post.dislikes_count }}</span>
        </button>
        <button @click="openCommentInput()" class="flex items-center gap-1.5 transition-all text-slate-300">
          <MessageCircle :size="22" />
          <span class="text-sm font-medium">{{ post.comments_count }}</span>
        </button>
      </template>

      <template #mobile-right>
        <button
          @click="handleApply"
          :disabled="applying"
          class="px-6 py-2 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm shadow-lg flex items-center"
        >
          <Wand2 v-if="!applying" :size="16" class="mr-1.5" />
          <div v-else class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1.5"></div>
          {{ applying ? '...' : $t('gallery.modal.apply_btn') }}
        </button>
      </template>
    </GalleryDetailModal>
  </div>
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
