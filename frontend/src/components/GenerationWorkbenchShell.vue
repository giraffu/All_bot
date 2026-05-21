<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    title: string
    description?: string
    containerClass?: string
    innerClass?: string
    leftPanelClass?: string
    leftBodyClass?: string
    rightPanelClass?: string
  }>(),
  {
    description: '',
    containerClass:
      'max-w-7xl mx-auto flex flex-col h-[calc(100vh-80px)] w-full py-4 px-2 sm:px-6',
    innerClass: 'flex flex-col lg:flex-row gap-6 flex-grow min-h-0',
    leftPanelClass:
      'w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden shrink-0',
    leftBodyClass: 'p-6 flex-grow overflow-y-auto custom-scrollbar',
    rightPanelClass:
      'w-full lg:w-[50%] flex flex-col bg-slate-500/40 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden relative',
  },
)
</script>

<template>
  <div :class="containerClass">
    <div :class="innerClass">
      <section :class="leftPanelClass">
        <div :class="leftBodyClass">
          <h2 class="text-2xl font-bold mb-2 text-slate-100">{{ title }}</h2>
          <p v-if="description" class="text-slate-400 mb-6 text-sm">
            {{ description }}
          </p>

          <slot name="left-top" />
          <slot name="left-content" />
        </div>

        <slot name="left-footer" />
      </section>

      <section :class="rightPanelClass">
        <slot name="right-panel" />
      </section>
    </div>
  </div>
</template>
