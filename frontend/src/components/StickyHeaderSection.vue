<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    className?: string
  }>(),
  {
    className: '',
  },
)
</script>

<template>
  <div
    class="flex flex-col mb-3 sticky top-0 z-40 pt-3 gap-3"
    :class="className"
  >
    <slot />
  </div>
</template>
