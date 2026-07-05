<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  DeleteOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

type MainButtonKey =
  | 'quick_undress'
  | 'quick_faceswap'
  | 'photo_edit'
  | 'ai_draw'
  | 'video_edit'
  | 'market'
  | 'main_bot_link'
type PhotoButtonKey = 'masturbation' | 'random_faceswap'
type UndressMethodKey = 'legacy' | 'i2i_draw'
type VideoButtonKey = 'missionary' | 'doggy' | 'blowjob' | 'undress_tongue' | 'closeup_blowjob'
type ResolutionKey = '512p' | '720p' | '1024p'
type DurationKey = '5s' | '8s' | '10s'
type VideoSceneEngine = 'image_to_video' | 'wan22_video_v2'
type DrawSceneEngine = 'free_edit' | 'free_edit_v2'
type SceneConfigKind = 'video' | 'draw'
type SceneConfigPanel = 'model' | 'reference'
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
}

interface DrawSceneConfig {
  id: string
  name: string
  prompt: string
  engine: DrawSceneEngine
  lora_name: string
  postprocess_draw_scene_id: string
}

interface QqccBotConfig {
  scene_preset_version: number
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
  scene_preset_version: number
  default_video_engine: VideoSceneEngine
  default_draw_engine: DrawSceneEngine
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

const props = defineProps<{
  fetchConfig: () => Promise<QqccBotConfigResponse>
  updateConfig: (payload: QqccBotConfig) => Promise<QqccBotConfigResponse>
}>()

const emptyOptions = (): QqccBotConfigOptions => ({
  scene_preset_version: 1,
  default_video_engine: 'image_to_video',
  default_draw_engine: 'free_edit_v2',
  video_engines: [],
  draw_engines: [],
  video_lora_models: [],
  image_lora_models: [],
})

const drawSceneMaxCount = 20

const emptyConfig = (): QqccBotConfig => ({
  scene_preset_version: 1,
  global_enabled: false,
  main_buttons: {
    quick_undress: false,
    quick_faceswap: false,
    photo_edit: false,
    ai_draw: false,
    video_edit: false,
    market: false,
    main_bot_link: false,
  },
  photo_buttons: {
    masturbation: false,
    random_faceswap: false,
  },
  undress_methods: {
    legacy: false,
    i2i_draw: false,
  },
  video_buttons: {
    missionary: false,
    doggy: false,
    blowjob: false,
    undress_tongue: false,
    closeup_blowjob: false,
  },
  video_settings: {
    resolutions: {
      '512p': false,
      '720p': false,
      '1024p': false,
    },
    durations: {
      '5s': false,
      '8s': false,
      '10s': false,
    },
  },
  video_scenes: [],
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
  { key: 'quick_faceswap', label: '快速换脸' },
  { key: 'ai_draw', label: 'AI绘图' },
  { key: 'video_edit', label: 'AI动图' },
  { key: 'market', label: '修仙市集' },
  { key: 'main_bot_link', label: '前往主bot' },
]
const legacyMainButtonKeys: MainButtonKey[] = ['quick_undress', 'photo_edit']

const photoButtonKeys: PhotoButtonKey[] = ['masturbation', 'random_faceswap']

const undressMethodKeys: UndressMethodKey[] = ['legacy', 'i2i_draw']

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
  { key: 'face_swap', label: '快速换脸' },
]

const loading = ref(false)
const saving = ref(false)
const configKey = ref('')
const updatedAt = ref<string | null>(null)
const config = reactive<QqccBotConfig>(emptyConfig())
const modelOptions = reactive<QqccBotConfigOptions>(emptyOptions())
const sceneCounter = ref(0)
const drawSceneCounter = ref(0)
const sceneConfig = reactive({
  open: false,
  kind: 'video' as SceneConfigKind,
  panel: 'model' as SceneConfigPanel,
  index: -1,
  engine: 'image_to_video',
  lora_name: '',
  end_frame_draw_scene_id: '',
  postprocess_draw_scene_id: '',
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

const normalizePostprocessDrawSceneId = (
  raw: unknown,
  sourceIndex: number,
  drawScenes = config.draw_scenes,
) => {
  const sceneId = typeof raw === 'string' ? raw.trim() : ''
  const sourceScene = drawScenes[sourceIndex]
  if (!sceneId || !sourceScene || sceneId === sourceScene.id) return ''
  return drawScenes.some((scene) => scene.id === sceneId) ? sceneId : ''
}

const findDrawPostprocessCycleIds = (drawScenes = config.draw_scenes) => {
  const scenesById = new Map(drawScenes.map((scene) => [scene.id, scene]))
  const cycleIds = new Set<string>()
  drawScenes.forEach((scene) => {
    const path: string[] = []
    const pathIndex = new Map<string, number>()
    let currentId = scene.id
    while (currentId && scenesById.has(currentId)) {
      const visitedIndex = pathIndex.get(currentId)
      if (visitedIndex !== undefined) {
        path.slice(visitedIndex).forEach((id) => cycleIds.add(id))
        break
      }
      pathIndex.set(currentId, path.length)
      path.push(currentId)
      currentId = scenesById.get(currentId)?.postprocess_draw_scene_id || ''
    }
  })
  return cycleIds
}

const hasDrawPostprocessCycle = (drawScenes = config.draw_scenes) =>
  findDrawPostprocessCycleIds(drawScenes).size > 0

const wouldCreateDrawPostprocessCycle = (
  sourceId: string,
  targetId: string,
  drawScenes = config.draw_scenes,
) => {
  if (!sourceId || !targetId) return false
  const scenesById = new Map(drawScenes.map((scene) => [scene.id, scene]))
  const visited = new Set<string>()
  let currentId = targetId
  while (currentId && scenesById.has(currentId)) {
    if (currentId === sourceId || visited.has(currentId)) return true
    visited.add(currentId)
    currentId = scenesById.get(currentId)?.postprocess_draw_scene_id || ''
  }
  return false
}

const normalizeDrawPostprocessRefs = (drawScenes: DrawSceneConfig[]) => {
  drawScenes.forEach((scene, index) => {
    scene.postprocess_draw_scene_id = normalizePostprocessDrawSceneId(
      scene.postprocess_draw_scene_id,
      index,
      drawScenes,
    )
  })
  const cycleIds = findDrawPostprocessCycleIds(drawScenes)
  drawScenes.forEach((scene) => {
    if (cycleIds.has(scene.id)) {
      scene.postprocess_draw_scene_id = ''
    }
  })
}

const mergeOptions = (raw?: Partial<QqccBotConfigOptions>): QqccBotConfigOptions => {
  const merged = emptyOptions()
  if (!raw || typeof raw !== 'object') return merged
  if (typeof raw.scene_preset_version === 'number' && raw.scene_preset_version >= 1) {
    merged.scene_preset_version = raw.scene_preset_version
  }
  merged.default_video_engine = normalizeVideoEngine(raw.default_video_engine)
  merged.default_draw_engine = normalizeDrawEngine(raw.default_draw_engine)
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
  config.draw_scenes.filter(
    (scene) => scene.id.trim() && scene.name.trim() && scene.prompt.trim(),
  )
)
const activePostprocessDrawOptions = computed(() => {
  const sourceScene = config.draw_scenes[sceneConfig.index]
  if (sceneConfig.kind !== 'draw' || !sourceScene) return []
  return config.draw_scenes.filter(
    (scene) =>
      scene.id.trim() &&
      scene.name.trim() &&
      scene.prompt.trim() &&
      scene.id !== sourceScene.id &&
      !wouldCreateDrawPostprocessCycle(sourceScene.id, scene.id),
  )
})
const sceneModalTitle = computed(() => {
  if (sceneConfig.panel === 'model') return '模型配置'
  return sceneConfig.kind === 'video' ? '首尾帧配置' : '后处理配置'
})

const mergeConfig = (raw?: Partial<QqccBotConfig>): QqccBotConfig => {
  const merged = emptyConfig()
  if (!raw || typeof raw !== 'object') return merged
  if (typeof raw.scene_preset_version === 'number' && raw.scene_preset_version >= 1) {
    merged.scene_preset_version = raw.scene_preset_version
  }
  if (typeof raw.global_enabled === 'boolean') {
    merged.global_enabled = raw.global_enabled
  }

  ;[...mainButtonOptions.map((item) => item.key), ...legacyMainButtonKeys].forEach((key) => {
    const value = raw.main_buttons?.[key]
    if (typeof value === 'boolean') merged.main_buttons[key] = value
  })
  legacyMainButtonKeys.forEach((key) => {
    merged.main_buttons[key] = false
  })
  photoButtonKeys.forEach((key) => {
    const value = raw.photo_buttons?.[key]
    if (typeof value === 'boolean') merged.photo_buttons[key] = value
  })
  undressMethodKeys.forEach((key) => {
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
    const normalizedDrawScenes = raw.draw_scenes
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
          postprocess_draw_scene_id:
            typeof scene?.postprocess_draw_scene_id === 'string'
              ? scene.postprocess_draw_scene_id.trim()
              : '',
        }
      })
      .filter((scene) => scene.name.trim() || scene.prompt.trim())
    normalizeDrawPostprocessRefs(normalizedDrawScenes)
    merged.draw_scenes = normalizedDrawScenes
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
        }
      })
      .filter((scene) => scene.name.trim() || scene.prompt.trim())
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
    engine: normalizeVideoEngine(modelOptions.default_video_engine),
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
    engine: normalizeDrawEngine(modelOptions.default_draw_engine),
    lora_name: '',
    postprocess_draw_scene_id: '',
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
  config.draw_scenes.forEach((scene) => {
    if (scene.postprocess_draw_scene_id === removed.id) {
      scene.postprocess_draw_scene_id = ''
    }
  })
}

