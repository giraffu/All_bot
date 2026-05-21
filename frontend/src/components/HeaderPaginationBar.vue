<script setup lang="ts">
import PagedNavigation from '@/components/PagedNavigation.vue'

const props = withDefaults(
  defineProps<{
    currentPage: number
    totalPages: number
    disabled?: boolean
    compact?: boolean
    wrapperClass?: string
    innerClass?: string
  }>(),
  {
    disabled: false,
    compact: false,
    wrapperClass: 'flex justify-center',
    innerClass:
      'rounded-2xl border border-slate-700/50 bg-slate-950/55 px-3 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]',
  },
)

const emit = defineEmits<{
  change: [page: number]
}>()
</script>

<template>
  <div :class="wrapperClass">
    <div :class="innerClass">
      <PagedNavigation
        :current-page="currentPage"
        :total-pages="totalPages"
        :disabled="disabled"
        :compact="compact"
        @change="emit('change', $event)"
      />
    </div>
  </div>
</template>
