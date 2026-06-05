<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  InboxOutlined,
  DownloadOutlined,
  VideoCameraOutlined,
  CloseCircleOutlined,
  LinkOutlined,
  RetweetOutlined,
  BranchesOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import GenerationActionBar from '@/components/GenerationActionBar.vue'
import GenerationUploadCard from '@/components/GenerationUploadCard.vue'
import GenerationWorkbenchShell from '@/components/GenerationWorkbenchShell.vue'
import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'
import { getWan22HistoryChain, stitchWan22HistoryChain } from '@/api/gallery'
import type { TaskRecord } from '@/types/gallery'
import { useSingleFileUploadPreview } from '@/composables/useSingleFileUploadPreview'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { useUpload } from '@/composables/useUpload'
import { useViewport } from '@/composables/useViewport'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import {
  DEFAULT_WAN22_VIDEO_V2_COST,
  DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS,
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET,
  getWan22VideoV2Cost,
  normalizeWan22VideoV2DurationSeconds,
  WAN22_VIDEO_V2_DURATION_OPTIONS,
  WAN22_VIDEO_V2_RESOLUTION_OPTIONS,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import {
  buildWan22ChainPrefill,
  type Wan22ChainPrefillErrorReason,
} from '@/features/generation/wan22Chain'
import { useGenerationRouteConfig } from '@/features/generation/generationRouteConfig'
import type { HistoryItem, Wan22ResultMeta } from '@/types/gallery'
import { buildStorageFileUrl } from '@/utils/storageUrl'
import { useTasksStore } from '@/stores/tasks'

const route = useRoute()
const router = useRouter()
const tasksStore = useTasksStore()
const { isMobile } = useViewport()
const { taskTitle, taskCost: baseTaskCost } = useGenerationRouteConfig(route, {
  taskType: 'wan22_video_v2',
  title: '图生视频 v2',
  cost: DEFAULT_WAN22_VIDEO_V2_COST,
})

const { uploadFile: uploadStartFile, uploading: startUploading, progress: startUploadProgress } = useUpload()
const { uploadFile: uploadEndFile, uploading: endUploading, progress: endUploadProgress } = useUpload()
const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()

const {
  fileList: startFileList,
  objectKey: startObjectKey,
  filePreview: startPreview,
  beforeUpload: beforeStartUpload,
  handleRemove: handleRemoveStart,
  setRemoteFile: setRemoteStartFile,
} = useSingleFileUploadPreview({
  uploadFile: uploadStartFile,
})

const {
  fileList: endFileList,
  objectKey: endObjectKey,
  filePreview: endPreview,
  beforeUpload: beforeEndUpload,
  handleRemove: handleRemoveEnd,
  setRemoteFile: setRemoteEndFile,
} = useSingleFileUploadPreview({
  uploadFile: uploadEndFile,
})

const prompt = ref('')
const negativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
const resolutionPreset = ref<Wan22VideoV2ResolutionPreset>(DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET)
const duration = ref(DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS)
const hasEndFrame = computed(() => Boolean(endObjectKey.value))
const taskCost = computed(() => getWan22VideoV2Cost(resolutionPreset.value, duration.value) ?? baseTaskCost.value)
const isStartFrameLocked = computed(() => chainMode.value !== 'default')
const resolvedStartPreview = computed(() => {
  if (startPreview.value) {
    return startPreview.value
  }
  if (startObjectKey.value) {
    return buildStorageFileUrl(startObjectKey.value)
  }
  return null
})
const chainRecords = ref<HistoryItem[]>([])
const chainLoading = ref(false)
const chainStitching = ref(false)
const chainMode = ref<'default' | 'extend' | 'regenerate'>('default')
const chainSourceTaskId = ref<string | null>(null)
const chainPrevTaskId = ref<string | null>(null)
const editingChainTaskIds = ref<string[]>([])
const chainBanner = ref('')
const currentResultChainLoadedForTaskId = ref<string | null>(null)

const currentTaskResultMeta = computed<Wan22ResultMeta>(() => currentTask.value?.resultMeta ?? {})
const canShowCurrentTaskChainActions = computed(
  () => currentTask.value?.status === 'success' && currentTask.value?.id && currentTask.value?.type === 'wan22_video_v2'
)
const currentTaskCanExtend = computed(() => Boolean(currentTask.value?.extraOutputs?.last_frame?.path))
const currentTaskCanStitch = computed(() => Boolean(currentTaskResultMeta.value?.wan22_prev_task_id))
const currentTaskCanRegenerate = computed(() => canShowCurrentTaskChainActions.value)
const activeEditorSegmentIndex = computed(() => {
  if (!chainSourceTaskId.value) {
    return null
  }
  const index = chainRecords.value.findIndex(record => record.task_id === chainSourceTaskId.value)
  return index >= 0 ? index : null
})
const activeSubmitChainTaskIds = computed(() => {
  if (chainMode.value === 'default') {
    return []
  }
  if (editingChainTaskIds.value.length) {
    return editingChainTaskIds.value
  }
  return chainRecords.value
    .map(record => record.task_id)
    .filter((taskId): taskId is string => Boolean(taskId))
})
const editorModeLabel = computed(() => {
  if (chainMode.value === 'extend') {
    return '扩展下一段'
  }
  if (chainMode.value === 'regenerate') {
    return '重生成当前段'
  }
  return '独立首段'
})
const editorContextSummary = computed(() => {
  if (chainMode.value === 'default') {
    return '上传起始帧即可开始首段，成功后可继续向后无限扩展。'
  }
  const segmentText = activeEditorSegmentIndex.value !== null
    ? `第 ${activeEditorSegmentIndex.value + 1} 段`
    : '当前段'
  const chainCount = activeSubmitChainTaskIds.value.length
  if (chainMode.value === 'extend') {
    return `当前正在从${segmentText}继续扩展，新结果会接在现有 ${chainCount} 段链路之后。`
  }
  return `当前正在重生成${segmentText}，只继承该段之前的 ${chainCount} 段上下文，后续旧分支不会带入本次提交。`
})
const generateButtonText = computed(() => {
  if (chainMode.value === 'extend') {
    return '生成下一段'
  }
  if (chainMode.value === 'regenerate') {
    return '重生成本段'
  }
  return '生成视频'
})
const chainStripClasses = computed(() =>
  isMobile.value
    ? 'flex-col overflow-y-auto max-h-[420px]'
    : 'overflow-x-auto'
)
const chainCardBaseClass = computed(() =>
  isMobile.value ? 'w-full' : 'min-w-[220px]'
)

const resolveChainSummaryText = computed(() => {
  if (!chainRecords.value.length) {
    return '当前是独立单段生成，生成完成后可继续扩展。'
  }
  return `当前链路共 ${chainRecords.value.length} 段，可继续向后扩展，或回到任一中间段重新生成。`
})

const applyRecordToEditor = (
  record: HistoryItem,
  options: {
    mode: 'extend' | 'regenerate'
    startKey: string
    startPreviewUrl: string | null
    endKey?: string | null
    endPreviewUrl?: string | null
    promptValue: string
    negativePromptValue: string
    resolution: Wan22VideoV2ResolutionPreset
    duration: string
    prevTaskId: string | null
    chainTaskIds: string[]
    banner: string
  }
) => {
  chainMode.value = options.mode
  chainSourceTaskId.value = record.task_id
  chainPrevTaskId.value = options.prevTaskId
  editingChainTaskIds.value = [...options.chainTaskIds]
  chainBanner.value = options.banner
  setRemoteStartFile(options.startKey, options.startPreviewUrl)
  if (options.endKey) {
    setRemoteEndFile(options.endKey, options.endPreviewUrl ?? null)
  } else {
    handleRemoveEnd()
  }
  prompt.value = options.promptValue
  negativePrompt.value = options.negativePromptValue
  resolutionPreset.value = options.resolution
  duration.value = normalizeWan22VideoV2DurationSeconds(options.duration)
}

const loadWan22Chain = async (taskId: string) => {
  chainLoading.value = true
  try {
    const payload = await getWan22HistoryChain(taskId)
    chainRecords.value = payload.items
    return payload.items
  } catch (error: any) {
    console.error(error)
    message.error(error?.response?.data?.detail || '加载视频链失败，请稍后再试')
    return []
  } finally {
    chainLoading.value = false
  }
}

const resolvePrefillErrorMessage = (reason: Wan22ChainPrefillErrorReason) => {
  const messages: Record<Wan22ChainPrefillErrorReason, string> = {
    history_empty: '未找到对应的链式视频记录',
    record_not_found: '未找到对应段落记录',
    last_frame_missing: '当前段落没有可用尾帧，请先重新生成该段视频',
    previous_record_missing: '上一段记录缺少任务 ID，暂时无法重生成当前段',
    previous_last_frame_missing: '上一段没有可用尾帧，暂时无法重生成当前段',
  }
  return messages[reason]
}

const prefillFromChain = async (mode: 'extend' | 'regenerate', taskId: string) => {
  const items = await loadWan22Chain(taskId)
  const prefill = buildWan22ChainPrefill(mode, taskId, items)
  if (prefill.status === 'error') {
    message.warning(resolvePrefillErrorMessage(prefill.reason))
    return
  }

  if (prefill.status === 'blank') {
    await resetForm()
    chainBanner.value = '已切换为首段重新生成，请重新上传起始帧和可选终止帧。'
    return
  }

  const currentRecord = items.find(item => item.task_id === prefill.sourceTaskId)
  if (!currentRecord) {
    message.warning('未找到对应段落记录')
    return
  }

  applyRecordToEditor(currentRecord, {
    mode,
    startKey: prefill.startFrame.key,
    startPreviewUrl: prefill.startFrame.preview,
    endKey: prefill.endFrame?.key ?? null,
    endPreviewUrl: prefill.endFrame?.preview ?? null,
    promptValue: prefill.prompt,
    negativePromptValue: prefill.negativePrompt,
    resolution: prefill.resolutionPreset,
    duration: prefill.duration,
    prevTaskId: prefill.prevTaskId,
    chainTaskIds: prefill.chainTaskIds,
    banner: mode === 'extend'
      ? `已载入第 ${prefill.segmentIndex} 段尾帧，下一段将延续当前链路继续生成。`
      : `已切换为第 ${prefill.segmentIndex} 段重生成模式，将复用上一段尾帧和当前段参数。`,
  })

  await router.replace({
    name: 'Wan22VideoV2',
    query: {
      mode,
      task_id: taskId,
    },
  })
}

const handleGenerate = async () => {
  if (!startObjectKey.value) {
    message.warning('请先上传起始帧图片')
    return
  }
  const payload = buildGenerationTaskPayload({
    taskType: 'wan22_video_v2',
    images: hasEndFrame.value && endObjectKey.value
      ? [startObjectKey.value, endObjectKey.value]
      : [startObjectKey.value],
    duration: Number(normalizeWan22VideoV2DurationSeconds(duration.value)),
    prompt: prompt.value,
    negativePrompt: negativePrompt.value,
    promptTarget: 'inputs',
    extraInputs: {
      use_end_frame: hasEndFrame.value,
      resolution_preset: resolutionPreset.value,
      wan22_prev_task_id: chainPrevTaskId.value,
      wan22_chain_task_ids: activeSubmitChainTaskIds.value,
    },
  })

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
    currentResultChainLoadedForTaskId.value = null
  }
}

