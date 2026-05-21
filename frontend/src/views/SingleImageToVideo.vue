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

const route = useRoute()
const { loadApplyContext } = useGalleryApplyContext()

const taskType = computed(() => (route.query.type as string) || 'image2video')
const taskTitle = computed(() => (route.query.title as string) || '动图生成')
const isCustomVideo = computed(() => taskType.value === 'custom_video')
const isVideoLora = computed(() => taskType.value === 'video_lora')
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
const loraName = ref('BreastGrow')

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
      && (taskType.value === 'custom_video'
        || taskType.value === 'video_lora'
        || taskType.value === 'ltx_video')
    ) {
      const templateState = resolveTemplateVideoApplyState(ctx, taskType.value)
      if (templateState) {
        if (templateState.prompt) prompt.value = templateState.prompt
        if (templateState.loraName) loraName.value = templateState.loraName
        if (templateState.sourcePostId != null) {
          templateSourcePostId.value = templateState.sourcePostId
        }
        if (templateState.resolution) resolution.value = templateState.resolution
        if (templateState.duration) duration.value = templateState.duration

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
  
  if (isVideoLora.value && !loraName.value) {
    message.warning('请选择附加模型！')
    return
  }

  const payload = {
    task_type: taskType.value,
    inputs: {
      images: [objectKey.value],
      resolution: isLtxVideo.value ? resolution.value : Number(resolution.value),
      duration: Number(duration.value),
      ...((isCustomVideo.value || isVideoLora.value || isLtxVideo.value) && prompt.value ? { prompt: prompt.value } : {}),
      ...(isVideoLora.value ? { lora_name: loraName.value } : {})
    },
    priority: 0,
    is_template: isTemplateApplied.value,
    ...(templateSourcePostId.value != null ? { source_post_id: templateSourcePostId.value } : {})
  }

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
  }
}

const resetForm = () => {
  handleRemove()
  prompt.value = ''
  loraName.value = 'BreastGrow'
  setSubmittedTaskId(null)
}
</script>

