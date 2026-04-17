<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { Heart, ThumbsDown, Wand2, Play, Image as ImageIcon, Video, Flame, Clock } from 'lucide-vue-next'
import api from '@/api'

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
}

const router = useRouter()
const posts = ref<Post[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const hasMore = ref(true)

const mediaType = ref('all')
const sortBy = ref('latest')

const detailVisible = ref(false)
const currentPost = ref<Post | null>(null)
const applying = ref(false)

const getFileUrl = (path: string, isThumbnail: boolean = false, mediaType: string = 'image') => {
  if (!path) return ''
  if (path.startsWith('http')) return path
  
  const storageUrl = import.meta.env.VITE_STORAGE_URL || ''
  const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl
  
  let fullPath = path
  if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
    if (!path.includes('/')) {
        fullPath = `comfyui-temp/${path}`
    } else {
        fullPath = `bot-data/${path}`
    }
  }

  const fileUrl = `${base}/${fullPath}`
  
  // Imgproxy optimization for thumbnails
  if (isThumbnail) {
    const imgproxyUrl = import.meta.env.VITE_IMGPROXY_URL || ''
    if (imgproxyUrl) {
      const imgproxyBase = imgproxyUrl.endsWith('/') ? imgproxyUrl.slice(0, -1) : imgproxyUrl
      if (mediaType === 'image') {
        // Resize images to max 400px width, maintaining aspect ratio, convert to webp
        // Using plain url format for simplicity: /insecure/rs:auto:400:0:0/plain/{url}
        return `${imgproxyBase}/insecure/rs:auto:400:0:0/plain/${fileUrl}`
      } else if (mediaType === 'video') {
        // For videos, imgproxy can extract the first frame
        // return `${imgproxyBase}/insecure/rs:auto:400:0:0/plain/${fileUrl}`
        // However, since the browser <video> handles metadata, we can just return original
        // or configure imgproxy with video extensions if supported
        return fileUrl
      }
    }
  }
  
  return fileUrl
}

const loadPosts = async (reset = false) => {
  if (loading.value || (!hasMore.value && !reset)) return
  loading.value = true
  if (reset) {
    page.value = 1
    posts.value = []
    hasMore.value = true
  }
  
  try {
    const res = await api.get('/gallery/posts', {
      params: {
        page: page.value,
        size: size.value,
        media_type: mediaType.value,
        sort_by: sortBy.value
      }
    })
    
    if (reset) {
      posts.value = res.data.items
    } else {
      posts.value = [...posts.value, ...res.data.items]
    }
    
    total.value = res.data.total
    if (page.value >= res.data.pages) {
      hasMore.value = false
    } else {
      page.value++
    }
  } catch (error) {
    console.error(error)
    message.error('获取广场数据失败')
  } finally {
    loading.value = false
  }
}

const handleInteract = async (post: Post, action: 'like' | 'dislike') => {
  if ((action === 'like' && post.has_liked) || (action === 'dislike' && post.has_disliked)) return
  
  try {
    await api.post(`/gallery/posts/${post.id}/interact`, null, {
      params: { action }
    })
    
    if (action === 'like') {
      post.likes_count++
      post.has_liked = true
    } else {
      post.dislikes_count++
      post.has_disliked = true
    }
    message.success(action === 'like' ? '点赞成功' : '点踩成功')
  } catch (error: any) {
    // Error is handled by interceptor, but we can show a specific message if needed
    console.error(error)
  }
}

const openDetail = (post: Post) => {
  currentPost.value = post
  detailVisible.value = true
}

