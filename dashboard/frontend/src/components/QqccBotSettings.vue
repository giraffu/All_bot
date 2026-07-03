<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

import { fetchQqccBotConfig, updateQqccBotConfig } from '../api/api'

type MainButtonKey = 'quick_undress' | 'photo_edit' | 'ai_draw' | 'video_edit' | 'market' | 'main_bot_link'
type PhotoButtonKey = 'masturbation' | 'random_faceswap'
type UndressMethodKey = 'legacy' | 'i2i_draw'
type VideoButtonKey = 'missionary' | 'doggy' | 'blowjob' | 'undress_tongue' | 'closeup_blowjob'
type ResolutionKey = '512p' | '720p' | '1024p'
type DurationKey = '5s' | '8s' | '10s'
type VideoSceneEngine = 'image_to_video' | 'wan22_video_v2'
type DrawSceneEngine = 'free_edit' | 'free_edit_v2'
type SceneConfigKind = 'video' | 'draw'
type PromptKey =
  | 'undress'
  | 'i2i_draw_quick_undress'
  | 'masturbation'
  | 'face_swap'
  | 'perfect_video_insert'
  | 'doggy_style'
  | 'blowjob'
  | 'undress_tongue'
  | 'closeup_blowjob'

interface VideoSceneConfig {
  id: string
  name: string
  prompt: string
  duration: DurationKey
  engine: VideoSceneEngine
  lora_name: string
  end_frame_draw_scene_id: string
  prompt_key?: PromptKey
}

interface DrawSceneConfig {
  id: string
  name: string
  prompt: string
  engine: DrawSceneEngine
  lora_name: string
}

interface QqccBotConfig {
  global_enabled: boolean
  main_buttons: Record<MainButtonKey, boolean>
  photo_buttons: Record<PhotoButtonKey, boolean>
  undress_methods: Record<UndressMethodKey, boolean>
  video_buttons: Record<VideoButtonKey, boolean>
  video_settings: {
    resolutions: Record<ResolutionKey, boolean>
    durations: Record<DurationKey, boolean>
  }
  video_scenes: VideoSceneConfig[]
  draw_scenes: DrawSceneConfig[]
  prompts: Record<PromptKey, string>
}

interface SceneEngineOption {
  value: string
  supports_lora: boolean
}

interface LoraModelOption {
  value: string
  label: string
}

interface QqccBotConfigOptions {
  video_engines: SceneEngineOption[]
  draw_engines: SceneEngineOption[]
  video_lora_models: LoraModelOption[]
  image_lora_models: LoraModelOption[]
}

interface QqccBotConfigResponse {
  key?: string
  updated_at?: string | null
  config?: Partial<QqccBotConfig>
  options?: Partial<QqccBotConfigOptions>
}

const defaultOptions = (): QqccBotConfigOptions => ({
  video_engines: [
    { value: 'image_to_video', supports_lora: true },
    { value: 'wan22_video_v2', supports_lora: false },
  ],
  draw_engines: [
    { value: 'free_edit', supports_lora: true },
    { value: 'free_edit_v2', supports_lora: false },
  ],
  video_lora_models: [{ value: '', label: '无' }],
  image_lora_models: [{ value: '', label: '无' }],
})

