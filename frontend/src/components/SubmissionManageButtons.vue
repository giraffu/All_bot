<script setup lang="ts">
import { Eye, EyeOff, Trash2 } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    isActive: boolean
    onShelfLabel: string
    offShelfLabel: string
    deleteLabel: string
    compact?: boolean
  }>(),
  {
    compact: false,
  },
)

const emit = defineEmits<{
  toggle: []
  delete: []
}>()
</script>

<template>
  <div :class="compact ? 'flex space-x-3' : 'flex space-x-2'">
    <button
      type="button"
      :class="compact
        ? `flex-1 py-2.5 rounded-lg border border-slate-700 bg-slate-800/80 transition-all flex items-center justify-center text-xs font-medium ${isActive ? 'text-orange-400' : 'text-green-400'}`
        : `flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500 hover:bg-slate-400 transition-all flex items-center justify-center text-sm font-medium ${isActive ? 'text-orange-400' : 'text-green-400'}`
      "
      @click="emit('toggle')"
    >
      <EyeOff v-if="isActive" :size="compact ? 16 : 18" :class="compact ? 'mr-1.5' : 'mr-2'" />
      <Eye v-else :size="compact ? 16 : 18" :class="compact ? 'mr-1.5' : 'mr-2'" />
      {{ isActive ? offShelfLabel : onShelfLabel }}
    </button>
    <button
      type="button"
      :class="compact
        ? 'flex-1 py-2.5 rounded-lg border border-red-900/50 bg-red-900/20 transition-all flex items-center justify-center text-xs font-medium text-red-400'
        : 'flex-1 py-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 transition-all flex items-center justify-center text-sm font-medium text-red-400 group'
      "
      @click="emit('delete')"
    >
      <Trash2 :size="compact ? 16 : 18" :class="compact ? 'mr-1.5' : 'mr-2 transition-transform group-hover:scale-110'" />
      {{ deleteLabel }}
    </button>
  </div>
</template>
