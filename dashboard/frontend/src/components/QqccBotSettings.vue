<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  DeleteOutlined,
  DownOutlined,
  LinkOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
  UploadOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'

type MainButtonKey =
  | 'quick_undress'
  | 'quick_faceswap'
  | 'photo_edit'
  | 'ai_draw'
  | 'ai_filter'
  | 'video_edit'
  | 'market'
  | 'main_bot_link'
  | 'private_bot'
type PhotoButtonKey = 'masturbation' | 'random_faceswap'
type UndressMethodKey = 'legacy' | 'i2i_draw'
type VideoButtonKey = 'missionary' | 'doggy' | 'blowjob' | 'undress_tongue' | 'closeup_blowjob'
type ResolutionKey = '512p' | '720p' | '1024p'
type DurationKey = '5s' | '8s' | '10s'
type VideoSceneEngine = 'image_to_video' | 'wan22_video_v2'
type DrawSceneEngine = 'free_edit' | 'free_edit_v2' | 'free_edit_v3'
type SceneConfigKind = 'video' | 'draw' | 'filter'
type SceneConfigPanel = 'model' | 'reference'
type DemoMediaSlot = 'input' | 'output'
type DemoUploadFile = File & { originFileObj?: File }
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
type CopywritingKey =
  | 'quick_faceswap_start'
  | 'ai_draw_menu'
  | 'ai_filter_menu'
  | 'video_menu'
  | 'ai_draw_scene_start'
  | 'ai_filter_scene_start'
  | 'video_scene_start'

interface SceneDemoMedia {
  object_key: string
  media_type: 'image' | 'video'
  mime_type: string
  file_name: string
  content_sha256?: string
  telegram_file_ids?: Record<string, string>
  preview_url?: string
}

interface SceneDemoFields {
  demo_input_media?: SceneDemoMedia
  demo_output_media?: SceneDemoMedia
}

interface VideoSceneConfig extends SceneDemoFields {
  id: string
  name: string
  prompt: string
  negative_prompt: string
  duration: DurationKey
  engine: VideoSceneEngine
  lora_name: string
  end_frame_draw_scene_id: string
}

interface DrawSceneConfig extends SceneDemoFields {
  id: string
  name: string
  prompt: string
  negative_prompt: string
  engine: DrawSceneEngine
  lora_name: string
  postprocess_draw_scene_id: string
  postprocess_filter_scene_id: string
  original_face_swap_enabled: boolean
}

