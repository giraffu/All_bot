<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { Heart, ThumbsDown, Wand2, Play, Image as ImageIcon, Video, Flame, Clock, Compass, ChevronLeft, ChevronRight, MessageCircle } from 'lucide-vue-next'
import { Waterfall } from 'vue-waterfall-plugin-next'
import 'vue-waterfall-plugin-next/dist/style.css'
import api from '@/api'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import {
  confirmTemplateApplyClose,
  useTemplateApplyStore
} from '@/stores/templateApply'
import { normalizeGalleryThumbnailPath } from '@/utils/galleryThumbnail'
import {
  buildLegacyTemplateRoute,
  resolveTemplateApplyEntry
} from '@/utils/templateApplyEntry'
import dayjs from 'dayjs'
import { useViewport } from '@/composables/useViewport'
import LazyVideo from '@/components/LazyVideo.vue'
import OverflowScrollRail from '@/components/OverflowScrollRail.vue'
import PagedNavigation from '@/components/PagedNavigation.vue'

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
  imgLoaded?: boolean
}



const router = useRouter()
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

const posts = ref<Post[]>([])
const loading = ref(false)
const currentPage = ref(1)
const pageCache = ref<Record<number, Post[]>>({})
const total = ref(0)
const totalPages = ref(0)
const pageSize = computed(() => (isMobile.value ? 10 : 20))

const mediaType = ref('all')
const taskType = ref('all')
const loraModel = ref('all')
const sortBy = ref('latest')
const timeRange = ref('all')

const allowedTypes = ref<{id: string, name: string}[]>([])
const videoLoraModels = ref<{id: string, name: string}[]>([])
const img2imgLoraModels = ref<{id: string, name: string}[]>([])

const currentLoraModels = computed(() => {
  if (taskType.value === 'img2img_lora') return img2imgLoraModels.value
  return videoLoraModels.value
})

const detailVisible = ref(false)
const currentPost = ref<Post | null>(null)
let applyRequestToken = 0
let pendingApplyAbortController: AbortController | null = null
let isGalleryUnmounted = false

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
const interactingPosts = ref<Record<number, boolean>>({})
const pendingPages = new Set<number>()

const currentIndex = computed(() => {
  if (!currentPost.value) return -1
  return posts.value.findIndex(p => p.id === currentPost.value?.id)
})

const hasPrev = computed(() => currentIndex.value > 0 || currentPage.value > 1)
const hasNext = computed(() => currentIndex.value >= 0 && (
  currentIndex.value < posts.value.length - 1 || currentPage.value < totalPages.value
))

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

const isVideoFile = (path: string, mediaType?: string) => {
  if (mediaType) {
    return mediaType === 'video'
  }
  if (!path) return false
  const lowerPath = path.toLowerCase()
  return lowerPath.endsWith('.mp4') || 
         lowerPath.endsWith('.mov') || 
         lowerPath.endsWith('.webm') || 
         lowerPath.endsWith('.mkv') ||
         lowerPath.endsWith('.avi')
}

const getFileUrl = (path: string, postId?: number) => {
  if (!path) return ''
  let url = path
  
  if (!path.startsWith('http')) {
    const storageUrl = import.meta.env.VITE_STORAGE_URL || ''
    // Ensure we don't double slash if storageUrl has a trailing slash
    const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl
    
    if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
      // If the path has no slash, it's a direct filename from ComfyUI worker in comfyui-temp
      if (!path.includes('/')) {
        url = `${base}/comfyui-temp/${path}`
      } else {
        // Otherwise, it's a structured path like 12345/output_images/... from bot-data
        url = `${base}/bot-data/${path}`
      }
    } else {
      url = `${base}/${path}`
    }
  }
  
  // 缓存策略：v=${postId} 作为静态版本号，仅在原 URL 无鉴权签名时安全拼接
  if (postId && !url.includes('X-Amz-Signature')) {
    const sep = url.includes('?') ? '&' : '?'
    url = `${url}${sep}v=${postId}`
  }
  
  return url
}
let currentVisibleRequestId = 0
let currentQueryVersion = 0

