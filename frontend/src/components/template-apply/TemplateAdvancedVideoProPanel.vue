<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useTemplateApplyUpload } from '@/composables/useTemplateApplyUpload'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import { MINIMAX_H3_ADDON_OPTIONS } from '@/features/generation/labModeConfig'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { TemplateApplyContext } from '@/types/templateApply'
import {
  areFrameAspectRatiosCompatible,
  getMinimaxH3TemplateCost,
  readImageDimensions,
  type ImageDimensions,
} from '@/utils/minimaxH3Template'
import TemplateApplyActionFooter from '@/components/template-apply/TemplateApplyActionFooter.vue'
import TemplateApplyResultSection from '@/components/template-apply/TemplateApplyResultSection.vue'
import TemplateApplyUploadSection from '@/components/template-apply/TemplateApplyUploadSection.vue'

interface UploadedFrame {
  objectKey: string
  preview: string
  dimensions: ImageDimensions
}

const props = defineProps<{
  sessionId: string
  context: TemplateApplyContext
}>()

const { t } = useI18n()
const templateApplyStore = useTemplateApplyStore()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const sessionIdRef = computed(() => props.sessionId)
const { uploadFile, uploadingSlots, progressBySlot, hasPendingUploads } = useTemplateApplyUpload(sessionIdRef)

const isFirstLastFrame = computed(() => props.context.rawTaskType === 'minimax_h3_flf2v')
const requiredImageCount = computed(() => isFirstLastFrame.value ? 2 : 1)
const firstFrame = ref<UploadedFrame | null>(null)
const lastFrame = ref<UploadedFrame | null>(null)
const lockedPrompt = computed(() => props.context.prompt || '')
const lockedDuration = computed(() => props.context.requestedDuration || 5)
const lockedResolution = computed(() => props.context.resolutionPreset || 'preview')
const lockedAspectRatio = computed(() => props.context.aspectRatio || 'source')
const lockedLoraItems = computed(() => props.context.loraItems)
const taskCost = computed(() => getMinimaxH3TemplateCost(lockedResolution.value, lockedDuration.value))
const addonLabels = computed(() => lockedLoraItems.value.map((item) => {
  const option = MINIMAX_H3_ADDON_OPTIONS.find(candidate => candidate.value === item.name)
  return `${option ? t(option.labelKey) : item.name} × ${item.strength}`
}))

watch(
  () => hasPendingUploads.value,
  pending => templateApplyStore.setPendingUploads(pending),
  { immediate: true },
)
watch(
  [firstFrame, lastFrame],
  () => templateApplyStore.setDirtyState(Boolean(firstFrame.value || lastFrame.value)),
  { immediate: true },
)

const revokeFrame = (frame: UploadedFrame | null) => {
  if (frame?.preview.startsWith('blob:')) URL.revokeObjectURL(frame.preview)
}

const setFrame = async (file: File, slot: 'first_frame' | 'last_frame') => {
  let dimensions: ImageDimensions
  try {
    dimensions = await readImageDimensions(file)
  } catch {
    message.error(t('template_apply.image_prompt.upload_read_failed'))
    return false
  }
  const { objectKey } = await uploadFile(file, { slot })
  if (!objectKey) return false
  const frame = { objectKey, preview: URL.createObjectURL(file), dimensions }
  if (slot === 'first_frame') {
    revokeFrame(firstFrame.value)
    firstFrame.value = frame
  } else {
    revokeFrame(lastFrame.value)
    lastFrame.value = frame
  }
  return false
}

const beforeUploadFirst = async (raw: File | { originFileObj?: File }) => {
  const file = raw instanceof File ? raw : raw.originFileObj
  if (!(file instanceof File)) return false
  return setFrame(file, 'first_frame')
}
const beforeUploadLast = async (raw: File | { originFileObj?: File }) => {
  const file = raw instanceof File ? raw : raw.originFileObj
  if (!(file instanceof File)) return false
  return setFrame(file, 'last_frame')
}

const removeFirst = () => {
  revokeFrame(firstFrame.value)
  firstFrame.value = null
}
const removeLast = () => {
  revokeFrame(lastFrame.value)
  lastFrame.value = null
}

const cleanup = async () => {
  removeFirst()
  removeLast()
  templateApplyStore.setDirtyState(false)
  templateApplyStore.setPendingUploads(false)
  setSubmittedTaskId(null)
}

