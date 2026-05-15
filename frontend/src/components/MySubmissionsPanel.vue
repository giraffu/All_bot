<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import {
  ChevronLeft,
  ChevronRight,
  Compass,
  Copy,
  Eye,
  EyeOff,
  Heart,
  Image as ImageIcon,
  ThumbsDown,
  Trash2,
  Video,
  Wand2,
} from 'lucide-vue-next'
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
}

const router = useRouter()
const { t } = useI18n()
const posts = ref<Post[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const hasMore = ref(true)
const detailVisible = ref(false)
const currentPost = ref<Post | null>(null)
const applying = ref(false)
const interactingPosts = ref<Record<number, boolean>>({})

const currentIndex = computed(() => {
  if (!currentPost.value) return -1
  return posts.value.findIndex((post) => post.id === currentPost.value?.id)
})

const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(
  () => currentIndex.value >= 0 && currentIndex.value < posts.value.length - 1,
)

const goPrev = () => {
  if (hasPrev.value) {
    currentPost.value = posts.value[currentIndex.value - 1]
  }
}

const goNext = () => {
  if (hasNext.value) {
    currentPost.value = posts.value[currentIndex.value + 1]
    if (currentIndex.value >= posts.value.length - 3 && hasMore.value) {
      void loadPosts()
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
    const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl

    if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
      if (!path.includes('/')) {
        url = `${base}/comfyui-temp/${path}`
      } else {
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

const isVideoFile = (path: string, mediaType?: string) => {
  if (mediaType) {
    return mediaType === 'video'
  }
  if (!path) return false
  const lowerPath = path.toLowerCase()
  return (
    lowerPath.endsWith('.mp4') ||
    lowerPath.endsWith('.mov') ||
    lowerPath.endsWith('.webm') ||
    lowerPath.endsWith('.mkv') ||
    lowerPath.endsWith('.avi')
  )
}

let currentRequestId = 0

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
    const res = await api.get('/gallery/my-posts', {
      params: {
        page: page.value,
        size: size.value,
      },
    })

    if (requestId !== currentRequestId) return

    if (reset) {
      posts.value = res.data.items
    } else {
      posts.value = [...posts.value, ...res.data.items]
    }

    if (page.value >= res.data.pages) {
      hasMore.value = false
    } else {
      page.value++
    }
  } catch (error) {
    if (requestId !== currentRequestId) return
    console.error(error)
    message.error(t('my_notes.load_failed'))
  } finally {
    if (requestId === currentRequestId) {
      loading.value = false
    }
  }
}

const handleInteract = async (post: Post, action: 'like' | 'dislike') => {
  if (interactingPosts.value[post.id]) return

  interactingPosts.value[post.id] = true
  try {
    const { data: resData } = await api.post(`/gallery/posts/${post.id}/interact`, null, {
      params: { action },
    })

    const result = resData.data
    const actionState = result.action_state

    post.likes_count = result.likes_count
    post.dislikes_count = result.dislikes_count

    if (actionState === 'added') {
      if (action === 'like') post.has_liked = true
      else post.has_disliked = true
      message.success(action === 'like' ? t('my_notes.like_added') : t('my_notes.dislike_added'))
    } else if (actionState === 'canceled') {
      if (action === 'like') post.has_liked = false
      else post.has_disliked = false
      message.success(action === 'like' ? t('my_notes.like_removed') : t('my_notes.dislike_removed'))
    } else if (actionState === 'switched') {
      if (action === 'like') {
        post.has_liked = true
        post.has_disliked = false
      } else {
        post.has_disliked = true
        post.has_liked = false
      }
      message.success(action === 'like' ? t('my_notes.like_added') : t('my_notes.dislike_added'))
    }
  } catch (error) {
    console.error(error)
  } finally {
    interactingPosts.value[post.id] = false
  }
}

const openDetail = (post: Post) => {
  currentPost.value = post
  detailVisible.value = true
}

const toggleStatus = async (post: Post) => {
  try {
    const newStatus = !post.is_active
    await api.put(`/gallery/posts/${post.id}/status`, null, {
      params: { is_active: newStatus },
    })
    post.is_active = newStatus
    message.success(newStatus ? t('my_notes.submission_published') : t('my_notes.submission_unpublished'))
  } catch (error) {
    console.error(error)
    message.error(t('my_notes.action_failed'))
  }
}

const deletePost = async (post: Post) => {
  if (!window.confirm(t('my_notes.confirm_delete_submission'))) return

  try {
    await api.delete(`/gallery/posts/${post.id}`)
    posts.value = posts.value.filter((item) => item.id !== post.id)
    message.success(t('my_notes.delete_success'))
    if (currentPost.value?.id === post.id) {
      detailVisible.value = false
    }
  } catch (error) {
    console.error(error)
    message.error(t('my_notes.delete_failed'))
  }
}

const copyPrompt = (post: Post) => {
  const prompt = post.prompt?.trim()
  if (!prompt) {
    message.warning(t('my_notes.prompt_empty'))
    return
  }

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard
      .writeText(prompt)
      .then(() => {
        message.success(t('my_notes.prompt_copied'))
      })
      .catch((error) => {
        console.error('Clipboard API failed:', error)
        fallbackCopyPrompt(prompt)
      })
    return
  }

  fallbackCopyPrompt(prompt)
}

const fallbackCopyPrompt = (text: string) => {
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'

    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()

    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)

    if (successful) {
      message.success(t('my_notes.prompt_copied'))
    } else {
      message.error(t('my_notes.copy_failed'))
    }
  } catch (error) {
    console.error('Fallback copy failed:', error)
    message.error(t('my_notes.copy_failed'))
  }
}

