<script setup lang="ts">
import { ref, onUnmounted, computed, watch, onMounted } from 'vue'
import { UploadOutlined, InboxOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'

const route = useRoute()
const router = useRouter()

const taskType = computed(() => (route.query.type as string) || 'i2i_pro')
const taskTitle = computed(() => (route.query.title as string) || '图片生成')
const taskCost = computed(() => {
  if (taskType.value === 'edit' && selectedLora.value) {
    return 2 // img2img_lora cost
  }
  return Number(route.query.cost) || 3
})

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isVideoUrl, isImageUrl, downloadResult } = useTaskResult()

const fileList = ref<any[]>([])
const objectKey = ref<string | null>(null)
const prompt = ref('')

const filePreview = ref<string | null>(null)
const isTemplateApplied = ref(false)

// LoRA Selection for Edit mode
const selectedLora = ref<string>('')
const loraOptions = [
  { value: '', label: '无' },
  { value: 'qwen/YARN_1.0.safetensors', label: '逼真' },
  { value: 'qwen/adjust_pussy_anus.safetensors', label: '菊花+内凹穴' },
  { value: 'qwen/realistic_texture.safetensors', label: '真实质感' },
  { value: 'qwen/flat_chest_hairless.safetensors', label: '平胸/无毛穴' },
  { value: 'qwen/penis.safetensors', label: '扶他(阴茎)' }
]

onMounted(() => {
  if (route.query.apply === 'true') {
    const ctxStr = sessionStorage.getItem('galleryApplyContext')
    if (ctxStr) {
      try {
        const ctx = JSON.parse(ctxStr)
        if (ctx.task_type === taskType.value) {
          if (ctx.prompt) prompt.value = ctx.prompt
          if (ctx.lora_name) selectedLora.value = ctx.lora_name
          isTemplateApplied.value = true
        }
      } catch (e) {
        console.error('Failed to parse apply context', e)
      }
    }
  }
})

watch(fileList, (newVal) => {
  if (newVal.length > 0 && newVal[0].originFileObj) {
    filePreview.value = URL.createObjectURL(newVal[0].originFileObj)
  } else if (newVal.length > 0 && newVal[0] instanceof File) {
    filePreview.value = URL.createObjectURL(newVal[0])
  } else {
    if (filePreview.value) URL.revokeObjectURL(filePreview.value)
    filePreview.value = null
  }
})

const beforeUpload = async (file: any) => {
  fileList.value = [file]
  const key = await uploadFile(file)
  if (key) objectKey.value = key
  return false
}

const handleRemove = () => {
  fileList.value = []
  objectKey.value = null
}

const handleGenerate = async () => {
  if (!objectKey.value) {
    message.warning('请先上传图片！')
    return
  }
  
  if (!prompt.value.trim()) {
    message.warning('请输入提示词！')
    return
  }

  const payload: any = {
    task_type: taskType.value === 'edit' && selectedLora.value ? 'img2img_lora' : taskType.value,
    inputs: {
      images: [objectKey.value]
    },
    prompt: prompt.value.trim(),
    priority: 0,
    is_template: isTemplateApplied.value
  }

  if (payload.task_type === 'img2img_lora') {
    payload.inputs.lora_name = selectedLora.value
    payload.inputs.lora_strength = 0.3
  }

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
  }
}

const resetForm = () => {
  handleRemove()
  prompt.value = ''
  setSubmittedTaskId(null)
}
</script>