const resetForm = async () => {
  handleRemoveStart()
  handleRemoveEnd()
  prompt.value = ''
  negativePrompt.value = DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
  resolutionPreset.value = DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
  duration.value = DEFAULT_WAN22_VIDEO_V2_DURATION_SECONDS
  setSubmittedTaskId(null)
  chainMode.value = 'default'
  chainSourceTaskId.value = null
  chainPrevTaskId.value = null
  editingChainTaskIds.value = []
  chainBanner.value = ''
  chainRecords.value = []
  currentResultChainLoadedForTaskId.value = null
  await router.replace({ name: 'Wan22VideoV2', query: {} })
}

const handleStitchCurrentChain = async () => {
  const taskId = currentTask.value?.id
  if (!taskId) {
    return
  }
  chainStitching.value = true
  const hide = message.loading('正在拼接整条视频链...', 0)
  try {
    const stitchedRecord = await stitchWan22HistoryChain(taskId)
    hide()
    message.success('整条链拼接完成，已生成新的闪回瓶记录')
    if (stitchedRecord.task_id) {
      await router.push({
        name: 'History',
        query: {
          task_id: stitchedRecord.task_id,
        },
      })
      return
    }
    if (stitchedRecord.task_id && stitchedRecord.type) {
      tasksStore.showDetailRecord(stitchedRecord as TaskRecord)
    }
  } catch (error: any) {
    console.error(error)
    hide()
    message.error(error?.response?.data?.detail || '拼接失败，请稍后再试')
  } finally {
    chainStitching.value = false
  }
}