const handleApply = async () => {
  if (!currentPost.value || applying.value) return
  applying.value = true

  try {
    const res = await api.get(`/gallery/posts/${currentPost.value.id}/apply-context`)
    const context = res.data
    detailVisible.value = false
    sessionStorage.setItem('galleryApplyContext', JSON.stringify(context))

    const featureMap: Record<string, { route: string; title: string; cost: number }> = {
      i2i_pro: { route: 'ImageAndPrompt', title: '幻想换脸', cost: 6 },
      i2i_draw: { route: 'ImageAndPrompt', title: '局部重绘', cost: 3 },
      edit: { route: 'ImageAndPrompt', title: '自由P图', cost: 2 },
      img2img_lora: { route: 'ImageAndPrompt', title: '图生图(附加模型)', cost: 2 },
      face_swap: { route: 'FaceSwap', title: '快速换脸', cost: 1 },
      face_video: { route: 'VideoSwap', title: '视频换脸', cost: 18 },
      custom_video: { route: 'SingleImageToVideo', title: '自定义图生视频', cost: 6 },
      video_lora: { route: 'SingleImageToVideo', title: '图生视频(附加模型)', cost: 6 },
      ltx_video: { route: 'SingleImageToVideo', title: '高级图生视频', cost: 10 },
    }

    const featureInfo = featureMap[context.task_type]
    if (featureInfo) {
      message.success(t('my_notes.template_loaded_with_upload_hint'))
      void router.push({
        name: featureInfo.route,
        query: {
          apply: 'true',
          type: context.task_type,
          title: featureInfo.title,
          cost: featureInfo.cost,
        },
      })
    } else {
      message.success(t('my_notes.template_loaded'))
      void router.push({ name: 'CustomFeatures', query: { apply: 'true' } })
    }
  } catch (error) {
    console.error(error)
    message.error(t('my_notes.template_load_failed'))
  } finally {
    applying.value = false
  }
}

const handleScroll = () => {
  const container = document.querySelector('.ant-layout-content')
  if (!container) return

  const { scrollTop, scrollHeight, clientHeight } = container
  if (scrollHeight - scrollTop - clientHeight < 200) {
    void loadPosts()
  }
}

const handleImageError = (event: Event, post: Post) => {
  const img = event.target as HTMLImageElement

  if (!img.dataset.fallbackAttempted && post.media_url && !isVideoFile(post.media_url, post.media_type)) {
    img.dataset.fallbackAttempted = 'true'
    img.src = post.media_url.includes('X-Amz-Signature')
      ? post.media_url
      : getFileUrl(post.media_url, post.id)
    img.style.opacity = '1'
  } else {
    img.style.opacity = '0.3'
  }
}

