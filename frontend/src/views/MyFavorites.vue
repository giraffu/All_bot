<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  Copy,
  Heart,
  MessageCircle,
  ThumbsDown,
  Trash2,
  Wand2,
} from 'lucide-vue-next'
import api from '@/api'
import MySubmissionsPanel from '@/components/MySubmissionsPanel.vue'
import DetailDesktopActions from '@/components/DetailDesktopActions.vue'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import HeaderPaginationBar from '@/components/HeaderPaginationBar.vue'
import ListStateBlock from '@/components/ListStateBlock.vue'
import SegmentedTabsRail from '@/components/SegmentedTabsRail.vue'
import StickyHeaderSection from '@/components/StickyHeaderSection.vue'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { useViewport } from '@/composables/useViewport'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useLegacyTemplateApply } from '@/composables/useLegacyTemplateApply'
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
const { saveApplyContext } = useGalleryApplyContext()

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
const { copyPrompt } = usePostPromptCopy(t)
const { applying, applyFromCurrentPost } = useLegacyTemplateApply<Post>({
  currentPost,
  closeDetail: () => {
    detailVisible.value = false
  },
  saveApplyContext,
  t
})

const formatTag = (tag: string) => formatGalleryTag(tag, t)

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

const handleApply = async () => {
  await applyFromCurrentPost({
    endpoint: (post) => (
      filterType.value === 'favorite'
        ? `/users/history/${post.task_id}/apply-context`
        : `/gallery/posts/${post.id}/apply-context`
    ),
    source: filterType.value === 'favorite' ? 'favorites' : 'gallery',
    entryEntityId: (post) => post.id,
    ignoreNotFound: true
  })
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
  <div class="gallery-container text-slate-200">
    <StickyHeaderSection class-name="-mx-3 px-3 md:-mx-6 md:px-6 pb-2">
      <!-- Top Filter Tabs -->
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

    <MySubmissionsPanel v-if="isSubmissionTab" :task-type="selectedTaskType" />

    <!-- Masonry Grid -->
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
            <div class="flex flex-wrap gap-1.5 mb-8">
              <span v-for="tag in post.tags.slice(0, 4)" :key="tag" class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md">
                {{ formatTag(tag) }}
              </span>
              <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
            </div>
          </div>
        </template>
        <template #bottom>
          <div v-if="filterType !== 'favorite'" class="absolute bottom-0 left-0 right-0 p-3 bg-black/60 backdrop-blur-md border-t border-white/10 flex justify-between items-center z-10 translate-y-0">
            <div class="flex items-center space-x-3">
              <div class="flex items-center text-slate-300 hover:text-pink-400 transition-colors" @click.stop="handleInteract(post, 'like')">
                <Heart :size="14" class="mr-1" :class="{'fill-pink-500 text-pink-500': post.has_liked}" />
                <span class="text-xs font-medium">{{ post.likes_count }}</span>
              </div>
              <div class="flex items-center text-slate-300 hover:text-slate-100 transition-colors" @click.stop="handleInteract(post, 'dislike')">
                <ThumbsDown :size="14" class="mr-1" :class="{'fill-slate-400 text-slate-400': post.has_disliked}" />
                <span class="text-xs font-medium">{{ post.dislikes_count }}</span>
              </div>
            </div>
            <div class="flex items-center text-indigo-300">
              <Wand2 :size="14" class="mr-1" />
              <span class="text-xs font-medium">{{ post.applied_count }}</span>
            </div>
          </div>
        </template>
      </GalleryMediaCard>
    </div>
    
    <ListStateBlock
      v-if="!isSubmissionTab"
      :loading="loading"
      :empty="posts.length === 0"
      :empty-text="emptyStateText"
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
      :title="t('gallery.modal.title')"
      :no-tags-text="t('my_notes.no_tags')"
      :format-tag="formatTag"
      :comments="comments"
      :comments-loading="commentsLoading"
      :comments-error="commentsError"
      :comments-page="commentsPage"
      :comments-total="commentsTotal"
      :comments-has-more="commentsHasMore"
      :submitting-comment="submittingComment"
      info-content-class="p-4 lg:p-6 flex-1 flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent"
      desktop-close-button-class="z-10"
      @prev="goPrev"
      @next="goNext"
      @retry-initial="currentPost && loadComments(currentPost.id, { page: 1, append: false })"
      @retry-more="loadMoreComments"
      @load-more="loadMoreComments"
      @submit-comment="submitComment"
    >
      <template #before-comments="{ post, openCommentInput }">
        <div
          v-if="filterType !== 'favorite'"
          class="hidden lg:flex space-x-2 mb-4 pt-4 border-t border-slate-700 lg:border-slate-400/30"
        >
          <button @click="handleInteract(post, 'like')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
            <Heart :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="post.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'" />
            <span class="font-medium" :class="post.has_liked ? 'text-pink-400' : 'text-slate-300'">{{ post.likes_count }}</span>
          </button>
          <button @click="handleInteract(post, 'dislike')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
            <ThumbsDown :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="post.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'" />
            <span class="font-medium" :class="post.has_disliked ? 'text-slate-400' : 'text-slate-300'">{{ post.dislikes_count }}</span>
          </button>
          <button @click="openCommentInput()" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400"><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/></svg>
            <span class="font-medium text-slate-300">{{ post.comments_count || 0 }}</span>
          </button>
        </div>
        <div
          v-else
          class="hidden lg:flex space-x-2 mb-4 pt-4 border-t border-slate-700 lg:border-slate-400/30"
        >
          <button @click="handleUnfavorite(post)" class="flex-1 py-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all flex items-center justify-center group">
            <Trash2 :size="18" class="mr-2 transition-transform group-hover:scale-110" />
            <span class="font-medium">{{ t('my_notes.unfavorite_button') }}</span>
          </button>
          <button @click="openCommentInput()" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400"><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/></svg>
            <span class="font-medium text-slate-300">{{ post.comments_count || 0 }}</span>
          </button>
        </div>
      </template>

      <template #after-comments="{ post }">
        <DetailDesktopActions container-class="mt-auto" bottom-class="space-y-4 pt-4">
          <template #bottom>
            <button
              v-if="post.prompt?.trim()"
              @click="copyPrompt(post)"
              class="w-full py-3 rounded-xl bg-slate-500 hover:bg-slate-400 text-white font-medium shadow-sm transition-all flex items-center justify-center border border-slate-400"
            >
              <Copy :size="18" class="mr-2" />
              {{ t('my_posts.copy_prompt') }}
            </button>
            <button
              @click="handleApply"
              :disabled="applying"
              class="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-bold text-lg shadow-[0_0_20px_rgba(56,189,248,0.4)] transition-all transform hover:scale-[1.02] flex items-center justify-center relative overflow-hidden group"
            >
              <div class="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
              <Wand2 v-if="!applying" :size="22" class="mr-2 relative z-10" />
              <div v-else class="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2 relative z-10"></div>
              <span class="relative z-10">{{ applying ? t('my_notes.applying_template') : t('gallery.modal.apply_btn') }}</span>
            </button>
            <p class="text-center text-xs text-slate-500 mt-3">{{ t('gallery.modal.apply_hint') }}</p>
          </template>
        </DetailDesktopActions>
      </template>

      <template #mobile-left="{ post, openCommentInput }">
        <template v-if="filterType !== 'favorite'">
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
            <span class="text-sm font-medium">{{ post.comments_count || 0 }}</span>
          </button>
        </template>
        <template v-else>
          <button @click="handleUnfavorite(post)" class="flex items-center gap-1.5 transition-all text-red-400">
            <Trash2 :size="22" />
            <span class="text-sm font-medium">{{ t('my_notes.unfavorite_button') }}</span>
          </button>
          <button @click="openCommentInput()" class="flex items-center gap-1.5 transition-all text-slate-300">
            <MessageCircle :size="22" />
            <span class="text-sm font-medium">{{ post.comments_count || 0 }}</span>
          </button>
        </template>
        <button v-if="post.prompt?.trim()" @click="copyPrompt(post)" class="flex items-center gap-1.5 transition-all text-slate-300">
          <Copy :size="22" />
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
          {{ applying ? '...' : t('gallery.modal.apply_btn') }}
        </button>
      </template>
    </GalleryDetailModal>
  </div>
</template>
