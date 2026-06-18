<script setup lang="ts">
import { ArrowRightToLine, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    currentPage: number
    totalPages: number
    disabled?: boolean
    compact?: boolean
    showJump?: boolean
    minimal?: boolean
  }>(),
  {
    disabled: false,
    compact: false,
    showJump: false,
    minimal: false,
  },
)

const emit = defineEmits<{
  (e: 'change', page: number): void
}>()

const jumpValue = ref('')

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

const jumpInputStyle = computed(() => {
  const digits = String(Math.max(props.totalPages, 1)).length
  return {
    width: `${Math.min(Math.max(digits + 1, 4), 7)}ch`,
  }
})

const maxJumpChars = computed(() => {
  return Math.max(String(Math.max(props.totalPages, 1)).length + 1, 2)
})

const getJumpTargetPage = () => {
  const parsedPage = Number.parseInt(jumpValue.value, 10)
  if (!Number.isFinite(parsedPage) || props.totalPages < 1) {
    return null
  }
  return Math.min(Math.max(parsedPage, 1), props.totalPages)
}

const canSubmitJump = computed(() => {
  const targetPage = getJumpTargetPage()
  return !props.disabled && targetPage !== null && targetPage !== props.currentPage
})

const handlePageChange = (page: number) => {
  if (props.disabled || page === props.currentPage || page < 1 || page > props.totalPages) {
    return
  }
  emit('change', page)
}

const handleJumpInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  const nextValue = input.value.replace(/\D/g, '').slice(0, maxJumpChars.value)
  jumpValue.value = nextValue
  input.value = nextValue
}

const handleJumpSubmit = () => {
  const targetPage = getJumpTargetPage()
  if (targetPage === null) {
    return
  }

  jumpValue.value = ''
  handlePageChange(targetPage)
}

watch(
  () => [props.currentPage, props.totalPages],
  () => {
    jumpValue.value = ''
  },
)
</script>

<template>
  <div
    v-if="totalPages > 1"
    class="paged-navigation flex flex-wrap items-center justify-center gap-2"
    :class="{ 'paged-navigation-minimal': minimal }"
  >
    <template v-if="minimal">
      <button
        class="pagination-button"
        :class="{ 'pagination-button-compact': compact, 'pagination-button-disabled': disabled || currentPage <= 1 }"
        :disabled="disabled || currentPage <= 1"
        aria-label="上一页"
        @click="handlePageChange(currentPage - 1)"
      >
        <ChevronLeft :size="compact ? 14 : 16" aria-hidden="true" />
      </button>

      <span
        class="pagination-page-indicator"
        :class="{ 'pagination-page-indicator-compact': compact }"
        aria-live="polite"
      >
        {{ currentPage }} / {{ totalPages }}
      </span>

      <button
        class="pagination-button"
        :class="{ 'pagination-button-compact': compact, 'pagination-button-disabled': disabled || currentPage >= totalPages }"
        :disabled="disabled || currentPage >= totalPages"
        aria-label="下一页"
        @click="handlePageChange(currentPage + 1)"
      >
        <ChevronRight :size="compact ? 14 : 16" aria-hidden="true" />
      </button>
    </template>

    <template v-else>
      <button
        class="pagination-button"
        :class="{ 'pagination-button-compact': compact, 'pagination-button-disabled': disabled || currentPage <= 1 }"
        :disabled="disabled || currentPage <= 1"
        aria-label="上一页"
        @click="handlePageChange(currentPage - 1)"
      >
        <ChevronLeft :size="compact ? 15 : 16" aria-hidden="true" />
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
          :aria-current="token === currentPage ? 'page' : undefined"
          @click="handlePageChange(token)"
        >
          {{ token }}
        </button>
      </template>

      <button
        class="pagination-button"
        :class="{ 'pagination-button-compact': compact, 'pagination-button-disabled': disabled || currentPage >= totalPages }"
        :disabled="disabled || currentPage >= totalPages"
        aria-label="下一页"
        @click="handlePageChange(currentPage + 1)"
      >
        <ChevronRight :size="compact ? 15 : 16" aria-hidden="true" />
      </button>

    </template>

    <form
      v-if="showJump"
      class="pagination-jump"
      :class="{ 'pagination-jump-compact': compact }"
      @submit.prevent="handleJumpSubmit"
    >
      <input
        class="pagination-jump-input"
        :class="{ 'pagination-jump-input-compact': compact }"
        :value="jumpValue"
        :style="jumpInputStyle"
        :disabled="disabled"
        inputmode="numeric"
        pattern="[0-9]*"
        autocomplete="off"
        :placeholder="String(currentPage)"
        :aria-label="`跳转页码，1 到 ${totalPages}`"
        @input="handleJumpInput"
      >
      <button
        type="submit"
        class="pagination-jump-submit"
        :class="{
          'pagination-jump-submit-compact': compact,
          'pagination-jump-submit-disabled': !canSubmitJump
        }"
        :disabled="!canSubmitJump"
        aria-label="跳转到输入页码"
        title="跳转到输入页码"
      >
        <ArrowRightToLine :size="compact ? 14 : 15" aria-hidden="true" />
      </button>
    </form>

    <span
      v-if="!minimal && !compact"
      class="ml-1 text-xs text-slate-400"
    >
      {{ currentPage }} / {{ totalPages }}
    </span>
  </div>
