<script setup>
import { CloseOutlined, LinkOutlined } from '@ant-design/icons-vue'

import MediaItem from './MediaItem.vue'
import { formatDate } from '../utils/helpers'

const props = defineProps({
  show: {
    type: Boolean,
    required: true,
  },
  user: {
    type: Object,
    default: null,
  },
  items: {
    type: Array,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  page: {
    type: Number,
    default: 1,
  },
  pageSize: {
    type: Number,
    default: 12,
  },
  total: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits(['close', 'pageChange'])

const buildMediaFileName = (item) => {
  if (item.media_type === 'video') {
    return 'favorite.mp4'
  }
  return 'favorite.jpg'
}

const openUrl = (url) => {
  if (url) {
    window.open(url, '_blank', 'noopener')
  }
}
</script>

<template>
  <a-modal
    :open="show"
    width="1180px"
    :footer="null"
    :closable="false"
    centered
    :body-style="{ padding: 0 }"
    @update:open="$emit('close')"
  >
    <div class="flex flex-col h-full max-h-[88vh]">
      <div class="p-6 border-b flex justify-between items-center bg-white sticky top-0 z-10 rounded-t-lg">
        <div>
          <h3 class="text-xl font-bold text-gray-800 m-0">用户收藏</h3>
          <p class="text-sm text-gray-500 m-0">
            {{ user?.full_name || '未知用户' }} ({{ user?.id }}) · 与 Web 端收藏页同源
          </p>
        </div>
        <a-button type="text" @click="emit('close')" class="flex items-center justify-center">
          <template #icon><close-outlined /></template>
        </a-button>
      </div>

      <div class="p-6 overflow-y-auto flex-grow bg-gray-50">
        <a-alert
          class="mb-4"
          type="info"
          show-icon
          message="当前列表直接复用 Web 端 /users/my-favorites 的同一后端 payload，可用于对照排查收藏可见性问题。"
        />

        <div v-if="loading" class="text-center py-24">
          <a-spin size="large" tip="正在获取收藏数据..." />
        </div>

        <div v-else-if="items.length === 0" class="text-center py-24">
          <a-empty description="该用户暂无收藏数据" />
        </div>

        <div v-else class="space-y-4">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <a-card
              v-for="item in items"
              :key="`${item.task_id}-${item.id}`"
              size="small"
              class="shadow-sm rounded-xl"
            >
              <template #title>
                <div class="flex justify-between items-center gap-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <a-tag :color="item.media_type === 'video' ? 'purple' : 'blue'">
                      {{ item.media_type }}
                    </a-tag>
                    <a-tag color="geekblue">
                      {{ item.task_type || 'unknown' }}
                    </a-tag>
                    <a-tag v-if="item.id === 0 || item.is_active === false" color="red">
                      帖子不存在或已下架
                    </a-tag>
                    <a-tag v-else color="green">帖子有效</a-tag>
                  </div>
                  <span class="text-[10px] text-gray-400 font-normal">
                    {{ formatDate(item.created_at) }}
                  </span>
                </div>
              </template>

              <div class="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-4">
                <div class="space-y-3">
                  <MediaItem
                    v-if="item.media_url"
                    :file="buildMediaFileName(item)"
                    :url="item.media_url"
                    label="原始媒体"
                    size="w-full h-44"
                  />
                  <div
                    v-else
                    class="w-full h-44 flex items-center justify-center bg-gray-100 rounded-lg text-xs text-gray-400 border border-dashed border-gray-300"
                  >
                    无 media_url
                  </div>

                  <MediaItem
                    v-if="item.thumbnail_url"
                    file="thumbnail.jpg"
                    :url="item.thumbnail_url"
                    label="缩略图"
                    size="w-full h-28"
                  />
                </div>

                <div class="space-y-3">
                  <div class="grid grid-cols-2 gap-3 text-xs">
                    <div class="bg-gray-50 border rounded p-3">
                      <div class="text-gray-500 mb-1">task_id</div>
                      <div class="font-mono break-all text-gray-800">{{ item.task_id || '-' }}</div>
                    </div>
                    <div class="bg-gray-50 border rounded p-3">
                      <div class="text-gray-500 mb-1">post_id</div>
                      <div class="font-mono text-gray-800">{{ item.id }}</div>
                    </div>
                    <div class="bg-gray-50 border rounded p-3">
                      <div class="text-gray-500 mb-1">尺寸</div>
                      <div class="text-gray-800">{{ item.width || '-' }} x {{ item.height || '-' }}</div>
                    </div>
                    <div class="bg-gray-50 border rounded p-3">
                      <div class="text-gray-500 mb-1">时长</div>
                      <div class="text-gray-800">{{ item.duration || '-' }}</div>
                    </div>
                  </div>

                  <div class="flex flex-wrap gap-2">
                    <a-button
                      v-if="item.media_url"
                      size="small"
                      @click="openUrl(item.media_url)"
                    >
                      <template #icon><link-outlined /></template>
                      打开原始媒体
                    </a-button>
                    <a-button
                      v-if="item.thumbnail_url"
                      size="small"
                      @click="openUrl(item.thumbnail_url)"
                    >
                      <template #icon><link-outlined /></template>
                      打开缩略图
                    </a-button>
                  </div>

                  <div class="bg-gray-50 border rounded p-3 text-xs">
                    <div class="text-gray-500 mb-1">标签</div>
                    <div v-if="item.tags?.length" class="flex flex-wrap gap-1">
                      <a-tag v-for="tag in item.tags" :key="tag" color="blue">{{ tag }}</a-tag>
                    </div>
                    <div v-else class="text-gray-400">无特定标签</div>
                  </div>

                  <div class="bg-gray-50 border rounded p-3 text-xs">
                    <div class="text-gray-500 mb-1">提示词</div>
                    <div class="whitespace-pre-wrap break-words text-gray-700">
                      {{ item.prompt || '无提示词' }}
                    </div>
                  </div>
                </div>
              </div>
            </a-card>
          </div>

          <div class="flex justify-end pt-2">
            <a-pagination
              :current="page"
              :page-size="pageSize"
              :total="total"
              :show-size-changer="false"
              :show-total="(count) => `共 ${count} 条收藏`"
              @change="emit('pageChange', $event)"
            />
          </div>
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
