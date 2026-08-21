<script setup lang="ts">
import { CloseOutlined, LockOutlined } from '@ant-design/icons-vue'
import { ref } from 'vue'
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
  reorder: [fromIndex: number, toIndex: number]
}>()

const { t } = useI18n()
const draggedIndex = ref<number | null>(null)

const startDrag = (index: number) => {
  draggedIndex.value = index
}

const dropAt = (index: number) => {
  if (draggedIndex.value !== null) emit('reorder', draggedIndex.value, index)
  draggedIndex.value = null
}
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
        :draggable="!item.uploading && !item.locked"
        @dragstart="startDrag(index)"
        @dragover.prevent
        @drop.prevent="dropAt(index)"
        @dragend="draggedIndex = null"
      >
        <span class="lab-reference-tray__order absolute bottom-0.5 left-0.5 rounded-full px-1.5 text-[10px] font-bold">
          {{ index + 1 }}
        </span>
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

        <button
          v-if="!item.uploading && !item.locked"
          type="button"
          class="lab-reference-tray__remove absolute right-0.5 top-0.5 inline-flex items-center justify-center rounded-full"
          :aria-label="t('lab.workbench.remove_reference')"
          :title="t('lab.workbench.remove_reference')"
          @click.stop.prevent="emit('remove', index)"
        >
          <CloseOutlined />
        </button>
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

.lab-reference-tray__item :deep(.ant-image-mask) {
  z-index: 1;
}

.lab-reference-tray__remove {
  z-index: 20;
  width: 24px;
  height: 24px;
  border: 1px solid rgba(255, 255, 255, 0.94);
  background: rgba(239, 68, 68, 0.96);
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.34);
  color: #ffffff;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 0;
}

.lab-reference-tray__order {
  z-index: 3;
  background: rgba(15, 23, 42, 0.82);
  color: #ffffff;
  pointer-events: none;
}

.lab-reference-tray__remove:hover,
.lab-reference-tray__remove:focus-visible {
  background: rgba(220, 38, 38, 1);
  color: #ffffff;
  outline: 2px solid rgba(255, 255, 255, 0.78);
  outline-offset: 1px;
}

:deep(.lab-reference-tray__remove .anticon),
:deep(.lab-reference-tray__remove svg) {
  display: block;
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
