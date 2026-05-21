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
  <div class="lg:hidden fixed bottom-0 left-0 right-0 bg-[#0f172a]/95 backdrop-blur-lg border-t border-slate-800 px-4 py-3 flex items-center justify-between z-50 safe-area-bottom">
    <div :class="leftClass">
      <slot name="left" />
    </div>
    <div :class="rightClass">
      <slot name="right" />
    </div>
  </div>
</template>
