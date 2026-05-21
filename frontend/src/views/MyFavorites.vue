<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  Compass,
  Copy,
  Heart,
  Image as ImageIcon,
  Play,
  ThumbsDown,
  Trash2,
  Video,
  Wand2,
} from 'lucide-vue-next'
import api from '@/api'
import dayjs from 'dayjs'
import MySubmissionsPanel from '@/components/MySubmissionsPanel.vue'
import OverflowScrollRail from '@/components/OverflowScrollRail.vue'
import PagedNavigation from '@/components/PagedNavigation.vue'
import DetailMediaPreview from '@/components/DetailMediaPreview.vue'
import DetailModalShell from '@/components/DetailModalShell.vue'
import DetailCommentsSection from '@/components/DetailCommentsSection.vue'
import DetailDesktopActions from '@/components/DetailDesktopActions.vue'
import DetailMobileBottomBar from '@/components/DetailMobileBottomBar.vue'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { useViewport } from '@/composables/useViewport'
import { copyTextWithFallback } from '@/utils/clipboard'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView, resolveMediaDetailView } from '@/utils/mediaCardView'
import {
  buildLegacyTemplateRoute,
  resolveTemplateApplyEntry
} from '@/utils/templateApplyEntry'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'

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

type FilterTab = 'favorite' | 'like' | 'apply' | 'submissions'
interface TaskTypeOption {
  id: string
  name: string
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const layoutContentRef = useMainLayoutContentRef()
const { saveApplyContext } = useGalleryApplyContext()

function normalizeFilterType(tabValue: unknown): FilterTab {
  const value = typeof tabValue === 'string' ? tabValue : ''
  if (value === 'like' || value === 'apply' || value === 'submissions') {
    return value
  }
  return 'favorite'
}

const { isMobile } = useViewport()

const filterType = ref<FilterTab>(normalizeFilterType(route.query.tab))
const selectedTaskType = ref('all')
const allowedTypes = ref<TaskTypeOption[]>([])
let configPromise: Promise<void> | null = null
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
const applying = ref(false)
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

const isSubmissionTab = computed(() => filterType.value === 'submissions')
const filterTabs = computed(() => [
  { id: 'favorite' as const, name: t('my_notes.tabs.favorite') },
  { id: 'like' as const, name: t('my_notes.tabs.like') },
  { id: 'apply' as const, name: t('my_notes.tabs.apply') },
  { id: 'submissions' as const, name: t('my_notes.tabs.submissions') },
])
const taskTypeTabs = computed(() => [
  { id: 'all', name: t('gallery.tabs.all') },
  ...allowedTypes.value,
])
const emptyStateText = computed(() => {
  if (filterType.value === 'like') return t('my_notes.empty_like')
  if (filterType.value === 'apply') return t('my_notes.empty_apply')
  return t('my_notes.empty_favorite')
})
const currentDetailMedia = computed(() => {
  if (!currentPost.value) {
    return null
  }

  return resolveMediaDetailView(currentPost.value)
})

const resolveTaskTypeLabel = (taskTypeId: string) => {
  if (taskTypeId === 'all') {
    return t('gallery.tabs.all')
  }

  const translationKey = taskTypeId
    .replace('i2i_pro', 'face_swap')
    .replace('edit', 'custom_edit')
    .replace('img2img_lora', 'img2img')
    .replace('custom_video', 'custom_video')
    .replace('video_lora', 'img2video')
    .replace('ltx_video', 'high_res_video')

  return t(`gallery.tabs.${translationKey}`)
}

const formatTag = (tag: string) => {
  if (tag.startsWith('#task.')) {
    const key = tag.substring(1)
    return '#' + t(key)
  }
  if (tag.startsWith('task.')) {
    return t(tag)
  }
  return tag
}

const loadConfig = async () => {
  if (configPromise) return configPromise

  configPromise = (async () => {
    try {
      const res = await api.get('/gallery/config')
      allowedTypes.value = res.data.allowed_types || []
    } catch (error) {
      console.error('Failed to load note filters config:', error)
    } finally {
      configPromise = null
    }
  })()

  return configPromise
}

const scrollToTop = async () => {
  await nextTick()
  layoutContentRef.value?.scrollTo({
    top: 0,
    behavior: 'smooth'
  })
}
const prefetchNextPage = () => {
  if (isSubmissionTab.value) {
    return
  }
  prefetchBrowserNextPage()
}

const goToPage = async (pageNumber: number) => {
  if (isSubmissionTab.value) {
    return
  }

  const changed = await browserGoToPage(pageNumber)
  if (!changed) return

  await scrollToTop()
  prefetchNextPage()
}
const loadPosts = async (reset = false) => {
  if (isSubmissionTab.value) return
  await loadBrowserPosts(reset)
}

const handleFilterTypeChange = (type: string) => {
  const nextType = normalizeFilterType(type)
  if (nextType === filterType.value) return
  filterType.value = nextType
}

const handleTaskTypeChange = (taskType: string) => {
  if (taskType === selectedTaskType.value) return
  selectedTaskType.value = taskType
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

const copyPrompt = (post: Post) => {
  const prompt = post.prompt?.trim()
  if (!prompt) {
    message.warning(t('my_notes.prompt_empty'))
    return
  }

  void copyTextWithFallback(prompt).then((successful) => {
    if (successful) {
      message.success(t('my_notes.prompt_copied'))
    } else {
      message.error(t('my_notes.copy_failed'))
    }
  })
}

const handleApply = async () => {
  if (!currentPost.value || applying.value) return
  applying.value = true
  
  try {
    const applyEndpoint = filterType.value === 'favorite'
      ? `/users/history/${currentPost.value.task_id}/apply-context`
      : `/gallery/posts/${currentPost.value.id}/apply-context`
    const res = await api.get(applyEndpoint)
    const rawContext = res.data
    const resolvedEntry = resolveTemplateApplyEntry({
      rawContext,
      source: filterType.value === 'favorite' ? 'favorites' : 'gallery',
      entryEntityId: currentPost.value.id,
      preferredMode: 'legacy'
    })

    if (resolvedEntry.status === 'invalid') {
      message.error(t('my_notes.template_load_failed'))
      return
    }

    if (resolvedEntry.status === 'unknown_task_type') {
      message.warning(t('template_apply.unknown_task_type'))
      return
    }

    detailVisible.value = false
    saveApplyContext(rawContext)
    message.success(t('my_notes.template_loaded_with_upload_hint'))
    void router.push(buildLegacyTemplateRoute(resolvedEntry, t))
    
  } catch (error: any) {
    if (error.response?.status === 404) {
      return
    }
    console.error(error)
    message.error(t('my_notes.template_load_failed'))
  } finally {
    applying.value = false
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
})

watch(
  () => route.query.tab,
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
    const currentTab = typeof route.query.tab === 'string' ? route.query.tab : undefined
    if (currentTab !== nextType) {
      void router.replace({
        name: 'MyFavorites',
        query: {
          ...route.query,
          tab: nextType,
        },
      })
    }

    if (nextType === 'submissions') {
      clearBrowserState()
      return
    }

    void loadPosts(true)
  },
  { immediate: true },
)

watch(selectedTaskType, () => {
  if (isSubmissionTab.value) {
    return
  }
  void loadPosts(true)
})

watch(isMobile, (nextIsMobile, previousIsMobile) => {
  if (nextIsMobile === previousIsMobile) {
    return
  }
  if (filterType.value === 'favorite') {
    void loadPosts(true)
  }
})
</script>

<template>
  <div class="gallery-container text-slate-200">
    <div class="sticky top-0 z-40 -mx-3 px-3 md:-mx-6 md:px-6 pt-3 pb-2 mb-3">
      <!-- Top Filter Tabs -->
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <OverflowScrollRail
          container-class="pb-2 md:pb-0"
          content-class="flex items-center space-x-2"
        >
          <button 
            v-for="ft in filterTabs" 
            :key="ft.id"
            @click="handleFilterTypeChange(ft.id)"
            class="px-4 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap"
            :class="filterType === ft.id ? 'bg-cyan-500 text-white shadow-[0_0_10px_rgba(56,189,248,0.4)]' : 'bg-slate-500 text-slate-400 hover:bg-slate-500 hover:text-slate-200'"
          >
            {{ ft.name }}
          </button>
        </OverflowScrollRail>
      </div>

