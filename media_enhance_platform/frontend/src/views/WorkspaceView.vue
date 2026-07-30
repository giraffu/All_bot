<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock3, Download, FileUp, Image, LoaderCircle, Sparkles, Trash2, Video } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { api, downloadFile } from '@/api'
import { quotePoints } from '@/pricing'
import { useAuthStore } from '@/stores/auth'
import type { MediaFile, Task, TaskType } from '@/types'

const { t } = useI18n()
const auth = useAuthStore()
const selectedFile = ref<File | null>(null)
const uploaded = ref<MediaFile | null>(null)
const files = ref<MediaFile[]>([])
const tasks = ref<Task[]>([])
const taskType = ref<TaskType>('image_upscale')
const multiplier = ref(2)
const pending = ref(false)
const error = ref('')
let timer: number | undefined

const availableTypes = computed<TaskType[]>(() =>
  uploaded.value?.media_kind === 'video'
    ? ['video_upscale', 'frame_interpolation']
    : ['image_upscale'],
)
const multiplierOptions = computed(() => {
  if (taskType.value === 'video_upscale') return [2]
  return [2, 4]
})
const quote = computed(() => {
  if (!uploaded.value) return 0
  return quotePoints(taskType.value, multiplier.value, uploaded.value.duration_seconds)
})

function choose(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
  uploaded.value = null
  taskType.value = selectedFile.value?.type.startsWith('video/') ? 'video_upscale' : 'image_upscale'
  multiplier.value = 2
}

async function upload() {
  if (!selectedFile.value) return
  pending.value = true
  error.value = ''
  const body = new FormData()
  body.append('file', selectedFile.value)
  try {
    uploaded.value = await api<MediaFile>('/uploads', { method: 'POST', body })
    await loadFiles()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'upload_failed'
  } finally {
    pending.value = false
  }
}

async function submit() {
  if (!uploaded.value) return
  pending.value = true
  error.value = ''
  try {
    await api<Task>('/tasks', {
      method: 'POST',
      body: JSON.stringify({
        source_file_id: uploaded.value.id,
        task_type: taskType.value,
        multiplier: multiplier.value,
      }),
    })
    selectedFile.value = null
    uploaded.value = null
    await Promise.all([loadTasks(), auth.refreshMe()])
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'submit_failed'
  } finally {
    pending.value = false
  }
}

async function loadTasks() {
  tasks.value = await api<Task[]>('/tasks')
}
async function loadFiles() {
  files.value = await api<MediaFile[]>('/uploads')
}
async function cancel(task: Task) {
  await api(`/tasks/${task.id}/cancel`, { method: 'POST' })
  await Promise.all([loadTasks(), auth.refreshMe()])
}
async function remove(file: MediaFile) {
  if (!confirm(`${t('common.delete')} ${file.original_name}?`)) return
  await api(`/uploads/${file.id}`, { method: 'DELETE' })
  await loadFiles()
}
async function downloadResult(fileId: string) {
  await downloadFile(fileId)
}
function statusLabel(task: Task) {
  return task.status_reason === 'no_worker_online'
    ? t('workspace.noWorker')
    : t(`workspace.status.${task.status}`)
}

