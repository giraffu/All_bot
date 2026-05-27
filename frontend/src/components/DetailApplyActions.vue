<script setup lang="ts">
import PromptCopyButton from '@/components/PromptCopyButton.vue'
import TemplateApplyButton from '@/components/TemplateApplyButton.vue'

withDefaults(
  defineProps<{
    showCopy?: boolean
    copyLabel?: string
    applyLabel: string
    applyLoading?: boolean
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
  <div :class="inline ? 'flex space-x-2' : 'space-y-4'">
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
      :label="applyLabel"
      :loading-label="applyLoadingLabel"
      @click="emit('apply')"
    />
    <p
      v-if="hintText"
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
