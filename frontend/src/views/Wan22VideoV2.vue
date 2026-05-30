<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { InboxOutlined, DownloadOutlined, VideoCameraOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import GenerationActionBar from '@/components/GenerationActionBar.vue'
import GenerationUploadCard from '@/components/GenerationUploadCard.vue'
import GenerationWorkbenchShell from '@/components/GenerationWorkbenchShell.vue'
import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'
import { useSingleFileUploadPreview } from '@/composables/useSingleFileUploadPreview'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { useUpload } from '@/composables/useUpload'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import { DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT } from '@/features/generation/imageToVideo'
import { useGenerationRouteConfig } from '@/features/generation/generationRouteConfig'

const route = useRoute()
const { taskTitle, taskCost } = useGenerationRouteConfig(route, {
  taskType: 'wan22_video_v2',
  title: '图生视频 v2',
  cost: 10,
})

const { uploadFile: uploadStartFile, uploading: startUploading, progress: startUploadProgress } = useUpload()
const { uploadFile: uploadEndFile, uploading: endUploading, progress: endUploadProgress } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()

const {
  fileList: startFileList,
  objectKey: startObjectKey,
  filePreview: startPreview,
  beforeUpload: beforeStartUpload,
  handleRemove: handleRemoveStart,
} = useSingleFileUploadPreview({
  uploadFile: uploadStartFile,
})

const {
  fileList: endFileList,
  objectKey: endObjectKey,
  filePreview: endPreview,
  beforeUpload: beforeEndUpload,
  handleRemove: handleRemoveEnd,
} = useSingleFileUploadPreview({
  uploadFile: uploadEndFile,
})

const prompt = ref('')
const negativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
const hasEndFrame = computed(() => Boolean(endObjectKey.value))

const handleGenerate = async () => {
  if (!startObjectKey.value) {
    message.warning('请先上传起始帧图片')
    return
  }
  const payload = buildGenerationTaskPayload({
    taskType: 'wan22_video_v2',
    images: hasEndFrame.value && endObjectKey.value
      ? [startObjectKey.value, endObjectKey.value]
      : [startObjectKey.value],
    duration: 5,
    prompt: prompt.value,
    negativePrompt: negativePrompt.value,
    promptTarget: 'inputs',
    extraInputs: {
      use_end_frame: hasEndFrame.value,
    },
  })

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
  }
}

const resetForm = () => {
  handleRemoveStart()
  handleRemoveEnd()
  prompt.value = ''
  negativePrompt.value = DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
  setSubmittedTaskId(null)
}
</script>