watch(
  () => route.query,
  query => {
    const mode = query.mode
    const taskId = query.task_id
    if ((mode === 'extend' || mode === 'regenerate') && typeof taskId === 'string' && taskId) {
      void prefillFromChain(mode, taskId)
    }
  },
  { immediate: true }
)

watch(
  () => currentTask.value?.id,
  async taskId => {
    if (!taskId || currentTask.value?.status !== 'success' || currentTask.value?.type !== 'wan22_video_v2') {
      return
    }
    if (currentResultChainLoadedForTaskId.value === taskId) {
      return
    }
    await loadWan22Chain(taskId)
    currentResultChainLoadedForTaskId.value = taskId
  }
)

onMounted(() => {
  if (!route.query.mode || !route.query.task_id) {
    chainBanner.value = '上传一张起始帧即可开始第一段；生成完成后可继续向后无限扩展。'
  }
})
</script>

<template>
  <GenerationWorkbenchShell :title="`${taskTitle}设置`">
    <template #left-content>
      <div class="flex flex-col gap-6 mb-6">
        <div class="wan22-video-v2__section rounded-xl p-4">
          <div class="flex flex-col gap-3">
            <div class="flex flex-col gap-1 md:flex-row md:items-start md:justify-between">
              <div>
                <h3 class="wan22-video-v2__section-title text-sm font-bold">多段链路工作台</h3>
                <p class="wan22-video-v2__field-label text-xs mt-1">
                  {{ chainBanner || resolveChainSummaryText }}
                </p>
              </div>
              <a-tag color="blue" class="self-start">
                {{ isMobile ? '手机端纵向编辑' : '桌面端链路侧览' }}
              </a-tag>
            </div>
            <div class="wan22-video-v2__editor-card rounded-xl p-3 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <div class="setting-title">{{ editorModeLabel }}</div>
                <div class="setting-desc mt-1">{{ editorContextSummary }}</div>
              </div>
              <a-tag color="cyan" class="self-start">
                已承接 {{ activeSubmitChainTaskIds.length }} 段上下文
              </a-tag>
            </div>
            <div
              class="wan22-video-v2__chain-strip flex gap-3 pb-1"
              :class="[chainStripClasses, { 'wan22-video-v2__chain-strip--empty': !chainRecords.length }]"
            >
              <div
                v-if="!chainRecords.length"
                class="wan22-video-v2__chain-card rounded-xl p-3"
                :class="chainCardBaseClass"
              >
                <div class="setting-title">第 1 段</div>
                <div class="setting-desc mt-1">从工作台直接上传起始帧，开始第一段视频生成。</div>
              </div>
              <button
                v-for="(record, index) in chainRecords"
                :key="record.task_id || index"
                type="button"
                class="wan22-video-v2__chain-card rounded-xl p-3 text-left"
                :class="[
                  chainCardBaseClass,
                  {
                    'wan22-video-v2__chain-card--active': chainSourceTaskId === record.task_id,
                  },
                ]"
                @click="record.task_id && prefillFromChain(record.result_meta?.wan22_prev_task_id ? 'regenerate' : 'extend', record.task_id)"
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="setting-title">第 {{ index + 1 }} 段</div>
                  <div class="flex items-center gap-2">
                    <a-tag v-if="chainSourceTaskId === record.task_id" size="small" color="blue">当前编辑</a-tag>
                    <a-tag size="small" :color="record.result_meta?.wan22_prev_task_id ? 'purple' : 'green'">
                      {{ record.result_meta?.wan22_prev_task_id ? '链中段' : '首段' }}
                    </a-tag>
                  </div>
                </div>
                <div class="setting-desc mt-2 line-clamp-2">
                  {{ record.prompt || '未填写提示词' }}
                </div>
                <div class="wan22-video-v2__chain-actions mt-3 flex flex-wrap gap-2">
                  <a-button
                    size="small"
                    :block="isMobile"
                    @click.stop="record.task_id && prefillFromChain('extend', record.task_id)"
                  >
                    扩展
                  </a-button>
                  <a-button
                    size="small"
                    :block="isMobile"
                    @click.stop="record.task_id && prefillFromChain('regenerate', record.task_id)"
                  >
                    重新生成
                  </a-button>
                </div>
              </button>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <GenerationUploadCard
              :title="isStartFrameLocked ? '起始帧（已锁定）' : '起始帧'"
              step="1."
              :file-list="startFileList"
              :preview-url="resolvedStartPreview"
              accept="image/png, image/jpeg"
              wrapper-class="upload-section flex flex-col w-full min-w-[160px] shrink-0 h-56"
              :before-upload="isStartFrameLocked ? undefined : beforeStartUpload"
              :disabled="isStartFrameLocked"
              :locked="isStartFrameLocked"
              :locked-text="chainMode === 'extend' ? '已锁定为上一段尾帧' : '已锁定为上一段尾帧'"
              @remove="!isStartFrameLocked && handleRemoveStart()"
              @update:fileList="startFileList = $event"
            >
              <template #placeholder-icon>
                <InboxOutlined />
              </template>
            </GenerationUploadCard>
            <div v-if="startUploading" class="mt-2">
              <span class="wan22-video-v2__progress-text text-xs">正在上传起始帧...</span>
              <a-progress :percent="startUploadProgress" status="active" strokeColor="#3b82f6" size="small" />
            </div>
          </div>

          <div>
            <GenerationUploadCard
              title="终止帧（可选）"
              step="2."
              :file-list="endFileList"
              :preview-url="endPreview"
              accept="image/png, image/jpeg"
              wrapper-class="upload-section flex flex-col w-full min-w-[160px] shrink-0 h-56"
              :before-upload="beforeEndUpload"
              @remove="handleRemoveEnd"
              @update:fileList="endFileList = $event"
            >
              <template #placeholder-icon>
                <InboxOutlined />
              </template>
            </GenerationUploadCard>
            <div v-if="endUploading" class="mt-2">
              <span class="wan22-video-v2__progress-text text-xs">正在上传终止帧...</span>
              <a-progress :percent="endUploadProgress" status="active" strokeColor="#3b82f6" size="small" />
            </div>
          </div>
        </div>

        <div class="wan22-video-v2__section rounded-xl p-4">
          <h3 class="wan22-video-v2__section-title text-sm font-bold mb-3">提示词</h3>
          <div class="grid grid-cols-1 gap-4">
            <div>
              <label class="wan22-video-v2__field-label block text-xs font-medium mb-2">正面提示词</label>
              <a-textarea
                v-model:value="prompt"
                :rows="4"
                placeholder="输入视频生成的正向提示词..."
                class="rounded-xl"
              />
            </div>
            <div>
              <label class="wan22-video-v2__field-label block text-xs font-medium mb-2">负面提示词</label>
              <a-textarea
                v-model:value="negativePrompt"
                :rows="3"
                placeholder="输入需要规避的内容..."
                class="rounded-xl"
              />
            </div>
          </div>
        </div>

        <div class="wan22-video-v2__section rounded-xl p-4">
          <h3 class="wan22-video-v2__section-title text-sm font-bold mb-3">生成设置</h3>
          <div class="grid grid-cols-1 gap-3">
            <div class="wan22-video-v2__fixed-card rounded-xl p-3">
              <div class="mb-3">
                <div class="setting-title">生成时长</div>
                <div class="setting-desc">时长越长，消耗灵石越多</div>
              </div>
              <a-radio-group v-model:value="duration" class="w-full">
                <div
                  class="grid"
                  :class="isMobile ? 'grid-cols-2 gap-2' : 'grid-cols-3 gap-3'"
                >
                  <label
                    v-for="option in WAN22_VIDEO_V2_DURATION_OPTIONS"
                    :key="option.value"
                    class="wan22-video-v2__preset-card rounded-xl p-3 cursor-pointer"
                    :class="[
                      { 'wan22-video-v2__preset-card--active': duration === option.value },
                      isMobile ? 'wan22-video-v2__preset-card--compact' : '',
                    ]"
                  >
                    <a-radio :value="option.value">
                      <span class="setting-title">{{ option.label }}</span>
                    </a-radio>
                    <div class="setting-desc mt-2" :class="{ 'wan22-video-v2__preset-desc--compact': isMobile }">
                      {{ option.frameCount }} 帧
                    </div>
                  </label>
                </div>
              </a-radio-group>
            </div>
            <div class="wan22-video-v2__fixed-card rounded-xl p-3">
              <div class="mb-3">
                <div class="setting-title">分辨率档位</div>
                <div class="setting-desc">档位越高越清晰，生成速度会更慢</div>
              </div>
              <a-radio-group v-model:value="resolutionPreset" class="w-full">
                <div
                  class="grid"
                  :class="isMobile ? 'grid-cols-2 gap-2' : 'grid-cols-2 gap-3'"
                >
                  <label
                    v-for="option in WAN22_VIDEO_V2_RESOLUTION_OPTIONS"
                    :key="option.value"
                    class="wan22-video-v2__preset-card rounded-xl p-3 cursor-pointer"
                    :class="[
                      { 'wan22-video-v2__preset-card--active': resolutionPreset === option.value },
                      isMobile ? 'wan22-video-v2__preset-card--compact' : '',
                    ]"
                  >
                    <a-radio :value="option.value">
                      <span class="setting-title">{{ option.label }}</span>
                    </a-radio>
                    <div class="wan22-video-v2__preset-cost mt-2">{{ getWan22VideoV2Cost(option.value, duration) }} 灵石</div>
                    <div class="setting-desc mt-2" :class="{ 'wan22-video-v2__preset-desc--compact': isMobile }">
                      {{ option.description }}
                    </div>
                  </label>
                </div>
              </a-radio-group>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template #left-footer>
      <GenerationActionBar
        :cost="taskCost"
        :button-text="generateButtonText"
        :disabled="!startObjectKey"
        :loading="isSubmitting"
        button-class="bg-blue-600 hover:bg-blue-500 w-40 h-12 text-base font-bold tracking-wider rounded-xl shadow-md transition-all hover:shadow-lg border-none flex items-center justify-center text-white"
        @submit="handleGenerate"
      >
        <template #button-icon><VideoCameraOutlined /></template>
      </GenerationActionBar>
    </template>

    <template #right-panel>
      <TaskResultPreviewPanel
        :current-task="currentTask"
        :is-image-url="isImageUrl"
        @download="downloadResult"
        @reset="resetForm"
      >
        <template #success-media="{ task }">
          <div class="w-full flex flex-col items-center gap-4">
            <video
              :src="task.resultUrl"
              controls
              class="max-w-full max-h-[46vh] rounded-xl shadow-sm bg-black"
            />
          </div>
        </template>
        <template #success-actions="{ task }">
          <div class="mt-8 grid grid-cols-1 sm:flex sm:flex-wrap gap-4 justify-center">
            <a-button
              type="primary"
              size="large"
              class="bg-blue-600 rounded-xl w-full sm:w-auto"
              @click="downloadResult(task.resultUrl, task.title)"
            >
              <template #icon><DownloadOutlined /></template>
              下载视频
            </a-button>
            <a-button
              v-if="canShowCurrentTaskChainActions"
              size="large"
              class="rounded-xl w-full sm:w-auto"
              :disabled="!currentTaskCanExtend"
              @click="task.id && prefillFromChain('extend', task.id)"
            >
              <template #icon><BranchesOutlined /></template>
              扩展生成
            </a-button>
            <a-button
              v-if="canShowCurrentTaskChainActions && currentTaskCanStitch"
              size="large"
              class="rounded-xl w-full sm:w-auto"
              :loading="chainStitching"
              @click="handleStitchCurrentChain"
            >
              <template #icon><LinkOutlined /></template>
              完成整链拼接
            </a-button>
            <a-button
              v-if="canShowCurrentTaskChainActions && currentTaskCanRegenerate"
              size="large"
              class="rounded-xl w-full sm:w-auto"
              @click="task.id && prefillFromChain('regenerate', task.id)"
            >
              <template #icon><RetweetOutlined /></template>
              重新生成
            </a-button>
          </div>
        </template>
        <template #empty-icon>
          <VideoCameraOutlined class="text-6xl mb-4" />
        </template>
        <template #download-icon>
          <DownloadOutlined />
        </template>
        <template #failed-icon>
          <CloseCircleOutlined class="text-5xl text-red-500 mb-4" />
        </template>
      </TaskResultPreviewPanel>
    </template>
  </GenerationWorkbenchShell>
