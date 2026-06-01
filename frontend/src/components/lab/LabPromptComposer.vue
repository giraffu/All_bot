<script setup lang="ts">
import { ArrowUpOutlined, LockOutlined, MoreOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import LabReferenceTray from '@/components/lab/LabReferenceTray.vue'
import { useViewport } from '@/composables/useViewport'

interface UploadedReferenceItem {
  key: string
  preview: string
  name: string
}

const props = defineProps<{
  title: string
  description: string
  modeKindLabel: string
  prompt: string
  promptPlaceholder: string
  promptLocked: boolean
  promptLockedHint?: string
  references: UploadedReferenceItem[]
  referenceTitle: string
  supportsUpload: boolean
  uploadButtonLabel: string
  beforeUpload: (file: File) => boolean | Promise<boolean>
  uploading: boolean
  uploadProgress: number
  submitText: string
  submitDisabled: boolean
  submitLoading: boolean
  cost: number
  costHint?: string
  hasAdvancedOptions: boolean
  notice?: string
  warning?: string
}>()

const emit = defineEmits<{
  'update:prompt': [value: string]
  submit: []
  removeReference: [index: number]
}>()

const { t } = useI18n()
const { isMobile } = useViewport()
const advancedVisible = ref(false)

const canShowAdvancedAsPopover = computed(() => !isMobile.value)

const closeAdvanced = () => {
  advancedVisible.value = false
}
</script>

<template>
  <section class="lab-composer mx-auto w-full max-w-4xl rounded-[24px] border p-3 shadow-sm sm:p-4">
    <div class="mb-3 flex items-start justify-between gap-4 px-1 sm:px-2">
      <div class="min-w-0">
        <div class="text-lg font-semibold tracking-tight sm:text-xl">{{ title }}</div>
        <p class="mt-1 max-w-2xl text-sm leading-6 opacity-70">
          {{ description }}
        </p>
      </div>
      <div class="lab-composer__badge hidden rounded-full px-3 py-1 text-xs font-medium sm:block">
        {{ t('lab.workbench.ready_badge') }}
      </div>
    </div>

    <div v-if="notice" class="lab-composer__notice mb-4 rounded-2xl border px-4 py-3 text-sm">
      {{ notice }}
    </div>

    <div v-if="warning" class="lab-composer__warning mb-4 rounded-2xl border px-4 py-3 text-sm">
      {{ warning }}
    </div>

    <LabReferenceTray
      v-if="references.length > 0"
      :title="referenceTitle"
      :items="references"
      class="mb-4"
      @remove="emit('removeReference', $event)"
    />

    <div class="lab-composer__textarea-shell rounded-[22px] border p-4 sm:p-5">
      <div v-if="promptLocked" class="lab-composer__locked flex min-h-[160px] flex-col items-center justify-center rounded-[18px] border px-6 py-8 text-center">
        <LockOutlined class="mb-4 text-2xl" />
        <div class="text-base font-semibold">{{ t('template_apply.common.prompt_locked_title') }}</div>
        <div class="mt-2 max-w-md text-sm opacity-80">
          {{ promptLockedHint || t('template_apply.common.prompt_locked_image_hint') }}
        </div>
      </div>

      <a-textarea
        v-else
        :value="prompt"
        :rows="5"
        :maxlength="512"
        show-count
        class="lab-composer__textarea"
        :placeholder="promptPlaceholder"
        @update:value="emit('update:prompt', String($event))"
      />

      <div v-if="uploading" class="mt-4">
        <div class="mb-2 text-xs opacity-75">{{ t('lab.workbench.uploading') }}</div>
        <a-progress :percent="uploadProgress" status="active" stroke-color="#3b82f6" size="small" />
      </div>

      <div class="mt-4 flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex flex-wrap items-center gap-2">
          <div class="lab-composer__mode-chip rounded-full px-3 py-1.5 text-sm font-medium">
            {{ modeKindLabel }}
          </div>

          <a-upload
            v-if="supportsUpload"
            accept="image/png,image/jpeg,image/webp"
            :show-upload-list="false"
            :before-upload="beforeUpload"
          >
            <a-button class="lab-composer__ghost-btn rounded-full">
              <template #icon>
                <PlusOutlined />
              </template>
              {{ uploadButtonLabel }}
            </a-button>
          </a-upload>

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

            <a-button class="lab-composer__ghost-btn rounded-full">
              <template #icon>
                <MoreOutlined />
              </template>
              {{ t('lab.workbench.more_settings') }}
            </a-button>
          </a-popover>

          <a-button
            v-else-if="hasAdvancedOptions"
            class="lab-composer__ghost-btn rounded-full"
            @click="advancedVisible = true"
          >
            <template #icon>
              <MoreOutlined />
            </template>
            {{ t('lab.workbench.more_settings') }}
          </a-button>
        </div>

        <div class="flex items-center justify-between gap-3 sm:justify-end">
          <div class="min-w-0 text-right sm:text-left">
            <div class="text-xs opacity-70">{{ t('lab.workbench.cost_label') }}</div>
            <div class="mt-1 text-lg font-semibold">
              {{ cost }}
              <span class="ml-1 text-sm opacity-80">{{ t('app.credits') }}</span>
            </div>
            <div v-if="costHint" class="mt-1 text-xs opacity-70">
              {{ costHint }}
            </div>
          </div>

          <a-button
            type="primary"
            size="large"
            class="lab-composer__submit-btn h-12 rounded-full px-5"
            :disabled="submitDisabled"
            :loading="submitLoading"
            @click="emit('submit')"
          >
            <template #icon>
              <ArrowUpOutlined />
            </template>
            {{ submitText }}
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

.lab-composer__badge {
  background: rgba(59, 130, 246, 0.12);
  border: 1px solid rgba(59, 130, 246, 0.18);
  color: #38bdf8;
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

:deep(.lab-composer__textarea textarea.ant-input) {
  min-height: 160px;
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

.lab-composer__ghost-btn {
  border-color: var(--theme-border) !important;
  background: var(--theme-pill-bg) !important;
  color: var(--theme-text-primary) !important;
}

.lab-composer__mode-chip {
  background: var(--theme-pill-bg);
  border: 1px solid var(--theme-border);
  color: var(--theme-text-primary);
}

.lab-composer__ghost-btn:hover {
  border-color: var(--theme-border-strong) !important;
  color: var(--theme-text-primary) !important;
}

.lab-composer__submit-btn {
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