<template>
  <GenerationWorkbenchShell :title="`${taskTitle}设置`">
    <template #left-content>
      <div class="flex flex-col gap-6 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <GenerationUploadCard
              title="起始帧"
              step="1."
              :file-list="startFileList"
              :preview-url="startPreview"
              accept="image/png, image/jpeg"
              wrapper-class="upload-section flex flex-col w-full min-w-[160px] shrink-0 h-56"
              :before-upload="beforeStartUpload"
              @remove="handleRemoveStart"
              @update:fileList="startFileList = $event"
            >
              <template #placeholder-icon>
                <InboxOutlined />
              </template>
            </GenerationUploadCard>
            <div v-if="startUploading" class="mt-2">
              <span class="wan22-video-v2__progress-text text-xs">正在上传起始帧...</span>
              <a-progress :percent="startUploadProgress" status="active" strokeColor="#3b82f6" size="small" />
            </div>
          </div>

          <div>
            <GenerationUploadCard
              title="终止帧（可选）"
              step="2."
              :file-list="endFileList"
              :preview-url="endPreview"
              accept="image/png, image/jpeg"
              wrapper-class="upload-section flex flex-col w-full min-w-[160px] shrink-0 h-56"
              :before-upload="beforeEndUpload"
              @remove="handleRemoveEnd"
              @update:fileList="endFileList = $event"
            >
              <template #placeholder-icon>
                <InboxOutlined />
              </template>
            </GenerationUploadCard>
            <div v-if="endUploading" class="mt-2">
              <span class="wan22-video-v2__progress-text text-xs">正在上传终止帧...</span>
              <a-progress :percent="endUploadProgress" status="active" strokeColor="#3b82f6" size="small" />
            </div>
          </div>
        </div>

        <div class="wan22-video-v2__section rounded-xl p-4">
          <h3 class="wan22-video-v2__section-title text-sm font-bold mb-3">提示词</h3>
          <div class="grid grid-cols-1 gap-4">
            <div>
              <label class="wan22-video-v2__field-label block text-xs font-medium mb-2">正面提示词</label>
              <a-textarea
                v-model:value="prompt"
                :rows="4"
                placeholder="输入视频生成的正向提示词..."
                class="rounded-xl"
              />
            </div>
            <div>
              <label class="wan22-video-v2__field-label block text-xs font-medium mb-2">负面提示词</label>
              <a-textarea
                v-model:value="negativePrompt"
                :rows="3"
                placeholder="输入需要规避的内容..."
                class="rounded-xl"
              />
            </div>
          </div>
        </div>

        <div class="wan22-video-v2__section rounded-xl p-4">
          <h3 class="wan22-video-v2__section-title text-sm font-bold mb-3">生成设置</h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div class="setting-card">
              <div>
                <div class="setting-title">首尾帧模式</div>
                <div class="setting-desc">
                  {{ hasEndFrame ? '已自动启用，当前会同时使用起始帧和终止帧' : '上传终止帧后将自动启用' }}
                </div>
              </div>
              <a-switch :checked="hasEndFrame" disabled />
            </div>
            <div class="wan22-video-v2__fixed-card rounded-xl p-3 flex items-center justify-between">
              <div>
                <div class="setting-title">生成时长</div>
                <div class="setting-desc">当前版本固定输出 5 秒</div>
              </div>
              <span class="wan22-video-v2__fixed-value text-sm font-semibold">5 秒</span>
            </div>
            <div class="wan22-video-v2__fixed-card rounded-xl p-3 flex items-center justify-between">
              <div>
                <div class="setting-title">尾帧提取</div>
                <div class="setting-desc">默认提取并存储，当前不会直接展示给用户</div>
              </div>
              <span class="wan22-video-v2__fixed-value text-sm font-semibold">默认开启</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template #left-footer>
      <GenerationActionBar
        :cost="taskCost"
        button-text="生成视频"
        :disabled="!startObjectKey"
        :loading="isSubmitting"
        button-class="bg-blue-600 hover:bg-blue-500 w-40 h-12 text-base font-bold tracking-wider rounded-xl shadow-md transition-all hover:shadow-lg border-none flex items-center justify-center text-white"
        @submit="handleGenerate"
      >
        <template #button-icon><VideoCameraOutlined /></template>
      </GenerationActionBar>
    </template>

    <template #right-panel>
      <TaskResultPreviewPanel
        :current-task="currentTask"
        :is-image-url="isImageUrl"
        @download="downloadResult"
        @reset="resetForm"
      >
        <template #success-media="{ task }">
          <div class="w-full flex flex-col items-center gap-4">
            <video
              :src="task.resultUrl"
              controls
              class="max-w-full max-h-[46vh] rounded-xl shadow-sm bg-black"
            />
          </div>
        </template>
        <template #success-actions="{ task }">
          <div class="mt-8 flex flex-wrap gap-4 justify-center">
            <a-button
              type="primary"
              size="large"
              class="bg-blue-600 rounded-xl"
              @click="downloadResult(task.resultUrl, task.title)"
            >
              <template #icon><DownloadOutlined /></template>
              下载视频
            </a-button>
            <a-button size="large" class="rounded-xl" @click="resetForm">
              继续生成
            </a-button>
          </div>
        </template>
        <template #empty-icon>
          <VideoCameraOutlined class="text-6xl mb-4" />
        </template>
        <template #download-icon>
          <DownloadOutlined />
        </template>
        <template #failed-icon>
          <CloseCircleOutlined class="text-5xl text-red-500 mb-4" />
        </template>
      </TaskResultPreviewPanel>
    </template>
  </GenerationWorkbenchShell>
</template>

<style scoped>
:deep(.ant-input),
:deep(.ant-input-affix-wrapper),
:deep(.ant-input-number),
:deep(.ant-input-number-input),
:deep(.ant-textarea) {
  background-color: var(--theme-card-strong-bg) !important;
  color: var(--theme-text-primary) !important;
  -webkit-text-fill-color: var(--theme-text-primary) !important;
  opacity: 1 !important;
  border-color: var(--theme-border) !important;
}

:deep(.ant-input::placeholder),
:deep(.ant-input-number-input::placeholder),
:deep(textarea::placeholder) {
  color: var(--theme-input-placeholder) !important;
}

.setting-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-radius: 12px;
  border: 1px solid var(--theme-border);
  background: var(--theme-panel-bg);
  padding: 12px;
}

.wan22-video-v2__section {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
}

.wan22-video-v2__section-title {
  color: var(--theme-text-primary);
}

.wan22-video-v2__field-label,
.wan22-video-v2__progress-text {
  color: var(--theme-text-secondary);
}

.wan22-video-v2__fixed-card {
  background: color-mix(in srgb, var(--theme-panel-bg) 86%, transparent);
  border: 1px solid var(--theme-border);
}

.wan22-video-v2__fixed-value {
  color: color-mix(in srgb, var(--theme-text-primary) 72%, #06b6d4 28%);
}

.setting-title {
  color: var(--theme-text-primary);
  font-size: 0.875rem;
  font-weight: 600;
}

.setting-desc {
  color: var(--theme-text-secondary);
  font-size: 0.75rem;
  margin-top: 2px;
}
</style>
