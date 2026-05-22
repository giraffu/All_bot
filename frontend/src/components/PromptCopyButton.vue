<script setup lang="ts">
import { Copy } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    label: string
    compact?: boolean
    fullWidth?: boolean
  }>(),
  {
    compact: false,
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
    :class="compact
      ? 'flex items-center gap-1.5 transition-all text-slate-300'
      : `${fullWidth ? 'w-full' : 'flex-1'} py-3 rounded-xl bg-slate-500 hover:bg-slate-400 text-white font-medium shadow-sm transition-all flex items-center justify-center border border-slate-400`
    "
    @click="emit('click')"
  >
    <Copy :size="compact ? 22 : 18" :class="compact ? '' : 'mr-2'" />
    <span v-if="!compact">{{ label }}</span>
  </button>
</template>
