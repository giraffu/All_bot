<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CloseCircleOutlined, DownloadOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useTemplateApplyUpload } from '@/composables/useTemplateApplyUpload'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import {
  PORNMASTER_FLUX2_MULTI_EDIT_TASK_TYPE,
  PORNMASTER_FLUX2_SINGLE_EDIT_TASK_TYPE,
} from '@/features/generation/labModeConfig'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { TemplateApplyContext } from '@/types/templateApply'

interface UploadedImageItem {
  slot: string
  key: string
  preview: string
}

const props = defineProps<{
  sessionId: string
  context: TemplateApplyContext
}>()

const { t } = useI18n()
const templateApplyStore = useTemplateApplyStore()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isVideoUrl, downloadResult } = useTaskResult()
const sessionIdRef = computed(() => props.sessionId)
const { uploadFile, uploadingSlots, progressBySlot, hasPendingUploads } = useTemplateApplyUpload(sessionIdRef)

const taskType = computed(() => props.context.taskType ?? 'i2i_pro')
const isFreeEditV2TaskType = computed(() => (
  taskType.value === PORNMASTER_FLUX2_SINGLE_EDIT_TASK_TYPE
  || taskType.value === PORNMASTER_FLUX2_MULTI_EDIT_TASK_TYPE
))
const maxImages = computed(() => ['i2i_pro', 'i2i_draw'].includes(taskType.value) ? 1 : 2)
const taskTitle = computed(() => {
  switch (taskType.value) {
    case 'i2i_pro':
      return t('template_apply.image_prompt.title_i2i_pro')
    case 'i2i_draw':
      return t('template_apply.image_prompt.title_i2i_draw')
    case 'edit':
      return t('template_apply.image_prompt.title_edit')
    case 'img2img_lora':
      return t('template_apply.image_prompt.title_img2img_lora')
    case PORNMASTER_FLUX2_SINGLE_EDIT_TASK_TYPE:
    case PORNMASTER_FLUX2_MULTI_EDIT_TASK_TYPE:
      return t('lab.cards.custom_edit_v2_title')
    default:
      return t('template_apply.common.start_generate')
  }
})

const uploadedImages = ref<UploadedImageItem[]>([])
const prompt = ref('')
const templateSourcePostId = ref<number | null>(null)
const isTemplateApplied = ref(false)
const selectedLora = ref('')
const customLoraStrength = ref(1.0)

const initialPrompt = ref('')
const initialSelectedLora = ref('')
const initialLoraStrength = ref(1.0)
const pendingUploadCount = computed(() =>
  Object.values(uploadingSlots.value).filter(Boolean).length
)
const isAnyUploading = computed(() => pendingUploadCount.value > 0)
const isPromptLocked = computed(() => isTemplateApplied.value)
const isLoraLocked = computed(() =>
  isTemplateApplied.value && (taskType.value === 'edit' || taskType.value === 'img2img_lora')
)
const showLoraSection = computed(() =>
  !isFreeEditV2TaskType.value
  && (taskType.value === 'edit' || taskType.value === 'img2img_lora')
  && !isLoraLocked.value
)
let uploadSlotCounter = 0

const loraOptions = [
  { value: '', label: t('template_apply.image_prompt.no_model') },
  { value: 'qwen/YARN_1.0.safetensors', label: '逼真' },
  { value: 'qwen/adjust_pussy_anus.safetensors', label: '菊花+内凹穴' },
  { value: 'qwen/realistic_texture.safetensors', label: '真实质感' },
  { value: 'qwen/flat_chest_hairless.safetensors', label: '平胸/无毛穴' },
  { value: 'qwen/penis.safetensors', label: '扶他(阴茎)' }
]

const LORA_DEFAULT_STRENGTHS: Record<string, number> = {
  'qwen/YARN_1.0.safetensors': 0.3,
  'qwen/adjust_pussy_anus.safetensors': 1.0,
  'qwen/realistic_texture.safetensors': 0.8,
  'qwen/flat_chest_hairless.safetensors': 0.8,
  'qwen/penis.safetensors': 0.7
}

const taskCost = computed(() => {
  if (
    taskType.value === 'edit'
    || taskType.value === 'img2img_lora'
    || isFreeEditV2TaskType.value
  ) {
    return uploadedImages.value.length === 2 ? 6 : 2
  }

  if (taskType.value === 'i2i_pro') {
    return 6
  }

  return 3
})

