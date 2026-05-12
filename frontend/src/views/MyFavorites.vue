<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import LazyVideo from '@/components/LazyVideo.vue'
import { Heart, ThumbsDown, Wand2, Play, Image as ImageIcon, Video, Flame, Clock, Trash2, Eye, EyeOff, Copy, Compass, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import api from '@/api'
import dayjs from 'dayjs'

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
  thumbnail_url: string
  media_url: string
  created_at: string
  has_liked: boolean
  has_disliked: boolean
  is_active: boolean
  prompt: string
  src?: string
}

const router = useRouter()
const { t } = useI18n()
const posts = ref<Post[]>([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const hasMore = ref(true)
const isMobile = ref(false)

const mediaType = ref('all')
const taskType = ref('all')
const loraModel = ref('all')
const sortBy = ref('latest')
const timeRange = ref('all')

const filterType = ref('all')

const allowedTypes = ref<{id: string, name: string}[]>([])
const loraModels = ref<{id: string, name: string}[]>([])

const detailVisible = ref(false)
const currentPost = ref<Post | null>(null)
const applying = ref(false)
const interactingPosts = ref<Record<number, boolean>>({})

const currentIndex = computed(() => {
  if (!currentPost.value) return -1
  return posts.value.findIndex(p => p.id === currentPost.value?.id)
})

const pageSize = computed(() => {
  if (filterType.value === 'favorite' && isMobile.value) {
    return 5
  }
  return 20
})

const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(() => currentIndex.value >= 0 && currentIndex.value < posts.value.length - 1)

const goPrev = () => {
  if (hasPrev.value) {
    currentPost.value = posts.value[currentIndex.value - 1]
  }
}

const goNext = () => {
  if (hasNext.value) {
    currentPost.value = posts.value[currentIndex.value + 1]
    if (currentIndex.value >= posts.value.length - 3 && hasMore.value) {
      loadPosts()
    }
  }
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
  
  if (!postId || url.includes('X-Amz-Signature') || /[?&]v=/.test(url)) {
    return url
  }
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}v=${postId}`
}

const getCardSrc = (post: Post) => {
  if (post.thumbnail_url) {
    return getFileUrl(post.thumbnail_url, post.id)
  }
  if (filterType.value !== 'favorite' && !isVideoFile(post.media_url, post.media_type) && post.media_url) {
    return getFileUrl(post.media_url, post.id)
  }
  return ''
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

let currentRequestId = 0

const updateViewportMode = () => {
  const nextIsMobile = window.innerWidth < 768
  if (nextIsMobile === isMobile.value) {
    return
  }
  isMobile.value = nextIsMobile
  if (filterType.value === 'favorite') {
    loadPosts(true)
  }
}

const loadConfig = async () => {
  try {
    const res = await api.get('/gallery/config')
    allowedTypes.value = res.data.allowed_types
    loraModels.value = res.data.lora_models
  } catch (error) {
    console.error('Failed to load gallery config:', error)
  }
}

const loadPosts = async (reset = false) => {
  if (!reset && (loading.value || !hasMore.value)) return
  
  loading.value = true
  if (reset) {
    page.value = 1
    posts.value = []
    hasMore.value = true
  }
  
  const requestId = ++currentRequestId
  
  try {
    const endpoint = filterType.value === 'favorite' ? '/users/my-favorites' : '/gallery/my-favorites'
    const res = await api.get(endpoint, {
      params: {
        page: page.value,
        size: pageSize.value,
        filter_type: filterType.value === 'favorite' ? 'all' : filterType.value
      }
    })
    
    if (requestId !== currentRequestId) return
    
    const newItems = res.data.items.map((p: Post) => {
      const src = getCardSrc(p)
      return { ...p, src }
    })
    
    if (reset) {
      posts.value = newItems
    } else {
      posts.value = [...posts.value, ...newItems]
    }
    
    total.value = res.data.total
    if (page.value >= res.data.pages) {
      hasMore.value = false
    } else {
      page.value++
    }
  } catch (error) {
    if (requestId !== currentRequestId) return
    console.error(error)
    message.error('获取广场数据失败')
  } finally {
    if (requestId === currentRequestId) {
      loading.value = false
    }
  }
}

const handleTaskTypeChange = (type: string) => {
  taskType.value = type
  if (type !== 'video_lora') {
    loraModel.value = 'all'
  }
  loadPosts(true)
}

const handleFilterTypeChange = (type: string) => {
  filterType.value = type
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

const handleUnfavorite = async (post: Post) => {
  if (!post) return
  
  try {
    await api.delete(`/users/history/${post.task_id}/favorite`)
    message.success('已取消收藏')
    detailVisible.value = false
    loadPosts(true)
  } catch (error: any) {
    console.error(error)
    message.error(error.response?.data?.detail || '操作失败')
  }
}

const openDetail = (post: Post) => {
  currentPost.value = post
  detailVisible.value = true
}

const copyPrompt = (post: Post) => {
  if (!post.prompt) {
    message.warning('此投稿没有提示词')
    return
  }
  navigator.clipboard.writeText(post.prompt).then(() => {
    message.success('提示词已复制到剪贴板')
  }).catch(() => {
    message.error('复制失败')
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
    const context = res.data
    detailVisible.value = false
    
    // Store context in sessionStorage to pass to target page
    sessionStorage.setItem('galleryApplyContext', JSON.stringify(context))
    
    // Route mapping
    const featureMap: Record<string, { route: string, title: string, cost: number }> = {
      // From CustomFeatures
      'i2i_pro': { route: 'ImageAndPrompt', title: '幻想换脸', cost: 6 },
      'i2i_draw': { route: 'ImageAndPrompt', title: '局部重绘', cost: 3 },
      'edit': { route: 'ImageAndPrompt', title: '自由P图', cost: 2 },
      'img2img_lora': { route: 'ImageAndPrompt', title: '图生图(附加模型)', cost: 2 },
      'face_swap': { route: 'FaceSwap', title: '快速换脸', cost: 1 }, 
      'face_video': { route: 'VideoSwap', title: '视频换脸', cost: 18 },
      'custom_video': { route: 'SingleImageToVideo', title: '自定义图生视频', cost: 6 },
      'video_lora': { route: 'SingleImageToVideo', title: '图生视频(附加模型)', cost: 6 },
      'ltx_video': { route: 'SingleImageToVideo', title: '高级图生视频', cost: 10 },
    }
    
    const featureInfo = featureMap[context.task_type]
    if (featureInfo) {
      message.success('已载入模板，请上传您的参考图')
      router.push({ 
        name: featureInfo.route, 
        query: { 
          apply: 'true',
          type: context.task_type,
          title: featureInfo.title,
          cost: featureInfo.cost
        } 
      })
    } else {
      message.success('已载入模板')
      router.push({ name: 'CustomFeatures', query: { apply: 'true' } })
    }
    
  } catch (error) {
    console.error(error)
    message.error('获取模板数据失败')
  } finally {
    applying.value = false
  }
}

// Scroll detection for lazy loading
const handleScroll = () => {
  const container = document.querySelector('.ant-layout-content')
  if (!container) return
  
  const { scrollTop, scrollHeight, clientHeight } = container
  if (scrollHeight - scrollTop - clientHeight < 200) {
    loadPosts()
  }
}

// Video hover logic
const playVideo = (e: Event) => {
  const video = e.target as HTMLVideoElement
  video.play().catch(() => {})
}

const pauseVideo = (e: Event) => {
  const video = e.target as HTMLVideoElement
  video.pause()
  video.currentTime = 0
}

const handleImageError = (e: Event, post: Post) => {
  const img = e.target as HTMLImageElement
  
  // 只有拿到缩略图后才允许回退原图，避免收藏列表在缺缩略图时直接加载大图。
  if (!img.dataset.fallbackAttempted && post.thumbnail_url && post.media_url && !isVideoFile(post.media_url, post.media_type)) {
    img.dataset.fallbackAttempted = 'true'
    img.src = getFileUrl(post.media_url, post.id)
    img.style.opacity = '1'
  } else {
    // 如果原图也加载失败，或者是视频（视频封面还没生成），则变暗显示破图图标/占位图
    img.style.opacity = '0.3'
  }
}

onMounted(() => {
  isMobile.value = window.innerWidth < 768
  loadConfig()
  loadPosts(true)
  const container = document.querySelector('.ant-layout-content')
  if (container) {
    container.addEventListener('scroll', handleScroll)
  }
  window.addEventListener('resize', updateViewportMode)
})

onUnmounted(() => {
  const container = document.querySelector('.ant-layout-content')
  if (container) {
    container.removeEventListener('scroll', handleScroll)
  }
  window.removeEventListener('resize', updateViewportMode)
})
</script>

<template>
  <div class="gallery-container text-slate-200">
    
    <!-- Top Filter Tabs -->
    <div class="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div class="flex items-center space-x-2 overflow-x-auto pb-2 md:pb-0 hide-scrollbar">
        <button 
          v-for="ft in [{id: 'all', name: '全部'}, {id: 'like', name: '我的点赞'}, {id: 'apply', name: '我的应用'}, {id: 'favorite', name: '我的收藏'}]" 
          :key="ft.id"
          @click="handleFilterTypeChange(ft.id)"
          class="px-4 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap"
          :class="filterType === ft.id ? 'bg-cyan-500 text-white shadow-[0_0_10px_rgba(56,189,248,0.4)]' : 'bg-slate-500 text-slate-400 hover:bg-slate-500 hover:text-slate-200'"
        >
          {{ ft.name }}
        </button>
      </div>
    </div>

    <!-- Masonry Grid -->
    <div class="columns-2 sm:columns-3 md:columns-4 lg:columns-5 gap-3 sm:gap-6">
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
            <ImageIcon v-if="!isVideoFile(post.media_url, post.media_type)" :size="24" />
            <Video v-else :size="24" />
          </div>
          
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
    <div v-if="loading" class="py-8 text-center">
      <div class="inline-block w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
    </div>
    
    <!-- Empty State -->
    <div v-if="!loading && posts.length === 0" class="py-20 text-center text-slate-500">
      <Compass :size="48" class="mx-auto mb-4 opacity-20" />
      <p>您还没有收藏过任何作品</p>
    </div>

    <!-- Detail Modal -->
    <a-modal
      v-model:visible="detailVisible"
      :footer="null"
      :closable="false"
      width="90%"
      style="max-width: 1000px; top: 20px"
      class="gallery-detail-modal"
      :bodyStyle="{ padding: 0, backgroundColor: 'transparent' }"
      destroyOnClose
    >
      <div v-if="currentPost" class="flex flex-col lg:flex-row bg-[#0f172a] rounded-2xl overflow-hidden border border-slate-400/50 shadow-2xl">
        <!-- Media Area -->
        <div class="lg:w-2/3 bg-black flex items-center justify-center relative min-h-[300px] group/media">
          <template v-if="currentPost.media_url">
            <img v-if="!isVideoFile(currentPost.media_url, currentPost.media_type)" :src="getFileUrl(currentPost.media_url, currentPost.id)" class="max-w-full max-h-[65vh] lg:max-h-[80vh] object-contain" />
            <video v-else :src="getFileUrl(currentPost.media_url, currentPost.id)" :poster="currentPost.src" class="max-w-full max-h-[65vh] lg:max-h-[80vh] object-contain" controls autoplay loop playsinline></video>
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
        <div class="lg:w-1/3 p-6 flex flex-col bg-slate-500/80 backdrop-blur-xl relative">
          <!-- Close button -->
          <button @click="detailVisible = false" class="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
          
          <h3 class="text-xl font-bold text-slate-100 mb-2 flex items-center">
            <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">修仙界作品</span>
          </h3>
          
          <div class="text-sm text-slate-400 mb-6 space-y-2">
            <div class="flex space-x-4">
              <span v-if="currentPost.width">📏 {{ currentPost.width }}x{{ currentPost.height }}</span>
              <span v-if="currentPost.duration">⏱️ {{ currentPost.duration }}秒</span>
            </div>
            <div v-if="currentPost.created_at">
              <span>📅 {{ dayjs(currentPost.created_at).format('YYYY-MM-DD HH:mm') }}</span>
            </div>
          </div>
          
          <div class="mb-6">
            <h4 class="text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wider">包含元素 (Tags)</h4>
            <div class="flex flex-wrap gap-2">
              <span v-for="tag in currentPost.tags" :key="tag" class="text-xs bg-slate-500 text-cyan-200 border border-slate-400 px-2.5 py-1 rounded-md">
                {{ tag.startsWith('#') ? formatTag(tag) : '#' + formatTag(tag) }}
              </span>
              <span v-if="!currentPost.tags || currentPost.tags.length === 0" class="text-sm text-slate-500">无特定标签</span>
            </div>
          </div>
          
          <div class="flex space-x-4 mb-auto pt-4" v-if="filterType !== 'favorite'">
            <button @click="handleInteract(currentPost, 'like')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
              <Heart :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'" />
              <span class="font-medium" :class="currentPost.has_liked ? 'text-pink-400' : 'text-slate-300'">{{ currentPost.likes_count }}</span>
            </button>
            <button @click="handleInteract(currentPost, 'dislike')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
              <ThumbsDown :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'" />
              <span class="font-medium" :class="currentPost.has_disliked ? 'text-slate-400' : 'text-slate-300'">{{ currentPost.dislikes_count }}</span>
            </button>
          </div>
          
          <div class="flex space-x-4 mb-auto pt-4" v-if="filterType === 'favorite'">
            <button @click="handleUnfavorite(currentPost)" class="flex-1 py-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all flex items-center justify-center">
              <Trash2 :size="18" class="mr-2" />
              <span class="font-medium">取消收藏</span>
            </button>
          </div>
          
          <div class="mt-8 space-y-4">
            <button v-if="currentPost.prompt"
              @click="copyPrompt(currentPost)"
              class="w-full py-3 rounded-xl bg-slate-500 hover:bg-slate-500 text-white font-medium shadow-sm transition-all flex items-center justify-center border border-slate-400"
            >
              <Copy :size="18" class="mr-2" />
              复制提示词 (Prompt)
            </button>
            <button 
              @click="handleApply" 
              :disabled="applying"
              class="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-bold text-lg shadow-[0_0_20px_rgba(56,189,248,0.4)] transition-all transform hover:scale-[1.02] flex items-center justify-center relative overflow-hidden group"
            >
              <div class="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
              <Wand2 v-if="!applying" :size="22" class="mr-2 relative z-10" />
              <div v-else class="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2 relative z-10"></div>
              <span class="relative z-10">{{ applying ? '提取模板中...' : '✨ 一键应用此模板' }}</span>
            </button>
            <p class="text-center text-xs text-slate-500 mt-3">系统将自动为您配置最佳参数，您只需上传参考图即可</p>
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