const defaultConfig = (): QqccBotConfig => ({
  global_enabled: true,
  main_buttons: {
    quick_undress: true,
    photo_edit: true,
    ai_draw: true,
    video_edit: true,
    market: true,
    main_bot_link: true,
  },
  photo_buttons: {
    masturbation: true,
    random_faceswap: true,
  },
  undress_methods: {
    legacy: true,
    i2i_draw: true,
  },
  video_buttons: {
    missionary: true,
    doggy: true,
    blowjob: true,
    undress_tongue: true,
    closeup_blowjob: true,
  },
  video_settings: {
    resolutions: {
      '512p': true,
      '720p': true,
      '1024p': true,
    },
    durations: {
      '5s': true,
      '8s': true,
      '10s': true,
    },
  },
  video_scenes: [
    {
      id: 'missionary',
      name: '🛌 动图传教士',
      prompt: '',
      duration: '5s',
      engine: 'image_to_video',
      lora_name: '',
      end_frame_draw_scene_id: '',
      prompt_key: 'perfect_video_insert',
    },
    {
      id: 'doggy',
      name: '🎬 动图后入',
      prompt: '',
      duration: '5s',
      engine: 'image_to_video',
      lora_name: '',
      end_frame_draw_scene_id: '',
      prompt_key: 'doggy_style',
    },
    {
      id: 'blowjob',
      name: '🎬 口交黑人',
      prompt: '',
      duration: '5s',
      engine: 'image_to_video',
      lora_name: '',
      end_frame_draw_scene_id: '',
      prompt_key: 'blowjob',
    },
    {
      id: 'undress_tongue',
      name: '🎬 脱衣吐舌',
      prompt: '',
      duration: '5s',
      engine: 'image_to_video',
      lora_name: '',
      end_frame_draw_scene_id: '',
      prompt_key: 'undress_tongue',
    },
    {
      id: 'closeup_blowjob',
      name: '🎬 特写口交',
      prompt: '',
      duration: '5s',
      engine: 'image_to_video',
      lora_name: '',
      end_frame_draw_scene_id: '',
      prompt_key: 'closeup_blowjob',
    },
  ],
  draw_scenes: [],
  prompts: {
    undress: '',
    i2i_draw_quick_undress: '',
    masturbation: '',
    face_swap: '',
    perfect_video_insert: '',
    doggy_style: '',
    blowjob: '',
    undress_tongue: '',
    closeup_blowjob: '',
  },
})

const mainButtonOptions: Array<{ key: MainButtonKey; label: string }> = [
  { key: 'quick_undress', label: '快速脱衣' },
  { key: 'photo_edit', label: '懒人P图' },
  { key: 'ai_draw', label: 'AI绘图' },
  { key: 'video_edit', label: 'AI动图' },
  { key: 'market', label: '修仙市集' },
  { key: 'main_bot_link', label: '前往主bot' },
]

const photoButtonOptions: Array<{ key: PhotoButtonKey; label: string }> = [
  { key: 'masturbation', label: '快速自慰' },
  { key: 'random_faceswap', label: '随机换脸' },
]

const undressMethodOptions: Array<{ key: UndressMethodKey; label: string }> = [
  { key: 'legacy', label: '头像/半身补全' },
  { key: 'i2i_draw', label: '全身保脸重绘' },
]

const videoButtonOptions: Array<{ key: VideoButtonKey; label: string }> = [
  { key: 'missionary', label: '动图传教士' },
  { key: 'doggy', label: '动图后入' },
  { key: 'blowjob', label: '口交' },
  { key: 'undress_tongue', label: '脱衣吐舌' },
  { key: 'closeup_blowjob', label: '特写口交' },
]

const resolutionOptions: ResolutionKey[] = ['512p', '720p', '1024p']
const durationOptions: DurationKey[] = ['5s', '8s', '10s']

const videoEngineLabels: Record<VideoSceneEngine, string> = {
  image_to_video: '图生视频',
  wan22_video_v2: '图生视频v2',
}

const drawEngineLabels: Record<DrawSceneEngine, string> = {
  free_edit: '自由P图',
  free_edit_v2: '自由P图v2',
}

const nonVideoPromptOptions: Array<{ key: PromptKey; label: string }> = [
  { key: 'undress', label: '快速脱衣' },
  { key: 'i2i_draw_quick_undress', label: '全身保脸重绘' },
  { key: 'masturbation', label: '快速自慰' },
  { key: 'face_swap', label: '随机换脸' },
]

const loading = ref(false)
const saving = ref(false)
const configKey = ref('')
const updatedAt = ref<string | null>(null)
const config = reactive<QqccBotConfig>(defaultConfig())
const modelOptions = reactive<QqccBotConfigOptions>(defaultOptions())
const sceneCounter = ref(0)
const drawSceneCounter = ref(0)
const sceneConfig = reactive({
  open: false,
  kind: 'video' as SceneConfigKind,
  index: -1,
  engine: 'image_to_video',
  lora_name: '',
  end_frame_draw_scene_id: '',
})

const statusText = computed(() => (config.global_enabled ? '开启' : '关闭'))
const updatedAtText = computed(() => updatedAt.value || '-')

const normalizeVideoEngine = (value: unknown): VideoSceneEngine =>
  value === 'wan22_video_v2' ? 'wan22_video_v2' : 'image_to_video'

