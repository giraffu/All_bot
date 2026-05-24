<script setup lang="ts">
import { computed } from 'vue'
import { RefreshCw, Server, Activity } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

type QueueStatusState = {
  loading: boolean
  isFirstLoad: boolean
  data: {
    comfy_online: boolean
    queue_size: number
    queue_by_type?: Record<string, number>
  }
}

const props = defineProps<{
  queueStatus: QueueStatusState
  resolveQueueTaskTypeLabel: (type: string | number) => string
  fetchQueueStatus: () => void | Promise<void>
}>()

const { t } = useI18n()

const queueByTypeEntries = computed(() =>
  Object.entries(props.queueStatus.data.queue_by_type || {})
)
</script>

<template>
  <div class="bg-slate-500/40 rounded-xl p-5 border border-slate-400/50 mt-4 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)]">
    <div class="flex items-center gap-3 mb-4">
      <div class="p-2 bg-cyan-500/20 rounded-xl border border-cyan-500/30">
        <Server class="w-5 h-5 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" />
      </div>
      <h3 class="text-lg font-bold text-slate-200 drop-shadow-sm">{{ t('profile.queue_status_title', '炼丹炉状态') }}</h3>

      <div class="ml-auto flex items-center gap-2">
        <button
          :title="t('profile.refresh_queue', '刷新')"
          class="p-1.5 rounded-lg text-cyan-400 hover:bg-cyan-500/20 transition-all border border-transparent hover:border-cyan-500/30 flex items-center justify-center cursor-pointer"
          :disabled="queueStatus.loading"
          @click="fetchQueueStatus"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': queueStatus.loading }" />
        </button>

        <div
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border"
          :class="queueStatus.data.comfy_online ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20'"
        >
          <div
            class="w-1.5 h-1.5 rounded-full"
            :class="queueStatus.data.comfy_online ? 'bg-emerald-400 animate-pulse shadow-[0_0_5px_rgba(16,185,129,0.8)]' : 'bg-rose-400'"
          />
          {{ queueStatus.data.comfy_online ? t('profile.online', '运行中') : t('profile.offline', '休息中') }}
        </div>
      </div>
    </div>

    <div v-if="queueStatus.isFirstLoad && queueStatus.loading" class="flex justify-center py-6">
      <svg class="animate-spin h-6 w-6 text-cyan-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
    </div>

    <div v-else class="space-y-3">
      <div class="flex justify-between items-center bg-slate-800/50 p-3 rounded-xl border border-slate-600/50">
        <div class="flex items-center gap-2 text-slate-300">
          <Activity class="w-4 h-4 text-indigo-400" />
          <span class="text-sm font-medium">{{ t('profile.total_queue', '总排队任务') }}</span>
        </div>
        <span class="text-lg font-bold text-slate-100">{{ queueStatus.data.queue_size }} <span class="text-xs text-slate-400 font-normal">{{ t('profile.tasks_unit', '个') }}</span></span>
      </div>

      <div v-if="queueByTypeEntries.length > 0" class="grid grid-cols-2 gap-2 mt-2">
        <div
          v-for="[type, count] in queueByTypeEntries"
          :key="type"
          class="flex flex-col bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/50"
        >
          <span class="text-xs text-slate-400 mb-1 truncate">{{ resolveQueueTaskTypeLabel(type) }}</span>
          <span class="text-sm font-bold text-slate-200">{{ count }} {{ t('profile.tasks_unit', '个') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