      <OverflowScrollRail
        v-if="taskTypeTabs.length > 1"
        container-class="mt-3 rounded-2xl border border-slate-700/50 bg-slate-950/55 px-2 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]"
        content-class="flex gap-1 bg-slate-500/50 p-1 rounded-xl border border-slate-400/50"
      >
        <button
          v-for="tab in taskTypeTabs"
          :key="tab.id"
          @click="handleTaskTypeChange(tab.id)"
          class="px-3 py-1 sm:px-4 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm whitespace-nowrap shrink-0"
          :class="selectedTaskType === tab.id ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_10px_rgba(56,189,248,0.2)]' : 'hover:text-cyan-300 text-slate-400'"
        >
          {{ resolveTaskTypeLabel(tab.id) }}
        </button>
      </OverflowScrollRail>

      <div
        v-if="!isSubmissionTab"
        class="mt-3 flex justify-center"
      >
        <div class="rounded-2xl border border-slate-700/50 bg-slate-950/55 px-3 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]">
          <PagedNavigation
            :current-page="currentPage"
            :total-pages="totalPages"
            :disabled="loading"
            :compact="isMobile"
            @change="goToPage"
          />
        </div>
      </div>
    </div>

    <MySubmissionsPanel v-if="isSubmissionTab" :task-type="selectedTaskType" />

