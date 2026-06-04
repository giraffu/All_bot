<script setup lang="ts">
import PromptCopyButton from '@/components/PromptCopyButton.vue'
import TemplateApplyButton from '@/components/TemplateApplyButton.vue'

withDefaults(
  defineProps<{
    showCopy?: boolean
    copyLabel?: string
    applyLabel: string
    applyLoading?: boolean
    applyDisabled?: boolean
    applyLoadingLabel?: string
    hintText?: string
    inline?: boolean
    compactCopy?: boolean
    compactApply?: boolean
  }>(),
  {
    showCopy: false,
    copyLabel: '',
    applyLoading: false,
    applyDisabled: false,
    applyLoadingLabel: '...',
    hintText: '',
    inline: false,
    compactCopy: false,
    compactApply: false,
  },
)

const emit = defineEmits<{
  copy: []
  apply: []
}>()
</script>

<template>
  <div :class="inline ? 'flex flex-col items-end gap-1 min-w-0' : 'space-y-4'">
    <div :class="inline ? 'flex items-center gap-2 min-w-0' : 'space-y-4'">
      <PromptCopyButton
        v-if="showCopy"
        :full-width="!inline"
        :compact="compactCopy"
        :label="copyLabel"
        @click="emit('copy')"
      />
      <TemplateApplyButton
        :full-width="!inline"
        :compact="compactApply"
        :loading="applyLoading"
        :disabled="applyDisabled"
        :label="applyLabel"
        :loading-label="applyLoadingLabel"
        @click="emit('apply')"
      />
    </div>
    <p
      v-if="hintText && !inline"
      class="detail-apply-hint text-center text-xs mt-3"
    >
      {{ hintText }}
    </p>
  </div>
</template>

<style scoped>
.detail-apply-hint {
  color: var(--detail-modal-text-muted);
}
</style>
