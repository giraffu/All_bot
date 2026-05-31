export interface TaskExtraOutput {
  path: string
  media_type: string
  url?: string | null
}

export type TaskExtraOutputs = Record<string, TaskExtraOutput>

export interface Wan22ResultMeta {
  wan22_resolution_preset?: string
  wan22_negative_prompt?: string
  wan22_use_end_frame?: boolean
  wan22_prev_task_id?: string
  wan22_chain_task_ids?: string[]
  wan22_segment_index?: number
  wan22_is_stitched?: boolean
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
  task_type?: string | null
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

export type LibraryCollectionScope = 'favorite' | 'like' | 'apply' | 'submissions'
export type ApplyContextSource = 'gallery' | 'favorites' | 'submissions'
