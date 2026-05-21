<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    currentTask: any
    isImageUrl?: ((url: string) => boolean) | null
    emptyTitle?: string
    emptyDescription?: string
    resultTitle?: string
    pendingLabel?: string
    failedTitle?: string
    retryText?: string
    continueText?: string
    bodyClass?: string
    contentClass?: string
  }>(),
  {
    isImageUrl: null,
    emptyTitle: '结果预览区',
    emptyDescription: '请在左侧配置参数并点击生成，结果将在此处显示',
    resultTitle: '生成结果',
    pendingLabel: '正在生成中...',
    failedTitle: '生成失败',
    retryText: '重试',
    continueText: '继续生成',
    bodyClass:
      'p-6 flex-grow flex flex-col items-center justify-center h-full overflow-y-auto custom-scrollbar',
    contentClass: 'w-full h-full flex flex-col items-center justify-center',
  },
)

const emit = defineEmits<{
  download: [resultUrl: string, title?: string]
  reset: []
}>()
</script>

<template>
  <div :class="bodyClass">
    <slot name="header">
      <h3
        class="text-xl font-bold mb-6 text-slate-200 w-full border-b border-slate-400/50 pb-4 flex items-center"
      >
        <span class="text-blue-500 mr-2">✨</span> {{ resultTitle }}
      </h3>
    </slot>

    <div v-if="!currentTask" :class="contentClass">
      <slot name="empty">
        <div
          class="flex flex-col items-center justify-center text-slate-500 w-full h-full opacity-60"
        >
          <slot name="empty-icon" />
          <p class="text-lg font-medium">{{ emptyTitle }}</p>
          <p class="text-sm mt-2">{{ emptyDescription }}</p>
        </div>
      </slot>
    </div>

    <div v-else :class="contentClass">
      <div
        v-if="currentTask.status === 'pending' || currentTask.status === 'running'"
        class="flex flex-col items-center justify-center py-8 w-full flex-grow"
      >
        <slot name="pending" :task="currentTask">
          <a-spin size="large" />
          <p class="mt-4 text-slate-400 font-medium">
            {{ pendingLabel }} {{ currentTask.progress }}%
          </p>
          <p
            v-if="currentTask.queuePos"
            class="text-sm text-slate-500 mt-1"
          >
            前面还有 {{ currentTask.queuePos }} 人排队
          </p>
          <a-progress
            :percent="currentTask.progress"
            status="active"
            strokeColor="#3b82f6"
            class="w-full max-w-md mt-4"
          />
        </slot>
      </div>

      <div
        v-else-if="currentTask.status === 'success' && currentTask.resultUrl"
        class="flex flex-col items-center w-full flex-grow justify-center"
      >
        <slot name="success-media" :task="currentTask">
          <a-image
            v-if="isImageUrl && isImageUrl(currentTask.resultUrl)"
            :src="currentTask.resultUrl"
            class="max-w-full max-h-[50vh] rounded-xl shadow-sm object-contain"
            :preview="true"
          />
          <video
            v-else
            :src="currentTask.resultUrl"
            controls
            class="max-w-full max-h-[50vh] rounded-xl shadow-sm bg-black"
          />
        </slot>

        <div class="mt-8 flex gap-4">
          <slot name="success-actions" :task="currentTask">
            <a-button
              type="primary"
              size="large"
              class="bg-blue-600 rounded-xl"
              @click="emit('download', currentTask.resultUrl, currentTask.title)"
            >
              <template #icon>
                <slot name="download-icon" />
              </template>
              下载结果
            </a-button>
            <a-button size="large" class="rounded-xl" @click="emit('reset')">
              {{ continueText }}
            </a-button>
          </slot>
        </div>
      </div>

      <div
        v-else-if="currentTask.status === 'failed'"
        class="flex flex-col items-center py-8 w-full flex-grow justify-center"
      >
        <slot name="failed" :task="currentTask">
          <slot name="failed-icon" />
          <p class="text-red-600 font-medium text-lg">{{ failedTitle }}</p>
          <p class="text-slate-400 mt-2">{{ currentTask.error || '未知错误' }}</p>
          <a-button class="mt-6 rounded-xl" @click="emit('reset')">
            {{ retryText }}
          </a-button>
        </slot>
      </div>
    </div>
  </div>
</template>
