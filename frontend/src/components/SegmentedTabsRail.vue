<script setup lang="ts">
import OverflowScrollRail from '@/components/OverflowScrollRail.vue'

interface TabItem {
  id: string
  name: string
}

const props = withDefaults(
  defineProps<{
    items: TabItem[]
    selectedId: string
    containerClass?: string
    contentClass?: string
    buttonClass?: string
    activeClass?: string
    inactiveClass?: string
  }>(),
  {
    containerClass: '',
    contentClass:
      'flex gap-1 bg-slate-500/50 p-1 rounded-xl border border-slate-400/50',
    buttonClass:
      'px-3 py-1 sm:px-4 sm:py-1.5 rounded-lg transition-all font-medium text-xs sm:text-sm whitespace-nowrap shrink-0',
    activeClass:
      'bg-cyan-500/20 text-cyan-400 shadow-[0_0_10px_rgba(56,189,248,0.2)]',
    inactiveClass: 'hover:text-cyan-300 text-slate-400',
  },
)

const emit = defineEmits<{
  select: [id: string]
}>()
</script>

<template>
  <OverflowScrollRail
    :container-class="containerClass"
    :content-class="contentClass"
  >
    <button
      v-for="item in items"
      :key="item.id"
      @click="emit('select', item.id)"
      :class="[
        buttonClass,
        selectedId === item.id ? activeClass : inactiveClass,
      ]"
    >
      {{ item.name }}
    </button>
  </OverflowScrollRail>
</template>
