<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    infoContentClass?: string
    desktopCloseButtonClass?: string
  }>(),
  {
    infoContentClass: 'p-4 lg:p-6 flex-1 flex flex-col',
    desktopCloseButtonClass: '',
  },
)

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <div class="flex flex-col lg:flex-row bg-[#0f172a] sm:rounded-2xl overflow-hidden sm:border border-slate-400/50 sm:shadow-2xl w-full min-h-full sm:min-h-0 relative">
    <div class="lg:hidden flex items-center justify-between px-4 h-14 shrink-0 bg-[#0f172a]/90 backdrop-blur-md sticky top-0 z-50 border-b border-slate-800">
      <div class="flex items-center gap-3">
        <button @click="emit('close')" class="text-slate-200 hover:text-white p-1 -ml-1">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <div class="flex items-center gap-2">
          <slot name="mobile-header" />
        </div>
      </div>
    </div>

    <slot name="media" />

    <div class="w-full lg:w-1/3 flex flex-col bg-[#0f172a] lg:bg-slate-500/80 lg:backdrop-blur-xl relative pb-[80px] lg:pb-0">
      <button
        @click="emit('close')"
        class="hidden lg:block absolute top-4 right-4 text-slate-400 hover:text-white transition-colors"
        :class="desktopCloseButtonClass"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>

      <div :class="infoContentClass">
        <slot name="info" />
      </div>
    </div>

    <slot />
  </div>
</template>
