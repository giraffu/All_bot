<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CloseCircleOutlined,
  InboxOutlined,
  VideoCameraOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useTemplateApplyUpload } from '@/composables/useTemplateApplyUpload'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskSubmission } from '@/composables/useTaskSubmission'
import {
  getScail2VideoDurationOptionsForMotionVideo,
  getScail2VideoCost
} from '@/features/generation/labModeConfig'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { TemplateApplyContext } from '@/types/templateApply'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'
import TemplateApplyResultSection from '@/components/template-apply/TemplateApplyResultSection.vue'

interface UploadedAsset {
  key: string | null
  preview: string | null
}

const props = defineProps<{
  sessionId: string
  context: TemplateApplyContext
}>()

warnIfPropsExceedBudget('TemplateScail2VideoPanel', Object.keys(props).length)

const { t } = useI18n()
const templateApplyStore = useTemplateApplyStore()
const { isSubmitting, submitTask } = useTaskSubmission()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const sessionIdRef = computed(() => props.sessionId)
const { uploadFile, uploadingSlots, progressBySlot, hasPendingUploads } = useTemplateApplyUpload(sessionIdRef)

const referenceAsset = ref<UploadedAsset>({ key: null, preview: null })
const prompt = ref('')
const negativePrompt = ref('')
const duration = ref('5')
const motionVideoDurationSeconds = ref<number | null>(null)
const preferredInitialDuration = ref('5')
const hasUserSelectedDuration = ref(false)

const initialReferenceKey = ref<string | null>(null)
const initialPrompt = ref('')
const initialNegativePrompt = ref('')
const initialDuration = ref('5')

const taskType = computed(() => {
  const rawTaskType = props.context.taskType ?? 'scail2_action_transfer'
  return rawTaskType === 'scail2_action_transfer_long'
    ? 'scail2_action_transfer'
    : rawTaskType
})
const scail2TitleKeyByTaskType: Record<string, string> = {
  scail2_action_transfer: 'lab.cards.scail2_action_transfer_title',
  scail2_video_replacement: 'lab.cards.scail2_video_replacement_title',
  scail2_face_swap_v2: 'lab.cards.scail2_face_swap_v2_title',
}
const scail2PromptKeyByTaskType: Record<string, string> = {
  scail2_action_transfer: 'lab.workbench.prompt_placeholders.scail2_action_transfer',
  scail2_video_replacement: 'lab.workbench.prompt_placeholders.scail2_video_replacement',
  scail2_face_swap_v2: 'lab.workbench.prompt_placeholders.scail2_face_swap_v2',
}
const taskTitle = computed(() => t(
  scail2TitleKeyByTaskType[taskType.value] ?? scail2TitleKeyByTaskType.scail2_action_transfer
))
const promptPlaceholder = computed(() => t(
  scail2PromptKeyByTaskType[taskType.value] ?? scail2PromptKeyByTaskType.scail2_action_transfer
))
const motionVideoKey = computed(() => props.context.inputFile ?? props.context.inputFiles?.[0] ?? null)
const motionVideoUrl = computed(() => props.context.inputFileUrl ?? props.context.inputFileUrls?.[0] ?? null)
const availableDurationOptions = computed(() => (
  getScail2VideoDurationOptionsForMotionVideo(motionVideoDurationSeconds.value, taskType.value)
))
const taskCost = computed(() => getScail2VideoCost(duration.value, taskType.value))

const revokePreview = (preview: string | null) => {
  if (preview?.startsWith('blob:')) {
    URL.revokeObjectURL(preview)
  }
}

watch(
  () => hasPendingUploads.value,
  (pending) => {
    templateApplyStore.setPendingUploads(pending)
  },
  { immediate: true }
)

watch(
  [referenceAsset, prompt, negativePrompt, duration],
  () => {
    const isDirty =
      referenceAsset.value.key !== initialReferenceKey.value
      || prompt.value.trim() !== initialPrompt.value
      || negativePrompt.value.trim() !== initialNegativePrompt.value
      || duration.value !== initialDuration.value
    templateApplyStore.setDirtyState(isDirty)
  },
  { immediate: true, deep: true }
)

const cleanup = async () => {
  revokePreview(referenceAsset.value.preview)
  referenceAsset.value = { key: null, preview: null }
  templateApplyStore.setDirtyState(false)
  templateApplyStore.setPendingUploads(false)
  setSubmittedTaskId(null)
}

const normalizeDuration = (value: number | string | null | undefined) => {
  const normalized = String(value ?? '5').replace(/s$/i, '')
  const allowedDurations = taskType.value === 'scail2_action_transfer'
    ? ['5', '8', '10', '15', '20']
    : ['5', '8']
  return allowedDurations.includes(normalized) ? normalized : '5'
}

const coerceDurationToAvailableOption = (value: number | string | null | undefined) => {
  const normalized = normalizeDuration(value)
  return availableDurationOptions.value.some(option => option.value === normalized)
    ? normalized
    : '5'
}

