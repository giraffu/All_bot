<script setup lang="ts">
import { computed, ref } from 'vue'
import { CloseCircleOutlined, DownloadOutlined, PictureOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'

import GenerationActionBar from '@/components/GenerationActionBar.vue'
import GenerationWorkbenchShell from '@/components/GenerationWorkbenchShell.vue'
import TaskResultPreviewPanel from '@/components/TaskResultPreviewPanel.vue'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'

const route = useRoute()

const taskType = computed(() => (route.query.type as string) || 'txt2img')
const taskTitle = computed(() => (route.query.title as string) || '文生图')
const taskCost = computed(() => Number(route.query.cost) || 2)

const prompt = ref('')

const { isSubmitting, submitTask } = useTaskStream()
const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()

const canSubmit = computed(() => prompt.value.trim().length > 0)

const handleGenerate = async () => {
  const trimmedPrompt = prompt.value.trim()
  if (!trimmedPrompt) {
    message.warning('请输入提示词！')
    return
  }

  const payload = buildGenerationTaskPayload({
    taskType: taskType.value,
    images: [],
    prompt: trimmedPrompt,
    promptTarget: 'topLevel',
  })

  const taskId = await submitTask(payload, taskTitle.value)
  if (taskId) {
    setSubmittedTaskId(taskId)
  }
}

const resetForm = () => {
  prompt.value = ''
  setSubmittedTaskId(null)
}
</script>

<template>
  <GenerationWorkbenchShell
    :title="taskTitle"
    description="输入提示词，直接发起文生图任务。当前测试版先提供最小参数集。"
    left-panel-class="w-full lg:w-[50%] flex flex-col bg-slate-500/50 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden shrink-0"
    right-panel-class="w-full lg:w-[50%] flex flex-col bg-slate-500/50 backdrop-blur-md rounded-2xl shadow-sm border border-slate-400/50 overflow-hidden relative"
  >
    <template #left-content>
      <div class="flex flex-col gap-6 p-6 flex-grow overflow-y-auto custom-scrollbar">
        <div class="rounded-xl border border-slate-400/50 bg-slate-500/60 p-4">
          <h3 class="text-sm font-bold mb-3 text-slate-200 flex items-center">
            <span class="text-slate-500 mr-2">1.</span> 提示词
          </h3>
          <a-textarea
            v-model:value="prompt"
            :rows="8"
            show-count
            :maxlength="512"
            placeholder="例如：masterpiece, cinematic portrait, moonlight, detailed face, realistic skin, soft rim light"
          />
          <p class="mt-3 text-xs text-slate-400">
            建议直接写清主体、构图、光线、风格和细节要求；首版暂不开放负面提示词与高级参数。
          </p>
        </div>
      </div>
    </template>

    <template #left-footer>
      <GenerationActionBar
        :cost="taskCost"
        button-text="生成图片"
        :disabled="!canSubmit"
        :loading="isSubmitting"
        @submit="handleGenerate"
      >
        <template #button-icon>
          <picture-outlined />
        </template>
      </GenerationActionBar>
    </template>

    <template #right-panel>
      <TaskResultPreviewPanel
        :current-task="currentTask"
        :is-image-url="isImageUrl"
        @download="downloadResult"
        @reset="resetForm"
      >
        <template #empty-icon>
          <picture-outlined class="text-6xl mb-4" />
        </template>
        <template #download-icon>
          <download-outlined />
        </template>
        <template #failed-icon>
          <close-circle-outlined class="text-5xl text-red-500 mb-4" />
        </template>
      </TaskResultPreviewPanel>
    </template>
  </GenerationWorkbenchShell>
</template>

<style scoped>
:deep(.ant-input),
:deep(.ant-input-affix-wrapper),
:deep(.ant-input-textarea textarea) {
  background-color: var(--theme-card-strong-bg) !important;
  color: var(--theme-text-primary) !important;
  border-color: var(--theme-border) !important;
}

:deep(.ant-input::placeholder),
:deep(.ant-input-textarea textarea::placeholder) {
  color: var(--theme-text-muted) !important;
}

:deep(.text-slate-200),
:deep(.text-slate-300) {
  color: var(--theme-text-primary) !important;
}

:deep(.text-slate-400),
:deep(.text-slate-500) {
  color: var(--theme-text-secondary) !important;
}
</style>
