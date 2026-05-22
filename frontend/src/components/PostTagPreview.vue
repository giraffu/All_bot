<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    tags: string[]
    formatTag: (tag: string) => string
    maxVisible?: number
    containerClass?: string
    tagClass?: string
    overflowClass?: string
  }>(),
  {
    maxVisible: 4,
    containerClass: 'flex flex-wrap gap-1.5 mb-8',
    tagClass:
      'text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md',
    overflowClass: 'text-[10px] text-slate-300 px-1',
  },
)
</script>

<template>
  <div :class="containerClass">
    <span
      v-for="tag in props.tags.slice(0, maxVisible)"
      :key="tag"
      :class="tagClass"
    >
      {{ formatTag(tag) }}
    </span>
    <span
      v-if="props.tags.length > maxVisible"
      :class="overflowClass"
    >
      ...
    </span>
  </div>
</template>
