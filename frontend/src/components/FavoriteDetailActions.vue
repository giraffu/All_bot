<script setup lang="ts">
import { MessageCircle, Trash2 } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    commentsCount: number
    unfavoriteLabel: string
    compact?: boolean
  }>(),
  {
    compact: false,
  },
)

const emit = defineEmits<{
  unfavorite: []
  comment: []
}>()
</script>

<template>
  <div :class="compact ? 'flex items-center gap-1.5' : 'flex space-x-2'">
    <button
      type="button"
      :class="compact
        ? 'flex items-center gap-1.5 transition-all text-red-400'
        : 'flex-1 py-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all flex items-center justify-center group'
      "
      @click="emit('unfavorite')"
    >
      <Trash2 :size="compact ? 22 : 18" :class="compact ? '' : 'mr-2 transition-transform group-hover:scale-110'" />
      <span :class="compact ? 'text-sm font-medium' : 'font-medium'">{{ unfavoriteLabel }}</span>
    </button>
    <button
      type="button"
      :class="compact
        ? 'flex items-center gap-1.5 transition-all text-slate-300'
        : 'flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group'
      "
      @click="emit('comment')"
    >
      <MessageCircle :size="compact ? 22 : 20" :class="compact ? '' : 'mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400'" />
      <span :class="compact ? 'text-sm font-medium' : 'font-medium text-slate-300'">{{ commentsCount }}</span>
    </button>
  </div>
</template>