onMounted(() => {
  void loadPosts(true)
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
    <div class="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-6 space-y-6">
      <div
        v-for="post in posts"
        :key="post.id"
        class="break-inside-avoid rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-400/50 bg-slate-500/40 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
        @click="openDetail(post)"
      >
        <div class="relative w-full overflow-hidden bg-slate-500 aspect-auto min-h-[100px]">
          <img
            :src="getFileUrl(post.thumbnail_url, post.id)"
            @error="handleImageError($event, post)"
            class="w-full h-auto object-cover transition-opacity duration-300"
            loading="lazy"
          />

          <div
            v-if="isVideoFile(post.thumbnail_url, post.media_type)"
            class="absolute inset-0 flex items-center justify-center pointer-events-none opacity-80 group-hover:opacity-0 transition-opacity duration-300"
          >
            <div class="w-12 h-12 bg-black/50 backdrop-blur-md rounded-full flex items-center justify-center border border-white/20 shadow-lg">
              <Video :size="24" class="text-white" />
            </div>
          </div>

          <div class="absolute top-2 left-2 flex items-center gap-2">
            <div
              class="bg-black/60 backdrop-blur-sm rounded-full px-2 py-1 shadow-sm border border-white/10 text-xs font-bold"
              :class="post.is_active ? 'text-green-400' : 'text-orange-400'"
            >
              {{ post.is_active ? t('my_posts.on_shelf') : t('my_posts.off_shelf') }}
            </div>
          </div>

          <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10">
            <ImageIcon v-if="!isVideoFile(post.thumbnail_url, post.media_type)" :size="14" class="text-cyan-400" />
            <Video v-else :size="14" class="text-indigo-400" />
          </div>

          <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-between p-4">
            <div class="flex justify-end gap-2">
              <button
                @click.stop="toggleStatus(post)"
                class="p-2 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm transition-all"
                :title="post.is_active ? t('my_posts.put_off_shelf') : t('my_posts.put_on_shelf')"
              >
                <Eye v-if="post.is_active" :size="16" class="text-green-400" />
                <EyeOff v-else :size="16" class="text-orange-400" />
              </button>
              <button
                @click.stop="deletePost(post)"
                class="p-2 rounded-full bg-black/50 hover:bg-red-500/80 text-white backdrop-blur-sm transition-all"
                :title="t('my_posts.delete')"
              >
                <Trash2 :size="16" />
              </button>
            </div>

            <div class="flex flex-wrap gap-1.5 mb-8">
              <span
                v-for="tag in post.tags.slice(0, 4)"
                :key="tag"
                class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md"
              >
                {{ formatTag(tag) }}
              </span>
              <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
            </div>
          </div>
        </div>

        <div class="absolute bottom-0 left-0 right-0 p-3 bg-black/60 backdrop-blur-md border-t border-white/10 flex justify-between items-center z-10 translate-y-0">
          <div class="flex items-center space-x-3">
            <div class="flex items-center text-slate-300 hover:text-pink-400 transition-colors" @click.stop="handleInteract(post, 'like')">
              <Heart :size="14" class="mr-1" :class="{ 'fill-pink-500 text-pink-500': post.has_liked }" />
              <span class="text-xs font-medium">{{ post.likes_count }}</span>
            </div>
            <div class="flex items-center text-slate-300 hover:text-slate-100 transition-colors" @click.stop="handleInteract(post, 'dislike')">
              <ThumbsDown :size="14" class="mr-1" :class="{ 'fill-slate-400 text-slate-400': post.has_disliked }" />
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

    <div v-if="loading" class="py-8 text-center">
      <div class="inline-block w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
    </div>

    <div v-if="!loading && posts.length === 0" class="py-20 text-center text-slate-500">
      <Compass :size="48" class="mx-auto mb-4 opacity-20" />
      <p>{{ t('my_posts.no_submissions') }}</p>
    </div>

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
      <div
        v-if="currentPost"
        class="flex flex-col lg:flex-row bg-[#0f172a] rounded-2xl overflow-hidden border border-slate-400/50 shadow-2xl"
      >
        <div class="lg:w-2/3 bg-black flex items-center justify-center relative min-h-[300px] group/media">
          <template v-if="currentPost.media_url">
            <img
              v-if="!isVideoFile(currentPost.media_url, currentPost.media_type)"
              :src="getFileUrl(currentPost.media_url, currentPost.id)"
              class="max-w-full max-h-[65vh] lg:max-h-[80vh] object-contain"
            />
            <video
              v-else
              :src="getFileUrl(currentPost.media_url, currentPost.id)"
              class="max-w-full max-h-[65vh] lg:max-h-[80vh] object-contain"
              controls
              autoplay
              loop
              playsinline
            ></video>
          </template>

          <button
            v-if="hasPrev"
            @click.stop="goPrev"
            class="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 sm:w-12 sm:h-12 bg-black/40 hover:bg-black/60 rounded-full flex items-center justify-center text-white/80 hover:text-white transition-all z-20 border border-white/10 backdrop-blur-sm opacity-100 lg:opacity-0 lg:group-hover/media:opacity-100"
          >
            <ChevronLeft :size="24" />
          </button>
          <button
            v-if="hasNext"
            @click.stop="goNext"
            class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 sm:w-12 sm:h-12 bg-black/40 hover:bg-black/60 rounded-full flex items-center justify-center text-white/80 hover:text-white transition-all z-20 border border-white/10 backdrop-blur-sm opacity-100 lg:opacity-0 lg:group-hover/media:opacity-100"
          >
            <ChevronRight :size="24" />
          </button>
        </div>

        <div class="lg:w-1/3 p-4 flex flex-col bg-slate-500/80 backdrop-blur-xl relative max-h-[50vh] lg:max-h-none overflow-y-auto">
          <button
            @click="detailVisible = false"
            class="absolute top-3 right-3 text-slate-400 hover:text-white transition-colors z-10 bg-black/50 p-1.5 rounded-full"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>

          <div class="flex justify-between items-start mb-3">
            <h3 class="text-lg font-bold text-slate-100 flex items-center">
              <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">
                {{ t('gallery.modal.title') }}
              </span>
            </h3>

            <div class="text-xs text-slate-400 flex items-center gap-3 mr-8">
              <span v-if="currentPost.width" class="bg-slate-500/80 px-2 py-1 rounded">
                📏 {{ currentPost.width }}x{{ currentPost.height }}
              </span>
              <span v-if="currentPost.created_at" class="bg-slate-500/80 px-2 py-1 rounded">
                📅 {{ dayjs(currentPost.created_at).format('MM-DD HH:mm') }}
              </span>
            </div>
          </div>

          <div v-if="currentPost.tags && currentPost.tags.length > 0" class="mb-4">
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="tag in currentPost.tags"
                :key="tag"
                class="text-[11px] bg-slate-500 text-cyan-200 border border-slate-400 px-2 py-0.5 rounded"
              >
                {{ tag.startsWith('#') ? formatTag(tag) : '#' + formatTag(tag) }}
              </span>
            </div>
          </div>

          <div class="flex space-x-3 mb-4">
            <button
              @click="handleInteract(currentPost, 'like')"
              class="flex-1 py-2 rounded-lg border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group"
            >
              <Heart
                :size="16"
                class="mr-1.5 transition-transform group-hover:scale-110"
                :class="currentPost.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'"
              />
              <span class="text-sm font-medium" :class="currentPost.has_liked ? 'text-pink-400' : 'text-slate-300'">
                {{ currentPost.likes_count }}
              </span>
            </button>
            <button
              @click="handleInteract(currentPost, 'dislike')"
              class="flex-1 py-2 rounded-lg border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group"
            >
              <ThumbsDown
                :size="16"
                class="mr-1.5 transition-transform group-hover:scale-110"
                :class="currentPost.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'"
              />
              <span
                class="text-sm font-medium"
                :class="currentPost.has_disliked ? 'text-slate-400' : 'text-slate-300'"
              >
                {{ currentPost.dislikes_count }}
              </span>
            </button>
          </div>

          <div class="flex space-x-3 mb-5 border-b border-slate-400/50 pb-4">
            <button
              @click="toggleStatus(currentPost)"
              class="flex-1 py-2 rounded-lg border border-slate-400 bg-slate-500 hover:bg-slate-500 transition-all flex items-center justify-center text-xs font-medium"
              :class="currentPost.is_active ? 'text-orange-400' : 'text-green-400'"
            >
              <EyeOff v-if="currentPost.is_active" :size="14" class="mr-1.5" />
              <Eye v-else :size="14" class="mr-1.5" />
              {{ currentPost.is_active ? t('my_posts.put_off_shelf') : t('my_posts.put_on_shelf') }}
            </button>
            <button
              @click="deletePost(currentPost)"
              class="flex-1 py-2 rounded-lg border border-red-900/30 bg-red-900/10 hover:bg-red-900/30 transition-all flex items-center justify-center text-xs font-medium text-red-400"
            >
              <Trash2 :size="14" class="mr-1.5" />
              {{ t('my_posts.delete') }}
            </button>
          </div>

          <div class="mt-auto space-y-3">
            <button
              v-if="currentPost.prompt?.trim()"
              @click="copyPrompt(currentPost)"
              class="w-full py-2.5 rounded-lg bg-slate-500 hover:bg-slate-500 text-white text-sm font-medium shadow-sm transition-all flex items-center justify-center border border-slate-400"
            >
              <Copy :size="16" class="mr-1.5" />
              {{ t('my_posts.copy_prompt') }}
            </button>
            <button
              @click="handleApply"
              :disabled="applying"
              class="w-full py-3 rounded-lg bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-bold shadow-md transition-all transform hover:scale-[1.02] flex items-center justify-center relative overflow-hidden group"
            >
              <div class="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
              <Wand2 v-if="!applying" :size="18" class="mr-2 relative z-10" />
              <div v-else class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2 relative z-10"></div>
              <span class="relative z-10">{{ applying ? '...' : t('gallery.modal.apply_btn') }}</span>
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