interface FilterSceneConfig extends SceneDemoFields {
  id: string
  name: string
  prompt: string
  negative_prompt: string
  engine: DrawSceneEngine
  lora_name: string
  original_face_swap_enabled: boolean
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
  filter_scenes: FilterSceneConfig[]
  prompts: Record<PromptKey, string>
  copywriting: Record<CopywritingKey, string>
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

interface QqccDemoMediaUploadResponse {
  media: SceneDemoMedia
  preview_url: string
}

interface QqccDemoGenerationResponse extends Partial<QqccDemoMediaUploadResponse> {
  generation_id: string
  status: string
  error?: string
}

type SceneConfig = VideoSceneConfig | DrawSceneConfig | FilterSceneConfig

const props = defineProps<{
  fetchConfig: () => Promise<QqccBotConfigResponse>
  updateConfig: (payload: QqccBotConfig) => Promise<QqccBotConfigResponse>
  uploadDemoMedia: (
    sceneKind: SceneConfigKind,
    sceneId: string,
    slot: DemoMediaSlot,
    file: File,
  ) => Promise<QqccDemoMediaUploadResponse>
  generateDemoMedia: (
    sceneKind: SceneConfigKind,
    scene: SceneConfig,
  ) => Promise<QqccDemoGenerationResponse>
  getDemoGeneration: (
    sceneKind: SceneConfigKind,
    sceneId: string,
    generationId: string,
  ) => Promise<QqccDemoGenerationResponse>
  demoMediaObjectPrefixes?: string[]
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

const filterSceneMaxCount = 20

const emptyConfig = (): QqccBotConfig => ({
  scene_preset_version: 1,
  global_enabled: false,
  main_buttons: {
    quick_undress: false,
    quick_faceswap: false,
    photo_edit: false,
    ai_draw: false,
    ai_filter: false,
    video_edit: false,
    market: false,
    main_bot_link: false,
    private_bot: false,
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
  filter_scenes: [],
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
  copywriting: {
    quick_faceswap_start: '',
    ai_draw_menu: '',
    ai_filter_menu: '',
    video_menu: '',
    ai_draw_scene_start: '',
    ai_filter_scene_start: '',
    video_scene_start: '',
  },
})

const mainButtonOptions: Array<{ key: MainButtonKey; label: string }> = [
  { key: 'quick_faceswap', label: '快速换脸' },
  { key: 'ai_draw', label: 'AI绘图' },
  { key: 'ai_filter', label: 'AI滤镜' },
  { key: 'video_edit', label: 'AI动图' },
  { key: 'market', label: '修仙市集' },
  { key: 'main_bot_link', label: '前往主bot' },
  { key: 'private_bot', label: '私有bot' },
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
const demoSlots: DemoMediaSlot[] = ['input', 'output']

const videoEngineLabels: Record<VideoSceneEngine, string> = {
  image_to_video: '图生视频',
  wan22_video_v2: '图生视频v2',
}

const drawEngineLabels: Record<DrawSceneEngine, string> = {
  free_edit: '自由P图',
  free_edit_v2: '自由P图v2',
  free_edit_v3: '自由P图v3',
}

const nonVideoPromptOptions: Array<{ key: PromptKey; label: string }> = [
  { key: 'face_swap', label: '快速换脸' },
]

const copywritingOptions: Array<{
  key: CopywritingKey
  label: string
  defaultText: string
  sceneButton?: boolean
}> = [
  {
    key: 'quick_faceswap_start',
    label: '快速换脸：点击后的文案',
    defaultText: '🎭 **已切换到【快速换脸】模式** (消耗 {cost} 灵石)。\n\n请发送一张【正脸】图片，我将自动匹配模板处理。\n\n随时可以发送 /cancel 退出流程。',
  },
  {
    key: 'ai_draw_menu',
    label: 'AI绘图：主菜单点击后的文案',
    defaultText: '🎨 **AI绘图**\n请选择绘图场景：',
  },
  {
    key: 'ai_filter_menu',
    label: 'AI滤镜：主菜单点击后的文案',
    defaultText: '🪄 **AI滤镜**\n请选择滤镜场景：',
  },
  {
    key: 'video_menu',
    label: 'AI动图：主菜单点击后的文案',
    defaultText: '🎬 **懒人动图**\n请选择演武场景：',
  },
  {
    key: 'ai_draw_scene_start',
    label: 'AI绘图：二级场景点击后的文案',
    defaultText: '🎨 **已切换到【{butten}】模式** (消耗 {cost} 灵石)。\n\n请发送一张图片，我将按照该场景提示词处理。\n\n随时可以发送 /cancel 退出流程。',
    sceneButton: true,
  },
  {
    key: 'ai_filter_scene_start',
    label: 'AI滤镜：二级场景点击后的文案',
    defaultText: '🎨 **已切换到【{butten}】模式** (消耗 {cost} 灵石)。\n\n请发送一张图片，我将按照该场景提示词处理。\n\n随时可以发送 /cancel 退出流程。',
    sceneButton: true,
  },
  {
    key: 'video_scene_start',
    label: 'AI动图：二级场景点击后的文案',
    defaultText: '🎬 **已切换到【{butten}】模式**。\n\n请发送一张【正面清晰图片】，我将自动处理。\n\n随时可以发送 /cancel 退出流程。',
    sceneButton: true,
  },
]

const loading = ref(false)
const saving = ref(false)
const uploadingDemoKeys = ref<ReadonlySet<string>>(new Set())
const generatingDemoKeys = ref<ReadonlySet<string>>(new Set())
const configKey = ref('')
const updatedAt = ref<string | null>(null)
const config = reactive<QqccBotConfig>(emptyConfig())
const modelOptions = reactive<QqccBotConfigOptions>(emptyOptions())
const scenePageSize = 5
const activeSceneTab = ref<SceneConfigKind>('video')
const scenePages = reactive<Record<SceneConfigKind, number>>({
  video: 1,
  draw: 1,
  filter: 1,
})
const sceneCounter = ref(0)
const drawSceneCounter = ref(0)
const filterSceneCounter = ref(0)
const sceneConfig = reactive({
  open: false,
  kind: 'video' as SceneConfigKind,
  panel: 'model' as SceneConfigPanel,
  index: -1,
  engine: 'image_to_video',
  lora_name: '',
  end_frame_draw_scene_id: '',
  postprocess_draw_scene_id: '',
  postprocess_filter_scene_id: '',
  original_face_swap_enabled: false,
})

const statusText = computed(() => (config.global_enabled ? '开启' : '关闭'))
const updatedAtText = computed(() => updatedAt.value || '-')

function paginateScenes<T>(scenes: T[], page: number) {
  const start = (page - 1) * scenePageSize
  return scenes.slice(start, start + scenePageSize).map((scene, offset) => ({
    scene,
    index: start + offset,
  }))
}

const paginatedVideoScenes = computed(() =>
  paginateScenes(config.video_scenes, scenePages.video),
)
const paginatedDrawScenes = computed(() =>
  paginateScenes(config.draw_scenes, scenePages.draw),
)
const paginatedFilterScenes = computed(() =>
  paginateScenes(config.filter_scenes, scenePages.filter),
)

const getSceneCount = (kind: SceneConfigKind) => {
  if (kind === 'video') return config.video_scenes.length
  if (kind === 'draw') return config.draw_scenes.length
  return config.filter_scenes.length
}

const normalizeScenePage = (kind: SceneConfigKind) => {
  const lastPage = Math.max(1, Math.ceil(getSceneCount(kind) / scenePageSize))
  scenePages[kind] = Math.min(Math.max(scenePages[kind], 1), lastPage)
}

const showScenePageContaining = (kind: SceneConfigKind, index: number) => {
  scenePages[kind] = Math.floor(index / scenePageSize) + 1
}

const normalizeVideoEngine = (value: unknown): VideoSceneEngine =>
  value === 'wan22_video_v2' ? 'wan22_video_v2' : 'image_to_video'

const normalizeDrawEngine = (value: unknown): DrawSceneEngine =>
  value === 'free_edit' || value === 'free_edit_v3' ? value : 'free_edit_v2'

const normalizeDemoMedia = (
  raw: unknown,
  options: {
    kind: SceneConfigKind
    sceneId: string
    slot: DemoMediaSlot
  },
): SceneDemoMedia | undefined => {
  const { kind, sceneId, slot } = options
  if (!raw || typeof raw !== 'object') return undefined
  const media = raw as Partial<SceneDemoMedia>
  const expectedMediaType = kind === 'video' && slot === 'output' ? 'video' : 'image'
  const allowedPrefixes = (props.demoMediaObjectPrefixes?.length
    ? props.demoMediaObjectPrefixes
    : ['qqcc/demo'])
    .map(prefix => prefix.replace(/\/+$/, ''))
  const hasAllowedObjectKey = allowedPrefixes.some(
    prefix => {
      const deterministicKey = `${prefix}/${kind}/${sceneId}/${slot}`
      const generatedPrefix = `${prefix}/${kind}/${sceneId}/generated/`
      return media.object_key === deterministicKey || (
        slot === 'output' &&
        typeof media.object_key === 'string' &&
        media.object_key.startsWith(generatedPrefix) &&
        media.object_key.endsWith('/output')
      )
    },
  )
  if (
    typeof media.object_key !== 'string' ||
    !hasAllowedObjectKey ||
    media.media_type !== expectedMediaType ||
    typeof media.mime_type !== 'string'
  ) {
    return undefined
  }
  return {
    object_key: media.object_key,
    media_type: expectedMediaType,
    mime_type: media.mime_type,
    file_name: typeof media.file_name === 'string' ? media.file_name : '',
    content_sha256:
      typeof media.content_sha256 === 'string' ? media.content_sha256 : undefined,
    telegram_file_ids:
      media.telegram_file_ids && typeof media.telegram_file_ids === 'object'
        ? { ...media.telegram_file_ids }
        : {},
    preview_url: typeof media.preview_url === 'string' ? media.preview_url : '',
  }
}

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

const normalizePostprocessFilterSceneId = (
  raw: unknown,
  filterScenes = config.filter_scenes,
) => {
  const sceneId = typeof raw === 'string' ? raw.trim() : ''
  return filterScenes.some((scene) => scene.id === sceneId) ? sceneId : ''
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

const normalizeDrawPostprocessRefs = (
  drawScenes: DrawSceneConfig[],
  filterScenes = config.filter_scenes,
) => {
  drawScenes.forEach((scene, index) => {
    scene.postprocess_draw_scene_id = normalizePostprocessDrawSceneId(
      scene.postprocess_draw_scene_id,
      index,
      drawScenes,
    )
    if (scene.postprocess_draw_scene_id) {
      scene.postprocess_filter_scene_id = ''
    } else {
      scene.postprocess_filter_scene_id = normalizePostprocessFilterSceneId(
        scene.postprocess_filter_scene_id,
        filterScenes,
      )
    }
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
const activePostprocessFilterOptions = computed(() =>
  config.filter_scenes.filter(
    (scene) => scene.id.trim() && scene.name.trim() && scene.prompt.trim(),
  )
)
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
  if (Array.isArray(raw.filter_scenes)) {
    merged.filter_scenes = raw.filter_scenes
      .map((scene, index) => {
        const id = typeof scene?.id === 'string' && scene.id.trim() ? scene.id.trim() : `filter_scene_${index + 1}`
        const name = typeof scene?.name === 'string' ? scene.name : ''
        const prompt = typeof scene?.prompt === 'string' ? scene.prompt : ''
        const negative_prompt =
          typeof scene?.negative_prompt === 'string' ? scene.negative_prompt : ''
        const engine = normalizeDrawEngine(scene?.engine)
        return {
          id,
          name,
          prompt,
          negative_prompt,
          engine,
          lora_name: normalizeLoraName(scene?.lora_name, { kind: 'filter', engine }),
          original_face_swap_enabled: scene?.original_face_swap_enabled === true,
          demo_input_media: normalizeDemoMedia(scene?.demo_input_media, {
            kind: 'filter', sceneId: id, slot: 'input',
          }),
          demo_output_media: normalizeDemoMedia(scene?.demo_output_media, {
            kind: 'filter', sceneId: id, slot: 'output',
          }),
        }
      })
      .filter((scene) => scene.name.trim() || scene.prompt.trim())
  }
  if (Array.isArray(raw.draw_scenes)) {
    const normalizedDrawScenes = raw.draw_scenes
      .map((scene, index) => {
        const id = typeof scene?.id === 'string' && scene.id.trim() ? scene.id.trim() : `draw_scene_${index + 1}`
        const name = typeof scene?.name === 'string' ? scene.name : ''
        const prompt = typeof scene?.prompt === 'string' ? scene.prompt : ''
        const negative_prompt =
          typeof scene?.negative_prompt === 'string' ? scene.negative_prompt : ''
        const engine = normalizeDrawEngine(scene?.engine)
        return {
          id,
          name,
          prompt,
          negative_prompt,
          engine,
          lora_name: normalizeLoraName(scene?.lora_name, { kind: 'draw', engine }),
          postprocess_draw_scene_id:
            typeof scene?.postprocess_draw_scene_id === 'string'
              ? scene.postprocess_draw_scene_id.trim()
              : '',
          postprocess_filter_scene_id:
            typeof scene?.postprocess_filter_scene_id === 'string'
              ? scene.postprocess_filter_scene_id.trim()
              : '',
          original_face_swap_enabled: scene?.original_face_swap_enabled === true,
          demo_input_media: normalizeDemoMedia(scene?.demo_input_media, {
            kind: 'draw', sceneId: id, slot: 'input',
          }),
          demo_output_media: normalizeDemoMedia(scene?.demo_output_media, {
            kind: 'draw', sceneId: id, slot: 'output',
          }),
        }
      })
      .filter((scene) => scene.name.trim() || scene.prompt.trim())
    normalizeDrawPostprocessRefs(normalizedDrawScenes, merged.filter_scenes)
    merged.draw_scenes = normalizedDrawScenes
  }
  if (Array.isArray(raw.video_scenes)) {
    merged.video_scenes = raw.video_scenes
      .map((scene, index) => {
        const id = typeof scene?.id === 'string' && scene.id.trim() ? scene.id.trim() : `scene_${index + 1}`
        const name = typeof scene?.name === 'string' ? scene.name : ''
        const prompt = typeof scene?.prompt === 'string' ? scene.prompt : ''
        const negative_prompt =
          typeof scene?.negative_prompt === 'string' ? scene.negative_prompt : ''
        const duration = durationOptions.includes(scene?.duration as DurationKey)
          ? (scene.duration as DurationKey)
          : '5s'
        const engine = normalizeVideoEngine(scene?.engine)
        return {
          id,
          name,
          prompt,
          negative_prompt,
          duration,
          engine,
          lora_name: normalizeLoraName(scene?.lora_name, { kind: 'video', engine }),
          end_frame_draw_scene_id: normalizeEndFrameDrawSceneId(
            scene?.end_frame_draw_scene_id,
            merged.draw_scenes,
          ),
          demo_input_media: normalizeDemoMedia(scene?.demo_input_media, {
            kind: 'video', sceneId: id, slot: 'input',
          }),
          demo_output_media: normalizeDemoMedia(scene?.demo_output_media, {
            kind: 'video', sceneId: id, slot: 'output',
          }),
        }
      })
      .filter((scene) => scene.name.trim() || scene.prompt.trim())
  }
  Object.keys(merged.prompts).forEach((key) => {
    const promptKey = key as PromptKey
    const value = raw.prompts?.[promptKey]
    if (typeof value === 'string') merged.prompts[promptKey] = value
  })
  Object.keys(merged.copywriting).forEach((key) => {
    const copywritingKey = key as CopywritingKey
    const value = raw.copywriting?.[copywritingKey]
    if (typeof value === 'string') merged.copywriting[copywritingKey] = value
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
    negative_prompt: '',
    duration: '5s',
    engine: normalizeVideoEngine(modelOptions.default_video_engine),
    lora_name: '',
    end_frame_draw_scene_id: '',
  })
  showScenePageContaining('video', config.video_scenes.length - 1)
}

const removeVideoScene = (index: number) => {
  config.video_scenes.splice(index, 1)
  normalizeScenePage('video')
}

const moveScene = (
  kind: SceneConfigKind,
  scenes: Array<{ id: string }>,
  index: number,
  offset: -1 | 1,
) => {
  const targetIndex = index + offset
  if (index < 0 || index >= scenes.length || targetIndex < 0 || targetIndex >= scenes.length) {
    return
  }
  const [scene] = scenes.splice(index, 1)
  if (scene) {
    scenes.splice(targetIndex, 0, scene)
    showScenePageContaining(kind, targetIndex)
  }
}

const createDrawSceneId = () => {
  drawSceneCounter.value += 1
  return `draw_${Date.now().toString(36)}_${drawSceneCounter.value}`
}

const createFilterSceneId = () => {
  filterSceneCounter.value += 1
  return `filter_${Date.now().toString(36)}_${filterSceneCounter.value}`
}

const addDrawScene = () => {
  config.draw_scenes.push({
    id: createDrawSceneId(),
    name: '',
    prompt: '',
    negative_prompt: '',
    engine: normalizeDrawEngine(modelOptions.default_draw_engine),
    lora_name: '',
    postprocess_draw_scene_id: '',
    postprocess_filter_scene_id: '',
    original_face_swap_enabled: false,
  })
  showScenePageContaining('draw', config.draw_scenes.length - 1)
}

const addFilterScene = () => {
  config.filter_scenes.push({
    id: createFilterSceneId(),
    name: '',
    prompt: '',
    negative_prompt: '',
    engine: normalizeDrawEngine(modelOptions.default_draw_engine),
    lora_name: '',
    original_face_swap_enabled: false,
  })
  showScenePageContaining('filter', config.filter_scenes.length - 1)
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
  normalizeScenePage('draw')
}

const removeFilterScene = (index: number) => {
  const [removed] = config.filter_scenes.splice(index, 1)
  if (!removed) return
  config.draw_scenes.forEach((scene) => {
    if (scene.postprocess_filter_scene_id === removed.id) {
      scene.postprocess_filter_scene_id = ''
    }
  })
  normalizeScenePage('filter')
}

const getSceneByKind = (kind: SceneConfigKind, index: number) => {
  if (kind === 'video') return config.video_scenes[index]
  if (kind === 'draw') return config.draw_scenes[index]
  return config.filter_scenes[index]
}

const getDemoMediaAccept = (kind: SceneConfigKind, slot: DemoMediaSlot) =>
  kind === 'video' && slot === 'output'
    ? 'video/mp4,.mp4'
    : 'image/png,image/jpeg,.png,.jpg,.jpeg'

const demoUploadErrorLabels: Record<string, string> = {
  'Input/output demo file type does not match the scene': '文件格式与当前示范槽位不匹配',
  'Demo file is empty or too large': '文件为空或超过大小限制',
  'Demo file content does not match its type': '文件内容与声明格式不一致',
  'Demo media storage unavailable': '媒体存储暂时不可用',
}

const resolveDemoUploadError = (error: unknown) => {
  const candidate = error as {
    message?: unknown
    response?: { status?: unknown; data?: { detail?: unknown } }
  }
  const detail = candidate.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return demoUploadErrorLabels[detail] || detail
  }
  if (candidate.message === 'Network Error') {
    return '网络或公网入口拒绝了上传请求'
  }
  if (candidate.message === 'QQCC_DEMO_UPLOAD_AUTH_REDIRECT') {
    return '公网安全层返回了非预期响应'
  }
  const status = candidate.response?.status
  if (status === 413) return '文件超过公网入口允许的大小'
  if (status === 401) return '登录已失效，请重新登录后上传'
  if (status === 403) return 'Cloudflare 安全规则拦截了上传请求'
  return '未知错误，请稍后重试'
}

const validateDemoUploadFile = (
  kind: SceneConfigKind,
  slot: DemoMediaSlot,
  file: File,
) => {
  const isVideo = kind === 'video' && slot === 'output'
  const allowedTypes = isVideo ? ['video/mp4'] : ['image/png', 'image/jpeg']
  const maxBytes = (isVideo ? 50 : 10) * 1024 * 1024
  if (!allowedTypes.includes(file.type)) {
    return isVideo ? '仅支持 MP4 视频' : '仅支持 JPEG 或 PNG 图片'
  }
  if (!file.size) return '文件内容为空'
  if (file.size > maxBytes) return `文件不能超过 ${isVideo ? 50 : 10}MB`
  return ''
}

const setDemoOperationLoading = (
  keys: typeof uploadingDemoKeys,
  key: string,
  isLoading: boolean,
) => {
  const next = new Set(keys.value)
  if (isLoading) next.add(key)
  else next.delete(key)
  keys.value = next
}

const isDemoUploadLoading = (key: string) => uploadingDemoKeys.value.has(key)
const isDemoGenerationLoading = (key: string) => generatingDemoKeys.value.has(key)

const uploadSceneDemo = async (
  kind: SceneConfigKind,
  index: number,
  slot: DemoMediaSlot,
  uploadFile: DemoUploadFile,
) => {
  const scene = getSceneByKind(kind, index)
  if (!scene?.id) return false
  const file = uploadFile.originFileObj instanceof File
    ? uploadFile.originFileObj
    : uploadFile
  const validationError = validateDemoUploadFile(kind, slot, file)
  if (validationError) {
    message.error(`示范文件上传失败：${validationError}`)
    return false
  }
  const uploadKey = `${kind}:${scene.id}:${slot}`
  setDemoOperationLoading(uploadingDemoKeys, uploadKey, true)
  try {
    const uploaded = await props.uploadDemoMedia(kind, scene.id, slot, file)
    if (!uploaded || typeof uploaded !== 'object' || !uploaded.media) {
      throw new Error('QQCC_DEMO_UPLOAD_AUTH_REDIRECT')
    }
    scene[`demo_${slot}_media`] = {
      ...uploaded.media,
      preview_url: uploaded.preview_url,
    }
    message.success(`${slot === 'input' ? '输入' : '输出'}示范文件已上传，请保存配置`)
  } catch (error: unknown) {
    message.error(`示范文件上传失败：${resolveDemoUploadError(error)}`)
  } finally {
    setDemoOperationLoading(uploadingDemoKeys, uploadKey, false)
  }
  return false
}

const waitForDemoGeneration = async (
  kind: SceneConfigKind,
  sceneId: string,
  generationId: string,
) => {
  const deadline = Date.now() + 15 * 60 * 1000
  while (Date.now() < deadline) {
    const result = await props.getDemoGeneration(kind, sceneId, generationId)
    if (result.status === 'done') return result
    if (result.status === 'failed') throw new Error(result.error || '示范生成失败')
    await new Promise(resolve => window.setTimeout(resolve, 2000))
  }
  throw new Error('示范生成超时，请稍后重试')
}

const generateSceneDemo = async (kind: SceneConfigKind, index: number) => {
  const scene = getSceneByKind(kind, index)
  if (!scene?.demo_input_media) {
    message.error('请先上传输入示范图片')
    return
  }
  if (!scene.prompt.trim()) {
    message.error('请先填写场景提示词')
    return
  }
  const generationKey = `${kind}:${scene.id}`
  setDemoOperationLoading(generatingDemoKeys, generationKey, true)
  try {
    const submitted = await props.generateDemoMedia(kind, JSON.parse(JSON.stringify(scene)))
    const generated = submitted.status === 'done'
      ? submitted
      : await waitForDemoGeneration(kind, scene.id, submitted.generation_id)
    if (!generated?.media) throw new Error('QQCC_DEMO_GENERATION_INVALID_RESPONSE')
    scene.demo_output_media = { ...generated.media, preview_url: generated.preview_url }
    message.success('输出示范已生成，请检查后保存配置')
  } catch (error: unknown) {
    const candidate = error as { response?: { data?: { detail?: unknown } } }
    const detail = candidate.response?.data?.detail
    message.error(`示范生成失败：${typeof detail === 'string' ? detail : '请稍后重试'}`)
  } finally {
    setDemoOperationLoading(generatingDemoKeys, generationKey, false)
  }
}

const validateVideoScenes = () =>
  config.video_scenes.every((scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()))

const validateDrawScenes = () =>
  config.draw_scenes.every(
    (scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()),
  )

const validateFilterScenes = () =>
  config.filter_scenes.every(
    (scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()),
  )

const buildPayload = (): QqccBotConfig => {
  const payload = JSON.parse(JSON.stringify(config)) as QqccBotConfig
  payload.scene_preset_version = config.scene_preset_version || modelOptions.scene_preset_version
  legacyMainButtonKeys.forEach((key) => {
    payload.main_buttons[key] = false
  })
  Object.keys(payload.copywriting).forEach((key) => {
    const copywritingKey = key as CopywritingKey
    payload.copywriting[copywritingKey] = payload.copywriting[copywritingKey].trim()
  })
  payload.filter_scenes = payload.filter_scenes
    .map((scene) => {
      const engine = normalizeDrawEngine(scene.engine)
      return {
        ...scene,
        id: scene.id.trim(),
        name: scene.name.trim(),
        prompt: scene.prompt.trim(),
        negative_prompt: scene.negative_prompt.trim(),
        engine,
        lora_name: normalizeLoraName(scene.lora_name, { kind: 'filter', engine }),
        original_face_swap_enabled: scene.original_face_swap_enabled === true,
      }
    })
    .filter((scene) => scene.name || scene.prompt)
    .slice(0, filterSceneMaxCount)
  const normalizedDrawScenes = payload.draw_scenes
    .map((scene) => {
      const engine = normalizeDrawEngine(scene.engine)
      return {
        ...scene,
        id: scene.id.trim(),
        name: scene.name.trim(),
        prompt: scene.prompt.trim(),
        negative_prompt: scene.negative_prompt.trim(),
        engine,
        lora_name: normalizeLoraName(scene.lora_name, { kind: 'draw', engine }),
        postprocess_draw_scene_id:
          typeof scene.postprocess_draw_scene_id === 'string'
            ? scene.postprocess_draw_scene_id.trim()
            : '',
        postprocess_filter_scene_id:
          typeof scene.postprocess_filter_scene_id === 'string'
            ? scene.postprocess_filter_scene_id.trim()
            : '',
        original_face_swap_enabled: scene.original_face_swap_enabled === true,
      }
    })
    .filter((scene) => scene.name || scene.prompt)
  normalizeDrawPostprocessRefs(normalizedDrawScenes, payload.filter_scenes)
  payload.draw_scenes = normalizedDrawScenes
  payload.video_scenes = payload.video_scenes
    .map((scene) => {
      const engine = normalizeVideoEngine(scene.engine)
      return {
        ...scene,
        id: scene.id.trim(),
        name: scene.name.trim(),
        prompt: scene.prompt.trim(),
        negative_prompt: scene.negative_prompt.trim(),
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
  normalizeScenePage('video')
  normalizeScenePage('draw')
  normalizeScenePage('filter')
  configKey.value = payload.key || ''
  updatedAt.value = payload.updated_at || null
}

const openSceneConfig = (
  kind: SceneConfigKind,
  index: number,
  panel: SceneConfigPanel,
) => {
  const scene =
    kind === 'video'
      ? config.video_scenes[index]
      : kind === 'filter'
        ? config.filter_scenes[index]
        : config.draw_scenes[index]
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
  sceneConfig.postprocess_filter_scene_id =
    kind === 'draw'
      ? normalizePostprocessFilterSceneId((scene as DrawSceneConfig).postprocess_filter_scene_id)
      : ''
  sceneConfig.original_face_swap_enabled =
    kind !== 'video' ? (scene as DrawSceneConfig | FilterSceneConfig).original_face_swap_enabled === true : false
  sceneConfig.open = true
}

const closeSceneConfig = () => {
  sceneConfig.open = false
  sceneConfig.panel = 'model'
  sceneConfig.index = -1
  sceneConfig.end_frame_draw_scene_id = ''
  sceneConfig.postprocess_draw_scene_id = ''
  sceneConfig.postprocess_filter_scene_id = ''
  sceneConfig.original_face_swap_enabled = false
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
  } else if (sceneConfig.kind === 'draw') {
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
      scene.postprocess_filter_scene_id = postprocessDrawSceneId
        ? ''
        : normalizePostprocessFilterSceneId(sceneConfig.postprocess_filter_scene_id)
      scene.original_face_swap_enabled = sceneConfig.original_face_swap_enabled === true
    }
  } else {
    const scene = config.filter_scenes[sceneConfig.index]
    if (!scene) return
    const engine = normalizeDrawEngine(sceneConfig.engine)
    scene.engine = engine
    scene.lora_name = normalizeLoraName(sceneConfig.lora_name, { kind: 'filter', engine })
    scene.original_face_swap_enabled = sceneConfig.original_face_swap_enabled === true
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
  if (!validateFilterScenes()) {
    message.error('请完善AI滤镜场景的按钮名称和提示词')
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
                  <a-switch
                    v-model:checked="config.main_buttons[item.key]"
                    :data-testid="`main-button-${item.key}`"
                  />
                </div>
              </div>
            </section>
          </div>
        </div>
      </a-spin>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h3 class="mb-1 text-base font-semibold text-slate-900">交互文案</h3>
      <p class="mb-4 text-sm text-slate-500">
        输入框直接展示当前系统默认文案；留空时仍使用它。二级场景文案可使用 <code>{butten}</code>，发送时会自动替换为用户点击的按钮名称。
      </p>
      <div class="grid gap-4 lg:grid-cols-2">
        <a-form-item v-for="item in copywritingOptions" :key="item.key" :label="item.label">
          <a-textarea
            v-model:value="config.copywriting[item.key]"
            :rows="item.sceneButton ? 4 : 3"
            :maxlength="4000"
            :data-testid="`copywriting-${item.key}`"
            :placeholder="item.defaultText"
          />
        </a-form-item>
      </div>
    </section>

    <section class="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div class="mb-1">
        <h3 class="text-base font-semibold text-slate-900">AI场景配置</h3>
        <p class="mt-1 text-sm text-slate-500">切换场景类型进行编辑，每页显示 5 条。</p>
      </div>

      <a-tabs v-model:active-key="activeSceneTab" class="scene-tabs">
        <a-tab-pane key="video">
          <template #tab>
            <span data-testid="scene-tab-video">AI动图 <span class="scene-tab-count">{{ config.video_scenes.length }}</span></span>
          </template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar">
              <span class="text-sm text-slate-500">管理动图按钮、提示词、时长、模型和尾帧来源</span>
              <a-button data-testid="add-video-scene" @click="addVideoScene">
                <template #icon><PlusOutlined /></template>
                添加场景
              </a-button>
            </div>
            <div class="hidden grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)_88px_286px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid">
              <span>按钮名称</span><span>提示词</span><span>负面提示词</span><span class="text-center">时长</span><span class="text-right">操作</span>
            </div>
            <div
              v-for="{ scene, index } in paginatedVideoScenes"
              :key="scene.id"
              class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)_88px_286px]"
            >
              <a-input v-model:value="scene.name" :data-testid="`video-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`video-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`video-scene-negative-prompt-${index}`" />
              <div class="scene-duration-cell">
                <a-select v-model:value="scene.duration" :data-testid="`video-scene-duration-${index}`" class="scene-duration-select">
                  <a-select-option v-for="item in durationOptions" :key="item" :value="item">{{ item }}</a-select-option>
                </a-select>
              </div>
              <div class="scene-action-cell">
                <div class="scene-management-actions">
                  <a-button class="scene-icon-button" :disabled="index === 0" :data-testid="`move-video-scene-up-${index}`" title="上移场景" aria-label="上移场景" @click="moveScene('video', config.video_scenes, index, -1)"><template #icon><UpOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :disabled="index === config.video_scenes.length - 1" :data-testid="`move-video-scene-down-${index}`" title="下移场景" aria-label="下移场景" @click="moveScene('video', config.video_scenes, index, 1)"><template #icon><DownOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-video-scene-model-${index}`" title="配置模型" aria-label="配置模型" @click="openSceneConfig('video', index, 'model')"><template #icon><SettingOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-video-scene-end-frame-${index}`" title="配置首尾帧" aria-label="配置首尾帧" @click="openSceneConfig('video', index, 'reference')"><template #icon><LinkOutlined /></template></a-button>
                  <a-button danger class="scene-icon-button" :data-testid="`remove-video-scene-${index}`" title="删除场景" aria-label="删除场景" @click="removeVideoScene(index)"><template #icon><DeleteOutlined /></template></a-button>
                </div>
                <div class="scene-demo-actions">
                  <span class="scene-demo-action-label">示范素材</span>
                  <div class="scene-demo-button-group">
                  <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('video', 'input')" :before-upload="(file: File) => uploadSceneDemo('video', index, 'input', file)">
                    <a-button size="small" :loading="isDemoUploadLoading(`video:${scene.id}:input`)" :data-testid="`upload-video-demo-input-${index}`"><template #icon><UploadOutlined /></template>输入示范</a-button>
                  </a-upload>
                  <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('video', 'output')" :before-upload="(file: File) => uploadSceneDemo('video', index, 'output', file)">
                    <a-button size="small" :loading="isDemoUploadLoading(`video:${scene.id}:output`)" :data-testid="`upload-video-demo-output-${index}`"><template #icon><UploadOutlined /></template>输出示范</a-button>
                  </a-upload>
                  <a-button type="primary" size="small" :disabled="!scene.demo_input_media" :loading="isDemoGenerationLoading(`video:${scene.id}`)" :data-testid="`generate-video-demo-${index}`" @click="generateSceneDemo('video', index)"><template #icon><PlayCircleOutlined /></template>生成</a-button>
                  </div>
                </div>
                <div v-if="scene.demo_input_media || scene.demo_output_media" class="scene-demo-preview-strip">
                  <div v-for="slot in demoSlots" :key="slot" class="scene-demo-preview-card" :title="slot === 'input' ? '输入示范' : '输出示范'">
                  <span class="scene-demo-preview-label">{{ slot === 'input' ? '输入' : '输出' }}</span>
                  <a-image v-if="scene[`demo_${slot}_media`]?.media_type === 'image' && scene[`demo_${slot}_media`]?.preview_url" :src="scene[`demo_${slot}_media`]?.preview_url" :width="60" :height="60" :data-testid="`video-demo-${slot}-preview-${index}`" alt="示范图片" />
                  <video v-else-if="scene[`demo_${slot}_media`]?.media_type === 'video' && scene[`demo_${slot}_media`]?.preview_url" :src="scene[`demo_${slot}_media`]?.preview_url" :data-testid="`video-demo-${slot}-preview-${index}`" controls preload="metadata" />
                  <span v-else class="scene-demo-preview-empty">未上传</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="config.video_scenes.length === 0" class="py-8 text-center text-sm text-slate-400">暂无场景</div>
            <div v-else class="scene-pagination-bar">
              <span>共 {{ config.video_scenes.length }} 个场景</span>
              <a-pagination v-model:current="scenePages.video" :total="config.video_scenes.length" :page-size="scenePageSize" :show-size-changer="false" :hide-on-single-page="true" show-less-items data-testid="video-scenes-pagination" />
            </div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="draw">
          <template #tab>
            <span data-testid="scene-tab-draw">AI绘图 <span class="scene-tab-count">{{ config.draw_scenes.length }}</span></span>
          </template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar">
              <span class="text-sm text-slate-500">管理绘图按钮、提示词、模型和后处理链</span>
              <a-button data-testid="add-draw-scene" @click="addDrawScene"><template #icon><PlusOutlined /></template>添加场景</a-button>
            </div>
            <div class="hidden grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)_286px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid">
              <span>按钮名称</span><span>提示词</span><span>负面提示词</span><span class="text-right">操作</span>
            </div>
            <div
              v-for="{ scene, index } in paginatedDrawScenes"
              :key="scene.id"
              class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)_286px]"
            >
              <a-input v-model:value="scene.name" :data-testid="`draw-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`draw-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`draw-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell">
                <div class="scene-management-actions">
                  <a-button class="scene-icon-button" :disabled="index === 0" :data-testid="`move-draw-scene-up-${index}`" title="上移场景" aria-label="上移场景" @click="moveScene('draw', config.draw_scenes, index, -1)"><template #icon><UpOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :disabled="index === config.draw_scenes.length - 1" :data-testid="`move-draw-scene-down-${index}`" title="下移场景" aria-label="下移场景" @click="moveScene('draw', config.draw_scenes, index, 1)"><template #icon><DownOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-draw-scene-model-${index}`" title="配置模型" aria-label="配置模型" @click="openSceneConfig('draw', index, 'model')"><template #icon><SettingOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-draw-scene-postprocess-${index}`" title="配置后处理" aria-label="配置后处理" @click="openSceneConfig('draw', index, 'reference')"><template #icon><LinkOutlined /></template></a-button>
                  <a-button danger class="scene-icon-button" :data-testid="`remove-draw-scene-${index}`" title="删除场景" aria-label="删除场景" @click="removeDrawScene(index)"><template #icon><DeleteOutlined /></template></a-button>
                </div>
                <div class="scene-demo-actions">
                  <span class="scene-demo-action-label">示范素材</span>
                  <div class="scene-demo-button-group">
                  <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('draw', 'input')" :before-upload="(file: File) => uploadSceneDemo('draw', index, 'input', file)">
                    <a-button size="small" :loading="isDemoUploadLoading(`draw:${scene.id}:input`)" :data-testid="`upload-draw-demo-input-${index}`"><template #icon><UploadOutlined /></template>输入示范</a-button>
                  </a-upload>
                  <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('draw', 'output')" :before-upload="(file: File) => uploadSceneDemo('draw', index, 'output', file)">
                    <a-button size="small" :loading="isDemoUploadLoading(`draw:${scene.id}:output`)" :data-testid="`upload-draw-demo-output-${index}`"><template #icon><UploadOutlined /></template>输出示范</a-button>
                  </a-upload>
                  <a-button type="primary" size="small" :disabled="!scene.demo_input_media" :loading="isDemoGenerationLoading(`draw:${scene.id}`)" :data-testid="`generate-draw-demo-${index}`" @click="generateSceneDemo('draw', index)"><template #icon><PlayCircleOutlined /></template>生成</a-button>
                  </div>
                </div>
                <div v-if="scene.demo_input_media || scene.demo_output_media" class="scene-demo-preview-strip">
                  <div v-for="slot in demoSlots" :key="slot" class="scene-demo-preview-card" :title="slot === 'input' ? '输入示范' : '输出示范'">
                  <span class="scene-demo-preview-label">{{ slot === 'input' ? '输入' : '输出' }}</span>
                  <a-image v-if="scene[`demo_${slot}_media`]?.preview_url" :src="scene[`demo_${slot}_media`]?.preview_url" :width="60" :height="60" :data-testid="`draw-demo-${slot}-preview-${index}`" alt="示范图片" />
                  <span v-else class="scene-demo-preview-empty">未上传</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="config.draw_scenes.length === 0" class="py-8 text-center text-sm text-slate-400">暂无场景</div>
            <div v-else class="scene-pagination-bar">
              <span>共 {{ config.draw_scenes.length }} 个场景</span>
              <a-pagination v-model:current="scenePages.draw" :total="config.draw_scenes.length" :page-size="scenePageSize" :show-size-changer="false" :hide-on-single-page="true" show-less-items data-testid="draw-scenes-pagination" />
            </div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="filter">
          <template #tab>
            <span data-testid="scene-tab-filter">AI滤镜 <span class="scene-tab-count">{{ config.filter_scenes.length }}</span></span>
          </template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar">
              <span class="text-sm text-slate-500">管理滤镜按钮、提示词和底层模型</span>
              <a-button data-testid="add-filter-scene" @click="addFilterScene"><template #icon><PlusOutlined /></template>添加场景</a-button>
            </div>
            <div class="hidden grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)_286px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid">
              <span>按钮名称</span><span>提示词</span><span>负面提示词</span><span class="text-right">操作</span>
            </div>
            <div
              v-for="{ scene, index } in paginatedFilterScenes"
              :key="scene.id"
              class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)_286px]"
            >
              <a-input v-model:value="scene.name" :data-testid="`filter-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`filter-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`filter-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell">
                <div class="scene-management-actions">
                  <a-button class="scene-icon-button" :disabled="index === 0" :data-testid="`move-filter-scene-up-${index}`" title="上移场景" aria-label="上移场景" @click="moveScene('filter', config.filter_scenes, index, -1)"><template #icon><UpOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :disabled="index === config.filter_scenes.length - 1" :data-testid="`move-filter-scene-down-${index}`" title="下移场景" aria-label="下移场景" @click="moveScene('filter', config.filter_scenes, index, 1)"><template #icon><DownOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-filter-scene-model-${index}`" title="配置模型" aria-label="配置模型" @click="openSceneConfig('filter', index, 'model')"><template #icon><SettingOutlined /></template></a-button>
                  <a-button danger class="scene-icon-button" :data-testid="`remove-filter-scene-${index}`" title="删除场景" aria-label="删除场景" @click="removeFilterScene(index)"><template #icon><DeleteOutlined /></template></a-button>
                </div>
                <div class="scene-demo-actions">
                  <span class="scene-demo-action-label">示范素材</span>
                  <div class="scene-demo-button-group">
                    <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('filter', 'input')" :before-upload="(file: File) => uploadSceneDemo('filter', index, 'input', file)">
                      <a-button size="small" :loading="isDemoUploadLoading(`filter:${scene.id}:input`)" :data-testid="`upload-filter-demo-input-${index}`"><template #icon><UploadOutlined /></template>输入示范</a-button>
                    </a-upload>
                    <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('filter', 'output')" :before-upload="(file: File) => uploadSceneDemo('filter', index, 'output', file)">
                      <a-button size="small" :loading="isDemoUploadLoading(`filter:${scene.id}:output`)" :data-testid="`upload-filter-demo-output-${index}`"><template #icon><UploadOutlined /></template>输出示范</a-button>
                    </a-upload>
                    <a-button type="primary" size="small" :disabled="!scene.demo_input_media" :loading="isDemoGenerationLoading(`filter:${scene.id}`)" :data-testid="`generate-filter-demo-${index}`" @click="generateSceneDemo('filter', index)"><template #icon><PlayCircleOutlined /></template>生成</a-button>
                  </div>
                </div>
                <div v-if="scene.demo_input_media || scene.demo_output_media" class="scene-demo-preview-strip">
                  <div v-for="slot in demoSlots" :key="slot" class="scene-demo-preview-card" :title="slot === 'input' ? '输入示范' : '输出示范'">
                  <span class="scene-demo-preview-label">{{ slot === 'input' ? '输入' : '输出' }}</span>
                  <a-image v-if="scene[`demo_${slot}_media`]?.preview_url" :src="scene[`demo_${slot}_media`]?.preview_url" :width="60" :height="60" :data-testid="`filter-demo-${slot}-preview-${index}`" alt="示范图片" />
                  <span v-else class="scene-demo-preview-empty">未上传</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="config.filter_scenes.length === 0" class="py-8 text-center text-sm text-slate-400">暂无场景</div>
            <div v-else class="scene-pagination-bar">
              <span>共 {{ config.filter_scenes.length }} 个场景</span>
              <a-pagination v-model:current="scenePages.filter" :total="config.filter_scenes.length" :page-size="scenePageSize" :show-size-changer="false" :hide-on-single-page="true" show-less-items data-testid="filter-scenes-pagination" />
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>
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
          v-if="sceneConfig.panel === 'model' && sceneConfig.kind === 'filter'"
          label="原图换脸"
          class="mb-4"
        >
          <a-switch
            v-model:checked="sceneConfig.original_face_swap_enabled"
            data-testid="filter-scene-original-face-swap-switch"
          />
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
        <a-form-item
          v-if="sceneConfig.panel === 'reference' && sceneConfig.kind === 'draw'"
          label="滤镜后处理"
          class="mb-4"
        >
          <a-select
            v-model:value="sceneConfig.postprocess_filter_scene_id"
            data-testid="scene-postprocess-filter-select"
            class="w-full"
            :get-popup-container="getSceneSelectPopupContainer"
          >
            <a-select-option value="">无</a-select-option>
            <a-select-option
              v-for="item in activePostprocessFilterOptions"
              :key="item.id"
              :value="item.id"
            >
              {{ item.name || item.id }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item
          v-if="sceneConfig.panel === 'reference' && sceneConfig.kind === 'draw'"
          label="原图换脸"
          class="mb-4"
        >
          <a-switch
            v-model:checked="sceneConfig.original_face_swap_enabled"
            data-testid="scene-original-face-swap-switch"
          />
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

.scene-tabs {
  margin-top: 8px;
}

.scene-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 14px;
}

.scene-tab-count {
  display: inline-flex;
  min-width: 22px;
  height: 20px;
  margin-left: 6px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 0 7px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 12px;
  line-height: 20px;
}

.scene-pane {
  min-width: 0;
}

.scene-pane-toolbar,
.scene-pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.scene-pane-toolbar {
  min-height: 40px;
  margin-bottom: 12px;
}

.scene-pagination-bar {
  min-height: 44px;
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
  color: #64748b;
  font-size: 13px;
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
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 10px;
}

.scene-management-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.scene-demo-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid #f1f5f9;
}

.scene-demo-action-label {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.scene-demo-button-group {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.scene-demo-preview-strip {
  display: flex;
  width: 100%;
  justify-content: flex-end;
  gap: 6px;
}

.scene-demo-preview-card {
  width: 68px;
  min-width: 68px;
  padding: 3px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
  text-align: center;
}

.scene-demo-preview-card :deep(.ant-image-img),
.scene-demo-preview-card video {
  display: block;
  width: 60px;
  height: 60px;
  border-radius: 4px;
  background: #0f172a;
  object-fit: cover;
}

.scene-demo-preview-label,
.scene-demo-preview-empty {
  display: block;
  margin-bottom: 2px;
  color: #64748b;
  font-size: 10px;
  line-height: 14px;
}

.scene-demo-preview-empty {
  height: 60px;
  margin-bottom: 0;
  align-content: center;
  text-align: center;
  word-break: keep-all;
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

  .scene-management-actions,
  .scene-demo-button-group,
  .scene-demo-preview-strip {
    justify-content: start;
  }

  .scene-demo-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .scene-pane-toolbar,
  .scene-pagination-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .scene-pane-toolbar :deep(.ant-btn) {
    width: 100%;
  }
}
</style>
