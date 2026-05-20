<script setup lang="ts">
import { ref, watch } from 'vue'
import { InboxOutlined, SwapOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useRoute } from 'vue-router'
import { onMounted } from 'vue'

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const { loadApplyContext } = useGalleryApplyContext()
const route = useRoute()

const faceFileList = ref<any[]>([])
const bodyFileList = ref<any[]>([])

const faceObjectKey = ref<string | null>(null)
const bodyObjectKey = ref<string | null>(null)

const facePreview = ref<string | null>(null)
const bodyPreview = ref<string | null>(null)
const isTemplateApplied = ref(false)
const templateSourcePostId = ref<number | null>(null)

onMounted(() => {
  if (route.query.apply === 'true') {
    const ctx = loadApplyContext()
    if (ctx && ctx.task_type === 'face_swap' && ctx.input_file) {
      // prefill target image
      bodyObjectKey.value = ctx.input_file
      bodyPreview.value = ctx.input_file_url || null
      if (ctx.source_post_id != null) {
        templateSourcePostId.value = Number(ctx.source_post_id)
      }
      isTemplateApplied.value = true
    }
  }
})

watch(faceFileList, (newVal) => {
  if (newVal.length > 0 && newVal[0].originFileObj) {
    facePreview.value = URL.createObjectURL(newVal[0].originFileObj)
  } else if (newVal.length > 0 && newVal[0] instanceof File) {
    facePreview.value = URL.createObjectURL(newVal[0])
  } else {
    if (facePreview.value) URL.revokeObjectURL(facePreview.value)
    facePreview.value = null
  }
})

watch(bodyFileList, (newVal) => {
  if (newVal.length > 0 && newVal[0].originFileObj) {
    bodyPreview.value = URL.createObjectURL(newVal[0].originFileObj)
  } else if (newVal.length > 0 && newVal[0] instanceof File) {
    bodyPreview.value = URL.createObjectURL(newVal[0])
  } else {
    if (bodyPreview.value) URL.revokeObjectURL(bodyPreview.value)
    bodyPreview.value = null
  }
})

// Before upload intercepts default AntD behavior
const beforeUploadFace = async (file: any) => {
  faceFileList.value = [file]
  const key = await uploadFile(file)
  if (key) faceObjectKey.value = key
  return false // Prevent default upload
}

const beforeUploadBody = async (file: any) => {
  bodyFileList.value = [file]
  const key = await uploadFile(file)
  if (key) bodyObjectKey.value = key
  return false
}

const handleRemoveFace = () => {
  faceFileList.value = []
  faceObjectKey.value = null
}

const handleRemoveBody = () => {
  bodyFileList.value = []
  bodyObjectKey.value = null
}

const handleGenerate = async () => {
  if (!faceObjectKey.value || !bodyObjectKey.value) {
    message.warning('请先上传人脸和目标图片！')
    return
  }

  const payload = {
    task_type: 'face_swap',
    inputs: {
      face_image: faceObjectKey.value,
      target_image: bodyObjectKey.value
    },
    priority: 0,
    is_template: isTemplateApplied.value,
    ...(templateSourcePostId.value != null ? { source_post_id: templateSourcePostId.value } : {})
  }

  const taskId = await submitTask(payload, '快速换脸')
  if (taskId) {
    setSubmittedTaskId(taskId)
  }
}

const resetForm = () => {
  handleRemoveFace()
  handleRemoveBody()
  setSubmittedTaskId(null)
}
</script>

