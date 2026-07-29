export interface User {
  id: number
  username: string | null
  full_name: string | null
  language_code: string | null
  credits: number
  user_group: string
  current_identity: string
}

export type AnimationId = 'idle' | 'turntable' | 'photo_pose' | 'dance_lite'
export type CameraPreset = 'front' | 'side' | 'back' | 'full_body' | 'half_body' | 'portrait'
export type BackgroundId = 'light' | 'dark' | 'transparent' | 'studio'
export type Resolution = '720x1280' | '1280x720' | '1024x1024'

export interface ModelView {
  view_type: string
  status: string
  width: number | null
  height: number | null
  preview_url: string | null
}

export interface ModelAsset {
  id: string
  character_id: string
  version: number
  provider: string
  status: string
  error_code: string | null
  model_url: string | null
  thumbnail_url: string | null
  rig_type: string | null
  animation_ids: AnimationId[]
  metadata: Record<string, unknown>
  views: ModelView[]
  created_at: string
  updated_at: string
}

export interface MiniCharacter {
  id: string
  name: string
  description: string | null
  status: string
  source_object_key: string
  preview_url: string | null
  latest_model: ModelAsset | null
}

export interface RenderJob {
  id: string
  asset_id: string
  status: string
  recipe: Record<string, unknown>
  error_code: string | null
  output_url: string | null
  created_at: string
  updated_at: string
}