const normalizeDrawEngine = (value: unknown): DrawSceneEngine =>
  value === 'free_edit' ? 'free_edit' : 'free_edit_v2'

const engineSupportsLora = (kind: SceneConfigKind, engine: string) => {
  const engines = kind === 'video' ? modelOptions.video_engines : modelOptions.draw_engines
  return engines.some((item) => item.value === engine && item.supports_lora)
}

const normalizeLoraName = (
  raw: unknown,
  options: {
    kind: SceneConfigKind
    engine: string
  },
) => {
  const { kind, engine } = options
  if (!engineSupportsLora(kind, engine)) return ''
  const loraName = typeof raw === 'string' ? raw : ''
  const loras = kind === 'video' ? modelOptions.video_lora_models : modelOptions.image_lora_models
  return loras.some((item) => item.value === loraName) ? loraName : ''
}

const normalizeEndFrameDrawSceneId = (raw: unknown, drawScenes = config.draw_scenes) => {
  const sceneId = typeof raw === 'string' ? raw.trim() : ''
  return drawScenes.some((scene) => scene.id === sceneId) ? sceneId : ''
}

const mergeOptions = (raw?: Partial<QqccBotConfigOptions>): QqccBotConfigOptions => {
  const merged = defaultOptions()
  if (!raw || typeof raw !== 'object') return merged
  if (Array.isArray(raw.video_engines) && raw.video_engines.length > 0) {
    merged.video_engines = raw.video_engines
      .filter((item) => typeof item?.value === 'string')
      .map((item) => ({ value: item.value, supports_lora: item.supports_lora === true }))
  }
  if (Array.isArray(raw.draw_engines) && raw.draw_engines.length > 0) {
    merged.draw_engines = raw.draw_engines
      .filter((item) => typeof item?.value === 'string')
      .map((item) => ({ value: item.value, supports_lora: item.supports_lora === true }))
  }
  if (Array.isArray(raw.video_lora_models) && raw.video_lora_models.length > 0) {
    merged.video_lora_models = raw.video_lora_models
      .filter((item) => typeof item?.value === 'string')
      .map((item) => ({ value: item.value, label: typeof item.label === 'string' ? item.label : item.value }))
  }
  if (Array.isArray(raw.image_lora_models) && raw.image_lora_models.length > 0) {
    merged.image_lora_models = raw.image_lora_models
      .filter((item) => typeof item?.value === 'string')
      .map((item) => ({ value: item.value, label: typeof item.label === 'string' ? item.label : item.value }))
  }
  return merged
}

const getEngineLabel = (kind: SceneConfigKind, engine: string) => {
  if (kind === 'video') return videoEngineLabels[normalizeVideoEngine(engine)]
  return drawEngineLabels[normalizeDrawEngine(engine)]
}

const getSceneSelectPopupContainer = (triggerNode: HTMLElement) =>
  triggerNode.parentElement || document.body

const activeEngineOptions = computed(() =>
  sceneConfig.kind === 'video' ? modelOptions.video_engines : modelOptions.draw_engines
)
const activeLoraOptions = computed(() =>
  sceneConfig.kind === 'video' ? modelOptions.video_lora_models : modelOptions.image_lora_models
)
const activeEngineSupportsLora = computed(() =>
  engineSupportsLora(sceneConfig.kind, sceneConfig.engine)
)
const activeEndFrameDrawOptions = computed(() =>
  config.draw_scenes.filter((scene) => scene.id.trim() && scene.name.trim() && scene.prompt.trim())
)

