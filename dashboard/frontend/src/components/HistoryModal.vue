<script setup>
import { getFileUrl, formatDate } from '../utils/helpers'
import MediaItem from './MediaItem.vue'
import { CloseOutlined } from '@ant-design/icons-vue'

defineProps({
  show: {
    type: Boolean,
    required: true
  },
  user: {
    type: Object,
    default: null
  },
  history: {
    type: Array,
    required: true
  },
  loading: {
    type: Boolean,
    default: false
  }
})

defineEmits(['close'])
</script>

<template>
  <a-modal
    :open="show"
    @update:open="$emit('close')"
    :title="null"
    :footer="null"
    :closable="false"
    width="1000px"
    centered
    :body-style="{ padding: 0 }"
  >
    <div class="flex flex-col h-full max-h-[85vh]">
      <!-- Modal Header -->
      <div class="p-6 border-b flex justify-between items-center bg-white sticky top-0 z-10 rounded-t-lg">
        <div>
          <h3 class="text-xl font-bold text-gray-800 m-0">用户历史记录</h3>
          <p class="text-sm text-gray-500 m-0">{{ user?.full_name }} ({{ user?.id }})</p>
        </div>
        <a-button type="text" @click="$emit('close')" class="flex items-center justify-center">
          <template #icon><close-outlined /></template>
        </a-button>
      </div>

      <!-- Modal Content -->
      <div class="p-6 overflow-y-auto flex-grow bg-gray-50">
        <div v-if="loading" class="text-center py-24">
          <a-spin size="large" tip="正在获取历史数据..." />
        </div>
        <div v-else-if="history.length === 0" class="text-center py-24">
          <a-empty description="该用户暂无生成记录" />
        </div>
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <a-card v-for="item in history" :key="item.id" size="small" class="shadow-sm rounded-xl">
            <template #title>
              <div class="flex justify-between items-center">
                <a-tag :color="item.type === 'image' ? 'blue' : 'orange'">
                  {{ item.type }}
                </a-tag>
                <span class="text-[10px] text-gray-400 font-normal">
                  {{ formatDate(item.created_at) }}
                </span>
              </div>
            </template>
            
            <div class="grid grid-cols-2 gap-4">
              <!-- Input Content -->
              <div class="space-y-2">
                <p class="text-[10px] text-gray-500 uppercase font-bold m-0">输入内容</p>
                <div class="flex flex-wrap gap-2">
                  <template v-if="item.input_file">
                    <MediaItem 
                      v-for="file in item.input_file.split('|')" 
                      :key="file"
                      :file="file"
                      :url="getFileUrl(item.user_id, 'input_images', file)"
                    />
                  </template>
                  <div v-else class="w-32 h-32 flex items-center justify-center bg-gray-100 rounded-lg text-[10px] text-gray-400 border border-dashed border-gray-300">无输入</div>
                </div>
              </div>

              <!-- Output Content -->
              <div class="space-y-2 text-right">
                <p class="text-[10px] text-gray-500 uppercase font-bold m-0">输出内容</p>
                <div class="flex justify-end">
                  <template v-if="item.output_file">
                    <MediaItem 
                      :file="item.output_file"
                      :url="getFileUrl(item.user_id, 'output_images', item.output_file)"
                    />
                  </template>
                  <div v-else class="w-32 h-32 flex items-center justify-center bg-gray-100 rounded-lg text-[10px] text-gray-400 border border-dashed border-gray-300">未完成</div>
                </div>
              </div>
            </div>

            <div class="mt-4 pt-3 border-t border-gray-100">
              <p class="text-[10px] text-gray-500 font-bold uppercase m-0 mb-1">提示词</p>
              <div class="text-xs text-gray-600 bg-gray-50 p-2 rounded border border-gray-100 italic">
                {{ item.prompt || '无提示词' }}
              </div>
            </div>
          </a-card>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
:deep(.ant-modal-content) {
  border-radius: 12px;
  overflow: hidden;
}
</style>