<template>
  <div class="single-image-video-container max-w-7xl mx-auto flex flex-col h-[calc(100vh-80px)] w-full py-4 px-2 sm:px-6">
    <div class="flex flex-col lg:flex-row gap-6 flex-grow min-h-0">
      <!-- Left Panel: Input & Settings -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden shrink-0">
        <div class="p-6 flex-grow overflow-y-auto custom-scrollbar">
          <h2 class="text-2xl font-bold mb-5 text-slate-100">{{ taskTitle }}设置</h2>
          
          <!-- Template Mode Notice -->
          <div v-if="isTemplateApplied" class="mb-6 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
            <div class="text-indigo-400 mr-3">✨</div>
            <div class="text-slate-300 text-sm">
              {{ templateApplyNotice }}
            </div>
          </div>
          <div v-if="templateSettingsWarning" class="mb-6 bg-amber-500/20 border border-amber-500/30 rounded-xl p-4 text-sm text-amber-200">
            {{ templateSettingsWarning }}
          </div>
          
          <div class="flex flex-col gap-6 mb-6">
            <!-- Row for Upload & Prompt -->
            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Image Upload -->
              <div class="upload-section flex flex-col w-full md:w-[40%] min-w-[160px] shrink-0 h-48 md:h-full">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center shrink-0">
                  <span class="text-slate-500 mr-2">1.</span> 基础图片
                </h3>
                <div v-if="filePreview" class="relative group rounded-xl overflow-hidden border border-slate-400/50 bg-slate-500/50 flex items-center justify-center flex-grow w-full">
                  <a-image :src="filePreview" class="max-w-full max-h-full object-contain" :preview="true" />
                  <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                    <a-button danger type="primary" @click="handleRemove" class="pointer-events-auto" size="small">重新上传</a-button>
                  </div>
                </div>
                <a-upload-dragger
                  v-else
                  v-model:fileList="fileList"
                  name="file"
                  :multiple="false"
                  accept="image/png, image/jpeg"
                  :before-upload="beforeUpload"
                  @remove="handleRemove"
                  class="upload-dragger flex-grow flex items-center justify-center w-full"
                  :show-upload-list="false"
                >
                  <div class="flex flex-col items-center justify-center h-full w-full p-4">
                    <p class="ant-upload-drag-icon text-blue-500 text-3xl mb-2"><inbox-outlined></inbox-outlined></p>
                    <p class="ant-upload-text font-medium text-slate-300 text-sm">点击/拖拽</p>
                    <p class="ant-upload-hint text-slate-500 mt-1 text-xs">JPG/PNG</p>
                  </div>
                </a-upload-dragger>
                
                <div v-if="uploading" class="mt-2 shrink-0">
                  <span class="text-xs text-slate-400">正在上传...</span>
                  <a-progress :percent="uploadProgress" status="active" strokeColor="#3b82f6" size="small" />
                </div>
              </div>

              <!-- Prompt Input -->
              <div class="prompt-section flex flex-col flex-grow min-w-0 h-48 md:h-full" v-if="isCustomVideo || isVideoLora || isLtxVideo">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center shrink-0">
                  <span class="text-slate-500 mr-2">2.</span> {{ isVideoLora ? '配置动作描述' : '输入描述 (选填)' }}
                </h3>
                
                <div v-if="isTemplatePromptLocked" class="bg-slate-500/80 border border-slate-400/50 rounded-xl p-4 text-center flex-grow flex flex-col items-center justify-center">
                  <div class="flex items-center justify-center text-slate-500 mb-2">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                    <span class="text-sm font-medium">参数已锁定</span>
                  </div>
                  <p class="text-slate-400 text-xs">模型与提示词已由模板自动配置并隐藏。</p>
                </div>
                
                <template v-else>
                  <div v-if="isVideoLora" class="mb-3 shrink-0">
                    <a-select
                      v-model:value="loraName"
                      placeholder="请选择附加模型"
                      class="w-full rounded-xl custom-select"
                      :popupClassName="'custom-dropdown'"
                    >
                      <a-select-option value="BreastGrow">巨乳膨胀</a-select-option>
                      <a-select-option value="BreastInsertion">乳交</a-select-option>
                      <a-select-option value="Cum">颜射</a-select-option>
                      <a-select-option value="Cunilingus">舔阴</a-select-option>
                      <a-select-option value="Flatchested">平胸</a-select-option>
                      <a-select-option value="Footjob">足交</a-select-option>
                      <a-select-option value="Insertion">插入优化</a-select-option>
                    </a-select>
                  </div>
                  <a-textarea 
                    v-model:value="prompt" 
                    :placeholder="isVideoLora ? '输入视频生成的正向提示词...' : (isLtxVideo ? '例如：Real Video, m15510n4ry, A close-up view of a single petite woman...' : '例如：人物微笑，背景有风吹过...')" 
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
          
          <!-- Video Settings -->
          <div class="settings-section border-t border-slate-400/50 pt-5">
            <h3 class="text-sm font-bold mb-3 text-slate-200">输出设置</h3>
            <div v-if="isTemplateVideoSettingsLocked" class="bg-slate-500/80 border border-slate-400/50 rounded-xl p-4 text-center">
              <p class="text-slate-400 text-xs">分辨率与时长已根据模板锁定，无需手动选择。</p>
            </div>
            <div v-else class="flex flex-col gap-4">
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-2">分辨率</label>
                <a-radio-group v-if="isLtxVideo" v-model:value="resolution" button-style="solid" class="w-full grid grid-cols-1 gap-2 max-w-[160px]">
                  <a-radio-button value="1280x704" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">1280x704 (自动适应)</a-radio-button>
                </a-radio-group>
                <a-radio-group v-else v-model:value="resolution" button-style="solid" class="w-full grid grid-cols-3 gap-2">
                  <a-radio-button value="512" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">512p</a-radio-button>
                  <a-radio-button value="720" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">720p</a-radio-button>
                  <a-radio-button value="1024" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center" :disabled="duration === '10'">1024p</a-radio-button>
                </a-radio-group>
              </div>
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-2">生成时长</label>
                <a-radio-group v-if="isLtxVideo" v-model:value="duration" button-style="solid" class="w-full grid grid-cols-4 gap-2 max-w-[320px]">
                  <a-radio-button value="5" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">5 秒</a-radio-button>
                  <a-radio-button value="10" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">10 秒</a-radio-button>
                  <a-radio-button value="15" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">15 秒</a-radio-button>
                  <a-radio-button value="20" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">20 秒</a-radio-button>
                </a-radio-group>
                <a-radio-group v-else v-model:value="duration" button-style="solid" class="w-full grid grid-cols-3 gap-2 max-w-[240px]">
                  <a-radio-button value="5" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">5 秒</a-radio-button>
                  <a-radio-button value="8" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center">8 秒</a-radio-button>
                  <a-radio-button value="10" class="w-full text-center py-1.5 h-auto text-xs rounded-lg !border-none !border-l-0 shadow-sm leading-tight flex items-center justify-center" :disabled="resolution === '1024'">10 秒</a-radio-button>
                </a-radio-group>
              </div>
            </div>
          </div>
        </div>

        <!-- Action Bar in Left Panel -->
        <div class="action-bar bg-slate-500/40 p-6 border-t border-slate-400/50 flex justify-between items-center shrink-0">
          <div class="cost-info flex flex-col">
            <span class="text-slate-400 text-sm font-medium">预计消耗灵石</span>
            <div class="flex items-end mt-1">
              <span class="font-bold text-3xl text-blue-600 leading-none">{{ taskCost }}</span>
              <span class="text-lg text-blue-400 ml-1 mb-0.5">💎</span>
            </div>
          </div>
          
          <a-button 
            type="primary" 
            size="large" 
            class="bg-blue-600 hover:bg-blue-500 w-40 h-12 text-base font-bold tracking-wider rounded-xl shadow-md transition-all hover:shadow-lg border-none flex items-center justify-center text-white" 
            :disabled="!objectKey"
            :loading="isSubmitting"
            @click="handleGenerate"
          >
            <template #icon><video-camera-outlined /></template>
            {{ isSubmitting ? '提交中...' : '生成视频' }}
          </a-button>
        </div>
      </div>

      <!-- Right Panel: Result Preview -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden relative">
        <div class="p-6 flex-grow flex flex-col items-center justify-center h-full overflow-y-auto custom-scrollbar">
          
          <!-- Empty State -->
          <div v-if="!currentTask" class="flex flex-col items-center justify-center text-slate-500 w-full h-full opacity-60">
            <video-camera-outlined class="text-6xl mb-4" />
            <p class="text-lg font-medium">结果预览区</p>
            <p class="text-sm mt-2">请在左侧配置参数并点击生成，结果将在此处显示</p>
          </div>

          <!-- Result Section -->
          <div v-else class="w-full h-full flex flex-col items-center justify-center">
            <h3 class="text-xl font-bold mb-6 text-slate-200 w-full border-b border-slate-400/50 pb-4 flex items-center">
              <span class="text-blue-500 mr-2">✨</span> 生成结果
            </h3>
            
            <div v-if="currentTask.status === 'pending' || currentTask.status === 'running'" class="flex flex-col items-center justify-center py-8 w-full flex-grow">
              <a-spin size="large" />
              <p class="mt-4 text-slate-400 font-medium">正在生成中... {{ currentTask.progress }}%</p>
              <p v-if="currentTask.queuePos" class="text-sm text-slate-500 mt-1">前面还有 {{ currentTask.queuePos }} 人排队</p>
              <a-progress :percent="currentTask.progress" status="active" strokeColor="#3b82f6" class="w-full max-w-md mt-4" />
            </div>
            
            <div v-else-if="currentTask.status === 'success' && currentTask.resultUrl" class="flex flex-col items-center w-full flex-grow justify-center">
              <a-image v-if="isImageUrl(currentTask.resultUrl)" :src="currentTask.resultUrl" class="max-w-full max-h-[50vh] rounded-xl shadow-sm object-contain" :preview="true" />
              <video v-else :src="currentTask.resultUrl" controls class="max-w-full max-h-[50vh] rounded-xl shadow-sm bg-black"></video>
              
              <div class="mt-8 flex gap-4">
                <a-button type="primary" size="large" class="bg-blue-600 rounded-xl" @click="downloadResult(currentTask.resultUrl, currentTask.title)">
                  <template #icon><download-outlined /></template> 下载结果
                </a-button>
                <a-button size="large" class="rounded-xl" @click="resetForm">
                  继续生成
                </a-button>
              </div>
            </div>
            
            <div v-else-if="currentTask.status === 'failed'" class="flex flex-col items-center py-8 w-full flex-grow justify-center">
              <close-circle-outlined class="text-5xl text-red-500 mb-4" />
              <p class="text-red-600 font-medium text-lg">生成失败</p>
              <p class="text-slate-400 mt-2">{{ currentTask.error || '未知错误' }}</p>
              <a-button class="mt-6 rounded-xl" @click="resetForm">重试</a-button>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  </div>
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
</style>

<style>
.custom-dropdown {
  background-color: rgba(30, 41, 59, 0.95) !important;
  backdrop-filter: blur(12px) !important;
  border: 1px solid rgba(71, 85, 105, 0.5) !important;
}
.custom-dropdown .ant-select-item {
  color: #cbd5e1 !important;
}
.custom-dropdown .ant-select-item-option-active,
.custom-dropdown .ant-select-item-option-selected {
  background-color: rgba(56, 189, 248, 0.15) !important;
  color: #38bdf8 !important;
}
</style>
