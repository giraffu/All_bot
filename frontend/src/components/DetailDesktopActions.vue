<script setup lang="ts">
import { computed, useSlots } from 'vue'

const props = withDefaults(
  defineProps<{
    containerClass?: string
    topClass?: string
    bottomClass?: string
  }>(),
  {
    containerClass: '',
    topClass: '',
    bottomClass: '',
  },
)

const slots = useSlots()
const hasTop = computed(() => !!slots.top)
const hasBottom = computed(() => !!slots.bottom)
</script>

<template>
  <div class="hidden lg:block" :class="containerClass">
    <div v-if="hasTop" :class="topClass">
      <slot name="top" />
    </div>
    <div v-if="hasBottom" :class="bottomClass">
      <slot name="bottom" />
    </div>
  </div>
</template>
