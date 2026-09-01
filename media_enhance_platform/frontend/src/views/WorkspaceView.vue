<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  CheckCircle2,
  Clock3,
  Download,
  FileUp,
  Gauge,
  HardDrive,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  Trash2,
  Video,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { api, downloadFile } from '@/api'
import { quotePoints } from '@/pricing'
import { useAuthStore } from '@/stores/auth'
import type { MediaFile, Task, TaskStatus } from '@/types'
import {
  VIDEO_UPSCALE_MAX_BYTES,
  VIDEO_UPSCALE_MAX_SECONDS,
  VIDEO_UPSCALE_MULTIPLIER,
  validateVideoSelection,
  type VideoSelectionError,
} from '@/videoUpscale'

interface VideoMetadata {
  duration: number
  width: number
  height: number
}

const { t, locale } = useI18n()
const auth = useAuthStore()
const selectedFile = ref<File | null>(null)
const selectedMetadata = ref<VideoMetadata | null>(null)
const previewUrl = ref('')
const uploaded = ref<MediaFile | null>(null)
const files = ref<MediaFile[]>([])
const tasks = ref<Task[]>([])
const dragActive = ref(false)
const pendingStage = ref<'metadata' | 'upload' | 'submit' | null>(null)
const error = ref('')
let timer: number | undefined

const quote = computed(() =>
  selectedMetadata.value
    ? quotePoints('video_upscale', VIDEO_UPSCALE_MULTIPLIER, selectedMetadata.value.duration)
    : 0,
)
const activeStatuses = new Set<TaskStatus>([
  'queued',
  'claimed',
  'preprocessing',
  'running',
  'uploading',
])
const predictedResolution = computed(() => {
  if (!selectedMetadata.value) return '—'
  return `${selectedMetadata.value.width * 2} × ${selectedMetadata.value.height * 2}`
})
const isPending = computed(() => pendingStage.value !== null)

function releasePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

function resetSelection() {
  releasePreview()
  selectedFile.value = null
  selectedMetadata.value = null
  uploaded.value = null
}

function errorLabel(code: string) {
  const known = [
    'video_only',
    'unsupported_video',
    'video_too_large',
    'video_too_long',
    'video_metadata_failed',
    'video_upscale_max_5_seconds',
    'video_upscale_max_40_mb',
    'insufficient_points',
    'no_worker_online',
    'request_failed',
  ]
  return known.includes(code) ? t(`workspace.errors.${code}`) : t('workspace.errors.request_failed')
}

function readVideoMetadata(file: File, url: string): Promise<VideoMetadata> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.onloadedmetadata = () => {
      const metadata = {
        duration: video.duration,
        width: video.videoWidth,
        height: video.videoHeight,
      }
      video.removeAttribute('src')
      video.load()
      resolve(metadata)
    }
    video.onerror = () => reject(new Error('video_metadata_failed'))
    video.src = url
  })
}

async function selectVideo(file: File | null) {
  resetSelection()
  error.value = ''
  if (!file) return
  const basicError = validateVideoSelection(file, 1)
  if (basicError && basicError !== 'video_too_long') {
    error.value = errorLabel(basicError)
    return
  }
  pendingStage.value = 'metadata'
  const url = URL.createObjectURL(file)
  try {
    const metadata = await readVideoMetadata(file, url)
    const validation = validateVideoSelection(file, metadata.duration)
    if (validation) {
      throw new Error(validation)
    }
    selectedFile.value = file
    selectedMetadata.value = metadata
    previewUrl.value = url
  } catch (cause) {
    URL.revokeObjectURL(url)
    const code = cause instanceof Error ? cause.message : 'video_metadata_failed'
    error.value = errorLabel(code as VideoSelectionError)
  } finally {
    pendingStage.value = null
  }
}

function choose(event: Event) {
  const input = event.target as HTMLInputElement
  void selectVideo(input.files?.[0] || null)
  input.value = ''
}

function drop(event: DragEvent) {
  dragActive.value = false
  void selectVideo(event.dataTransfer?.files?.[0] || null)
}

async function uploadSelected(): Promise<MediaFile> {
  if (uploaded.value) return uploaded.value
  if (!selectedFile.value) throw new Error('video_only')
  pendingStage.value = 'upload'
  const body = new FormData()
  body.append('file', selectedFile.value)
  const media = await api<MediaFile>('/uploads', { method: 'POST', body })
  uploaded.value = media
  await loadFiles()
  return media
}

