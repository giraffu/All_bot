<script setup lang="ts">
import { ref, computed } from 'vue'
import { VideoCameraOutlined, InboxOutlined, DownloadOutlined, CloseCircleOutlined, HistoryOutlined } from '@ant-design/icons-vue'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useDualFileUploadPreview } from '@/composables/useDualFileUploadPreview'
import { useSwapResetController } from '@/composables/useSwapResetController'
import { useSwapTaskSubmit } from '@/composables/useSwapTaskSubmit'
import { useRoute } from 'vue-router'
import { onMounted } from 'vue'
import { useGenerationRouteConfig } from '@/features/generation/generationRouteConfig'
import GenerationActionBar from '@/components/GenerationActionBar.vue'
import GenerationUploadCard from '@/components/GenerationUploadCard.vue'
import GenerationWorkbenchShell from '@/components/GenerationWorkbenchShell.vue'
import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'

const { uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const { loadApplyContext } = useGalleryApplyContext()
const route = useRoute()
const { routeApplyEnabled } = useGenerationRouteConfig(route, {
  taskType: 'face_video',
  title: '视频换脸',
  cost: 18,
})
const {
  primaryFileList: faceFileList,
  secondaryFileList: bodyFileList,
  primaryObjectKey: faceObjectKey,
  secondaryObjectKey: bodyObjectKey,
  primaryPreviewUrl: facePreview,
  secondaryPreviewUrl: bodyPreview,
  beforeUploadPrimary: beforeUploadFace,
  beforeUploadSecondary: beforeUploadBody,
  removePrimary: handleRemoveFace,
  removeSecondary: handleRemoveBody,
  applySecondaryTemplateTarget,
} = useDualFileUploadPreview({
  uploadFile,
})
const resolution = ref('720')

const taskCost = computed(() => {
  const res = resolution.value;
  if (res === '720') return 18;
  if (res === '1024') return 36;
  return 18; // default fallback for 720p
})

const isTemplateApplied = ref(false)
const templateSourcePostId = ref<number | null>(null)

const initializeLegacySwapApply = () => {
  if (!routeApplyEnabled.value) {
    return
  }

  const context = loadApplyContext()
  if (!context || context.task_type !== 'face_video' || !context.input_file) {
    return
  }

  applySecondaryTemplateTarget({
    objectKey: context.input_file,
    previewUrl: context.input_file_url || null,
  })

  if (context.source_post_id != null) {
    templateSourcePostId.value = Number(context.source_post_id)
  }

  if (context.width != null) {
    resolution.value = String(context.width)
  }

  isTemplateApplied.value = true
}

onMounted(() => {
  initializeLegacySwapApply()
})

const { handleGenerate } = useSwapTaskSubmit({
  taskType: 'face_video',
  taskTitle: '视频换脸',
  targetField: 'target_video',
  getFaceAssetKey: () => faceObjectKey.value,
  getTargetAssetKey: () => bodyObjectKey.value,
  getResolution: () => Number(resolution.value),
  getIsTemplateApplied: () => isTemplateApplied.value,
  getSourcePostId: () => templateSourcePostId.value,
  warningMessage: '请确保已上传人脸图片和目标视频！',
  submitTask,
  setSubmittedTaskId,
})

const { resetSwapState } = useSwapResetController({
  resetUploads: () => {
    handleRemoveFace()
    handleRemoveBody()
  },
  clearSubmittedTask: () => setSubmittedTaskId(null),
  resetResolution: () => {
    resolution.value = '720'
  },
  clearTemplateState: () => {
    isTemplateApplied.value = false
    templateSourcePostId.value = null
  },
})

</script>

<template>
  <GenerationWorkbenchShell title="视频换脸设置">
    <template #left-top>
      <div v-if="isTemplateApplied" class="mb-6 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
        <div class="text-indigo-400 mr-3">✨</div>
        <div class="text-slate-300 text-sm">已加载一键视频换脸模板，目标视频已锁定，请在上方上传您需要替换的人脸即可开始生成。</div>
      </div>
    </template>

    <template #left-content>
      <div class="flex flex-col gap-6 mb-6">
            <!-- Row for Upload -->
            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Face Upload -->
              <GenerationUploadCard
                title="清晰人脸"
                step="1."
                :file-list="faceFileList"
                :preview-url="facePreview"
                accept="image/png, image/jpeg"
                wrapper-class="upload-section flex flex-col w-full md:w-[40%] min-w-[160px] shrink-0 h-48 md:h-full"
                :before-upload="beforeUploadFace"
                @remove="handleRemoveFace"
                @update:fileList="faceFileList = $event"
              >
                <template #placeholder-icon>
                  <inbox-outlined />
                </template>
              </GenerationUploadCard>

              <!-- Video Upload -->
              <GenerationUploadCard
                title="目标视频"
                step="2."
                :file-list="bodyFileList"
                :preview-url="bodyPreview"
                preview-kind="video"
                name="video"
                accept="video/mp4, video/quicktime"
                wrapper-class="upload-section flex flex-col flex-grow min-w-0 h-48 md:h-full"
                dragger-class="upload-dragger bg-slate-500/50 backdrop-blur-md border-dashed border-2 border-blue-200 hover:border-blue-400 transition-colors flex-grow flex items-center justify-center w-full"
                :before-upload="beforeUploadBody"
                upload-text="上传目标视频"
                upload-hint="支持 MP4/MOV"
                @remove="handleRemoveBody"
                @update:fileList="bodyFileList = $event"
              >
                <template #placeholder-icon>
                  <video-camera-outlined />
                </template>
              </GenerationUploadCard>
            </div>
          </div>
          
          <!-- Video Settings -->
          <div class="settings-section border-t border-slate-400/50 pt-5">
            <h3 class="text-sm font-bold mb-3 text-slate-200">输出设置</h3>
            <div class="flex flex-col gap-4">
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-2">分辨率</label>
                <a-radio-group v-model:value="resolution" button-style="solid" class="w-full grid grid-cols-2 gap-2 max-w-[240px]">
                  <a-radio-button value="720" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">720p (高清)</a-radio-button>
                  <a-radio-button value="1024" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">1024p</a-radio-button>
                </a-radio-group>
              </div>
            </div>
          </div>
    </template>

    <template #left-footer>
      <GenerationActionBar
        :cost="taskCost"
        button-text="开始换脸"
        :disabled="!faceObjectKey || !bodyObjectKey"
        :loading="isSubmitting"
        @submit="handleGenerate"
      >
        <template #button-icon><video-camera-outlined /></template>
      </GenerationActionBar>
    </template>

    <template #right-panel>
      <TaskResultPreviewPanel
        :current-task="currentTask"
        :is-image-url="isImageUrl"
        body-class="h-full flex flex-col"
        content-class="flex-grow flex items-center justify-center p-6 min-h-0 bg-black/20"
        pending-label="AI 正在为您生成大片..."
        @download="downloadResult"
        @reset="resetSwapState"
      >
        <template #header>
          <h3 class="text-lg font-bold p-4 border-b border-slate-400/50 text-slate-200 bg-slate-500/50 flex items-center shrink-0">
            <video-camera-outlined class="mr-2 text-blue-400" /> 结果预览区
          </h3>
        </template>
        <template #empty>
          <div class="text-center text-slate-500 flex flex-col items-center">
            <video-camera-outlined class="text-5xl mb-4 opacity-50" />
            <p>请在左侧配置参数并点击生成，结果将在此处显示</p>
          </div>
        </template>
        <template #pending="{ task }">
          <div class="flex flex-col items-center justify-center w-full h-full">
            <div class="relative w-32 h-32 flex items-center justify-center mb-6">
              <div class="absolute inset-0 border-4 border-slate-400 rounded-full"></div>
              <div class="absolute inset-0 border-4 border-blue-500 rounded-full border-t-transparent animate-spin"></div>
              <div class="text-blue-400 font-bold text-base">
                {{ task.awaitingResult ? '保存中' : task.status === 'pending' ? '排队中' : '生成中' }}
              </div>
            </div>
            <p class="text-slate-300 font-medium text-lg animate-pulse">
              {{ task.awaitingResult ? '正在保存结果...' : 'AI 正在为您生成大片...' }}
            </p>
            <p v-if="task.status === 'pending' && task.queuePos != null" class="text-sm text-slate-500 mt-2 bg-slate-500 px-3 py-1 rounded-full">
              队列位置: <span class="text-blue-400 font-bold">{{ task.queuePos + 1 }}</span>
            </p>
          </div>
        </template>
        <template #success-media="{ task }">
          <div class="relative w-full h-full flex items-center justify-center bg-black/40 rounded-xl overflow-hidden border border-slate-400/50 shadow-2xl">
            <a-image v-if="isImageUrl(task.resultUrl)" :src="task.resultUrl" class="max-w-full max-h-full object-contain" :preview="true" />
            <video v-else :src="task.resultUrl" controls class="max-w-full max-h-full object-contain"></video>
          </div>
        </template>
        <template #success-actions="{ task }">
          <div class="flex gap-3 mt-4 w-full justify-center">
            <a-button type="primary" ghost @click="downloadResult(task.resultUrl, task.title)" class="flex items-center px-6 rounded-lg">
              <download-outlined class="mr-1" /> 保存到本地
            </a-button>
            <a-button type="default" @click="resetSwapState" class="flex items-center px-6 rounded-lg border-slate-400 text-slate-300 hover:text-white hover:border-slate-400 bg-slate-500/50">
              继续生成
            </a-button>
            <a-button type="default" @click="$router.push('/history')" class="flex items-center px-6 rounded-lg border-slate-400 text-slate-300 hover:text-white hover:border-slate-400 bg-slate-500/50">
              <history-outlined class="mr-1" /> 查看历史
            </a-button>
          </div>
        </template>
        <template #failed="{ task }">
          <div class="text-center text-red-400 flex flex-col items-center bg-red-950/20 p-8 rounded-2xl border border-red-900/50">
            <close-circle-outlined class="text-5xl mb-4" />
            <h4 class="text-lg font-bold mb-2">生成失败</h4>
            <p class="text-sm opacity-80">{{ task.error || '未知错误，请重试' }}</p>
          </div>
        </template>
      </TaskResultPreviewPanel>
    </template>
  </GenerationWorkbenchShell>
</template>


<style scoped>
:deep(.ant-input), :deep(.ant-input-affix-wrapper) {
  background-color: var(--theme-card-strong-bg) !important;
  color: var(--theme-text-primary) !important;
  -webkit-text-fill-color: var(--theme-text-primary) !important;
  opacity: 1 !important;
  border-color: var(--theme-border) !important;
}
:deep(.ant-input::placeholder) {
  color: var(--theme-input-placeholder) !important;
}
:deep(.ant-upload.ant-upload-drag) {
  background: var(--theme-card-strong-bg) !important;
  border-color: var(--theme-border) !important;
}
:deep(.ant-upload.ant-upload-drag:hover) {
  border-color: var(--theme-border-strong) !important;
}
:deep(.ant-upload.ant-upload-drag .ant-upload-text) {
  color: var(--theme-text-primary) !important;
}
:deep(.ant-upload.ant-upload-drag .ant-upload-hint) {
  color: var(--theme-text-secondary) !important;
}

.upload-dragger {
  background: var(--theme-card-strong-bg);
  border-radius: 12px;
}
:deep(.ant-radio-button-wrapper) {
  background: var(--theme-pill-bg) !important;
  color: var(--theme-text-secondary) !important;
  border-color: var(--theme-border) !important;
}
:deep(.ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled)) {
  background: #3b82f6 !important;
  color: #ffffff !important;
  border-color: #3b82f6 !important;
}
:deep(.ant-radio-button-wrapper:before) {
  display: none !important;
}

:deep(.text-slate-200),
:deep(.text-slate-300) {
  color: var(--theme-text-primary) !important;
}

:deep(.text-slate-400),
:deep(.text-slate-500) {
  color: var(--theme-text-secondary) !important;
}
</style>
