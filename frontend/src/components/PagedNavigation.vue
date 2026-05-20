<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    currentPage: number
    totalPages: number
    disabled?: boolean
    compact?: boolean
  }>(),
  {
    disabled: false,
    compact: false,
  },
)

const emit = defineEmits<{
  (e: 'change', page: number): void
}>()

const pageTokens = computed<(number | string)[]>(() => {
  const total = Math.max(0, props.totalPages)
  const current = Math.min(Math.max(props.currentPage, 1), Math.max(total, 1))

  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1)
  }

  const tokens: (number | string)[] = [1]
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  if (start > 2) {
    tokens.push('start-ellipsis')
  }

  for (let page = start; page <= end; page += 1) {
    tokens.push(page)
  }

  if (end < total - 1) {
    tokens.push('end-ellipsis')
  }

  tokens.push(total)
  return tokens
})

const handlePageChange = (page: number) => {
  if (props.disabled || page === props.currentPage || page < 1 || page > props.totalPages) {
    return
  }
  emit('change', page)
}
</script>

<template>
  <div
    v-if="totalPages > 1"
    class="flex flex-wrap items-center justify-center gap-2"
  >
    <button
      class="pagination-button"
      :class="{ 'pagination-button-compact': compact, 'pagination-button-disabled': disabled || currentPage <= 1 }"
      :disabled="disabled || currentPage <= 1"
      @click="handlePageChange(currentPage - 1)"
    >
      &lt;
    </button>

    <template v-for="token in pageTokens" :key="String(token)">
      <span
        v-if="typeof token === 'string'"
        class="px-1 text-slate-500 select-none"
      >
        ...
      </span>
      <button
        v-else
        class="pagination-button"
        :class="{
          'pagination-button-compact': compact,
          'pagination-button-active': token === currentPage
        }"
        :disabled="disabled"
        @click="handlePageChange(token)"
      >
        {{ token }}
      </button>
    </template>

    <button
      class="pagination-button"
      :class="{ 'pagination-button-compact': compact, 'pagination-button-disabled': disabled || currentPage >= totalPages }"
      :disabled="disabled || currentPage >= totalPages"
      @click="handlePageChange(currentPage + 1)"
    >
      &gt;
    </button>

    <span
      v-if="!compact"
      class="ml-1 text-xs text-slate-400"
    >
      {{ currentPage }} / {{ totalPages }}
    </span>
  </div>
</template>

<style scoped>
.pagination-button {
  min-width: 2.25rem;
  height: 2.25rem;
  padding: 0 0.75rem;
  border-radius: 0.75rem;
  border: 1px solid rgb(100 116 139 / 0.45);
  background: rgb(15 23 42 / 0.72);
  color: rgb(226 232 240);
  font-size: 0.875rem;
  font-weight: 600;
  transition: all 0.2s ease;
}

.pagination-button:hover:not(:disabled) {
  border-color: rgb(34 211 238 / 0.55);
  color: rgb(103 232 249);
}

.pagination-button-active {
  border-color: rgb(34 211 238 / 0.75);
  background: rgb(8 145 178 / 0.2);
  color: rgb(103 232 249);
  box-shadow: 0 0 14px rgb(34 211 238 / 0.18);
}

.pagination-button-disabled {
  opacity: 0.45;
}

.pagination-button-compact {
  min-width: 2rem;
  height: 2rem;
  padding: 0 0.55rem;
  border-radius: 0.625rem;
  font-size: 0.75rem;
}
</style>