<template>
  <div class="face-swap-container max-w-7xl mx-auto flex flex-col h-[calc(100vh-80px)] w-full py-4 px-2 sm:px-6">
    <div class="flex flex-col lg:flex-row gap-6 flex-grow min-h-0">
      <!-- Left Panel: Input & Settings -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden shrink-0">
        <div class="p-6 flex-grow overflow-y-auto custom-scrollbar">
          <h2 class="text-2xl font-bold mb-2 text-slate-100">快速换脸</h2>
          <p class="text-slate-400 mb-6 text-sm">请提供两张图片，系统将把第一张的人脸替换到第二张的目标场景中。</p>
          
          <!-- Template Mode Notice -->
          <div v-if="isTemplateApplied" class="col-span-full mb-4 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
            <div class="text-indigo-400 mr-3">✨</div>
            <div class="text-slate-300 text-sm">已加载一键换脸模板，底图已为您锁定，请在左侧上传您需要替换的人脸即可开始生成。</div>
          </div>
          
          <div class="flex flex-col gap-6">
            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Face Upload -->
              <div class="upload-section flex flex-col w-full md:w-[50%] min-w-[160px] shrink-0 h-48 md:h-full">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center">
                  <span class="text-slate-500 mr-2">1.</span> 清晰人脸
                </h3>
                <div v-if="facePreview" class="relative group rounded-xl overflow-hidden border border-slate-400/50 bg-slate-500/50 flex items-center justify-center flex-grow w-full">
                  <a-image :src="facePreview" class="max-w-full max-h-full object-contain" :preview="true" />
                  <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                    <a-button danger type="primary" @click="handleRemoveFace" class="pointer-events-auto" size="small">重新上传</a-button>
                  </div>
                </div>
                <a-upload-dragger
                  v-else
                  v-model:fileList="faceFileList"
                  name="file"
                  :multiple="false"
                  accept="image/png, image/jpeg"
                  :before-upload="beforeUploadFace"
                  @remove="handleRemoveFace"
                  class="upload-dragger flex-grow flex items-center justify-center w-full"
                  :show-upload-list="false"
                >
                  <div class="flex flex-col items-center justify-center h-full w-full p-4">
                    <p class="ant-upload-drag-icon text-blue-500 text-3xl mb-2">
                      <inbox-outlined></inbox-outlined>
                    </p>
                    <p class="ant-upload-text font-medium text-slate-300 text-sm">点击/拖拽上传人脸</p>
                    <p class="ant-upload-hint text-slate-500 mt-1 text-xs">JPG/PNG，五官清晰</p>
                  </div>
                </a-upload-dragger>
              </div>

              <!-- Body Upload -->
              <div class="upload-section flex flex-col w-full md:w-[50%] min-w-[160px] shrink-0 h-48 md:h-full">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center">
                  <span class="text-slate-500 mr-2">2.</span> 目标场景
                </h3>
                <div v-if="bodyPreview" class="relative group rounded-xl overflow-hidden border border-slate-400/50 bg-slate-500/50 flex items-center justify-center flex-grow w-full">
                  <a-image :src="bodyPreview" class="max-w-full max-h-full object-contain" :preview="true" />
                  <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                    <a-button danger type="primary" @click="handleRemoveBody" class="pointer-events-auto" size="small">重新上传</a-button>
                  </div>
                </div>
                <a-upload-dragger
                  v-else
                  v-model:fileList="bodyFileList"
                  name="file"
                  :multiple="false"
                  accept="image/png, image/jpeg"
                  :before-upload="beforeUploadBody"
                  @remove="handleRemoveBody"
                  class="upload-dragger flex-grow flex items-center justify-center w-full"
                  :show-upload-list="false"
                >
                  <div class="flex flex-col items-center justify-center h-full w-full p-4">
                    <p class="ant-upload-drag-icon text-blue-500 text-3xl mb-2">
                      <inbox-outlined></inbox-outlined>
                    </p>
                    <p class="ant-upload-text font-medium text-slate-300 text-sm">点击/拖拽上传目标图</p>
                    <p class="ant-upload-hint text-slate-500 mt-1 text-xs">人脸将替换至此图</p>
                  </div>
                </a-upload-dragger>
              </div>
            </div>
          </div>
          
          <div v-if="uploading" class="mt-4">
            <span class="text-xs text-slate-400">正在上传至服务器...</span>
            <a-progress :percent="uploadProgress" status="active" strokeColor="#3b82f6" size="small" />
          </div>
        </div>

        <!-- Action Bar in Left Panel -->
        <div class="p-6 border-t border-slate-400/50 bg-slate-500/40 shrink-0 flex items-center justify-between">
          <div class="flex flex-col">
            <span class="text-slate-400 text-sm font-medium mb-1">预计消耗灵石</span>
            <div class="flex items-baseline text-blue-400 font-bold">
              <span class="text-2xl leading-none mr-1">1</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6 2L2 8l10 14L22 8l-4-6H6z"></path></svg>
            </div>
          </div>
          
          <a-button 
            type="primary" 
            size="large" 
            class="bg-blue-600 hover:bg-blue-500 border-none px-8 font-bold tracking-wider rounded-xl shadow-lg shadow-blue-500/20" 
            :disabled="!faceObjectKey || !bodyObjectKey"
            :loading="isSubmitting"
            @click="handleGenerate"
          >
            <template #icon><swap-outlined /></template>
            {{ isSubmitting ? '提交中...' : '开始换脸' }}
          </a-button>
        </div>
      </div>

      <!-- Right Panel: Result Preview -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden relative">
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
</style>