    <!-- Masonry Grid -->
    <div v-else class="columns-2 sm:columns-3 md:columns-4 lg:columns-5 gap-3 sm:gap-6">
      <div 
        v-for="post in posts" 
        :key="post.id"
        class="mb-3 sm:mb-6 break-inside-avoid rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-400/50 bg-slate-500/40 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
        @click="openDetail(post)"
      >
        <!-- Media -->
        <div class="relative w-full overflow-hidden bg-slate-500 aspect-auto min-h-[100px]"
             :style="post.width && post.height ? { aspectRatio: `${post.width}/${post.height}` } : { aspectRatio: '1/1' }">
          <img 
            v-if="post.src"
            :src="post.src" 
            @error="handleImageError($event, post)"
            class="w-full h-full object-cover transition-opacity duration-300 absolute inset-0" 
            loading="lazy" 
          />
          <div v-else class="absolute inset-0 flex items-center justify-center text-slate-400">
            <ImageIcon v-if="!post.cardIsVideo" :size="24" />
            <Video v-else :size="24" />
          </div>
          
          <!-- Type Badge -->
          <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10">
            <ImageIcon v-if="!post.cardIsVideo" :size="14" class="text-cyan-400" />
            <Video v-else :size="14" class="text-indigo-400" />
          </div>
          
          <!-- Play Icon Overlay for Videos -->
          <div v-if="post.cardIsVideo" class="absolute inset-0 flex items-center justify-center pointer-events-none opacity-80 group-hover:opacity-0 transition-opacity duration-300">
            <div class="w-12 h-12 bg-black/50 backdrop-blur-md rounded-full flex items-center justify-center border border-white/20 shadow-lg">
              <Play :size="24" class="text-white ml-1" />
            </div>
          </div>
          
          <!-- Tags Overlay on Hover -->
          <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-between p-4">
            <div class="flex flex-wrap gap-1.5 mb-8">
              <span v-for="tag in post.tags.slice(0, 4)" :key="tag" class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md">
                {{ formatTag(tag) }}
              </span>
              <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
            </div>
          </div>
        </div>
        
        <!-- Stats Bar -->
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
      </div>
    </div>
    
    <!-- Loading State -->
    <div v-if="!isSubmissionTab && loading" class="py-8 text-center">
      <div class="inline-block w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
    </div>
    
    <!-- Empty State -->
    <div v-if="!isSubmissionTab && !loading && posts.length === 0" class="py-20 text-center text-slate-500">
      <Compass :size="48" class="mx-auto mb-4 opacity-20" />
      <p>{{ emptyStateText }}</p>
    </div>