const mergeConfig = (raw?: Partial<QqccBotConfig>): QqccBotConfig => {
  const merged = defaultConfig()
  if (!raw || typeof raw !== 'object') return merged
  if (typeof raw.global_enabled === 'boolean') {
    merged.global_enabled = raw.global_enabled
  }

  mainButtonOptions.forEach(({ key }) => {
    const value = raw.main_buttons?.[key]
    if (typeof value === 'boolean') merged.main_buttons[key] = value
  })
  photoButtonOptions.forEach(({ key }) => {
    const value = raw.photo_buttons?.[key]
    if (typeof value === 'boolean') merged.photo_buttons[key] = value
  })
  undressMethodOptions.forEach(({ key }) => {
    const value = raw.undress_methods?.[key]
    if (typeof value === 'boolean') merged.undress_methods[key] = value
  })
  videoButtonOptions.forEach(({ key }) => {
    const value = raw.video_buttons?.[key]
    if (typeof value === 'boolean') merged.video_buttons[key] = value
  })
  resolutionOptions.forEach((key) => {
    const value = raw.video_settings?.resolutions?.[key]
    if (typeof value === 'boolean') merged.video_settings.resolutions[key] = value
  })
  durationOptions.forEach((key) => {
    const value = raw.video_settings?.durations?.[key]
    if (typeof value === 'boolean') merged.video_settings.durations[key] = value
  })
  if (Array.isArray(raw.draw_scenes)) {
    merged.draw_scenes = raw.draw_scenes
      .map((scene, index) => {
        const id = typeof scene?.id === 'string' && scene.id.trim() ? scene.id.trim() : `draw_scene_${index + 1}`
        const name = typeof scene?.name === 'string' ? scene.name : ''
        const prompt = typeof scene?.prompt === 'string' ? scene.prompt : ''
        const engine = normalizeDrawEngine(scene?.engine)
        return {
          id,
          name,
          prompt,
          engine,
          lora_name: normalizeLoraName(scene?.lora_name, { kind: 'draw', engine }),
        }
      })
      .filter((scene) => scene.name.trim() || scene.prompt.trim())
  }
  if (Array.isArray(raw.video_scenes)) {
    merged.video_scenes = raw.video_scenes
      .map((scene, index) => {
        const id = typeof scene?.id === 'string' && scene.id.trim() ? scene.id.trim() : `scene_${index + 1}`
        const name = typeof scene?.name === 'string' ? scene.name : ''
        const prompt = typeof scene?.prompt === 'string' ? scene.prompt : ''
        const duration = durationOptions.includes(scene?.duration as DurationKey)
          ? (scene.duration as DurationKey)
          : '5s'
        const promptKey = typeof scene?.prompt_key === 'string' ? (scene.prompt_key as PromptKey) : undefined
        const engine = normalizeVideoEngine(scene?.engine)
        return {
          id,
          name,
          prompt,
          duration,
          engine,
          lora_name: normalizeLoraName(scene?.lora_name, { kind: 'video', engine }),
          end_frame_draw_scene_id: normalizeEndFrameDrawSceneId(
            scene?.end_frame_draw_scene_id,
            merged.draw_scenes,
          ),
          ...(promptKey ? { prompt_key: promptKey } : {}),
        }
      })
      .filter((scene) => scene.name.trim() || scene.prompt.trim() || scene.prompt_key)
  }
  Object.keys(merged.prompts).forEach((key) => {
    const promptKey = key as PromptKey
    const value = raw.prompts?.[promptKey]
    if (typeof value === 'string') merged.prompts[promptKey] = value
  })
  return merged
}

const createVideoSceneId = () => {
  sceneCounter.value += 1
  return `scene_${Date.now().toString(36)}_${sceneCounter.value}`
}

const addVideoScene = () => {
  config.video_scenes.push({
    id: createVideoSceneId(),
    name: '',
    prompt: '',
    duration: '5s',
    engine: 'image_to_video',
    lora_name: '',
    end_frame_draw_scene_id: '',
  })
}

const removeVideoScene = (index: number) => {
  config.video_scenes.splice(index, 1)
}

const createDrawSceneId = () => {
  drawSceneCounter.value += 1
  return `draw_${Date.now().toString(36)}_${drawSceneCounter.value}`
}

const addDrawScene = () => {
  config.draw_scenes.push({
    id: createDrawSceneId(),
    name: '',
    prompt: '',
    engine: 'free_edit_v2',
    lora_name: '',
  })
}

const removeDrawScene = (index: number) => {
  const [removed] = config.draw_scenes.splice(index, 1)
  if (!removed) return
  config.video_scenes.forEach((scene) => {
    if (scene.end_frame_draw_scene_id === removed.id) {
      scene.end_frame_draw_scene_id = ''
    }
  })
}

const validateVideoScenes = () =>
  config.video_scenes.every((scene) => {
    if (!scene.name.trim()) return false
    if (scene.prompt_key) return true
    return Boolean(scene.prompt.trim())
  })

const validateDrawScenes = () =>
  config.draw_scenes.every((scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()))

