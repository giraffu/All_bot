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
  buildDefaultLtxVideoLoraItem,
  getDefaultImageToVideoLoraSelection,
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
  getImageToVideoRequestTaskType,
  IMAGE_TO_VIDEO_LORA_OPTIONS,
  LTX_VIDEO_LORA_OPTIONS,
  normalizeLtxVideoLoraItems,
  isUnifiedImageToVideoTaskType,
  normalizeImageToVideoLoraSelection,
  type LtxVideoLoraItem
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
const loraStrength = computed(() => getImageToVideoPayloadLoraStrength(taskType.value, loraSelection.value))
const ltxLoraItems = ref<LtxVideoLoraItem[]>([])
const selectedLtxLoraNames = ref<string[]>([])
const expandedLtxLoraEditors = ref<string[]>([])

const syncLtxLoraItems = (names: string[]) => {
  const uniqueNames = Array.from(new Set(names.filter(value => value && value !== '__none__'))).slice(0, 3)
  if (uniqueNames.length < names.length) {
    message.warning('最多只能选择 3 个附加模型')
  }
  selectedLtxLoraNames.value = uniqueNames
  ltxLoraItems.value = uniqueNames
    .map((name) => {
      const existing = ltxLoraItems.value.find(item => item.name === name)
      return existing ?? buildDefaultLtxVideoLoraItem(name)
    })
    .filter((item): item is LtxVideoLoraItem => Boolean(item))
  expandedLtxLoraEditors.value = expandedLtxLoraEditors.value.filter(name => uniqueNames.includes(name))
}

const removeLtxLoraItem = (name: string) => {
  syncLtxLoraItems(selectedLtxLoraNames.value.filter(item => item !== name))
}

const updateLtxLoraStrength = (name: string, strength: number | null) => {
  if (typeof strength !== 'number' || !Number.isFinite(strength)) {
    return
  }
  const nextStrength = Math.min(2, Math.max(0.1, Number(strength.toFixed(2))))
  ltxLoraItems.value = ltxLoraItems.value.map(item => (
    item.name === name
      ? { ...item, strength: nextStrength }
      : item
  ))
}

const toggleLtxLoraStrengthEditor = (name: string) => {
  expandedLtxLoraEditors.value = expandedLtxLoraEditors.value.includes(name)
    ? expandedLtxLoraEditors.value.filter(item => item !== name)
    : [...expandedLtxLoraEditors.value, name]
}

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
        ltxLoraItems.value = normalizeLtxVideoLoraItems(templateState.loraItems)
        selectedLtxLoraNames.value = ltxLoraItems.value.map(item => item.name)
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

watch(isLtxVideo, (value) => {
  if (!value) {
    ltxLoraItems.value = []
    selectedLtxLoraNames.value = []
    expandedLtxLoraEditors.value = []
  }
}, { immediate: true })

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
    loraStrength: loraStrength.value,
    loraItems: isLtxVideo.value ? ltxLoraItems.value : undefined,
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
  ltxLoraItems.value = []
  selectedLtxLoraNames.value = []
  expandedLtxLoraEditors.value = []
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
              v-if="isUnifiedImageToVideo || isLtxVideo"
              class="w-full bg-slate-500/60 rounded-xl p-4 border border-slate-400/50 shrink-0"
            >
              <h3 class="text-sm font-bold mb-3 text-slate-200 flex items-center">
                <span class="text-slate-500 mr-2">0.</span> 附加模型 (LoRA)
              </h3>
              <a-radio-group
                v-if="!isLtxVideo"
                v-model:value="loraSelection"
                button-style="solid"
                class="video-lora-group w-full"
              >
                <a-radio-button
                  v-for="option in (isLtxVideo ? LTX_VIDEO_LORA_OPTIONS : IMAGE_TO_VIDEO_LORA_OPTIONS)"
                  :key="option.value"
                  :value="option.value"
                  class="text-center"
                >
                  {{ option.label }}
                </a-radio-button>
              </a-radio-group>
              <template v-else>
                <a-select
                  :value="selectedLtxLoraNames"
                  mode="multiple"
                  placeholder="选择要叠加的附加模型"
                  class="w-full"
                  :max-tag-count="2"
                  :max-tag-placeholder="(omittedValues: Array<{ label: string; value: string }>) => `+${omittedValues.length}`"
                  @change="syncLtxLoraItems($event as string[])"
                >
                  <a-select-option
                    v-for="option in LTX_VIDEO_LORA_OPTIONS.filter(item => item.value !== '__none__')"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </a-select-option>
                </a-select>
                <p class="mt-3 text-xs text-slate-400">最多可叠加 3 个附加模型，每个模型可单独调整强度。</p>
                <div v-if="ltxLoraItems.length > 0" class="mt-4 space-y-3">
                  <div
                    v-for="item in ltxLoraItems"
                    :key="item.name"
                    class="rounded-xl border border-slate-400/40 bg-slate-900/30 p-3"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <div class="text-sm text-slate-100">
                        {{ LTX_VIDEO_LORA_OPTIONS.find(option => option.value === item.name)?.label ?? item.name }}
                      </div>
                      <div class="flex items-center gap-2">
                        <span class="text-xs text-slate-400">默认/当前强度：{{ item.strength.toFixed(2) }}</span>
                        <a-button size="small" @click="toggleLtxLoraStrengthEditor(item.name)">
                          {{ expandedLtxLoraEditors.includes(item.name) ? '收起设置' : '设置强度' }}
                        </a-button>
                        <a-button size="small" danger ghost @click="removeLtxLoraItem(item.name)">移除</a-button>
                      </div>
                    </div>
                    <div v-if="expandedLtxLoraEditors.includes(item.name)" class="mt-3 flex items-center gap-3">
                      <a-slider
                        :min="0.1"
                        :max="2"
                        :step="0.05"
                        :value="item.strength"
                        class="flex-1"
                        @update:value="updateLtxLoraStrength(item.name, $event as number)"
                      />
                      <a-input-number
                        :min="0.1"
                        :max="2"
                        :step="0.05"
                        :value="item.strength"
                        size="small"
                        @update:value="updateLtxLoraStrength(item.name, $event as number | null)"
                      />
                    </div>
                  </div>
                </div>
              </template>
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
  background-color: var(--theme-card-strong-bg) !important;
  color: var(--theme-text-primary) !important;
  border-color: var(--theme-border) !important;
}
:deep(.ant-select-selection-item) {
  color: var(--theme-text-primary) !important;
}
:deep(.ant-select-selection-placeholder) {
  color: var(--theme-text-muted) !important;
}
:deep(.ant-select-arrow) {
  color: var(--theme-text-secondary) !important;
}
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
:deep(.compact-option-group .ant-radio-button-wrapper) {
  min-width: 0;
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
