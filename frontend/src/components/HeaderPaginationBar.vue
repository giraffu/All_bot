<script setup lang="ts">
import PagedNavigation from '@/components/PagedNavigation.vue'

const props = withDefaults(
  defineProps<{
    currentPage: number
    totalPages: number
    disabled?: boolean
    compact?: boolean
    showJump?: boolean
    wrapperClass?: string
    innerClass?: string
  }>(),
  {
    disabled: false,
    compact: false,
    showJump: false,
    wrapperClass: 'flex justify-center',
    innerClass: 'pagination-shell rounded-2xl px-3 py-2',
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
        :show-jump="showJump"
        @change="emit('change', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.pagination-shell {
  border: 1px solid var(--theme-border);
  background: var(--theme-card-strong-bg);
  box-shadow: var(--theme-shadow);
}
</style>
