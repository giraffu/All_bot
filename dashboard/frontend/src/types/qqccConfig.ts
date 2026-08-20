export type MainButtonKey =
  | 'quick_undress' | 'quick_faceswap' | 'photo_edit' | 'ai_draw' | 'ai_draw_v1'
  | 'ai_draw_v2' | 'ai_filter' | 'video_edit' | 'video_edit_v1' | 'video_edit_v2'
  | 'ai_video' | 'market' | 'queue' | 'main_bot_link' | 'private_bot'
export type MainMenuButtonKey = Exclude<MainButtonKey, 'quick_undress' | 'photo_edit'>
export type MainMenuButtonsPerRow = 1 | 2 | 3 | 4
export type PhotoButtonKey = 'masturbation' | 'random_faceswap'
export type UndressMethodKey = 'legacy' | 'i2i_draw'
export type VideoButtonKey = 'missionary' | 'doggy' | 'blowjob' | 'undress_tongue' | 'closeup_blowjob'
export type ResolutionKey = '512p' | '720p' | '1024p'
export type AiVideoResolutionKey = 'preview' | 'small' | 'standard' | 'hd'
export type DurationKey = '5s' | '8s' | '10s'
export type AiVideoDurationKey = 5 | 10 | 15
export type VideoSceneEngine = 'image_to_video' | 'wan22_video_v2'
export type VideoAspectRatio = 'source' | '9:16' | '16:9' | '1:1'
export type AiVideoSceneEngine = 'minimax_h3'
export type AiVideoMode = 'i2v' | 'ref2v'
export type AiVideoAspectRatio = '16:9' | '9:16' | '1:1'
export type DrawSceneEngine = 'free_edit' | 'free_edit_v2' | 'free_edit_v2_5' | 'free_edit_v3'
export type SceneConfigKind = 'video' | 'video_v1' | 'ai_video' | 'draw' | 'draw_v1' | 'filter'
export type DemoMediaSlot = 'input' | 'output'
export type DemoUploadFile = File & { originFileObj?: File }
export type PromptKey =
  | 'undress' | 'i2i_draw_quick_undress' | 'masturbation' | 'face_swap'
  | 'perfect_video_insert' | 'doggy_style' | 'blowjob' | 'undress_tongue'
  | 'closeup_blowjob'
export type CopywritingKey =
  | 'quick_faceswap_start' | 'ai_draw_menu' | 'ai_filter_menu' | 'video_menu'
  | 'ai_video_menu' | 'ai_draw_scene_start' | 'ai_filter_scene_start'
  | 'video_scene_start' | 'ai_video_scene_start'

export interface SceneDemoMedia {
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

export interface VideoLoraItem { name: string; strength: number }
export interface AiVideoLoraItem { name: string; strength: number }

export interface VideoSceneConfig extends SceneDemoFields {
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

export interface AiVideoSceneConfig extends SceneDemoFields {
  id: string
  name: string
  prompt: string
  negative_prompt: string
  duration: AiVideoDurationKey
  resolution: AiVideoResolutionKey
  engine: AiVideoSceneEngine
  mode: AiVideoMode
  reference_images: string[]
  reference_image_previews?: string[]
  aspect_ratio: AiVideoAspectRatio
  lora_items: AiVideoLoraItem[]
  end_frame_draw_scene_id: string
  jump_draw_scene_id?: string
  next_scene_id: string | null
  credit_cost: number | null
}

export interface DrawSceneConfig extends SceneDemoFields {
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

export interface FilterSceneConfig extends SceneDemoFields {
  id: string
  name: string
  prompt: string
  negative_prompt: string
  engine: DrawSceneEngine
  lora_name: string
  original_face_swap_enabled: boolean
  credit_cost: number | null
}

export interface QqccBotConfig {
  scene_preset_version: number
  global_enabled: boolean
  main_buttons: Record<MainButtonKey, boolean>
  main_menu_layout: { buttons_per_row: MainMenuButtonsPerRow | null; button_order: MainMenuButtonKey[] }
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

export interface SceneEngineOption { value: string; supports_lora: boolean }
export interface LoraModelOption { value: string; label: string; default_strength?: number }
export interface ResolutionOption<T extends string> { value: T; label: string }
export interface QqccBotConfigOptions {
  scene_preset_version: number
  default_video_engine: VideoSceneEngine
  default_ai_video_engine: AiVideoSceneEngine
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
  default_video_resolution: ResolutionKey
  default_ai_video_resolution: AiVideoResolutionKey
  default_scene_credit_costs: Partial<Record<SceneConfigKind, number>>
}

export interface QqccBotConfigResponse {
  key?: string
  updated_at?: string | null
  config?: Partial<QqccBotConfig>
  options?: Partial<QqccBotConfigOptions>
}
export interface QqccDemoMediaUploadResponse { media: SceneDemoMedia; preview_url: string }
export interface QqccReferenceImageUploadResponse {
  media: SceneDemoMedia
  preview_url: string
}
export interface QqccDemoGenerationResponse extends Partial<QqccDemoMediaUploadResponse> {
  generation_id: string
  status: string
  config_saved?: boolean
  error?: string
}
export type SceneConfig = VideoSceneConfig | AiVideoSceneConfig | DrawSceneConfig | FilterSceneConfig
