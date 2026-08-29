export interface TaskExtraOutput {
  path: string
  media_type: string
  url?: string | null
}

export interface PromptModel {
  id: string
  display_key: string
  strength?: number
}

export type TaskExtraOutputs = Record<string, TaskExtraOutput>

export interface Wan22ResultMeta {
  wan22_resolution_preset?: string
  wan22_duration_seconds?: number
  wan22_negative_prompt?: string
  wan22_use_end_frame?: boolean
  wan22_prev_task_id?: string
  wan22_chain_task_ids?: string[]
  wan22_segment_index?: number
  wan22_is_stitched?: boolean
  wan22_model_profile?: string
  lora_name?: string
  lora_strength?: number
  ltx_mode?: string
  ltx_use_end_frame?: boolean
  ltx_prev_task_id?: string
  ltx_chain_task_ids?: string[]
  ltx_segment_index?: number
  ltx_is_stitched?: boolean
  ltx_width?: number
  ltx_height?: number
  ltx_duration_seconds?: number
  lora_items?: Array<{ name: string; strength?: number }>
  minimax_h3_prev_task_id?: string
  minimax_h3_chain_task_ids?: string[]
  minimax_h3_segment_index?: number
  minimax_h3_is_stitched?: boolean
}

export interface GalleryPost {
  id: number
  task_id: string
  media_type: string
  billing_resolution?: string | null
  width: number | null
  height: number | null
  duration: number | null
  tags: string[]
  likes_count: number
  dislikes_count: number
  applied_count: number
  comments_count: number
  thumbnail_url: string
  media_url: string
  created_at: string
  has_liked: boolean
  has_disliked: boolean
  author_id?: number | null
  is_active: boolean
  prompt: string | null
  prompt_model?: PromptModel | null
  prompt_unlocked?: boolean
  prompt_unlockable?: boolean
  prompt_is_masked?: boolean
  prompt_unlock_price?: number
  task_type?: string | null
  result_meta?: Wan22ResultMeta
  input_file?: string | null
  input_file_url?: string | null
  input_files?: string[]
  input_file_urls?: string[]
  template_apply_supported?: boolean
  template_apply_disabled_reason?: 'wan22_stitched' | string | null
  author_name?: string | null
  author_username?: string | null
  is_following_author?: boolean
  src?: string
  cardIsVideo?: boolean
  cardPoster?: string
  imgLoaded?: boolean
}

export interface HistoryItem {
  id: number
  task_id: string | null
  type: string | null
  prompt: string | null
  prompt_model?: PromptModel | null
  input_file: string | null
  input_file_urls?: string[]
  output_file: string | null
  billing_resolution?: string | null
  width?: number | null
  height?: number | null
  duration?: number | null
  requested_duration?: number | null
  output_file_url?: string | null
  thumbnail_url?: string | null
  extra_outputs?: TaskExtraOutputs
  result_meta?: Wan22ResultMeta
  created_at: string
  allow_contribute?: boolean | null
  source?: string | null
  is_public?: boolean | null
  is_favorited?: boolean | null
}

export type TaskRecord = Omit<HistoryItem, 'task_id' | 'type'> & {
  task_id: string
  type: string
}

export interface PaginatedGalleryResponse<TItem = GalleryPost> {
  items: TItem[]
  total: number
  page: number
  size: number
  pages: number
}

export interface RecentHistoryResponse {
  items: HistoryItem[]
  total: number
  page: 1
  size: 8
}

export interface Wan22HistoryChainResponse {
  current_task_id: string
  items: HistoryItem[]
}

export interface LtxHistoryChainResponse {
  current_task_id: string
  items: HistoryItem[]
}

export interface MiniMaxH3HistoryChainResponse {
  current_task_id: string
  items: HistoryItem[]
}

export type LibraryCollectionScope = 'favorite' | 'like' | 'apply' | 'prompt_templates' | 'submissions'
export type ApplyContextSource = 'gallery' | 'favorites' | 'submissions'