let configPromise: Promise<void> | null = null

const loadConfig = async () => {
  if (configPromise) return configPromise
  
  configPromise = (async () => {
    try {
      const res = await api.get('/gallery/config')
      allowedTypes.value = res.data.allowed_types
      videoLoraModels.value = res.data.lora_models || []
      img2imgLoraModels.value = res.data.img2img_lora_models || []
    } catch (error) {
      console.error('Failed to load gallery config:', error)
    } finally {
      configPromise = null
    }
  })()
  
  return configPromise
}

const resetPaginationState = () => {
  currentPage.value = 1
  posts.value = []
  pageCache.value = {}
  total.value = 0
  totalPages.value = 0
  loading.value = false
}

const scrollToTop = async () => {
  await nextTick()
  layoutContentRef.value?.scrollTo({
    top: 0,
    behavior: 'smooth'
  })
}

const syncPageResult = (pageNumber: number, items: Post[], resData: any) => {
  pageCache.value = {
    ...pageCache.value,
    [pageNumber]: items
  }
  total.value = typeof resData.total === 'number' ? resData.total : total.value
  totalPages.value = typeof resData.pages === 'number' && resData.pages > 0
    ? resData.pages
    : Math.max(1, Math.ceil((total.value || items.length) / pageSize.value))
}

const fetchPostsPage = async (
  pageNumber: number,
  options: { activate?: boolean; force?: boolean } = {}
) => {
  const { activate = false, force = false } = options
  const cachedItems = pageCache.value[pageNumber]

  if (!force && cachedItems) {
    if (activate) {
      currentPage.value = pageNumber
      posts.value = cachedItems
    }
    return true
  }

  if (pendingPages.has(pageNumber)) {
    return false
  }

  const requestVersion = currentQueryVersion
  const visibleRequestId = activate ? ++currentVisibleRequestId : currentVisibleRequestId
  pendingPages.add(pageNumber)

  if (activate) {
    loading.value = true
  }

  try {
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

    if (requestVersion !== currentQueryVersion) return false

    const newItems = res.data.items.map((p: Post) => {
      // 兼容后端还没重启的情况：如果后端下发的 thumbnail_url 还是原视频 (.mp4)，前端自己算出 _thumb.jpg
      const isVideo = isVideoFile(p.media_url, p.media_type)
      const thumbUrl = normalizeGalleryThumbnailPath(p.thumbnail_url, isVideo)

      const src = getFileUrl(thumbUrl, p.id)
      return { ...p, src }
    })

    syncPageResult(pageNumber, newItems, res.data)

    if (activate && visibleRequestId === currentVisibleRequestId) {
      currentPage.value = pageNumber
      posts.value = newItems

      // 如果返回数据为空，或者没有更多数据，必须手动释放 loading 锁
      // 因为 Waterfall 的 @afterRender 可能不会被触发
      if (newItems.length === 0) {
        loading.value = false
      } else {
        // 异常情况兜底：防止瀑布流渲染失败或卡死导致 loading 锁无法释放
        setTimeout(() => {
          if (loading.value && visibleRequestId === currentVisibleRequestId) {
            loading.value = false
            console.warn('Fallback: Force released loading lock after 3s')
          }
        }, 3000)
      }
    }
    return true
  } catch (error) {
    if (requestVersion !== currentQueryVersion) return false
    console.error(error)
    message.error('获取广场数据失败')
    if (activate && visibleRequestId === currentVisibleRequestId) {
      loading.value = false
    }
    return false
  } finally {
    pendingPages.delete(pageNumber)
  }
}

const prefetchNextPage = () => {
  if (!totalPages.value || currentPage.value >= totalPages.value) {
    return
  }
  void fetchPostsPage(currentPage.value + 1)
}

