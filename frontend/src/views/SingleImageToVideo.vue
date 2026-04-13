<script setup lang="ts">
import { ref, onUnmounted, computed, watch } from 'vue'
import { UploadOutlined, InboxOutlined, VideoCameraOutlined, DownloadOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { useUpload } from '@/composables/useUpload'
import { useTaskStream } from '@/composables/useTaskStream'
import { useTaskResult } from '@/composables/useTaskResult'

const route = useRoute()
const router = useRouter()

const taskType = computed(() => (route.query.type as string) || 'image2video')
const taskTitle = computed(() => (route.query.title as string) || '动图生成')
const taskCost = computed(() => Number(route.query.cost) || 6)
const isCustomVideo = computed(() => taskType.value === 'custom_video')

const { uploading, progress: uploadProgress, uploadFile } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isVideoUrl, isImageUrl, downloadResult } = useTaskResult()

const fileList = ref<any[]>([])
const objectKey = ref<string | null>(null)
const resolution = ref('512')
const duration = ref('5')
const prompt = ref('')

const filePreview = ref<string | null>(null)

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

  const payload = {
    task_type: taskType.value,
    inputs: {
      images: [objectKey.value],
      resolution: Number(resolution.value),
      duration: Number(duration.value),
      ...(isCustomVideo.value && prompt.value ? { prompt: prompt.value } : {})
    },
    priority: 0
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
  <div class="single-image-video-container max-w-4xl mx-auto flex flex-col h-full w-full">
    <div class="flex items-center mb-6 shrink-0">
      <a-button type="link" @click="router.push('/profile')" class="pl-0 text-blue-500 hover:text-blue-600 flex items-center text-base">
        <span class="mr-1">&larr;</span> 返回工作台
      </a-button>
    </div>

    <div class="bg-white p-8 rounded-2xl shadow-sm border border-gray-100 flex-grow mb-6 overflow-y-auto">
      <h2 class="text-3xl font-bold mb-6 text-gray-900">{{ taskTitle }}设置</h2>
      
      <div class="grid grid-cols-1 md:grid-cols-2 gap-10 mb-8">
        <!-- Image Upload -->
        <div class="upload-section flex flex-col">
          <h3 class="text-xl font-bold mb-4 text-gray-800 flex items-center">
            <span class="text-gray-400 mr-2">1.</span> 提供基础图片
          </h3>
          <div v-if="filePreview" class="relative group rounded-xl overflow-hidden border border-gray-200 bg-gray-50 flex items-center justify-center flex-grow h-64">
            <a-image :src="filePreview" class="max-w-full max-h-64 object-contain" :preview="true" />
            <div class="absolute inset-0 bg-black bg-opacity-50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
              <a-button danger type="primary" @click="handleRemove" class="pointer-events-auto">重新上传</a-button>
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
            class="upload-dragger flex-grow h-64 flex items-center justify-center"
            :show-upload-list="false"
          >
            <div class="flex flex-col items-center justify-center h-full w-full">
              <p class="ant-upload-drag-icon text-blue-500 text-4xl mb-4"><inbox-outlined></inbox-outlined></p>
              <p class="ant-upload-text font-medium text-gray-700">点击或拖拽上传图片</p>
              <p class="ant-upload-hint text-gray-400 mt-2">支持 JPG/PNG，作为视频生成的起点</p>
            </div>
          </a-upload-dragger>
          
          <div v-if="uploading" class="mt-4">
            <span class="text-sm text-gray-500">正在上传...</span>
            <a-progress :percent="uploadProgress" status="active" strokeColor="#3b82f6" />
          </div>
        </div>

        <!-- Prompt Input (Optional, mainly for custom_video) -->
        <div class="prompt-section flex flex-col h-full" v-if="isCustomVideo">
          <h3 class="text-xl font-bold mb-4 text-gray-800 flex items-center">
            <span class="text-gray-400 mr-2">2.</span> 输入动作描述 (选填)
          </h3>
          <a-textarea 
            v-model:value="prompt" 
            placeholder="例如：人物微笑，背景有风吹过..." 
            class="rounded-xl border-gray-200 focus:border-blue-500 focus:ring-blue-500 text-base p-4 flex-grow resize-none"
          />
        </div>
        <div class="prompt-section flex flex-col justify-center text-center p-6 bg-gray-50 rounded-xl h-full" v-else>
          <component :is="InboxOutlined" class="text-4xl text-gray-300 mb-2" />
          <h3 class="text-lg font-medium text-gray-600">AI 智能动作预设</h3>
          <p class="text-sm text-gray-400 mt-2">系统将自动为当前功能生成专属动作视频，无需手动输入提示词。</p>
        </div>
      </div>
      
      <!-- Video Settings -->
      <div class="settings-section border-t border-gray-100 pt-8">
        <h3 class="text-xl font-bold mb-6 text-gray-800">输出设置</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-3">分辨率</label>
            <a-radio-group v-model:value="resolution" button-style="solid" class="w-full flex">
              <a-radio-button value="512" class="flex-1 text-center py-2 h-auto">512p (基础)</a-radio-button>
              <a-radio-button value="720" class="flex-1 text-center py-2 h-auto">720p (高清)</a-radio-button>
              <a-radio-button value="1024" class="flex-1 text-center py-2 h-auto" disabled>1024p (超清)</a-radio-button>
            </a-radio-group>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-3">生成时长</label>
            <a-radio-group v-model:value="duration" button-style="solid" class="w-full flex">
              <a-radio-button value="5" class="flex-1 text-center py-2 h-auto">5 秒</a-radio-button>
              <a-radio-button value="8" class="flex-1 text-center py-2 h-auto">8 秒</a-radio-button>
              <a-radio-button value="10" class="flex-1 text-center py-2 h-auto" disabled>10 秒</a-radio-button>
            </a-radio-group>
          </div>
        </div>
      </div>

      <!-- Result Section -->
      <div v-if="currentTask" class="mt-10 bg-gray-50 p-6 rounded-2xl border border-gray-100">
        <h3 class="text-xl font-bold mb-4 text-gray-800 flex items-center justify-center">
          <span class="text-blue-500 mr-2">✨</span> 生成结果
        </h3>
        
        <div v-if="currentTask.status === 'pending' || currentTask.status === 'running'" class="flex flex-col items-center justify-center py-8">
          <a-spin size="large" />
          <p class="mt-4 text-gray-600 font-medium">正在生成中... {{ currentTask.progress }}%</p>
          <p v-if="currentTask.queuePos" class="text-sm text-gray-400 mt-1">前面还有 {{ currentTask.queuePos }} 人排队</p>
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
          <p class="text-gray-500 mt-2">{{ currentTask.error || '未知错误' }}</p>
          <a-button class="mt-6 rounded-xl" @click="resetForm">重试</a-button>
        </div>
      </div>
    </div>

    <!-- Action Bar -->
    <div class="action-bar bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex justify-between items-center shrink-0">
      <div class="cost-info flex flex-col">
        <span class="text-gray-500 text-sm font-medium">预计消耗灵石</span>
        <div class="flex items-end mt-1">
          <span class="font-bold text-3xl text-blue-600 leading-none">{{ taskCost }}</span>
          <span class="text-lg text-blue-400 ml-1 mb-0.5">💎</span>
        </div>
      </div>
      
      <a-button 
        type="primary" 
        size="large" 
        class="bg-blue-600 hover:bg-blue-700 w-48 h-14 text-lg font-bold tracking-wider rounded-xl shadow-md transition-all hover:shadow-lg border-none flex items-center justify-center" 
        :disabled="!objectKey"
        :loading="isSubmitting"
        @click="handleGenerate"
      >
        <template #icon><video-camera-outlined /></template>
        {{ isSubmitting ? '提交中...' : '生成视频' }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.upload-dragger {
  background: #f8fafc;
  border-radius: 12px;
}
</style>