const validateVideoScenes = () =>
  config.video_scenes.every((scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()))

const validateDrawScenes = () =>
  config.draw_scenes.every(
    (scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()),
  )

const buildPayload = (): QqccBotConfig => {
  const payload = JSON.parse(JSON.stringify(config)) as QqccBotConfig
  payload.scene_preset_version = config.scene_preset_version || modelOptions.scene_preset_version
  legacyMainButtonKeys.forEach((key) => {
    payload.main_buttons[key] = false
  })
  const normalizedDrawScenes = payload.draw_scenes
    .map((scene) => {
      const engine = normalizeDrawEngine(scene.engine)
      return {
        ...scene,
        id: scene.id.trim(),
        name: scene.name.trim(),
        prompt: scene.prompt.trim(),
        engine,
        lora_name: normalizeLoraName(scene.lora_name, { kind: 'draw', engine }),
        postprocess_draw_scene_id:
          typeof scene.postprocess_draw_scene_id === 'string'
            ? scene.postprocess_draw_scene_id.trim()
            : '',
      }
    })
    .filter((scene) => scene.name || scene.prompt)
  normalizeDrawPostprocessRefs(normalizedDrawScenes)
  payload.draw_scenes = normalizedDrawScenes.slice(0, drawSceneMaxCount)
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
    .filter((scene) => scene.name || scene.prompt)
  return payload
}

