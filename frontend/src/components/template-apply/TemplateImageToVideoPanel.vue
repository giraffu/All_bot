<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useTemplateApplyUpload } from '@/composables/useTemplateApplyUpload'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import {
  buildDefaultLtxVideoLoraItem,
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  getDefaultImageToVideoLoraSelection,
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
  getImageToVideoRequestTaskType,
  normalizeLtxVideoLoraItems,
  isUnifiedImageToVideoTaskType,
  isWan22TemplateVideoTaskType,
  normalizeImageToVideoLoraSelection,
  normalizeWan22VideoV2ResolutionPreset,
  normalizeWan22VideoV2DurationSeconds,
  getWan22VideoV2Cost,
  DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS,
  type LtxVideoLoraItem
} from '@/features/generation/imageToVideo'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { TemplateApplyContext } from '@/types/templateApply'
import { resolveTemplateVideoApplyState } from '@/utils/templateVideoApplyState'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'
import TemplateApplyActionFooter from '@/components/template-apply/TemplateApplyActionFooter.vue'
import TemplateApplyLoraPromptSection from '@/components/template-apply/TemplateApplyLoraPromptSection.vue'
import TemplateApplyOutputSettingsSection from '@/components/template-apply/TemplateApplyOutputSettingsSection.vue'
import TemplateApplyResultSection from '@/components/template-apply/TemplateApplyResultSection.vue'
import TemplateApplyTemplateLocks from '@/components/template-apply/TemplateApplyTemplateLocks.vue'
import TemplateApplyUploadSection from '@/components/template-apply/TemplateApplyUploadSection.vue'

const props = defineProps<{
  sessionId: string
  context: TemplateApplyContext
}>()

warnIfPropsExceedBudget('TemplateImageToVideoPanel', Object.keys(props).length)

const { t } = useI18n()
const templateApplyStore = useTemplateApplyStore()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
const sessionIdRef = computed(() => props.sessionId)
const { uploadFile, uploadingSlots, progressBySlot, hasPendingUploads } = useTemplateApplyUpload(sessionIdRef)

const taskType = computed(() => props.context.taskType ?? 'custom_video')
const isUnifiedImageToVideo = computed(() => isUnifiedImageToVideoTaskType(taskType.value))
const isWan22VideoV2 = computed(() => taskType.value === 'wan22_video_v2')
const isLtxVideo = computed(() => taskType.value === 'ltx_video')
const taskTitle = computed(() => {
  if (isWan22VideoV2.value) return t('template_apply.image_to_video.title_wan22_video_v2')
  if (isLtxVideo.value) return t('template_apply.image_to_video.title_ltx_video')
  return t('template_apply.image_to_video.title_custom_video')
})

const objectKey = ref<string | null>(null)
const filePreview = ref<string | null>(null)
const resolution = ref('preview')
const duration = ref('5')
const prompt = ref('')
const negativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
const loraSelection = ref(getDefaultImageToVideoLoraSelection(taskType.value))
const loraName = computed(() => getImageToVideoPayloadLoraName(taskType.value, loraSelection.value))
const loraStrength = computed(() => getImageToVideoPayloadLoraStrength(taskType.value, loraSelection.value))
const ltxLoraItems = ref<LtxVideoLoraItem[]>([])
const selectedLtxLoraNames = ref<string[]>([])
const expandedLtxLoraEditors = ref<string[]>([])
const templateSourcePostId = ref<number | null>(null)
const isTemplateApplied = ref(false)
const isTemplateVideoSettingsLocked = ref(false)
const isTemplatePromptLocked = ref(false)
const templateSettingsWarning = ref('')
const templateApplyNotice = ref('')
const showActionSection = computed(() => !isTemplatePromptLocked.value)
const showOutputSettingsSection = computed(() => !isTemplateVideoSettingsLocked.value)

const initialObjectKey = ref<string | null>(null)
const initialResolution = ref('512')
const initialDuration = ref('5')
const initialPrompt = ref('')
const initialNegativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
const initialLoraSelection = ref(getDefaultImageToVideoLoraSelection(taskType.value))
const initialLtxLoraItems = ref<LtxVideoLoraItem[]>([])

const syncLtxLoraItems = (names: string[]) => {
  const uniqueNames = Array.from(new Set(names.filter(value => value && value !== '__none__'))).slice(0, 3)
  if (uniqueNames.length < names.length) {
    message.warning('最多只能选择 3 个附加模型')
  }
  selectedLtxLoraNames.value = uniqueNames
  ltxLoraItems.value = uniqueNames
    .map((name) => {
      const existing = ltxLoraItems.value.find(item => item.name === name)
      return existing ?? buildDefaultLtxVideoLoraItem(name)
    })
    .filter((item): item is LtxVideoLoraItem => Boolean(item))
  expandedLtxLoraEditors.value = expandedLtxLoraEditors.value.filter(name => uniqueNames.includes(name))
}

