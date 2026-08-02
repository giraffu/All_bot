<script setup lang="ts">
import {
  ArrowUpOutlined,
  CloseOutlined,
  EllipsisOutlined,
  LockOutlined,
  PictureOutlined,
  PlusOutlined,
  ThunderboltOutlined,
  UndoOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons-vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import LabReferenceTray from '@/components/lab/LabReferenceTray.vue'
import { useViewport } from '@/composables/useViewport'
import type { LabUploadSlotId } from '@/features/generation/labModeConfig'
import type { PromptOptimizerTemplate } from '@/composables/lab-workbench/usePromptOptimizer'

interface UploadedReferenceItem {
  key: string
  preview: string
  name: string
  uploading?: boolean
  progress?: number
  locked?: boolean
  lockedLabel?: string
}

type LabAssetUploadSlot = {
  id: LabUploadSlotId
  label: string
  hint: string
  buttonLabel: string
  accept: string
  previewKind: 'image' | 'video'
  required: boolean
  item: (UploadedReferenceItem & { previewKind: 'image' | 'video' }) | null
}

const props = defineProps<{
  title: string
  description: string
  promptPlaceholder: string
  prompt: string
  showPromptInput?: boolean
  promptLocked: boolean
  promptLockedHint?: string
  showStructuredPromptInput: boolean
  references: UploadedReferenceItem[]
  assetUploadSlots: LabAssetUploadSlot[]
  referenceTitle: string
  supportsUpload: boolean
  canUploadReference: boolean
  uploadButtonLabel: string
  beforeUpload: (file: File) => boolean | Promise<boolean>
  beforeUploadSlot: (slotId: LabUploadSlotId, file: File) => boolean | Promise<boolean>
  submitText: string
  submitDisabled: boolean
  submitLoading: boolean
  cost: number
  costHint?: string
  hasAdvancedOptions: boolean
  notice?: string
  warning?: string
  promptOptimizerTemplates?: PromptOptimizerTemplate[]
  selectedPromptTemplateRef?: string
  showPromptOptimizer?: boolean
  optimizePromptDisabled?: boolean
  optimizePromptLoading?: boolean
  canRestoreOriginalPrompt?: boolean
}>()

const emit = defineEmits<{
  'update:prompt': [value: string]
  submit: []
  removeReference: [index: number]
  removeUploadSlot: [slotId: LabUploadSlotId]
  assetVideoMetadata: [slotId: LabUploadSlotId, durationSeconds: number | null]
  optimizePrompt: []
  restoreOriginalPrompt: []
  'update:selectedPromptTemplateRef': [value: string]
}>()

const { t } = useI18n()
const { isMobile } = useViewport()
const advancedVisible = ref(false)

const canShowAdvancedAsPopover = computed(() => !isMobile.value)
const hasAssetUploadSlots = computed(() => props.assetUploadSlots.length > 0)

const closeAdvanced = () => {
  advancedVisible.value = false
}

const handleBeforeUploadSlot = (slotId: LabUploadSlotId) => (file: File) => props.beforeUploadSlot(slotId, file)

const normalizeVideoDuration = (value: number) => (
  Number.isFinite(value) && value > 0 ? value : null
)

const handleAssetVideoLoadedMetadata = (slotId: LabUploadSlotId, event: Event) => {
  const video = event.currentTarget as HTMLVideoElement | null
  emit('assetVideoMetadata', slotId, normalizeVideoDuration(video?.duration ?? Number.NaN))
}

const compactUploadLabel = (label: string) => label
  .replace(/^添加\s*/, '')
  .replace(/^Add\s+/i, '')
</script>

<template>
  <section class="lab-composer mx-auto w-full max-w-4xl rounded-[22px] border p-3 shadow-sm sm:p-4">
    <div class="mb-2 px-1 sm:px-2">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0 truncate text-base font-semibold tracking-tight sm:text-lg">{{ title }}</div>
        <div
          class="lab-composer__cost-pill shrink-0 rounded-full px-3 py-1.5 text-sm font-semibold"
          :title="costHint || undefined"
        >
          {{ cost }}
          <span class="ml-1 text-xs opacity-75">{{ t('app.credits') }}</span>
        </div>
      </div>
      <div class="min-w-0">
        <p class="mt-1 max-w-2xl text-sm leading-5 opacity-70">
          {{ description }}
        </p>
      </div>
    </div>

    <div v-if="notice" class="lab-composer__notice mb-3 rounded-2xl border px-4 py-2.5 text-sm">
      {{ notice }}
    </div>

    <div v-if="warning" class="lab-composer__warning mb-3 rounded-2xl border px-4 py-2.5 text-sm">
      {{ warning }}
    </div>

    <div class="lab-composer__textarea-shell rounded-[20px] border p-3 sm:p-4">
      <slot name="before-prompt" />

      <LabReferenceTray
        v-if="references.length > 0"
        :title="referenceTitle"
        :items="references"
        class="mb-3"
        @remove="emit('removeReference', $event)"
      />

      <div v-if="hasAssetUploadSlots">
        <div class="lab-composer__asset-grid">
          <div
            v-for="slot in assetUploadSlots"
            :key="slot.id"
            class="lab-composer__asset-card flex min-h-0 flex-col rounded-[20px] border p-2 sm:p-3"
          >
            <div
              class="lab-composer__asset-preview relative rounded-2xl"
              :class="{ 'lab-composer__asset-preview--uploading': slot.item?.uploading }"
            >
              <img
                v-if="slot.item && slot.previewKind === 'image'"
                :src="slot.item.preview"
                :alt="slot.item.name"
              >
              <video
                v-else-if="slot.item && slot.previewKind === 'video'"
                :src="slot.item.preview"
                muted
                playsinline
                preload="metadata"
                @loadedmetadata="handleAssetVideoLoadedMetadata(slot.id, $event)"
                @durationchange="handleAssetVideoLoadedMetadata(slot.id, $event)"
              />
              <component
                :is="slot.previewKind === 'video' ? VideoCameraOutlined : PictureOutlined"
                v-else
                class="text-3xl opacity-70"
              />

              <div v-if="slot.item?.uploading" class="lab-composer__asset-uploading absolute inset-0 flex items-center justify-center">
                <a-progress
                  type="circle"
                  :percent="slot.item.progress ?? 0"
                  :width="38"
                  :show-info="false"
                  stroke-color="#3b82f6"
                />
              </div>
            </div>

            <div class="lab-composer__asset-meta mt-2 flex items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-semibold">{{ slot.label }}</div>
                <div class="lab-composer__asset-hint mt-1 text-xs leading-4 opacity-70">
                  {{ slot.item?.name || slot.hint }}
                </div>
              </div>

              <a-button
                v-if="slot.item && !slot.item.uploading"
                class="lab-composer__icon-btn"
                shape="circle"
                size="small"
                :aria-label="t('lab.workbench.remove_asset')"
                @click="emit('removeUploadSlot', slot.id)"
              >
                <template #icon>
                  <CloseOutlined />
                </template>
              </a-button>
            </div>

            <a-upload
              :accept="slot.accept"
              :show-upload-list="false"
              :before-upload="handleBeforeUploadSlot(slot.id)"
              :disabled="slot.item?.uploading"
            >
              <a-button class="lab-composer__asset-upload-btn lab-composer__ghost-btn mt-2 w-full rounded-full" :disabled="slot.item?.uploading">
                <template #icon>
                  <PlusOutlined />
                </template>
                {{ slot.item && !slot.item.uploading ? t('lab.workbench.replace_asset') : compactUploadLabel(slot.buttonLabel) }}
              </a-button>
            </a-upload>
          </div>
        </div>

        <a-textarea
          v-if="showStructuredPromptInput && !promptLocked"
          :value="prompt"
          :auto-size="{ minRows: 2, maxRows: 5 }"
          :maxlength="2000"
          show-count
          class="lab-composer__textarea lab-composer__structured-prompt mt-3 rounded-2xl border px-3 py-2"
          :placeholder="promptPlaceholder"
          @update:value="emit('update:prompt', String($event))"
        />
      </div>

      <div v-else-if="promptLocked && showPromptInput !== false" class="lab-composer__locked flex min-h-[160px] flex-col items-center justify-center rounded-[18px] border px-6 py-8 text-center">
        <LockOutlined class="mb-4 text-2xl" />
        <div class="text-base font-semibold">{{ t('template_apply.common.prompt_locked_title') }}</div>
        <div class="mt-2 max-w-md text-sm opacity-80">
          {{ promptLockedHint || t('template_apply.common.prompt_locked_image_hint') }}
        </div>
      </div>

      <a-textarea
        v-else-if="showPromptInput !== false"
        :value="prompt"
        :auto-size="{ minRows: 2, maxRows: 6 }"
        :maxlength="2000"
        show-count
        class="lab-composer__textarea"
        :placeholder="promptPlaceholder"
        @update:value="emit('update:prompt', String($event))"
      />

      <div class="lab-composer__actions mt-3 flex items-center justify-between gap-2 border-t pt-3">
        <div class="lab-composer__actions-left flex min-w-0 items-center gap-2 overflow-hidden">
          <a-upload
            v-if="supportsUpload && !hasAssetUploadSlots && canUploadReference"
            accept="image/png,image/jpeg,image/webp"
            :show-upload-list="false"
            :before-upload="beforeUpload"
          >
            <a-button class="lab-composer__compact-btn lab-composer__ghost-btn rounded-full">
              <template #icon>
                <PlusOutlined />
              </template>
              {{ compactUploadLabel(uploadButtonLabel) }}
            </a-button>
          </a-upload>

          <a-select
            v-if="showPromptOptimizer"
            :value="selectedPromptTemplateRef"
            class="min-w-[132px] max-w-[190px]"
            size="middle"
            :options="(promptOptimizerTemplates || []).map(item => ({
              value: `${item.id}@${item.version}`,
              label: item.label,
              title: item.description,
            }))"
            @update:value="emit('update:selectedPromptTemplateRef', String($event))"
          />

          <a-button
            v-if="showPromptOptimizer"
            class="lab-composer__compact-btn lab-composer__ghost-btn rounded-full"
            :disabled="optimizePromptDisabled"
            :loading="optimizePromptLoading"
            @click="emit('optimizePrompt')"
          >
            <template #icon><ThunderboltOutlined /></template>
            {{ t('lab.workbench.optimize_prompt') }} · 1 {{ t('app.credits') }}
          </a-button>

          <a-button
            v-if="showPromptOptimizer && canRestoreOriginalPrompt"
            class="lab-composer__icon-only-btn lab-composer__ghost-btn rounded-full"
            :title="t('lab.workbench.restore_original_prompt')"
            @click="emit('restoreOriginalPrompt')"
          >
            <template #icon><UndoOutlined /></template>
          </a-button>

          <a-popover
            v-if="hasAdvancedOptions && canShowAdvancedAsPopover"
            v-model:open="advancedVisible"
            trigger="click"
            placement="bottomRight"
            overlay-class-name="app-theme-overlay"
          >
            <template #content>
              <div class="w-[min(90vw,420px)]">
                <slot name="advanced-panel" :close="closeAdvanced" />
              </div>
            </template>

            <a-button
              class="lab-composer__icon-only-btn lab-composer__ghost-btn rounded-full"
              :aria-label="t('lab.workbench.more_settings')"
              :title="t('lab.workbench.more_settings')"
            >
              <template #icon>
                <EllipsisOutlined />
              </template>
            </a-button>
          </a-popover>

          <a-button
            v-else-if="hasAdvancedOptions"
            class="lab-composer__icon-only-btn lab-composer__ghost-btn rounded-full"
            :aria-label="t('lab.workbench.more_settings')"
            :title="t('lab.workbench.more_settings')"
            @click="advancedVisible = true"
          >
            <template #icon>
              <EllipsisOutlined />
            </template>
          </a-button>
        </div>

        <div class="lab-composer__actions-submit flex shrink-0 items-center">
          <a-button
            type="primary"
            size="large"
            shape="circle"
            class="lab-composer__submit-btn h-11 w-11 rounded-full p-0"
            :aria-label="submitText"
            :title="submitText"
            :disabled="submitDisabled"
            :loading="submitLoading"
            @click="emit('submit')"
          >
            <template #icon>
              <ArrowUpOutlined />
            </template>
          </a-button>
        </div>
      </div>
    </div>

    <a-drawer
      v-if="hasAdvancedOptions && !canShowAdvancedAsPopover"
      v-model:open="advancedVisible"
      placement="bottom"
      height="auto"
      class="lab-composer__drawer"
      :title="t('lab.workbench.advanced_title')"
    >
      <slot name="advanced-panel" :close="closeAdvanced" />
    </a-drawer>
  </section>
