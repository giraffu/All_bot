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
  displayedReferences,
  isSubmitting,
  currentTask,
  isImageUrl,
  downloadResult,
  selectMode,
  openLegacyMode,
  beforeUpload,
  beforeUploadSlot,
  handleRemoveReference,
  handleRemoveUploadSlot,
  handleSubmit,
  resetAfterResult,
  cost,
  costHint,
  canSubmit,
  hasAdvancedOptions,
  assetUploadSlots,
  canUploadReference,
  referenceTitle,
  uploadButtonLabel,
  editLoraOptions,
  selectedEditLora,
  customEditLoraStrength,
  videoLoraOptions,
  selectedVideoLora,
  ltxLoraOptions,
  selectedLtxLoraNames,
  ltxLoraItems,
  syncLtxLoraItems,
  removeLtxLoraItem,
  updateLtxLoraStrength,
  negativePrompt,
  wan22ResolutionOptions,
  wan22ResolutionPreset,
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

const isVideoMode = computed(() => currentMode.value.kindKey === 'lab.workbench.mode_kinds.video')

const promptLockedHint = computed(() => (
  currentMode.value.id === 'custom_video'
    ? t('template_apply.common.prompt_locked_video_hint')
    : t('template_apply.common.prompt_locked_image_hint')
))
</script>

<template>
  <div class="lab-workbench mx-auto flex w-full max-w-7xl flex-col gap-4 px-2 py-3 sm:px-6">
    <div
      class="grid grid-cols-1 gap-4"
      :class="currentTask ? 'xl:grid-cols-[minmax(0,1.24fr)_minmax(360px,0.82fr)]' : ''"
    >
      <LabPromptComposer
        :title="t(currentMode.titleKey)"
        :description="t(currentMode.descriptionKey)"
        :prompt="prompt"
        :prompt-locked="isTemplatePromptLocked"
        :prompt-locked-hint="promptLockedHint"
        :references="displayedReferences"
        :asset-upload-slots="assetUploadSlots"
        :reference-title="referenceTitle"
        :supports-upload="currentMode.supportsUpload"
        :can-upload-reference="canUploadReference"
        :upload-button-label="uploadButtonLabel"
        :before-upload="beforeUpload"
        :before-upload-slot="beforeUploadSlot"
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
        @remove-upload-slot="handleRemoveUploadSlot"
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
            :ltx-lora-options="ltxLoraOptions"
            :selected-ltx-lora-names="selectedLtxLoraNames"
            :ltx-lora-items="ltxLoraItems"
            :resolution-options="videoResolutionOptions"
            :selected-resolution="resolution"
            :duration-options="videoDurationOptions"
            :selected-duration="duration"
            :negative-prompt="negativePrompt"
            :wan22-resolution-options="wan22ResolutionOptions"
            :selected-wan22-resolution-preset="wan22ResolutionPreset"
            :is-template-edit-settings-locked="isTemplateEditSettingsLocked"
            :is-template-video-settings-locked="isTemplateVideoSettingsLocked"
            @update:selected-edit-lora="selectedEditLora = $event"
            @update:edit-lora-strength="customEditLoraStrength = $event"
            @update:selected-video-lora="selectedVideoLora = $event"
            @update:selected-ltx-lora-names="syncLtxLoraItems"
            @update:ltx-lora-strength="updateLtxLoraStrength"
            @remove-ltx-lora-item="removeLtxLoraItem"
            @update:selected-resolution="resolution = $event"
            @update:selected-duration="duration = $event"
            @update:negative-prompt="negativePrompt = $event"
            @update:selected-wan22-resolution-preset="wan22ResolutionPreset = $event as any"
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

    <div class="lab-workbench__mode-dock mx-auto w-full max-w-4xl">
      <LabModeRail
        :modes="unifiedModes"
        :active-mode-id="currentModeId"
        :resolve-label="t"
        @select="selectMode"
      />
    </div>

    <LabLegacyModeGrid
      v-if="legacyModes.length > 0"
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

.lab-workbench__result {
  background: var(--theme-card-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-primary);
  box-shadow: var(--theme-shadow);
}

.lab-workbench__mode-dock {
  margin-top: -6px;
}
</style>