onMounted(async () => {
  await Promise.all([loadTasks(), loadFiles()])
  timer = window.setInterval(loadTasks, 5000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <section class="app-page">
    <div class="app-heading">
      <div><span class="section-index">CREATE</span><h1>{{ t('workspace.title') }}</h1><p>{{ t('workspace.subtitle') }}</p></div>
      <div class="balance-card">
        <span>{{ t('common.available') }}</span><b>{{ auth.user?.available_points }}</b>
        <small>{{ t('common.reserved') }} · {{ auth.user?.reserved_points }}</small>
      </div>
    </div>

    <div class="workspace-grid">
      <div class="composer-card">
        <div class="composer-step"><b>01</b><span>{{ t('common.upload') }}</span></div>
        <label class="upload-zone">
          <input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm" @change="choose" />
          <FileUp :size="32" />
          <strong>{{ selectedFile?.name || t('workspace.drop') }}</strong>
          <span>{{ t('workspace.browse') }}</span>
        </label>
        <button v-if="selectedFile && !uploaded" class="glass-button full" :disabled="pending" @click="upload">
          <LoaderCircle v-if="pending" class="spin" :size="17" />{{ t('common.upload') }}
        </button>
        <div v-if="uploaded" class="selected-file">
          <Image v-if="uploaded.media_kind === 'image'" :size="22" /><Video v-else :size="22" />
          <div><b>{{ uploaded.original_name }}</b><span>{{ Math.round(uploaded.size_bytes / 1024) }} KB</span></div>
          <i>✓</i>
        </div>
      </div>

      <div class="composer-card" :class="{ disabled: !uploaded }">
        <div class="composer-step"><b>02</b><span>{{ t('workspace.method') }}</span></div>
        <div class="method-grid">
          <button v-for="type in availableTypes" :key="type" :class="{ active: taskType === type }" @click="taskType = type; multiplier = 2">
            <Sparkles :size="20" /><b>{{ t(`workspace.types.${type}`) }}</b>
          </button>
        </div>
        <label class="select-label">{{ t('workspace.multiplier') }}
          <select v-model="multiplier"><option v-for="item in multiplierOptions" :key="item" :value="item">{{ item }}×</option></select>
        </label>
        <div class="quote-row"><span>{{ t('workspace.quote') }}</span><b>{{ quote }} {{ t('common.points') }}</b></div>
        <p class="queue-notice"><Clock3 :size="15" />{{ t('workspace.queueNote') }}</p>
        <p v-if="error" class="error-text">{{ error }}</p>
        <button class="primary-button large full" :disabled="!uploaded || pending" @click="submit">{{ t('common.submit') }}</button>
      </div>
    </div>

    <section class="data-section">
      <div class="data-heading"><h2>{{ t('workspace.tasks') }}</h2><span>{{ tasks.length }}</span></div>
      <div v-if="tasks.length" class="task-list">
        <article v-for="task in tasks" :key="task.id" class="task-card">
          <div class="task-icon"><Image v-if="task.task_type === 'image_upscale'" :size="20" /><Video v-else :size="20" /></div>
          <div class="task-main">
            <div><h3>{{ t(`workspace.types.${task.task_type}`) }} · {{ task.multiplier }}×</h3><small>{{ new Date(task.created_at).toLocaleString() }} · {{ task.id.slice(0, 8) }}</small></div>
            <div class="progress-track"><i :style="{ width: `${task.progress}%` }"></i></div>
          </div>
          <span class="status-pill" :class="task.status">{{ statusLabel(task) }}</span>
          <div class="task-actions">
            <button v-if="task.output_file_id" class="icon-button" @click="downloadResult(task.output_file_id)"><Download :size="17" /></button>
            <button v-if="task.status === 'queued' || task.status === 'claimed'" class="icon-button" @click="cancel(task)">{{ t('common.cancel') }}</button>
          </div>
        </article>
      </div>
      <div v-else class="empty-state">{{ t('common.none') }}</div>
    </section>

    <section class="data-section">
      <div class="data-heading"><h2>{{ t('common.upload') }}</h2><span>{{ files.filter(file => !file.deleted_at).length }}</span></div>
      <div class="file-grid">
        <article v-for="file in files.filter(item => !item.deleted_at)" :key="file.id" class="file-card">
          <Image v-if="file.media_kind === 'image'" :size="20" /><Video v-else :size="20" />
          <div><b>{{ file.original_name }}</b><small>{{ (file.size_bytes / 1024 / 1024).toFixed(1) }} MB</small></div>
          <button class="icon-button danger" @click="remove(file)"><Trash2 :size="16" /></button>
        </article>
      </div>
    </section>
  </section>
</template>