const templateNotice = computed(() => {
  if (!isTemplateApplied.value) {
    return ''
  }

  if (taskType.value === 'i2i_pro' || taskType.value === 'i2i_draw') {
    return t('template_apply.image_prompt.template_notice_i2i')
  }

  if (selectedLora.value) {
    return t('template_apply.image_prompt.template_notice_lora')
  }

  return t('template_apply.image_prompt.template_notice_image')
})

watch(selectedLora, (newLora) => {
  if (isLoraLocked.value) {
    return
  }

  if (newLora) {
    customLoraStrength.value = LORA_DEFAULT_STRENGTHS[newLora] || 1.0
  }
})

watch(
  () => hasPendingUploads.value,
  (pending) => {
    templateApplyStore.setPendingUploads(pending)
  },
  { immediate: true }
)

watch(
  [prompt, selectedLora, customLoraStrength, uploadedImages],
  () => {
    const isDirty =
      prompt.value.trim() !== initialPrompt.value
      || selectedLora.value !== initialSelectedLora.value
      || Number(customLoraStrength.value) !== Number(initialLoraStrength.value)
      || uploadedImages.value.length > 0
    templateApplyStore.setDirtyState(isDirty)
  },
  { immediate: true, deep: true }
)

const revokePreview = (preview: string) => {
  if (preview.startsWith('blob:')) {
    URL.revokeObjectURL(preview)
  }
}

const clearPreviews = () => {
  uploadedImages.value.forEach(item => revokePreview(item.preview))
}

const cleanup = async () => {
  clearPreviews()
  uploadedImages.value = []
  templateApplyStore.setDirtyState(false)
  templateApplyStore.setPendingUploads(false)
  setSubmittedTaskId(null)
}

const initializeFromContext = () => {
  prompt.value = props.context.prompt ?? ''
  templateSourcePostId.value = props.context.sourcePostId
  selectedLora.value = isFreeEditV2TaskType.value ? '' : (props.context.loraName ?? '')
  customLoraStrength.value = props.context.loraStrength
    ?? (selectedLora.value ? (LORA_DEFAULT_STRENGTHS[selectedLora.value] || 1.0) : 1.0)
  isTemplateApplied.value = true

  initialPrompt.value = prompt.value.trim()
  initialSelectedLora.value = selectedLora.value
  initialLoraStrength.value = Number(customLoraStrength.value)
}

const resolveSubmitTaskType = () => {
  if (!isFreeEditV2TaskType.value) {
    return taskType.value
  }
  return uploadedImages.value.length >= 2
    ? PORNMASTER_FLUX2_MULTI_EDIT_TASK_TYPE
    : PORNMASTER_FLUX2_SINGLE_EDIT_TASK_TYPE
}

const beforeUpload = async (rawFile: File | { originFileObj?: File }) => {
  if (uploadedImages.value.length + pendingUploadCount.value >= maxImages.value) {
    message.warning(t('template_apply.image_prompt.max_images_warning', { count: maxImages.value }))
    return false
  }

  const file = rawFile instanceof File ? rawFile : rawFile.originFileObj
  if (!(file instanceof File)) {
    message.error(t('template_apply.image_prompt.upload_read_failed'))
    return false
  }

  const slot = `image_${uploadSlotCounter++}`
  const { objectKey } = await uploadFile(file, { slot })
  if (!objectKey) {
    return false
  }

  uploadedImages.value = [
    ...uploadedImages.value,
    {
      slot,
      key: objectKey,
      preview: URL.createObjectURL(file)
    }
  ]

  return false
}

const handleRemove = (index: number) => {
  const current = uploadedImages.value[index]
  if (current) {
    revokePreview(current.preview)
  }
  uploadedImages.value.splice(index, 1)
}

