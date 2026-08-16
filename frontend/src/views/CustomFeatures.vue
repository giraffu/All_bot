<script setup lang="ts">
import {
  BranchesOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  LinkOutlined,
  PictureOutlined,
  RetweetOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'
import CharacterReferenceWorkbench from '@/components/lab/CharacterReferenceWorkbench.vue'
import LabAdvancedOptionsPanel from '@/components/lab/LabAdvancedOptionsPanel.vue'
import LabModeRail from '@/components/lab/LabModeRail.vue'
import LabPromptComposer from '@/components/lab/LabPromptComposer.vue'
import LtxT2VCharacterSelector from '@/components/lab/LtxT2VCharacterSelector.vue'
import { useLabWorkbench } from '@/composables/useLabWorkbench'

const { t } = useI18n()
const {
  unifiedModes,
  currentMode,
  currentModeId,
  prompt,
  audioPrompt,
  displayedReferences,
  isSubmitting,
  currentTask,
  isImageUrl,
  downloadResult,
  selectMode,
  beforeUpload,
  beforeUploadSlot,
  handleAssetVideoMetadata,
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
  promptPlaceholder,
  showStructuredPromptInput,
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
  selectedCharacterIds,
  useT2VReferences,
  environmentSource,
  selectedEnvironmentId,
  minimaxH3Mode,
  minimaxH3ResolutionPreset,
  minimaxH3AspectRatio,
  minimaxH3ReferenceDescriptions,
  minimaxH3AddonOptions,
  minimaxH3AddonNames,
  minimaxH3AddonItems,
  templateNotice,
  templateWarning,
  composerNotice,
  composerWarning,
  isTemplatePromptLocked,
  isTemplateEditSettingsLocked,
  isTemplateVideoSettingsLocked,
  currentTaskIsWan22VideoV2,
  wan22CurrentTaskCanExtend,
  wan22CurrentTaskCanStitch,
  currentTaskIsLtxVideo,
  ltxCurrentTaskCanExtend,
  ltxCurrentTaskCanStitch,
  wan22ChainLoading,
  wan22ChainStitching,
  ltxChainStitching,
  openWan22CurrentTaskEditor,
  openLtxCurrentTaskEditor,
  stitchCurrentWan22Chain,
  stitchCurrentLtxChain,
  isPromptOptimizerAvailable,
  canOptimizePrompt,
  canRestoreOriginalPrompt,
  isOptimizingPrompt,
  promptOptimizerStreamPreview,
  promptOptimizerFailedPartial,
  promptOptimizerRefundStatus,
  optimizePrompt,
  restoreOriginalPrompt,
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
      :class="currentModeId !== 'character_reference' && currentTask ? 'xl:grid-cols-[minmax(0,1.24fr)_minmax(360px,0.82fr)]' : ''"
    >
      <CharacterReferenceWorkbench
        v-if="currentModeId === 'character_reference'"
        class="min-w-0"
      />
      <template v-else>
      <LabPromptComposer
        :title="t(currentMode.titleKey)"
        :description="t(currentMode.descriptionKey)"
        :prompt-placeholder="promptPlaceholder"
        :prompt="prompt"
        :show-prompt-input="currentMode.supportsPromptInput !== false"
        :prompt-locked="isTemplatePromptLocked"
        :prompt-locked-hint="promptLockedHint"
        :show-structured-prompt-input="showStructuredPromptInput"
        :references="displayedReferences"
        :asset-upload-slots="assetUploadSlots"
        :reference-title="referenceTitle"
        :supports-upload="currentMode.supportsUpload && currentModeId !== 'ltx_t2v' && !(currentModeId === 'minimax_h3' && minimaxH3Mode === 't2v')"
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
        :notice="composerNotice || templateNotice"
        :warning="composerWarning || templateWarning"
        :show-prompt-optimizer="isPromptOptimizerAvailable"
        :optimize-prompt-disabled="!canOptimizePrompt"
        :optimize-prompt-loading="isOptimizingPrompt"
        :can-restore-original-prompt="canRestoreOriginalPrompt"
        :prompt-stream-preview="promptOptimizerStreamPreview"
        :prompt-failed-partial="promptOptimizerFailedPartial"
        :prompt-refund-status="promptOptimizerRefundStatus"
        @update:prompt="prompt = $event"
        @asset-video-metadata="handleAssetVideoMetadata"
        @remove-reference="handleRemoveReference"
        @remove-upload-slot="handleRemoveUploadSlot"
        @submit="handleSubmit"
        @optimize-prompt="optimizePrompt"
        @restore-original-prompt="restoreOriginalPrompt"
      >
        <template v-if="currentModeId === 'ltx_t2v'" #before-prompt>
          <div class="mb-3 space-y-3">
            <LtxT2VCharacterSelector
              v-model="selectedCharacterIds"
              v-model:enabled="useT2VReferences"
              v-model:environment-source="environmentSource"
              v-model:environment-id="selectedEnvironmentId"
              :can-upload-environment="canUploadReference"
              :before-upload-environment="beforeUpload"
            />
            <a-textarea
              v-model:value="audioPrompt"
              :maxlength="500"
              :auto-size="{ minRows: 1, maxRows: 3 }"
              :placeholder="t('characters.audio_prompt')"
            />
          </div>
        </template>
        <template v-if="currentModeId === 'minimax_h3'" #before-prompt>
          <div class="mb-4 space-y-3 rounded-2xl border p-3">
            <a-segmented
              v-model:value="minimaxH3Mode"
              block
              :options="[
                { label: t('lab.workbench.minimax_h3_modes.t2v'), value: 't2v' },
                { label: t('lab.workbench.minimax_h3_modes.i2v'), value: 'i2v' },
                { label: t('lab.workbench.minimax_h3_modes.flf2v'), value: 'flf2v' },
              ]"
            />
            <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <a-select v-model:value="duration" :options="[{value:'5',label:'5s'},{value:'10',label:'10s'},{value:'15',label:'15s'}]" />
              <a-select v-model:value="minimaxH3ResolutionPreset" :options="[
                { value: 'preview', label: t('lab.workbench.minimax_h3_resolution_presets.preview') },
                { value: 'small', label: t('lab.workbench.minimax_h3_resolution_presets.small') },
                { value: 'standard', label: t('lab.workbench.minimax_h3_resolution_presets.standard') },
                { value: 'hd', label: t('lab.workbench.minimax_h3_resolution_presets.hd') },
              ]" />
              <a-select v-if="minimaxH3Mode === 't2v'" v-model:value="minimaxH3AspectRatio" :options="['16:9','9:16','1:1','4:3','3:4'].map(value => ({value,label:value}))" />
              <div v-else class="flex min-h-8 items-center rounded-md border border-white/10 px-3 text-xs text-slate-400">
                {{ t('lab.workbench.minimax_h3_first_frame_ratio') }}
              </div>
            </div>
            <div class="space-y-2">
              <div class="text-xs font-medium text-slate-600 dark:text-slate-300">
                {{ t('lab.workbench.minimax_h3_addons') }}
              </div>
              <a-select
                v-model:value="minimaxH3AddonNames"
                mode="multiple"
                allow-clear
                class="w-full"
                :options="minimaxH3AddonOptions.map(option => ({
                  value: option.value,
                  label: t(option.labelKey),
                }))"
              />
              <div
                v-for="item in minimaxH3AddonItems"
                :key="item.name"
                class="minimax-h3-addon-strength grid grid-cols-[minmax(0,1fr)_8rem] items-center gap-3 rounded-lg border border-white/10 px-3 py-2"
              >
                <div class="truncate text-xs text-slate-600 dark:text-slate-300">
                  {{ t(minimaxH3AddonOptions.find(option => option.value === item.name)?.labelKey ?? item.name) }}
                </div>
                <a-input-number
                  v-model:value="item.strength"
                  :min="0.1"
                  :max="2"
                  :step="0.05"
                  :precision="2"
                  :addon-before="t('lab.workbench.minimax_h3_addon_strength')"
                />
              </div>
            </div>
          </div>
        </template>
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
            :is-video-resolution-locked="currentModeId === 'ltx_t2v' && selectedCharacterIds.length > 0"
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
          <template #success-actions="{ task }">
            <div
              v-if="currentTaskIsWan22VideoV2"
              class="lab-workbench__result-actions flex w-full flex-wrap items-center justify-center gap-2"
            >
              <a-button
                type="primary"
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                @click="downloadResult(task.resultUrl, task.title)"
              >
                <template #icon><DownloadOutlined /></template>
                {{ $t('template_apply.common.download_result') }}
              </a-button>
              <a-button
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                :disabled="!wan22CurrentTaskCanExtend"
                :loading="wan22ChainLoading"
                @click="openWan22CurrentTaskEditor('extend')"
              >
                <template #icon><BranchesOutlined /></template>
                {{ $t('lab.workbench.wan22_extend_generation') }}
              </a-button>
              <a-button
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                :loading="wan22ChainLoading"
                @click="openWan22CurrentTaskEditor('regenerate')"
              >
                <template #icon><RetweetOutlined /></template>
                {{ $t('lab.workbench.wan22_regenerate_generation') }}
              </a-button>
              <a-button
                v-if="wan22CurrentTaskCanStitch"
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                :loading="wan22ChainStitching"
                @click="stitchCurrentWan22Chain"
              >
                <template #icon><LinkOutlined /></template>
                {{ $t('lab.workbench.wan22_stitch_chain') }}
              </a-button>
            </div>
            <div
              v-else-if="currentTaskIsLtxVideo"
              class="lab-workbench__result-actions flex w-full flex-wrap items-center justify-center gap-2"
            >
              <a-button
                type="primary"
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                @click="downloadResult(task.resultUrl, task.title)"
              >
                <template #icon><DownloadOutlined /></template>
                {{ $t('template_apply.common.download_result') }}
              </a-button>
              <a-button
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                :disabled="!ltxCurrentTaskCanExtend"
                @click="openLtxCurrentTaskEditor"
              >
                <template #icon><BranchesOutlined /></template>
                {{ $t('lab.workbench.ltx_extend_generation') }}
              </a-button>
              <a-button
                v-if="ltxCurrentTaskCanStitch"
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                :loading="ltxChainStitching"
                @click="stitchCurrentLtxChain"
              >
                <template #icon><LinkOutlined /></template>
                {{ $t('lab.workbench.ltx_stitch_chain') }}
              </a-button>
              <a-button
                size="large"
                class="min-w-[94px] max-w-[112px] flex-1 rounded-xl !px-2 whitespace-nowrap"
                @click="resetAfterResult"
              >
                {{ $t('lab.workbench.continue_generation') }}
              </a-button>
            </div>
            <div v-else class="flex gap-4">
              <a-button
                type="primary"
                size="large"
                class="bg-blue-600 rounded-xl"
                @click="downloadResult(task.resultUrl, task.title)"
              >
                <template #icon>
                  <DownloadOutlined />
                </template>
                {{ $t('template_apply.common.download_result') }}
              </a-button>
              <a-button size="large" class="rounded-xl" @click="resetAfterResult">
                {{ $t('lab.workbench.continue_generation') }}
              </a-button>
            </div>
          </template>
          <template #failed-icon>
            <close-circle-outlined class="text-5xl text-red-500 mb-4" />
          </template>
        </TaskResultPreviewPanel>
      </section>
      </template>
    </div>

    <div class="lab-workbench__mode-dock mx-auto w-full max-w-4xl">
      <LabModeRail
        :modes="unifiedModes"
        :active-mode-id="currentModeId"
        :resolve-label="t"
        @select="selectMode"
      />
    </div>
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