    <!-- Detail Modal -->
    <a-modal
      v-model:open="detailVisible"
      :footer="null"
      :closable="false"
      :width="isMobile ? '100%' : '90%'"
      :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { maxWidth: '1000px', top: '20px' }"
      :wrapClassName="isMobile ? 'mobile-full-modal' : ''"
      class="gallery-detail-modal"
      :bodyStyle="isMobile ? { padding: 0, height: '100%', backgroundColor: '#0f172a' } : { padding: 0, backgroundColor: 'transparent' }"
      destroyOnClose
    >
      <DetailModalShell
        v-if="currentPost"
        info-content-class="p-4 lg:p-6 flex-1 flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent"
        desktop-close-button-class="z-10"
        @close="detailVisible = false"
      >
        <template #mobile-header>
          <span class="text-slate-200 font-medium text-sm">{{ t('gallery.modal.title') }}</span>
        </template>

        <template #media>
          <DetailMediaPreview
            :media="currentDetailMedia"
            :has-prev="hasPrev"
            :has-next="hasNext"
            @prev="goPrev"
            @next="goNext"
          />
        </template>

        <template #info>
            <!-- Desktop Title -->
            <h3 class="hidden lg:flex text-xl font-bold text-slate-100 mb-2 items-center">
              <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">{{ t('gallery.modal.title') }}</span>
            </h3>
            
            <!-- Tags & Time Area -->
            <div class="mb-4 lg:mb-6 mt-2 lg:mt-0">
              <div class="flex flex-wrap gap-2 mb-3">
                <span v-for="tag in currentPost.tags" :key="tag" class="text-xs bg-slate-800 lg:bg-slate-500 text-cyan-400 lg:text-cyan-200 border border-slate-700 lg:border-slate-400 px-2.5 py-1 rounded-full">
                  {{ tag.startsWith('#') ? formatTag(tag) : '#' + formatTag(tag) }}
                </span>
                <span v-if="!currentPost.tags || currentPost.tags.length === 0" class="text-sm text-slate-500 lg:text-slate-400">{{ t('my_notes.no_tags') }}</span>
              </div>
              <div class="text-xs text-slate-500 lg:text-slate-400 space-y-1">
                <div v-if="currentPost.created_at">
                  <span>{{ dayjs(currentPost.created_at).format('YYYY-MM-DD HH:mm') }}</span>
                </div>
                <div class="flex space-x-4">
                  <span v-if="currentPost.width">{{ currentPost.width }}x{{ currentPost.height }}</span>
                  <span v-if="currentPost.duration">{{ currentPost.duration }}s</span>
                </div>
              </div>
            </div>
            
            <!-- Desktop Interactions (Hidden on Mobile) -->
            <div class="hidden lg:flex space-x-2 mb-4 pt-4 border-t border-slate-700 lg:border-slate-400/30" v-if="filterType !== 'favorite'">
              <button @click="handleInteract(currentPost, 'like')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <Heart :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'" />
                <span class="font-medium" :class="currentPost.has_liked ? 'text-pink-400' : 'text-slate-300'">{{ currentPost.likes_count }}</span>
              </button>
              <button @click="handleInteract(currentPost, 'dislike')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <ThumbsDown :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'" />
                <span class="font-medium" :class="currentPost.has_disliked ? 'text-slate-400' : 'text-slate-300'">{{ currentPost.dislikes_count }}</span>
              </button>
              <button @click="showCommentInput = true" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400"><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/></svg>
                <span class="font-medium text-slate-300">{{ currentPost.comments_count || 0 }}</span>
              </button>
            </div>
            <div class="hidden lg:flex space-x-2 mb-4 pt-4 border-t border-slate-700 lg:border-slate-400/30" v-if="filterType === 'favorite'">
              <button @click="handleUnfavorite(currentPost)" class="flex-1 py-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all flex items-center justify-center group">
                <Trash2 :size="18" class="mr-2 transition-transform group-hover:scale-110" />
                <span class="font-medium">{{ t('my_notes.unfavorite_button') }}</span>
              </button>
              <button @click="showCommentInput = true" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400"><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/></svg>
                <span class="font-medium text-slate-300">{{ currentPost.comments_count || 0 }}</span>
              </button>
            </div>
            

