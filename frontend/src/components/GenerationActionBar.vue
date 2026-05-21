<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    cost: string | number
    buttonText: string
    loadingText?: string
    disabled?: boolean
    loading?: boolean
    wrapperClass?: string
    costLabel?: string
    costUnit?: string
    buttonClass?: string
  }>(),
  {
    loadingText: '提交中...',
    disabled: false,
    loading: false,
    wrapperClass:
      'p-6 border-t border-slate-400/50 bg-slate-500/40 shrink-0 flex items-center justify-between',
    costLabel: '预计消耗灵石',
    costUnit: '💎',
    buttonClass:
      'bg-blue-600 hover:bg-blue-500 border-none px-8 font-bold tracking-wider rounded-xl shadow-lg shadow-blue-500/20',
  },
)

const emit = defineEmits<{
  submit: []
}>()
</script>

<template>
  <div :class="wrapperClass">
    <div class="flex flex-col">
      <span class="text-slate-400 text-sm font-medium mb-1">{{ costLabel }}</span>
      <div class="flex items-baseline text-blue-400 font-bold">
        <span class="text-2xl leading-none mr-1">{{ cost }}</span>
        <slot name="cost-unit">
          <span class="text-lg ml-1 mb-0.5">{{ costUnit }}</span>
        </slot>
      </div>
    </div>

    <a-button
      type="primary"
      size="large"
      :class="buttonClass"
      :disabled="disabled"
      :loading="loading"
      @click="emit('submit')"
    >
      <template #icon>
        <slot name="button-icon" />
      </template>
      {{ loading ? loadingText : buttonText }}
    </a-button>
  </div>
</template>
