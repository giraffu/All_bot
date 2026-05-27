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
  <div class="detail-modal-shell flex flex-col lg:flex-row sm:rounded-2xl overflow-hidden sm:border w-full min-h-full sm:min-h-0 relative">
    <div class="detail-modal-mobile-header lg:hidden flex items-center justify-between px-4 h-14 shrink-0 sticky top-0 z-50">
      <div class="flex items-center gap-3">
        <button @click="emit('close')" class="detail-modal-icon-button p-1 -ml-1">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <div class="flex items-center gap-2">
          <slot name="mobile-header" />
        </div>
      </div>
    </div>

    <slot name="media" />

    <div class="detail-modal-info-panel w-full lg:w-1/3 flex flex-col relative pb-[80px] lg:pb-0">
      <button
        @click="emit('close')"
        class="detail-modal-desktop-close hidden lg:block absolute top-4 right-4 transition-colors"
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

<style scoped>
.detail-modal-shell {
  background: var(--detail-modal-shell-bg);
  border-color: var(--detail-modal-border);
  box-shadow: var(--detail-modal-shadow);
}

.detail-modal-mobile-header {
  background: var(--detail-modal-header-bg);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--detail-modal-divider);
}

.detail-modal-info-panel {
  background: var(--detail-modal-panel-bg);
  color: var(--detail-modal-text-primary);
}

.detail-modal-icon-button,
.detail-modal-desktop-close {
  color: var(--detail-modal-text-secondary);
}

.detail-modal-icon-button:hover,
.detail-modal-desktop-close:hover {
  color: var(--detail-modal-text-primary);
}
</style>
