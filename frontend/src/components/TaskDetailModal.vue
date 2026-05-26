<script setup lang="ts">
import { computed } from 'vue'
import { Image as ImageIcon, Video, Clock, Download, Star, Trash2, Upload, Send } from 'lucide-vue-next'
import { useViewport } from '@/composables/useViewport'
import { useTasksStore } from '@/stores/tasks'
import { useTaskFormat } from '@/composables/useTaskFormat'
import { useTaskInteraction } from '@/composables/useTaskInteraction'
import { useI18n } from 'vue-i18n'

const { isMobile } = useViewport()
const { t } = useI18n()
const tasksStore = useTasksStore()

const { formatDate, getTypeLabel, getFileUrl, isVideoFile } = useTaskFormat()

const detailVisible = computed({
  get: () => tasksStore.detailModalVisible,
  set: (val) => {
    if (val) {
      return
    }
    tasksStore.closeDetailModal()
  }
})

const currentRecord = computed(() => tasksStore.currentDetailRecord)

const {
  submittingTasks,
  submitToGallery,
  handleFavorite,
  handleDelete,
  handleDownload,
  handleSendToBot
} = useTaskInteraction({
  onDeleteSuccess: (record) => {
    // If the currently viewed record is deleted, close the modal
    if (currentRecord.value?.id === record.id) {
      detailVisible.value = false
    }
  }
})

</script>

