<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CloseCircleOutlined,
  DownloadOutlined,
  InboxOutlined,
  VideoCameraOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useTemplateApplyUpload } from '@/composables/useTemplateApplyUpload'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import {
  getDefaultImageToVideoLoraSelection,
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
  getImageToVideoRequestTaskType,
  IMAGE_TO_VIDEO_LORA_OPTIONS,
  LTX_VIDEO_LORA_OPTIONS,
  isUnifiedImageToVideoTaskType,
  normalizeImageToVideoLoraSelection
} from '@/features/generation/imageToVideo'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { TemplateApplyContext } from '@/types/templateApply'
import { resolveTemplateVideoApplyState } from '@/utils/templateVideoApplyState'

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

const taskType = computed(() => props.context.taskType ?? 'custom_video')
const isUnifiedImageToVideo = computed(() => isUnifiedImageToVideoTaskType(taskType.value))
const isLtxVideo = computed(() => taskType.value === 'ltx_video')
const taskTitle = computed(() => {
  if (isLtxVideo.value) return t('template_apply.image_to_video.title_ltx_video')
  return t('template_apply.image_to_video.title_custom_video')
})

const objectKey = ref<string | null>(null)
const filePreview = ref<string | null>(null)
const resolution = ref('512')
const duration = ref('5')
const prompt = ref('')
const loraSelection = ref(getDefaultImageToVideoLoraSelection(taskType.value))
const loraName = computed(() => getImageToVideoPayloadLoraName(taskType.value, loraSelection.value))
const loraStrength = computed(() => getImageToVideoPayloadLoraStrength(taskType.value, loraSelection.value))
const templateSourcePostId = ref<number | null>(null)
const isTemplateApplied = ref(false)
const isTemplateVideoSettingsLocked = ref(false)
const isTemplatePromptLocked = ref(false)
const templateSettingsWarning = ref('')
const templateApplyNotice = ref('')

const initialObjectKey = ref<string | null>(null)
const initialResolution = ref('512')
const initialDuration = ref('5')
const initialPrompt = ref('')
const initialLoraSelection = ref(getDefaultImageToVideoLoraSelection(taskType.value))

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

  const res = resolution.value
  const dur = duration.value

  let baseCost = 6
  if (res === '720') baseCost = 18
  else if (res === '1024') baseCost = 36

  let multiplier = 1
  if (dur === '8') multiplier = 2
  else if (dur === '10') multiplier = 3

  return baseCost * multiplier
})

watch(
  () => hasPendingUploads.value,
  (pending) => {
    templateApplyStore.setPendingUploads(pending)
  },
  { immediate: true }
)

watch(
  [objectKey, resolution, duration, prompt, loraSelection],
  () => {
    const isDirty =
      objectKey.value !== initialObjectKey.value
      || resolution.value !== initialResolution.value
      || duration.value !== initialDuration.value
      || prompt.value.trim() !== initialPrompt.value
      || loraSelection.value !== initialLoraSelection.value
    templateApplyStore.setDirtyState(isDirty)
  },
  { immediate: true }
)

watch(resolution, (value) => {
  if (!isLtxVideo.value && value === '1024' && duration.value === '10') {
    duration.value = '8'
  }
})

