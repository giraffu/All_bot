<script setup lang="ts">
import { CloseOutlined, LockOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

interface UploadedReferenceItem {
  key: string
  preview: string
  name: string
  uploading?: boolean
  progress?: number
  locked?: boolean
  lockedLabel?: string
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
  <div v-if="items.length > 0" class="lab-reference-tray">
    <div class="sr-only">
      {{ title }} {{ t('lab.workbench.reference_count', { count: items.length }) }}
    </div>

    <div class="flex flex-wrap gap-2">
      <div
        v-for="(item, index) in items"
        :key="item.key"
        class="lab-reference-tray__item group relative overflow-hidden rounded-xl"
        :class="{ 'lab-reference-tray__item--uploading': item.uploading }"
      >
        <a-image
          :src="item.preview"
          class="lab-reference-tray__image block"
          :preview="!item.uploading"
        />

        <div v-if="item.uploading" class="lab-reference-tray__uploading absolute inset-0 flex items-center justify-center">
          <a-progress
            type="circle"
            :percent="item.progress ?? 0"
            :width="34"
            :show-info="false"
            stroke-color="#3b82f6"
          />
        </div>

        <div
          v-if="item.locked && !item.uploading"
          class="lab-reference-tray__locked absolute bottom-1 left-1 right-1 flex items-center justify-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
          :title="item.lockedLabel"
        >
          <LockOutlined />
          <span class="truncate">{{ item.lockedLabel || item.name }}</span>
        </div>

        <a-button
          v-if="!item.uploading && !item.locked"
          danger
          type="primary"
          size="small"
          shape="circle"
          class="lab-reference-tray__remove absolute -right-1 -top-1"
          :aria-label="t('lab.workbench.remove_reference')"
          @click="emit('remove', index)"
        >
          <template #icon>
            <CloseOutlined />
          </template>
        </a-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab-reference-tray__item {
  width: 56px;
  height: 56px;
  border: 1px solid var(--theme-border);
  background: var(--theme-card-strong-bg);
}

:deep(.lab-reference-tray__image),
:deep(.lab-reference-tray__image .ant-image-img),
:deep(.lab-reference-tray__item .ant-image),
:deep(.lab-reference-tray__item img) {
  width: 56px !important;
  height: 56px !important;
  object-fit: cover !important;
  display: block;
}

.lab-reference-tray__item--uploading :deep(img) {
  filter: grayscale(1);
}

.lab-reference-tray__remove {
  z-index: 1;
  width: 18px !important;
  min-width: 18px !important;
  height: 18px !important;
  box-shadow: 0 6px 12px rgba(15, 23, 42, 0.25);
  font-size: 10px;
}

.lab-reference-tray__uploading {
  background: rgba(15, 23, 42, 0.48);
  backdrop-filter: grayscale(1);
}

.lab-reference-tray__locked {
  z-index: 1;
  background: rgba(15, 23, 42, 0.78);
  color: #f8fafc;
  line-height: 1;
}

:deep(.lab-reference-tray__locked .anticon),
:deep(.lab-reference-tray__locked svg) {
  display: block;
  flex: 0 0 auto;
  font-size: 9px;
}

:deep(.lab-reference-tray__uploading .ant-progress-inner) {
  background: rgba(255, 255, 255, 0.22);
}
</style>
