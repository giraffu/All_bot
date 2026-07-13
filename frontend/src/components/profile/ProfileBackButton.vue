<script setup lang="ts">
import { ChevronLeft } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    label?: string
  }>(),
  {
    label: '返回个人中心',
  },
)

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()
</script>

<template>
  <button
    type="button"
    class="profile-back-button"
    :aria-label="label"
    :title="label"
    data-testid="profile-back-button"
    @click="emit('click', $event)"
  >
    <ChevronLeft :size="24" :stroke-width="2.4" aria-hidden="true" />
    <span class="profile-back-button__label">{{ label }}</span>
  </button>
</template>

<style scoped>
.profile-back-button {
  inline-size: 2.5rem;
  block-size: 2.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border-radius: 999px;
  border: 1px solid var(--theme-border);
  background: var(--theme-card-strong-bg);
  color: var(--theme-text-secondary);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(14px);
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
}

.profile-back-button:hover,
.profile-back-button:focus-visible {
  background: var(--theme-card-hover-bg);
  border-color: var(--theme-border-strong);
  color: var(--theme-text-primary);
  box-shadow: var(--theme-shadow);
}

.profile-back-button:active {
  transform: translateX(-1px) scale(0.98);
}

.profile-back-button__label {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 640px) {
  .profile-back-button {
    inline-size: 2.625rem;
    block-size: 2.625rem;
  }
}
</style>