const buildPayload = (): QqccBotConfig => {
  const payload = JSON.parse(JSON.stringify(config)) as QqccBotConfig
  payload.draw_scenes = payload.draw_scenes
    .map((scene) => {
      const engine = normalizeDrawEngine(scene.engine)
      return {
        ...scene,
        id: scene.id.trim(),
        name: scene.name.trim(),
        prompt: scene.prompt.trim(),
        engine,
        lora_name: normalizeLoraName(scene.lora_name, { kind: 'draw', engine }),
      }
    })
    .filter((scene) => scene.name || scene.prompt)
  payload.video_scenes = payload.video_scenes
    .map((scene) => {
      const engine = normalizeVideoEngine(scene.engine)
      return {
        ...scene,
        id: scene.id.trim(),
        name: scene.name.trim(),
        prompt: scene.prompt.trim(),
        engine,
        lora_name: normalizeLoraName(scene.lora_name, { kind: 'video', engine }),
        end_frame_draw_scene_id: normalizeEndFrameDrawSceneId(
          scene.end_frame_draw_scene_id,
          payload.draw_scenes,
        ),
      }
    })
    .filter((scene) => scene.name || scene.prompt || scene.prompt_key)
  return payload
}

const applyResponse = (payload: QqccBotConfigResponse) => {
  Object.assign(modelOptions, mergeOptions(payload.options))
  Object.assign(config, mergeConfig(payload.config))
  configKey.value = payload.key || ''
  updatedAt.value = payload.updated_at || null
}

const openSceneConfig = (kind: SceneConfigKind, index: number) => {
  const scene = kind === 'video' ? config.video_scenes[index] : config.draw_scenes[index]
  if (!scene) return
  sceneConfig.kind = kind
  sceneConfig.index = index
  sceneConfig.engine = scene.engine
  sceneConfig.lora_name = scene.lora_name || ''
  sceneConfig.end_frame_draw_scene_id =
    kind === 'video'
      ? normalizeEndFrameDrawSceneId((scene as VideoSceneConfig).end_frame_draw_scene_id)
      : ''
  sceneConfig.open = true
}

const closeSceneConfig = () => {
  sceneConfig.open = false
  sceneConfig.index = -1
  sceneConfig.end_frame_draw_scene_id = ''
}

const onSceneEngineChange = () => {
  if (!activeEngineSupportsLora.value) {
    sceneConfig.lora_name = ''
  }
}

const confirmSceneConfig = () => {
  if (sceneConfig.index < 0) return
  if (sceneConfig.kind === 'video') {
    const scene = config.video_scenes[sceneConfig.index]
    if (!scene) return
    const engine = normalizeVideoEngine(sceneConfig.engine)
    scene.engine = engine
    scene.lora_name = normalizeLoraName(sceneConfig.lora_name, { kind: 'video', engine })
    scene.end_frame_draw_scene_id = normalizeEndFrameDrawSceneId(sceneConfig.end_frame_draw_scene_id)
  } else {
    const scene = config.draw_scenes[sceneConfig.index]
    if (!scene) return
    const engine = normalizeDrawEngine(sceneConfig.engine)
    scene.engine = engine
    scene.lora_name = normalizeLoraName(sceneConfig.lora_name, { kind: 'draw', engine })
  }
  closeSceneConfig()
}