<template>
  <div class="image-prompt-container max-w-7xl mx-auto flex flex-col h-[calc(100vh-80px)] w-full py-4 px-2 sm:px-6">
    <div class="flex flex-col lg:flex-row gap-6 flex-grow min-h-0">
      <!-- Left Panel: Input & Settings -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-800/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-700/50 overflow-hidden shrink-0">
        <div class="p-6 flex-grow overflow-y-auto custom-scrollbar">
          <h2 class="text-2xl font-bold mb-2 text-slate-100">{{ taskTitle }}</h2>
          <p class="text-slate-400 mb-6 text-sm">上传一张图片，并输入你想要 AI 如何修改它的描述。</p>
          
          <!-- Template Mode Notice -->
          <div v-if="isTemplateApplied" class="mb-6 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
            <div class="text-indigo-400 mr-3">✨</div>
            <div class="text-slate-300 text-sm">已加载一键应用模板，原作品的提示词已自动填入，您只需上传基础图片即可生成同款效果。</div>
          </div>
          
          <div class="flex flex-col gap-6">
            <div v-if="taskType === 'edit'" class="w-full bg-slate-900/60 rounded-xl p-4 border border-slate-700/50 shrink-0">
              <h3 class="text-sm font-bold mb-3 text-slate-200 flex items-center">
                <span class="text-slate-500 mr-2">0.</span> 附加模型 (LoRA)
              </h3>
              <div class="flex flex-wrap gap-3">
                <a-radio-group v-model:value="selectedLora" button-style="solid" class="w-full sm:w-auto" :disabled="isTemplateApplied">
                  <a-radio-button v-for="option in loraOptions" :key="option.value" :value="option.value" class="text-center">
                    {{ option.label }}
                  </a-radio-button>
                </a-radio-group>
              </div>
            </div>

            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Image Upload -->
              <div class="upload-section flex flex-col w-full md:w-[40%] min-w-[160px] shrink-0 h-48 md:h-full">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center">
                  <span class="text-slate-500 mr-2">1.</span> 基础图片
                </h3>
                <div v-if="filePreview" class="relative group rounded-xl overflow-hidden border border-slate-600/50 bg-slate-900/50 flex items-center justify-center flex-grow w-full">
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
              <div class="prompt-section flex flex-col flex-grow min-w-0 h-48 md:h-full">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center shrink-0">
                  <span class="text-slate-500 mr-2">2.</span> 输入修改描述
                </h3>
                
                <div v-if="isTemplateApplied" class="bg-slate-900/80 border border-slate-700/50 rounded-xl p-4 text-center flex-grow flex flex-col items-center justify-center">
                  <div class="flex items-center justify-center text-slate-500 mb-2">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                  <span class="text-sm font-medium">提示词已锁定</span>
                </div>
                  <p class="text-slate-400 text-xs">提示词已由模板自动配置并隐藏。</p>
                </div>
                
                <template v-else>
                  <a-textarea 
                    v-model:value="prompt" 
                    placeholder="例如：把背景变成海滩，让他戴上墨镜..." 
                    class="rounded-xl border-slate-600/50 focus:border-blue-500 focus:ring-blue-500 text-sm p-3 flex-grow resize-none w-full !text-slate-200"
                  />
                  <p class="text-xs text-slate-500 mt-2 shrink-0">提示：描述越详细， AI 理解越准确。</p>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Action Bar in Left Panel -->
        <div class="p-6 border-t border-slate-700/50 bg-slate-900/40 shrink-0 flex items-center justify-between">
          <div class="flex flex-col">
            <span class="text-slate-400 text-sm font-medium mb-1">预计消耗灵石</span>
            <div class="flex items-baseline text-blue-400 font-bold">
              <span class="text-2xl leading-none mr-1">{{ taskCost }}</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6 2L2 8l10 14L22 8l-4-6H6z"></path></svg>
            </div>
          </div>
          
          <a-button 
            type="primary" 
            size="large" 
            class="bg-blue-600 hover:bg-blue-500 border-none px-8 font-bold tracking-wider rounded-xl shadow-lg shadow-blue-500/20" 
            :disabled="!objectKey || !prompt"
            :loading="isSubmitting"
            @click="handleGenerate"
          >
            <template #icon><picture-outlined /></template>
            {{ isSubmitting ? '提交中...' : '生成图片' }}
          </a-button>
        </div>
      </div>

      <!-- Right Panel: Result Preview -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-800/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-700/50 overflow-hidden relative">
        <div class="p-6 flex-grow flex flex-col items-center justify-center h-full overflow-y-auto custom-scrollbar">
          
          <!-- Empty State -->
          <div v-if="!currentTask" class="flex flex-col items-center justify-center text-slate-500 w-full h-full opacity-60">
            <picture-outlined class="text-6xl mb-4" />
            <p class="text-lg font-medium">结果预览区</p>
            <p class="text-sm mt-2">请在左侧配置参数并点击生成，结果将在此处显示</p>
          </div>

          <!-- Result Section -->
          <div v-else class="w-full h-full flex flex-col items-center justify-center">
            <h3 class="text-xl font-bold mb-6 text-slate-200 w-full border-b border-slate-700/50 pb-4 flex items-center">
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
</style>