const goToPage = async (pageNumber: number) => {
  if (pageNumber < 1 || (totalPages.value > 0 && pageNumber > totalPages.value)) {
    return
  }

  const changed = await fetchPostsPage(pageNumber, { activate: true })
  if (!changed) return

  await scrollToTop()
  prefetchNextPage()
}

const goPrev = async () => {
  if (currentIndex.value > 0) {
    currentPost.value = posts.value[currentIndex.value - 1]
    return
  }

  if (currentPage.value <= 1) return
  const changed = await fetchPostsPage(currentPage.value - 1, { activate: true })
  if (changed) {
    currentPost.value = posts.value[posts.value.length - 1] ?? null
  }
}

const goNext = async () => {
  if (currentIndex.value >= 0 && currentIndex.value < posts.value.length - 1) {
    currentPost.value = posts.value[currentIndex.value + 1]
    if (currentIndex.value >= posts.value.length - 3) {
      prefetchNextPage()
    }
    return
  }

  if (currentPage.value >= totalPages.value) return
  const changed = await fetchPostsPage(currentPage.value + 1, { activate: true })
  if (changed) {
    currentPost.value = posts.value[0] ?? null
  }
}

const loadPosts = async (reset = false) => {
  if (!reset) {
    prefetchNextPage()
    return
  }

  currentQueryVersion += 1
  resetPaginationState()
  const loaded = await fetchPostsPage(1, { activate: true, force: true })
  if (loaded) {
    prefetchNextPage()
  }
}

const handleTaskTypeChange = (type: string) => {
  taskType.value = type
  if (type !== 'video_lora' && type !== 'img2img_lora') {
    loraModel.value = 'all'
  }
  loadPosts(true)
}

const handleInteract = async (post: Post, action: 'like' | 'dislike') => {
  if (interactingPosts.value[post.id]) return
  
  interactingPosts.value[post.id] = true
  try {
    const { data: resData } = await api.post(`/gallery/posts/${post.id}/interact`, null, {
      params: { action }
    })
    
    const result = resData.data
    const action_state = result.action_state
    
    post.likes_count = result.likes_count
    post.dislikes_count = result.dislikes_count
    
    if (action_state === 'added') {
      if (action === 'like') post.has_liked = true
      else post.has_disliked = true
      message.success(action === 'like' ? '点赞成功' : '点踩成功')
    } else if (action_state === 'canceled') {
      if (action === 'like') post.has_liked = false
      else post.has_disliked = false
      message.success(action === 'like' ? '已取消点赞' : '已取消点踩')
    } else if (action_state === 'switched') {
      if (action === 'like') {
        post.has_liked = true
        post.has_disliked = false
      } else {
        post.has_disliked = true
        post.has_liked = false
      }
      message.success(action === 'like' ? '点赞成功' : '点踩成功')
    }
  } catch (error: any) {
    console.error(error)
  } finally {
    interactingPosts.value[post.id] = false
  }
}

const openDetail = (post: Post) => {
  currentPost.value = post
  detailVisible.value = true
}

const invalidatePendingApplyContext = () => {
  applyRequestToken += 1
  pendingApplyAbortController?.abort()
  pendingApplyAbortController = null
  applying.value = false
}

const handleLegacyFallback = async (params: {
  rawContext: any
  entryEntityId: number | string | null
}) => {
  const resolvedEntry = resolveTemplateApplyEntry({
    rawContext: params.rawContext,
    source: 'gallery',
    entryEntityId: params.entryEntityId,
    preferredMode: 'legacy'
  })

  if (resolvedEntry.status === 'invalid') {
    message.error(t('template_apply.invalid_context'))
    return false
  }

  if (resolvedEntry.status === 'unknown_task_type') {
    message.warning(t('template_apply.unknown_task_type'))
    return false
  }

  sessionStorage.setItem('galleryApplyContext', JSON.stringify(params.rawContext))
  detailVisible.value = false
  message.success(t('template_apply.legacy_loaded'))
  await router.push(buildLegacyTemplateRoute(resolvedEntry, t))
  return true
}

