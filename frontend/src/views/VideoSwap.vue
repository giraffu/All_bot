<script setup lang="ts">
import { ref, onUnmounted, watch } from 'vue'
import { UploadOutlined, VideoCameraOutlined, InboxOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'
import { useRoute } from 'vue-router'
import { onMounted } from 'vue'

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isVideoUrl, isImageUrl, downloadResult } = useTaskResult()
const route = useRoute()

const faceFileList = ref<any[]>([])
const bodyFileList = ref<any[]>([])
const faceObjectKey = ref<string | null>(null)
const bodyObjectKey = ref<string | null>(null)
const resolution = ref('512')

const facePreview = ref<string | null>(null)
const bodyPreview = ref<string | null>(null)
const isTemplateApplied = ref(false)

onMounted(() => {
  if (route.query.apply === 'true') {
    const ctxStr = sessionStorage.getItem('galleryApplyContext')
    if (ctxStr) {
      try {
        const ctx = JSON.parse(ctxStr)
        if (ctx.task_type === 'face_video' && ctx.input_file) {
          // prefill target video
          bodyObjectKey.value = ctx.input_file
          bodyPreview.value = ctx.input_file_url || null
          if (ctx.width) resolution.value = ctx.width.toString()
          isTemplateApplied.value = true
        }
      } catch (e) {
        console.error('Failed to parse apply context', e)
      }
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
      images: [faceObjectKey.value],
      videos: [bodyObjectKey.value],
      resolution: Number(resolution.value)
    },
    priority: 0,
    is_template: isTemplateApplied.value
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
  <div class="video-swap-container max-w-4xl mx-auto flex flex-col h-full w-full py-4">
    <div class="flex items-center mb-4 shrink-0">
      <a-button type="link" @click="$router.push('/profile')" class="pl-0 text-blue-500 hover:text-blue-600 flex items-center text-base">
        <span class="mr-1">&larr;</span> 返回工作台
      </a-button>
    </div>

    <div class="bg-slate-800/40 backdrop-blur-md p-6 rounded-2xl shadow-sm border border-slate-700/50 flex-grow mb-4 overflow-y-auto">
      <h2 class="text-2xl font-bold mb-4 text-slate-100">视频换脸设置</h2>
      
      <!-- Template Mode Notice -->
      <div v-if="isTemplateApplied" class="mb-6 bg-indigo-500/20 border border-indigo-500/30 rounded-xl p-4 flex items-center">
        <div class="text-indigo-400 mr-3">✨</div>
        <div class="text-slate-300 text-sm">已加载一键视频换脸模板，目标视频已锁定，请在上方上传您需要替换的人脸即可开始生成。</div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <!-- Face Upload -->
        <div class="upload-section flex flex-col h-full">
          <h3 class="text-lg font-bold mb-3 text-slate-200 flex items-center">
            <span class="text-slate-500 mr-2">1.</span> 提供清晰人脸
          </h3>
          <div v-if="facePreview" class="relative group rounded-xl overflow-hidden border border-slate-600/50 bg-slate-900/50 flex items-center justify-center flex-grow h-48">
            <a-image :src="facePreview" class="max-w-full max-h-48 object-contain" :preview="true" />
            <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
              <a-button danger type="primary" @click="handleRemoveFace" class="pointer-events-auto">重新上传</a-button>
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
            class="upload-dragger flex-grow h-48 flex items-center justify-center"
            :show-upload-list="false"
          >
            <div class="flex flex-col items-center justify-center h-full w-full">
              <p class="ant-upload-drag-icon text-blue-500 text-3xl mb-2">
                <inbox-outlined></inbox-outlined>
              </p>
              <p class="ant-upload-text font-medium text-slate-300 text-sm">点击或拖拽上传人脸图片</p>
              <p class="ant-upload-hint text-slate-500 mt-1 text-xs">支持 JPG/PNG，五官清晰无遮挡</p>
            </div>
          </a-upload-dragger>
        </div>

        <!-- Video Upload -->
        <div class="upload-section flex flex-col h-full">
          <h3 class="text-lg font-bold mb-3 text-slate-200 flex items-center">
            <span class="text-slate-500 mr-2">2.</span> 提供目标视频
          </h3>
          <div v-if="bodyPreview" class="relative group rounded-xl overflow-hidden border border-slate-600/50 bg-slate-900/50 flex items-center justify-center flex-grow h-48">
            <video :src="bodyPreview" class="max-w-full max-h-48 bg-black" controls></video>
            <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
              <a-button danger type="primary" @click="handleRemoveBody" class="pointer-events-auto">重新上传</a-button>
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
            class="upload-dragger bg-slate-800/40 backdrop-blur-md border-dashed border-2 border-blue-200 hover:border-blue-400 transition-colors flex-grow h-48 flex items-center justify-center"
            :show-upload-list="false"
          >
            <div class="flex flex-col items-center justify-center h-full w-full">
              <p class="ant-upload-drag-icon text-blue-500 text-3xl mb-2">
                <video-camera-outlined></video-camera-outlined>
              </p>
              <p class="ant-upload-text font-medium text-slate-300 text-sm">点击或拖拽上传目标视频</p>
              <p class="ant-upload-hint text-slate-500 mt-1 text-xs">支持 MP4/MOV，最大 50MB</p>
            </div>
          </a-upload-dragger>
        </div>
      </div>
      
      <!-- Video Settings -->
      <div class="settings-section border-t border-slate-700/50 pt-5 w-full max-w-2xl mx-auto">
        <h3 class="text-lg font-bold mb-4 text-slate-200">输出设置</h3>
        <div class="grid grid-cols-1 gap-6">
          <div>
            <label class="block text-sm font-medium text-slate-300 mb-2">分辨率</label>
            <a-radio-group v-model:value="resolution" button-style="solid" class="w-full flex">
              <a-radio-button value="512" class="flex-1 text-center py-1 h-auto text-sm">512p (基础)</a-radio-button>
              <a-radio-button value="720" class="flex-1 text-center py-1 h-auto text-sm">720p (高清)</a-radio-button>
              <a-radio-button value="1024" class="flex-1 text-center py-1 h-auto text-sm" disabled>1024p</a-radio-button>
            </a-radio-group>
          </div>
        </div>
      </div>

      <!-- Result Section -->
      <div v-if="currentTask" class="mt-8 bg-slate-900/50 p-5 rounded-2xl border border-slate-700/50">
        <h3 class="text-xl font-bold mb-4 text-slate-200 flex items-center justify-center">
          <span class="text-blue-500 mr-2">✨</span> 生成结果
        </h3>
        
        <div v-if="currentTask.status === 'pending' || currentTask.status === 'running'" class="flex flex-col items-center justify-center py-8">
          <a-spin size="large" />
          <p class="mt-4 text-slate-400 font-medium">正在生成中... {{ currentTask.progress }}%</p>
          <p v-if="currentTask.queuePos" class="text-sm text-slate-500 mt-1">前面还有 {{ currentTask.queuePos }} 人排队</p>
          <a-progress :percent="currentTask.progress" status="active" strokeColor="#3b82f6" class="w-full max-w-md mt-4" />
        </div>
        
        <div v-else-if="currentTask.status === 'success' && currentTask.resultUrl" class="flex flex-col items-center">
          <a-image v-if="isImageUrl(currentTask.resultUrl)" :src="currentTask.resultUrl" class="max-w-full max-h-96 rounded-xl shadow-sm object-contain" :preview="true" />
          <video v-else :src="currentTask.resultUrl" controls class="max-w-full max-h-96 rounded-xl shadow-sm bg-black"></video>
          
          <div class="mt-6 flex gap-4">
            <a-button type="primary" size="large" class="bg-blue-600 rounded-xl" @click="downloadResult(currentTask.resultUrl, currentTask.title)">
              <template #icon><download-outlined /></template> 下载结果
            </a-button>
            <a-button size="large" class="rounded-xl" @click="resetForm">
              继续生成
            </a-button>
          </div>
        </div>
        
        <div v-else-if="currentTask.status === 'failed'" class="flex flex-col items-center py-8">
          <close-circle-outlined class="text-5xl text-red-500 mb-4" />
          <p class="text-red-600 font-medium text-lg">生成失败</p>
          <p class="text-slate-400 mt-2">{{ currentTask.error || '未知错误' }}</p>
          <a-button class="mt-6 rounded-xl" @click="resetForm">重试</a-button>
        </div>
      </div>
    </div>

    <!-- Action Bar -->
    <div class="action-bar bg-slate-800/40 backdrop-blur-md p-6 rounded-2xl shadow-sm border border-slate-700/50 flex justify-between items-center shrink-0">
      <div class="cost-info flex flex-col">
        <span class="text-slate-400 text-sm font-medium">预计消耗灵石</span>
        <div class="flex items-end mt-1">
          <span class="font-bold text-3xl text-blue-600 leading-none">20</span>
          <span class="text-lg text-blue-400 ml-1 mb-0.5">💎</span>
        </div>
      </div>
      
      <a-button 
        type="primary" 
        size="large" 
        class="bg-blue-600 hover:bg-blue-700 w-48 h-14 text-lg font-bold tracking-wider rounded-xl shadow-md transition-all hover:shadow-lg border-none flex items-center justify-center text-white" 
        :disabled="!faceObjectKey || !bodyObjectKey"
        :loading="isSubmitting"
        @click="handleGenerate"
      >
        <template #icon><video-camera-outlined /></template>
        {{ isSubmitting ? '提交中...' : '开始换脸' }}
      </a-button>
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