async function submit() {
  if (!selectedFile.value || !selectedMetadata.value) return
  error.value = ''
  try {
    const media = await uploadSelected()
    pendingStage.value = 'submit'
    await api<Task>('/tasks', {
      method: 'POST',
      body: JSON.stringify({
        source_file_id: media.id,
        task_type: 'video_upscale',
        multiplier: VIDEO_UPSCALE_MULTIPLIER,
      }),
    })
    resetSelection()
    await Promise.all([loadTasks(), auth.refreshMe()])
  } catch (cause) {
    const code = cause instanceof Error ? cause.message : 'request_failed'
    error.value = errorLabel(code)
  } finally {
    pendingStage.value = null
  }
}

async function loadTasks(refreshBalance = false) {
  tasks.value = await api<Task[]>('/tasks')
  if (refreshBalance) await auth.refreshMe()
}

async function loadFiles() {
  files.value = await api<MediaFile[]>('/uploads')
}

async function cancel(task: Task) {
  try {
    await api(`/tasks/${task.id}/cancel`, { method: 'POST' })
    await Promise.all([loadTasks(), auth.refreshMe()])
  } catch (cause) {
    error.value = errorLabel(cause instanceof Error ? cause.message : 'request_failed')
  }
}

async function remove(file: MediaFile) {
  if (!confirm(`${t('common.delete')} ${file.original_name}?`)) return
  await api(`/uploads/${file.id}`, { method: 'DELETE' })
  await loadFiles()
}

async function downloadResult(fileId: string, taskId: string) {
  await downloadFile(fileId, `clarity-${taskId.slice(0, 8)}-2x.mp4`)
}

function statusLabel(task: Task) {
  if (task.status_reason === 'no_worker_online') return t('workspace.noWorker')
  if (task.status_reason === 'provider_recovery') return t('workspace.reconnecting')
  return t(`workspace.status.${task.status}`)
}