const removeLtxLoraItem = (name: string) => {
  syncLtxLoraItems(selectedLtxLoraNames.value.filter(item => item !== name))
}

const updateLtxLoraStrength = (name: string, strength: number | null) => {
  if (typeof strength !== 'number' || !Number.isFinite(strength)) return
  const nextStrength = Math.min(2, Math.max(0.1, Number(strength.toFixed(2))))
  ltxLoraItems.value = ltxLoraItems.value.map(item => (
    item.name === name ? { ...item, strength: nextStrength } : item
  ))
}

const toggleLtxLoraStrengthEditor = (name: string) => {
  expandedLtxLoraEditors.value = expandedLtxLoraEditors.value.includes(name)
    ? expandedLtxLoraEditors.value.filter(item => item !== name)
    : [...expandedLtxLoraEditors.value, name]
}

const taskCost = computed(() => {
  if (isLtxVideo.value) {
    const dur = duration.value
    let baseCost = 10
    let multiplier = 1
    if (dur === '10') multiplier = 2
    else if (dur === '15') multiplier = 3
    else if (dur === '20') multiplier = 4
    return baseCost * multiplier
  }

  return getWan22VideoV2Cost(resolution.value, duration.value)
})

watch(
  () => hasPendingUploads.value,
  (pending) => {
    templateApplyStore.setPendingUploads(pending)
  },
  { immediate: true }
)

watch(
  [objectKey, resolution, duration, prompt, negativePrompt, loraSelection, ltxLoraItems],
  () => {
    const isDirty =
      objectKey.value !== initialObjectKey.value
      || resolution.value !== initialResolution.value
      || duration.value !== initialDuration.value
      || prompt.value.trim() !== initialPrompt.value
      || negativePrompt.value.trim() !== initialNegativePrompt.value
      || loraSelection.value !== initialLoraSelection.value
      || JSON.stringify(ltxLoraItems.value) !== JSON.stringify(initialLtxLoraItems.value)
    templateApplyStore.setDirtyState(isDirty)
  },
  { immediate: true }
)

watch(isLtxVideo, (value) => {
  if (!value) {
    ltxLoraItems.value = []
    selectedLtxLoraNames.value = []
    expandedLtxLoraEditors.value = []
  }
}, { immediate: true })

const cleanup = async () => {
  if (filePreview.value?.startsWith('blob:')) {
    URL.revokeObjectURL(filePreview.value)
  }
  filePreview.value = null
  objectKey.value = null
  templateApplyStore.setDirtyState(false)
  templateApplyStore.setPendingUploads(false)
  setSubmittedTaskId(null)
}

const initializeFromContext = () => {
  if (isLtxVideo.value) {
    resolution.value = '1280x704'
  } else {
    resolution.value = 'preview'
    duration.value = DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS
  }
  negativePrompt.value = DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT

  const templateState = resolveTemplateVideoApplyState(
    props.context.raw as any,
    taskType.value as 'custom_video' | 'video_lora' | 'wan22_video_v2' | 'ltx_video'
  )

  if (templateState) {
    if (templateState.prompt) prompt.value = templateState.prompt
    if (isWan22VideoV2.value) {
      negativePrompt.value = templateState.negativePrompt || DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    }
    loraSelection.value = normalizeImageToVideoLoraSelection(templateState.loraName)
    ltxLoraItems.value = normalizeLtxVideoLoraItems(templateState.loraItems)
    selectedLtxLoraNames.value = ltxLoraItems.value.map(item => item.name)
    if (templateState.sourcePostId != null) {
      templateSourcePostId.value = templateState.sourcePostId
    }
    if (templateState.resolution) {
      resolution.value = isLtxVideo.value
        ? templateState.resolution
        : normalizeWan22VideoV2ResolutionPreset(templateState.resolution)
    }
    duration.value = isLtxVideo.value
      ? (templateState.duration ?? '5')
      : normalizeWan22VideoV2DurationSeconds(templateState.duration)

    templateSettingsWarning.value = templateState.templateSettingsWarning
    templateApplyNotice.value = templateState.templateApplyNotice
    isTemplateApplied.value = templateState.isTemplateApplied
    isTemplateVideoSettingsLocked.value = templateState.isTemplateVideoSettingsLocked
    isTemplatePromptLocked.value = templateState.isTemplatePromptLocked
  }

  initialObjectKey.value = null
  initialResolution.value = resolution.value
  initialDuration.value = duration.value
  initialPrompt.value = prompt.value.trim()
  initialNegativePrompt.value = negativePrompt.value.trim()
  initialLoraSelection.value = loraSelection.value
  initialLtxLoraItems.value = [...ltxLoraItems.value]
}