            <!-- Comments Section -->
            <DetailCommentsSection
              :comments="comments"
              :comments-loading="commentsLoading"
              :comments-error="commentsError"
              :comments-page="commentsPage"
              :comments-total="commentsTotal"
              :comments-has-more="commentsHasMore"
              :is-mobile="isMobile"
              @retry-initial="currentPost && loadComments(currentPost.id, { page: 1, append: false })"
              @retry-more="loadMoreComments"
              @load-more="loadMoreComments"
            />
            <DetailDesktopActions container-class="mt-auto" bottom-class="space-y-4 pt-4">
              <template #bottom>
                <button
                  v-if="currentPost.prompt?.trim()"
                  @click="copyPrompt(currentPost)"
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

        <DetailMobileBottomBar>
          <template #left>
            <template v-if="filterType !== 'favorite'">
              <button @click="handleInteract(currentPost, 'like')" class="flex items-center gap-1.5 transition-all" :class="currentPost.has_liked ? 'text-pink-500' : 'text-slate-300'">
                <Heart :size="22" :class="{'fill-pink-500': currentPost.has_liked}" />
                <span class="text-sm font-medium">{{ currentPost.likes_count }}</span>
              </button>
              <button @click="handleInteract(currentPost, 'dislike')" class="flex items-center gap-1.5 transition-all" :class="currentPost.has_disliked ? 'text-slate-400' : 'text-slate-300'">
                <ThumbsDown :size="22" :class="{'fill-slate-400': currentPost.has_disliked}" />
                <span class="text-sm font-medium">{{ currentPost.dislikes_count }}</span>
              </button>
              <button @click="showCommentInput = true" class="flex items-center gap-1.5 transition-all text-slate-300">
                <MessageCircle :size="22" />
                <span class="text-sm font-medium">{{ currentPost.comments_count || 0 }}</span>
              </button>
            </template>
            <template v-else>
              <button @click="handleUnfavorite(currentPost)" class="flex items-center gap-1.5 transition-all text-red-400">
                <Trash2 :size="22" />
                <span class="text-sm font-medium">{{ t('my_notes.unfavorite_button') }}</span>
              </button>
              <button @click="showCommentInput = true" class="flex items-center gap-1.5 transition-all text-slate-300">
                <MessageCircle :size="22" />
                <span class="text-sm font-medium">{{ currentPost.comments_count || 0 }}</span>
              </button>
            </template>
            <button v-if="currentPost.prompt?.trim()" @click="copyPrompt(currentPost)" class="flex items-center gap-1.5 transition-all text-slate-300">
              <Copy :size="22" />
            </button>
          </template>
          <template #right>
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
        </DetailMobileBottomBar>
      </DetailModalShell>
    </a-modal>
    <!-- Comment Input Modal -->
    <a-modal
      v-model:open="showCommentInput"
      :title="t('gallery.comments.modal_title')"
      :footer="null"
      :destroyOnClose="true"
      :width="isMobile ? '95%' : 500"
      :bodyStyle="{ padding: '24px' }"
      class="comment-modal"
    >
      <div class="flex flex-col gap-4">
        <textarea
          v-model="newComment"
          maxlength="500"
          :placeholder="t('gallery.comments.placeholder')"
          class="w-full h-32 p-3 rounded-xl bg-slate-800 border border-slate-600 text-slate-200 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
        ></textarea>
        <div class="flex justify-between items-center">
          <span class="text-xs text-slate-500">{{ newComment.length }}/500</span>
          <div class="flex gap-3">
            <button 
              @click="showCommentInput = false"
              class="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors text-sm font-medium"
            >
              {{ t('gallery.comments.cancel') }}
            </button>
            <button 
              @click="submitComment"
              :disabled="!newComment.trim() || submittingComment"
              class="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:hover:bg-cyan-600 text-white transition-colors text-sm font-medium flex items-center"
            >
              <div v-if="submittingComment" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"></div>
              {{ t('gallery.comments.submit') }}
            </button>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style>
.gallery-detail-modal .ant-modal-content {
  background-color: transparent !important;
  box-shadow: none !important;
}
.gallery-detail-modal .ant-modal-mask {
  background-color: rgba(0, 0, 0, 0.85) !important;
  backdrop-filter: blur(8px);
}
</style>
