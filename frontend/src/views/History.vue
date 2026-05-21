<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import LazyVideo from '@/components/LazyVideo.vue'
import { Image as ImageIcon, Video, Clock, Download, Compass, Star, Trash2, Upload } from 'lucide-vue-next'
import dayjs from 'dayjs'
import { useViewport } from '@/composables/useViewport'
import { useTasksStore } from '@/stores/tasks'
import { useTaskFormat } from '@/composables/useTaskFormat'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { isMobile } = useViewport()
const tasksStore = useTasksStore()
const { getTypeLabel, getFileUrl, isVideoFile } = useTaskFormat()

const getThumbnailUrl = (output_file: string) => {
  if (!output_file) return ''
  
  // Split URL and query parameters to avoid truncating signatures
  const [pathPart, queryPart] = output_file.split('?')
  
  const isVideo = isVideoFile(pathPart)
  const lastDotIndex = pathPart.lastIndexOf('.')
  const basePath = lastDotIndex !== -1 ? pathPart.substring(0, lastDotIndex) : pathPart
  
  const newPath = isVideo ? `${basePath}_thumb.jpg` : `${basePath}_thumb.webp`
  const thumbUrl = queryPart ? `${newPath}?${queryPart}` : newPath
  
  return getFileUrl(thumbUrl)
}

const handleImageError = (e: Event, record: any) => {
  const img = e.target as HTMLImageElement
  if (!img.dataset.fallbackAttempted && record.output_file && !isVideoFile(record.output_file)) {
    img.dataset.fallbackAttempted = 'true'
    img.src = record.output_file_url || getFileUrl(record.output_file)
    img.style.opacity = '1'
  } else {
    img.style.opacity = '0.3'
  }
}

const data = ref<any[]>([])
const loading = ref(false)

const pagination = ref({
  current: 1,
  pageSize: 8,
  total: 0,
  hideOnSinglePage: true // Hide pagination since we only ever show max 8 items now
})

const openDetail = (record: any) => {
  tasksStore.showDetailRecord(record)
}

const fetchHistory = async (page = 1) => {
  loading.value = true
  try {
    const res = await api.get('/users/history', {
      params: { page, size: pagination.value.pageSize }
    })
    data.value = res.data.items
    pagination.value.total = res.data.total
    pagination.value.current = res.data.page
    
    // Check if we need to auto-open a specific task detail
    if (route.query.task_id) {
      const targetId = route.query.task_id as string
      const targetRecord = data.value.find(item => item.task_id === targetId)
      if (targetRecord) {
        openDetail(targetRecord)
      } else if (page === 1) {
        // If not found on first page, just call store to fetch and open
        tasksStore.openDetailModal(targetId)
      }
      // Remove query param so it doesn't reopen on refresh
      router.replace({ query: {} })
    }
  } catch (error) {
    console.error('Failed to fetch history:', error)
  } finally {
    loading.value = false
  }
}

const handleDelete = async (record: any, event?: Event) => {
  if (event) event.stopPropagation()
  
  Modal.confirm({
    title: '确认删除',
    content: '确认删除该记录吗？（若已发布至广场也将同步下架）',
    okText: '确认',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await api.delete(`/users/history/${record.id}`)
        message.success('删除成功')
        data.value = data.value.filter(item => item.id !== record.id)
        if (tasksStore.detailModalVisible && tasksStore.currentDetailRecord?.id === record.id) {
          tasksStore.closeDetailModal()
        }
      } catch (error: any) {
        console.error(error)
        message.error(error.response?.data?.detail || '删除失败，请稍后再试')
      }
    }
  })
}

onMounted(() => {
  fetchHistory()
})

watch(() => route.query.task_id, (newTaskId) => {
  if (newTaskId) {
    const targetRecord = data.value.find(item => item.task_id === newTaskId)
    if (targetRecord) {
      openDetail(targetRecord)
      router.replace({ query: {} })
    } else {
      // If not in current data, use store action to fetch
      tasksStore.openDetailModal(newTaskId as string)
      router.replace({ query: {} })
    }
  }
})
</script>

