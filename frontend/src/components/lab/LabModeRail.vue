<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'

import OverflowScrollRail from '@/components/OverflowScrollRail.vue'
import type { LabModeConfig, UnifiedLabModeId } from '@/features/generation/labModeConfig'

const props = defineProps<{
  modes: LabModeConfig[]
  activeModeId: UnifiedLabModeId
  resolveLabel: (key: string) => string
}>()

const emit = defineEmits<{
  select: [modeId: UnifiedLabModeId]
}>()

const modeButtonRefs = ref<Partial<Record<UnifiedLabModeId, HTMLButtonElement>>>({})

const setModeButtonRef = (modeId: UnifiedLabModeId, element: unknown) => {
  if (element instanceof HTMLButtonElement) {
    modeButtonRefs.value[modeId] = element
  } else {
    delete modeButtonRefs.value[modeId]
  }
}

const scrollActiveModeIntoView = async () => {
  await nextTick()
  modeButtonRefs.value[props.activeModeId]?.scrollIntoView({
    behavior: 'smooth',
    block: 'nearest',
    inline: 'center',
  })
}

onMounted(scrollActiveModeIntoView)

watch(
  () => props.activeModeId,
  scrollActiveModeIntoView,
)
</script>

<template>
  <OverflowScrollRail
    container-class="pb-1"
    content-class="flex justify-start gap-2 pr-2 sm:justify-center"
  >
    <button
      v-for="mode in modes"
      :key="mode.id"
      :ref="(element) => setModeButtonRef(mode.id as UnifiedLabModeId, element)"
      type="button"
      class="lab-mode-rail__item rounded-full border px-3.5 py-2 text-left transition-all sm:px-4"
      :class="mode.id === activeModeId ? 'lab-mode-rail__item--active' : 'lab-mode-rail__item--idle'"
      @click="emit('select', mode.id as UnifiedLabModeId)"
    >
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0">
          <div class="whitespace-nowrap text-sm font-semibold">
            {{ resolveLabel(mode.titleKey) }}
          </div>
        </div>
        <div class="lab-mode-rail__cost shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold">
          {{ mode.baseCost }}
        </div>
      </div>
    </button>
  </OverflowScrollRail>
</template>

<style scoped>
.lab-mode-rail__item {
  background: var(--theme-pill-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-secondary);
}

.lab-mode-rail__item--active {
  background: var(--theme-card-hover-bg);
  border-color: var(--theme-tab-active-border);
  color: var(--theme-text-primary);
  box-shadow: 0 8px 20px rgba(59, 130, 246, 0.12);
}

.lab-mode-rail__item--idle:hover {
  border-color: var(--theme-border-strong);
  color: var(--theme-text-primary);
  transform: translateY(-1px);
}

.lab-mode-rail__cost {
  background: var(--theme-panel-strong-bg);
  border: 1px solid var(--theme-border);
  color: #38bdf8;
}

.lab-mode-rail__item--active .lab-mode-rail__cost {
  border-color: rgba(56, 189, 248, 0.26);
  color: #0ea5e9;
}
</style>