</template>

<style scoped>
.paged-navigation {
  row-gap: 0.5rem;
}

.paged-navigation-minimal {
  flex-wrap: nowrap;
  gap: 0.375rem;
  row-gap: 0;
}

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
  display: inline-flex;
  align-items: center;
  justify-content: center;
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

.paged-navigation-minimal .pagination-button-compact {
  min-width: 1.85rem;
  height: 1.85rem;
  padding: 0 0.35rem;
  border-radius: 0.55rem;
}

.pagination-page-indicator {
  height: 2.25rem;
  min-width: 4.75rem;
  padding: 0 0.65rem;
  border-radius: 0.75rem;
  border: 1px solid rgb(34 211 238 / 0.36);
  background: rgb(8 145 178 / 0.16);
  color: rgb(103 232 249);
  font-size: 0.8125rem;
  font-weight: 700;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.pagination-page-indicator-compact {
  height: 1.85rem;
  min-width: 4.25rem;
  padding: 0 0.5rem;
  border-radius: 0.55rem;
  font-size: 0.72rem;
}

.pagination-jump {
  height: 2.25rem;
  padding: 0.2rem 0.25rem;
  border-radius: 0.75rem;
  border: 1px solid rgb(100 116 139 / 0.38);
  background: rgb(15 23 42 / 0.5);
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.pagination-jump-compact {
  height: 2rem;
  padding: 0.18rem 0.22rem;
  border-radius: 0.625rem;
}

.pagination-jump-input {
  height: 1.75rem;
  min-width: 2.65rem;
  max-width: 4.8rem;
  box-sizing: border-box;
  border-radius: 0.55rem;
  border: 1px solid rgb(100 116 139 / 0.4);
  background: rgb(15 23 42 / 0.66);
  color: rgb(226 232 240);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
  text-align: center;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, color 0.2s ease;
}

.pagination-jump-input::placeholder {
  color: rgb(148 163 184 / 0.82);
}

.pagination-jump-input:focus {
  border-color: rgb(34 211 238 / 0.65);
  color: rgb(103 232 249);
  box-shadow: 0 0 12px rgb(34 211 238 / 0.16);
}

.pagination-jump-input:disabled {
  opacity: 0.55;
}

.pagination-jump-input-compact {
  height: 1.55rem;
  min-width: 2.35rem;
  max-width: 4.4rem;
  border-radius: 0.48rem;
  font-size: 0.7rem;
}

.pagination-jump-submit {
  width: 1.75rem;
  height: 1.75rem;
  padding: 0;
  border-radius: 0.55rem;
  border: 1px solid rgb(34 211 238 / 0.4);
  background: rgb(8 145 178 / 0.18);
  color: rgb(103 232 249);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.pagination-jump-submit:hover:not(:disabled) {
  border-color: rgb(34 211 238 / 0.68);
  background: rgb(8 145 178 / 0.28);
  box-shadow: 0 0 12px rgb(34 211 238 / 0.16);
}

.pagination-jump-submit-disabled {
  opacity: 0.45;
}

.pagination-jump-submit-compact {
  width: 1.55rem;
  height: 1.55rem;
  border-radius: 0.48rem;
}
</style>
