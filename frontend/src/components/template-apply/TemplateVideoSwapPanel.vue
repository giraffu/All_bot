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
import { useSwapTaskSubmit } from '@/composables/useSwapTaskSubmit'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { TemplateApplyContext } from '@/types/templateApply'
import { resolveTierBillingResolution } from '@/utils/templateVideoSettings'

interface UploadedAsset {
  key: string | null
  preview: string | null
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

const faceAsset = ref<UploadedAsset>({ key: null, preview: null })
const targetAsset = ref<UploadedAsset>({ key: null, preview: null })
const resolution = ref('720')
const initialFaceKey = ref<string | null>(null)
const initialTargetKey = ref<string | null>(null)
const initialResolution = ref('720')
const templateSourcePostId = ref<number | null>(null)
const isTemplateApplied = ref(false)
const isTargetLocked = computed(() => isTemplateApplied.value && !!initialTargetKey.value)

const revokePreview = (preview: string | null) => {
  if (preview?.startsWith('blob:')) {
    URL.revokeObjectURL(preview)
  }
}

const updateAsset = (target: typeof faceAsset, key: string | null, preview: string | null) => {
  revokePreview(target.value.preview)
  target.value = { key, preview }
}

watch(
  () => hasPendingUploads.value,
  (pending) => {
    templateApplyStore.setPendingUploads(pending)
  },
  { immediate: true }
)

watch(
  [faceAsset, targetAsset, resolution],
  () => {
    const isDirty =
      faceAsset.value.key !== initialFaceKey.value
      || targetAsset.value.key !== initialTargetKey.value
      || resolution.value !== initialResolution.value
    templateApplyStore.setDirtyState(isDirty)
  },
  { immediate: true, deep: true }
)

const cleanup = async () => {
  revokePreview(faceAsset.value.preview)
  revokePreview(targetAsset.value.preview)
  faceAsset.value = { key: null, preview: null }
  targetAsset.value = { key: null, preview: null }
  templateApplyStore.setDirtyState(false)
  templateApplyStore.setPendingUploads(false)
  setSubmittedTaskId(null)
}

const initializeFromContext = () => {
  isTemplateApplied.value = props.context.rawTaskType === 'face_video'
  templateSourcePostId.value = props.context.sourcePostId

  const targetKey = props.context.inputFile ?? null
  const targetPreview = props.context.inputFileUrl ?? null
  targetAsset.value = {
    key: targetKey,
    preview: targetPreview
  }

  const normalizedResolution = resolveTierBillingResolution({
    billing_resolution: props.context.billingResolution,
    width: props.context.width,
    height: props.context.height
  })
  resolution.value = normalizedResolution === '1024' ? '1024' : '720'
  initialFaceKey.value = null
  initialTargetKey.value = targetKey
  initialResolution.value = resolution.value
}

const handleUpload = async (
  rawFile: File | { originFileObj?: File },
  slot: 'face_image' | 'target_video',
  target: typeof faceAsset
) => {
  const file = rawFile instanceof File ? rawFile : rawFile.originFileObj
  if (!(file instanceof File)) {
    message.error(t('template_apply.image_prompt.upload_read_failed'))
    return false
  }

  const { objectKey } = await uploadFile(file, { slot })
  if (!objectKey) {
    return false
  }

  updateAsset(target, objectKey, URL.createObjectURL(file))
  return false
}

const beforeUploadFace = (rawFile: File | { originFileObj?: File }) =>
  handleUpload(rawFile, 'face_image', faceAsset)

const beforeUploadTarget = (rawFile: File | { originFileObj?: File }) => {
  if (isTargetLocked.value) {
    message.warning(t('template_apply.video_swap.target_locked'))
    return false
  }

  return handleUpload(rawFile, 'target_video', targetAsset)
}

const handleRemoveFace = () => {
  updateAsset(faceAsset, null, null)
}

const handleRemoveTarget = () => {
  if (isTargetLocked.value) {
    return
  }
  updateAsset(targetAsset, null, null)
}

const { handleGenerate } = useSwapTaskSubmit({
  taskType: 'face_video',
  taskTitle: t('template_apply.video_swap.title'),
  targetField: 'target_video',
  getFaceAssetKey: () => faceAsset.value.key,
  getTargetAssetKey: () => targetAsset.value.key,
  getResolution: () => Number(resolution.value),
  getIsTemplateApplied: () => isTemplateApplied.value,
  getSourcePostId: () => templateSourcePostId.value,
  warningMessage: t('template_apply.video_swap.upload_required'),
  submitTask,
  setSubmittedTaskId,
})

onMounted(() => {
  initializeFromContext()
  templateApplyStore.setDirtyState(false)
  setSubmittedTaskId(null)
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
        <h2 class="text-2xl font-bold text-slate-100 mb-2">{{ t('template_apply.video_swap.title') }}</h2>
        <p class="text-slate-400 text-sm mb-6">{{ t('template_apply.video_swap.current_page_desc') }}</p>

        <div
          v-if="isTemplateApplied"
          class="mb-6 rounded-xl border border-indigo-500/40 bg-indigo-500/15 px-4 py-3 text-sm text-slate-200"
        >
          {{ t('template_apply.video_swap.template_notice') }}
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] gap-4">
          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
            <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.face_image') }}</div>
            <div v-if="faceAsset.preview" class="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950/80">
              <img :src="faceAsset.preview" class="h-56 w-full object-contain bg-slate-950/80" />
              <button
                class="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white"
                @click="handleRemoveFace"
              >
                <CloseCircleOutlined />
              </button>
            </div>
            <a-upload-dragger
              v-else
              :before-upload="beforeUploadFace"
              :show-upload-list="false"
              accept="image/*"
              class="template-upload"
            >
              <p class="ant-upload-drag-icon">
                <InboxOutlined class="text-cyan-400" />
              </p>
              <p class="text-slate-200">{{ t('template_apply.common.upload_face_image') }}</p>
              <p class="text-slate-400 text-xs">{{ t('template_apply.video_swap.face_hint') }}</p>
            </a-upload-dragger>
          </div>

          <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
            <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.target_video') }}</div>
            <div v-if="targetAsset.preview" class="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950/80">
              <video :src="targetAsset.preview" controls class="h-56 w-full object-contain bg-slate-950/80" />
              <button
                v-if="!isTargetLocked"
                class="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white"
                @click="handleRemoveTarget"
              >
                <CloseCircleOutlined />
              </button>
            </div>
            <a-upload-dragger
              v-else
              :before-upload="beforeUploadTarget"
              :show-upload-list="false"
              accept="video/mp4,video/quicktime,video/webm"
              class="template-upload"
            >
              <p class="ant-upload-drag-icon">
                <VideoCameraOutlined class="text-cyan-400" />
              </p>
              <p class="text-slate-200">{{ t('template_apply.common.upload_target_video') }}</p>
              <p class="text-slate-400 text-xs">{{ t('template_apply.video_swap.template_target_hint') }}</p>
            </a-upload-dragger>
          </div>
        </div>

        <div class="mt-6 rounded-xl border border-slate-700 bg-slate-800/70 p-4">
          <div class="text-sm font-semibold text-slate-200 mb-3">{{ t('template_apply.common.output_settings') }}</div>
          <a-radio-group v-model:value="resolution" button-style="solid" class="w-full grid grid-cols-2 gap-2 max-w-[240px]">
            <a-radio-button value="720" class="w-full text-center">720p</a-radio-button>
            <a-radio-button value="1024" class="w-full text-center">1024p</a-radio-button>
          </a-radio-group>
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
          {{ t('template_apply.common.estimated_cost') }} <span class="text-cyan-300 font-semibold">{{ resolution === '1024' ? 36 : 18 }}</span> {{ t('template_apply.common.credits_unit') }}
        </div>
        <a-button
          type="primary"
          size="large"
          :loading="isSubmitting"
          :disabled="hasPendingUploads || !faceAsset.key || !targetAsset.key"
          @click="handleGenerate"
        >
          <template #icon>
            <VideoCameraOutlined />
          </template>
          {{ t('template_apply.common.start_face_swap') }}
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
              <span>{{ currentTask.status }}</span>
            </div>
            <a-progress
              class="mt-3"
              :percent="currentTask.progress"
              :status="currentTask.status === 'failed' ? 'exception' : 'active'"
            />
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