<template>
  <div class="history-container p-4 sm:p-6 rounded-xl text-slate-200">
    <div class="flex justify-between items-center mb-6">
      <h2 class="text-2xl font-bold drop-shadow-sm">{{ $t('history.title') }}</h2>
      <a-button class="bg-slate-500 text-cyan-200 border-cyan-500/30 hover:bg-slate-500 hover:text-white hover:border-cyan-400" @click="fetchHistory(1)">{{ $t('history.refresh') }}</a-button>
    </div>

    <!-- Privacy and Convenience Notice -->
    <div class="mb-6 bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-4 flex items-start">
      <div class="text-indigo-400 mr-3 mt-0.5"><Clock :size="18" /></div>
      <div class="text-slate-300 text-sm leading-relaxed">
        {{ $t('history.warning', { max: 8 }) }}
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="py-8 text-center">
      <div class="inline-block w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
    </div>

    <!-- Empty State -->
    <div v-else-if="data.length === 0" class="py-20 text-center text-slate-500">
      <Compass :size="48" class="mx-auto mb-4 opacity-20" />
      <p>暂无记录</p>
    </div>

    <!-- Cards Grid -->
    <div v-else class="columns-2 md:columns-4 gap-3 sm:gap-6">
      <div
        v-for="record in data"
        :key="record.id"
        class="mb-3 sm:mb-6 break-inside-avoid rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-400/50 bg-slate-800 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
        @click="openDetail(record)"
      >
        <!-- Media -->
        <div class="relative w-full overflow-hidden aspect-auto min-h-[120px] flex items-center justify-center bg-slate-900">
          <!-- Delete Button (Top Left) -->
          <button
            class="absolute top-2 left-2 bg-black/60 hover:bg-red-500/80 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10 z-20 text-slate-300 hover:text-white transition-colors opacity-0 group-hover:opacity-100"
            @click="handleDelete(record, $event)"
            title="删除"
          >
            <Trash2 :size="14" />
          </button>
          <template v-if="record.output_file">
            <img
              :src="record.thumbnail_url || getThumbnailUrl(record.output_file)"
              @error="handleImageError($event, record)"
              class="w-full h-auto object-cover min-h-[120px] transition-opacity duration-300"
              loading="lazy"
            />
            <!-- Play Icon Overlay for Videos -->
            <div v-if="isVideoFile(record.output_file)" class="absolute inset-0 flex items-center justify-center pointer-events-none opacity-80 group-hover:opacity-0 transition-opacity duration-300">
              <div class="w-12 h-12 bg-black/50 backdrop-blur-md rounded-full flex items-center justify-center border border-white/20 shadow-lg">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-white ml-1"><polygon points="6 3 20 12 6 21 6 3"></polygon></svg>
              </div>
            </div>
          </template>
          <div v-else class="py-10 text-slate-500 italic text-sm">无文件</div>

          <!-- Video Icon Badge (Top Right) -->
          <div v-if="record.output_file && isVideoFile(record.output_file)" class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10 z-10">
            <Video :size="14" class="text-indigo-400" />
          </div>

          <!-- Tags Overlay (Always Visible, Bottom) -->
          <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent p-2.5 pt-8 z-10">
            <div class="flex justify-between items-end">
              <div class="flex flex-col gap-1.5 items-start">
                <span class="text-[11px] px-2 py-0.5 rounded-md backdrop-blur-md flex items-center border border-white/20 shadow-sm"
                      :class="record.type === 'face_video' ? 'bg-blue-500/40 text-blue-100' : (record.type === 'face_swap' ? 'bg-purple-500/40 text-purple-100' : 'bg-cyan-500/40 text-cyan-100')">
                  <Video v-if="record.type === 'face_video'" :size="12" class="mr-1 text-blue-300" />
                  <ImageIcon v-else :size="12" class="mr-1 text-cyan-300" />
                  {{ getTypeLabel(record.type) }}
                </span>
                <span class="text-[10px] px-2 py-0.5 rounded-md backdrop-blur-md border border-white/10 shadow-sm"
                      :class="record.source === 'web' ? 'bg-green-500/40 text-green-100' : 'bg-orange-500/40 text-orange-100'">
                  <span v-if="record.source === 'web'">🌐 {{ $t('history.web_creation') }}</span>
                  <span v-else>🤖 {{ $t('history.bot_creation') }}</span>
                </span>
              </div>
              
              <!-- 投稿状态 -->
              <span v-if="['i2i_pro', 'i2i_draw', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video'].includes(record.type) && record.allow_contribute !== false"
                    class="text-[10px] px-2 py-0.5 rounded-full backdrop-blur-md border border-white/20 shadow-sm whitespace-nowrap ml-1"
                    :class="record.is_public ? 'bg-indigo-500/40 text-indigo-100' : 'bg-slate-500/40 text-slate-200'">
                {{ record.is_public ? '已投稿' : '未投稿' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-container {
  min-height: 100%;
}
</style>