const initializeFromContext = () => {
  prompt.value = props.context.prompt ?? ''
  negativePrompt.value = props.context.negativePrompt ?? ''
  motionVideoDurationSeconds.value = null
  hasUserSelectedDuration.value = false
  preferredInitialDuration.value = normalizeDuration(props.context.requestedDuration ?? props.context.duration)
  duration.value = coerceDurationToAvailableOption(preferredInitialDuration.value)

  initialReferenceKey.value = null
  initialPrompt.value = prompt.value.trim()
  initialNegativePrompt.value = negativePrompt.value.trim()
  initialDuration.value = duration.value
}

watch(
  availableDurationOptions,
  () => {
    const targetDuration = hasUserSelectedDuration.value
      ? duration.value
      : preferredInitialDuration.value
    const nextDuration = coerceDurationToAvailableOption(targetDuration)
    duration.value = nextDuration
    if (!hasUserSelectedDuration.value) {
      initialDuration.value = nextDuration
    }
  },
  { immediate: true }
)

const normalizeVideoDuration = (value: number) => (
  Number.isFinite(value) && value > 0 ? value : null
)

const handleMotionVideoLoadedMetadata = (event: Event) => {
  const video = event.currentTarget as HTMLVideoElement | null
  motionVideoDurationSeconds.value = normalizeVideoDuration(video?.duration ?? Number.NaN)
}

const handleDurationChange = (value: string | number | null | undefined) => {
  hasUserSelectedDuration.value = true
  duration.value = coerceDurationToAvailableOption(value)
}

const beforeUploadReference = async (rawFile: File | { originFileObj?: File }) => {
  const file = rawFile instanceof File ? rawFile : rawFile.originFileObj
  if (!(file instanceof File)) {
    message.error(t('template_apply.image_prompt.upload_read_failed'))
    return false
  }

  const { objectKey } = await uploadFile(file, { slot: 'reference_image' })
  if (!objectKey) {
    return false
  }

  revokePreview(referenceAsset.value.preview)
  referenceAsset.value = {
    key: objectKey,
    preview: URL.createObjectURL(file)
  }
  return false
}

const handleRemoveReference = () => {
  revokePreview(referenceAsset.value.preview)
  referenceAsset.value = { key: null, preview: null }
}

const handleGenerate = async () => {
  if (!referenceAsset.value.key) {
    message.warning(t('template_apply.scail2_video.upload_reference_first'))
    return
  }
  if (!motionVideoKey.value) {
    message.warning(t('template_apply.scail2_video.motion_video_missing'))
    return
  }

  const payload = buildGenerationTaskPayload({
    taskType: taskType.value,
    images: [referenceAsset.value.key, motionVideoKey.value],
    duration: Number(duration.value),
    prompt: prompt.value,
    negativePrompt: negativePrompt.value,
    promptTarget: 'inputs',
    isTemplate: true,
    sourcePostId: props.context.sourcePostId,
  })

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
    await templateApplyStore.closeAfterSubmission(props.sessionId)
  }
}

onMounted(() => {
  setSubmittedTaskId(null)
  initializeFromContext()
  templateApplyStore.setDirtyState(false)
  templateApplyStore.registerPanelController({
    sessionId: props.sessionId,
    cleanup
  })
})

onBeforeUnmount(() => {
  cleanup()
  templateApplyStore.registerPanelController(null)
})
</script>

