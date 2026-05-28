<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronUp, Copy } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    title: string
    prompt?: string | null
    expandLabel: string
    collapseLabel: string
    copyLabel?: string
    showCopy?: boolean
    collapsedLines?: number
    collapsedChars?: number
  }>(),
  {
    prompt: '',
    copyLabel: '',
    showCopy: false,
    collapsedLines: 4,
    collapsedChars: 220,
  },
)

const emit = defineEmits<{
  copy: []
}>()

const expanded = ref(false)

const normalizedPrompt = computed(() => props.prompt?.trim() ?? '')
const lineCount = computed(() => normalizedPrompt.value.split(/\r?\n/).length)
const shouldCollapse = computed(() =>
  normalizedPrompt.value.length > props.collapsedChars || lineCount.value > props.collapsedLines
)
const isCollapsed = computed(() => shouldCollapse.value && !expanded.value)
const collapsedContentStyle = computed(() =>
  isCollapsed.value ? { WebkitLineClamp: String(props.collapsedLines) } : undefined
)

watch(normalizedPrompt, () => {
  expanded.value = false
})
</script>

<template>
  <section v-if="normalizedPrompt" class="prompt-preview-panel rounded-2xl border p-4 lg:p-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="prompt-preview-title text-sm font-semibold">
          {{ title }}
        </div>
        <div class="prompt-preview-subtitle mt-1 text-xs">
          {{ normalizedPrompt.length }} chars
        </div>
      </div>
      <button
        v-if="showCopy"
        type="button"
        class="prompt-preview-action-btn shrink-0 inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition-colors"
        @click="emit('copy')"
      >
        <Copy :size="14" />
        <span>{{ copyLabel }}</span>
      </button>
    </div>

    <p
      class="prompt-preview-content mt-3 whitespace-pre-wrap break-words text-sm leading-6"
      :class="{ 'is-collapsed': isCollapsed }"
      :style="collapsedContentStyle"
    >
      {{ normalizedPrompt }}
    </p>

    <div v-if="shouldCollapse" class="mt-3 flex justify-end">
      <button
        type="button"
        class="prompt-preview-toggle inline-flex items-center gap-1 text-xs font-medium transition-colors"
        @click="expanded = !expanded"
      >
        <span>{{ expanded ? collapseLabel : expandLabel }}</span>
        <ChevronUp v-if="expanded" :size="14" />
        <ChevronDown v-else :size="14" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.prompt-preview-panel {
  background: var(--prompt-preview-bg, rgba(15, 23, 42, 0.58));
  border-color: var(--prompt-preview-border, rgba(148, 163, 184, 0.2));
  box-shadow: var(--prompt-preview-shadow, inset 0 1px 0 rgba(255, 255, 255, 0.04));
}

.prompt-preview-title {
  color: var(--prompt-preview-title, var(--detail-modal-text-primary, #f8fafc));
}

.prompt-preview-subtitle,
.prompt-preview-toggle {
  color: var(--prompt-preview-muted, var(--detail-modal-text-muted, #94a3b8));
}

.prompt-preview-content {
  color: var(--prompt-preview-text, var(--detail-modal-text-secondary, #cbd5e1));
}

.prompt-preview-content.is-collapsed {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
}

.prompt-preview-action-btn {
  border: 1px solid var(--prompt-preview-action-border, rgba(148, 163, 184, 0.24));
  background: var(--prompt-preview-action-bg, rgba(51, 65, 85, 0.35));
  color: var(--prompt-preview-action-text, var(--detail-modal-text-primary, #f8fafc));
}

.prompt-preview-action-btn:hover {
  background: var(--prompt-preview-action-hover, rgba(71, 85, 105, 0.5));
}

.prompt-preview-toggle:hover {
  color: var(--prompt-preview-title, var(--detail-modal-text-primary, #f8fafc));
}
</style>