const loadConfig = async () => {
  loading.value = true
  try {
    const payload = await fetchQqccBotConfig()
    applyResponse(payload)
  } catch {
    message.error('加载懒人Bot配置失败')
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  if (!validateVideoScenes()) {
    message.error('请完善AI动图场景的按钮名称和提示词')
    return
  }
  if (!validateDrawScenes()) {
    message.error('请完善AI绘图场景的按钮名称和提示词')
    return
  }
  saving.value = true
  try {
    const saved = await updateQqccBotConfig(buildPayload())
    applyResponse(saved)
    message.success('懒人Bot配置已保存')
  } catch {
    message.error('保存懒人Bot配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadConfig()
})
</script>

<template>
  <div class="qqcc-bot-settings flex-1 flex flex-col gap-5">
    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-semibold text-slate-900">懒人Bot配置</h2>
          <div class="mt-1 text-sm text-slate-500">
            状态：{{ statusText }} · 更新时间：{{ updatedAtText }}
          </div>
        </div>
        <div class="flex items-center gap-2">
          <a-button :loading="loading" @click="loadConfig">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
          <a-button type="primary" :loading="saving" @click="saveConfig">
            <template #icon><SaveOutlined /></template>
            保存
          </a-button>
        </div>
      </div>

      <a-spin :spinning="loading">
        <div class="grid gap-5 xl:grid-cols-[280px_1fr]">
          <div class="rounded-lg border border-slate-200 p-4">
            <div class="mb-4 flex items-center justify-between gap-3">
              <span class="text-sm font-medium text-slate-700">全局开关</span>
              <a-switch v-model:checked="config.global_enabled" data-testid="global-enabled" />
            </div>
            <div class="text-xs text-slate-400">Key：{{ configKey || '-' }}</div>
          </div>

          <div class="grid gap-4 lg:grid-cols-3">
            <section class="rounded-lg border border-slate-200 p-4">
              <h3 class="mb-3 text-sm font-semibold text-slate-800">主菜单</h3>
              <div class="space-y-3">
                <div
                  v-for="item in mainButtonOptions"
                  :key="item.key"
                  class="flex items-center justify-between gap-3"
                >
                  <span class="text-sm text-slate-700">{{ item.label }}</span>
                  <a-switch v-model:checked="config.main_buttons[item.key]" />
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 p-4">
              <h3 class="mb-3 text-sm font-semibold text-slate-800">懒人P图</h3>
              <div class="space-y-3">
                <div
                  v-for="item in photoButtonOptions"
                  :key="item.key"
                  class="flex items-center justify-between gap-3"
                >
                  <span class="text-sm text-slate-700">{{ item.label }}</span>
                  <a-switch v-model:checked="config.photo_buttons[item.key]" />
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-slate-200 p-4">
              <h3 class="mb-3 text-sm font-semibold text-slate-800">脱衣方式</h3>
              <div class="space-y-3">
                <div
                  v-for="item in undressMethodOptions"
                  :key="item.key"
                  class="flex items-center justify-between gap-3"
                >
                  <span class="text-sm text-slate-700">{{ item.label }}</span>
                  <a-switch v-model:checked="config.undress_methods[item.key]" />
                </div>
              </div>
            </section>
          </div>
        </div>
      </a-spin>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-sm font-semibold text-slate-800">AI动图场景</h3>
        <a-button data-testid="add-video-scene" @click="addVideoScene">
          <template #icon><PlusOutlined /></template>
          添加
        </a-button>
      </div>

      <div>
        <div>
          <div
            class="hidden grid-cols-[180px_minmax(360px,1fr)_120px_56px] gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid"
          >
            <span>按钮名称</span>
            <span>提示词</span>
            <span>时长</span>
            <span>操作</span>
          </div>
          <div
            v-for="(scene, index) in config.video_scenes"
            :key="scene.id"
            class="grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[180px_minmax(360px,1fr)_120px_56px]"
          >
            <div class="grid grid-cols-[minmax(0,1fr)_36px] gap-2">
              <a-input
                v-model:value="scene.name"
                :data-testid="`video-scene-name-${index}`"
              />
              <a-button
                :data-testid="`config-video-scene-${index}`"
                title="配置模型"
                @click="openSceneConfig('video', index)"
              >
                <template #icon><SettingOutlined /></template>
              </a-button>
            </div>
            <a-textarea
              v-model:value="scene.prompt"
              :rows="3"
              :data-testid="`video-scene-prompt-${index}`"
              placeholder="留空使用 prompts.ini"
            />
            <div
              class="grid grid-cols-[1fr_56px] gap-3 md:contents"
            >
              <a-select
                v-model:value="scene.duration"
                :data-testid="`video-scene-duration-${index}`"
                class="w-full"
              >
                <a-select-option v-for="item in durationOptions" :key="item" :value="item">
                  {{ item }}
                </a-select-option>
              </a-select>
              <a-button
                danger
                :data-testid="`remove-video-scene-${index}`"
                @click="removeVideoScene(index)"
              >
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
          </div>
          <div v-if="config.video_scenes.length === 0" class="py-6 text-center text-sm text-slate-400">
            暂无场景
          </div>
        </div>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-sm font-semibold text-slate-800">AI绘图场景</h3>
        <a-button data-testid="add-draw-scene" @click="addDrawScene">
          <template #icon><PlusOutlined /></template>
          添加
        </a-button>
      </div>

      <div>
        <div
          class="hidden grid-cols-[180px_minmax(360px,1fr)_56px] gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid"
        >
          <span>按钮名称</span>
          <span>提示词</span>
          <span>操作</span>
        </div>
        <div
          v-for="(scene, index) in config.draw_scenes"
          :key="scene.id"
          class="grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[180px_minmax(360px,1fr)_56px]"
        >
          <div class="grid grid-cols-[minmax(0,1fr)_36px] gap-2">
            <a-input
              v-model:value="scene.name"
              :data-testid="`draw-scene-name-${index}`"
            />
            <a-button
              :data-testid="`config-draw-scene-${index}`"
              title="配置模型"
              @click="openSceneConfig('draw', index)"
            >
              <template #icon><SettingOutlined /></template>
            </a-button>
          </div>
          <a-textarea
            v-model:value="scene.prompt"
            :rows="3"
            :data-testid="`draw-scene-prompt-${index}`"
          />
          <div class="flex justify-end md:contents">
            <a-button
              danger
              :data-testid="`remove-draw-scene-${index}`"
              @click="removeDrawScene(index)"
            >
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
        </div>
        <div v-if="config.draw_scenes.length === 0" class="py-6 text-center text-sm text-slate-400">
          暂无场景
        </div>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5">
      <h3 class="mb-4 text-sm font-semibold text-slate-800">提示词覆盖</h3>
      <div class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <a-form-item v-for="item in nonVideoPromptOptions" :key="item.key" :label="item.label">
          <a-textarea
            v-model:value="config.prompts[item.key]"
            :rows="5"
            :data-testid="`non-video-prompt-${item.key}`"
            placeholder="留空使用 prompts.ini"
          />
        </a-form-item>
      </div>
    </section>

    <a-modal
      v-model:open="sceneConfig.open"
      title="模型与首尾帧配置"
      :footer="null"
      :width="520"
      wrap-class-name="qqcc-scene-config-modal"
      @cancel="closeSceneConfig"
    >
      <a-form layout="vertical" class="scene-config-form">
        <a-form-item label="底层模型" class="mb-4">
          <a-select
            v-model:value="sceneConfig.engine"
            data-testid="scene-engine-select"
            class="w-full"
            :get-popup-container="getSceneSelectPopupContainer"
            @change="onSceneEngineChange"
          >
            <a-select-option
              v-for="item in activeEngineOptions"
              :key="item.value"
              :value="item.value"
            >
              {{ getEngineLabel(sceneConfig.kind, item.value) }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="附加模型" class="mb-4">
          <a-select
            v-model:value="sceneConfig.lora_name"
            data-testid="scene-lora-select"
            class="w-full"
            :disabled="!activeEngineSupportsLora"
            :get-popup-container="getSceneSelectPopupContainer"
          >
            <a-select-option
              v-for="item in activeLoraOptions"
              :key="item.value"
              :value="item.value"
            >
              {{ item.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item v-if="sceneConfig.kind === 'video'" label="尾帧来源" class="mb-4">
          <a-select
            v-model:value="sceneConfig.end_frame_draw_scene_id"
            data-testid="scene-end-frame-select"
            class="w-full"
            :get-popup-container="getSceneSelectPopupContainer"
          >
            <a-select-option value="">无</a-select-option>
            <a-select-option
              v-for="item in activeEndFrameDrawOptions"
              :key="item.id"
              :value="item.id"
            >
              {{ item.name || item.id }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <div class="flex justify-end gap-2">
          <a-button @click="closeSceneConfig">取消</a-button>
          <a-button
            type="primary"
            data-testid="scene-config-confirm"
            @click="confirmSceneConfig"
          >
            确定
          </a-button>
        </div>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
:global(.qqcc-scene-config-modal) {
  width: 100vw;
  left: 0;
  right: 0;
  overflow-x: hidden;
}

:global(.qqcc-scene-config-modal .ant-modal) {
  max-width: calc(100vw - 32px);
  margin: 0 auto;
}

:global(.qqcc-scene-config-modal .ant-modal-body) {
  padding-top: 8px;
}
</style>
