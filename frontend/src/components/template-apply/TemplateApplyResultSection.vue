<script setup lang="ts">
import { DownloadOutlined } from '@ant-design/icons-vue'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

interface TaskPreviewState {
  title: string
  status: string
  progress: number
  cancelRequested?: boolean
  cancelMessage?: string | null
  refundMessage?: string | null
  error?: string | null
  resultUrl?: string | null
}

const props = defineProps<{
  currentTask: TaskPreviewState | null
  isImageUrl: (url: string) => boolean
}>()

warnIfPropsExceedBudget('TemplateApplyResultSection', Object.keys(props).length)

const emit = defineEmits<{
  download: [url: string, title: string]
}>()
</script>

<template>
  <section class="w-full lg:w-[48%] flex flex-col bg-slate-900/70 rounded-2xl border border-slate-700/70 overflow-hidden">
    <div class="p-6 border-b border-slate-700">
      <h3 class="text-lg font-semibold text-slate-100">{{ $t('template_apply.common.result_title') }}</h3>
    </div>

    <div class="flex-1 overflow-y-auto p-6">
      <div v-if="currentTask" class="space-y-4">
        <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
          <div class="flex items-center justify-between text-sm text-slate-300">
            <span>{{ currentTask.title }}</span>
            <span>
              {{
                currentTask.status === 'cancelled'
                  ? '已取消'
                  : currentTask.cancelRequested
                    ? '撤销确认中'
                    : currentTask.status
              }}
            </span>
          </div>
          <a-progress
            class="mt-3"
            :percent="currentTask.status === 'cancelled' ? 100 : currentTask.progress"
            :status="currentTask.cancelRequested || currentTask.status === 'cancelled'
              ? 'normal'
              : currentTask.status === 'failed'
                ? 'exception'
                : 'active'"
          />
          <div v-if="currentTask.cancelRequested" class="mt-3 text-sm text-amber-300">
            {{ currentTask.cancelMessage || '已提交撤销请求，等待执行端确认。' }}
          </div>
          <div
            v-if="currentTask.cancelRequested || currentTask.status === 'cancelled'"
            class="mt-1 text-xs text-slate-400"
          >
            {{ currentTask.refundMessage || '确认后将自动退回灵石。' }}
          </div>
          <div v-if="currentTask.error" class="mt-3 text-sm text-rose-300">
            {{ currentTask.error }}
          </div>
        </div>

        <div
          v-if="currentTask.resultUrl"
          class="rounded-xl border border-slate-700 bg-slate-950/80 p-3"
        >
          <img
            v-if="isImageUrl(currentTask.resultUrl)"
            :src="currentTask.resultUrl"
            class="w-full rounded-xl object-contain"
          />
          <video
            v-else
            :src="currentTask.resultUrl"
            controls
            class="w-full rounded-xl"
          />

          <div class="mt-3 flex justify-end">
            <a-button @click="emit('download', currentTask.resultUrl, currentTask.title)">
              <template #icon>
                <DownloadOutlined />
              </template>
              {{ $t('template_apply.common.download_result') }}
            </a-button>
          </div>
        </div>
      </div>

      <div
        v-else
        class="h-full min-h-[240px] flex items-center justify-center text-center text-slate-400"
      >
        {{ $t('template_apply.common.result_empty') }}
      </div>
    </div>
  </section>
</template>