const openTemplateWorkbench = async (
  rawContext: any,
  snapshot: { entryEntityId: number | string | null }
): Promise<boolean> => {
  const result = await templateApplyStore.openFromRawContext({
    source: 'gallery',
    entryEntityId: snapshot.entryEntityId,
    rawContext
  })

  if (result.status === 'opened') {
    detailVisible.value = false
    message.success(t('template_apply.open_success'))
    return true
  }

  if (result.status === 'legacy_fallback') {
    if (result.fallbackKind === 'legacy_supported' && result.context && result.meta) {
      sessionStorage.setItem('galleryApplyContext', JSON.stringify(rawContext))
      detailVisible.value = false
      message.success(t('template_apply.legacy_loaded'))
      await router.push(buildLegacyTemplateRoute({
        status: 'legacy_supported',
        context: result.context,
        meta: result.meta
      }, t))
      return true
    }

    return handleLegacyFallback({
      rawContext,
      entryEntityId: snapshot.entryEntityId
    })
  }

  if (result.status === 'invalid') {
    message.error(result.message)
    return false
  }

  if (result.status === 'confirm_required') {
    const confirmed = await confirmTemplateApplyClose(result.confirmReason)
    if (!confirmed) {
      return false
    }
    await templateApplyStore.confirmCloseAndCleanup('open_replace')
    return openTemplateWorkbench(rawContext, snapshot)
  }

  return false
}

const handleApply = async () => {
  if (!currentPost.value || applying.value) return
  const snapshot = {
    postId: currentPost.value.id,
    entryEntityId: currentPost.value.id
  }
  const requestToken = ++applyRequestToken
  pendingApplyAbortController?.abort()
  const abortController = new AbortController()
  pendingApplyAbortController = abortController
  applying.value = true
  
  try {
    const res = await api.get(`/gallery/posts/${snapshot.postId}/apply-context`, {
      signal: abortController.signal
    })
    if (
      applyRequestToken !== requestToken
      || pendingApplyAbortController !== abortController
      || isGalleryUnmounted
      || !detailVisible.value
      || currentPost.value?.id !== snapshot.postId
    ) {
      return
    }
    await openTemplateWorkbench(res.data, snapshot)
  } catch (error: any) {
    if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') {
      return
    }
    console.error(error)
    message.error(t('my_notes.template_load_failed'))
  } finally {
    if (pendingApplyAbortController === abortController) {
      pendingApplyAbortController = null
    }
    if (applyRequestToken === requestToken) {
      applying.value = false
    }
  }
}

// Scroll detection for lazy loading
const handleScroll = () => {
  if (templateApplyStore.visible) {
    return
  }

  const container = layoutContentRef.value
  if (!container) return
  
  const { scrollTop, scrollHeight, clientHeight } = container
  if (scrollHeight - scrollTop - clientHeight < 200) {
    prefetchNextPage()
  }
}

const handleImageError = (e: Event, post: Post) => {
  const img = e.target as HTMLImageElement
  
  // 降级机制：如果缩略图加载失败（如尚未生成），回退加载原图
  // 但注意：如果原图是视频，绝不能让 img 去加载 .mp4
  if (!img.dataset.fallbackAttempted && post.media_url && !isVideoFile(post.media_url, post.media_type)) {
    img.dataset.fallbackAttempted = 'true'
    img.src = post.media_url.includes('X-Amz-Signature') ? post.media_url : getFileUrl(post.media_url, post.id)
    img.style.opacity = '1'
  } else {
    // 如果原图也加载失败，或者是视频（视频封面还没生成），则变暗显示破图图标/占位图
    img.style.opacity = '0.3'
  }
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
  layoutContentRef,
  (container, previousContainer) => {
    previousContainer?.removeEventListener('scroll', handleScroll)
    container?.addEventListener('scroll', handleScroll)
  },
  { immediate: true }
)

