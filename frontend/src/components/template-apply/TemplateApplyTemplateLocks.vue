<script setup lang="ts">
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

const props = defineProps<{
  isTemplateApplied: boolean
  templateApplyNotice: string
  templateSettingsWarning: string
}>()

warnIfPropsExceedBudget('TemplateApplyTemplateLocks', Object.keys(props).length)
</script>

<template>
  <div v-if="isTemplateApplied || templateSettingsWarning" class="space-y-4">
    <div
      v-if="isTemplateApplied"
      class="rounded-xl border border-indigo-500/40 bg-indigo-500/15 px-4 py-3 text-sm text-slate-200"
    >
      {{ templateApplyNotice }}
    </div>

    <div
      v-if="templateSettingsWarning"
      class="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
    >
      {{ templateSettingsWarning }}
    </div>
  </div>
</template>
