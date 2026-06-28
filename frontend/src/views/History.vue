<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { Image as ImageIcon, Video, Clock, Trash2 } from 'lucide-vue-next'
import { useTasksStore } from '@/stores/tasks'
import { useTaskFormat } from '@/composables/useTaskFormat'
import { useHistoryRecords } from '@/composables/useHistoryRecords'
import ListStateBlock from '@/components/ListStateBlock.vue'

const route = useRoute()
const router = useRouter()
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

const handleHistoryVideoLoaded = (event: Event) => {
  const video = event.target as HTMLVideoElement
  // Freeze on the first decoded frame to avoid looping previews in the history grid.
  video.pause()
}

const {
  data,
  loading,
  openDetail,
  fetchHistory,
  handleDelete,
} = useHistoryRecords({
  route,
  router,
  tasksStore,
})
</script>

<template>
  <div class="history-container p-4 sm:p-6 rounded-xl">
    <div class="flex justify-between items-center mb-6">
      <h2 class="history-title text-2xl font-bold drop-shadow-sm">{{ $t('history.title') }}</h2>
      <a-button class="history-refresh-btn" @click="fetchHistory(1)">{{ $t('history.refresh') }}</a-button>
    </div>

    <!-- Privacy and Convenience Notice -->
    <div class="history-notice mb-6 rounded-xl p-4 flex items-start">
      <div class="history-notice-icon mr-3 mt-0.5"><Clock :size="18" /></div>
      <div class="history-notice-text text-sm leading-relaxed">
        {{ $t('history.warning', { max: 8 }) }}
      </div>
    </div>

    <ListStateBlock
      v-if="loading || data.length === 0"
      :loading="loading"
      :empty="data.length === 0"
      empty-text="暂无记录"
    />

    <!-- Cards Grid -->
    <div v-else class="columns-2 md:columns-4 gap-3 sm:gap-6">
      <div
        v-for="record in data"
        :key="record.id"
        class="history-card mb-3 sm:mb-6 break-inside-avoid rounded-2xl overflow-hidden relative group cursor-pointer transition-all duration-300"
        @click="openDetail(record)"
      >
        <!-- Media -->
        <div class="history-card-media relative w-full overflow-hidden aspect-auto min-h-[120px] flex items-center justify-center">
          <!-- Delete Button (Top Left) -->
          <button
            class="history-delete-btn absolute top-2 left-2 backdrop-blur-sm rounded-full p-1.5 shadow-sm z-20 transition-colors opacity-0 group-hover:opacity-100"
            @click="handleDelete(record, $event)"
            title="删除"
          >
            <Trash2 :size="14" />
          </button>
          <template v-if="record.output_file">
            <video
              v-if="isVideoFile(record.output_file)"
              :src="record.output_file_url || getFileUrl(record.output_file)"
              :poster="record.thumbnail_url || getThumbnailUrl(record.output_file)"
              @loadeddata="handleHistoryVideoLoaded"
              class="w-full h-auto object-cover min-h-[120px] transition-opacity duration-300 bg-black pointer-events-none"
              muted
              playsinline
              preload="auto"
            />
            <img
              v-else
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
          <div v-else class="history-empty py-10 italic text-sm">无文件</div>

          <!-- Video Icon Badge (Top Right) -->
          <div v-if="record.output_file && isVideoFile(record.output_file)" class="history-video-badge absolute top-2 right-2 backdrop-blur-sm rounded-full p-1.5 shadow-sm z-10">
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
                  {{ getTypeLabel(record.type || '') }}
                </span>
                <span class="text-[10px] px-2 py-0.5 rounded-md backdrop-blur-md border border-white/10 shadow-sm"
                      :class="record.source === 'web' ? 'bg-green-500/40 text-green-100' : 'bg-orange-500/40 text-orange-100'">
                  <span v-if="record.source === 'web'">🌐 {{ $t('history.web_creation') }}</span>
                  <span v-else>🤖 {{ $t('history.bot_creation') }}</span>
                </span>
              </div>
              
              <!-- 投稿状态 -->
              <span v-if="['txt2img', 'i2i_pro', 'i2i_draw', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'pornmaster_flux2_single_edit', 'pornmaster_flux2_multi_edit', 'ltx_video', 'scail2_action_transfer', 'scail2_action_transfer_long', 'scail2_video_replacement', 'scail2_face_swap_v2'].includes(record.type || '') && record.allow_contribute !== false"
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
  color: var(--theme-text-primary);
}

.history-title {
  color: var(--theme-text-primary);
}

.history-refresh-btn {
  background: var(--theme-pill-bg) !important;
  color: var(--theme-text-primary) !important;
  border-color: var(--theme-border-strong) !important;
}

.history-refresh-btn:hover,
.history-refresh-btn:focus {
  background: var(--theme-panel-bg) !important;
  color: var(--theme-text-primary) !important;
  border-color: var(--theme-border-strong) !important;
}

.history-notice {
  background: color-mix(in srgb, var(--theme-panel-bg) 86%, #6366f1 14%);
  border: 1px solid color-mix(in srgb, var(--theme-border) 70%, #818cf8 30%);
}

.history-notice-icon {
  color: #6366f1;
}

.history-notice-text {
  color: var(--theme-text-secondary);
}

.history-card {
  border: 1px solid var(--theme-border);
  background: var(--theme-card-bg);
  box-shadow: var(--theme-shadow);
}

.history-card:hover {
  border-color: var(--theme-border-strong);
  box-shadow: 0 8px 30px rgba(56, 189, 248, 0.12);
  transform: translateY(-0.25rem);
}

.history-card-media {
  background: var(--theme-card-strong-bg);
}

.history-delete-btn,
.history-video-badge {
  background: rgba(15, 23, 42, 0.68);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #e2e8f0;
}

.history-delete-btn:hover {
  background: rgba(239, 68, 68, 0.85);
  color: #fff;
}

.history-empty {
  color: var(--theme-text-muted);
}
</style>
