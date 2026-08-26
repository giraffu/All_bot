<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import {
  DeleteOutlined,
  DownOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
  UploadOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import {
  getWan22LoraHelp,
  type Wan22LoraHelpModel,
  type Wan22LoraStrengthStage,
} from '../data/wan22LoraHelp'
import { useQqccConfigPersistence } from '../composables/useQqccConfigPersistence'

type MainButtonKey =
  | 'quick_undress'
  | 'quick_faceswap'
  | 'photo_edit'
  | 'ai_draw'
  | 'ai_draw_v1'
  | 'ai_draw_v2'
  | 'ai_filter'
  | 'video_edit'
  | 'video_edit_v1'
  | 'video_edit_v2'
  | 'ai_video'
  | 'market'
  | 'queue'
  | 'main_bot_link'
  | 'private_bot'
type MainMenuButtonKey = Exclude<MainButtonKey, 'quick_undress' | 'photo_edit'>
type MainMenuButtonsPerRow = 1 | 2 | 3 | 4
type PhotoButtonKey = 'masturbation' | 'random_faceswap'
type UndressMethodKey = 'legacy' | 'i2i_draw'
type VideoButtonKey = 'missionary' | 'doggy' | 'blowjob' | 'undress_tongue' | 'closeup_blowjob'
type ResolutionKey = '512p' | '720p' | '1024p'
type AiVideoResolutionKey = 'preview' | 'small' | 'standard' | 'hd'
type DurationKey = '5s' | '8s' | '10s'
type AiVideoDurationKey = 5 | 10 | 15
type VideoSceneEngine = 'image_to_video' | 'wan22_video_v2'
type VideoAspectRatio = 'source' | '9:16' | '16:9' | '1:1'
type AiVideoSceneEngine = 'minimax_h3'
type AiVideoMainModel = '10eros' | 'official' | 'official_ref2v_turbo'
type AiVideoMode = 'i2v' | 'ref2v'
type AiVideoCreditCosts = Partial<Record<
  AiVideoMode,
  Partial<Record<AiVideoDurationKey, Partial<Record<AiVideoResolutionKey, number>>>>
>>
type AiVideoAspectRatio = '16:9' | '9:16' | '1:1'
type DrawSceneEngine = 'free_edit' | 'free_edit_v2' | 'free_edit_v2_5' | 'free_edit_v3'
type SceneConfigKind = 'video' | 'video_v1' | 'ai_video' | 'draw' | 'draw_v1' | 'filter'
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
  | 'ai_video_menu'
  | 'ai_draw_scene_start'
  | 'ai_filter_scene_start'
  | 'video_scene_start'
  | 'ai_video_scene_start'

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
  resolution: ResolutionKey
  engine: VideoSceneEngine
  aspect_ratio: VideoAspectRatio
  lora_name: string
  lora_strength: number
  lora_items: VideoLoraItem[]
  end_frame_draw_scene_id: string
  jump_draw_scene_id?: string
  next_scene_id: string | null
  credit_cost: number | null
}

interface VideoLoraItem {
  name: string
  strength: number
}

interface AiVideoLoraItem {
  name: string
  strength: number
}

interface AiVideoSceneConfig extends SceneDemoFields {
  id: string
  name: string
  prompt: string
  negative_prompt: string
  duration: AiVideoDurationKey
  resolution: AiVideoResolutionKey
  engine: AiVideoSceneEngine
  main_model: AiVideoMainModel
  mode: AiVideoMode
  reference_images: string[]
  reference_image_names: string[]
  reference_image_telegram_file_ids: Record<string, string>[]
  reference_image_previews?: string[]
  aspect_ratio: AiVideoAspectRatio
  lora_items: AiVideoLoraItem[]
  end_frame_draw_scene_id: string
  jump_draw_scene_id?: string
  next_scene_id: string | null
  credit_cost: number | null
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
  credit_cost: number | null
}

interface FilterSceneConfig extends SceneDemoFields {
  id: string
  name: string
  prompt: string
  negative_prompt: string
  engine: DrawSceneEngine
  lora_name: string
  original_face_swap_enabled: boolean
  credit_cost: number | null
}

interface QqccBotConfig {
  scene_preset_version: number
  global_enabled: boolean
  main_buttons: Record<MainButtonKey, boolean>
  main_menu_layout: {
    buttons_per_row: MainMenuButtonsPerRow | null
    button_order: MainMenuButtonKey[]
  }
  photo_buttons: Record<PhotoButtonKey, boolean>
  undress_methods: Record<UndressMethodKey, boolean>
  video_buttons: Record<VideoButtonKey, boolean>
  video_settings: {
    resolutions: Record<ResolutionKey, boolean>
    durations: Record<DurationKey, boolean>
  }
  video_scenes: VideoSceneConfig[]
  video_scenes_v1: VideoSceneConfig[]
  video_scenes_v2: VideoSceneConfig[]
  ai_video_scenes: AiVideoSceneConfig[]
  draw_scenes: DrawSceneConfig[]
  draw_scenes_v1: DrawSceneConfig[]
  draw_scenes_v2: DrawSceneConfig[]
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
  default_strength?: number
  supported_modes?: AiVideoMode[]
}

interface ResolutionOption<T extends string> {
  value: T
  label: string
}

interface AiVideoMainModelOption extends ResolutionOption<AiVideoMainModel> {
  supported_modes?: AiVideoMode[]
}

interface QqccBotConfigOptions {
  scene_preset_version: number
  default_video_engine: VideoSceneEngine
  default_ai_video_engine: AiVideoSceneEngine
  default_ai_video_main_model: AiVideoMainModel
  default_draw_engine: DrawSceneEngine
  video_engines: SceneEngineOption[]
  video_aspect_ratios: VideoAspectRatio[]
  ai_video_engines: SceneEngineOption[]
  draw_engines: SceneEngineOption[]
  video_lora_models: LoraModelOption[]
  ai_video_addon_models_version: number
  ai_video_addon_models: LoraModelOption[]
  image_lora_models: LoraModelOption[]
  video_resolutions: ResolutionOption<ResolutionKey>[]
  ai_video_resolutions: ResolutionOption<AiVideoResolutionKey>[]
  ai_video_main_models: AiVideoMainModelOption[]
  default_video_resolution: ResolutionKey
  default_ai_video_resolution: AiVideoResolutionKey
  default_scene_credit_costs: Partial<Record<SceneConfigKind, number>>
  ai_video_credit_costs: AiVideoCreditCosts
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

interface QqccReferenceImageUploadResponse {
  media: SceneDemoMedia
  preview_url: string
}

interface QqccDemoGenerationResponse extends Partial<QqccDemoMediaUploadResponse> {
  generation_id: string
  status: string
  config_saved?: boolean
  error?: string
}

type SceneConfig = VideoSceneConfig | AiVideoSceneConfig | DrawSceneConfig | FilterSceneConfig

const props = defineProps<{
  fetchConfig: () => Promise<QqccBotConfigResponse>
  updateConfig: (payload: QqccBotConfig) => Promise<QqccBotConfigResponse>
  uploadDemoMedia: (
    sceneKind: SceneConfigKind,
    sceneId: string,
    slot: DemoMediaSlot,
    file: File,
  ) => Promise<QqccDemoMediaUploadResponse>
  uploadReferenceImage?: (
    sceneId: string,
    index: number,
    file: File,
  ) => Promise<QqccReferenceImageUploadResponse>
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
  ref2vEnabled?: boolean
}>()

const emptyOptions = (): QqccBotConfigOptions => ({
  scene_preset_version: 1,
  default_video_engine: 'image_to_video',
  default_ai_video_engine: 'minimax_h3',
  default_ai_video_main_model: '10eros',
  default_draw_engine: 'free_edit_v2',
  video_engines: [],
  video_aspect_ratios: ['source', '9:16', '16:9', '1:1'],
  ai_video_engines: [],
  draw_engines: [],
  video_lora_models: [],
  ai_video_addon_models_version: 6,
  ai_video_addon_models: [],
  image_lora_models: [],
  video_resolutions: [],
  ai_video_resolutions: [],
  ai_video_main_models: [
    { value: '10eros', label: '10Eros Max H3 v3' },
    { value: 'official', label: 'MiniMax H3 官方模型' },
    {
      value: 'official_ref2v_turbo', label: '官方 REF2V 极速',
      supported_modes: ['ref2v'],
    },
  ],
  default_video_resolution: '720p',
  default_ai_video_resolution: 'preview',
  default_scene_credit_costs: {},
  ai_video_credit_costs: { i2v: {}, ref2v: {} },
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
    ai_draw_v1: false,
    ai_draw_v2: false,
    ai_filter: false,
    video_edit: false,
    video_edit_v1: false,
    video_edit_v2: false,
    ai_video: false,
    market: false,
    queue: false,
    main_bot_link: false,
    private_bot: false,
  },
  main_menu_layout: {
    buttons_per_row: null,
    button_order: [
      'quick_faceswap',
      'ai_draw',
      'ai_filter',
      'video_edit',
      'ai_video',
      'market',
      'queue',
      'private_bot',
      'main_bot_link',
    ],
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
  video_scenes_v1: [],
  video_scenes_v2: [],
  ai_video_scenes: [],
  draw_scenes: [],
  draw_scenes_v1: [],
  draw_scenes_v2: [],
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
    ai_video_menu: '',
    ai_draw_scene_start: '',
    ai_filter_scene_start: '',
    video_scene_start: '',
    ai_video_scene_start: '',
  },
})

const mainButtonOptions: Array<{ key: MainMenuButtonKey; label: string }> = [
  { key: 'quick_faceswap', label: '快速换脸' },
  { key: 'ai_draw_v1', label: 'AI绘图V1' },
  { key: 'ai_draw_v2', label: 'AI绘图V2' },
  { key: 'ai_filter', label: 'AI滤镜' },
  { key: 'video_edit_v1', label: 'AI动图V1' },
  { key: 'video_edit_v2', label: 'AI动图V2' },
  { key: 'ai_video', label: 'AI视频' },
  { key: 'market', label: '修仙市集' },
  { key: 'queue', label: '排队状态' },
  { key: 'private_bot', label: '私有bot' },
  { key: 'main_bot_link', label: '前往主bot' },
]
const mainMenuButtonKeys = mainButtonOptions.map((item) => item.key)
const mainButtonOptionsByKey = Object.fromEntries(
  mainButtonOptions.map((item) => [item.key, item]),
) as Record<MainMenuButtonKey, { key: MainMenuButtonKey; label: string }>
const normalizeMainMenuButtonOrder = (raw: unknown): MainMenuButtonKey[] => {
  const ordered: MainMenuButtonKey[] = []
  if (Array.isArray(raw)) {
    raw.forEach((candidate) => {
      if (
        typeof candidate === 'string'
        && mainMenuButtonKeys.includes(candidate as MainMenuButtonKey)
        && !ordered.includes(candidate as MainMenuButtonKey)
      ) {
        ordered.push(candidate as MainMenuButtonKey)
      }
    })
  }
  mainMenuButtonKeys.forEach((key) => {
    if (!ordered.includes(key)) ordered.push(key)
  })
  return ordered
}
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
const aiVideoResolutionOptions: readonly AiVideoResolutionKey[] = [
  'preview',
  'small',
  'standard',
  'hd',
]
const durationOptions: DurationKey[] = ['5s', '8s', '10s']
const aiVideoDurationOptions: AiVideoDurationKey[] = [5, 10, 15]
const demoSlots: DemoMediaSlot[] = ['input', 'output']

const videoEngineLabels: Record<VideoSceneEngine, string> = {
  image_to_video: '图生视频',
  wan22_video_v2: '图生视频v2',
}

const videoAspectRatioLabels: Record<VideoAspectRatio, string> = {
  source: '跟随原图',
  '9:16': '9:16（竖屏）',
  '16:9': '16:9（横屏）',
  '1:1': '1:1（方形）',
}

const aiVideoEngineLabels: Record<AiVideoSceneEngine, string> = {
  minimax_h3: '高级图生视频pro',
}

const drawEngineLabels: Record<DrawSceneEngine, string> = {
  free_edit: '自由P图',
  free_edit_v2: '自由P图v2',
  free_edit_v3: '自由P图v3',
  free_edit_v2_5: '自由P图v2.5',
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
    key: 'ai_video_menu',
    label: 'AI视频：主菜单点击后的文案',
    defaultText: '🎞️ **AI视频**\n请选择视频场景：',
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
  {
    key: 'ai_video_scene_start',
    label: 'AI视频：二级场景点击后的文案',
    defaultText: '🎞️ **已切换到【{butten}】模式**。\n\n请发送一张【正面清晰图片】，我将按固定场景参数生成视频。\n\n随时可以发送 /cancel 退出流程。',
    sceneButton: true,
  },
]

