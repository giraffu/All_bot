<script setup lang="ts">
import { Activity } from 'lucide-vue-next'

type ActionItem = {
  key: string
  label: string
  className: string
  icon: unknown
  onClick: () => void
}

defineProps<{
  title: string
  description: string
  actions: ActionItem[]
}>()
</script>

<template>
  <div class="quick-actions-panel backdrop-blur-md rounded-xl p-6">
    <h3 class="quick-actions-panel__title text-lg font-bold mb-2 flex items-center drop-shadow-sm">
      <Activity :size="20" class="mr-2 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" /> {{ title }}
    </h3>
    <p class="quick-actions-panel__description mb-4">{{ description }}</p>
    <div class="flex flex-wrap gap-3">
      <a-button
        v-for="action in actions"
        :key="action.key"
        :data-testid="`quick-action-${action.key}`"
        :class="['quick-action-btn', action.className]"
        :type="action.key === 'lab' ? 'primary' : 'default'"
        @click="action.onClick"
      >
        <component :is="action.icon" :size="16" class="mr-1 inline" /> {{ action.label }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.quick-actions-panel {
  background: var(--theme-card-bg);
  border: 1px solid var(--theme-border);
  box-shadow: var(--theme-shadow);
}

.quick-actions-panel__title {
  color: var(--theme-text-primary);
}

.quick-actions-panel__description {
  color: var(--theme-text-secondary);
}

:deep(.quick-action-btn) {
  background: var(--theme-pill-bg) !important;
  color: var(--theme-text-primary) !important;
  border-color: var(--theme-border) !important;
  box-shadow: none !important;
}

:deep(.quick-action-btn:hover),
:deep(.quick-action-btn:focus) {
  background: var(--theme-panel-bg) !important;
  color: var(--theme-text-primary) !important;
}

:deep(.quick-action-btn--amber) {
  color: #b45309 !important;
  border-color: rgba(245, 158, 11, 0.35) !important;
}

:deep(.quick-action-btn--amber:hover),
:deep(.quick-action-btn--amber:focus) {
  color: #92400e !important;
  border-color: rgba(245, 158, 11, 0.45) !important;
}

:deep(.quick-action-btn--emerald) {
  color: #047857 !important;
  border-color: rgba(16, 185, 129, 0.35) !important;
}

:deep(.quick-action-btn--emerald:hover),
:deep(.quick-action-btn--emerald:focus) {
  color: #065f46 !important;
  border-color: rgba(16, 185, 129, 0.45) !important;
}

:deep(.quick-action-btn--violet) {
  color: #7c3aed !important;
  border-color: rgba(139, 92, 246, 0.35) !important;
}

:deep(.quick-action-btn--violet:hover),
:deep(.quick-action-btn--violet:focus) {
  color: #6d28d9 !important;
  border-color: rgba(139, 92, 246, 0.45) !important;
}

:deep(.quick-action-btn--indigo) {
  color: #4338ca !important;
  border-color: rgba(99, 102, 241, 0.35) !important;
}

:deep(.quick-action-btn--indigo:hover),
:deep(.quick-action-btn--indigo:focus) {
  color: #3730a3 !important;
  border-color: rgba(99, 102, 241, 0.45) !important;
}
</style>