</template>

<style scoped>
.lab-composer {
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.14), transparent 32%),
    linear-gradient(180deg, var(--theme-card-hover-bg), var(--theme-card-bg));
  border-color: var(--theme-border);
  color: var(--theme-text-primary);
  box-shadow: var(--theme-shadow);
}

.lab-composer__notice {
  background: rgba(79, 70, 229, 0.12);
  border-color: rgba(129, 140, 248, 0.24);
  color: var(--theme-text-primary);
}

.lab-composer__warning {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.24);
  color: var(--theme-text-primary);
}

.lab-composer__textarea-shell {
  background: var(--theme-card-strong-bg);
  border-color: var(--theme-border);
}

.lab-composer__locked {
  background: var(--theme-panel-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-secondary);
}

.lab-composer__asset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.lab-composer__asset-card {
  background: var(--theme-panel-bg);
  border-color: var(--theme-border);
}

.lab-composer__asset-meta {
  min-height: 52px;
}

.lab-composer__asset-hint {
  display: -webkit-box;
  min-height: 32px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.lab-composer__asset-upload-btn {
  display: inline-flex !important;
  margin-top: auto !important;
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

:deep(.lab-composer__asset-upload-btn .ant-btn-icon) {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

:deep(.lab-composer__asset-upload-btn span:not(.ant-btn-icon)) {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
}

:deep(.lab-composer__asset-upload-btn .anticon),
:deep(.lab-composer__asset-upload-btn svg) {
  display: block;
}

.lab-composer__asset-preview {
  display: flex;
  height: clamp(60px, 14vw, 96px);
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(14, 165, 233, 0.06)),
    var(--theme-card-strong-bg);
  color: var(--theme-text-secondary);
}

.lab-composer__asset-preview img,
.lab-composer__asset-preview video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.lab-composer__asset-preview--uploading img,
.lab-composer__asset-preview--uploading video {
  filter: grayscale(1);
}

.lab-composer__asset-uploading {
  background: rgba(15, 23, 42, 0.44);
}

.lab-composer__structured-prompt {
  display: block;
  background: var(--theme-panel-bg);
  border-color: var(--theme-border) !important;
}

:deep(.lab-composer__asset-uploading .ant-progress-inner) {
  background: rgba(255, 255, 255, 0.22);
}

.lab-composer__icon-btn {
  flex: 0 0 auto;
  border-color: var(--theme-border) !important;
  background: var(--theme-pill-bg) !important;
  color: var(--theme-text-primary) !important;
}

:deep(.lab-composer__textarea textarea.ant-input) {
  min-height: 62px !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--theme-text-primary) !important;
  padding: 0 !important;
  font-size: 15px;
  line-height: 1.75;
}

:deep(.lab-composer__textarea textarea.ant-input::placeholder) {
  color: var(--theme-input-placeholder) !important;
}

:deep(.lab-composer__textarea.ant-input-textarea-show-count::after),
:deep(.lab-composer__textarea .ant-input-data-count) {
  color: var(--theme-text-secondary) !important;
  -webkit-text-fill-color: var(--theme-text-secondary) !important;
  opacity: 0.9;
}

.lab-composer__ghost-btn {
  border-color: var(--theme-border) !important;
  background: var(--theme-pill-bg) !important;
  color: var(--theme-text-primary) !important;
}

.lab-composer__actions {
  display: grid !important;
  grid-template-columns: minmax(0, 1fr) auto;
  min-width: 0;
  width: 100%;
  align-items: center;
}

.lab-composer__actions-left {
  justify-self: start;
}

.lab-composer__actions-submit {
  justify-self: end;
}

.lab-composer__compact-btn {
  display: inline-flex !important;
  max-width: min(52vw, 180px);
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding-inline: 12px !important;
}

.lab-composer__icon-only-btn {
  display: inline-flex !important;
  width: 38px !important;
  min-width: 38px !important;
  height: 38px !important;
  align-items: center;
  justify-content: center;
  padding: 0 !important;
  flex: 0 0 auto;
}

:deep(.lab-composer__compact-btn .ant-btn-icon) {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

:deep(.lab-composer__compact-btn span:not(.ant-btn-icon)) {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
}

:deep(.lab-composer__compact-btn .anticon),
:deep(.lab-composer__compact-btn svg) {
  display: block;
}

.lab-composer__cost-pill {
  white-space: nowrap;
  background: var(--theme-pill-bg);
  border: 1px solid var(--theme-border);
  color: var(--theme-text-primary);
}

.lab-composer__ghost-btn:hover {
  border-color: var(--theme-border-strong) !important;
  color: var(--theme-text-primary) !important;
}

.lab-composer__submit-btn {
  display: inline-flex !important;
  align-items: center;
  justify-content: center;
  min-width: 44px !important;
  border: none !important;
  background: linear-gradient(135deg, #2563eb, #3b82f6) !important;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.22);
}

:deep(.lab-composer__drawer .ant-drawer-content),
:deep(.lab-composer__drawer .ant-drawer-header) {
  background: var(--theme-overlay-bg) !important;
  color: var(--theme-text-primary) !important;
}
</style>