const handleGenerate = async () => {
  if (uploadedImages.value.length === 0) {
    message.warning(t('template_apply.image_prompt.upload_first'))
    return
  }

  if (!prompt.value.trim()) {
    message.warning(t('template_apply.image_prompt.prompt_required'))
    return
  }

  const payload = buildGenerationTaskPayload({
    taskType: resolveSubmitTaskType(),
    images: uploadedImages.value.map(item => item.key),
    prompt: prompt.value,
    promptTarget: 'topLevel',
    loraName: !isFreeEditV2TaskType.value ? (selectedLora.value || undefined) : undefined,
    loraStrength: !isFreeEditV2TaskType.value && selectedLora.value ? Number(customLoraStrength.value) : undefined,
    isTemplate: isTemplateApplied.value,
    sourcePostId: templateSourcePostId.value,
    normalizeEditLoraTask: taskType.value === 'edit',
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
  clearPreviews()
  templateApplyStore.registerPanelController(null)
  templateApplyStore.setPendingUploads(false)
})
</script>

<template>
  <div class="template-panel flex flex-col lg:flex-row gap-6 min-h-[70vh]">
    <section class="w-full lg:w-[52%] flex flex-col bg-slate-900/70 rounded-2xl border border-slate-700/70 overflow-hidden">
      <div class="p-6 overflow-y-auto flex-1">
        <h2 class="text-2xl font-bold text-slate-100 mb-2">{{ taskTitle }}</h2>
        <p class="text-slate-400 text-sm mb-6">{{ t('template_apply.current_page_desc') }}</p>

        <div
          v-if="isTemplateApplied"
          class="mb-6 rounded-xl border border-indigo-500/40 bg-indigo-500/15 px-4 py-3 text-sm text-slate-200"
        >
          {{ templateNotice }}
        </div>

        <div
          v-if="showLoraSection"
          class="mb-6 rounded-xl border border-slate-700 bg-slate-800/70 p-4"
        >
          <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.addon_model') }}</div>
          <a-radio-group
            v-model:value="selectedLora"
            button-style="solid"
            class="w-full"
          >
            <a-radio-button
              v-for="option in loraOptions"
              :key="option.value"
              :value="option.value"
              class="mb-2 mr-2"
            >
              {{ option.label }}
            </a-radio-button>
          </a-radio-group>

          <div v-if="selectedLora" class="mt-4">
            <div class="flex items-center justify-between text-xs text-slate-400 mb-2">
              <span>{{ t('template_apply.common.model_strength') }}</span>
              <span>{{ customLoraStrength.toFixed(2) }}</span>
            </div>
            <a-slider
              v-model:value="customLoraStrength"
              :min="0.1"
              :max="2"
              :step="0.05"
            />
          </div>
        </div>

        <div class="mb-6">
          <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.image_prompt.upload_image') }}</div>
          <a-upload-dragger
            :before-upload="beforeUpload"
            :show-upload-list="false"
            accept="image/*"
            class="template-upload"
          >
            <p class="ant-upload-drag-icon">
              <InboxOutlined class="text-cyan-400" />
            </p>
            <p class="text-slate-200">{{ t('template_apply.common.upload_reference_image') }}</p>
            <p class="text-slate-400 text-xs">{{ t('template_apply.common.upload_limit', { count: maxImages }) }}</p>
          </a-upload-dragger>

          <div v-if="isAnyUploading" class="mt-3 space-y-2">
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

          <div class="mt-4 grid grid-cols-2 gap-3">
            <div
              v-for="(image, index) in uploadedImages"
              :key="image.slot"
              class="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950/80"
            >
              <img :src="image.preview" class="h-32 w-full object-cover" />
              <button
                class="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white"
                @click="handleRemove(index)"
              >
                <CloseCircleOutlined />
              </button>
            </div>
          </div>
        </div>

        <div v-if="!isPromptLocked" class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
          <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.prompt') }}</div>
          <a-textarea
            v-model:value="prompt"
            :rows="8"
            :placeholder="t('template_apply.image_prompt.prompt_placeholder')"
          />
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
          :disabled="isAnyUploading"
          @click="handleGenerate"
        >
          {{ t('template_apply.common.start_generate') }}
        </a-button>
      </div>
    </section>

    <section class="w-full lg:w-[48%] flex flex-col bg-slate-900/70 rounded-2xl border border-slate-700/70 overflow-hidden">
      <div class="p-6 border-b border-slate-700">
        <h3 class="text-lg font-semibold text-slate-100">{{ t('template_apply.common.result_title') }}</h3>
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        <div
          v-if="currentTask"
          class="space-y-4"
        >
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
            <div class="flex items-center justify-between text-sm text-slate-300">
              <span>{{ currentTask.title }}</span>
              <span>
                {{
                  currentTask.status === 'cancelled'
                    ? '已取消'
                      : currentTask.cancelRequested
                        ? '撤销确认中'
                        : currentTask.awaitingResult
                          ? '保存结果中'
                          : currentTask.status === 'pending'
                            ? '排队中'
                            : currentTask.status === 'running'
                              ? '生成中'
                              : currentTask.status
                }}
              </span>
            </div>
            <div
              v-if="currentTask.status === 'pending' && currentTask.queuePos != null"
              class="mt-3 text-sm text-slate-400"
            >
              当前排在第 {{ currentTask.queuePos + 1 }} 位
            </div>
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
            <video
              v-if="isVideoUrl(currentTask.resultUrl)"
              :src="currentTask.resultUrl"
              controls
              class="w-full rounded-xl"
            />
            <img
              v-else
              :src="currentTask.resultUrl"
              class="w-full rounded-xl object-contain"
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
</style>