const handleApply = async () => {
  if (!currentPost.value || applying.value) return
  applying.value = true
  
  try {
    const res = await api.get(`/gallery/posts/${currentPost.value.id}/apply-context`)
    const context = res.data
    detailVisible.value = false
    
    // Store context in sessionStorage to pass to target page
    sessionStorage.setItem('galleryApplyContext', JSON.stringify(context))
    
    // Route mapping
    const featureMap: Record<string, { route: string, title: string, cost: number }> = {
      // From CustomFeatures
      'i2i_pro': { route: 'ImageAndPrompt', title: '幻想换脸', cost: 6 },
      'edit': { route: 'ImageAndPrompt', title: '自由P图', cost: 2 },
      'face_swap': { route: 'FaceSwap', title: '快速换脸', cost: 1 }, 
      'face_video': { route: 'VideoSwap', title: '视频换脸', cost: 20 },
      'custom_video': { route: 'SingleImageToVideo', title: '自定义图生视频', cost: 6 },
      'video_lora': { route: 'SingleImageToVideo', title: '图生视频 (附加模型)', cost: 6 },
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
  // Fallback to original image if imgproxy fails or times out
  const img = e.target as HTMLImageElement
  const originalUrl = getFileUrl(post.thumbnail_url, false, post.media_type)
  if (img.src !== originalUrl) {
    img.src = originalUrl
  }
}

onMounted(() => {
  loadPosts(true)
  const container = document.querySelector('.ant-layout-content')
  if (container) {
    container.addEventListener('scroll', handleScroll)
  }
})

onUnmounted(() => {
  const container = document.querySelector('.ant-layout-content')
  if (container) {
    container.removeEventListener('scroll', handleScroll)
  }
})
</script>

<template>
  <div class="gallery-container text-slate-200">
    <!-- Header Controls -->
    <div class="flex flex-col md:flex-row justify-between items-center mb-6 gap-4">
      <div class="flex bg-slate-800/50 p-1 rounded-xl border border-slate-700/50">
        <button 
          v-for="tab in [{k:'all', n:'全部'}, {k:'image', n:'纯图'}, {k:'video', n:'动态'}]" 
          :key="tab.k"
          @click="mediaType = tab.k; loadPosts(true)"
          class="px-4 py-1.5 rounded-lg transition-all font-medium text-sm"
          :class="mediaType === tab.k ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_10px_rgba(56,189,248,0.2)]' : 'hover:text-cyan-300 text-slate-400'"
        >
          {{ tab.n }}
        </button>
      </div>
      
      <div class="flex bg-slate-800/50 p-1 rounded-xl border border-slate-700/50">
        <button 
          v-for="sort in [{k:'latest', n:'最新发布', i: Clock}, {k:'likes', n:'最多点赞', i: Heart}, {k:'applied', n:'最多应用', i: Flame}]" 
          :key="sort.k"
          @click="sortBy = sort.k; loadPosts(true)"
          class="px-3 py-1.5 rounded-lg transition-all font-medium text-sm flex items-center"
          :class="sortBy === sort.k ? 'bg-indigo-500/20 text-indigo-400 shadow-[0_0_10px_rgba(129,140,248,0.2)]' : 'hover:text-indigo-300 text-slate-400'"
        >
          <component :is="sort.i" :size="14" class="mr-1.5" />
          {{ sort.n }}
        </button>
      </div>
    </div>

    <!-- Masonry Grid -->
    <div class="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-6 space-y-6">
      <div 
        v-for="post in posts" 
        :key="post.id"
        class="break-inside-avoid rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-700/30 bg-slate-800/20 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
        @click="openDetail(post)"
      >
        <!-- Media -->
        <div class="relative w-full overflow-hidden bg-slate-900 aspect-auto min-h-[100px]">
          <img 
            v-if="post.media_type === 'image'" 
            :src="getFileUrl(post.thumbnail_url, true, post.media_type)" 
            @error="handleImageError($event, post)"
            class="w-full h-auto object-cover transition-opacity duration-300" 
            loading="lazy" 
          />
          <video 
            v-else 
            :src="getFileUrl(post.thumbnail_url, true, post.media_type)" 
            class="w-full h-auto object-cover" 
            preload="metadata" 
            muted 
            loop
            playsinline
            @mouseenter="playVideo"
            @mouseleave="pauseVideo"
          ></video>
          
          <!-- Type Badge -->
          <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10">
            <ImageIcon v-if="post.media_type === 'image'" :size="14" class="text-cyan-400" />
            <Video v-else :size="14" class="text-indigo-400" />
          </div>
          
          <!-- Tags Overlay on Hover -->
          <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-4">
            <div class="flex flex-wrap gap-1.5 mb-8">
              <span v-for="tag in post.tags.slice(0, 4)" :key="tag" class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md">
                {{ tag }}
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
      <p>暂无道友分享作品</p>
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
      <div v-if="currentPost" class="flex flex-col lg:flex-row bg-[#0f172a] rounded-2xl overflow-hidden border border-slate-700/50 shadow-2xl">
        <!-- Media Area -->
        <div class="lg:w-2/3 bg-black flex items-center justify-center relative min-h-[300px]">
          <img v-if="currentPost.media_type === 'image'" :src="getFileUrl(currentPost.media_url)" class="max-w-full max-h-[80vh] object-contain" />
          <video v-else :src="getFileUrl(currentPost.media_url)" class="max-w-full max-h-[80vh] object-contain" controls autoplay loop></video>
        </div>
        
        <!-- Info Area -->
        <div class="lg:w-1/3 p-6 flex flex-col bg-slate-900/80 backdrop-blur-xl relative">
          <!-- Close button -->
          <button @click="detailVisible = false" class="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
          
          <h3 class="text-xl font-bold text-slate-100 mb-2 flex items-center">
            <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">修仙界作品</span>
          </h3>
          
          <div class="text-sm text-slate-400 mb-6 flex space-x-4">
            <span v-if="currentPost.width">📏 {{ currentPost.width }}x{{ currentPost.height }}</span>
            <span v-if="currentPost.duration">⏱️ {{ currentPost.duration }}秒</span>
          </div>
          
          <div class="mb-6">
            <h4 class="text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wider">包含元素 (Tags)</h4>
            <div class="flex flex-wrap gap-2">
              <span v-for="tag in currentPost.tags" :key="tag" class="text-xs bg-slate-800 text-cyan-200 border border-slate-700 px-2.5 py-1 rounded-md">
                {{ tag }}
              </span>
              <span v-if="!currentPost.tags || currentPost.tags.length === 0" class="text-sm text-slate-500">无特定标签</span>
            </div>
          </div>
          
          <div class="flex space-x-4 mb-auto pt-4">
            <button @click="handleInteract(currentPost, 'like')" class="flex-1 py-3 rounded-xl border border-slate-700 bg-slate-800/50 hover:bg-slate-700 transition-all flex items-center justify-center group">
              <Heart :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'" />
              <span class="font-medium" :class="currentPost.has_liked ? 'text-pink-400' : 'text-slate-300'">{{ currentPost.likes_count }}</span>
            </button>
            <button @click="handleInteract(currentPost, 'dislike')" class="flex-1 py-3 rounded-xl border border-slate-700 bg-slate-800/50 hover:bg-slate-700 transition-all flex items-center justify-center group">
              <ThumbsDown :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="currentPost.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'" />
              <span class="font-medium" :class="currentPost.has_disliked ? 'text-slate-400' : 'text-slate-300'">{{ currentPost.dislikes_count }}</span>
            </button>
          </div>
          
          <div class="mt-8">
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
