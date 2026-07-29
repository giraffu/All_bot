<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import api from '@/api'
import AvatarViewer from '@/components/AvatarViewer.vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, type ThemePreference } from '@/stores/theme'
import type {
  AnimationId,
  BackgroundId,
  CameraPreset,
  MiniCharacter,
  ModelAsset,
  RenderJob,
  Resolution,
} from '@/types'

const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()
const characters = ref<MiniCharacter[]>([])
const selectedId = ref<string | null>(null)
const loadingCharacters = ref(false)
const createOpen = ref(false)
const settingsOpen = ref(false)
const renderOpen = ref(false)
const viewer = ref<InstanceType<typeof AvatarViewer> | null>(null)
const playing = ref(true)
const animationId = ref<AnimationId>('idle')
const cameraPreset = ref<CameraPreset>('full_body')
const background = ref<BackgroundId>('studio')
const speed = ref(1)
const loop = ref(true)
const progress = ref(0)
const buildError = ref<string | null>(null)
const renderJob = ref<RenderJob | null>(null)
const renderResolution = ref<Resolution>('1280x720')
const renderDuration = ref(3)
const renderFps = ref<24 | 30>(24)
const uploadName = ref('')
const uploadDescription = ref('')
const uploadFile = ref<File | null>(null)
const uploading = ref(false)
let pollTimer: number | null = null

const selected = computed(
  () => characters.value.find((character) => character.id === selectedId.value) || null,
)
const asset = computed(() => selected.value?.latest_model || null)
const isBuilding = computed(() =>
  ['queued', 'preparing_views', 'reconstructing', 'rigging'].includes(asset.value?.status || ''),
)
const buildSteps = ['queued', 'preparing_views', 'reconstructing', 'rigging', 'ready']
const currentBuildStep = computed(() => Math.max(0, buildSteps.indexOf(asset.value?.status || 'queued')))
const animations: AnimationId[] = ['idle', 'turntable', 'photo_pose', 'dance_lite']
const cameras: CameraPreset[] = ['front', 'side', 'back', 'full_body', 'half_body', 'portrait']
const backgrounds: BackgroundId[] = ['studio', 'light', 'dark', 'transparent']

async function loadCharacters(keepSelection = true) {
  loadingCharacters.value = true
  try {
    const { data } = await api.get<MiniCharacter[]>('/miniapp/characters')
    characters.value = data
    if (!keepSelection || !data.some((item) => item.id === selectedId.value)) {
      selectedId.value = data[0]?.id || null
    }
  } finally {
    loadingCharacters.value = false
  }
}

async function refreshAsset() {
  if (!asset.value) return
  const { data } = await api.get<ModelAsset>(`/miniapp/model-assets/${asset.value.id}`)
  if (selected.value) selected.value.latest_model = data
}

function schedulePoll() {
  if (pollTimer) window.clearTimeout(pollTimer)
  if (!isBuilding.value && !['queued', 'rendering'].includes(renderJob.value?.status || '')) return
  pollTimer = window.setTimeout(async () => {
    try {
      if (isBuilding.value) await refreshAsset()
      if (renderJob.value && ['queued', 'rendering'].includes(renderJob.value.status)) {
        const { data } = await api.get<RenderJob>(`/miniapp/renders/${renderJob.value.id}`)
        renderJob.value = data
      }
    } finally {
      schedulePoll()
    }
  }, 1800)
}

watch([isBuilding, () => renderJob.value?.status], schedulePoll)

async function startBuild() {
  if (!selected.value) return
  buildError.value = null
  try {
    const { data } = await api.post<{ asset_id: string; status: string }>(
      `/miniapp/characters/${selected.value.id}/fixture-build`,
    )
    selected.value.latest_model = {
      id: data.asset_id,
      character_id: selected.value.id,
      version: 1,
      provider: 'local_fixture',
      status: data.status,
      error_code: null,
      model_url: null,
      thumbnail_url: null,
      rig_type: null,
      animation_ids: [],
      metadata: {},
      views: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    schedulePoll()
  } catch (error: any) {
    buildError.value = error.response?.data?.reason || error.response?.data?.detail?.reason || 'BUILD_FAILED'
    await loadCharacters()
  }
}

function selectFile(event: Event) {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0] || null
}

