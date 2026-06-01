<script setup lang="ts">
import {
  CloseCircleOutlined,
  DownloadOutlined,
  PictureOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'
import LabAdvancedOptionsPanel from '@/components/lab/LabAdvancedOptionsPanel.vue'
import LabLegacyModeGrid from '@/components/lab/LabLegacyModeGrid.vue'
import LabModeRail from '@/components/lab/LabModeRail.vue'
import LabPromptComposer from '@/components/lab/LabPromptComposer.vue'
import { useLabWorkbench } from '@/composables/useLabWorkbench'

const { t } = useI18n()
const {
  unifiedModes,
  legacyModes,
  currentMode,
  currentModeId,
  prompt,
  uploadedReferences,
  uploadProgress,
  uploading,
  isSubmitting,
  currentTask,
  isImageUrl,
  downloadResult,
  selectMode,
  openLegacyMode,
  beforeUpload,
  handleRemoveReference,
  handleSubmit,
  resetAfterResult,
  cost,
  costHint,
  canSubmit,
  hasAdvancedOptions,
  referenceTitle,
  uploadButtonLabel,
  editLoraOptions,
  selectedEditLora,
  customEditLoraStrength,
  videoLoraOptions,
  selectedVideoLora,
  videoResolutionOptions,
  resolution,
  videoDurationOptions,
  duration,
  templateNotice,
  templateWarning,
  isTemplatePromptLocked,
  isTemplateEditSettingsLocked,
  isTemplateVideoSettingsLocked,
} = useLabWorkbench()

const isVideoMode = computed(() => currentMode.value.id === 'custom_video')

const promptLockedHint = computed(() => (
  currentMode.value.id === 'custom_video'
    ? t('template_apply.common.prompt_locked_video_hint')
    : t('template_apply.common.prompt_locked_image_hint')
))
</script>

<template>
  <div class="lab-workbench mx-auto flex w-full max-w-7xl flex-col gap-6 px-2 py-4 sm:px-6">
    <section class="lab-workbench__intro text-center">
      <h2 class="text-3xl font-semibold tracking-tight sm:text-4xl">
        {{ $t('lab.title') }}
      </h2>
      <p class="mx-auto mt-3 max-w-2xl text-sm leading-6 opacity-70 sm:text-base">
        {{ $t('lab.workbench.hero_desc') }}
      </p>

      <div class="mt-5">
        <LabModeRail
          :modes="unifiedModes"
          :active-mode-id="currentModeId"
          :resolve-label="t"
          @select="selectMode"
        />
      </div>
    </section>

    <div
      class="grid grid-cols-1 gap-5"
      :class="currentTask ? 'xl:grid-cols-[minmax(0,1.24fr)_minmax(360px,0.82fr)]' : ''"
    >
      <LabPromptComposer
        :title="t(currentMode.titleKey)"
        :description="t(currentMode.descriptionKey)"
        :mode-kind-label="t(currentMode.kindKey)"
        :prompt="prompt"
        :prompt-placeholder="t(currentMode.promptPlaceholderKey)"
        :prompt-locked="isTemplatePromptLocked"
        :prompt-locked-hint="promptLockedHint"
        :references="uploadedReferences"
        :reference-title="referenceTitle"
        :supports-upload="currentMode.supportsUpload"
        :upload-button-label="uploadButtonLabel"
        :before-upload="beforeUpload"
        :uploading="uploading"
        :upload-progress="uploadProgress"
        :submit-text="t(currentMode.submitLabelKey)"
        :submit-disabled="!canSubmit"
        :submit-loading="isSubmitting"
        :cost="cost"
        :cost-hint="costHint"
        :has-advanced-options="hasAdvancedOptions"
        :notice="templateNotice"
        :warning="templateWarning"
        @update:prompt="prompt = $event"
        @remove-reference="handleRemoveReference"
        @submit="handleSubmit"
      >
        <template #advanced-panel="{ close }">
          <LabAdvancedOptionsPanel
            :mode="currentMode"
            :edit-lora-options="editLoraOptions"
            :selected-edit-lora="selectedEditLora"
            :edit-lora-strength="customEditLoraStrength"
            :video-lora-options="videoLoraOptions"
            :selected-video-lora="selectedVideoLora"
            :resolution-options="videoResolutionOptions"
            :selected-resolution="resolution"
            :duration-options="videoDurationOptions"
            :selected-duration="duration"
            :is-template-edit-settings-locked="isTemplateEditSettingsLocked"
            :is-template-video-settings-locked="isTemplateVideoSettingsLocked"
            @update:selected-edit-lora="selectedEditLora = $event"
            @update:edit-lora-strength="customEditLoraStrength = $event"
            @update:selected-video-lora="selectedVideoLora = $event"
            @update:selected-resolution="resolution = $event"
            @update:selected-duration="duration = $event"
          />
          <div class="mt-4 flex justify-end">
            <a-button class="rounded-full" @click="close()">
              {{ $t('lab.workbench.close_advanced') }}
            </a-button>
          </div>
        </template>
      </LabPromptComposer>

      <section v-if="currentTask" class="lab-workbench__result rounded-[24px] border">
        <TaskResultPreviewPanel
          :current-task="currentTask"
          :is-image-url="isImageUrl"
          :result-title="$t('template_apply.common.result_title')"
          :empty-title="$t('lab.workbench.result_empty_title')"
          :empty-description="$t('lab.workbench.result_empty_desc')"
          @download="downloadResult"
          @reset="resetAfterResult"
        >
          <template #empty-icon>
            <component :is="isVideoMode ? VideoCameraOutlined : PictureOutlined" class="text-6xl mb-4" />
          </template>
          <template #download-icon>
            <download-outlined />
          </template>
          <template #failed-icon>
            <close-circle-outlined class="text-5xl text-red-500 mb-4" />
          </template>
        </TaskResultPreviewPanel>
      </section>
    </div>

    <LabLegacyModeGrid
      :modes="legacyModes"
      :resolve-label="t"
      @open="openLegacyMode"
    />
  </div>
</template>

<style scoped>
.lab-workbench {
  color: var(--theme-text-primary);
}

.lab-workbench__intro {
  color: var(--theme-text-primary);
}

.lab-workbench__result {
  background: var(--theme-card-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-primary);
  box-shadow: var(--theme-shadow);
}
</style>
