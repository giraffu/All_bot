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
      ? 'prompt-copy-button-compact flex items-center gap-1.5 transition-all'
      : `prompt-copy-button ${fullWidth ? 'w-full' : 'flex-1'} py-3 rounded-xl font-medium shadow-sm transition-all flex items-center justify-center`
    "
    @click="emit('click')"
  >
    <Copy :size="compact ? 22 : 18" :class="compact ? '' : 'mr-2'" />
    <span v-if="!compact">{{ label }}</span>
  </button>
</template>

<style scoped>
.prompt-copy-button {
  border: 1px solid var(--detail-modal-action-border);
  background: var(--detail-modal-copy-button-bg);
  color: var(--detail-modal-copy-button-text);
}

.prompt-copy-button:hover {
  background: var(--detail-modal-copy-button-hover-bg);
}

.prompt-copy-button-compact {
  color: var(--detail-modal-text-secondary);
}

.prompt-copy-button-compact:hover {
  color: var(--detail-modal-text-primary);
}
</style>
