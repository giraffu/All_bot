<script setup lang="ts">
import { ref, onUnmounted, computed, watch, onMounted } from 'vue'
import { UploadOutlined, InboxOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'

const route = useRoute()
const router = useRouter()
const { loadApplyContext } = useGalleryApplyContext()

const taskType = computed(() => (route.query.type as string) || 'i2i_pro')
const taskTitle = computed(() => (route.query.title as string) || '图片生成')
const maxImages = computed(() => ['i2i_pro', 'i2i_draw'].includes(taskType.value) ? 1 : 2)
const taskCost = computed(() => {
  if (taskType.value === 'edit' || taskType.value === 'img2img_lora') {
    return uploadedImages.value.length === 2 ? 6 : 2
  }
  return Number(route.query.cost) || 3
})

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isVideoUrl, isImageUrl, downloadResult } = useTaskResult()

const uploadedImages = ref<{key: string, preview: string}[]>([])
const pendingUploads = ref(0)
const prompt = ref('')
const templateSourcePostId = ref<number | null>(null)

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

const LORA_DEFAULT_STRENGTHS: Record<string, number> = {
  'qwen/YARN_1.0.safetensors': 0.3,
  'qwen/adjust_pussy_anus.safetensors': 1.0,
  'qwen/realistic_texture.safetensors': 0.8,
  'qwen/flat_chest_hairless.safetensors': 0.8,
  'qwen/penis.safetensors': 0.7
}

const customLoraStrength = ref<number>(1.0)

watch(selectedLora, (newLora) => {
  if (isTemplateApplied.value) return 

  if (newLora) {
    customLoraStrength.value = LORA_DEFAULT_STRENGTHS[newLora] || 1.0
  }
})

watch(taskType, () => {
  resetForm()
})

onMounted(() => {
  if (route.query.apply === 'true') {
    const ctx = loadApplyContext()
    if (ctx && ctx.task_type === taskType.value) {
      if (ctx.prompt) prompt.value = ctx.prompt
      if (ctx.source_post_id != null) {
        templateSourcePostId.value = Number(ctx.source_post_id)
      }
      if (ctx.lora_name) {
        selectedLora.value = ctx.lora_name
        customLoraStrength.value = ctx.lora_strength != null 
          ? Number(ctx.lora_strength) 
          : (LORA_DEFAULT_STRENGTHS[ctx.lora_name] || 1.0)
      }
      isTemplateApplied.value = true
    }
  }
})

const beforeUpload = async (file: any) => {
  if (uploadedImages.value.length + pendingUploads.value >= maxImages.value) {
    message.warning(`最多只能上传${maxImages.value}张图片！`)
    return false
  }
  pendingUploads.value++
  try {
    const key = await uploadFile(file)
    if (key) {
      uploadedImages.value.push({
        key,
        preview: URL.createObjectURL(file)
      })
    }
  } finally {
    pendingUploads.value--
  }
  return false
}

const handleRemove = (index: number) => {
  const img = uploadedImages.value[index]
  if (img && img.preview) {
    URL.revokeObjectURL(img.preview)
  }
  uploadedImages.value.splice(index, 1)
}

const handleGenerate = async () => {
  if (uploadedImages.value.length === 0) {
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
      images: uploadedImages.value.map(img => img.key)
    },
    prompt: prompt.value.trim(),
    priority: 0,
    is_template: isTemplateApplied.value,
    ...(templateSourcePostId.value != null ? { source_post_id: templateSourcePostId.value } : {})
  }

  if (payload.task_type === 'img2img_lora') {
    payload.inputs.lora_name = selectedLora.value
    payload.inputs.lora_strength = Number(customLoraStrength.value)
  }

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
  }
}

const resetForm = () => {
  uploadedImages.value.forEach(img => {
    if (img.preview) URL.revokeObjectURL(img.preview)
  })
  uploadedImages.value = []
  
  if (!isTemplateApplied.value) {
    prompt.value = ''
    selectedLora.value = ''
    customLoraStrength.value = 1.0
  }
  
  setSubmittedTaskId(null)
}
</script>