const uploadingDemoKeys = ref<ReadonlySet<string>>(new Set())
const uploadingReferenceKeys = ref<ReadonlySet<string>>(new Set())
const generatingDemoKeys = ref<ReadonlySet<string>>(new Set())
const configKey = ref('')
const updatedAt = ref<string | null>(null)
const config = reactive<QqccBotConfig>(emptyConfig())
const mainMenuLayoutMode = computed({
  get: () => config.main_menu_layout.buttons_per_row?.toString() ?? 'legacy',
  set: (value: string) => {
    const parsed = Number(value)
    config.main_menu_layout.buttons_per_row = ([1, 2, 3, 4] as number[]).includes(parsed)
      ? parsed as MainMenuButtonsPerRow
      : null
  },
})
const orderedMainButtonOptions = computed(() =>
  config.main_menu_layout.button_order
    .map((key) => mainButtonOptionsByKey[key])
    .filter((item): item is { key: MainMenuButtonKey; label: string } => Boolean(item)),
)
const modelOptions = reactive<QqccBotConfigOptions>(emptyOptions())
const scenePageSize = 5
const activeSceneTab = ref<SceneConfigKind>('video_v1')
const scenePages = reactive<Record<SceneConfigKind, number>>({
  video: 1,
  video_v1: 1,
  ai_video: 1,
  draw: 1,
  draw_v1: 1,
  filter: 1,
})
const sceneCounter = ref(0)
const aiVideoSceneCounter = ref(0)
const drawSceneCounter = ref(0)
const filterSceneCounter = ref(0)
const sceneConfig = reactive({
  open: false,
  kind: 'video' as SceneConfigKind,
  index: -1,
  credit_cost: null as number | null,
  duration: '5s' as DurationKey | AiVideoDurationKey,
  resolution: '720p' as ResolutionKey | AiVideoResolutionKey,
  engine: 'image_to_video',
  main_model: '10eros' as AiVideoMainModel,
  mode: 'i2v' as AiVideoMode,
  aspect_ratio: 'source' as VideoAspectRatio,
  lora_name: '',
  video_lora_items: [] as VideoLoraItem[],
  lora_items: [] as AiVideoLoraItem[],
  end_frame_draw_scene_id: '',
  jump_draw_scene_id: '',
  next_scene_id: '',
  postprocess_draw_scene_id: '',
  postprocess_filter_scene_id: '',
  original_face_swap_enabled: false,
})
const loraHelp = ref<Wan22LoraHelpModel | null>(null)
const loraHelpLabel = ref('')
const demoVideoPreview = reactive({
  open: false,
  url: '',
  title: '',
})

const openDemoVideoPreview = (
  sceneName: string,
  slot: DemoMediaSlot,
  previewUrl: string,
) => {
  if (!previewUrl) return
  demoVideoPreview.url = previewUrl
  demoVideoPreview.title = `${sceneName || '未命名场景'} · ${slot === 'input' ? '输入示范' : '输出示范'}`
  demoVideoPreview.open = true
}

const closeDemoVideoPreview = () => {
  demoVideoPreview.open = false
  demoVideoPreview.url = ''
  demoVideoPreview.title = ''
}

const loraStrengthSourceLabels: Record<string, string> = {
  archive_general_guidance: '归档页通用建议',
  local_conservative_start: '本地保守起点',
  publisher: '发布者建议',
  publisher_context: '发布者上下文建议',
  publisher_general_guidance: '发布者通用建议',
}

const formatLoraStrengthStage = (stage: Wan22LoraStrengthStage) =>
  `${stage.min.toFixed(2)}–${stage.max.toFixed(2)} / 推荐 ${stage.recommended.toFixed(2)}`

const openLoraHelp = (modelKey: string) => {
  const help = getWan22LoraHelp(modelKey)
  if (!help) return
  loraHelp.value = help
  loraHelpLabel.value = activeLoraOptions.value.find(option => option.value === modelKey)?.label || modelKey
}

const closeLoraHelp = () => {
  loraHelp.value = null
  loraHelpLabel.value = ''
}

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
const paginatedVideoV1Scenes = computed(() =>
  paginateScenes(config.video_scenes_v1, scenePages.video_v1),
)
const paginatedAiVideoScenes = computed(() =>
  paginateScenes(config.ai_video_scenes, scenePages.ai_video),
)
const paginatedDrawScenes = computed(() =>
  paginateScenes(config.draw_scenes, scenePages.draw),
)
const paginatedDrawV1Scenes = computed(() =>
  paginateScenes(config.draw_scenes_v1, scenePages.draw_v1),
)
const paginatedFilterScenes = computed(() =>
  paginateScenes(config.filter_scenes, scenePages.filter),
)

const getSceneCount = (kind: SceneConfigKind) => {
  if (kind === 'video') return config.video_scenes.length
  if (kind === 'video_v1') return config.video_scenes_v1.length
  if (kind === 'ai_video') return config.ai_video_scenes.length
  if (kind === 'draw') return config.draw_scenes.length
  if (kind === 'draw_v1') return config.draw_scenes_v1.length
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

const normalizeVideoAspectRatio = (value: unknown): VideoAspectRatio =>
  value === '9:16' || value === '16:9' || value === '1:1' ? value : 'source'

const normalizeAiVideoEngine = (_value: unknown): AiVideoSceneEngine => 'minimax_h3'
const normalizeAiVideoMainModel = (value: unknown): AiVideoMainModel =>
  value === 'official' || value === 'official_ref2v_turbo' ? value : '10eros'
const normalizeAiVideoMode = (value: unknown): AiVideoMode => value === 'ref2v' ? 'ref2v' : 'i2v'
const normalizeAiVideoAspectRatio = (value: unknown): AiVideoAspectRatio =>
  value === '9:16' || value === '1:1' ? value : '16:9'
const normalizeReferenceImages = (value: unknown) =>
  Array.isArray(value)
    ? value.filter((item): item is string =>
        typeof item === 'string' && item.startsWith('qqcc/config/ref2v/ai_video/'),
      ).slice(0, 4)
    : []
const normalizeReferenceNames = (value: unknown, count: number) =>
  Array.from({ length: count }, (_, index) => {
    const candidate = Array.isArray(value) ? value[index] : undefined
    return typeof candidate === 'string' && candidate.trim()
      ? candidate.trim().slice(0, 64)
      : `模板 ${index + 1}`
  })
const normalizeReferenceFileIds = (value: unknown, count: number) =>
  Array.from({ length: count }, (_, index) => {
    const candidate = Array.isArray(value) ? value[index] : undefined
    if (!candidate || typeof candidate !== 'object') return {}
    return Object.fromEntries(
      Object.entries(candidate as Record<string, unknown>)
        .filter(([botId, fileId]) => /^\d+$/.test(botId) && typeof fileId === 'string' && fileId.trim())
        .slice(0, 4)
        .map(([botId, fileId]) => [botId, String(fileId).trim().slice(0, 512)]),
    )
  })

const normalizeDrawEngine = (value: unknown): DrawSceneEngine =>
  value === 'free_edit' || value === 'free_edit_v2_5' || value === 'free_edit_v3' ? value : 'free_edit_v2'

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
  const expectedMediaType = (kind === 'video' || kind === 'video_v1' || kind === 'ai_video') && slot === 'output' ? 'video' : 'image'
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
  const engines = kind === 'video' || kind === 'video_v1'
    ? modelOptions.video_engines
    : kind === 'ai_video'
      ? modelOptions.ai_video_engines
      : modelOptions.draw_engines
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
  const loras = kind === 'video' || kind === 'video_v1' ? modelOptions.video_lora_models : modelOptions.image_lora_models
  return loras.some((item) => item.value === loraName) ? loraName : ''
}

const normalizeLoraStrength = (raw: unknown, fallback = 1) => {
  const numeric = typeof raw === 'number' ? raw : Number(raw)
  const safe = Number.isFinite(numeric) ? numeric : fallback
  return Math.round(Math.min(2, Math.max(0.1, safe)) * 20) / 20
}

const normalizeAiVideoLoraItems = (
  raw: unknown,
  mode: AiVideoMode = 'i2v',
): AiVideoLoraItem[] => {
  if (!Array.isArray(raw)) return []
  const allowed = new Map(modelOptions.ai_video_addon_models.map(item => [item.value, item]))
  const seen = new Set<string>()
  const normalized: AiVideoLoraItem[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const candidate = item as { name?: unknown; path?: unknown; strength?: unknown }
    const rawName = candidate.name ?? candidate.path
    const name = typeof rawName === 'string' ? rawName.trim() : ''
    const option = allowed.get(name)
    if (
      !option
      || seen.has(name)
      || (option.supported_modes && !option.supported_modes.includes(mode))
    ) continue
    seen.add(name)
    normalized.push({
      name,
      strength: normalizeLoraStrength(candidate.strength, option.default_strength ?? 1),
    })
    if (normalized.length >= 13) break
  }
  return normalized
}

const normalizeVideoLoraItems = (
  raw: unknown,
  legacyName: unknown = '',
  legacyStrength: unknown = undefined,
): VideoLoraItem[] => {
  const source = Array.isArray(raw) && raw.length > 0
    ? raw
    : typeof legacyName === 'string' && legacyName.trim()
      ? [{ name: legacyName, strength: legacyStrength }]
      : []
  const allowed = new Map(modelOptions.video_lora_models.map(item => [item.value, item]))
  const seen = new Set<string>()
  const normalized: VideoLoraItem[] = []
  for (const item of source) {
    if (!item || typeof item !== 'object') continue
    const candidate = item as { name?: unknown; path?: unknown; strength?: unknown }
    const nameValue = candidate.name ?? candidate.path
    const name = typeof nameValue === 'string' ? nameValue.trim() : ''
    const option = allowed.get(name)
    if (!option || seen.has(name)) continue
    seen.add(name)
    normalized.push({
      name,
      strength: normalizeLoraStrength(candidate.strength, option.default_strength ?? 1),
    })
    if (normalized.length >= 5) break
  }
  return normalized
}

const updateVideoLoraSelection = (names: string[]) => {
  const current = new Map(
    sceneConfig.video_lora_items.map(item => [item.name, item.strength]),
  )
  sceneConfig.video_lora_items = names.slice(0, 5).map(name => {
    const option = modelOptions.video_lora_models.find(item => item.value === name)
    return {
      name,
      strength: normalizeLoraStrength(current.get(name), option?.default_strength ?? 1),
    }
  })
}

const updateAiVideoLoraSelection = (names: string[]) => {
  const current = new Map(sceneConfig.lora_items.map(item => [item.name, item.strength]))
  sceneConfig.lora_items = names.slice(0, 13).map(name => {
    const option = modelOptions.ai_video_addon_models.find(item => item.value === name)
    return {
      name,
      strength: normalizeLoraStrength(current.get(name), option?.default_strength ?? 1),
    }
  })
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
  merged.default_ai_video_engine = normalizeAiVideoEngine(raw.default_ai_video_engine)
  merged.default_ai_video_main_model = normalizeAiVideoMainModel(raw.default_ai_video_main_model)
  merged.default_draw_engine = normalizeDrawEngine(raw.default_draw_engine)
  if (resolutionOptions.includes(raw.default_video_resolution as ResolutionKey)) {
    merged.default_video_resolution = raw.default_video_resolution as ResolutionKey
  }
  if (aiVideoResolutionOptions.includes(raw.default_ai_video_resolution as AiVideoResolutionKey)) {
    merged.default_ai_video_resolution = raw.default_ai_video_resolution as AiVideoResolutionKey
  }
  if (Array.isArray(raw.video_resolutions)) {
    merged.video_resolutions = raw.video_resolutions.filter(
      (item): item is ResolutionOption<ResolutionKey> =>
        resolutionOptions.includes(item?.value as ResolutionKey)
        && typeof item?.label === 'string',
    )
  }
  if (Array.isArray(raw.ai_video_resolutions)) {
    merged.ai_video_resolutions = raw.ai_video_resolutions.filter(
      (item): item is ResolutionOption<AiVideoResolutionKey> =>
        aiVideoResolutionOptions.includes(item?.value as AiVideoResolutionKey)
        && typeof item?.label === 'string',
    )
  }
  if (Array.isArray(raw.ai_video_main_models)) {
    const mainModels = raw.ai_video_main_models.filter(
      (item): item is AiVideoMainModelOption =>
        (item?.value === '10eros'
          || item?.value === 'official'
          || item?.value === 'official_ref2v_turbo')
        && typeof item?.label === 'string',
    )
    if (mainModels.length > 0) merged.ai_video_main_models = mainModels
  }
  const rawCreditCosts = raw.default_scene_credit_costs
  if (rawCreditCosts && typeof rawCreditCosts === 'object') {
    ;(['video', 'ai_video', 'draw', 'filter'] as SceneConfigKind[]).forEach((kind) => {
      const value = rawCreditCosts[kind]
      if (typeof value === 'number' && Number.isInteger(value) && value >= 1) {
        merged.default_scene_credit_costs[kind] = value
      }
    })
  }
  const rawAiVideoCreditCosts = raw.ai_video_credit_costs
  if (rawAiVideoCreditCosts && typeof rawAiVideoCreditCosts === 'object') {
    ;(['i2v', 'ref2v'] as AiVideoMode[]).forEach((mode) => {
      const rawDurations = rawAiVideoCreditCosts[mode]
      if (!rawDurations || typeof rawDurations !== 'object') return
      ;([5, 10, 15] as AiVideoDurationKey[]).forEach((duration) => {
        const rawPresets = rawDurations[duration]
        if (!rawPresets || typeof rawPresets !== 'object') return
        aiVideoResolutionOptions.forEach((preset) => {
          const value = rawPresets[preset]
          if (typeof value === 'number' && Number.isInteger(value) && value >= 1) {
            const modeCosts = merged.ai_video_credit_costs[mode] ??= {}
            const durationCosts = modeCosts[duration] ??= {}
            durationCosts[preset] = value
          }
        })
      })
    })
  }
  if (Array.isArray(raw.video_engines) && raw.video_engines.length > 0) {
    merged.video_engines = raw.video_engines
      .filter((item) => typeof item?.value === 'string')
      .map((item) => ({ value: item.value, supports_lora: item.supports_lora === true }))
  }
  if (Array.isArray(raw.video_aspect_ratios) && raw.video_aspect_ratios.length > 0) {
    const ratios = raw.video_aspect_ratios
      .map(normalizeVideoAspectRatio)
      .filter((item, index, values) => values.indexOf(item) === index)
    merged.video_aspect_ratios = ratios.length > 0 ? ratios : merged.video_aspect_ratios
  }
  if (Array.isArray(raw.ai_video_engines) && raw.ai_video_engines.length > 0) {
    merged.ai_video_engines = raw.ai_video_engines
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
      .map((item) => ({
        value: item.value,
        label: typeof item.label === 'string' ? item.label : item.value,
        default_strength: normalizeLoraStrength(item.default_strength, 1),
      }))
  }
  if (Array.isArray(raw.image_lora_models) && raw.image_lora_models.length > 0) {
    merged.image_lora_models = raw.image_lora_models
      .filter((item) => typeof item?.value === 'string')
      .map((item) => ({ value: item.value, label: typeof item.label === 'string' ? item.label : item.value }))
  }
  if (Array.isArray(raw.ai_video_addon_models)) {
    merged.ai_video_addon_models = raw.ai_video_addon_models
      .filter((item) => typeof item?.value === 'string')
      .map((item) => ({
        value: item.value,
        label: typeof item.label === 'string' ? item.label : item.value,
        default_strength: normalizeLoraStrength(item.default_strength, 1),
        supported_modes: Array.isArray(item.supported_modes)
          ? item.supported_modes.filter(
              (mode): mode is AiVideoMode => mode === 'i2v' || mode === 'ref2v',
            )
          : undefined,
      }))
  }
  return merged
}

