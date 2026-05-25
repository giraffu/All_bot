<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { InboxOutlined, VideoCameraOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { resolveTemplateVideoApplyState } from '@/utils/templateVideoApplyState'
import { useSingleFileUploadPreview } from '@/composables/useSingleFileUploadPreview'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import {
  getDefaultImageToVideoLoraSelection,
  getImageToVideoPayloadLoraName,
  getImageToVideoRequestTaskType,
  IMAGE_TO_VIDEO_LORA_OPTIONS,
  isUnifiedImageToVideoTaskType,
  normalizeImageToVideoLoraSelection
} from '@/features/generation/imageToVideo'
import GenerationActionBar from '@/components/GenerationActionBar.vue'
import GenerationUploadCard from '@/components/GenerationUploadCard.vue'
import GenerationWorkbenchShell from '@/components/GenerationWorkbenchShell.vue'
import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'

const route = useRoute()
const { loadApplyContext } = useGalleryApplyContext()

const taskType = computed(() => (route.query.type as string) || 'image2video')
const taskTitle = computed(() => (route.query.title as string) || '动图生成')
const isUnifiedImageToVideo = computed(() => isUnifiedImageToVideoTaskType(taskType.value))
const isLtxVideo = computed(() => taskType.value === 'ltx_video')

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
const resolution = ref('512')
const duration = ref('5')
const templateSourcePostId = ref<number | null>(null)

const taskCost = computed(() => {
  if (isLtxVideo.value) {
    const dur = duration.value;
    let baseCost = 10; // 1280x704
    let multiplier = 1;
    if (dur === '10') multiplier = 2;
    else if (dur === '15') multiplier = 3;
    else if (dur === '20') multiplier = 4;
    return baseCost * multiplier;
  }
  
  const res = resolution.value;
  const dur = duration.value;
  
  let baseCost = 6;
  if (res === '720') baseCost = 18;
  else if (res === '1024') baseCost = 36;
  
  let multiplier = 1;
  if (dur === '8') multiplier = 2;
  else if (dur === '10') multiplier = 3;
  
  return baseCost * multiplier;
})
const prompt = ref('')
const loraSelection = ref(getDefaultImageToVideoLoraSelection(taskType.value))
const loraName = computed(() => getImageToVideoPayloadLoraName(taskType.value, loraSelection.value))

const isTemplateApplied = ref(false)
const isTemplateVideoSettingsLocked = ref(false)
const isTemplatePromptLocked = ref(false)
const templateSettingsWarning = ref('')

const templateApplyNotice = computed(() => {
  if (!isTemplateApplied.value) {
    return ''
  }

  if (isTemplateVideoSettingsLocked.value && isTemplatePromptLocked.value) {
    return '已加载一键应用模板，原作品的提示词、分辨率与时长等参数已自动填入，您只需上传基础图片即可生成同款大片。'
  }

  if (isTemplateVideoSettingsLocked.value) {
    return '已加载一键应用模板，分辨率与时长已按原作品恢复；模板缺少完整的提示词或模型信息，您仍可手动调整相关参数。'
  }

  if (isTemplatePromptLocked.value) {
    return '已加载一键应用模板，原作品的提示词已自动填入；由于模板缺少完整画质信息，您仍可手动选择分辨率与时长。'
  }

  return '已加载一键应用模板，但模板信息不完整，您仍可手动调整提示词、模型、分辨率与时长。'
})

onMounted(() => {
  if (isLtxVideo.value) {
    resolution.value = '1280x704'
  }
  
  if (route.query.apply === 'true') {
    const ctx = loadApplyContext()
    if (
      ctx
      && (isUnifiedImageToVideo.value || isLtxVideo.value)
    ) {
      const templateState = resolveTemplateVideoApplyState(
        ctx,
        taskType.value as 'custom_video' | 'video_lora' | 'ltx_video'
      )
      if (templateState) {
        if (templateState.prompt) prompt.value = templateState.prompt
        loraSelection.value = normalizeImageToVideoLoraSelection(templateState.loraName)
        if (templateState.sourcePostId != null) {
          templateSourcePostId.value = templateState.sourcePostId
        }
        if (templateState.resolution) resolution.value = templateState.resolution
        if (templateState.duration) duration.value = templateState.duration
        if (!isLtxVideo.value && resolution.value === '1024' && duration.value === '10') {
          resolution.value = '720'
        }

        templateSettingsWarning.value = templateState.templateSettingsWarning
        isTemplateApplied.value = templateState.isTemplateApplied
        isTemplateVideoSettingsLocked.value = templateState.isTemplateVideoSettingsLocked
        isTemplatePromptLocked.value = templateState.isTemplatePromptLocked
      }
    }
  }
})

watch(resolution, (val) => {
  if (val === '1024' && duration.value === '10') {
    duration.value = '8'
  }
})

watch(duration, (val) => {
  if (val === '10' && resolution.value === '1024') {
    resolution.value = '720'
  }
})

const handleGenerate = async () => {
  if (!objectKey.value) {
    message.warning('请先上传图片！')
    return
  }

  const payload = buildGenerationTaskPayload({
    taskType: getImageToVideoRequestTaskType(taskType.value, loraSelection.value),
    images: [objectKey.value],
    resolution: isLtxVideo.value ? resolution.value : Number(resolution.value),
    duration: Number(duration.value),
    prompt: (isUnifiedImageToVideo.value || isLtxVideo.value) ? prompt.value : undefined,
    promptTarget: 'inputs',
    loraName: loraName.value,
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
  prompt.value = ''
  loraSelection.value = getDefaultImageToVideoLoraSelection(taskType.value)
  setSubmittedTaskId(null)
}
</script>

<template>
  <GenerationWorkbenchShell :title="`${taskTitle}设置`">
    <template #left-top>
      <div v-if="isTemplateApplied" class="mb-6 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
        <div class="text-indigo-400 mr-3">✨</div>
        <div class="text-slate-300 text-sm">
          {{ templateApplyNotice }}
        </div>
      </div>
      <div v-if="templateSettingsWarning" class="mb-6 bg-amber-500/20 border border-amber-500/30 rounded-xl p-4 text-sm text-amber-200">
        {{ templateSettingsWarning }}
      </div>
    </template>

    <template #left-content>
      <div class="flex flex-col gap-6 mb-6">
            <div
              v-if="isUnifiedImageToVideo"
              class="w-full bg-slate-500/60 rounded-xl p-4 border border-slate-400/50 shrink-0"
            >
              <h3 class="text-sm font-bold mb-3 text-slate-200 flex items-center">
                <span class="text-slate-500 mr-2">0.</span> 附加模型 (LoRA)
              </h3>
              <a-radio-group
                v-model:value="loraSelection"
                button-style="solid"
                class="video-lora-group w-full"
              >
                <a-radio-button
                  v-for="option in IMAGE_TO_VIDEO_LORA_OPTIONS"
                  :key="option.value"
                  :value="option.value"
                  class="text-center"
                >
                  {{ option.label }}
                </a-radio-button>
              </a-radio-group>
            </div>

            <!-- Row for Upload & Prompt -->
            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Image Upload -->
              <GenerationUploadCard
                title="基础图片"
                step="1."
                :file-list="fileList"
                :preview-url="filePreview"
                accept="image/png, image/jpeg"
                wrapper-class="upload-section flex flex-col w-full md:w-[40%] min-w-[160px] shrink-0 h-48 md:h-full"
                :before-upload="beforeUpload"
                @remove="handleRemove"
                @update:fileList="fileList = $event"
              >
                <template #placeholder-icon>
                  <inbox-outlined />
                </template>
              </GenerationUploadCard>

                <div v-if="uploading" class="mt-2 shrink-0">
                  <span class="text-xs text-slate-400">正在上传...</span>
                  <a-progress :percent="uploadProgress" status="active" strokeColor="#3b82f6" size="small" />
                </div>

              <!-- Prompt Input -->
              <div class="prompt-section flex flex-col flex-grow min-w-0 h-48 md:h-full" v-if="isUnifiedImageToVideo || isLtxVideo">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center shrink-0">
                  <span class="text-slate-500 mr-2">2.</span> {{ isUnifiedImageToVideo ? '输入动作描述' : '输入描述 (选填)' }}
                </h3>
                
                <div v-if="isTemplatePromptLocked" class="bg-slate-500/80 border border-slate-400/50 rounded-xl p-4 text-center flex-grow flex flex-col items-center justify-center">
                  <div class="flex items-center justify-center text-slate-500 mb-2">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                    <span class="text-sm font-medium">参数已锁定</span>
                  </div>
                  <p class="text-slate-400 text-xs">模型与提示词已由模板自动配置并隐藏。</p>
                </div>
                
                <template v-else>
                  <a-textarea 
                    v-model:value="prompt" 
                    :placeholder="isUnifiedImageToVideo ? '输入视频生成的正向提示词...' : (isLtxVideo ? '例如：Real Video, m15510n4ry, A close-up view of a single petite woman...' : '例如：人物微笑，背景有风吹过...')" 
                    class="rounded-xl border-slate-400/50 focus:border-blue-500 focus:ring-blue-500 text-sm p-3 flex-grow resize-none w-full"
                  />
                </template>
              </div>
              <div class="prompt-section flex flex-col justify-center text-center p-4 bg-slate-500/50 rounded-xl flex-grow min-w-0 h-48 md:h-full" v-else>
                <component :is="InboxOutlined" class="text-4xl text-gray-300 mb-2" />
                <h3 class="text-base font-medium text-slate-400">AI 动作预设</h3>
                <p class="text-xs text-slate-500 mt-2">自动生成专属动作视频</p>
              </div>
            </div>
      </div>

      <div class="settings-section border-t border-slate-400/50 pt-5">
        <h3 class="text-sm font-bold mb-3 text-slate-200">输出设置</h3>
        <div v-if="isTemplateVideoSettingsLocked" class="bg-slate-500/80 border border-slate-400/50 rounded-xl p-4 text-center">
          <p class="text-slate-400 text-xs">分辨率与时长已根据模板锁定，无需手动选择。</p>
        </div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div class="rounded-xl bg-slate-900/20 border border-slate-400/30 p-3">
            <label class="block text-xs font-medium text-slate-300 mb-2">分辨率</label>
            <a-radio-group v-if="isLtxVideo" v-model:value="resolution" button-style="solid" class="w-full grid grid-cols-1 gap-2 max-w-[160px]">
              <a-radio-button value="1280x704" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">1280x704 (自动适应)</a-radio-button>
            </a-radio-group>
            <a-radio-group v-else v-model:value="resolution" button-style="solid" class="compact-option-group w-full grid grid-cols-3 gap-2">
              <a-radio-button value="512" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">512p</a-radio-button>
              <a-radio-button value="720" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">720p</a-radio-button>
              <a-radio-button value="1024" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center" :disabled="duration === '10'">1024p</a-radio-button>
            </a-radio-group>
          </div>
          <div class="rounded-xl bg-slate-900/20 border border-slate-400/30 p-3">
            <label class="block text-xs font-medium text-slate-300 mb-2">生成时长</label>
            <a-radio-group v-if="isLtxVideo" v-model:value="duration" button-style="solid" class="w-full grid grid-cols-4 gap-2 max-w-[320px]">
              <a-radio-button value="5" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">5 秒</a-radio-button>
              <a-radio-button value="10" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">10 秒</a-radio-button>
              <a-radio-button value="15" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">15 秒</a-radio-button>
              <a-radio-button value="20" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">20 秒</a-radio-button>
            </a-radio-group>
            <a-radio-group v-else v-model:value="duration" button-style="solid" class="compact-option-group w-full grid grid-cols-3 gap-2">
              <a-radio-button value="5" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">5 秒</a-radio-button>
              <a-radio-button value="8" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">8 秒</a-radio-button>
              <a-radio-button value="10" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center" :disabled="resolution === '1024'">10 秒</a-radio-button>
            </a-radio-group>
          </div>
        </div>
      </div>
    </template>

    <template #left-footer>
      <GenerationActionBar
        :cost="taskCost"
        button-text="生成视频"
        :disabled="!objectKey"
        :loading="isSubmitting"
        button-class="bg-blue-600 hover:bg-blue-500 w-40 h-12 text-base font-bold tracking-wider rounded-xl shadow-md transition-all hover:shadow-lg border-none flex items-center justify-center text-white"
        @submit="handleGenerate"
      >
        <template #button-icon><video-camera-outlined /></template>
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
          <video-camera-outlined class="text-6xl mb-4" />
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
:deep(.ant-select-selector) {
  background-color: rgba(15, 23, 42, 0.4) !important;
  color: #e2e8f0 !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-select-selection-item) {
  color: #e2e8f0 !important;
}
:deep(.ant-select-arrow) {
  color: #94a3b8 !important;
}
:deep(.ant-input), :deep(.ant-input-affix-wrapper) {
  background-color: rgba(15, 23, 42, 0.4) !important;
  color: #e2e8f0 !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-input::placeholder) {
  color: #64748b !important;
}
:deep(.ant-upload.ant-upload-drag) {
  background: rgba(15, 23, 42, 0.4) !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-upload.ant-upload-drag:hover) {
  border-color: #3b82f6 !important;
}
:deep(.ant-upload.ant-upload-drag .ant-upload-text) {
  color: #cbd5e1 !important;
}
:deep(.ant-upload.ant-upload-drag .ant-upload-hint) {
  color: #64748b !important;
}

.upload-dragger {
  background: rgba(15, 23, 42, 0.4);
  border-radius: 12px;
}
.video-lora-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
:deep(.video-lora-group .ant-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
:deep(.video-lora-group .ant-radio-button-wrapper) {
  border-radius: 8px !important;
  border-left-width: 1px !important;
}
:deep(.ant-radio-button-wrapper) {
  background: rgba(15, 23, 42, 0.4) !important;
  color: #94a3b8 !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled)) {
  background: #3b82f6 !important;
  color: #ffffff !important;
  border-color: #3b82f6 !important;
}
:deep(.ant-radio-button-wrapper:before) {
  display: none !important;
}
:deep(.compact-option-group .ant-radio-button-wrapper) {
  min-width: 0;
}
</style>
