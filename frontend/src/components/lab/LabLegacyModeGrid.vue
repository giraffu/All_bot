<script setup lang="ts">
import type { LegacyLabModeId, LabModeConfig } from '@/features/generation/labModeConfig'

defineProps<{
  modes: LabModeConfig[]
  resolveLabel: (key: string) => string
}>()

const emit = defineEmits<{
  open: [modeId: LegacyLabModeId]
}>()
</script>

<template>
  <section class="lab-legacy-grid mx-auto w-full max-w-4xl">
    <div class="mb-3 flex items-center justify-between gap-3 px-1">
      <div>
        <div class="text-base font-semibold">{{ resolveLabel('lab.workbench.legacy_title') }}</div>
        <div class="mt-1 text-xs opacity-65 sm:text-sm">{{ resolveLabel('lab.workbench.legacy_desc') }}</div>
      </div>
      <div class="lab-legacy-grid__badge hidden rounded-full px-3 py-1 text-xs font-medium sm:block">
        {{ resolveLabel('lab.workbench.legacy_badge') }}
      </div>
    </div>

    <div class="flex gap-3 overflow-x-auto pb-1">
      <button
        v-for="mode in modes"
        :key="mode.id"
        type="button"
        class="lab-legacy-grid__card min-w-[180px] rounded-xl border px-4 py-3 text-left transition-all"
        @click="emit('open', mode.id as LegacyLabModeId)"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="truncate text-sm font-semibold">{{ resolveLabel(mode.titleKey) }}</div>
            <div class="mt-1 line-clamp-1 text-xs opacity-75">
              {{ resolveLabel(mode.descriptionKey) }}
            </div>
          </div>
          <div class="lab-legacy-grid__cost shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold">
            {{ mode.baseCost }}
          </div>
        </div>
      </button>
    </div>
  </section>
</template>

<style scoped>
.lab-legacy-grid {
  color: var(--theme-text-primary);
}

.lab-legacy-grid__badge {
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid var(--theme-border);
  color: var(--theme-text-secondary);
}

.lab-legacy-grid__card {
  background: var(--theme-card-strong-bg);
  border-color: var(--theme-border);
  color: inherit;
}

.lab-legacy-grid__card:hover {
  border-color: var(--theme-border-strong);
  transform: translateY(-2px);
}

.lab-legacy-grid__cost {
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-border);
  color: #38bdf8;
}
</style>
