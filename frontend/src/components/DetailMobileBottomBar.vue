<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    leftClass?: string
    rightClass?: string
  }>(),
  {
    leftClass: 'flex items-center gap-6',
    rightClass: '',
  },
)
</script>

<template>
  <div class="detail-mobile-bottom-bar lg:hidden fixed bottom-0 left-0 right-0 px-4 py-3 flex items-center justify-between z-50 safe-area-bottom">
    <div :class="leftClass">
      <slot name="left" />
    </div>
    <div :class="rightClass">
      <slot name="right" />
    </div>
  </div>
</template>

<style scoped>
.detail-mobile-bottom-bar {
  background: var(--detail-modal-bottom-bar-bg);
  backdrop-filter: blur(18px);
  border-top: 1px solid var(--detail-modal-divider);
}
</style>
