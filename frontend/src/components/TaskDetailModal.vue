<script setup lang="ts">
import { computed, ref } from 'vue'
import { Image as ImageIcon, Video, Clock, Download, Star, Trash2, Upload, Send } from 'lucide-vue-next'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { useViewport } from '@/composables/useViewport'
import { useTasksStore } from '@/stores/tasks'
import { useTaskFormat } from '@/composables/useTaskFormat'
import { useTaskInteraction } from '@/composables/useTaskInteraction'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import PromptPreviewPanel from '@/components/PromptPreviewPanel.vue'
import { useI18n } from 'vue-i18n'
import { stitchWan22HistoryChain } from '@/api/gallery'
import type { HistoryItem } from '@/types/gallery'

const { isMobile } = useViewport()
const { t } = useI18n()
const tasksStore = useTasksStore()
const router = useRouter()

const { formatDate, getTypeLabel, getFileUrl, isVideoFile } = useTaskFormat()
const { copyPrompt } = usePostPromptCopy(t)

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
const wan22ActionLoading = ref<'stitch' | null>(null)

const isWan22Record = computed(() => currentRecord.value?.type === 'wan22_video_v2')
const isWan22StitchedRecord = computed(() => Boolean(currentRecord.value?.result_meta?.wan22_is_stitched))
const canExtendWan22Chain = computed(
  () => isWan22Record.value && Boolean(currentRecord.value?.task_id && currentRecord.value?.extra_outputs?.last_frame?.path)
)
const canRegenerateWan22Segment = computed(
  () => isWan22Record.value && Boolean(currentRecord.value?.result_meta?.wan22_prev_task_id)
)
const canStitchWan22Chain = computed(
  () => isWan22Record.value && Boolean(currentRecord.value?.result_meta?.wan22_prev_task_id)
)
const canShowWan22ChainCard = computed(() => isWan22Record.value && !isWan22StitchedRecord.value)

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

const openWan22Editor = async (mode: 'extend' | 'regenerate') => {
  const record = currentRecord.value as HistoryItem | null
  if (!record?.task_id) {
    message.warning('当前记录缺少任务 ID，暂时无法继续编辑')
    return
  }
  detailVisible.value = false
  await router.push({
    name: 'Wan22VideoV2',
    query: {
      mode,
      task_id: record.task_id,
    },
  })
}