function formatDuration(seconds: number | null) {
  return seconds === null ? '—' : `${seconds.toFixed(2)}s`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(locale.value === 'zh' ? 'zh-CN' : 'en', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

onMounted(async () => {
  await Promise.all([loadTasks(), loadFiles()])
  timer = window.setInterval(() => void loadTasks(true), 4000)
})
onBeforeUnmount(() => {
  window.clearInterval(timer)
  releasePreview()
})
</script>

<template>
  <section class="app-page video-workspace">
    <div class="app-heading">
      <div>
        <span class="section-index">VIDEO UPSCALE · TEST WORKER</span>
        <h1>{{ t('workspace.title') }}</h1>
        <p>{{ t('workspace.subtitle') }}</p>
      </div>
      <div class="balance-card">
        <span>{{ t('common.available') }}</span><b>{{ auth.user?.available_points }}</b>
        <small>{{ t('common.reserved') }} · {{ auth.user?.reserved_points }}</small>
      </div>
    </div>

    <div class="worker-contract-bar">
      <span><Video :size="15" /> MP4 / MOV / WebM</span>
      <span><Clock3 :size="15" /> ≤ {{ VIDEO_UPSCALE_MAX_SECONDS }}s</span>
      <span><HardDrive :size="15" /> ≤ {{ VIDEO_UPSCALE_MAX_BYTES / 1024 / 1024 }}MB</span>
      <span><Gauge :size="15" /> 2×</span>
      <small>{{ t('workspace.testWorkerBadge') }}</small>
    </div>

    <div class="workspace-grid video-composer-grid">
      <div class="composer-card source-composer">
        <div class="composer-step"><b>01</b><span>{{ t('workspace.chooseVideo') }}</span></div>
        <label
          v-if="!selectedFile"
          class="upload-zone video-upload-zone"
          :class="{ dragging: dragActive }"
          @dragenter.prevent="dragActive = true"
          @dragover.prevent="dragActive = true"
          @dragleave.prevent="dragActive = false"
          @drop.prevent="drop"
        >
          <input type="file" accept="video/mp4,video/quicktime,video/webm" @change="choose" />
          <LoaderCircle v-if="pendingStage === 'metadata'" class="spin" :size="32" />
          <FileUp v-else :size="32" />
          <strong>{{ t('workspace.dropVideo') }}</strong>
          <span>{{ t('workspace.videoHint') }}</span>
        </label>
        <div v-else class="video-selection">
          <video :src="previewUrl" controls muted playsinline preload="metadata"></video>
          <div class="selected-file video-file-summary">
            <Video :size="22" />
            <div><b>{{ selectedFile.name }}</b><span>{{ (selectedFile.size / 1024 / 1024).toFixed(1) }} MB</span></div>
            <button class="icon-button" :aria-label="t('workspace.replaceVideo')" @click="resetSelection"><RotateCcw :size="16" /></button>
          </div>
          <div class="media-facts">
            <span><small>{{ t('workspace.sourceResolution') }}</small><b>{{ selectedMetadata?.width }} × {{ selectedMetadata?.height }}</b></span>
            <span><small>{{ t('workspace.duration') }}</small><b>{{ formatDuration(selectedMetadata?.duration ?? null) }}</b></span>
            <span><small>{{ t('workspace.outputResolution') }}</small><b>{{ predictedResolution }}</b></span>
          </div>
        </div>
        <p v-if="error" class="error-text workspace-error">{{ error }}</p>
      </div>

      <div class="composer-card processing-composer">
        <div class="composer-step"><b>02</b><span>{{ t('workspace.processingPlan') }}</span></div>
        <div class="active-method-card">
          <span><ShieldCheck :size="21" /></span>
          <div><b>{{ t('workspace.types.video_upscale') }}</b><small>{{ t('workspace.videoMethodDesc') }}</small></div>
          <CheckCircle2 :size="19" />
        </div>
        <div class="processing-specs">
          <div><span>{{ t('workspace.multiplier') }}</span><b>2×</b></div>
          <div><span>{{ t('workspace.audio') }}</span><b>{{ t('workspace.preserved') }}</b></div>
          <div><span>{{ t('workspace.quote') }}</span><b>{{ quote }} {{ t('common.points') }}</b></div>
        </div>
        <p class="queue-notice"><Clock3 :size="15" />{{ t('workspace.queueNote') }}</p>
        <button class="primary-button large full start-enhance-button" :disabled="!selectedFile || isPending" @click="submit">
          <LoaderCircle v-if="isPending" class="spin" :size="18" />
          {{ pendingStage === 'upload' ? t('workspace.uploading') : pendingStage === 'submit' ? t('workspace.submitting') : t('workspace.startVideo') }}
        </button>
        <small class="submit-footnote">{{ t('workspace.billingNote') }}</small>
      </div>
    </div>

    <section class="data-section task-section">
      <div class="data-heading"><h2>{{ t('workspace.tasks') }}</h2><span>{{ tasks.length }}</span></div>
      <div v-if="tasks.length" class="task-list">
        <article v-for="task in tasks" :key="task.id" class="task-card video-task-card">
          <div class="task-icon"><Video :size="20" /></div>
          <div class="task-main">
            <div>
              <h3>{{ t('workspace.types.video_upscale') }} · 2×</h3>
              <small>{{ formatDate(task.created_at) }} · {{ task.id.slice(0, 8) }} · {{ task.cost_points }} {{ t('common.points') }}</small>
            </div>
            <div class="task-progress-block">
              <div class="progress-track"><i :style="{ width: `${task.progress}%` }"></i></div>
              <small>{{ task.progress }}%</small>
            </div>
          </div>
          <span class="status-pill" :class="task.status">{{ statusLabel(task) }}</span>
          <div class="task-actions">
            <button v-if="task.output_file_id" class="icon-button download-action" @click="downloadResult(task.output_file_id, task.id)"><Download :size="17" /><span>{{ t('common.download') }}</span></button>
            <button v-else-if="activeStatuses.has(task.status)" class="icon-button" @click="cancel(task)">{{ t('common.cancel') }}</button>
          </div>
        </article>
      </div>
      <div v-else class="empty-state video-empty-state"><Video :size="25" /><span>{{ t('workspace.noTasks') }}</span></div>
    </section>

    <section class="data-section source-library">
      <div class="data-heading"><h2>{{ t('workspace.sourceLibrary') }}</h2><span>{{ files.filter(file => !file.deleted_at && !file.is_output).length }}</span></div>
      <div v-if="files.some(file => !file.deleted_at && !file.is_output)" class="file-grid">
        <article v-for="file in files.filter(item => !item.deleted_at && !item.is_output)" :key="file.id" class="file-card">
          <Video :size="20" />
          <div><b>{{ file.original_name }}</b><small>{{ (file.size_bytes / 1024 / 1024).toFixed(1) }} MB · {{ formatDuration(file.duration_seconds) }}</small></div>
          <button class="icon-button danger" @click="remove(file)"><Trash2 :size="16" /></button>
        </article>
      </div>
      <div v-else class="empty-state compact-empty">{{ t('workspace.noSources') }}</div>
    </section>
  </section>
</template>
