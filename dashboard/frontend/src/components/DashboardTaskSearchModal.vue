<script setup lang="ts">
interface TaskSearchResult {
  id: string
  status?: string
  queue_pos?: number
  queue_remaining?: number
  progress?: number
  result_path?: string
  error?: string
}

withDefaults(defineProps<{
  visible?: boolean
  searchResult?: TaskSearchResult | null
  isImage: (path: string) => boolean
  isVideo: (path: string) => boolean
  getTaskImageUrl: (taskId: string) => string
  getTaskVideoUrl: (taskId: string) => string
  getStatusColor: (status: string) => string
}>(), { visible: false, searchResult: null })

const emit = defineEmits<{
  'update:visible': [value: boolean]
  close: []
}>()
</script>

<template>
  <a-modal
    :visible="visible"
    title="任务状态查询"
    :footer="null"
    width="600px"
    @update:visible="emit('update:visible', $event)"
    @cancel="emit('close')"
  >
    <div v-if="searchResult" class="flex flex-col gap-4">
      <div class="flex justify-between items-center p-3 bg-gray-50 rounded">
        <span class="font-bold text-gray-600">任务ID:</span>
        <span class="font-mono text-xs select-all">{{ searchResult.id }}</span>
      </div>

      <div class="flex justify-between items-center p-3 bg-gray-50 rounded">
        <span class="font-bold text-gray-600">状态:</span>
        <a-tag :color="getStatusColor(searchResult.status || '')" class="text-lg px-3 py-1">
          {{ searchResult.status ? searchResult.status.toUpperCase() : 'UNKNOWN' }}
        </a-tag>
      </div>

      <div
        v-if="searchResult.status === 'pending'"
        class="flex flex-col gap-2 p-3 bg-orange-50 rounded border border-orange-100"
      >
        <div class="flex justify-between">
          <span class="text-orange-800">当前队列位置:</span>
          <span class="font-bold text-orange-600">{{ searchResult.queue_pos }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-orange-800">剩余等待数:</span>
          <span class="font-bold text-orange-600">{{ searchResult.queue_remaining }}</span>
        </div>
      </div>

      <div
        v-if="searchResult.status === 'running'"
        class="flex flex-col gap-2 p-3 bg-blue-50 rounded border border-blue-100"
      >
        <div class="flex justify-between mb-1">
          <span class="text-blue-800">生成进度:</span>
          <span class="font-bold text-blue-600">{{ Math.round((searchResult.progress || 0) * 100) }}%</span>
        </div>
        <a-progress :percent="Math.round((searchResult.progress || 0) * 100)" status="active" />
      </div>

      <div v-if="searchResult.status === 'done'" class="flex flex-col gap-2">
        <div v-if="isImage(searchResult.result_path || '')" class="rounded-lg overflow-hidden border shadow-sm">
          <img :src="getTaskImageUrl(searchResult.id)" class="w-full object-contain max-h-[500px] bg-gray-100" />
        </div>
        <div v-else-if="isVideo(searchResult.result_path || '')" class="rounded-lg overflow-hidden border shadow-sm">
          <video controls :src="getTaskVideoUrl(searchResult.id)" class="w-full max-h-[500px] bg-black"></video>
        </div>
        <div v-else class="p-4 bg-green-50 text-green-700 rounded border border-green-200">
          任务已完成，结果文件: {{ searchResult.result_path }}
        </div>
        <a-button
          type="primary"
          block
          :href="isImage(searchResult.result_path || '') ? getTaskImageUrl(searchResult.id) : getTaskVideoUrl(searchResult.id)"
          target="_blank"
          class="mt-2"
        >
          下载/查看原文件
        </a-button>
      </div>

      <div v-if="searchResult.status === 'error'" class="p-4 bg-red-50 text-red-700 rounded border border-red-200">
        <div class="font-bold mb-1">错误信息:</div>
        <div class="font-mono text-sm whitespace-pre-wrap">{{ searchResult.error }}</div>
      </div>
    </div>
  </a-modal>
</template>
