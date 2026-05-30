<script setup lang="ts">
import { ref } from 'vue'
import { InboxOutlined, SwapOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
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

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const { loadApplyContext } = useGalleryApplyContext()
const route = useRoute()
const { routeApplyEnabled } = useGenerationRouteConfig(route, {
  taskType: 'face_swap',
  title: '快速换脸',
  cost: 2,
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
  resetAll,
} = useDualFileUploadPreview({
  uploadFile,
})
const isTemplateApplied = ref(false)
const templateSourcePostId = ref<number | null>(null)

const initializeLegacySwapApply = () => {
  if (!routeApplyEnabled.value) {
    return
  }

  const context = loadApplyContext()
  if (!context || context.task_type !== 'face_swap' || !context.input_file) {
    return
  }

  applySecondaryTemplateTarget({
    objectKey: context.input_file,
    previewUrl: context.input_file_url || null,
  })

  if (context.source_post_id != null) {
    templateSourcePostId.value = Number(context.source_post_id)
  }

  isTemplateApplied.value = true
}

onMounted(() => {
  initializeLegacySwapApply()
})

const { handleGenerate } = useSwapTaskSubmit({
  taskType: 'face_swap',
  taskTitle: '快速换脸',
  targetField: 'target_image',
  getFaceAssetKey: () => faceObjectKey.value,
  getTargetAssetKey: () => bodyObjectKey.value,
  getIsTemplateApplied: () => isTemplateApplied.value,
  getSourcePostId: () => templateSourcePostId.value,
  warningMessage: '请先上传人脸和目标图片！',
  submitTask,
  setSubmittedTaskId,
})

const { resetSwapState: resetForm } = useSwapResetController({
  resetUploads: resetAll,
  clearSubmittedTask: () => setSubmittedTaskId(null),
  clearTemplateState: () => {
    isTemplateApplied.value = false
    templateSourcePostId.value = null
  },
})
</script>

<template>
  <GenerationWorkbenchShell
    title="快速换脸"
    description="请提供两张图片，系统将把第一张的人脸替换到第二张的目标场景中。"
  >
    <template #left-top>
      <div v-if="isTemplateApplied" class="col-span-full mb-4 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
        <div class="text-indigo-400 mr-3">✨</div>
        <div class="text-slate-300 text-sm">已加载一键换脸模板，底图已为您锁定，请在左侧上传您需要替换的人脸即可开始生成。</div>
      </div>
    </template>

    <template #left-content>
      <div class="flex flex-col gap-6">
            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Face Upload -->
              <GenerationUploadCard
                title="清晰人脸"
                step="1."
                :file-list="faceFileList"
                :preview-url="facePreview"
                accept="image/png, image/jpeg"
                wrapper-class="upload-section flex flex-col w-full md:w-[50%] min-w-[160px] shrink-0 h-48 md:h-full"
                :before-upload="beforeUploadFace"
                upload-text="点击/拖拽上传人脸"
                upload-hint="JPG/PNG，五官清晰"
                @remove="handleRemoveFace"
                @update:fileList="faceFileList = $event"
              >
                <template #placeholder-icon>
                  <inbox-outlined />
                </template>
              </GenerationUploadCard>

              <!-- Body Upload -->
              <GenerationUploadCard
                title="目标场景"
                step="2."
                :file-list="bodyFileList"
                :preview-url="bodyPreview"
                accept="image/png, image/jpeg"
                wrapper-class="upload-section flex flex-col w-full md:w-[50%] min-w-[160px] shrink-0 h-48 md:h-full"
                :before-upload="beforeUploadBody"
                upload-text="点击/拖拽上传目标图"
                upload-hint="人脸将替换至此图"
                @remove="handleRemoveBody"
                @update:fileList="bodyFileList = $event"
              >
                <template #placeholder-icon>
                  <inbox-outlined />
                </template>
              </GenerationUploadCard>
            </div>
          </div>
          
          <div v-if="uploading" class="mt-4">
            <span class="text-xs text-slate-400">正在上传至服务器...</span>
            <a-progress :percent="uploadProgress" status="active" strokeColor="#3b82f6" size="small" />
          </div>
    </template>

    <template #left-footer>
      <GenerationActionBar
        :cost="1"
        button-text="开始换脸"
        :disabled="!faceObjectKey || !bodyObjectKey"
        :loading="isSubmitting"
        @submit="handleGenerate"
      >
        <template #button-icon><swap-outlined /></template>
        <template #cost-unit>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6 2L2 8l10 14L22 8l-4-6H6z"></path></svg>
        </template>
      </GenerationActionBar>
    </template>

    <template #right-panel>
      <TaskResultPreviewPanel
        :current-task="currentTask"
        :is-image-url="isImageUrl"
        @download="downloadResult"
        @reset="resetForm"
      >
        <template #empty-icon>
          <picture-outlined class="text-6xl mb-4" />
        </template>
        <template #download-icon>
          <download-outlined />
        </template>
        <template #failed-icon>
          <close-circle-outlined class="text-5xl text-red-500 mb-4" />
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

:deep(.text-slate-200),
:deep(.text-slate-300) {
  color: var(--theme-text-primary) !important;
}

:deep(.text-slate-400),
:deep(.text-slate-500) {
  color: var(--theme-text-secondary) !important;
}
</style>