<template>
  <a-modal
    v-model:open="detailVisible"
    :footer="null"
    :closable="false"
    :width="isMobile ? '100%' : '90%'"
    :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { maxWidth: '1000px', top: '20px' }"
    :wrapClassName="isMobile ? 'mobile-full-modal' : ''"
    class="history-detail-modal"
    :bodyStyle="isMobile ? { padding: 0, backgroundColor: '#0f172a', height: '100vh', overflowY: 'auto' } : { padding: 0, backgroundColor: 'transparent' }"
    destroyOnClose
  >
    <div v-if="currentRecord" class="flex flex-col lg:flex-row bg-[#0f172a] lg:rounded-2xl overflow-hidden border-none lg:border lg:border-slate-400/50 lg:shadow-2xl min-h-[100vh] lg:min-h-0">
      
      <!-- Mobile Header (Back Button) -->
      <div class="lg:hidden absolute top-0 left-0 right-0 z-50 p-4 flex justify-between items-center bg-gradient-to-b from-black/60 to-transparent pointer-events-none">
        <button @click="detailVisible = false" class="text-white bg-black/40 backdrop-blur-md p-2 rounded-full flex items-center justify-center pointer-events-auto">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
      </div>

      <!-- Media Area -->
      <div class="w-full lg:w-2/3 bg-black flex items-center justify-center relative min-h-[60vh] lg:min-h-[300px]">
        <template v-if="currentRecord.output_file">
          <video v-if="isVideoFile(currentRecord.output_file)" :src="currentRecord.output_file_url || getFileUrl(currentRecord.output_file)" class="w-full h-auto lg:max-w-full lg:max-h-[80vh] lg:object-contain object-cover" controls autoplay loop playsinline></video>
          <img v-else :src="currentRecord.output_file_url || getFileUrl(currentRecord.output_file)" class="w-full h-auto lg:max-w-full lg:max-h-[80vh] lg:object-contain object-cover" />
        </template>
        <div v-else class="text-slate-500">无文件</div>
      </div>

      <!-- Info Area -->
      <div class="w-full lg:w-1/3 flex flex-col bg-[#0f172a] lg:bg-slate-500/80 lg:backdrop-blur-xl relative pb-[120px] lg:pb-0">
        <!-- Desktop Close button -->
        <button @click="detailVisible = false" class="hidden lg:block absolute top-4 right-4 text-slate-400 hover:text-white transition-colors z-10">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>

        <div class="p-4 lg:p-6 flex-1 flex flex-col">
          <h3 class="text-lg lg:text-xl font-bold text-slate-100 mb-4 flex items-center mt-0 lg:mt-2">
            <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">作品详情</span>
          </h3>

          <div class="space-y-4 lg:space-y-6 mb-6 lg:mb-8">
            <!-- Labels -->
            <div>
              <div class="text-[10px] lg:text-xs text-slate-400 mb-1.5 lg:mb-2 uppercase tracking-wider">类型标签</div>
              <div class="flex flex-wrap gap-1.5 lg:gap-2">
                <span class="text-xs px-2 py-0.5 lg:text-sm lg:px-3 lg:py-1 rounded-md border border-white/20 bg-black/40 text-white flex items-center shadow-sm">
                  <Video v-if="currentRecord.type === 'face_video'" :size="isMobile ? 12 : 14" class="mr-1 lg:mr-1.5 text-blue-400" />
                  <ImageIcon v-else :size="isMobile ? 12 : 14" class="mr-1 lg:mr-1.5 text-cyan-400" />
                  {{ getTypeLabel(currentRecord.type) }}
                </span>
                <span class="text-xs px-2 py-0.5 lg:text-sm lg:px-3 lg:py-1 rounded-md border border-white/10"
                      :class="currentRecord.source === 'web' ? 'bg-green-500/30 text-green-100' : 'bg-orange-500/30 text-orange-100'">
                  {{ currentRecord.source === 'web' ? '🌐 ' + $t('history.web_creation') : '🤖 ' + $t('history.bot_creation') }}
                </span>
              </div>
            </div>

            <!-- Time -->
            <div>
              <div class="text-[10px] lg:text-xs text-slate-400 mb-1.5 lg:mb-2 uppercase tracking-wider">创建时间</div>
              <div class="flex items-center text-slate-300 text-xs lg:text-sm bg-black/20 w-fit px-2 py-1 lg:px-3 lg:py-1.5 rounded-lg border border-slate-500/30">
                <Clock :size="isMobile ? 14 : 16" class="mr-1.5 lg:mr-2 text-cyan-400" />
                {{ formatDate(currentRecord.created_at) }}
              </div>
            </div>
          </div>

          <!-- Desktop Actions -->
          <div class="hidden lg:flex mt-auto flex-col space-y-3 pt-6">
            <template v-if="currentRecord.output_file">
              <a-button
                v-if="['txt2img', 'i2i_pro', 'i2i_draw', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video'].includes(currentRecord.type) && currentRecord.allow_contribute !== false"
                type="primary"
                :disabled="currentRecord.is_public"
                class="w-full h-12 border-none rounded-xl text-base font-medium flex items-center justify-center"
                :class="currentRecord.is_public ? 'bg-indigo-500/50 text-indigo-100 cursor-not-allowed' : 'bg-gradient-to-r from-cyan-600 to-indigo-600 shadow-[0_0_15px_rgba(56,189,248,0.3)] hover:scale-[1.02] transition-transform'"
                :loading="submittingTasks[currentRecord.task_id]"
                @click="!currentRecord.is_public && submitToGallery(currentRecord)"
              >
                {{ currentRecord.is_public ? '已投稿' : (submittingTasks[currentRecord.task_id] ? $t('history.submitting') : $t('history.submit')) }}
              </a-button>
              <div v-else class="w-full h-12 bg-slate-600/30 border border-slate-500/30 rounded-xl text-slate-400 flex items-center justify-center text-sm">
                {{ $t('history.cannot_post') }}
              </div>

              <a-button
                ghost
                class="w-full h-12 border-slate-500/50 hover:bg-slate-500/30 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                :class="currentRecord.is_favorited ? 'text-slate-400 cursor-not-allowed' : 'text-amber-400 hover:text-amber-300 hover:border-amber-400/50'"
                @click="!currentRecord.is_favorited && handleFavorite(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Star :size="18" class="mr-2" :class="{ 'fill-current': currentRecord.is_favorited }" />
                  {{ currentRecord.is_favorited ? '已收藏' : '收藏' }}
                </span>
              </a-button>

              <a-button
                ghost
                class="w-full h-12 text-cyan-400 border-cyan-500/50 hover:text-cyan-300 hover:border-cyan-400 hover:bg-cyan-500/10 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                @click="handleDownload(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Download :size="18" class="mr-2" />
                  {{ $t('history.save') }}
                </span>
              </a-button>

              <a-button
                ghost
                class="w-full h-12 text-indigo-400 border-indigo-500/50 hover:text-indigo-300 hover:border-indigo-400 hover:bg-indigo-500/10 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                @click="handleSendToBot(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Send :size="18" class="mr-2" />
                  发送至私聊
                </span>
              </a-button>

              <a-button
                ghost
                class="w-full h-12 text-red-400 border-red-500/50 hover:text-red-300 hover:border-red-400 hover:bg-red-500/10 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center mt-3"
                @click="handleDelete(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Trash2 :size="18" class="mr-2" />
                  删除
                </span>
              </a-button>
            </template>
            <div v-else class="text-center text-slate-500 italic py-4 border border-dashed border-slate-600 rounded-xl">暂无文件可操作</div>
          </div>
        </div>
      </div>

      <!-- Mobile Bottom Interaction Bar -->
      <div class="lg:hidden fixed bottom-0 left-0 right-0 bg-[#0f172a]/95 backdrop-blur-lg border-t border-slate-800 px-4 py-2 pb-6 flex items-center justify-between z-50 safe-area-bottom">
        <template v-if="currentRecord.output_file">
          <div class="flex gap-6">
            <button class="flex flex-col items-center justify-center gap-1 transition-colors" :class="currentRecord.is_favorited ? 'text-amber-400' : 'text-slate-400 hover:text-slate-200'" @click="!currentRecord.is_favorited && handleFavorite(currentRecord)">
              <Star :size="20" :class="{ 'fill-current': currentRecord.is_favorited }" />
              <span class="text-[10px]">{{ currentRecord.is_favorited ? '已收藏' : '收藏' }}</span>
            </button>
            <button class="flex flex-col items-center justify-center gap-1 text-slate-400 hover:text-slate-200 transition-colors" @click="handleDownload(currentRecord)">
              <Download :size="20" />
              <span class="text-[10px]">保存</span>
            </button>
            <button class="flex flex-col items-center justify-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors" @click="handleSendToBot(currentRecord)">
              <Send :size="20" />
              <span class="text-[10px]">发私聊</span>
            </button>
            <button class="flex flex-col items-center justify-center gap-1 text-slate-400 hover:text-red-400 transition-colors" @click="handleDelete(currentRecord)">
              <Trash2 :size="20" />
              <span class="text-[10px]">删除</span>
            </button>
          </div>
          
          <button 
            v-if="['txt2img', 'i2i_pro', 'i2i_draw', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video'].includes(currentRecord.type) && currentRecord.allow_contribute !== false"
            @click="!currentRecord.is_public && submitToGallery(currentRecord)"
            :disabled="currentRecord.is_public || submittingTasks[currentRecord.task_id]"
            class="px-5 py-2 rounded-full font-medium text-sm transition-all flex items-center justify-center min-w-[100px]"
            :class="currentRecord.is_public ? 'bg-indigo-500/30 text-indigo-200' : 'bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg hover:shadow-cyan-500/25'"
          >
            <div v-if="submittingTasks[currentRecord.task_id]" class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1.5"></div>
            <Upload v-else-if="!currentRecord.is_public" :size="16" class="mr-1.5" />
            <span>{{ currentRecord.is_public ? '已投稿' : (submittingTasks[currentRecord.task_id] ? '投稿中...' : '一键投稿') }}</span>
          </button>
        </template>
        <div v-else class="w-full text-center text-slate-500 text-sm py-2">暂无文件可操作</div>
      </div>

    </div>
  </a-modal>
</template>

<style>
.history-detail-modal .ant-modal-content {
  background-color: transparent !important;
  box-shadow: none !important;
}
.history-detail-modal .ant-modal-mask {
  background-color: rgba(0, 0, 0, 0.85) !important;
  backdrop-filter: blur(8px);
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