</template>

<style scoped>
:deep(.ant-input),
:deep(.ant-input-affix-wrapper),
:deep(.ant-input-number),
:deep(.ant-input-number-input),
:deep(.ant-textarea) {
  background-color: var(--theme-card-strong-bg) !important;
  color: var(--theme-text-primary) !important;
  -webkit-text-fill-color: var(--theme-text-primary) !important;
  opacity: 1 !important;
  border-color: var(--theme-border) !important;
}

:deep(.ant-input::placeholder),
:deep(.ant-input-number-input::placeholder),
:deep(textarea::placeholder) {
  color: var(--theme-input-placeholder) !important;
}

.setting-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-radius: 12px;
  border: 1px solid var(--theme-border);
  background: var(--theme-panel-bg);
  padding: 12px;
}

.wan22-video-v2__section {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
}

.wan22-video-v2__section-title {
  color: var(--theme-text-primary);
}

.wan22-video-v2__field-label,
.wan22-video-v2__progress-text {
  color: var(--theme-text-secondary);
}

.wan22-video-v2__fixed-card {
  background: color-mix(in srgb, var(--theme-panel-bg) 86%, transparent);
  border: 1px solid var(--theme-border);
}

.wan22-video-v2__editor-card {
  background: color-mix(in srgb, #0ea5e9 8%, var(--theme-panel-bg));
  border: 1px solid color-mix(in srgb, var(--theme-border) 76%, #38bdf8 24%);
}

.wan22-video-v2__fixed-value {
  color: color-mix(in srgb, var(--theme-text-primary) 72%, #06b6d4 28%);
}

.wan22-video-v2__preset-card {
  display: block;
  min-height: 118px;
  border: 1px solid var(--theme-border);
  background: var(--theme-panel-bg);
  transition: border-color 0.2s ease, background 0.2s ease;
}

.wan22-video-v2__preset-card--compact {
  min-height: 110px;
  padding: 10px 8px;
}

.wan22-video-v2__preset-card--active {
  border-color: #2563eb;
  background: color-mix(in srgb, #2563eb 10%, var(--theme-panel-bg));
}

.wan22-video-v2__preset-cost {
  color: color-mix(in srgb, var(--theme-text-primary) 78%, #22d3ee 22%);
  font-size: 0.75rem;
  font-weight: 600;
}

.wan22-video-v2__chain-strip {
  scrollbar-width: thin;
}

.wan22-video-v2__chain-card {
  border: 1px solid var(--theme-border);
  background: var(--theme-panel-bg);
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

.wan22-video-v2__chain-card:hover {
  border-color: var(--theme-border-strong);
  transform: translateY(-1px);
}

.wan22-video-v2__chain-card--active {
  border-color: #2563eb;
  background: color-mix(in srgb, #2563eb 10%, var(--theme-panel-bg));
}

.setting-title {
  color: var(--theme-text-primary);
  font-size: 0.875rem;
  font-weight: 600;
}

.setting-desc {
  color: var(--theme-text-secondary);
  font-size: 0.75rem;
  margin-top: 2px;
}

.wan22-video-v2__preset-desc--compact {
  font-size: 0.6875rem;
  line-height: 1.25;
}

@media (max-width: 767px) {
  .wan22-video-v2__preset-card :deep(.ant-radio-wrapper) {
    align-items: flex-start;
    margin-inline-end: 0;
    width: 100%;
  }

  .wan22-video-v2__preset-card :deep(.ant-radio) {
    top: 1px;
  }

  .wan22-video-v2__preset-card .setting-title {
    font-size: 0.8125rem;
  }

  .wan22-video-v2__preset-cost {
    font-size: 0.6875rem;
  }
}
</style>