watch(duration, (value) => {
  if (!isLtxVideo.value && value === '10' && resolution.value === '1024') {
    resolution.value = '720'
  }
})

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
  }

  const templateState = resolveTemplateVideoApplyState(
    props.context.raw as any,
    taskType.value as 'custom_video' | 'video_lora' | 'ltx_video'
  )

  if (templateState) {
    if (templateState.prompt) prompt.value = templateState.prompt
    loraSelection.value = normalizeImageToVideoLoraSelection(templateState.loraName)
    if (templateState.sourcePostId != null) {
      templateSourcePostId.value = templateState.sourcePostId
    }
    if (templateState.resolution) resolution.value = templateState.resolution
    if (templateState.duration) duration.value = templateState.duration
    if (!isLtxVideo.value && resolution.value === '1024' && duration.value === '10') {
      resolution.value = '720'
    }

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
  initialLoraSelection.value = loraSelection.value
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
    resolution: isLtxVideo.value ? resolution.value : Number(resolution.value),
    duration: Number(duration.value),
    prompt: (isUnifiedImageToVideo.value || isLtxVideo.value) ? prompt.value : undefined,
    promptTarget: 'inputs',
    loraName: loraName.value,
    loraStrength: loraStrength.value,
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

        <div
          v-if="isTemplateApplied"
          class="mb-4 rounded-xl border border-indigo-500/40 bg-indigo-500/15 px-4 py-3 text-sm text-slate-200"
        >
          {{ templateApplyNotice }}
        </div>

        <div
          v-if="templateSettingsWarning"
          class="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
        >
          {{ templateSettingsWarning }}
        </div>

        <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
          <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.base_image') }}</div>
          <div v-if="filePreview" class="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950/80">
            <img :src="filePreview" class="h-56 w-full object-contain bg-slate-950/80" />
            <button
              class="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white"
              @click="handleRemove"
            >
              <CloseCircleOutlined />
            </button>
          </div>
          <a-upload-dragger
            v-else
            :before-upload="beforeUpload"
            :show-upload-list="false"
            accept="image/*"
            class="template-upload"
          >
            <p class="ant-upload-drag-icon">
              <InboxOutlined class="text-cyan-400" />
            </p>
            <p class="text-slate-200">{{ t('template_apply.common.upload_base_image') }}</p>
            <p class="text-slate-400 text-xs">{{ t('template_apply.common.continue_after_close') }}</p>
          </a-upload-dragger>
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

        <div class="mt-6 rounded-xl border border-slate-700 bg-slate-800/70 p-4">
          <div class="text-sm font-semibold text-slate-200 mb-3">
            {{ isUnifiedImageToVideo ? t('template_apply.image_to_video.action_and_model') : t('template_apply.image_to_video.desc_and_params') }}
          </div>

          <div v-if="isTemplatePromptLocked" class="rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-6 text-center text-sm text-slate-300">
            <div class="font-medium text-slate-200">{{ t('template_apply.common.prompt_locked_title') }}</div>
            <div class="mt-2 text-xs text-slate-400">{{ t('template_apply.common.prompt_locked_video_hint') }}</div>
          </div>
          <template v-else>
            <div v-if="isUnifiedImageToVideo || isLtxVideo" class="mb-3">
              <a-select
                v-model:value="loraSelection"
                :placeholder="t('template_apply.image_to_video.select_addon')"
                class="w-full"
              >
                <a-select-option
                  v-for="option in (isLtxVideo ? LTX_VIDEO_LORA_OPTIONS : IMAGE_TO_VIDEO_LORA_OPTIONS)"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </a-select-option>
              </a-select>
              <p v-if="isLtxVideo && loraName && loraStrength != null" class="mt-2 text-xs text-slate-400">
                默认强度：{{ loraStrength }}
              </p>
            </div>
            <a-textarea
              v-model:value="prompt"
              :rows="6"
              :placeholder="isUnifiedImageToVideo ? t('template_apply.image_to_video.prompt_placeholder_video_lora') : t('template_apply.image_to_video.prompt_placeholder_custom')"
            />
          </template>
        </div>

        <div class="mt-6 rounded-xl border border-slate-700 bg-slate-800/70 p-4">
          <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.output_settings') }}</div>
          <div v-if="isTemplateVideoSettingsLocked" class="rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-6 text-center text-sm text-slate-300">
            {{ t('template_apply.common.template_locked_settings') }}
          </div>
          <div v-else class="space-y-4">
            <div>
              <label class="block text-xs font-medium text-slate-300 mb-2">{{ t('template_apply.common.resolution') }}</label>
              <a-radio-group
                v-if="isLtxVideo"
                v-model:value="resolution"
                button-style="solid"
                class="w-full grid grid-cols-1 gap-2 max-w-[180px]"
              >
                <a-radio-button value="1280x704" class="w-full text-center">1280x704</a-radio-button>
              </a-radio-group>
              <a-radio-group
                v-else
                v-model:value="resolution"
                button-style="solid"
                class="w-full grid grid-cols-3 gap-2"
              >
                <a-radio-button value="512" class="w-full text-center">512p</a-radio-button>
                <a-radio-button value="720" class="w-full text-center">720p</a-radio-button>
                <a-radio-button value="1024" class="w-full text-center" :disabled="duration === '10'">1024p</a-radio-button>
              </a-radio-group>
            </div>

            <div>
              <label class="block text-xs font-medium text-slate-300 mb-2">{{ t('template_apply.common.duration') }}</label>
              <a-radio-group
                v-if="isLtxVideo"
                v-model:value="duration"
                button-style="solid"
                class="w-full grid grid-cols-4 gap-2 max-w-[320px]"
              >
                <a-radio-button value="5" class="w-full text-center">5 {{ t('template_apply.common.seconds') }}</a-radio-button>
                <a-radio-button value="10" class="w-full text-center">10 {{ t('template_apply.common.seconds') }}</a-radio-button>
                <a-radio-button value="15" class="w-full text-center">15 {{ t('template_apply.common.seconds') }}</a-radio-button>
                <a-radio-button value="20" class="w-full text-center">20 {{ t('template_apply.common.seconds') }}</a-radio-button>
              </a-radio-group>
              <a-radio-group
                v-else
                v-model:value="duration"
                button-style="solid"
                class="w-full grid grid-cols-3 gap-2 max-w-[240px]"
              >
                <a-radio-button value="5" class="w-full text-center">5 {{ t('template_apply.common.seconds') }}</a-radio-button>
                <a-radio-button value="8" class="w-full text-center">8 {{ t('template_apply.common.seconds') }}</a-radio-button>
                <a-radio-button value="10" class="w-full text-center" :disabled="resolution === '1024'">10 {{ t('template_apply.common.seconds') }}</a-radio-button>
              </a-radio-group>
            </div>
          </div>
        </div>
      </div>

      <div class="border-t border-slate-700 px-6 py-4 flex items-center justify-between gap-4">
        <div class="text-sm text-slate-300">
          {{ t('template_apply.common.estimated_cost') }} <span class="text-cyan-300 font-semibold">{{ taskCost }}</span> {{ t('template_apply.common.credits_unit') }}
        </div>
        <a-button
          type="primary"
          size="large"
          :loading="isSubmitting"
          :disabled="hasPendingUploads || !objectKey"
          @click="handleGenerate"
        >
          <template #icon>
            <VideoCameraOutlined />
          </template>
          {{ t('template_apply.common.generate_video') }}
        </a-button>
      </div>
    </section>

    <section class="w-full lg:w-[48%] flex flex-col bg-slate-900/70 rounded-2xl border border-slate-700/70 overflow-hidden">
      <div class="p-6 border-b border-slate-700">
        <h3 class="text-lg font-semibold text-slate-100">{{ t('template_apply.common.result_title') }}</h3>
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        <div v-if="currentTask" class="space-y-4">
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
            <div class="flex items-center justify-between text-sm text-slate-300">
              <span>{{ currentTask.title }}</span>
              <span>
                {{
                  currentTask.status === 'cancelled'
                    ? '已取消'
                    : currentTask.cancelRequested
                      ? '撤销确认中'
                      : currentTask.status
                }}
              </span>
            </div>
            <a-progress
              class="mt-3"
              :percent="currentTask.status === 'cancelled' ? 100 : currentTask.progress"
              :status="currentTask.cancelRequested || currentTask.status === 'cancelled'
                ? 'normal'
                : currentTask.status === 'failed'
                  ? 'exception'
                  : 'active'"
            />
            <div v-if="currentTask.cancelRequested" class="mt-3 text-sm text-amber-300">
              {{ currentTask.cancelMessage || '已提交撤销请求，等待执行端确认。' }}
            </div>
            <div
              v-if="currentTask.cancelRequested || currentTask.status === 'cancelled'"
              class="mt-1 text-xs text-slate-400"
            >
              {{ currentTask.refundMessage || '确认后将自动退回灵石。' }}
            </div>
            <div v-if="currentTask.error" class="mt-3 text-sm text-rose-300">
              {{ currentTask.error }}
            </div>
          </div>

          <div
            v-if="currentTask.resultUrl"
            class="rounded-xl border border-slate-700 bg-slate-950/80 p-3"
          >
            <img
              v-if="isImageUrl(currentTask.resultUrl)"
              :src="currentTask.resultUrl"
              class="w-full rounded-xl object-contain"
            />
            <video
              v-else
              :src="currentTask.resultUrl"
              controls
              class="w-full rounded-xl"
            />

            <div class="mt-3 flex justify-end">
              <a-button @click="downloadResult(currentTask.resultUrl, currentTask.title)">
                <template #icon>
                  <DownloadOutlined />
                </template>
                {{ t('template_apply.common.download_result') }}
              </a-button>
            </div>
          </div>
        </div>

        <div
          v-else
          class="h-full min-h-[240px] flex items-center justify-center text-center text-slate-400"
        >
          {{ t('template_apply.common.result_empty') }}
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.template-upload :deep(.ant-upload.ant-upload-drag) {
  background: rgba(15, 23, 42, 0.75);
  border-color: rgba(71, 85, 105, 0.9);
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
