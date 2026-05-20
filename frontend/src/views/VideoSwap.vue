<script setup lang="ts">
import { ref, onUnmounted, watch, computed } from 'vue'
import { UploadOutlined, VideoCameraOutlined, InboxOutlined, DownloadOutlined, CloseCircleOutlined, HistoryOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useRoute } from 'vue-router'
import { onMounted } from 'vue'

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isVideoUrl, isImageUrl, downloadResult } = useTaskResult()
const { loadApplyContext } = useGalleryApplyContext()
const route = useRoute()

const faceFileList = ref<any[]>([])
const bodyFileList = ref<any[]>([])
const faceObjectKey = ref<string | null>(null)
const bodyObjectKey = ref<string | null>(null)
const resolution = ref('720')

const taskCost = computed(() => {
  const res = resolution.value;
  if (res === '720') return 18;
  if (res === '1024') return 36;
  return 18; // default fallback for 720p
})

const facePreview = ref<string | null>(null)
const bodyPreview = ref<string | null>(null)
const isTemplateApplied = ref(false)
const templateSourcePostId = ref<number | null>(null)

onMounted(() => {
  if (route.query.apply === 'true') {
    const ctx = loadApplyContext()
    if (ctx && ctx.task_type === 'face_video' && ctx.input_file) {
      // prefill target video
      bodyObjectKey.value = ctx.input_file
      bodyPreview.value = ctx.input_file_url || null
      if (ctx.width) resolution.value = ctx.width.toString()
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

const beforeUploadFace = async (file: any) => {
  faceFileList.value = [file]
  const key = await uploadFile(file)
  if (key) faceObjectKey.value = key
  return false
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
    message.warning('请确保已上传人脸图片和目标视频！')
    return
  }

  const payload = {
    task_type: 'face_video',
    inputs: {
      face_image: faceObjectKey.value,
      target_video: bodyObjectKey.value,
      resolution: Number(resolution.value)
    },
    priority: 0,
    is_template: isTemplateApplied.value,
    ...(templateSourcePostId.value != null ? { source_post_id: templateSourcePostId.value } : {})
  }

  const taskId = await submitTask(payload, '视频换脸')
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
  <div class="video-swap-container max-w-7xl mx-auto flex flex-col h-[calc(100vh-80px)] w-full py-4 px-2 sm:px-6">
    <div class="flex flex-col lg:flex-row gap-6 flex-grow min-h-0">
      <!-- Left Panel: Input & Settings -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden shrink-0">
        <!-- Scrollable Content -->
        <div class="p-6 flex-grow overflow-y-auto custom-scrollbar">
          <h2 class="text-2xl font-bold mb-5 text-slate-100">视频换脸设置</h2>
          
          <div v-if="isTemplateApplied" class="mb-6 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
            <div class="text-indigo-400 mr-3">✨</div>
            <div class="text-slate-300 text-sm">已加载一键视频换脸模板，目标视频已锁定，请在上方上传您需要替换的人脸即可开始生成。</div>
          </div>

          <div class="flex flex-col gap-6 mb-6">
            <!-- Row for Upload -->
            <div class="flex flex-col md:flex-row gap-4 md:h-64 w-full">
              <!-- Face Upload -->
              <div class="upload-section flex flex-col w-full md:w-[40%] min-w-[160px] shrink-0 h-48 md:h-full">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center shrink-0">
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
                    <p class="ant-upload-text font-medium text-slate-300 text-sm">点击/拖拽</p>
                    <p class="ant-upload-hint text-slate-500 mt-1 text-xs">JPG/PNG</p>
                  </div>
                </a-upload-dragger>
              </div>

              <!-- Video Upload -->
              <div class="upload-section flex flex-col flex-grow min-w-0 h-48 md:h-full">
                <h3 class="text-sm font-bold mb-2 text-slate-200 flex items-center shrink-0">
                  <span class="text-slate-500 mr-2">2.</span> 目标视频
                </h3>
                <div v-if="bodyPreview" class="relative group rounded-xl overflow-hidden border border-slate-400/50 bg-slate-500/50 flex items-center justify-center flex-grow w-full">
                  <video :src="bodyPreview" class="max-w-full max-h-full bg-black object-contain" controls></video>
                  <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                    <a-button danger type="primary" @click="handleRemoveBody" class="pointer-events-auto" size="small">重新上传</a-button>
                  </div>
                </div>
                <a-upload-dragger
                  v-else
                  v-model:fileList="bodyFileList"
                  name="video"
                  :multiple="false"
                  accept="video/mp4, video/quicktime"
                  :before-upload="beforeUploadBody"
                  @remove="handleRemoveBody"
                  class="upload-dragger bg-slate-500/50 backdrop-blur-md border-dashed border-2 border-blue-200 hover:border-blue-400 transition-colors flex-grow flex items-center justify-center w-full"
                  :show-upload-list="false"
                >
                  <div class="flex flex-col items-center justify-center h-full w-full p-4">
                    <p class="ant-upload-drag-icon text-blue-500 text-3xl mb-2">
                      <video-camera-outlined></video-camera-outlined>
                    </p>
                    <p class="ant-upload-text font-medium text-slate-300 text-sm">上传目标视频</p>
                    <p class="ant-upload-hint text-slate-500 mt-1 text-xs">支持 MP4/MOV</p>
                  </div>
                </a-upload-dragger>
              </div>
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
        </div>

        <!-- Fixed Bottom Bar -->
        <div class="p-6 border-t border-slate-400/50 bg-slate-500/40 shrink-0 flex items-center justify-between">
          <div class="flex flex-col">
            <span class="text-slate-400 text-sm font-medium mb-1">预计消耗灵石</span>
            <div class="flex items-baseline text-blue-400 font-bold">
              <span class="text-2xl leading-none mr-1">{{ taskCost }}</span>
              <span class="text-lg ml-1 mb-0.5">💎</span>
            </div>
          </div>
          
          <a-button 
            type="primary" 
            size="large" 
            :loading="isSubmitting" 
            :disabled="!faceObjectKey || !bodyObjectKey" 
            @click="handleGenerate"
            class="bg-blue-600 hover:bg-blue-500 border-none px-8 font-bold tracking-wider rounded-xl shadow-lg shadow-blue-500/20"
          >
            <template #icon><video-camera-outlined /></template>
            {{ isSubmitting ? '提交中...' : '开始换脸' }}
          </a-button>
        </div>
      </div>

      <!-- Right Panel: Result Preview -->
      <div class="w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden relative">
        <h3 class="text-lg font-bold p-4 border-b border-slate-400/50 text-slate-200 bg-slate-500/50 flex items-center shrink-0">
          <video-camera-outlined class="mr-2 text-blue-400" /> 结果预览区
        </h3>
        
        <div class="flex-grow flex items-center justify-center p-6 min-h-0 bg-black/20">
          <!-- Default State -->
          <div v-if="!currentTask" class="text-center text-slate-500 flex flex-col items-center">
            <video-camera-outlined class="text-5xl mb-4 opacity-50" />
            <p>请在左侧配置参数并点击生成，结果将在此处显示</p>
          </div>
          
          <!-- Loading State -->
          <div v-else-if="currentTask.status === 'pending' || currentTask.status === 'running'" class="flex flex-col items-center justify-center w-full h-full">
            <div class="relative w-32 h-32 flex items-center justify-center mb-6">
              <div class="absolute inset-0 border-4 border-slate-400 rounded-full"></div>
              <div class="absolute inset-0 border-4 border-blue-500 rounded-full border-t-transparent animate-spin"></div>
              <div class="text-blue-400 font-bold text-xl">{{ currentTask.progress }}%</div>
            </div>
            <p class="text-slate-300 font-medium text-lg animate-pulse">AI 正在为您生成大片...</p>
            <p v-if="currentTask.queuePos" class="text-sm text-slate-500 mt-2 bg-slate-500 px-3 py-1 rounded-full">
              队列位置: <span class="text-blue-400 font-bold">{{ currentTask.queuePos }}</span>
            </p>
            <div class="w-64 mt-6">
              <a-progress :percent="currentTask.progress" status="active" strokeColor="#3b82f6" :showInfo="false" size="small" />
            </div>
          </div>
          
          <!-- Success State -->
          <div v-else-if="currentTask.status === 'success' && currentTask.resultUrl" class="w-full h-full flex flex-col items-center justify-center">
            <div class="relative w-full h-full flex items-center justify-center bg-black/40 rounded-xl overflow-hidden border border-slate-400/50 shadow-2xl">
              <a-image v-if="isImageUrl(currentTask.resultUrl)" :src="currentTask.resultUrl" class="max-w-full max-h-full object-contain" :preview="true" />
              <video v-else :src="currentTask.resultUrl" controls class="max-w-full max-h-full object-contain"></video>
            </div>
            
            <!-- Actions Bar -->
            <div class="flex gap-3 mt-4 w-full justify-center">
              <a-button type="primary" ghost @click="downloadResult(currentTask.resultUrl, currentTask.title)" class="flex items-center px-6 rounded-lg">
                <download-outlined class="mr-1" /> 保存到本地
              </a-button>
              <a-button type="default" @click="$router.push('/history')" class="flex items-center px-6 rounded-lg border-slate-400 text-slate-300 hover:text-white hover:border-slate-400 bg-slate-500/50">
                <history-outlined class="mr-1" /> 查看历史
              </a-button>
            </div>
          </div>
          
          <!-- Error State -->
          <div v-else-if="currentTask.status === 'failed'" class="text-center text-red-400 flex flex-col items-center bg-red-950/20 p-8 rounded-2xl border border-red-900/50">
            <close-circle-outlined class="text-5xl mb-4" />
            <h4 class="text-lg font-bold mb-2">生成失败</h4>
            <p class="text-sm opacity-80">{{ currentTask.error || '未知错误，请重试' }}</p>
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