<template>
  <div class="image-prompt-container max-w-7xl mx-auto flex flex-col h-[calc(100vh-80px)] w-full py-4 px-2 sm:px-6">
    <div class="flex flex-col lg:flex-row gap-6 flex-grow min-h-0">
      <!-- Left Panel: Input & Settings -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/50 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden shrink-0">
        <div class="p-6 flex-grow overflow-y-auto custom-scrollbar">
          <h2 class="text-2xl font-bold mb-2 text-slate-100">{{ taskTitle }}</h2>
          <p class="text-slate-400 mb-6 text-sm">上传一张图片，并输入你想要 AI 如何修改它的描述。</p>
          
          <!-- Template Mode Notice -->
          <div v-if="isTemplateApplied" class="mb-6 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
            <div class="text-indigo-400 mr-3">✨</div>
            <div class="text-slate-300 text-sm">已加载一键应用模板，原作品的提示词已自动填入，您只需上传基础图片即可生成同款效果。</div>
          </div>
          
          <div class="flex flex-col gap-6">
            <div v-if="taskType === 'edit' || taskType === 'img2img_lora'" class="w-full bg-slate-500/60 rounded-xl p-4 border border-slate-400/50 shrink-0">
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
              
              <!-- 新增：强度自定义滑块 (仅在选中了具体模型时显示) -->
              <div v-if="selectedLora" class="flex flex-col mt-4 pt-4 border-t border-slate-500/50">
                <div class="flex justify-between items-center mb-2">
                  <span class="text-xs text-slate-300">模型强度 (Lora Strength)</span>
                  <span class="text-xs text-slate-400">推荐值已自动适配</span>
                </div>
                <div class="flex items-center gap-4">
                  <a-slider 
                    v-model:value="customLoraStrength" 
                    :min="0.1" 
                    :max="2.0" 
                    :step="0.05" 
                    class="flex-grow"
                    :disabled="isTemplateApplied"
                  />
                  <a-input-number 
                    v-model:value="customLoraStrength" 
                    :min="0.1" 
                    :max="2.0" 
                    :step="0.05" 
                    class="w-20 bg-slate-800/50 border-slate-400/50 text-slate-200"
                    size="small"
                    :disabled="isTemplateApplied"
                  />
                </div>
              </div>
            </div>

            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Image Upload -->
              <div class="upload-section flex flex-col w-full md:w-[40%] min-w-[160px] shrink-0 h-48 md:h-full">
                <div class="flex items-center justify-between mb-2">
                  <h3 class="text-sm font-bold text-slate-200 flex items-center">
                    <span class="text-slate-500 mr-2">1.</span> 基础图片
                  </h3>
                  <span v-if="taskType === 'edit' || taskType === 'img2img_lora'" class="text-[10px] text-slate-400 font-normal">1张=2灵石, 2张=6灵石</span>
                </div>
                
                <div class="flex gap-2 flex-grow w-full overflow-hidden">
                  <div v-for="(img, index) in uploadedImages" :key="img.key" class="relative group rounded-xl overflow-hidden border border-slate-400/50 bg-slate-500/50 flex items-center justify-center h-full" :class="maxImages === 1 ? 'w-full' : 'w-1/2'">
                    <a-image :src="img.preview" class="max-w-full max-h-full object-contain" :preview="true" />
                    <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                      <a-button danger type="primary" @click="handleRemove(index)" class="pointer-events-auto" size="small">删除</a-button>
                    </div>
                  </div>
                  
                  <a-upload-dragger
                    v-if="uploadedImages.length < maxImages"
                    name="file"
                    :multiple="maxImages === 2"
                    accept="image/png, image/jpeg, image/webp"
                    :before-upload="beforeUpload"
                    class="upload-dragger flex-grow flex items-center justify-center h-full"
                    :class="maxImages === 1 ? 'w-full' : (uploadedImages.length === 1 ? 'w-1/2' : 'w-full')"
                    :show-upload-list="false"
                  >
                    <div class="flex flex-col items-center justify-center h-full w-full p-2">
                      <p class="ant-upload-drag-icon text-blue-500 text-2xl mb-1"><inbox-outlined></inbox-outlined></p>
                      <p class="ant-upload-text font-medium text-slate-300 text-xs">点击/拖拽</p>
                      <p v-if="taskType !== 'i2i_pro' && uploadedImages.length === 1" class="ant-upload-hint text-slate-500 mt-1 text-[10px]">第2张(可选)</p>
                      <p v-else class="ant-upload-hint text-slate-500 mt-1 text-[10px]">JPG/PNG</p>
                    </div>
                  </a-upload-dragger>
                </div>
                
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
                
                <div v-if="isTemplateApplied" class="bg-slate-500/80 border border-slate-400/50 rounded-xl p-4 text-center flex-grow flex flex-col items-center justify-center">
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
                    class="rounded-xl border-slate-400/50 focus:border-blue-500 focus:ring-blue-500 text-sm p-3 flex-grow resize-none w-full !text-slate-200"
                  />
                  <p class="text-xs text-slate-500 mt-2 shrink-0">
                    提示：描述越详细， AI 理解越准确。
                    <span v-if="taskType === 'i2i_draw'" class="text-amber-500 block mt-1">目前只支持单人女性</span>
                  </p>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Action Bar in Left Panel -->
        <div class="p-6 border-t border-slate-400/50 bg-slate-500/50 shrink-0 flex items-center justify-between">
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
            :disabled="uploadedImages.length === 0 || !prompt"
            :loading="isSubmitting"
            @click="handleGenerate"
          >
            <template #icon><picture-outlined /></template>
            {{ isSubmitting ? '提交中...' : '生成图片' }}
          </a-button>
        </div>
      </div>

      <!-- Right Panel: Result Preview -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/50 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden relative">
        <div class="p-6 flex-grow flex flex-col items-center justify-center h-full overflow-y-auto custom-scrollbar">
          
          <!-- Empty State -->
          <div v-if="!currentTask" class="flex flex-col items-center justify-center text-slate-500 w-full h-full opacity-60">
            <picture-outlined class="text-6xl mb-4" />
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

:deep(.ant-input-number) {
  background-color: rgba(15, 23, 42, 0.4) !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
  color: #e2e8f0 !important;
}
:deep(.ant-input-number-input) {
  color: #e2e8f0 !important;
}
:deep(.ant-input-number-handler-wrap) {
  background-color: rgba(15, 23, 42, 0.6) !important;
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-input-number-handler) {
  border-color: rgba(71, 85, 105, 0.5) !important;
}
:deep(.ant-input-number-handler-up-inner),
:deep(.ant-input-number-handler-down-inner) {
  color: #94a3b8 !important;
}
</style>
