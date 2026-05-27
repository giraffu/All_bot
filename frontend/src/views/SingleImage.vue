<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { InboxOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useSingleFileUploadPreview } from '@/composables/useSingleFileUploadPreview'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import GenerationActionBar from '@/components/GenerationActionBar.vue'
import GenerationUploadCard from '@/components/GenerationUploadCard.vue'
import GenerationWorkbenchShell from '@/components/GenerationWorkbenchShell.vue'
import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'

const route = useRoute()
const { loadApplyContext } = useGalleryApplyContext()

const taskType = computed(() => (route.query.type as string) || 'random_faceswap')
const taskTitle = computed(() => (route.query.title as string) || '单图生成')
const taskCost = computed(() => Number(route.query.cost) || 1)

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const {
  fileList,
  objectKey,
  filePreview,
  beforeUpload,
  handleRemove,
} = useSingleFileUploadPreview({
  uploadFile
})
const isTemplateApplied = ref(false)
const templateSourcePostId = ref<number | null>(null)

onMounted(() => {
  if (route.query.apply === 'true') {
    const ctx = loadApplyContext()
    if (ctx && ctx.task_type === taskType.value) {
      if (ctx.source_post_id != null) {
        templateSourcePostId.value = Number(ctx.source_post_id)
      }
      isTemplateApplied.value = true
    }
  }
})

const handleGenerate = async () => {
  if (!objectKey.value) {
    message.warning('请先上传图片！')
    return
  }

  const payload = buildGenerationTaskPayload({
    taskType: taskType.value,
    images: [objectKey.value],
    isTemplate: isTemplateApplied.value,
    sourcePostId: templateSourcePostId.value,
  })

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
  }
}

const resetForm = () => {
  handleRemove()
  setSubmittedTaskId(null)
}
</script>

<template>
  <GenerationWorkbenchShell
    :title="taskTitle"
    description="请上传一张符合要求的图片以开始生成。"
    left-body-class="p-6 flex-grow overflow-y-auto custom-scrollbar flex flex-col"
  >
    <template #left-top>
      <div v-if="isTemplateApplied" class="mb-6 w-full max-w-md bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center text-left">
        <div class="text-indigo-400 mr-3">✨</div>
        <div class="text-slate-300 text-sm">已准备好应用所选的模板效果，请上传您的图片即可生成。</div>
      </div>
    </template>

    <template #left-content>
      <GenerationUploadCard
        title="基础图片"
        step="1."
        :file-list="fileList"
        :preview-url="filePreview"
        accept="image/png, image/jpeg"
        wrapper-class="upload-section flex flex-col w-full flex-grow min-h-0 h-48 md:h-full"
        dragger-class="upload-dragger bg-slate-500/50 backdrop-blur-md border-dashed border-2 border-blue-200 hover:border-blue-400 transition-colors flex-grow flex items-center justify-center w-full"
        :before-upload="beforeUpload"
        @remove="handleRemove"
        @update:fileList="fileList = $event"
      >
        <template #placeholder-icon>
          <inbox-outlined />
        </template>
      </GenerationUploadCard>

      <div v-if="uploading" class="mt-4 w-full">
        <span class="text-xs text-slate-400 mb-1 block">正在上传至服务器...</span>
        <a-progress :percent="uploadProgress" status="active" strokeColor="#3b82f6" size="small" />
      </div>
    </template>

    <template #left-footer>
      <GenerationActionBar
        :cost="taskCost"
        button-text="生成图片"
        :disabled="!objectKey"
        :loading="isSubmitting"
        @submit="handleGenerate"
      >
        <template #button-icon><picture-outlined /></template>
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
  border-color: var(--theme-border) !important;
}
:deep(.ant-input::placeholder) {
  color: var(--theme-text-muted) !important;
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