<template>
  <div class="template-panel flex flex-col lg:flex-row gap-6 min-h-[70vh]">
    <section class="w-full lg:w-[52%] flex flex-col bg-slate-900/70 rounded-2xl border border-slate-700/70 overflow-hidden">
      <div class="p-6 overflow-y-auto flex-1">
        <h2 class="text-2xl font-bold text-slate-100 mb-2">{{ taskTitle }}</h2>
        <p class="text-slate-400 text-sm mb-6">{{ t('template_apply.scail2_video.current_page_desc') }}</p>

        <div class="mb-6 rounded-xl border border-indigo-500/40 bg-indigo-500/15 px-4 py-3 text-sm text-slate-200">
          {{ t('template_apply.scail2_video.template_notice') }}
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-[0.95fr_1.05fr] gap-4 min-w-0">
          <div class="scail2-template-card rounded-xl border border-slate-700 bg-slate-800/70 p-4">
            <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('lab.workbench.upload_slots.reference_image') }}</div>
            <div v-if="referenceAsset.preview" class="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950/80">
              <img :src="referenceAsset.preview" class="h-56 w-full object-contain bg-slate-950/80" />
              <button
                class="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white"
                @click="handleRemoveReference"
              >
                <CloseCircleOutlined />
              </button>
            </div>
            <a-upload-dragger
              v-else
              :before-upload="beforeUploadReference"
              :show-upload-list="false"
              accept="image/png,image/jpeg,image/webp"
              class="template-upload w-full min-w-0 overflow-hidden"
            >
              <p class="ant-upload-drag-icon">
                <InboxOutlined class="text-cyan-400" />
              </p>
              <p class="text-slate-200">{{ t('template_apply.common.upload_reference_image') }}</p>
              <p class="text-slate-400 text-xs">{{ t('lab.workbench.upload_slot_hints.reference_image') }}</p>
            </a-upload-dragger>
          </div>

          <div class="scail2-template-card rounded-xl border border-slate-700 bg-slate-800/70 p-4">
            <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('lab.workbench.upload_slots.motion_video') }}</div>
            <div class="rounded-xl overflow-hidden border border-slate-700 bg-slate-950/80">
              <video
                v-if="motionVideoUrl"
                :src="motionVideoUrl"
                controls
                class="h-56 w-full object-contain bg-slate-950/80"
                preload="metadata"
                @loadedmetadata="handleMotionVideoLoadedMetadata"
                @durationchange="handleMotionVideoLoadedMetadata"
              />
              <div
                v-else
                class="h-56 w-full flex items-center justify-center px-4 text-center text-sm text-slate-400 bg-slate-950/80"
              >
                {{ motionVideoKey || t('template_apply.scail2_video.motion_video_missing') }}
              </div>
            </div>
            <p class="mt-3 text-xs text-slate-400">{{ t('template_apply.scail2_video.motion_video_locked_hint') }}</p>
          </div>
        </div>

        <div class="mt-6 rounded-xl border border-slate-700 bg-slate-800/70 p-4 space-y-4">
          <div>
            <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.prompt') }}</div>
            <a-textarea
              v-model:value="prompt"
              :rows="4"
              :placeholder="promptPlaceholder"
            />
          </div>
          <div>
            <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('lab.workbench.negative_prompt') }}</div>
            <a-textarea
              v-model:value="negativePrompt"
              :rows="3"
              :placeholder="t('lab.workbench.negative_prompt_placeholder')"
            />
          </div>
          <div>
            <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.duration') }}</div>
            <a-radio-group
              :value="duration"
              button-style="solid"
              class="w-full grid grid-cols-2 gap-2 max-w-[240px]"
              @update:value="handleDurationChange"
            >
              <a-radio-button
                v-for="option in availableDurationOptions"
                :key="option.value"
                :value="option.value"
                class="w-full text-center"
              >
                {{ option.label }}
              </a-radio-button>
            </a-radio-group>
          </div>
        </div>

        <div
          v-if="Object.values(uploadingSlots).some(Boolean)"
          class="mt-4 space-y-2"
        >
          <div
            v-for="(progress, slot) in progressBySlot"
            :key="slot"
            v-show="uploadingSlots[slot]"
            class="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-2"
          >
            <div class="flex items-center justify-between text-xs text-slate-300 mb-1">
              <span>{{ slot }}</span>
              <span>{{ progress }}%</span>
            </div>
            <a-progress :percent="progress" size="small" />
          </div>
        </div>
      </div>

      <div class="border-t border-slate-700 px-6 py-4 flex items-center justify-between gap-4">
        <div class="text-sm text-slate-300">
          {{ t('template_apply.common.estimated_cost') }}
          <span class="text-cyan-300 font-semibold">{{ taskCost }}</span>
          {{ t('template_apply.common.credits_unit') }}
        </div>
        <a-button
          type="primary"
          size="large"
          :loading="isSubmitting"
          :disabled="hasPendingUploads || !referenceAsset.key || !motionVideoKey"
          @click="handleGenerate"
        >
          <template #icon>
            <VideoCameraOutlined />
          </template>
          {{ t('template_apply.common.generate_video') }}
        </a-button>
      </div>
    </section>

    <TemplateApplyResultSection
      :current-task="currentTask"
      :is-image-url="isImageUrl"
      @download="downloadResult"
    />
  </div>
</template>

<style scoped>
.scail2-template-card {
  min-width: 0;
  overflow: hidden;
}

.template-upload {
  display: block;
  width: 100%;
  min-width: 0;
}

.template-upload :deep(.ant-upload) {
  width: 100%;
  min-width: 0;
}

.template-upload :deep(.ant-upload.ant-upload-drag) {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.75);
  border-color: rgba(71, 85, 105, 0.9);
}

.template-upload :deep(.ant-upload.ant-upload-drag .ant-upload) {
  box-sizing: border-box;
  display: flex;
  padding: 0;
}

.template-upload :deep(.ant-upload.ant-upload-drag .ant-upload-btn) {
  width: 100%;
  min-width: 0;
}

.template-upload :deep(.ant-upload-drag-container) {
  box-sizing: border-box;
  display: flex;
  min-height: 14rem;
  width: 100%;
  min-width: 0;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
  text-align: center;
}

.template-upload :deep(.ant-upload.ant-upload-drag:hover) {
  border-color: rgba(34, 211, 238, 0.8);
}

:deep(.ant-radio-button-wrapper) {
  background: rgba(15, 23, 42, 0.6);
  color: #cbd5e1;
  border-color: rgba(71, 85, 105, 0.9);
}

:deep(.ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled)) {
  background: rgba(34, 211, 238, 0.2);
  color: #67e8f9;
  border-color: rgba(34, 211, 238, 0.8);
}
</style>