async function createCharacter() {
  if (!uploadFile.value || !uploadName.value.trim()) return
  uploading.value = true
  try {
    const params = new URLSearchParams({
      filename: uploadFile.value.name,
      content_type: uploadFile.value.type || 'image/jpeg',
    })
    const { data } = await api.get<{ upload_url: string; object_key: string }>(
      `/storage/presigned-url?${params}`,
    )
    const upload = await fetch(data.upload_url, {
      method: 'PUT',
      headers: { 'Content-Type': uploadFile.value.type || 'image/jpeg' },
      body: uploadFile.value,
    })
    if (!upload.ok) throw new Error('UPLOAD_FAILED')
    const response = await api.post<MiniCharacter>('/characters/drafts', {
      name: uploadName.value.trim(),
      description: uploadDescription.value.trim() || null,
      source_object_key: data.object_key,
    })
    createOpen.value = false
    uploadName.value = ''
    uploadDescription.value = ''
    uploadFile.value = null
    await loadCharacters(false)
    selectedId.value = response.data.id
  } finally {
    uploading.value = false
  }
}

async function submitRender() {
  if (!asset.value) return
  const { data } = await api.post<RenderJob>('/miniapp/renders', {
    asset_id: asset.value.id,
    animation_id: animationId.value,
    camera_preset: cameraPreset.value,
    resolution: renderResolution.value,
    fps: renderFps.value,
    duration_seconds: renderDuration.value,
    background: background.value,
    loop: loop.value,
  })
  renderJob.value = data
  renderOpen.value = false
  schedulePoll()
}

async function cancelRender() {
  if (!renderJob.value) return
  const { data } = await api.post<RenderJob>(`/miniapp/renders/${renderJob.value.id}/cancel`)
  renderJob.value = data
}

function toggleLocale() {
  locale.value = locale.value === 'zh' ? 'en' : 'zh'
  localStorage.setItem('avatar_miniapp_locale', locale.value)
}

function logout() {
  auth.logout()
  void router.replace('/login')
}

onMounted(async () => {
  await loadCharacters(false)
  schedulePoll()
})

onBeforeUnmount(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
})
</script>

