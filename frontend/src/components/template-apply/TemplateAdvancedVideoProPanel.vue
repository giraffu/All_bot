<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useTemplateApplyUpload } from '@/composables/useTemplateApplyUpload'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskSubmission } from '@/composables/useTaskSubmission'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
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
import H3ReferenceAudioUpload from '@/components/lab/H3ReferenceAudioUpload.vue'
import H3ReferenceVideoUpload from '@/components/lab/H3ReferenceVideoUpload.vue'
import type { H3ReferenceVideoClipDuration, UploadedReferenceAudio, UploadedReferenceVideo } from '@/composables/lab-workbench/types'
import {
  H3_REFERENCE_VIDEO_CLIP_DURATIONS,
  H3_REFERENCE_VIDEO_MAX_BYTES,
  H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS,
  readVideoDurationSeconds,
} from '@/composables/lab-workbench/useH3ReferenceVideo'

interface UploadedFrame {
  objectKey: string
  preview: string
  dimensions: ImageDimensions
}

interface TemplateReference {
  objectKey: string
  preview: string
  isReplacement: boolean
}

const props = defineProps<{
  sessionId: string
  context: TemplateApplyContext
}>()

const { t } = useI18n()
const templateApplyStore = useTemplateApplyStore()
const { isSubmitting, submitTask } = useTaskSubmission()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const sessionIdRef = computed(() => props.sessionId)
const { uploadFile, uploadingSlots, progressBySlot, hasPendingUploads } = useTemplateApplyUpload(sessionIdRef)

const isFirstLastFrame = computed(() => props.context.rawTaskType === 'minimax_h3_flf2v')
const isReferenceVideo = computed(() => props.context.rawTaskType === 'minimax_h3_ref2v')
const requiredImageCount = computed(() => isFirstLastFrame.value ? 2 : 1)
const firstFrame = ref<UploadedFrame | null>(null)
const lastFrame = ref<UploadedFrame | null>(null)
const templateReferences = ref<TemplateReference[]>(
  (props.context.inputFiles || []).flatMap((objectKey, index) => {
    const preview = props.context.inputFileUrls?.[index]
    return objectKey && preview
      ? [{ objectKey, preview, isReplacement: false }]
      : []
  }),
)
const hadTemplateReferenceAudio = Boolean(
  props.context.referenceAudioRef && props.context.referenceAudioUrl,
)
const referenceAudio = ref<UploadedReferenceAudio | null>(
  props.context.referenceAudioRef && props.context.referenceAudioUrl
    ? {
        key: '',
        preview: props.context.referenceAudioUrl,
        name: t('lab.workbench.minimax_h3_reference_audio_title'),
        referenceRef: props.context.referenceAudioRef,
      }
    : null,
)
const referenceVideo = ref<UploadedReferenceVideo | null>(null)
const referenceVideoClipDuration = ref<H3ReferenceVideoClipDuration>(5)
const referenceVideoClipDurationOptions = computed(() => (
  H3_REFERENCE_VIDEO_CLIP_DURATIONS.filter(
    duration => duration <= (referenceVideo.value?.durationSeconds ?? 0) + 1e-6,
  )
))
const lockedPrompt = computed(() => props.context.prompt || '')
const lockedDuration = computed(() => props.context.requestedDuration || 5)
const lockedResolution = computed(() => props.context.resolutionPreset || 'preview')
const lockedAspectRatio = computed(() => props.context.aspectRatio || 'source')
const taskCost = computed(() => getMinimaxH3TemplateCost(
  lockedResolution.value,
  lockedDuration.value,
  isReferenceVideo.value ? 'ref2v' : 'normal',
  {
    referenceAudio: Boolean(referenceAudio.value),
    referenceVideoDuration: referenceVideo.value ? referenceVideoClipDuration.value : null,
  },
))