const handleGenerate = async () => {
  const frames = [firstFrame.value, ...(isFirstLastFrame.value ? [lastFrame.value] : [])]
  if (frames.length !== requiredImageCount.value || frames.some(frame => !frame)) {
    message.warning(t('template_apply.advanced_video_pro.required_images', { count: requiredImageCount.value }))
    return
  }
  if (
    isFirstLastFrame.value
    && !areFrameAspectRatiosCompatible(firstFrame.value!.dimensions, lastFrame.value!.dimensions)
  ) {
    message.warning(t('template_apply.advanced_video_pro.aspect_mismatch'))
    return
  }
  const payload = buildGenerationTaskPayload({
    taskType: props.context.rawTaskType,
    images: frames.map(frame => frame!.objectKey),
    prompt: lockedPrompt.value,
    promptTarget: 'inputs',
    duration: lockedDuration.value,
    loraItems: lockedLoraItems.value,
    extraInputs: {
      resolution_preset: lockedResolution.value,
      aspect_ratio: lockedAspectRatio.value,
      reference_descriptions: [],
    },
    isTemplate: true,
    sourcePostId: props.context.sourcePostId,
  })
  const taskId = await submitTask(payload, t('lab.cards.minimax_h3_title'))
  if (taskId) {
    setSubmittedTaskId(taskId)
    await templateApplyStore.closeAfterSubmission(props.sessionId)
  }
}

onMounted(() => {
  setSubmittedTaskId(null)
  templateApplyStore.setDirtyState(false)
  templateApplyStore.registerPanelController({ sessionId: props.sessionId, cleanup })
})
onBeforeUnmount(() => {
  cleanup()
  templateApplyStore.registerPanelController(null)
})
</script>

<template>
  <div class="template-panel flex flex-col lg:flex-row gap-6 min-h-[70vh]">
    <section class="w-full lg:w-[52%] flex flex-col bg-slate-900/70 rounded-2xl border border-slate-700/70 overflow-hidden">
      <div class="p-6 overflow-y-auto flex-1 space-y-5">
        <div>
          <h2 class="text-2xl font-bold text-slate-100">{{ t('lab.cards.minimax_h3_title') }}</h2>
          <p class="mt-2 text-sm text-cyan-200">{{ t('template_apply.advanced_video_pro.notice') }}</p>
        </div>

        <div class="rounded-xl border border-cyan-800/60 bg-cyan-950/30 p-4 space-y-3">
          <div class="text-sm font-semibold text-cyan-100">{{ t('template_apply.advanced_video_pro.locked_title') }}</div>
          <textarea :value="lockedPrompt" disabled rows="4" class="w-full rounded-lg border border-slate-700 bg-slate-950/70 p-3 text-sm text-slate-300" />
          <div class="grid grid-cols-2 gap-2 text-xs text-slate-300">
            <div>{{ t('template_apply.common.duration') }}：{{ lockedDuration }} {{ t('template_apply.common.seconds') }}</div>
            <div>{{ t('template_apply.common.resolution') }}：{{ lockedResolution }}</div>
            <div>{{ t('template_apply.advanced_video_pro.mode') }}：{{ isFirstLastFrame ? 'FLF2V' : 'I2V' }}</div>
            <div>{{ t('template_apply.advanced_video_pro.aspect') }}：{{ lockedAspectRatio }}</div>
          </div>
          <div v-if="addonLabels.length" class="flex flex-wrap gap-2">
            <span v-for="label in addonLabels" :key="label" class="rounded-full bg-slate-800 px-2 py-1 text-xs text-slate-200">{{ label }}</span>
          </div>
        </div>

        <TemplateApplyUploadSection
          :title="t('template_apply.common.start_frame')"
          :upload-text="t('template_apply.common.upload_start_frame')"
          :file-preview="firstFrame?.preview || null"
          :uploading-slots="uploadingSlots"
          :progress-by-slot="progressBySlot"
          :before-upload="beforeUploadFirst"
          @remove="removeFirst"
        />
        <TemplateApplyUploadSection
          v-if="isFirstLastFrame"
          :title="t('template_apply.advanced_video_pro.required_end_frame')"
          :upload-text="t('template_apply.common.upload_end_frame')"
          :file-preview="lastFrame?.preview || null"
          :uploading-slots="uploadingSlots"
          :progress-by-slot="progressBySlot"
          :before-upload="beforeUploadLast"
          @remove="removeLast"
        />
      </div>

      <TemplateApplyActionFooter
        :task-cost="taskCost"
        :is-submitting="isSubmitting"
        :has-pending-uploads="hasPendingUploads"
        :has-object-key="Boolean(firstFrame) && (!isFirstLastFrame || Boolean(lastFrame))"
        @generate="handleGenerate"
      />
    </section>

    <TemplateApplyResultSection
      :current-task="currentTask"
      :is-image-url="isImageUrl"
      @download="downloadResult"
    />
  </div>
</template>