const beforeUpload = async (rawFile: File | { originFileObj?: File }) => {
  const file = rawFile instanceof File ? rawFile : rawFile.originFileObj
  if (!(file instanceof File)) {
    message.error(t('template_apply.image_prompt.upload_read_failed'))
    return false
  }

  const { objectKey: uploadedKey } = await uploadFile(file, { slot: 'base_image' })
  if (!uploadedKey) {
    return false
  }

  if (filePreview.value?.startsWith('blob:')) {
    URL.revokeObjectURL(filePreview.value)
  }
  filePreview.value = URL.createObjectURL(file)
  objectKey.value = uploadedKey
  return false
}

const handleRemove = () => {
  if (filePreview.value?.startsWith('blob:')) {
    URL.revokeObjectURL(filePreview.value)
  }
  filePreview.value = null
  objectKey.value = null
}

const handleGenerate = async () => {
  if (!objectKey.value) {
    message.warning(t('template_apply.image_to_video.upload_first'))
    return
  }

  const payload = buildGenerationTaskPayload({
    taskType: getImageToVideoRequestTaskType(taskType.value, loraSelection.value),
    images: [objectKey.value],
    resolution: isLtxVideo.value ? resolution.value : undefined,
    duration: isLtxVideo.value
      ? Number(duration.value)
      : Number(normalizeWan22VideoV2DurationSeconds(duration.value)),
    prompt: (isWan22TemplateVideoTaskType(taskType.value) || isLtxVideo.value) ? prompt.value : undefined,
    negativePrompt: isWan22VideoV2.value ? negativePrompt.value : undefined,
    promptTarget: 'inputs',
    loraName: loraName.value,
    loraStrength: loraStrength.value,
    loraItems: isLtxVideo.value ? ltxLoraItems.value : undefined,
    extraInputs: !isLtxVideo.value
      ? {
          resolution_preset: normalizeWan22VideoV2ResolutionPreset(resolution.value),
          use_end_frame: false,
        }
      : undefined,
    isTemplate: isTemplateApplied.value,
    sourcePostId: templateSourcePostId.value,
  })

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
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
        <p class="text-slate-400 text-sm mb-6">{{ t('template_apply.image_to_video.current_page_desc') }}</p>

        <TemplateApplyTemplateLocks
          class="mb-6"
          :is-template-applied="isTemplateApplied"
          :template-apply-notice="templateApplyNotice"
          :template-settings-warning="templateSettingsWarning"
        />

        <TemplateApplyUploadSection
          :file-preview="filePreview"
          :uploading-slots="uploadingSlots"
          :progress-by-slot="progressBySlot"
          :before-upload="beforeUpload"
          @remove="handleRemove"
        />

        <TemplateApplyLoraPromptSection
          class="mt-6"
          :show-action-section="showActionSection"
          :is-unified-image-to-video="isUnifiedImageToVideo"
          :is-ltx-video="isLtxVideo"
          :prompt="prompt"
          :lora-selection="loraSelection"
          :selected-ltx-lora-names="selectedLtxLoraNames"
          :ltx-lora-items="ltxLoraItems"
          :expanded-ltx-lora-editors="expandedLtxLoraEditors"
          @update:prompt="prompt = $event"
          @update:lora-selection="loraSelection = $event"
          @sync-ltx-lora-items="syncLtxLoraItems"
          @toggle-ltx-lora-strength-editor="toggleLtxLoraStrengthEditor"
          @remove-ltx-lora-item="removeLtxLoraItem"
          @update-ltx-lora-strength="updateLtxLoraStrength"
        />

        <TemplateApplyOutputSettingsSection
          class="mt-6"
          :show-output-settings-section="showOutputSettingsSection"
          :is-ltx-video="isLtxVideo"
          :resolution="resolution"
          :duration="duration"
          @update:resolution="resolution = $event"
          @update:duration="duration = $event"
        />
      </div>

      <TemplateApplyActionFooter
        :task-cost="taskCost"
        :is-submitting="isSubmitting"
        :has-pending-uploads="hasPendingUploads"
        :has-object-key="!!objectKey"
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
