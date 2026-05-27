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
      <section :class="['generation-workbench-panel', leftPanelClass]">
        <div :class="leftBodyClass">
          <h2 class="generation-workbench-title text-2xl font-bold mb-2">{{ title }}</h2>
          <p v-if="description" class="generation-workbench-description mb-6 text-sm">
            {{ description }}
          </p>

          <slot name="left-top" />
          <slot name="left-content" />
        </div>

        <slot name="left-footer" />
      </section>

      <section :class="['generation-workbench-panel', rightPanelClass]">
        <slot name="right-panel" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.generation-workbench-panel {
  background: var(--theme-card-bg) !important;
  border: 1px solid var(--theme-border) !important;
  box-shadow: var(--theme-shadow) !important;
}

.generation-workbench-title {
  color: var(--theme-text-primary);
}

.generation-workbench-description {
  color: var(--theme-text-secondary);
}
</style>