const applyResponse = (payload: QqccBotConfigResponse) => {
  Object.assign(modelOptions, mergeOptions(payload.options))
  Object.assign(config, mergeConfig(payload.config))
  configKey.value = payload.key || ''
  updatedAt.value = payload.updated_at || null
}

const openSceneConfig = (
  kind: SceneConfigKind,
  index: number,
  panel: SceneConfigPanel,
) => {
  const scene = kind === 'video' ? config.video_scenes[index] : config.draw_scenes[index]
  if (!scene) return
  sceneConfig.kind = kind
  sceneConfig.panel = panel
  sceneConfig.index = index
  sceneConfig.engine = scene.engine
  sceneConfig.lora_name = scene.lora_name || ''
  sceneConfig.end_frame_draw_scene_id =
    kind === 'video'
      ? normalizeEndFrameDrawSceneId((scene as VideoSceneConfig).end_frame_draw_scene_id)
      : ''
  sceneConfig.postprocess_draw_scene_id =
    kind === 'draw'
      ? normalizePostprocessDrawSceneId((scene as DrawSceneConfig).postprocess_draw_scene_id, index)
      : ''
  sceneConfig.open = true
}

const closeSceneConfig = () => {
  sceneConfig.open = false
  sceneConfig.panel = 'model'
  sceneConfig.index = -1
  sceneConfig.end_frame_draw_scene_id = ''
  sceneConfig.postprocess_draw_scene_id = ''
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
    if (sceneConfig.panel === 'model') {
      const engine = normalizeVideoEngine(sceneConfig.engine)
      scene.engine = engine
      scene.lora_name = normalizeLoraName(sceneConfig.lora_name, { kind: 'video', engine })
    } else {
      scene.end_frame_draw_scene_id = normalizeEndFrameDrawSceneId(
        sceneConfig.end_frame_draw_scene_id,
      )
    }
  } else {
    const scene = config.draw_scenes[sceneConfig.index]
    if (!scene) return
    if (sceneConfig.panel === 'model') {
      const engine = normalizeDrawEngine(sceneConfig.engine)
      scene.engine = engine
      scene.lora_name = normalizeLoraName(sceneConfig.lora_name, { kind: 'draw', engine })
    } else {
      const postprocessDrawSceneId = normalizePostprocessDrawSceneId(
        sceneConfig.postprocess_draw_scene_id,
        sceneConfig.index,
      )
      if (
        postprocessDrawSceneId &&
        wouldCreateDrawPostprocessCycle(scene.id, postprocessDrawSceneId)
      ) {
        message.error('AI绘图后处理配置不能形成循环')
        return
      }
      scene.postprocess_draw_scene_id = postprocessDrawSceneId
    }
  }
  closeSceneConfig()
}

