<script setup lang="ts">
import { Compass, RotateCw } from 'lucide-vue-next'

const emit = defineEmits<{
  retry: []
}>()

withDefaults(
  defineProps<{
    loading?: boolean
    empty?: boolean
    emptyText?: string
    errorText?: string
    showRetry?: boolean
    retryText?: string
  }>(),
  {
    loading: false,
    empty: false,
    emptyText: '',
    errorText: '',
    showRetry: false,
    retryText: '重试',
  },
)
</script>

<template>
  <div v-if="loading" class="py-8 text-center">
    <div class="inline-block h-8 w-8 animate-spin rounded-full border-2 border-cyan-500/30 border-t-cyan-500" />
  </div>

  <div v-else-if="errorText" class="py-10 text-center text-slate-400">
    <p class="mb-4">{{ errorText }}</p>
    <button
      v-if="showRetry"
      type="button"
      class="inline-flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-slate-800/70 px-4 py-2 text-cyan-200 transition hover:border-cyan-400 hover:text-white"
      @click="emit('retry')"
    >
      <RotateCw :size="16" />
      <span>{{ retryText }}</span>
    </button>
  </div>

  <div v-else-if="empty" class="py-20 text-center text-slate-500">
    <slot name="empty-icon">
      <Compass :size="48" class="mx-auto mb-4 opacity-20" />
    </slot>
    <p>{{ emptyText }}</p>
  </div>
</template>