watch(
  () => hasPendingUploads.value,
  pending => templateApplyStore.setPendingUploads(pending),
  { immediate: true },
)
watch(
  [firstFrame, lastFrame, templateReferences, referenceAudio, referenceVideo],
  () => templateApplyStore.setDirtyState(Boolean(
    firstFrame.value
    || lastFrame.value
    || templateReferences.value.some(reference => reference.isReplacement)
    || referenceAudio.value?.referenceRef?.source === 'upload'
    || referenceVideo.value !== null
    || (hadTemplateReferenceAudio && referenceAudio.value === null)
  )),
  { immediate: true, deep: true },
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

const beforeUploadReference = (index: number) => async (raw: File | { originFileObj?: File }) => {
  const file = raw instanceof File ? raw : raw.originFileObj
  if (!(file instanceof File)) return false
  try {
    await readImageDimensions(file)
  } catch {
    message.error(t('template_apply.image_prompt.upload_read_failed'))
    return false
  }
  const { objectKey } = await uploadFile(file, { slot: `reference_${index + 1}` })
  if (!objectKey) return false
  const current = templateReferences.value[index]
  if (current?.preview.startsWith('blob:')) URL.revokeObjectURL(current.preview)
  templateReferences.value[index] = {
    objectKey,
    preview: URL.createObjectURL(file),
    isReplacement: true,
  }
  return false
}

const removeFirst = () => {
  revokeFrame(firstFrame.value)
  firstFrame.value = null
}
const removeLast = () => {
  revokeFrame(lastFrame.value)
  lastFrame.value = null
}

const clearReferenceAudio = () => {
  if (referenceAudio.value?.preview.startsWith('blob:')) {
    URL.revokeObjectURL(referenceAudio.value.preview)
  }
  referenceAudio.value = null
}

const beforeUploadReferenceAudio = async (file: File) => {
  const { objectKey } = await uploadFile(file, { slot: 'reference_audio' })
  if (!objectKey) return false
  clearReferenceAudio()
  referenceAudio.value = {
    key: objectKey,
    preview: URL.createObjectURL(file),
    name: file.name,
    referenceRef: { source: 'upload', object_key: objectKey },
  }
  return false
}

const clearReferenceVideo = () => {
  if (referenceVideo.value?.preview.startsWith('blob:')) {
    URL.revokeObjectURL(referenceVideo.value.preview)
  }
  referenceVideo.value = null
  referenceVideoClipDuration.value = 5
}

const beforeUploadReferenceVideo = async (file: File) => {
  let durationSeconds: number
  try {
    durationSeconds = await readVideoDurationSeconds(file)
  }
  catch {
    message.warning(t('lab.workbench.validation.minimax_h3_reference_video_unreadable'))
    return false
  }
  if (durationSeconds > H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS) {
    message.warning(t('lab.workbench.validation.minimax_h3_reference_video_too_long'))
    return false
  }
  if (durationSeconds + 1e-6 < H3_REFERENCE_VIDEO_CLIP_DURATIONS[0]) {
    message.warning(t('lab.workbench.validation.minimax_h3_reference_video_too_short'))
    return false
  }
  const { objectKey } = await uploadFile(file, {
    slot: 'reference_video',
    maxSizeBytes: H3_REFERENCE_VIDEO_MAX_BYTES,
  })
  if (!objectKey) return false
  clearReferenceVideo()
  referenceVideo.value = {
    key: objectKey,
    preview: URL.createObjectURL(file),
    name: file.name,
    durationSeconds,
    referenceRef: { source: 'upload', object_key: objectKey },
  }
  referenceVideoClipDuration.value = durationSeconds >= 5 ? 5 : 3
  return false
}

const cleanup = async () => {
  removeFirst()
  removeLast()
  templateReferences.value.forEach((reference) => {
    if (reference.isReplacement && reference.preview.startsWith('blob:')) {
      URL.revokeObjectURL(reference.preview)
    }
  })
  clearReferenceAudio()
  clearReferenceVideo()
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
    images: [
      ...frames.map(frame => frame!.objectKey),
      ...(isReferenceVideo.value
        ? templateReferences.value.map(reference => reference.objectKey)
        : []),
    ],
    prompt: lockedPrompt.value,
    promptTarget: 'inputs',
    duration: lockedDuration.value,
    extraInputs: {
      resolution_preset: lockedResolution.value,
      aspect_ratio: lockedAspectRatio.value,
      reference_descriptions: [],
      ...(isReferenceVideo.value && referenceAudio.value?.referenceRef
        ? { reference_audio_ref: referenceAudio.value.referenceRef }
        : {}),
      ...(isReferenceVideo.value && referenceVideo.value?.referenceRef
        ? {
            reference_video_ref: referenceVideo.value.referenceRef,
            reference_video_duration: referenceVideoClipDuration.value,
          }
        : {}),
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
            <div>{{ t('template_apply.advanced_video_pro.mode') }}：{{ isReferenceVideo ? 'REF2V' : isFirstLastFrame ? 'FLF2V' : 'I2V' }}</div>
            <div>{{ t('template_apply.advanced_video_pro.aspect') }}：{{ lockedAspectRatio }}</div>
          </div>
        </div>

        <TemplateApplyUploadSection
          :title="isReferenceVideo ? t('original_inputs.primary_image') : t('template_apply.common.start_frame')"
          :upload-text="isReferenceVideo ? t('template_apply.common.upload_reference_image') : t('template_apply.common.upload_start_frame')"
          :file-preview="firstFrame?.preview || null"
          :uploading-slots="uploadingSlots"
          :progress-by-slot="progressBySlot"
          :before-upload="beforeUploadFirst"
          @remove="removeFirst"
        />
        <template v-if="isReferenceVideo">
          <TemplateApplyUploadSection
            v-for="(reference, index) in templateReferences"
            :key="`${reference.objectKey}-${index}`"
            :title="t('template_apply.advanced_video_pro.template_reference', { count: index + 1 })"
            :file-preview="reference.preview"
            :uploading-slots="uploadingSlots"
            :progress-by-slot="progressBySlot"
            :before-upload="beforeUploadReference(index)"
            :replace-text="t('template_apply.advanced_video_pro.replace_reference')"
            :show-remove="false"
          />
          <H3ReferenceAudioUpload
            :item="referenceAudio"
            :uploading="Boolean(uploadingSlots.reference_audio)"
            :before-upload="beforeUploadReferenceAudio"
            @remove="clearReferenceAudio"
          />
          <H3ReferenceVideoUpload
            :item="referenceVideo"
            :uploading="Boolean(uploadingSlots.reference_video)"
            :before-upload="beforeUploadReferenceVideo"
            :clip-duration="referenceVideoClipDuration"
            :clip-duration-options="referenceVideoClipDurationOptions"
            @update:clip-duration="referenceVideoClipDuration = $event"
            @remove="clearReferenceVideo"
          />
        </template>
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