const isVideoSceneKind = (kind: SceneConfigKind) =>
  kind === 'video' || kind === 'video_v1'

const isDrawSceneKind = (kind: SceneConfigKind) =>
  kind === 'draw' || kind === 'draw_v1'

const getEngineLabel = (kind: SceneConfigKind, engine: string) => {
  if (isVideoSceneKind(kind)) return videoEngineLabels[normalizeVideoEngine(engine)]
  if (kind === 'ai_video') return aiVideoEngineLabels[normalizeAiVideoEngine(engine)]
  return drawEngineLabels[normalizeDrawEngine(engine)]
}

const normalizeSceneCreditCost = (raw: unknown): number | null =>
  typeof raw === 'number' && Number.isInteger(raw) && raw >= 1 ? raw : null

const getSceneSelectPopupContainer = (triggerNode: HTMLElement) =>
  triggerNode.parentElement || document.body

const fixedEngineOption = (options: Array<{ value: string }>, value: string) =>
  options.filter(item => item.value === value).length > 0
    ? options.filter(item => item.value === value)
    : [{ value, label: getEngineLabel(value === 'image_to_video' || value === 'wan22_video_v2' ? 'video' : 'draw', value) }]

const activeEngineOptions = computed(() => {
  if (sceneConfig.kind === 'video_v1') {
    return fixedEngineOption(modelOptions.video_engines, 'image_to_video')
  }
  if (sceneConfig.kind === 'video') {
    return fixedEngineOption(modelOptions.video_engines, 'wan22_video_v2')
  }
  if (sceneConfig.kind === 'ai_video') return modelOptions.ai_video_engines
  if (sceneConfig.kind === 'draw_v1') {
    return fixedEngineOption(modelOptions.draw_engines, 'free_edit')
  }
  if (sceneConfig.kind === 'draw') {
    return fixedEngineOption(modelOptions.draw_engines, 'free_edit_v2_5')
  }
  return modelOptions.draw_engines
})
const activeLoraOptions = computed(() =>
  isVideoSceneKind(sceneConfig.kind)
    ? modelOptions.video_lora_models
    : sceneConfig.kind === 'ai_video'
      ? modelOptions.ai_video_addon_models.filter(
          option => !option.supported_modes || option.supported_modes.includes(sceneConfig.mode),
        )
      : modelOptions.image_lora_models
)
const activeAiVideoMainModelOptions = computed(() =>
  modelOptions.ai_video_main_models.filter(
    option => !option.supported_modes || option.supported_modes.includes(sceneConfig.mode),
  )
)
const activeEngineSupportsLora = computed(() =>
  engineSupportsLora(sceneConfig.kind, sceneConfig.engine)
)
const activeEndFrameDrawOptions = computed(() =>
  (sceneConfig.kind === 'video_v1' ? config.draw_scenes_v1 : config.draw_scenes).filter(
    (scene) => scene.id.trim() && scene.name.trim() && scene.prompt.trim(),
  )
)
const videoScenesForKind = (kind: SceneConfigKind) =>
  kind === 'video'
    ? config.video_scenes
    : kind === 'video_v1'
      ? config.video_scenes_v1
    : kind === 'ai_video'
      ? config.ai_video_scenes
      : []