<template>
  <main class="studio-shell">
    <header class="studio-header">
      <div class="header-brand">
        <span class="brand-mark small">A</span>
        <div>
          <strong>{{ t('miniapp.brand') }}</strong>
          <span>LOCAL 3D LAB</span>
        </div>
      </div>
      <div class="header-actions">
        <button class="ghost-button compact" @click="toggleLocale">{{ locale === 'zh' ? 'EN' : '中' }}</button>
        <select
          class="compact-select"
          :value="theme.selected"
          @change="theme.setTheme(($event.target as HTMLSelectElement).value as ThemePreference)"
        >
          <option value="system">{{ t('miniapp.theme.system') }}</option>
          <option value="light">{{ t('miniapp.theme.light') }}</option>
          <option value="dark">{{ t('miniapp.theme.dark') }}</option>
        </select>
        <button class="user-chip" @click="logout">
          <span>{{ (auth.user?.username || 'U').slice(0, 1).toUpperCase() }}</span>
          <b>{{ auth.user?.username }}</b>
        </button>
      </div>
    </header>

    <section class="studio-grid">
      <aside class="character-rail">
        <div class="panel-heading">
          <div>
            <span class="eyebrow">CHARACTERS</span>
            <h2>{{ t('miniapp.character.title') }}</h2>
          </div>
          <button class="icon-button" title="Add character" @click="createOpen = true">＋</button>
        </div>
        <div v-if="!characters.length && !loadingCharacters" class="empty-panel">
          <span>◇</span>
          <p>{{ t('miniapp.character.empty') }}</p>
        </div>
        <button
          v-for="character in characters"
          :key="character.id"
          class="character-card"
          :class="{ active: character.id === selectedId }"
          @click="selectedId = character.id"
        >
          <span class="character-thumb">
            <img v-if="character.latest_model?.thumbnail_url || character.preview_url" :src="character.latest_model?.thumbnail_url || character.preview_url || ''" alt="" />
            <b v-else>{{ character.name.slice(0, 1) }}</b>
          </span>
          <span class="character-copy">
            <strong>{{ character.name }}</strong>
            <small>{{ character.latest_model ? t(`miniapp.build.${character.latest_model.status}`) : t('miniapp.build.title') }}</small>
          </span>
          <i :class="['status-dot', character.latest_model?.status || 'draft']" />
        </button>
        <button class="add-character" @click="createOpen = true">＋ {{ t('miniapp.character.create') }}</button>
      </aside>

      <section class="canvas-stage">
        <div class="canvas-toolbar">
          <span v-if="selected" class="stage-title">
            <i class="live-dot" />
            {{ selected.name }}
            <small>v{{ asset?.version || '—' }}</small>
          </span>
          <span v-else class="stage-title">{{ t('miniapp.studio.select') }}</span>
          <div>
            <button class="ghost-button compact" :disabled="!asset?.model_url" @click="viewer?.screenshot()">
              ◉ {{ t('miniapp.studio.screenshot') }}
            </button>
            <button class="primary-button compact" :disabled="asset?.status !== 'ready'" @click="renderOpen = true">
              ▶ {{ t('miniapp.studio.render') }}
            </button>
          </div>
        </div>

        <AvatarViewer
          ref="viewer"
          :model-url="asset?.model_url || null"
          :animation-id="animationId"
          :playing="playing"
          :speed="speed"
          :loop="loop"
          :camera-preset="cameraPreset"
          :background="background"
          @progress="progress = $event"
        >
          <div v-if="selected && !asset" class="build-card">
            <span class="build-icon">◇</span>
            <h2>{{ t('miniapp.build.title') }}</h2>
            <p>{{ t('miniapp.build.disclaimer') }}</p>
            <button class="primary-button" @click="startBuild">{{ t('miniapp.build.start') }}</button>
            <small v-if="buildError" class="form-error">{{ buildError }}</small>
          </div>
          <div v-else-if="asset && asset.status !== 'ready'" class="build-card wide">
            <span class="eyebrow">LOCAL FIXTURE PIPELINE</span>
            <h2>{{ t(`miniapp.build.${asset.status}`) }}</h2>
            <div class="build-steps">
              <span
                v-for="(step, index) in buildSteps"
                :key="step"
                :class="{ done: index <= currentBuildStep, active: index === currentBuildStep }"
              >
                <i />
                <small>{{ t(`miniapp.build.${step}`) }}</small>
              </span>
            </div>
            <p>{{ t('miniapp.build.disclaimer') }}</p>
          </div>
          <div v-else-if="!selected" class="build-card transparent">
            <span class="build-icon">◇</span>
            <h2>{{ t('miniapp.studio.select') }}</h2>
          </div>
        </AvatarViewer>

        <div v-if="asset?.status === 'ready'" class="playback-bar">
          <button class="round-button" @click="playing = !playing">{{ playing ? 'Ⅱ' : '▶' }}</button>
          <div class="timeline"><span :style="{ width: `${progress * 100}%` }" /></div>
          <span>{{ animationId.replace('_', ' ') }}</span>
          <button class="mobile-settings" @click="settingsOpen = !settingsOpen">☷</button>
        </div>
      </section>

      <aside class="control-panel" :class="{ open: settingsOpen }">
        <div class="panel-heading mobile-only">
          <h2>{{ t('miniapp.studio.settings') }}</h2>
          <button class="icon-button" @click="settingsOpen = false">×</button>
        </div>
        <section class="control-section">
          <span class="eyebrow">MOTION</span>
          <h3>{{ t('miniapp.studio.animation') }}</h3>
          <div class="option-grid two">
            <button
              v-for="item in animations"
              :key="item"
              :class="{ active: animationId === item }"
              @click="animationId = item"
            >
              <i>{{ item === 'dance_lite' ? '♪' : item === 'photo_pose' ? '✦' : '◌' }}</i>
              {{ t(`miniapp.animation.${item}`) }}
            </button>
          </div>
          <label class="range-row">
            <span>{{ t('miniapp.studio.speed') }} <b>{{ speed.toFixed(1) }}×</b></span>
            <input v-model.number="speed" type="range" min="0.5" max="1.5" step="0.1" />
          </label>
          <label class="toggle-row">
            <span>{{ t('miniapp.studio.loop') }}</span>
            <input v-model="loop" type="checkbox" />
          </label>
        </section>

        <section class="control-section">
          <span class="eyebrow">CAMERA</span>
          <h3>{{ t('miniapp.studio.camera') }}</h3>
          <div class="chip-grid">
            <button v-for="item in cameras" :key="item" :class="{ active: cameraPreset === item }" @click="cameraPreset = item">
              {{ t(`miniapp.camera.${item}`) }}
            </button>
          </div>
        </section>

        <section class="control-section">
          <span class="eyebrow">ENVIRONMENT</span>
          <h3>{{ t('miniapp.studio.background') }}</h3>
          <div class="swatch-grid">
            <button v-for="item in backgrounds" :key="item" :class="[item, { active: background === item }]" @click="background = item">
              <i />
              {{ t(`miniapp.background.${item}`) }}
            </button>
          </div>
        </section>

        <section v-if="asset?.views.length" class="control-section">
          <span class="eyebrow">REFERENCE</span>
          <h3>{{ t('miniapp.studio.views') }}</h3>
          <div class="view-grid">
            <img v-for="view in asset.views" :key="view.view_type" :src="view.preview_url || ''" :alt="view.view_type" />
          </div>
        </section>

        <section v-if="renderJob" class="render-status-card">
          <span class="status-dot" :class="renderJob.status" />
          <div>
            <strong>{{ t(`miniapp.render.${renderJob.status}`) }}</strong>
            <small>{{ renderJob.id.slice(0, 8) }}</small>
          </div>
          <a v-if="renderJob.output_url" :href="renderJob.output_url" target="_blank">{{ t('miniapp.render.download') }}</a>
          <button v-else-if="['queued', 'rendering'].includes(renderJob.status)" @click="cancelRender">{{ t('miniapp.render.cancel') }}</button>
        </section>
      </aside>
    </section>

    <div v-if="createOpen" class="modal-backdrop" @click.self="createOpen = false">
      <form class="modal-card" @submit.prevent="createCharacter">
        <button type="button" class="modal-close" @click="createOpen = false">×</button>
        <span class="eyebrow">NEW CHARACTER</span>
        <h2>{{ t('miniapp.character.create') }}</h2>
        <label><span>{{ t('miniapp.character.name') }}</span><input v-model="uploadName" required maxlength="60" /></label>
        <label><span>{{ t('miniapp.character.description') }}</span><textarea v-model="uploadDescription" maxlength="500" /></label>
        <label class="file-drop">
          <input type="file" accept="image/png,image/jpeg,image/webp" required @change="selectFile" />
          <span>＋</span>
          <b>{{ uploadFile?.name || t('miniapp.character.image') }}</b>
        </label>
        <button class="primary-button" :disabled="uploading">{{ uploading ? t('miniapp.character.uploading') : t('miniapp.character.upload') }}</button>
      </form>
    </div>

    <div v-if="renderOpen" class="modal-backdrop" @click.self="renderOpen = false">
      <form class="modal-card" @submit.prevent="submitRender">
        <button type="button" class="modal-close" @click="renderOpen = false">×</button>
        <span class="eyebrow">CPU · EEVEE · H.264</span>
        <h2>{{ t('miniapp.render.title') }}</h2>
        <label>
          <span>{{ t('miniapp.render.resolution') }}</span>
          <select v-model="renderResolution">
            <option value="1280x720">16:9 · 1280×720</option>
            <option value="720x1280">9:16 · 720×1280</option>
            <option value="1024x1024">1:1 · 1024×1024</option>
          </select>
        </label>
        <label>
          <span>{{ t('miniapp.render.duration') }}</span>
          <input v-model.number="renderDuration" type="range" min="3" max="10" />
          <small>{{ renderDuration }}s</small>
        </label>
        <label>
          <span>{{ t('miniapp.render.fps') }}</span>
          <select v-model="renderFps"><option :value="24">24 FPS</option><option :value="30">30 FPS</option></select>
        </label>
        <button class="primary-button">{{ t('miniapp.render.submit') }}</button>
      </form>
    </div>
  </main>
</template>
