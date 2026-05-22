<script setup lang="ts">
import { Wand2 } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    loading?: boolean
    compact?: boolean
    label: string
    loadingLabel?: string
    fullWidth?: boolean
  }>(),
  {
    loading: false,
    compact: false,
    loadingLabel: '...',
    fullWidth: false,
  },
)

const emit = defineEmits<{
  click: []
}>()
</script>

<template>
  <button
    type="button"
    :disabled="loading"
    :class="compact
      ? `px-5 py-2 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm shadow-lg flex items-center ${fullWidth ? 'w-full justify-center' : ''}`
      : `rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-bold text-lg shadow-[0_0_20px_rgba(56,189,248,0.4)] transition-all transform hover:scale-[1.02] flex items-center justify-center relative overflow-hidden group ${fullWidth ? 'w-full py-4' : 'flex-1 py-4'}`
    "
    @click="emit('click')"
  >
    <div
      v-if="!compact"
      class="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"
    />
    <Wand2
      v-if="!loading"
      :size="compact ? 16 : 22"
      :class="compact ? 'mr-1.5' : 'mr-2 relative z-10'"
    />
    <div
      v-else
      :class="compact
        ? 'inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1.5'
        : 'inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2 relative z-10'"
    />
    <span :class="compact ? '' : 'relative z-10'">
      {{ loading ? loadingLabel : label }}
    </span>
  </button>
</template>
