<script setup lang="ts">
import { CloseOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

interface UploadedReferenceItem {
  key: string
  preview: string
  name: string
}

defineProps<{
  title: string
  items: UploadedReferenceItem[]
}>()

const emit = defineEmits<{
  remove: [index: number]
}>()

const { t } = useI18n()
</script>

<template>
  <div v-if="items.length > 0" class="lab-reference-tray rounded-3xl border p-4">
    <div class="mb-3 flex items-center justify-between gap-3">
      <div class="text-sm font-semibold">{{ title }}</div>
      <div class="text-xs opacity-75">
        {{ t('lab.workbench.reference_count', { count: items.length }) }}
      </div>
    </div>

    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div
        v-for="(item, index) in items"
        :key="item.key"
        class="lab-reference-tray__item group relative overflow-hidden rounded-2xl"
      >
        <a-image
          :src="item.preview"
          class="block h-20 w-full object-cover sm:h-24"
          :preview="true"
        />

        <a-button
          danger
          type="primary"
          size="small"
          shape="circle"
          class="lab-reference-tray__remove absolute right-2 top-2"
          :aria-label="t('lab.workbench.remove_reference')"
          @click="emit('remove', index)"
        >
          <template #icon>
            <CloseOutlined />
          </template>
        </a-button>

        <div class="lab-reference-tray__overlay absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-3">
          <div class="min-w-0 text-xs text-white">
            <div class="truncate font-medium">{{ item.name }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab-reference-tray {
  background: var(--theme-panel-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-primary);
}

.lab-reference-tray__item {
  border: 1px solid var(--theme-border);
  background: var(--theme-card-strong-bg);
}

.lab-reference-tray__overlay {
  pointer-events: none;
  background: linear-gradient(180deg, transparent, rgba(15, 23, 42, 0.82));
}

.lab-reference-tray__remove {
  z-index: 1;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.25);
}
</style>
