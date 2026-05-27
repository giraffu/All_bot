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
      ? `template-apply-button-compact px-5 py-2 rounded-full font-bold text-sm shadow-lg flex items-center ${fullWidth ? 'w-full justify-center' : ''}`
      : `template-apply-button rounded-xl font-bold text-lg transition-all transform hover:scale-[1.02] flex items-center justify-center relative overflow-hidden group ${fullWidth ? 'w-full py-4' : 'flex-1 py-4'}`
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

<style scoped>
.template-apply-button,
.template-apply-button-compact {
  color: #ffffff;
}

.template-apply-button {
  background: var(--detail-modal-primary-gradient);
  box-shadow: var(--detail-modal-primary-glow);
}

.template-apply-button:hover:not(:disabled) {
  background: var(--detail-modal-primary-gradient-hover);
}

.template-apply-button-compact {
  background: var(--detail-modal-primary-solid);
}

.template-apply-button-compact:hover:not(:disabled) {
  background: var(--detail-modal-primary-solid-hover);
}

.template-apply-button:disabled,
.template-apply-button-compact:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
</style>