const loadConfig = async () => {
  loading.value = true
  try {
    const payload = await props.fetchConfig()
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
  if (hasDrawPostprocessCycle(config.draw_scenes)) {
    message.error('AI绘图后处理配置不能形成循环')
    return
  }
  saving.value = true
  try {
    const saved = await props.updateConfig(buildPayload())
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
  <div class="qqcc-bot-settings flex flex-1 flex-col gap-5">
    <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-lg font-semibold text-slate-950">懒人Bot配置</h2>
            <span
              class="rounded-full px-2.5 py-0.5 text-xs font-medium"
              :class="config.global_enabled ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-slate-100 text-slate-500 ring-1 ring-slate-200'"
            >
              状态：{{ statusText }}
            </span>
          </div>
          <div class="mt-1 truncate text-sm text-slate-500">
            更新时间：{{ updatedAtText }}
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
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
          <div class="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
            <div class="mb-4 flex items-center justify-between gap-3">
              <span class="text-sm font-medium text-slate-700">全局开关</span>
              <a-switch v-model:checked="config.global_enabled" data-testid="global-enabled" />
            </div>
            <div class="text-xs text-slate-400">Key：{{ configKey || '-' }}</div>
          </div>

          <div class="grid gap-4 lg:grid-cols-1">
            <section class="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
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
          </div>
        </div>
      </a-spin>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-base font-semibold text-slate-900">AI动图场景</h3>
        <a-button data-testid="add-video-scene" @click="addVideoScene">
          <template #icon><PlusOutlined /></template>
          添加
        </a-button>
      </div>

      <div>
        <div>
          <div
            class="hidden grid-cols-[180px_minmax(0,1fr)_96px_132px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid"
          >
            <span>按钮名称</span>
            <span>提示词</span>
            <span class="text-center">时长</span>
            <span class="text-right">操作</span>
          </div>
          <div
            v-for="(scene, index) in config.video_scenes"
            :key="scene.id"
            class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[180px_minmax(0,1fr)_96px_132px]"
          >
            <a-input
              v-model:value="scene.name"
              :data-testid="`video-scene-name-${index}`"
            />
            <a-textarea
              v-model:value="scene.prompt"
              :rows="3"
              :data-testid="`video-scene-prompt-${index}`"
            />
            <div class="scene-duration-cell">
              <a-select
                v-model:value="scene.duration"
                :data-testid="`video-scene-duration-${index}`"
                class="scene-duration-select"
              >
                <a-select-option v-for="item in durationOptions" :key="item" :value="item">
                  {{ item }}
                </a-select-option>
              </a-select>
            </div>
            <div class="scene-action-cell">
              <a-button
                class="scene-icon-button"
                :data-testid="`config-video-scene-model-${index}`"
                title="配置模型"
                aria-label="配置模型"
                @click="openSceneConfig('video', index, 'model')"
              >
                <template #icon><SettingOutlined /></template>
              </a-button>
              <a-button
                class="scene-icon-button"
                :data-testid="`config-video-scene-end-frame-${index}`"
                title="配置首尾帧"
                aria-label="配置首尾帧"
                @click="openSceneConfig('video', index, 'reference')"
              >
                <template #icon><LinkOutlined /></template>
              </a-button>
              <a-button
                danger
                class="scene-icon-button"
                :data-testid="`remove-video-scene-${index}`"
                title="删除场景"
                aria-label="删除场景"
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

    <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-base font-semibold text-slate-900">AI绘图场景</h3>
        <a-button data-testid="add-draw-scene" @click="addDrawScene">
          <template #icon><PlusOutlined /></template>
          添加
        </a-button>
      </div>

      <div>
        <div
          class="hidden grid-cols-[180px_minmax(0,1fr)_132px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid"
        >
          <span>按钮名称</span>
          <span>提示词</span>
          <span class="text-right">操作</span>
        </div>
        <div
          v-for="(scene, index) in config.draw_scenes"
          :key="scene.id"
          class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[180px_minmax(0,1fr)_132px]"
        >
          <a-input
            v-model:value="scene.name"
            :data-testid="`draw-scene-name-${index}`"
          />
          <a-textarea
            v-model:value="scene.prompt"
            :rows="3"
            :data-testid="`draw-scene-prompt-${index}`"
          />
          <div class="scene-action-cell">
            <a-button
              class="scene-icon-button"
              :data-testid="`config-draw-scene-model-${index}`"
              title="配置模型"
              aria-label="配置模型"
              @click="openSceneConfig('draw', index, 'model')"
            >
              <template #icon><SettingOutlined /></template>
            </a-button>
            <a-button
              class="scene-icon-button"
              :data-testid="`config-draw-scene-postprocess-${index}`"
              title="配置后处理"
              aria-label="配置后处理"
              @click="openSceneConfig('draw', index, 'reference')"
            >
              <template #icon><LinkOutlined /></template>
            </a-button>
            <a-button
              danger
              class="scene-icon-button"
              :data-testid="`remove-draw-scene-${index}`"
              title="删除场景"
              aria-label="删除场景"
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

    <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h3 class="mb-4 text-base font-semibold text-slate-900">提示词覆盖</h3>
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
      :title="sceneModalTitle"
      :footer="null"
      :width="520"
      wrap-class-name="qqcc-scene-config-modal"
      @cancel="closeSceneConfig"
    >
      <a-form layout="vertical" class="scene-config-form">
        <a-form-item v-if="sceneConfig.panel === 'model'" label="底层模型" class="mb-4">
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
        <a-form-item v-if="sceneConfig.panel === 'model'" label="附加模型" class="mb-4">
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
        <a-form-item
          v-if="sceneConfig.panel === 'reference' && sceneConfig.kind === 'video'"
          label="尾帧来源"
          class="mb-4"
        >
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
        <a-form-item
          v-if="sceneConfig.panel === 'reference' && sceneConfig.kind === 'draw'"
          label="绘图后处理"
          class="mb-4"
        >
          <a-select
            v-model:value="sceneConfig.postprocess_draw_scene_id"
            data-testid="scene-postprocess-select"
            class="w-full"
            :get-popup-container="getSceneSelectPopupContainer"
          >
            <a-select-option value="">无</a-select-option>
            <a-select-option
              v-for="item in activePostprocessDrawOptions"
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
.qqcc-bot-settings {
  width: 100%;
  min-width: 0;
}

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

.scene-row {
  align-items: center;
  min-width: 0;
}

.scene-duration-cell,
.scene-action-cell {
  display: flex;
  align-items: center;
}

.scene-duration-cell {
  justify-content: flex-start;
}

.scene-action-cell {
  justify-content: flex-end;
  gap: 8px;
}

.scene-duration-select {
  width: 88px;
}

.scene-icon-button {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  padding: 0;
}

:deep(.scene-duration-select .ant-select-selector) {
  align-items: center;
  padding-inline-end: 28px;
}

:deep(.scene-duration-select .ant-select-selection-item) {
  text-align: center;
}

:deep(.scene-duration-select .ant-select-arrow) {
  top: 50%;
  margin-top: 0;
  transform: translateY(-50%);
}

:deep(.ant-input),
:deep(.ant-input-affix-wrapper),
:deep(.ant-select-selector),
:deep(textarea.ant-input) {
  border-radius: 7px;
}

:deep(.ant-form-item-label > label) {
  color: #475569;
  font-size: 13px;
  font-weight: 600;
}

@media (max-width: 767px) {
  .scene-row {
    align-items: stretch;
  }

  .scene-duration-cell,
  .scene-action-cell {
    justify-content: flex-start;
  }
}
</style>
