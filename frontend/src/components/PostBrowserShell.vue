<script setup lang="ts">
import ListStateBlock from '@/components/ListStateBlock.vue'

withDefaults(
  defineProps<{
    containerClass?: string
    showState?: boolean
    loading?: boolean
    errorText?: string
    showRetry?: boolean
    empty?: boolean
    emptyText?: string
    retryText?: string
  }>(),
  {
    containerClass: 'gallery-container text-slate-200',
    showState: true,
    loading: false,
    errorText: '',
    showRetry: false,
    empty: false,
    emptyText: '',
    retryText: '重试',
  },
)

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <div :class="containerClass">
    <slot name="header" />
    <slot />
    <ListStateBlock
      v-if="showState"
      :loading="loading"
      :error-text="errorText"
      :show-retry="showRetry"
      :empty="empty"
      :empty-text="emptyText"
      :retry-text="retryText"
      @retry="emit('retry')"
    />
  </div>
</template>