const handleWan22ChainStitch = async () => {
  const record = currentRecord.value as HistoryItem | null
  if (!record?.task_id) {
    message.warning('当前记录缺少任务 ID，暂时无法拼接')
    return
  }
  wan22ActionLoading.value = 'stitch'
  const hide = message.loading('正在拼接整条视频链...', 0)
  try {
    const stitchedRecord = await stitchWan22HistoryChain(record.task_id)
    tasksStore.showDetailRecord(stitchedRecord)
    hide()
    message.success('拼接完成，已生成新的闪回瓶记录')
  } catch (error: any) {
    console.error(error)
    hide()
    message.error(error?.response?.data?.detail || '拼接失败，请稍后再试')
  } finally {
    wan22ActionLoading.value = null
  }
}

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
    :bodyStyle="isMobile ? { padding: 0, backgroundColor: 'var(--task-detail-shell-bg)', height: '100vh', overflowY: 'auto' } : { padding: 0, backgroundColor: 'transparent' }"
    destroyOnClose
  >
    <div v-if="currentRecord" class="task-detail-shell flex flex-col lg:flex-row lg:rounded-2xl overflow-hidden border-none lg:border min-h-[100vh] lg:min-h-0">
      
      <!-- Mobile Header (Back Button) -->
      <div class="task-detail-mobile-header lg:hidden absolute top-0 left-0 right-0 z-50 p-4 flex justify-between items-center pointer-events-none">
        <button @click="detailVisible = false" class="task-detail-mobile-close p-2 rounded-full flex items-center justify-center pointer-events-auto">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
      </div>

      <!-- Media Area -->
      <div class="w-full lg:w-2/3 bg-black flex items-center justify-center relative min-h-[60vh] lg:min-h-[300px]">
        <template v-if="currentRecord.output_file">
          <video v-if="isVideoFile(currentRecord.output_file)" :src="currentRecord.output_file_url || getFileUrl(currentRecord.output_file)" class="w-full h-auto lg:max-w-full lg:max-h-[80vh] lg:object-contain object-cover" controls autoplay loop playsinline></video>
          <img v-else :src="currentRecord.output_file_url || getFileUrl(currentRecord.output_file)" class="w-full h-auto lg:max-w-full lg:max-h-[80vh] lg:object-contain object-cover" />
        </template>
        <div v-else class="task-detail-empty-file">无文件</div>
      </div>

      <!-- Info Area -->
      <div class="task-detail-info-panel w-full lg:w-1/3 flex flex-col relative pb-[120px] lg:pb-0">
        <!-- Desktop Close button -->
        <button @click="detailVisible = false" class="task-detail-desktop-close hidden lg:block absolute top-4 right-4 transition-colors z-10">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>

        <div class="p-4 lg:p-6 flex-1 flex flex-col">
          <h3 class="task-detail-title text-lg lg:text-xl font-bold mb-4 flex items-center mt-0 lg:mt-2">
            <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">作品详情</span>
          </h3>

          <div class="space-y-4 lg:space-y-6 mb-6 lg:mb-8">
            <!-- Labels -->
            <div>
              <div class="task-detail-section-label text-[10px] lg:text-xs mb-1.5 lg:mb-2 uppercase tracking-wider">类型标签</div>
              <div class="flex flex-wrap gap-1.5 lg:gap-2">
                <span class="task-detail-type-badge text-xs px-2 py-0.5 lg:text-sm lg:px-3 lg:py-1 rounded-md flex items-center shadow-sm">
                  <Video v-if="currentRecord.type === 'face_video'" :size="isMobile ? 12 : 14" class="mr-1 lg:mr-1.5 text-blue-400" />
                  <ImageIcon v-else :size="isMobile ? 12 : 14" class="mr-1 lg:mr-1.5 text-cyan-400" />
                  {{ getTypeLabel(currentRecord.type) }}
                </span>
                <span class="task-detail-source-badge text-xs px-2 py-0.5 lg:text-sm lg:px-3 lg:py-1 rounded-md border"
                      :class="currentRecord.source === 'web' ? 'is-web' : 'is-bot'">
                  {{ currentRecord.source === 'web' ? '🌐 ' + $t('history.web_creation') : '🤖 ' + $t('history.bot_creation') }}
                </span>
              </div>
            </div>

            <!-- Time -->
            <div>
              <div class="task-detail-section-label text-[10px] lg:text-xs mb-1.5 lg:mb-2 uppercase tracking-wider">创建时间</div>
              <div class="task-detail-time-badge flex items-center text-xs lg:text-sm w-fit px-2 py-1 lg:px-3 lg:py-1.5 rounded-lg">
                <Clock :size="isMobile ? 14 : 16" class="mr-1.5 lg:mr-2 text-cyan-400" />
                {{ formatDate(currentRecord.created_at) }}
              </div>
            </div>

            <PromptPreviewPanel
              v-if="currentRecord.prompt?.trim()"
              :title="$t('prompt_panel.title')"
              :prompt="currentRecord.prompt"
              :expand-label="$t('prompt_panel.expand')"
              :collapse-label="$t('prompt_panel.collapse')"
              :show-copy="true"
              :copy-label="$t('my_posts.copy_prompt')"
              @copy="copyPrompt(currentRecord)"
            />

            <div
              v-if="canShowWan22ChainCard"
              class="task-detail-chain-card rounded-2xl border p-4 space-y-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div class="task-detail-section-label text-[10px] lg:text-xs uppercase tracking-wider">
                    图生视频 v2 多段编辑
                  </div>
                  <div class="task-detail-chain-desc text-xs lg:text-sm mt-1">
                    {{ isMobile ? '手机端会进入纵向链路编辑，按钮更适合单手连续操作。' : '大屏建议进入工作台连续编辑，可直接查看整条链路并切换段落。' }}
                  </div>
                </div>
                <a-tag color="blue" class="self-start">
                  {{ isMobile ? '移动端' : '桌面端' }}
                </a-tag>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <a-button
                  type="primary"
                  class="task-detail-primary-btn border-none rounded-xl"
                  :disabled="!canExtendWan22Chain"
                  @click="openWan22Editor('extend')"
                >
                  扩展下一段
                </a-button>
                <a-button
                  class="task-detail-secondary-btn rounded-xl"
                  :disabled="!canRegenerateWan22Segment"
                  @click="openWan22Editor('regenerate')"
                >
                  重新生成本段
                </a-button>
                <a-button
                  class="task-detail-secondary-btn rounded-xl sm:col-span-2"
                  :disabled="!canStitchWan22Chain"
                  :loading="wan22ActionLoading === 'stitch'"
                  @click="handleWan22ChainStitch"
                >
                  完成整链拼接
                </a-button>
              </div>
              <div class="task-detail-chain-tip text-[11px] lg:text-xs">
                {{ canExtendWan22Chain ? '扩展会自动继承当前段尾帧；重生成只保留当前段之前的链路上下文。' : '当前记录缺少可用尾帧，暂时不能继续扩展。' }}
              </div>
            </div>

          </div>

          <!-- Desktop Actions -->
          <div class="hidden lg:flex mt-auto flex-col space-y-3 pt-6">
            <template v-if="currentRecord.output_file">
              <a-button
                v-if="['txt2img', 'i2i_pro', 'i2i_draw', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video', 'wan22_video_v2'].includes(currentRecord.type) && currentRecord.allow_contribute !== false"
                type="primary"
                :disabled="currentRecord.is_public"
                class="task-detail-primary-btn w-full h-12 border-none rounded-xl text-base font-medium flex items-center justify-center"
                :class="currentRecord.is_public ? 'is-disabled' : 'is-active'"
                :loading="submittingTasks[currentRecord.task_id]"
                @click="!currentRecord.is_public && submitToGallery(currentRecord)"
              >
                {{ currentRecord.is_public ? '已投稿' : (submittingTasks[currentRecord.task_id] ? $t('history.submitting') : $t('history.submit')) }}
              </a-button>
              <div v-else class="task-detail-disabled-box w-full h-12 rounded-xl flex items-center justify-center text-sm">
                {{ $t('history.cannot_post') }}
              </div>

              <a-button
                ghost
                class="task-detail-secondary-btn task-detail-favorite-btn w-full h-12 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                :class="currentRecord.is_favorited ? 'is-disabled' : ''"
                @click="!currentRecord.is_favorited && handleFavorite(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Star :size="18" class="mr-2" :class="{ 'fill-current': currentRecord.is_favorited }" />
                  {{ currentRecord.is_favorited ? '已收藏' : '收藏' }}
                </span>
              </a-button>

              <a-button
                ghost
                class="task-detail-secondary-btn task-detail-download-btn w-full h-12 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                @click="handleDownload(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Download :size="18" class="mr-2" />
                  {{ $t('history.save') }}
                </span>
              </a-button>

              <a-button
                ghost
                class="task-detail-secondary-btn task-detail-bot-btn w-full h-12 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center"
                @click="handleSendToBot(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Send :size="18" class="mr-2" />
                  发送至私聊
                </span>
              </a-button>

              <a-button
                ghost
                class="task-detail-secondary-btn task-detail-delete-btn w-full h-12 transition-colors rounded-xl text-base font-medium !flex !items-center !justify-center mt-3"
                @click="handleDelete(currentRecord)"
              >
                <span class="flex items-center justify-center">
                  <Trash2 :size="18" class="mr-2" />
                  删除
                </span>
              </a-button>
            </template>
            <div v-else class="task-detail-empty-actions text-center italic py-4 border border-dashed rounded-xl">暂无文件可操作</div>
          </div>
        </div>
      </div>

      <!-- Mobile Bottom Interaction Bar -->
      <div class="task-detail-mobile-bar lg:hidden fixed bottom-0 left-0 right-0 px-4 py-2 pb-6 flex items-center justify-between z-50 safe-area-bottom">
        <template v-if="currentRecord.output_file">
          <div class="flex gap-6">
            <button class="task-detail-mobile-action flex flex-col items-center justify-center gap-1 transition-colors" :class="currentRecord.is_favorited ? 'is-favorite' : ''" @click="!currentRecord.is_favorited && handleFavorite(currentRecord)">
              <Star :size="20" :class="{ 'fill-current': currentRecord.is_favorited }" />
              <span class="text-[10px]">{{ currentRecord.is_favorited ? '已收藏' : '收藏' }}</span>
            </button>
            <button class="task-detail-mobile-action flex flex-col items-center justify-center gap-1 transition-colors" @click="handleDownload(currentRecord)">
              <Download :size="20" />
              <span class="text-[10px]">保存</span>
            </button>
            <button class="task-detail-mobile-action task-detail-mobile-bot flex flex-col items-center justify-center gap-1 transition-colors" @click="handleSendToBot(currentRecord)">
              <Send :size="20" />
              <span class="text-[10px]">发私聊</span>
            </button>
            <button class="task-detail-mobile-action task-detail-mobile-delete flex flex-col items-center justify-center gap-1 transition-colors" @click="handleDelete(currentRecord)">
              <Trash2 :size="20" />
              <span class="text-[10px]">删除</span>
            </button>
          </div>
          
          <button 
            v-if="['txt2img', 'i2i_pro', 'i2i_draw', 'edit', 'custom_video', 'video_lora', 'img2img_lora', 'ltx_video', 'wan22_video_v2'].includes(currentRecord.type) && currentRecord.allow_contribute !== false"
            @click="!currentRecord.is_public && submitToGallery(currentRecord)"
            :disabled="currentRecord.is_public || submittingTasks[currentRecord.task_id]"
            class="task-detail-mobile-submit px-5 py-2 rounded-full font-medium text-sm transition-all flex items-center justify-center min-w-[100px]"
            :class="currentRecord.is_public ? 'is-disabled' : 'is-active'"
          >
            <div v-if="submittingTasks[currentRecord.task_id]" class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1.5"></div>
            <Upload v-else-if="!currentRecord.is_public" :size="16" class="mr-1.5" />
            <span>{{ currentRecord.is_public ? '已投稿' : (submittingTasks[currentRecord.task_id] ? '投稿中...' : '一键投稿') }}</span>
          </button>
        </template>
        <div v-else class="task-detail-empty-actions w-full text-center text-sm py-2">暂无文件可操作</div>
      </div>

    </div>
  </a-modal>
</template>

<style>
.history-detail-modal {
  --task-detail-shell-bg: #0f172a;
  --task-detail-panel-bg: rgba(71, 85, 105, 0.8);
  --task-detail-header-bg: linear-gradient(to bottom, rgba(2, 6, 23, 0.55), transparent);
  --task-detail-mobile-close-bg: rgba(2, 6, 23, 0.4);
  --task-detail-border: rgba(148, 163, 184, 0.34);
  --task-detail-divider: rgba(51, 65, 85, 0.95);
  --task-detail-shadow: 0 24px 60px rgba(2, 6, 23, 0.38);
  --task-detail-text-primary: #f8fafc;
  --task-detail-text-secondary: #cbd5e1;
  --task-detail-text-muted: #94a3b8;
  --task-detail-badge-bg: rgba(2, 6, 23, 0.42);
  --task-detail-badge-border: rgba(255, 255, 255, 0.18);
  --task-detail-badge-text: #ffffff;
  --task-detail-time-bg: rgba(2, 6, 23, 0.2);
  --task-detail-time-border: rgba(100, 116, 139, 0.3);
  --task-detail-mobile-bar-bg: rgba(15, 23, 42, 0.95);
  --task-detail-secondary-bg: rgba(100, 116, 139, 0.14);
  --task-detail-secondary-hover: rgba(100, 116, 139, 0.24);
  --task-detail-secondary-border: rgba(148, 163, 184, 0.36);
  --task-detail-primary-gradient: linear-gradient(90deg, #0891b2, #4f46e5);
  --task-detail-primary-gradient-hover: linear-gradient(90deg, #06b6d4, #6366f1);
  --prompt-preview-bg: rgba(2, 6, 23, 0.28);
  --prompt-preview-border: rgba(100, 116, 139, 0.32);
  --prompt-preview-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.05);
  --prompt-preview-title: #f8fafc;
  --prompt-preview-text: #dbeafe;
  --prompt-preview-muted: #94a3b8;
  --prompt-preview-action-bg: rgba(15, 23, 42, 0.66);
  --prompt-preview-action-hover: rgba(30, 41, 59, 0.84);
  --prompt-preview-action-border: rgba(100, 116, 139, 0.5);
  --prompt-preview-action-text: #f8fafc;
}

html[data-theme='light'] .history-detail-modal {
  --task-detail-shell-bg: #ffffff;
  --task-detail-panel-bg: rgba(248, 250, 252, 0.97);
  --task-detail-header-bg: linear-gradient(to bottom, rgba(255, 255, 255, 0.72), transparent);
  --task-detail-mobile-close-bg: rgba(255, 255, 255, 0.74);
  --task-detail-border: rgba(203, 213, 225, 0.92);
  --task-detail-divider: rgba(226, 232, 240, 0.96);
  --task-detail-shadow: 0 24px 60px rgba(15, 23, 42, 0.14);
  --task-detail-text-primary: #0f172a;
  --task-detail-text-secondary: #334155;
  --task-detail-text-muted: #64748b;
  --task-detail-badge-bg: rgba(241, 245, 249, 0.98);
  --task-detail-badge-border: rgba(203, 213, 225, 0.95);
  --task-detail-badge-text: #0f172a;
  --task-detail-time-bg: rgba(241, 245, 249, 0.92);
  --task-detail-time-border: rgba(203, 213, 225, 0.95);
  --task-detail-mobile-bar-bg: rgba(255, 255, 255, 0.96);
  --task-detail-secondary-bg: rgba(241, 245, 249, 0.98);
  --task-detail-secondary-hover: rgba(226, 232, 240, 0.98);
  --task-detail-secondary-border: rgba(148, 163, 184, 0.35);
  --task-detail-primary-gradient: linear-gradient(90deg, #2563eb, #4f46e5);
  --task-detail-primary-gradient-hover: linear-gradient(90deg, #1d4ed8, #4338ca);
  --prompt-preview-bg: rgba(255, 255, 255, 0.88);
  --prompt-preview-border: rgba(203, 213, 225, 0.95);
  --prompt-preview-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
  --prompt-preview-title: #0f172a;
  --prompt-preview-text: #334155;
  --prompt-preview-muted: #64748b;
  --prompt-preview-action-bg: rgba(241, 245, 249, 0.98);
  --prompt-preview-action-hover: rgba(226, 232, 240, 0.98);
  --prompt-preview-action-border: rgba(203, 213, 225, 0.95);
  --prompt-preview-action-text: #1e293b;
}

.history-detail-modal .ant-modal-content {
  background-color: transparent !important;
  box-shadow: none !important;
}
.history-detail-modal .ant-modal-mask {
  background-color: rgba(0, 0, 0, 0.85) !important;
  backdrop-filter: blur(8px);
}

.task-detail-shell {
  background: var(--task-detail-shell-bg);
  border-color: var(--task-detail-border);
  box-shadow: var(--task-detail-shadow);
}

.task-detail-mobile-header {
  background: var(--task-detail-header-bg);
}

.task-detail-mobile-close {
  color: var(--task-detail-text-primary);
  background: var(--task-detail-mobile-close-bg);
  backdrop-filter: blur(16px);
}

.task-detail-empty-file,
.task-detail-empty-actions {
  color: var(--task-detail-text-muted);
}

.task-detail-info-panel {
  background: var(--task-detail-panel-bg);
  color: var(--task-detail-text-primary);
  backdrop-filter: blur(20px);
}

.task-detail-desktop-close {
  color: var(--task-detail-text-muted);
}

.task-detail-desktop-close:hover {
  color: var(--task-detail-text-primary);
}

.task-detail-title {
  color: var(--task-detail-text-primary);
}

.task-detail-section-label {
  color: var(--task-detail-text-muted);
}

.task-detail-type-badge {
  border: 1px solid var(--task-detail-badge-border);
  background: var(--task-detail-badge-bg);
  color: var(--task-detail-badge-text);
}

.task-detail-source-badge.is-web {
  border-color: rgba(34, 197, 94, 0.2);
  background: rgba(34, 197, 94, 0.18);
  color: #166534;
}

.task-detail-source-badge.is-bot {
  border-color: rgba(249, 115, 22, 0.2);
  background: rgba(249, 115, 22, 0.18);
  color: #c2410c;
}

.history-detail-modal:not([data-theme='dark']) .task-detail-time-badge {
  color: var(--task-detail-text-secondary);
}

.task-detail-time-badge {
  background: var(--task-detail-time-bg);
  border: 1px solid var(--task-detail-time-border);
  color: var(--task-detail-text-secondary);
}

.task-detail-chain-card {
  background: color-mix(in srgb, var(--task-detail-secondary-bg) 78%, transparent);
  border-color: var(--task-detail-secondary-border);
}

.task-detail-chain-desc {
  color: var(--task-detail-text-secondary);
}

.task-detail-primary-btn.is-active,
.task-detail-mobile-submit.is-active {
  background: var(--task-detail-primary-gradient);
  color: #ffffff !important;
}

.task-detail-primary-btn.is-active:hover,
.task-detail-mobile-submit.is-active:hover {
  background: var(--task-detail-primary-gradient-hover);
}

.task-detail-primary-btn.is-disabled,
.task-detail-mobile-submit.is-disabled {
  background: rgba(99, 102, 241, 0.24) !important;
  color: rgba(224, 231, 255, 0.95) !important;
}

.task-detail-disabled-box {
  background: var(--task-detail-secondary-bg);
  border: 1px solid var(--task-detail-secondary-border);
  color: var(--task-detail-text-muted);
}

.task-detail-secondary-btn {
  background: var(--task-detail-secondary-bg);
  border-color: var(--task-detail-secondary-border) !important;
}

.task-detail-secondary-btn:hover {
  background: var(--task-detail-secondary-hover) !important;
}

.task-detail-favorite-btn {
  color: #f59e0b !important;
}

.task-detail-favorite-btn.is-disabled {
  color: var(--task-detail-text-muted) !important;
  cursor: not-allowed;
}

.task-detail-download-btn {
  color: #06b6d4 !important;
  border-color: rgba(6, 182, 212, 0.35) !important;
}

.task-detail-bot-btn {
  color: #6366f1 !important;
  border-color: rgba(99, 102, 241, 0.35) !important;
}

.task-detail-delete-btn {
  color: #f87171 !important;
  border-color: rgba(248, 113, 113, 0.35) !important;
}

.task-detail-empty-actions {
  border-color: var(--task-detail-secondary-border);
}

.task-detail-mobile-bar {
  background: var(--task-detail-mobile-bar-bg);
  backdrop-filter: blur(18px);
  border-top: 1px solid var(--task-detail-divider);
}

.task-detail-mobile-action {
  color: var(--task-detail-text-muted);
}

.task-detail-mobile-action:hover {
  color: var(--task-detail-text-secondary);
}

.task-detail-mobile-action.is-favorite {
  color: #f59e0b;
}

.task-detail-mobile-bot {
  color: #6366f1;
}

.task-detail-mobile-delete:hover {
  color: #f87171;
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
  background-color: var(--task-detail-shell-bg, var(--theme-card-strong-bg)) !important;
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