watch(
  detailVisible,
  (visible, previousVisible) => {
    if (!visible && previousVisible) {
      invalidatePendingApplyContext()
    }
  },
  { flush: 'sync' }
)

onUnmounted(() => {
  isGalleryUnmounted = true
  invalidatePendingApplyContext()
  layoutContentRef.value?.removeEventListener('scroll', handleScroll)
})
</script>

<template>
  <div class="gallery-container text-slate-200">
    <!-- Header Controls -->
    <div class="flex flex-col mb-3 sticky top-0 z-40 -mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8 pt-3 gap-3">
      <div class="flex flex-col xl:flex-row justify-between xl:items-center gap-4">
        <!-- Task Types -->
        <OverflowScrollRail
          container-class="w-full xl:w-auto shrink-0"
          content-class="flex gap-1 bg-slate-500/50 p-1 rounded-xl border border-slate-400/50"
        >
          <button 
            @click="handleTaskTypeChange('all')"
            class="px-3 py-1 sm:px-4 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm whitespace-nowrap shrink-0"
            :class="taskType === 'all' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_10px_rgba(56,189,248,0.2)]' : 'hover:text-cyan-300 text-slate-400'"
          >
            {{ $t('gallery.tabs.all') }}
          </button>
          <button 
            v-for="tab in allowedTypes" 
            :key="tab.id"
            @click="handleTaskTypeChange(tab.id)"
            class="px-3 py-1 sm:px-4 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm whitespace-nowrap shrink-0"
            :class="taskType === tab.id ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_10px_rgba(56,189,248,0.2)]' : 'hover:text-cyan-300 text-slate-400'"
          >
            {{ $t(`gallery.tabs.${tab.id.replace('i2i_pro', 'face_swap').replace('edit', 'custom_edit').replace('img2img_lora', 'img2img').replace('custom_video', 'custom_video').replace('video_lora', 'img2video').replace('ltx_video', 'high_res_video')}`) }}
          </button>
        </OverflowScrollRail>
        
        <OverflowScrollRail
          container-class="w-full xl:w-auto shrink-0 rounded-2xl border border-slate-700/50 bg-slate-950/55 px-2 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]"
          content-class="flex items-center gap-3"
        >
          <!-- Time Range -->
          <div class="flex bg-slate-500/50 p-1 rounded-xl border border-slate-400/50 shrink-0">
            <button 
              v-for="time in [{k:'all', n: $t('gallery.filters.all')}, {k:'today', n: $t('gallery.filters.today')}, {k:'week', n: $t('gallery.filters.this_week')}, {k:'month', n: $t('gallery.filters.this_month')}]" 
              :key="time.k"
              @click="timeRange = time.k; loadPosts(true)"
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
              @click="sortBy = sort.k; loadPosts(true)"
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
        v-if="taskType === 'video_lora' || taskType === 'img2img_lora'"
        container-class="w-full shrink-0 px-1 rounded-2xl border border-slate-700/50 bg-slate-950/55 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]"
        content-class="flex items-center gap-2"
      >
        <span class="text-xs sm:text-sm text-slate-400 whitespace-nowrap shrink-0">{{ $t('gallery.choose_addon') }}</span>
        <div class="flex gap-2 shrink-0">
          <button 
            @click="loraModel = 'all'; loadPosts(true)"
            class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
            :class="loraModel === 'all' ? 'bg-pink-500/20 border-pink-500/50 text-pink-400' : 'border-slate-400 hover:border-slate-500 text-slate-400'"
          >
            {{ $t('gallery.all_models') }}
          </button>
          <button 
            v-for="lora in currentLoraModels" 
            :key="lora.id"
            @click="loraModel = lora.id; loadPosts(true)"
            class="px-2 py-0.5 sm:px-3 sm:py-1 rounded-lg text-xs transition-all border whitespace-nowrap shrink-0"
            :class="loraModel === lora.id ? 'bg-pink-500/20 border-pink-500/50 text-pink-400' : 'border-slate-400 hover:border-slate-500 text-slate-400'"
          >
            {{ lora.name }}
          </button>
        </div>
      </OverflowScrollRail>
    </div>

    <div class="-mt-1 flex justify-center">
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

    <!-- Masonry Grid -->
    <Waterfall 
      :list="posts" 
      rowKey="id"
      :breakpoints="breakpoints" 
      :gutter="isMobile ? 12 : 24" 
      :animationDuration="400"
      backgroundColor="transparent"
      @afterRender="() => { loading = false }"
      :hasAroundGutter="false"
    >
      <template #default="{ item: post }">
        <div 
          class="rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-400/50 bg-slate-500/40 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
          @click="openDetail(post)"
        >
          <!-- Media -->
          <div 
            class="relative w-full overflow-hidden bg-slate-500"
            :style="post.width && post.height ? { aspectRatio: `${post.width}/${post.height}` } : { aspectRatio: '1/1' }"
          >
            <!-- Render as standard image if it's an image task OR if it's a video BUT the thumbnail is loaded successfully -->
            <img 
              v-show="!isVideoFile(post.media_url, post.media_type)" 
              :src="post.src" 
              @error="handleImageError($event, post)"
              class="w-full object-cover transition-opacity duration-300 absolute inset-0 h-full"
              loading="lazy" 
            />
            
            <LazyVideo 
              v-show="isVideoFile(post.media_url, post.media_type)" 
              :src="getFileUrl(post.media_url, post.id)" 
              :poster="post.src"
              className="w-full object-cover absolute inset-0 h-full"
            />
          
          <!-- Type Badge -->
          <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10">
            <ImageIcon v-if="!isVideoFile(post.media_url, post.media_type)" :size="14" class="text-cyan-400" />
            <Video v-else :size="14" class="text-indigo-400" />
          </div>
          
          <!-- Play Icon Overlay for Videos -->
          <div v-if="isVideoFile(post.media_url, post.media_type)" class="absolute inset-0 flex items-center justify-center pointer-events-none opacity-80 group-hover:opacity-0 transition-opacity duration-300">
            <div class="w-12 h-12 bg-black/50 backdrop-blur-md rounded-full flex items-center justify-center border border-white/20 shadow-lg">
              <Play :size="24" class="text-white ml-1" />
            </div>
          </div>
          
          <!-- Tags Overlay on Hover -->
          <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-4">
            <div class="flex flex-wrap gap-1.5 mb-8">
              <span v-for="tag in post.tags.slice(0, 4)" :key="tag" class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md">
                {{ formatTag(tag) }}
              </span>
              <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
            </div>
          </div>
        </div>
        
        <!-- Stats Bar -->
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
        </div>
      </template>
    </Waterfall>
    
    <!-- Loading State -->
    <div v-if="loading" class="py-8 text-center">
      <div class="inline-block w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
    </div>
    
    <!-- Empty State -->
    <div v-if="!loading && posts.length === 0" class="py-20 text-center text-slate-500">
      <Compass :size="48" class="mx-auto mb-4 opacity-20" />
      <p>{{ $t('gallery.no_posts') }}</p>
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
      <div v-if="currentPost" class="flex flex-col lg:flex-row bg-[#0f172a] sm:rounded-2xl overflow-hidden sm:border border-slate-400/50 sm:shadow-2xl w-full min-h-full sm:min-h-0 relative">
        
        <!-- Mobile Header (Visible only on mobile) -->
        <div class="lg:hidden flex items-center justify-between px-4 h-14 shrink-0 bg-[#0f172a]/90 backdrop-blur-md sticky top-0 z-50 border-b border-slate-800">
          <div class="flex items-center gap-3">
              <button @click="detailVisible = false" class="text-slate-200 hover:text-white p-1 -ml-1">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
            </button>
            <div class="flex items-center gap-2">
              <div class="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-indigo-500 flex items-center justify-center text-white font-bold text-xs">
                {{ currentPost.author_name ? currentPost.author_name.charAt(0).toUpperCase() : '修' }}
              </div>
              <span class="text-slate-200 font-medium text-sm">{{ currentPost.author_name || '匿名修士' }}</span>
            </div>
          </div>
        </div>

        <!-- Media Area -->
        <div class="w-full lg:w-2/3 bg-black flex items-center justify-center relative group/media">
          <template v-if="currentPost.media_url">
            <img v-if="!isVideoFile(currentPost.media_url, currentPost.media_type)" :src="getFileUrl(currentPost.media_url, currentPost.id)" class="w-full h-auto max-h-[65vh] object-contain lg:max-w-full lg:max-h-[80vh]" />
            <video v-else :src="getFileUrl(currentPost.media_url, currentPost.id)" class="w-full h-auto max-h-[65vh] object-contain lg:max-w-full lg:max-h-[80vh]" controls autoplay loop playsinline></video>
          </template>
          
          <!-- Navigation Arrows -->
          <button v-if="hasPrev" @click.stop="goPrev" class="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 sm:w-12 sm:h-12 bg-black/40 hover:bg-black/60 rounded-full flex items-center justify-center text-white/80 hover:text-white transition-all z-20 border border-white/10 backdrop-blur-sm opacity-100 lg:opacity-0 lg:group-hover/media:opacity-100">
            <ChevronLeft :size="24" />
          </button>
          <button v-if="hasNext" @click.stop="goNext" class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 sm:w-12 sm:h-12 bg-black/40 hover:bg-black/60 rounded-full flex items-center justify-center text-white/80 hover:text-white transition-all z-20 border border-white/10 backdrop-blur-sm opacity-100 lg:opacity-0 lg:group-hover/media:opacity-100">
            <ChevronRight :size="24" />
          </button>
        </div>
        
        <!-- Info Area -->
        <div class="w-full lg:w-1/3 flex flex-col bg-[#0f172a] lg:bg-slate-500/80 lg:backdrop-blur-xl relative pb-[80px] lg:pb-0">
          <!-- Desktop Close button -->
          <button @click="detailVisible = false" class="hidden lg:block absolute top-4 right-4 text-slate-400 hover:text-white transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
          
          <div class="p-4 lg:p-6 flex-1 flex flex-col">
            <!-- Desktop Title -->
            <h3 class="hidden lg:flex text-xl font-bold text-slate-100 mb-2 items-center">
              <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">{{ $t('gallery.modal.title') }}</span>
            </h3>
            
            <!-- Tags & Time Area -->
            <div class="mb-4 lg:mb-6 mt-2 lg:mt-0">
              <div class="flex flex-wrap gap-2 mb-3">
                <span v-for="tag in currentPost.tags" :key="tag" class="text-xs bg-slate-800 lg:bg-slate-500 text-cyan-400 lg:text-cyan-200 border border-slate-700 lg:border-slate-400 px-2.5 py-1 rounded-full">
                  {{ tag.startsWith('#') ? formatTag(tag) : '#' + formatTag(tag) }}
                </span>
                <span v-if="!currentPost.tags || currentPost.tags.length === 0" class="text-sm text-slate-500 lg:text-slate-400">None</span>
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
            <div class="hidden lg:flex space-x-2 mb-4 pt-4">
              <button @click="handleInteract(currentPost, 'like')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <Heart :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'" />
                <span class="font-medium" :class="currentPost.has_liked ? 'text-pink-400' : 'text-slate-300'">{{ currentPost.likes_count }}</span>
              </button>
              <button @click="handleInteract(currentPost, 'dislike')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <ThumbsDown :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'" />
                <span class="font-medium" :class="currentPost.has_disliked ? 'text-slate-400' : 'text-slate-300'">{{ currentPost.dislikes_count }}</span>
              </button>
              <button @click="showCommentInput = true" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
                <MessageCircle :size="20" class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400" />
                <span class="font-medium text-slate-300">{{ currentPost.comments_count }}</span>
              </button>
            </div>
            
            <!-- Desktop Apply Button -->
            <div class="hidden lg:block mt-8">
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
            </div>

            <!-- Comments Section -->
            <div class="mt-6 flex flex-col min-h-[200px] lg:flex-1 lg:max-h-none lg:overflow-hidden">
              <div class="flex items-center justify-between mb-4 shrink-0">
                <h3 class="text-slate-200 font-medium flex items-center gap-2">
                  <MessageCircle :size="18" />
                  {{ t('gallery.comments.section_title', { count: commentsTotal }) }}
                </h3>
              </div>
              <div
                :class="isMobile
                  ? 'pr-0'
                  : 'flex-1 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent'"
              >
                <div v-if="commentsLoading && commentsPage === 1" class="py-8 text-center">
                  <div class="inline-block w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
                </div>
                <div v-else-if="commentsError && comments.length === 0" class="py-8 text-center text-sm">
                  <p class="text-rose-300">{{ commentsError }}</p>
                  <button
                    @click="currentPost && loadComments(currentPost.id, { page: 1, append: false })"
                    class="mt-3 text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    {{ t('gallery.comments.retry') }}
                  </button>
                </div>
                <div v-else-if="comments.length === 0" class="py-8 text-center text-slate-500 text-sm">
                  {{ t('gallery.comments.empty') }}
                </div>
                <div v-else class="space-y-4 pb-24 lg:pb-4">
                  <div v-if="commentsError" class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                    <span>{{ commentsError }}</span>
                    <button
                      @click="loadMoreComments"
                      class="ml-3 text-cyan-300 hover:text-cyan-200 transition-colors"
                    >
                      {{ t('gallery.comments.retry') }}
                    </button>
                  </div>
                  <div v-for="comment in comments" :key="comment.id" class="flex gap-3">
                    <div class="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center shrink-0 border border-slate-600">
                      <span class="text-slate-300 text-xs font-medium">{{ comment.user.author_name.charAt(0).toUpperCase() }}</span>
                    </div>
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2 mb-1">
                        <span class="text-sm font-medium text-slate-300 truncate">{{ comment.user.author_name }}</span>
                        <span class="text-xs text-slate-500">{{ dayjs(comment.created_at).format('MM-DD HH:mm') }}</span>
                      </div>
                      <p class="text-sm text-slate-300 break-words whitespace-pre-wrap">{{ comment.content }}</p>
                    </div>
                  </div>
                  <div v-if="commentsHasMore" class="pt-2 pb-4 text-center">
                    <button 
                      @click="loadMoreComments" 
                      :disabled="commentsLoading"
                      class="text-xs text-cyan-400 hover:text-cyan-300 transition-colors disabled:opacity-50"
                    >
                      {{ commentsLoading ? t('gallery.comments.loading_more') : t('gallery.comments.load_more') }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Mobile Bottom Interaction Bar -->
        <div class="lg:hidden fixed bottom-0 left-0 right-0 bg-[#0f172a]/95 backdrop-blur-lg border-t border-slate-800 px-4 py-3 flex items-center justify-between z-50 safe-area-bottom">
          <div class="flex items-center gap-6">
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
              <span class="text-sm font-medium">{{ currentPost.comments_count }}</span>
            </button>
          </div>
          <button 
            @click="handleApply" 
            :disabled="applying"
            class="px-6 py-2 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm shadow-lg flex items-center"
          >
            <Wand2 v-if="!applying" :size="16" class="mr-1.5" />
            <div v-else class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1.5"></div>
            {{ applying ? '...' : $t('gallery.modal.apply_btn') }}
          </button>
        </div>

      </div>
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
