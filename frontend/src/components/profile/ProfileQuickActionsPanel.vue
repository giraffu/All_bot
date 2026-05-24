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
  <div class="bg-slate-500/50 backdrop-blur-md rounded-xl p-6 border border-slate-400/50 shadow-[0_4px_12px_rgba(0,0,0,0.2)]">
    <h3 class="text-lg font-bold text-slate-200 mb-2 flex items-center drop-shadow-sm">
      <Activity :size="20" class="mr-2 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" /> {{ title }}
    </h3>
    <p class="text-slate-400 mb-4">{{ description }}</p>
    <div class="flex flex-wrap gap-3">
      <a-button
        v-for="action in actions"
        :key="action.key"
        :data-testid="`quick-action-${action.key}`"
        :class="action.className"
        :type="action.key === 'lab' ? 'primary' : 'default'"
        @click="action.onClick"
      >
        <component :is="action.icon" :size="16" class="mr-1 inline" /> {{ action.label }}
      </a-button>
    </div>
  </div>
</template>