const wouldCreateVideoSceneCycle = (
  kind: SceneConfigKind,
  sourceSceneId: string,
  candidateSceneId: string,
) => {
  const scenes = videoScenesForKind(kind)
  const byId = new Map(scenes.map(scene => [scene.id, scene]))
  const visited = new Set<string>()
  let current = candidateSceneId
  while (current) {
    if (current === sourceSceneId) return true
    if (visited.has(current)) return true
    visited.add(current)
    current = byId.get(current)?.next_scene_id || ''
  }
  return false
}
const activeNextVideoSceneOptions = computed(() => {
  const scenes = videoScenesForKind(sceneConfig.kind)
  const source = scenes[sceneConfig.index]
  if (!source) return []
  return scenes.filter(scene =>
    scene.id.trim()
    && scene.name.trim()
    && scene.id !== source.id
    && !wouldCreateVideoSceneCycle(sceneConfig.kind, source.id, scene.id),
  )
})
const activeVideoSceneChainPreview = computed(() => {
  const scenes = videoScenesForKind(sceneConfig.kind)
  const source = scenes[sceneConfig.index]
  if (!source) return ''
  const byId = new Map(scenes.map(scene => [scene.id, scene]))
  const names = [source.name || source.id]
  const visited = new Set([source.id])
  let current = sceneConfig.next_scene_id
  while (current && !visited.has(current)) {
    visited.add(current)
    const scene = byId.get(current)
    if (!scene) break
    names.push(scene.name || scene.id)
    current = scene.next_scene_id || ''
  }
  return names.join(' → ')
})
const activePostprocessDrawOptions = computed(() => {
  const drawScenes = sceneConfig.kind === 'draw_v1' ? config.draw_scenes_v1 : config.draw_scenes
  const sourceScene = drawScenes[sceneConfig.index]
  if ((sceneConfig.kind !== 'draw' && sceneConfig.kind !== 'draw_v1') || !sourceScene) return []
  return drawScenes.filter(
    (scene) =>
      scene.id.trim() &&
      scene.name.trim() &&
      scene.prompt.trim() &&
      scene.id !== sourceScene.id &&
      !wouldCreateDrawPostprocessCycle(sourceScene.id, scene.id, drawScenes),
  )
})
const activePostprocessFilterOptions = computed(() =>
  config.filter_scenes.filter(
    (scene) => scene.id.trim() && scene.name.trim() && scene.prompt.trim(),
  )
)
const sceneModalTitle = computed(() => '场景配置')

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
  const rawButtonsPerRow = raw.main_menu_layout?.buttons_per_row
  merged.main_menu_layout.buttons_per_row = (
    typeof rawButtonsPerRow === 'number'
    && Number.isInteger(rawButtonsPerRow)
    && rawButtonsPerRow >= 1
    && rawButtonsPerRow <= 4
  )
    ? rawButtonsPerRow as MainMenuButtonsPerRow
    : null
  merged.main_menu_layout.button_order = normalizeMainMenuButtonOrder(
    raw.main_menu_layout?.button_order,
  )
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
          credit_cost: normalizeSceneCreditCost(scene?.credit_cost),
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
          credit_cost: normalizeSceneCreditCost(scene?.credit_cost),
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
  // Versioned collections use the same validated scene shape.  Keep them in
  // the draft even when the V2 compatibility projection above is displayed.
  if (Array.isArray(raw.draw_scenes_v1)) merged.draw_scenes_v1 = raw.draw_scenes_v1 as DrawSceneConfig[]
  if (Array.isArray(raw.draw_scenes_v2)) merged.draw_scenes_v2 = raw.draw_scenes_v2 as DrawSceneConfig[]
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
        const loraItems = normalizeVideoLoraItems(
          scene?.lora_items,
          scene?.lora_name,
          scene?.lora_strength,
        )
        return {
          id,
          name,
          prompt,
          negative_prompt,
          duration,
          resolution: resolutionOptions.includes(scene?.resolution as ResolutionKey)
            ? scene.resolution as ResolutionKey
            : modelOptions.default_video_resolution,
          engine,
          aspect_ratio: normalizeVideoAspectRatio(scene?.aspect_ratio),
          lora_name: loraItems[0]?.name || '',
          lora_strength: loraItems[0]?.strength ?? 1,
          lora_items: loraItems,
          end_frame_draw_scene_id: normalizeEndFrameDrawSceneId(
            scene?.end_frame_draw_scene_id,
            merged.draw_scenes,
          ),
          jump_draw_scene_id: normalizeEndFrameDrawSceneId(
            scene?.jump_draw_scene_id,
            merged.draw_scenes,
          ),
          next_scene_id: typeof scene?.next_scene_id === 'string' && scene.next_scene_id.trim()
            ? scene.next_scene_id.trim()
            : null,
          credit_cost: normalizeSceneCreditCost(scene?.credit_cost),
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
  if (Array.isArray(raw.video_scenes_v1)) merged.video_scenes_v1 = raw.video_scenes_v1 as VideoSceneConfig[]
  if (Array.isArray(raw.video_scenes_v2)) merged.video_scenes_v2 = raw.video_scenes_v2 as VideoSceneConfig[]
  if (Array.isArray(raw.ai_video_scenes)) {
    merged.ai_video_scenes = raw.ai_video_scenes
      .map((scene, index) => {
        const id = typeof scene?.id === 'string' && scene.id.trim()
          ? scene.id.trim()
          : `ai_video_scene_${index + 1}`
        const rawDuration = Number(scene?.duration)
        const duration = aiVideoDurationOptions.includes(rawDuration as AiVideoDurationKey)
          ? (rawDuration as AiVideoDurationKey)
          : 5
        const referenceImages = normalizeReferenceImages(scene?.reference_images)
        return {
          id,
          name: typeof scene?.name === 'string' ? scene.name : '',
          prompt: typeof scene?.prompt === 'string' ? scene.prompt : '',
          negative_prompt: typeof scene?.negative_prompt === 'string' ? scene.negative_prompt : '',
          duration,
          resolution: aiVideoResolutionOptions.includes(scene?.resolution as AiVideoResolutionKey)
            ? scene.resolution as AiVideoResolutionKey
            : modelOptions.default_ai_video_resolution,
          engine: normalizeAiVideoEngine(scene?.engine),
          main_model: normalizeAiVideoMainModel(scene?.main_model),
          mode: normalizeAiVideoMode(scene?.mode),
          reference_images: referenceImages,
          reference_image_names: normalizeReferenceNames(
            scene?.reference_image_names,
            referenceImages.length,
          ),
          reference_image_telegram_file_ids: normalizeReferenceFileIds(
            scene?.reference_image_telegram_file_ids,
            referenceImages.length,
          ),
          reference_image_previews: Array.isArray(scene?.reference_image_previews)
            ? scene.reference_image_previews.filter((item): item is string => typeof item === 'string')
            : [],
          aspect_ratio: normalizeAiVideoAspectRatio(scene?.aspect_ratio),
          lora_items: normalizeAiVideoLoraItems(
            scene?.lora_items,
            normalizeAiVideoMode(scene?.mode),
          ),
          end_frame_draw_scene_id: normalizeEndFrameDrawSceneId(
            scene?.end_frame_draw_scene_id,
            merged.draw_scenes,
          ),
          jump_draw_scene_id: normalizeEndFrameDrawSceneId(
            scene?.jump_draw_scene_id,
            merged.draw_scenes,
          ),
          next_scene_id: typeof scene?.next_scene_id === 'string' && scene.next_scene_id.trim()
            ? scene.next_scene_id.trim()
            : null,
          credit_cost: normalizeSceneCreditCost(scene?.credit_cost),
          demo_input_media: normalizeDemoMedia(scene?.demo_input_media, {
            kind: 'ai_video', sceneId: id, slot: 'input',
          }),
          demo_output_media: normalizeDemoMedia(scene?.demo_output_media, {
            kind: 'ai_video', sceneId: id, slot: 'output',
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

const defaultSceneCreditCost = (kind: SceneConfigKind) =>
  normalizeSceneCreditCost(modelOptions.default_scene_credit_costs[kind])

const sceneConfigDefaultCreditCost = computed(() => {
  if (sceneConfig.kind !== 'ai_video') return defaultSceneCreditCost(sceneConfig.kind)
  return normalizeSceneCreditCost(
    modelOptions.ai_video_credit_costs[sceneConfig.mode]?.[
      sceneConfig.duration as AiVideoDurationKey
    ]?.[sceneConfig.resolution as AiVideoResolutionKey],
  )
})

const sceneConfigCreditCostPlaceholder = computed(() => (
  sceneConfigDefaultCreditCost.value === null
    ? '未配置/沿用模型价格'
    : `未配置/默认 ${sceneConfigDefaultCreditCost.value} 灵石`
))

const addVideoScene = (kind: 'video' | 'video_v1' = 'video') => {
  const scenes = kind === 'video_v1' ? config.video_scenes_v1 : config.video_scenes
  scenes.push({
    id: createVideoSceneId(),
    name: '',
    prompt: '',
    negative_prompt: '',
    duration: '5s',
    resolution: modelOptions.default_video_resolution,
    engine: kind === 'video_v1' ? 'image_to_video' : 'wan22_video_v2',
    aspect_ratio: 'source',
    lora_name: '',
    lora_strength: 1,
    lora_items: [],
    end_frame_draw_scene_id: '',
    jump_draw_scene_id: '',
    next_scene_id: null,
    credit_cost: defaultSceneCreditCost(kind),
  })
  showScenePageContaining(kind, scenes.length - 1)
}

const createAiVideoSceneId = () => {
  aiVideoSceneCounter.value += 1
  return `ai_video_${Date.now().toString(36)}_${aiVideoSceneCounter.value}`
}

const addAiVideoScene = () => {
  config.ai_video_scenes.push({
    id: createAiVideoSceneId(),
    name: '',
    prompt: '',
    negative_prompt: '',
    duration: 5,
    resolution: modelOptions.default_ai_video_resolution,
    engine: normalizeAiVideoEngine(modelOptions.default_ai_video_engine),
    main_model: normalizeAiVideoMainModel(modelOptions.default_ai_video_main_model),
    mode: 'i2v',
    reference_images: [],
    reference_image_names: [],
    reference_image_telegram_file_ids: [],
    reference_image_previews: [],
    aspect_ratio: '16:9',
    lora_items: [],
    end_frame_draw_scene_id: '',
    jump_draw_scene_id: '',
    next_scene_id: null,
    credit_cost: defaultSceneCreditCost('ai_video'),
  })
  showScenePageContaining('ai_video', config.ai_video_scenes.length - 1)
}

const removeAiVideoScene = (index: number) => {
  const [removed] = config.ai_video_scenes.splice(index, 1)
  if (removed) {
    config.ai_video_scenes.forEach((scene) => {
      if (scene.next_scene_id === removed.id) scene.next_scene_id = null
    })
  }
  normalizeScenePage('ai_video')
}

const removeVideoScene = (index: number) => {
  const [removed] = config.video_scenes.splice(index, 1)
  if (removed) {
    config.video_scenes.forEach((scene) => {
      if (scene.next_scene_id === removed.id) scene.next_scene_id = null
    })
  }
  normalizeScenePage('video')
}

const removeVersionedVideoScene = (kind: 'video' | 'video_v1', index: number) => {
  const scenes = kind === 'video_v1' ? config.video_scenes_v1 : config.video_scenes
  const [removed] = scenes.splice(index, 1)
  if (removed) scenes.forEach(scene => {
    if (scene.next_scene_id === removed.id) scene.next_scene_id = null
  })
  normalizeScenePage(kind)
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

const moveMainMenuButton = (index: number, offset: -1 | 1) => {
  const targetIndex = index + offset
  const order = config.main_menu_layout.button_order
  if (index < 0 || index >= order.length || targetIndex < 0 || targetIndex >= order.length) {
    return
  }
  const [buttonKey] = order.splice(index, 1)
  if (buttonKey) order.splice(targetIndex, 0, buttonKey)
}

const createDrawSceneId = () => {
  drawSceneCounter.value += 1
  return `draw_${Date.now().toString(36)}_${drawSceneCounter.value}`
}

const createFilterSceneId = () => {
  filterSceneCounter.value += 1
  return `filter_${Date.now().toString(36)}_${filterSceneCounter.value}`
}

const addDrawScene = (kind: 'draw' | 'draw_v1' = 'draw') => {
  const scenes = kind === 'draw_v1' ? config.draw_scenes_v1 : config.draw_scenes
  scenes.push({
    id: createDrawSceneId(),
    name: '',
    prompt: '',
    negative_prompt: '',
    engine: kind === 'draw_v1' ? 'free_edit' : 'free_edit_v2_5',
    lora_name: '',
    postprocess_draw_scene_id: '',
    postprocess_filter_scene_id: '',
    original_face_swap_enabled: false,
    credit_cost: defaultSceneCreditCost(kind),
  })
  showScenePageContaining(kind, scenes.length - 1)
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
    credit_cost: defaultSceneCreditCost('filter'),
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
    if (scene.jump_draw_scene_id === removed.id) scene.jump_draw_scene_id = ''
  })
  config.ai_video_scenes.forEach((scene) => {
    if (scene.end_frame_draw_scene_id === removed.id) scene.end_frame_draw_scene_id = ''
    if (scene.jump_draw_scene_id === removed.id) scene.jump_draw_scene_id = ''
  })
  config.draw_scenes.forEach((scene) => {
    if (scene.postprocess_draw_scene_id === removed.id) {
      scene.postprocess_draw_scene_id = ''
    }
  })
  normalizeScenePage('draw')
}

const removeVersionedDrawScene = (kind: 'draw' | 'draw_v1', index: number) => {
  const scenes = kind === 'draw_v1' ? config.draw_scenes_v1 : config.draw_scenes
  const videos = kind === 'draw_v1' ? config.video_scenes_v1 : config.video_scenes
  const [removed] = scenes.splice(index, 1)
  if (!removed) return
  videos.forEach(scene => {
    if (scene.end_frame_draw_scene_id === removed.id) scene.end_frame_draw_scene_id = ''
    if (scene.jump_draw_scene_id === removed.id) scene.jump_draw_scene_id = ''
  })
  scenes.forEach(scene => {
    if (scene.postprocess_draw_scene_id === removed.id) scene.postprocess_draw_scene_id = ''
  })
  normalizeScenePage(kind)
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
  if (kind === 'video_v1') return config.video_scenes_v1[index]
  if (kind === 'ai_video') return config.ai_video_scenes[index]
  if (kind === 'draw') return config.draw_scenes[index]
  if (kind === 'draw_v1') return config.draw_scenes_v1[index]
  return config.filter_scenes[index]
}

const getDemoMediaAccept = (kind: SceneConfigKind, slot: DemoMediaSlot) =>
  (kind === 'video' || kind === 'video_v1' || kind === 'ai_video') && slot === 'output'
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
  const isVideo = (kind === 'video' || kind === 'video_v1' || kind === 'ai_video') && slot === 'output'
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
const isReferenceUploadLoading = (key: string) => uploadingReferenceKeys.value.has(key)

const uploadReferenceImage = async (
  sceneIndex: number,
  referenceIndex: number,
  uploadFile: DemoUploadFile,
) => {
  const scene = config.ai_video_scenes[sceneIndex]
  if (!scene?.id || referenceIndex < 0 || referenceIndex > 3) return false
  const file = uploadFile.originFileObj instanceof File ? uploadFile.originFileObj : uploadFile
  const validationError = validateDemoUploadFile('ai_video', 'input', file)
  if (validationError) {
    message.error(`参考图上传失败：${validationError}`)
    return false
  }
  const uploadKey = `${scene.id}:${referenceIndex}`
  setDemoOperationLoading(uploadingReferenceKeys, uploadKey, true)
  try {
    if (!props.uploadReferenceImage) {
      throw new Error('QQCC REF2V is available only in the official control panel')
    }
    const uploaded = await props.uploadReferenceImage(scene.id, referenceIndex, file)
    const objectKey = String(uploaded?.media?.object_key || '')
    if (!objectKey.startsWith('qqcc/config/ref2v/ai_video/')) {
      throw new Error('QQCC_REF2V_REFERENCE_INVALID_RESPONSE')
    }
    scene.reference_images.splice(referenceIndex, 1, objectKey)
    if (referenceIndex >= scene.reference_image_names.length) {
      scene.reference_image_names.push(`模板 ${referenceIndex + 1}`)
    }
    scene.reference_image_telegram_file_ids.splice(referenceIndex, 1, {})
    const previews = [...(scene.reference_image_previews || [])]
    previews.splice(referenceIndex, 1, uploaded.preview_url)
    scene.reference_image_previews = previews
    message.success(referenceIndex < scene.reference_images.length - 1 ? '参考图已替换' : '参考图已添加')
  } catch (error: unknown) {
    message.error(`参考图上传失败：${resolveDemoUploadError(error)}`)
  } finally {
    setDemoOperationLoading(uploadingReferenceKeys, uploadKey, false)
  }
  return false
}

const removeReferenceImage = (scene: AiVideoSceneConfig, referenceIndex: number) => {
  scene.reference_images.splice(referenceIndex, 1)
  scene.reference_image_names.splice(referenceIndex, 1)
  scene.reference_image_telegram_file_ids.splice(referenceIndex, 1)
  scene.reference_image_previews?.splice(referenceIndex, 1)
}

const moveReferenceImage = (
  scene: AiVideoSceneConfig,
  referenceIndex: number,
  direction: -1 | 1,
) => {
  const target = referenceIndex + direction
  if (target < 0 || target >= scene.reference_images.length) return
  ;[scene.reference_images[referenceIndex], scene.reference_images[target]] =
    [scene.reference_images[target], scene.reference_images[referenceIndex]]
  ;[scene.reference_image_names[referenceIndex], scene.reference_image_names[target]] =
    [scene.reference_image_names[target], scene.reference_image_names[referenceIndex]]
  ;[scene.reference_image_telegram_file_ids[referenceIndex], scene.reference_image_telegram_file_ids[target]] =
    [scene.reference_image_telegram_file_ids[target], scene.reference_image_telegram_file_ids[referenceIndex]]
  if (scene.reference_image_previews) {
    ;[scene.reference_image_previews[referenceIndex], scene.reference_image_previews[target]] =
      [scene.reference_image_previews[target], scene.reference_image_previews[referenceIndex]]
  }
}

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
    const generated = submitted.status === 'done' && submitted.config_saved === true
      ? submitted
      : await waitForDemoGeneration(kind, scene.id, submitted.generation_id)
    if (!generated?.media || generated.config_saved !== true) {
      throw new Error('QQCC_DEMO_GENERATION_INVALID_RESPONSE')
    }
    scene.demo_output_media = { ...generated.media, preview_url: generated.preview_url }
    message.success('输出示范已生成并自动保存')
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

const validateAiVideoScenes = () =>
  config.ai_video_scenes.every((scene) =>
    Boolean(scene.name.trim())
    && Boolean(scene.prompt.trim())
    && (scene.mode !== 'ref2v' || scene.reference_images.length >= 1),
  )

const validateDrawScenes = () =>
  config.draw_scenes.every(
    (scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()),
  )

const validateFilterScenes = () =>
  config.filter_scenes.every(
    (scene) => Boolean(scene.name.trim()) && Boolean(scene.prompt.trim()),
  )

const validateSceneCreditCosts = () =>
  [
    ...config.video_scenes,
    ...config.video_scenes_v1,
    ...config.ai_video_scenes,
    ...config.draw_scenes,
    ...config.draw_scenes_v1,
    ...config.filter_scenes,
  ].every(
    scene => ('mode' in scene && scene.mode === 'ref2v')
      || scene.credit_cost === null
      || (Number.isInteger(scene.credit_cost) && scene.credit_cost >= 1),
  )

const buildPayload = (): QqccBotConfig => {
  const payload = JSON.parse(JSON.stringify(config)) as QqccBotConfig
  payload.scene_preset_version = config.scene_preset_version || modelOptions.scene_preset_version
  payload.main_menu_layout.button_order = normalizeMainMenuButtonOrder(
    payload.main_menu_layout.button_order,
  )
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
  payload.draw_scenes_v1 = payload.draw_scenes_v1
    .map((scene) => ({
      ...scene,
      id: scene.id.trim(), name: scene.name.trim(), prompt: scene.prompt.trim(),
      negative_prompt: scene.negative_prompt.trim(), engine: 'free_edit' as DrawSceneEngine,
      lora_name: normalizeLoraName(scene.lora_name, { kind: 'draw_v1', engine: 'free_edit' }),
      postprocess_draw_scene_id: typeof scene.postprocess_draw_scene_id === 'string' ? scene.postprocess_draw_scene_id.trim() : '',
      postprocess_filter_scene_id: typeof scene.postprocess_filter_scene_id === 'string' ? scene.postprocess_filter_scene_id.trim() : '',
      original_face_swap_enabled: scene.original_face_swap_enabled === true,
    }))
    .filter(scene => scene.name || scene.prompt)
  normalizeDrawPostprocessRefs(payload.draw_scenes_v1, payload.filter_scenes)
  payload.video_scenes = payload.video_scenes
    .map((scene) => {
      const { jump_draw_scene_id: rawJumpDrawSceneId, ...videoScene } = scene
      const engine = normalizeVideoEngine(scene.engine)
      const loraItems = normalizeVideoLoraItems(
        scene.lora_items,
        scene.lora_name,
        scene.lora_strength,
      )
      return {
        ...videoScene,
        id: scene.id.trim(),
        name: scene.name.trim(),
        prompt: scene.prompt.trim(),
        negative_prompt: scene.negative_prompt.trim(),
        engine,
        aspect_ratio: normalizeVideoAspectRatio(scene.aspect_ratio),
        lora_name: loraItems[0]?.name || '',
        lora_strength: loraItems[0]?.strength ?? 1,
        lora_items: loraItems,
        end_frame_draw_scene_id: normalizeEndFrameDrawSceneId(
          scene.end_frame_draw_scene_id,
          payload.draw_scenes,
        ),
        ...(normalizeEndFrameDrawSceneId(rawJumpDrawSceneId, payload.draw_scenes)
          ? { jump_draw_scene_id: normalizeEndFrameDrawSceneId(rawJumpDrawSceneId, payload.draw_scenes) }
          : {}),
        next_scene_id: typeof scene.next_scene_id === 'string' && scene.next_scene_id.trim()
          ? scene.next_scene_id.trim()
          : null,
      }
    })
    .filter((scene) => scene.name || scene.prompt)
  payload.video_scenes_v1 = payload.video_scenes_v1
    .map((scene) => {
      const { jump_draw_scene_id: rawJumpDrawSceneId, ...videoScene } = scene
      const loraItems = normalizeVideoLoraItems(scene.lora_items, scene.lora_name, scene.lora_strength)
      return {
        ...videoScene, id: scene.id.trim(), name: scene.name.trim(), prompt: scene.prompt.trim(),
        negative_prompt: scene.negative_prompt.trim(), engine: 'image_to_video' as VideoSceneEngine,
        aspect_ratio: normalizeVideoAspectRatio(scene.aspect_ratio), lora_name: loraItems[0]?.name || '',
        lora_strength: loraItems[0]?.strength ?? 1, lora_items: loraItems,
        end_frame_draw_scene_id: normalizeEndFrameDrawSceneId(scene.end_frame_draw_scene_id, payload.draw_scenes_v1),
        ...(normalizeEndFrameDrawSceneId(rawJumpDrawSceneId, payload.draw_scenes_v1)
          ? { jump_draw_scene_id: normalizeEndFrameDrawSceneId(rawJumpDrawSceneId, payload.draw_scenes_v1) } : {}),
        next_scene_id: typeof scene.next_scene_id === 'string' && scene.next_scene_id.trim() ? scene.next_scene_id.trim() : null,
      }
    })
    .filter(scene => scene.name || scene.prompt)
  payload.ai_video_scenes = payload.ai_video_scenes
    .map((scene) => {
      const {
        jump_draw_scene_id: rawJumpDrawSceneId,
        reference_image_previews: _referenceImagePreviews,
        ...aiVideoScene
      } = scene
      return {
      ...aiVideoScene,
      id: scene.id.trim(),
      name: scene.name.trim(),
      prompt: scene.prompt.trim(),
      negative_prompt: scene.negative_prompt.trim(),
      engine: normalizeAiVideoEngine(scene.engine),
      main_model: normalizeAiVideoMainModel(scene.main_model),
      mode: normalizeAiVideoMode(scene.mode),
      reference_images: normalizeReferenceImages(scene.reference_images),
      reference_image_names: normalizeReferenceNames(
        scene.reference_image_names,
        scene.reference_images.length,
      ),
      reference_image_telegram_file_ids: normalizeReferenceFileIds(
        scene.reference_image_telegram_file_ids,
        scene.reference_images.length,
      ),
      aspect_ratio: normalizeAiVideoAspectRatio(scene.aspect_ratio),
      duration: aiVideoDurationOptions.includes(scene.duration) ? scene.duration : 5,
      lora_items: normalizeAiVideoLoraItems(scene.lora_items, normalizeAiVideoMode(scene.mode)),
      end_frame_draw_scene_id: scene.mode === 'ref2v' ? '' : normalizeEndFrameDrawSceneId(
          scene.end_frame_draw_scene_id,
          payload.draw_scenes,
        ),
      ...(normalizeEndFrameDrawSceneId(rawJumpDrawSceneId, payload.draw_scenes)
        ? { jump_draw_scene_id: normalizeEndFrameDrawSceneId(rawJumpDrawSceneId, payload.draw_scenes) }
        : {}),
      next_scene_id: scene.mode !== 'ref2v' && typeof scene.next_scene_id === 'string' && scene.next_scene_id.trim()
        ? scene.next_scene_id.trim()
        : null,
      }
    })
    .filter((scene) => scene.name || scene.prompt)
  return payload
}

const applyResponse = (payload: QqccBotConfigResponse) => {
  Object.assign(modelOptions, mergeOptions(payload.options))
  Object.assign(config, mergeConfig(payload.config))
  normalizeScenePage('video')
  normalizeScenePage('video_v1')
  normalizeScenePage('ai_video')
  normalizeScenePage('draw')
  normalizeScenePage('draw_v1')
  normalizeScenePage('filter')
  configKey.value = payload.key || ''
  updatedAt.value = payload.updated_at || null
}

const openSceneConfig = (
  kind: SceneConfigKind,
  index: number,
) => {
  const scene =
    kind === 'video'
      ? config.video_scenes[index]
      : kind === 'video_v1'
        ? config.video_scenes_v1[index]
      : kind === 'ai_video'
        ? config.ai_video_scenes[index]
      : kind === 'filter'
        ? config.filter_scenes[index]
        : kind === 'draw_v1'
          ? config.draw_scenes_v1[index]
          : config.draw_scenes[index]
  if (!scene) return
  sceneConfig.kind = kind
  sceneConfig.index = index
  sceneConfig.credit_cost = normalizeSceneCreditCost(scene.credit_cost)
  sceneConfig.duration = kind === 'video' || kind === 'video_v1' || kind === 'ai_video'
    ? (scene as VideoSceneConfig | AiVideoSceneConfig).duration
    : '5s'
  sceneConfig.resolution = kind === 'video' || kind === 'video_v1'
    ? (scene as VideoSceneConfig).resolution
    : kind === 'ai_video'
      ? (scene as AiVideoSceneConfig).resolution
      : modelOptions.default_video_resolution
  sceneConfig.engine = scene.engine
  sceneConfig.main_model = kind === 'ai_video'
    ? normalizeAiVideoMainModel((scene as AiVideoSceneConfig).main_model)
    : modelOptions.default_ai_video_main_model
  sceneConfig.mode = kind === 'ai_video'
    ? normalizeAiVideoMode((scene as AiVideoSceneConfig).mode)
    : 'i2v'
  sceneConfig.aspect_ratio = kind === 'video' || kind === 'video_v1'
    ? normalizeVideoAspectRatio((scene as VideoSceneConfig).aspect_ratio)
    : kind === 'ai_video'
      ? normalizeAiVideoAspectRatio((scene as AiVideoSceneConfig).aspect_ratio)
      : 'source'
  sceneConfig.lora_name = 'lora_name' in scene ? scene.lora_name || '' : ''
  sceneConfig.video_lora_items = kind === 'video' || kind === 'video_v1'
    ? normalizeVideoLoraItems(
        (scene as VideoSceneConfig).lora_items,
        (scene as VideoSceneConfig).lora_name,
        (scene as VideoSceneConfig).lora_strength,
      )
    : []
  sceneConfig.lora_items = kind === 'ai_video'
    ? normalizeAiVideoLoraItems(
        (scene as AiVideoSceneConfig).lora_items,
        normalizeAiVideoMode((scene as AiVideoSceneConfig).mode),
      )
    : []
  sceneConfig.end_frame_draw_scene_id =
    kind === 'video' || kind === 'video_v1' || kind === 'ai_video'
      ? normalizeEndFrameDrawSceneId((scene as VideoSceneConfig | AiVideoSceneConfig).end_frame_draw_scene_id)
      : ''
  sceneConfig.jump_draw_scene_id =
    kind === 'video' || kind === 'video_v1' || kind === 'ai_video'
      ? normalizeEndFrameDrawSceneId((scene as VideoSceneConfig | AiVideoSceneConfig).jump_draw_scene_id)
      : ''
  sceneConfig.next_scene_id =
    kind === 'video' || kind === 'video_v1' || kind === 'ai_video'
      ? (scene as VideoSceneConfig | AiVideoSceneConfig).next_scene_id || ''
      : ''
  sceneConfig.postprocess_draw_scene_id =
    kind === 'draw' || kind === 'draw_v1'
      ? normalizePostprocessDrawSceneId((scene as DrawSceneConfig).postprocess_draw_scene_id, index)
      : ''
  sceneConfig.postprocess_filter_scene_id =
    kind === 'draw' || kind === 'draw_v1'
      ? normalizePostprocessFilterSceneId((scene as DrawSceneConfig).postprocess_filter_scene_id)
      : ''
  sceneConfig.original_face_swap_enabled =
    isDrawSceneKind(kind) || kind === 'filter'
      ? (scene as DrawSceneConfig | FilterSceneConfig).original_face_swap_enabled === true
      : false
  sceneConfig.open = true
}

const closeSceneConfig = () => {
  sceneConfig.open = false
  sceneConfig.index = -1
  sceneConfig.credit_cost = null
  sceneConfig.duration = '5s'
  sceneConfig.resolution = modelOptions.default_video_resolution
  sceneConfig.lora_items = []
  sceneConfig.main_model = modelOptions.default_ai_video_main_model
  sceneConfig.mode = 'i2v'
  sceneConfig.video_lora_items = []
  sceneConfig.aspect_ratio = 'source'
  sceneConfig.end_frame_draw_scene_id = ''
  sceneConfig.jump_draw_scene_id = ''
  sceneConfig.next_scene_id = ''
  sceneConfig.postprocess_draw_scene_id = ''
  sceneConfig.postprocess_filter_scene_id = ''
  sceneConfig.original_face_swap_enabled = false
}

const onSceneEngineChange = () => {
  if (sceneConfig.kind !== 'video' && sceneConfig.kind !== 'video_v1' && !activeEngineSupportsLora.value) {
    sceneConfig.lora_name = ''
    sceneConfig.lora_items = []
  }
}

const onAiVideoModeChange = () => {
  if (!activeAiVideoMainModelOptions.value.some(
    option => option.value === sceneConfig.main_model,
  )) {
    sceneConfig.main_model = modelOptions.default_ai_video_main_model
  }
}

const confirmSceneConfig = () => {
  if (sceneConfig.index < 0) return
  if (sceneConfig.kind === 'video' || sceneConfig.kind === 'video_v1') {
    const scene = (sceneConfig.kind === 'video_v1' ? config.video_scenes_v1 : config.video_scenes)[sceneConfig.index]
    if (!scene) return
    if (sceneConfig.resolution === '1024p' && sceneConfig.duration === '10s') {
      message.error('AI动图不支持 1024p + 10s，请调整分辨率或时长')
      return
    }
    const engine = sceneConfig.kind === 'video_v1' ? 'image_to_video' : 'wan22_video_v2'
    scene.credit_cost = normalizeSceneCreditCost(sceneConfig.credit_cost)
    scene.duration = sceneConfig.duration as DurationKey
    scene.resolution = sceneConfig.resolution as ResolutionKey
    scene.engine = engine
    scene.aspect_ratio = normalizeVideoAspectRatio(sceneConfig.aspect_ratio)
    scene.lora_items = normalizeVideoLoraItems(sceneConfig.video_lora_items)
    scene.lora_name = scene.lora_items[0]?.name || ''
    scene.lora_strength = scene.lora_items[0]?.strength ?? 1
    scene.end_frame_draw_scene_id = normalizeEndFrameDrawSceneId(
      sceneConfig.end_frame_draw_scene_id,
    )
    scene.jump_draw_scene_id = normalizeEndFrameDrawSceneId(sceneConfig.jump_draw_scene_id)
    scene.next_scene_id = sceneConfig.next_scene_id || null
  } else if (sceneConfig.kind === 'ai_video') {
    const scene = config.ai_video_scenes[sceneConfig.index]
    if (!scene) return
    scene.mode = normalizeAiVideoMode(sceneConfig.mode)
    scene.aspect_ratio = normalizeAiVideoAspectRatio(sceneConfig.aspect_ratio)
    scene.duration = sceneConfig.duration as AiVideoDurationKey
    scene.resolution = sceneConfig.resolution as AiVideoResolutionKey
    scene.credit_cost = normalizeSceneCreditCost(sceneConfig.credit_cost)
    scene.engine = normalizeAiVideoEngine(sceneConfig.engine)
    scene.main_model = normalizeAiVideoMainModel(sceneConfig.main_model)
    scene.lora_items = normalizeAiVideoLoraItems(sceneConfig.lora_items, scene.mode)
    scene.end_frame_draw_scene_id = scene.mode === 'ref2v' ? '' : normalizeEndFrameDrawSceneId(
        sceneConfig.end_frame_draw_scene_id,
      )
    scene.jump_draw_scene_id = scene.mode === 'ref2v' ? '' : normalizeEndFrameDrawSceneId(sceneConfig.jump_draw_scene_id)
    scene.next_scene_id = scene.mode === 'ref2v' ? null : sceneConfig.next_scene_id || null
  } else if (sceneConfig.kind === 'draw' || sceneConfig.kind === 'draw_v1') {
    const scene = (sceneConfig.kind === 'draw_v1' ? config.draw_scenes_v1 : config.draw_scenes)[sceneConfig.index]
    if (!scene) return
    const engine = sceneConfig.kind === 'draw_v1' ? 'free_edit' : 'free_edit_v2_5'
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
    scene.credit_cost = normalizeSceneCreditCost(sceneConfig.credit_cost)
    scene.engine = engine
    scene.lora_name = normalizeLoraName(sceneConfig.lora_name, { kind: 'draw', engine })
    scene.postprocess_draw_scene_id = postprocessDrawSceneId
    scene.postprocess_filter_scene_id = postprocessDrawSceneId
      ? ''
      : normalizePostprocessFilterSceneId(sceneConfig.postprocess_filter_scene_id)
    scene.original_face_swap_enabled = sceneConfig.original_face_swap_enabled === true
  } else {
    const scene = config.filter_scenes[sceneConfig.index]
    if (!scene) return
    const engine = normalizeDrawEngine(sceneConfig.engine)
    scene.credit_cost = normalizeSceneCreditCost(sceneConfig.credit_cost)
    scene.engine = engine
    scene.lora_name = normalizeLoraName(sceneConfig.lora_name, { kind: 'filter', engine })
    scene.original_face_swap_enabled = sceneConfig.original_face_swap_enabled === true
  }
  closeSceneConfig()
}

const { loading, saving, loadConfig, saveConfig } = useQqccConfigPersistence({
  fetchConfig: props.fetchConfig,
  updateConfig: props.updateConfig,
  applyResponse,
  buildPayload,
  validate: () => {
    if (!validateVideoScenes()) return '请完善AI动图场景的按钮名称和提示词'
    if (!validateAiVideoScenes()) return '请完善AI视频场景的按钮名称和提示词'
    if (!validateDrawScenes()) return '请完善AI绘图场景的按钮名称和提示词'
    if (!validateFilterScenes()) return '请完善AI滤镜场景的按钮名称和提示词'
    if (!validateSceneCreditCosts()) return '灵石消耗必须留空或填写大于等于 1 的整数'
    if (hasDrawPostprocessCycle(config.draw_scenes)) return 'AI绘图后处理配置不能形成循环'
    return null
  },
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
              <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 class="text-sm font-semibold text-slate-800">主菜单</h3>
                  <p class="mt-1 text-xs text-slate-500">可调整所有按钮的显示顺序；沿用现有布局时保持当前每行按钮数量。</p>
                </div>
                <a-select
                  v-model:value="mainMenuLayoutMode"
                  class="w-48"
                  data-testid="main-menu-buttons-per-row"
                >
                  <a-select-option value="legacy">沿用现有布局</a-select-option>
                  <a-select-option value="1">每行 1 个按钮</a-select-option>
                  <a-select-option value="2">每行 2 个按钮</a-select-option>
                  <a-select-option value="3">每行 3 个按钮</a-select-option>
                  <a-select-option value="4">每行 4 个按钮</a-select-option>
                </a-select>
              </div>
              <div class="space-y-2">
                <div
                  v-for="(item, index) in orderedMainButtonOptions"
                  :key="item.key"
                  class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2"
                >
                  <div class="flex min-w-0 items-center gap-2">
                    <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-500">
                      {{ index + 1 }}
                    </span>
                    <span class="truncate text-sm text-slate-700">{{ item.label }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <a-switch
                      v-model:checked="config.main_buttons[item.key]"
                      :data-testid="`main-button-${item.key}`"
                    />
                    <a-button
                      size="small"
                      :disabled="index === 0"
                      :data-testid="`move-main-menu-button-up-${item.key}`"
                      :title="`上移${item.label}`"
                      :aria-label="`上移${item.label}`"
                      @click="moveMainMenuButton(index, -1)"
                    >
                      <template #icon><UpOutlined /></template>
                    </a-button>
                    <a-button
                      size="small"
                      :disabled="index === orderedMainButtonOptions.length - 1"
                      :data-testid="`move-main-menu-button-down-${item.key}`"
                      :title="`下移${item.label}`"
                      :aria-label="`下移${item.label}`"
                      @click="moveMainMenuButton(index, 1)"
                    >
                      <template #icon><DownOutlined /></template>
                    </a-button>
                  </div>
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
        <a-tab-pane key="video_v1">
          <template #tab><span data-testid="scene-tab-video-v1">AI动图V1 <span class="scene-tab-count">{{ config.video_scenes_v1.length }}</span></span></template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar"><span class="text-sm text-slate-500">V1 固定使用图生视频；场景、尾帧、跳转与示范素材均独立维护。</span><a-button data-testid="add-video-v1-scene" @click="addVideoScene('video_v1')"><template #icon><PlusOutlined /></template>添加场景</a-button></div>
            <div v-for="{ scene, index } in paginatedVideoV1Scenes" :key="`v1-${scene.id}`" class="scene-row grid gap-3 border-b border-slate-100 py-3 md:grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px]">
              <a-input v-model:value="scene.name" :data-testid="`video-v1-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`video-v1-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`video-v1-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell"><div class="scene-management-actions"><a-button class="scene-icon-button" :disabled="index === 0" @click="moveScene('video_v1', config.video_scenes_v1, index, -1)"><template #icon><UpOutlined /></template></a-button><a-button class="scene-icon-button" :disabled="index === config.video_scenes_v1.length - 1" @click="moveScene('video_v1', config.video_scenes_v1, index, 1)"><template #icon><DownOutlined /></template></a-button><a-button class="scene-icon-button" :data-testid="`config-video-v1-scene-${index}`" @click="openSceneConfig('video_v1', index)"><template #icon><SettingOutlined /></template></a-button><a-button danger class="scene-icon-button" @click="removeVersionedVideoScene('video_v1', index)"><template #icon><DeleteOutlined /></template></a-button></div><div class="scene-demo-button-group"><a-upload :show-upload-list="false" :accept="getDemoMediaAccept('video_v1', 'input')" :before-upload="(file: File) => uploadSceneDemo('video_v1', index, 'input', file)"><a-button size="small">输入示范</a-button></a-upload><a-upload :show-upload-list="false" :accept="getDemoMediaAccept('video_v1', 'output')" :before-upload="(file: File) => uploadSceneDemo('video_v1', index, 'output', file)"><a-button size="small">输出示范</a-button></a-upload></div></div>
            </div>
            <div v-if="config.video_scenes_v1.length === 0" class="py-8 text-center text-sm text-slate-400">暂无场景</div><div v-else class="scene-pagination-bar"><span>共 {{ config.video_scenes_v1.length }} 个场景</span><a-pagination v-model:current="scenePages.video_v1" :total="config.video_scenes_v1.length" :page-size="scenePageSize" :show-size-changer="false" :hide-on-single-page="true" /></div>
          </div>
        </a-tab-pane>
        <a-tab-pane key="video">
          <template #tab>
            <span data-testid="scene-tab-video">AI动图V2 <span class="scene-tab-count">{{ config.video_scenes.length }}</span></span>
          </template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar">
              <span class="text-sm text-slate-500">管理动图按钮、提示词、时长、模型和尾帧来源</span>
              <a-button data-testid="add-video-scene" @click="addVideoScene">
                <template #icon><PlusOutlined /></template>
                添加场景
              </a-button>
            </div>
            <div class="hidden grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid">
              <span>按钮名称</span><span>提示词</span><span>负面提示词</span><span class="text-right">操作</span>
            </div>
            <div
              v-for="{ scene, index } in paginatedVideoScenes"
              :key="scene.id"
              class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px]"
            >
              <a-input v-model:value="scene.name" :data-testid="`video-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`video-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`video-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell">
                <div class="scene-management-actions">
                  <a-button class="scene-icon-button" :disabled="index === 0" :data-testid="`move-video-scene-up-${index}`" title="上移场景" aria-label="上移场景" @click="moveScene('video', config.video_scenes, index, -1)"><template #icon><UpOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :disabled="index === config.video_scenes.length - 1" :data-testid="`move-video-scene-down-${index}`" title="下移场景" aria-label="下移场景" @click="moveScene('video', config.video_scenes, index, 1)"><template #icon><DownOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-video-scene-${index}`" title="场景配置" aria-label="场景配置" @click="openSceneConfig('video', index)"><template #icon><SettingOutlined /></template></a-button>
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
                  <video
                    v-else-if="scene[`demo_${slot}_media`]?.media_type === 'video' && scene[`demo_${slot}_media`]?.preview_url"
                    :src="scene[`demo_${slot}_media`]?.preview_url"
                    :data-testid="`video-demo-${slot}-preview-${index}`"
                    class="scene-demo-video-trigger"
                    muted
                    playsinline
                    preload="metadata"
                    role="button"
                    tabindex="0"
                    :aria-label="`放大查看${scene.name || '场景'}${slot === 'input' ? '输入' : '输出'}示范视频`"
                    @click="openDemoVideoPreview(scene.name, slot, scene[`demo_${slot}_media`]?.preview_url || '')"
                    @keydown.enter.prevent="openDemoVideoPreview(scene.name, slot, scene[`demo_${slot}_media`]?.preview_url || '')"
                    @keydown.space.prevent="openDemoVideoPreview(scene.name, slot, scene[`demo_${slot}_media`]?.preview_url || '')"
                  />
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

        <a-tab-pane key="ai_video">
          <template #tab>
            <span data-testid="scene-tab-ai-video">AI视频 <span class="scene-tab-count">{{ config.ai_video_scenes.length }}</span></span>
          </template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar">
              <span class="text-sm text-slate-500">管理高级图生视频pro按钮、提示词、固定时长和尾帧来源</span>
              <a-button data-testid="add-ai-video-scene" @click="addAiVideoScene"><template #icon><PlusOutlined /></template>添加场景</a-button>
            </div>
            <div class="hidden grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid">
              <span>按钮名称</span><span>提示词</span><span>负面提示词</span><span class="text-right">操作</span>
            </div>
            <div
              v-for="{ scene, index } in paginatedAiVideoScenes"
              :key="scene.id"
              class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px]"
            >
              <a-input v-model:value="scene.name" :data-testid="`ai-video-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`ai-video-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" placeholder="留空使用 ComfyUI 工作流默认负面提示词" :data-testid="`ai-video-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell">
                <div class="scene-management-actions">
                  <a-button class="scene-icon-button" :disabled="index === 0" :data-testid="`move-ai-video-scene-up-${index}`" title="上移场景" @click="moveScene('ai_video', config.ai_video_scenes, index, -1)"><template #icon><UpOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :disabled="index === config.ai_video_scenes.length - 1" :data-testid="`move-ai-video-scene-down-${index}`" title="下移场景" @click="moveScene('ai_video', config.ai_video_scenes, index, 1)"><template #icon><DownOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-ai-video-scene-${index}`" title="场景配置" @click="openSceneConfig('ai_video', index)"><template #icon><SettingOutlined /></template></a-button>
                  <a-button danger class="scene-icon-button" :data-testid="`remove-ai-video-scene-${index}`" title="删除场景" @click="removeAiVideoScene(index)"><template #icon><DeleteOutlined /></template></a-button>
                </div>
                <div class="scene-demo-actions">
                  <span class="scene-demo-action-label">示范素材</span>
                  <div class="scene-demo-button-group">
                    <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('ai_video', 'input')" :before-upload="(file: File) => uploadSceneDemo('ai_video', index, 'input', file)"><a-button size="small" :loading="isDemoUploadLoading(`ai_video:${scene.id}:input`)" :data-testid="`upload-ai-video-demo-input-${index}`"><template #icon><UploadOutlined /></template>输入示范</a-button></a-upload>
                    <a-upload :show-upload-list="false" :accept="getDemoMediaAccept('ai_video', 'output')" :before-upload="(file: File) => uploadSceneDemo('ai_video', index, 'output', file)"><a-button size="small" :loading="isDemoUploadLoading(`ai_video:${scene.id}:output`)" :data-testid="`upload-ai-video-demo-output-${index}`"><template #icon><UploadOutlined /></template>输出示范</a-button></a-upload>
                    <a-button type="primary" size="small" :disabled="!scene.demo_input_media" :loading="isDemoGenerationLoading(`ai_video:${scene.id}`)" :data-testid="`generate-ai-video-demo-${index}`" @click="generateSceneDemo('ai_video', index)"><template #icon><PlayCircleOutlined /></template>生成</a-button>
                  </div>
                </div>
                <div v-if="scene.demo_input_media || scene.demo_output_media" class="scene-demo-preview-strip">
                  <div v-for="slot in demoSlots" :key="slot" class="scene-demo-preview-card">
                    <span class="scene-demo-preview-label">{{ slot === 'input' ? '输入' : '输出' }}</span>
                    <a-image v-if="scene[`demo_${slot}_media`]?.media_type === 'image' && scene[`demo_${slot}_media`]?.preview_url" :src="scene[`demo_${slot}_media`]?.preview_url" :width="60" :height="60" />
                    <video
                      v-else-if="scene[`demo_${slot}_media`]?.media_type === 'video' && scene[`demo_${slot}_media`]?.preview_url"
                      :src="scene[`demo_${slot}_media`]?.preview_url"
                      :data-testid="`ai-video-demo-${slot}-preview-${index}`"
                      class="scene-demo-video-trigger"
                      muted
                      playsinline
                      preload="metadata"
                      role="button"
                      tabindex="0"
                      :aria-label="`放大查看${scene.name || '场景'}${slot === 'input' ? '输入' : '输出'}示范视频`"
                      @click="openDemoVideoPreview(scene.name, slot, scene[`demo_${slot}_media`]?.preview_url || '')"
                      @keydown.enter.prevent="openDemoVideoPreview(scene.name, slot, scene[`demo_${slot}_media`]?.preview_url || '')"
                      @keydown.space.prevent="openDemoVideoPreview(scene.name, slot, scene[`demo_${slot}_media`]?.preview_url || '')"
                    />
                    <span v-else class="scene-demo-preview-empty">未上传</span>
                  </div>
                </div>
              </div>
              <div v-if="scene.mode === 'ref2v'" class="md:col-span-4 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3" :data-testid="`ref2v-reference-manager-${index}`">
                <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div class="text-sm font-medium text-slate-700">管理员参考图（{{ scene.reference_images.length }}/4）</div>
                    <div class="text-xs text-slate-500">用户主体固定为 &lt;Picture 1&gt;；这里依次对应 &lt;Picture 2&gt;–&lt;Picture 5&gt;。</div>
                  </div>
                  <a-upload v-if="scene.reference_images.length < 4" :show-upload-list="false" accept="image/png,image/jpeg,.png,.jpg,.jpeg" :before-upload="(file: File) => uploadReferenceImage(index, scene.reference_images.length, file)">
                    <a-button size="small" :loading="isReferenceUploadLoading(`${scene.id}:${scene.reference_images.length}`)" :data-testid="`add-ref2v-reference-${index}`"><template #icon><UploadOutlined /></template>添加参考图</a-button>
                  </a-upload>
                </div>
                <div class="flex flex-wrap gap-3">
                  <div v-for="(objectKey, referenceIndex) in scene.reference_images" :key="objectKey" class="w-32 rounded-md border border-slate-200 bg-white p-2">
                    <a-image v-if="scene.reference_image_previews?.[referenceIndex]" :src="scene.reference_image_previews[referenceIndex]" :width="112" :height="88" class="object-cover" />
                    <div v-else class="flex h-[88px] items-center justify-center bg-slate-100 text-xs text-slate-400">参考图 {{ referenceIndex + 1 }}</div>
                    <div class="mt-1 text-center text-xs text-slate-500">&lt;Picture {{ referenceIndex + 2 }}&gt;</div>
                    <a-input v-model:value="scene.reference_image_names[referenceIndex]" :maxlength="64" size="small" class="mt-1" :data-testid="`ref2v-reference-name-${index}-${referenceIndex}`" placeholder="模板显示名称" />
                    <div class="mt-2 flex justify-center gap-1">
                      <a-button size="small" :disabled="referenceIndex === 0" @click="moveReferenceImage(scene, referenceIndex, -1)"><template #icon><UpOutlined /></template></a-button>
                      <a-button size="small" :disabled="referenceIndex === scene.reference_images.length - 1" @click="moveReferenceImage(scene, referenceIndex, 1)"><template #icon><DownOutlined /></template></a-button>
                      <a-upload :show-upload-list="false" accept="image/png,image/jpeg,.png,.jpg,.jpeg" :before-upload="(file: File) => uploadReferenceImage(index, referenceIndex, file)"><a-button size="small" :loading="isReferenceUploadLoading(`${scene.id}:${referenceIndex}`)"><template #icon><UploadOutlined /></template></a-button></a-upload>
                      <a-button size="small" danger @click="removeReferenceImage(scene, referenceIndex)"><template #icon><DeleteOutlined /></template></a-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="config.ai_video_scenes.length === 0" class="py-8 text-center text-sm text-slate-400">暂无场景</div>
            <div v-else class="scene-pagination-bar"><span>共 {{ config.ai_video_scenes.length }} 个场景</span><a-pagination v-model:current="scenePages.ai_video" :total="config.ai_video_scenes.length" :page-size="scenePageSize" :show-size-changer="false" :hide-on-single-page="true" show-less-items data-testid="ai-video-scenes-pagination" /></div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="draw_v1">
          <template #tab><span data-testid="scene-tab-draw-v1">AI绘图V1 <span class="scene-tab-count">{{ config.draw_scenes_v1.length }}</span></span></template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar"><span class="text-sm text-slate-500">V1 固定使用自由P图；后处理与示范素材独立维护。</span><a-button data-testid="add-draw-v1-scene" @click="addDrawScene('draw_v1')"><template #icon><PlusOutlined /></template>添加场景</a-button></div>
            <div v-for="{ scene, index } in paginatedDrawV1Scenes" :key="`draw-v1-${scene.id}`" class="scene-row grid gap-3 border-b border-slate-100 py-3 md:grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px]">
              <a-input v-model:value="scene.name" :data-testid="`draw-v1-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`draw-v1-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`draw-v1-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell"><div class="scene-management-actions"><a-button class="scene-icon-button" :disabled="index === 0" @click="moveScene('draw_v1', config.draw_scenes_v1, index, -1)"><template #icon><UpOutlined /></template></a-button><a-button class="scene-icon-button" :disabled="index === config.draw_scenes_v1.length - 1" @click="moveScene('draw_v1', config.draw_scenes_v1, index, 1)"><template #icon><DownOutlined /></template></a-button><a-button class="scene-icon-button" :data-testid="`config-draw-v1-scene-${index}`" @click="openSceneConfig('draw_v1', index)"><template #icon><SettingOutlined /></template></a-button><a-button danger class="scene-icon-button" @click="removeVersionedDrawScene('draw_v1', index)"><template #icon><DeleteOutlined /></template></a-button></div><div class="scene-demo-button-group"><a-upload :show-upload-list="false" :accept="getDemoMediaAccept('draw_v1', 'input')" :before-upload="(file: File) => uploadSceneDemo('draw_v1', index, 'input', file)"><a-button size="small">输入示范</a-button></a-upload><a-upload :show-upload-list="false" :accept="getDemoMediaAccept('draw_v1', 'output')" :before-upload="(file: File) => uploadSceneDemo('draw_v1', index, 'output', file)"><a-button size="small">输出示范</a-button></a-upload></div></div>
            </div>
            <div v-if="config.draw_scenes_v1.length === 0" class="py-8 text-center text-sm text-slate-400">暂无场景</div><div v-else class="scene-pagination-bar"><span>共 {{ config.draw_scenes_v1.length }} 个场景</span><a-pagination v-model:current="scenePages.draw_v1" :total="config.draw_scenes_v1.length" :page-size="scenePageSize" :show-size-changer="false" :hide-on-single-page="true" /></div>
          </div>
        </a-tab-pane>
        <a-tab-pane key="draw">
          <template #tab>
            <span data-testid="scene-tab-draw">AI绘图V2 <span class="scene-tab-count">{{ config.draw_scenes.length }}</span></span>
          </template>
          <div class="scene-pane">
            <div class="scene-pane-toolbar">
              <span class="text-sm text-slate-500">管理绘图按钮、提示词、模型和后处理链</span>
              <a-button data-testid="add-draw-scene" @click="addDrawScene"><template #icon><PlusOutlined /></template>添加场景</a-button>
            </div>
            <div class="hidden grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid">
              <span>按钮名称</span><span>提示词</span><span>负面提示词</span><span class="text-right">操作</span>
            </div>
            <div
              v-for="{ scene, index } in paginatedDrawScenes"
              :key="scene.id"
              class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px]"
            >
              <a-input v-model:value="scene.name" :data-testid="`draw-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`draw-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`draw-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell">
                <div class="scene-management-actions">
                  <a-button class="scene-icon-button" :disabled="index === 0" :data-testid="`move-draw-scene-up-${index}`" title="上移场景" aria-label="上移场景" @click="moveScene('draw', config.draw_scenes, index, -1)"><template #icon><UpOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :disabled="index === config.draw_scenes.length - 1" :data-testid="`move-draw-scene-down-${index}`" title="下移场景" aria-label="下移场景" @click="moveScene('draw', config.draw_scenes, index, 1)"><template #icon><DownOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-draw-scene-${index}`" title="场景配置" aria-label="场景配置" @click="openSceneConfig('draw', index)"><template #icon><SettingOutlined /></template></a-button>
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
            <div class="hidden grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px] items-center gap-3 border-b border-slate-100 pb-2 text-xs font-medium text-slate-500 md:grid">
              <span>按钮名称</span><span>提示词</span><span>负面提示词</span><span class="text-right">操作</span>
            </div>
            <div
              v-for="{ scene, index } in paginatedFilterScenes"
              :key="scene.id"
              class="scene-row grid gap-3 border-b border-slate-100 py-3 last:border-b-0 md:grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_238px]"
            >
              <a-input v-model:value="scene.name" :data-testid="`filter-scene-name-${index}`" />
              <a-textarea v-model:value="scene.prompt" :rows="5" :data-testid="`filter-scene-prompt-${index}`" />
              <a-textarea v-model:value="scene.negative_prompt" :rows="5" :data-testid="`filter-scene-negative-prompt-${index}`" />
              <div class="scene-action-cell">
                <div class="scene-management-actions">
                  <a-button class="scene-icon-button" :disabled="index === 0" :data-testid="`move-filter-scene-up-${index}`" title="上移场景" aria-label="上移场景" @click="moveScene('filter', config.filter_scenes, index, -1)"><template #icon><UpOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :disabled="index === config.filter_scenes.length - 1" :data-testid="`move-filter-scene-down-${index}`" title="下移场景" aria-label="下移场景" @click="moveScene('filter', config.filter_scenes, index, 1)"><template #icon><DownOutlined /></template></a-button>
                  <a-button class="scene-icon-button" :data-testid="`config-filter-scene-${index}`" title="场景配置" aria-label="场景配置" @click="openSceneConfig('filter', index)"><template #icon><SettingOutlined /></template></a-button>
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
      v-model:open="demoVideoPreview.open"
      :title="demoVideoPreview.title"
      :footer="null"
      :width="960"
      data-testid="demo-video-modal"
      wrap-class-name="qqcc-demo-video-modal"
      @cancel="closeDemoVideoPreview"
    >
      <video
        v-if="demoVideoPreview.url"
        :src="demoVideoPreview.url"
        data-testid="demo-video-modal-player"
        class="demo-video-modal-player"
        controls
        autoplay
        playsinline
        preload="metadata"
      />
    </a-modal>

    <a-modal
      v-model:open="sceneConfig.open"
      :title="sceneModalTitle"
      :footer="null"
      :width="720"
      wrap-class-name="qqcc-scene-config-modal"
      @cancel="closeSceneConfig"
    >
      <a-form layout="vertical" class="scene-config-form">
        <section class="scene-config-section" data-testid="scene-config-basic-section">
          <h3>基础配置</h3>
          <div class="scene-config-grid">
            <a-form-item label="灵石消耗" class="mb-0">
              <a-input-number v-model:value="sceneConfig.credit_cost" :min="1" :step="1" :precision="0" :placeholder="sceneConfigCreditCostPlaceholder" data-testid="scene-config-credit-cost" class="w-full" />
            </a-form-item>
            <a-form-item v-if="sceneConfig.kind === 'ai_video'" label="场景模式" class="mb-0">
              <a-select v-model:value="sceneConfig.mode" data-testid="scene-config-ai-video-mode" :get-popup-container="getSceneSelectPopupContainer" @change="onAiVideoModeChange">
                <a-select-option value="i2v">图生视频</a-select-option>
                <a-select-option v-if="props.ref2vEnabled" value="ref2v">参考生视频 REF2V</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item v-if="isVideoSceneKind(sceneConfig.kind)" label="分辨率" class="mb-0">
              <a-select v-model:value="sceneConfig.resolution" data-testid="scene-config-resolution" :get-popup-container="getSceneSelectPopupContainer">
                <a-select-option v-for="item in modelOptions.video_resolutions" :key="item.value" :value="item.value" :disabled="item.value === '1024p' && sceneConfig.duration === '10s'">{{ item.label }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item v-if="sceneConfig.kind === 'ai_video'" label="分辨率" class="mb-0">
              <a-select v-model:value="sceneConfig.resolution" data-testid="scene-config-resolution" :get-popup-container="getSceneSelectPopupContainer">
                <a-select-option v-for="item in modelOptions.ai_video_resolutions" :key="item.value" :value="item.value">{{ item.label }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item v-if="isVideoSceneKind(sceneConfig.kind)" label="时长" class="mb-0">
              <a-select v-model:value="sceneConfig.duration" data-testid="scene-config-duration" :get-popup-container="getSceneSelectPopupContainer">
                <a-select-option v-for="item in durationOptions" :key="item" :value="item" :disabled="item === '10s' && sceneConfig.resolution === '1024p'">{{ item }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item v-if="sceneConfig.kind === 'ai_video'" label="时长" class="mb-0">
              <a-select v-model:value="sceneConfig.duration" data-testid="scene-config-duration" :get-popup-container="getSceneSelectPopupContainer">
                <a-select-option v-for="item in aiVideoDurationOptions" :key="item" :value="item">{{ item }}s</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item v-if="isVideoSceneKind(sceneConfig.kind)" label="画面比例" class="mb-0">
              <a-select v-model:value="sceneConfig.aspect_ratio" data-testid="scene-video-aspect-ratio-select" :get-popup-container="getSceneSelectPopupContainer">
                <a-select-option v-for="item in modelOptions.video_aspect_ratios" :key="item" :value="item">{{ videoAspectRatioLabels[item] }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item v-if="sceneConfig.kind === 'ai_video' && sceneConfig.mode === 'ref2v'" label="固定画面比例" class="mb-0">
              <a-select v-model:value="sceneConfig.aspect_ratio" data-testid="scene-config-ref2v-aspect-ratio" :get-popup-container="getSceneSelectPopupContainer">
                <a-select-option value="16:9">16:9</a-select-option>
                <a-select-option value="9:16">9:16</a-select-option>
                <a-select-option value="1:1">1:1</a-select-option>
              </a-select>
            </a-form-item>
          </div>
        </section>

        <section class="scene-config-section" data-testid="scene-config-model-section">
        <h3>模型配置</h3>
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
        <a-form-item v-if="sceneConfig.kind === 'ai_video'" label="主模型" class="mb-4">
          <a-select
            v-model:value="sceneConfig.main_model"
            data-testid="scene-ai-video-main-model-select"
            class="w-full"
            :get-popup-container="getSceneSelectPopupContainer"
          >
            <a-select-option
              v-for="item in activeAiVideoMainModelOptions"
              :key="item.value"
              :value="item.value"
            >
              {{ item.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item v-if="!isVideoSceneKind(sceneConfig.kind) && sceneConfig.kind !== 'ai_video'" label="附加模型" class="mb-4">
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
        <a-form-item v-if="isVideoSceneKind(sceneConfig.kind)" label="附加模型（最多 5 个）" class="mb-4">
          <a-select
            :value="sceneConfig.video_lora_items.map(item => item.name)"
            mode="multiple"
            show-search
            option-filter-prop="label"
            :max-tag-count="5"
            data-testid="scene-video-lora-select"
            class="w-full"
            :disabled="!activeEngineSupportsLora"
            :get-popup-container="getSceneSelectPopupContainer"
            @change="updateVideoLoraSelection"
          >
            <a-select-option v-for="item in activeLoraOptions" :key="item.value" :value="item.value" :label="item.label" :disabled="sceneConfig.video_lora_items.length >= 5 && !sceneConfig.video_lora_items.some(selected => selected.name === item.value)">{{ item.label }}</a-select-option>
          </a-select>
          <div v-for="item in sceneConfig.video_lora_items" :key="item.name" class="video-lora-strength-row mt-3">
            <div class="min-w-0 truncate text-sm text-slate-600">{{ activeLoraOptions.find(option => option.value === item.name)?.label || item.name }}</div>
            <a-button
              v-if="getWan22LoraHelp(item.name)"
              type="text"
              class="lora-help-button"
              :data-testid="`scene-video-lora-help-${item.name}`"
              :title="`查看 ${activeLoraOptions.find(option => option.value === item.name)?.label || item.name} 说明`"
              :aria-label="`查看 ${activeLoraOptions.find(option => option.value === item.name)?.label || item.name} 说明`"
              @click="openLoraHelp(item.name)"
            >
              <template #icon><InfoCircleOutlined /></template>
            </a-button>
            <a-input-number v-model:value="item.strength" :min="0.1" :max="2" :step="0.05" :precision="2" :data-testid="`scene-video-lora-strength-${item.name}`" />
          </div>
        </a-form-item>
        <a-form-item v-if="sceneConfig.kind === 'ai_video' && activeLoraOptions.length > 0" :label="`附加模型（最多 13 个，当前可选 ${activeLoraOptions.length} 种）`" class="mb-4">
          <a-select
            :value="sceneConfig.lora_items.map(item => item.name)"
            mode="multiple"
            :max-tag-count="5"
            data-testid="scene-ai-video-lora-select"
            class="w-full"
            :disabled="!activeEngineSupportsLora"
            :get-popup-container="getSceneSelectPopupContainer"
            @change="updateAiVideoLoraSelection"
          >
            <a-select-option v-for="item in activeLoraOptions" :key="item.value" :value="item.value" :disabled="sceneConfig.lora_items.length >= 13 && !sceneConfig.lora_items.some(selected => selected.name === item.value)">{{ item.label }}</a-select-option>
          </a-select>
          <div v-for="item in sceneConfig.lora_items" :key="item.name" class="mt-3 grid grid-cols-[minmax(0,1fr)_92px] items-center gap-3">
            <div class="min-w-0 truncate text-sm text-slate-600">{{ activeLoraOptions.find(option => option.value === item.name)?.label || item.name }}</div>
            <a-input-number v-model:value="item.strength" :min="0.1" :max="2" :step="0.05" :precision="2" :data-testid="`scene-ai-video-lora-strength-${item.name}`" />
          </div>
        </a-form-item>
        </section>
        <section v-if="isVideoSceneKind(sceneConfig.kind) || sceneConfig.kind === 'ai_video'" class="scene-config-section" data-testid="scene-config-frame-section">
        <h3>首尾帧配置</h3>
        <a-form-item
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
        <a-form-item label="示例输入跳转至 AI绘图场景" class="mb-4">
          <a-select
            v-model:value="sceneConfig.jump_draw_scene_id"
            data-testid="scene-jump-draw-scene-select"
            class="w-full"
            :get-popup-container="getSceneSelectPopupContainer"
          >
            <a-select-option value="">无</a-select-option>
            <a-select-option v-for="item in activeEndFrameDrawOptions" :key="item.id" :value="item.id">
              {{ item.name || item.id }}
            </a-select-option>
          </a-select>
          <div class="mt-2 text-xs text-slate-500">Bot 会在该场景的示例下展示跳转按钮，用户可进入所选 AI绘图场景生成输入图。</div>
        </a-form-item>
        <a-form-item
          label="自动拼接下一个模板"
          class="mb-4"
        >
          <a-select
            v-model:value="sceneConfig.next_scene_id"
            data-testid="scene-next-video-scene-select"
            class="w-full"
            :get-popup-container="getSceneSelectPopupContainer"
          >
            <a-select-option value="">无</a-select-option>
            <a-select-option
              v-for="item in activeNextVideoSceneOptions"
              :key="item.id"
              :value="item.id"
            >
              {{ item.name || item.id }}
            </a-select-option>
          </a-select>
          <div
            v-if="activeVideoSceneChainPreview"
            class="mt-2 text-xs text-slate-500"
            data-testid="scene-video-chain-preview"
          >
            {{ activeVideoSceneChainPreview }}
          </div>
        </a-form-item>
        </section>
        <section v-if="isDrawSceneKind(sceneConfig.kind) || sceneConfig.kind === 'filter'" class="scene-config-section" data-testid="scene-config-postprocess-section">
        <h3>后处理配置</h3>
        <a-form-item
          v-if="isDrawSceneKind(sceneConfig.kind)"
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
          v-if="isDrawSceneKind(sceneConfig.kind)"
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
          label="原图换脸"
          class="mb-4"
        >
          <a-switch
            v-model:checked="sceneConfig.original_face_swap_enabled"
            data-testid="scene-original-face-swap-switch"
          />
        </a-form-item>
        </section>
        <div class="flex justify-end gap-2">
          <a-button data-testid="scene-config-cancel" @click="closeSceneConfig">取消</a-button>
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

    <a-modal
      :open="Boolean(loraHelp)"
      :title="loraHelpLabel ? `${loraHelpLabel} · 模型说明` : '模型说明'"
      :footer="null"
      :width="760"
      wrap-class-name="qqcc-lora-help-modal"
      data-testid="wan22-lora-help-modal"
      @cancel="closeLoraHelp"
    >
      <div v-if="loraHelp" class="lora-help-content">
        <dl class="lora-help-summary">
          <div>
            <dt>分类</dt>
            <dd>{{ loraHelp.category }}</dd>
          </div>
          <div>
            <dt>用途</dt>
            <dd>{{ loraHelp.purpose }}</dd>
          </div>
          <div>
            <dt>触发词 / 关键词</dt>
            <dd class="lora-help-keywords">
              <code v-for="keyword in loraHelp.trigger_words" :key="keyword">{{ keyword }}</code>
            </dd>
          </div>
          <div>
            <dt>强度</dt>
            <dd>
              <div>HIGH：{{ formatLoraStrengthStage(loraHelp.strength.high) }}</div>
              <div>LOW：{{ formatLoraStrengthStage(loraHelp.strength.low) }}</div>
              <div class="lora-help-source">
                建议来源：{{ loraStrengthSourceLabels[loraHelp.strength.source] || loraHelp.strength.source }}
                <span>（{{ loraHelp.strength.source }}）</span>
              </div>
            </dd>
          </div>
          <div>
            <dt>模型页</dt>
            <dd>
              <a :href="loraHelp.model_page" target="_blank" rel="noopener noreferrer">
                {{ loraHelp.model_page }}
              </a>
            </dd>
          </div>
        </dl>

        <section class="lora-help-section">
          <h3>提示词示例与翻译</h3>
          <details
            v-for="(example, index) in loraHelp.prompt_examples"
            :key="`${index}:${example.prompt}`"
            class="lora-prompt-example"
            :data-testid="`wan22-lora-prompt-example-${index}`"
          >
            <summary>示例 {{ index + 1 }}</summary>
            <div class="lora-prompt-language">英文原文</div>
            <p>{{ example.prompt }}</p>
            <div class="lora-prompt-language">中文翻译</div>
            <p>{{ example.translation_zh }}</p>
          </details>
        </section>

        <section class="lora-help-section">
          <h3>注意点</h3>
          <ul>
            <li v-for="note in loraHelp.notes" :key="note">{{ note }}</li>
          </ul>
        </section>
      </div>
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

:global(.qqcc-lora-help-modal .ant-modal) {
  max-width: calc(100vw - 32px);
  margin: 0 auto;
}

.video-lora-strength-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px 92px;
  align-items: center;
  gap: 10px;
}

.lora-help-button {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #1677ff;
  font-size: 17px;
}

.lora-help-content {
  max-height: min(72vh, 760px);
  overflow-y: auto;
  padding-right: 6px;
  color: #334155;
}

.lora-help-summary {
  display: grid;
  gap: 14px;
  margin: 0;
}

.lora-help-summary > div {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 12px;
}

.lora-help-summary dt,
.lora-help-section h3 {
  color: #0f172a;
  font-weight: 700;
}

.lora-help-summary dd {
  min-width: 0;
  margin: 0;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.lora-help-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.lora-help-keywords code {
  border-radius: 6px;
  padding: 2px 7px;
  background: #f1f5f9;
  color: #334155;
  white-space: normal;
}

.lora-help-source {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.lora-help-section {
  margin-top: 20px;
}

.lora-help-section h3 {
  margin: 0 0 10px;
  font-size: 15px;
}

.lora-prompt-example {
  margin-bottom: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  background: #f8fafc;
}

.lora-prompt-example summary {
  cursor: pointer;
  color: #1e293b;
  font-weight: 600;
}

.lora-prompt-example p {
  margin: 4px 0 12px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.lora-prompt-language {
  margin-top: 12px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.lora-help-section ul {
  margin: 0;
  padding-left: 20px;
}

.lora-help-section li {
  margin-bottom: 6px;
  line-height: 1.65;
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
.scene-credit-cell,
.scene-action-cell {
  display: flex;
  align-items: center;
}

.scene-duration-cell {
  justify-content: flex-start;
}

.scene-credit-cell {
  min-width: 0;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}

.scene-credit-input {
  width: 100%;
}

.scene-mobile-field-label {
  display: none;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
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

.scene-demo-video-trigger {
  cursor: zoom-in;
}

.demo-video-modal-player {
  display: block;
  width: 100%;
  max-height: min(72vh, 760px);
  border-radius: 10px;
  background: #020617;
  object-fit: contain;
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

.scene-config-form {
  max-height: min(72vh, 760px);
  overflow-y: auto;
  padding-right: 6px;
}

.scene-config-section {
  margin-bottom: 18px;
  padding: 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.scene-config-section h3 {
  margin: 0 0 14px;
  color: #0f172a;
  font-size: 15px;
  font-weight: 700;
}

.scene-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
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
  .video-lora-strength-row {
    grid-template-columns: minmax(0, 1fr) 34px 84px;
    gap: 8px;
  }

  .lora-help-summary > div {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }

  .scene-config-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .scene-row {
    align-items: stretch;
  }

  .scene-duration-cell,
  .scene-credit-cell,
  .scene-action-cell {
    justify-content: flex-start;
  }

  .scene-mobile-field-label {
    display: block;
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
