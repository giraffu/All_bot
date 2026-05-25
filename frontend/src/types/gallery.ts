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
  is_active: boolean
  prompt: string | null
  task_type?: string | null
  author_name?: string | null
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
  output_file: string | null
  billing_resolution?: string | null
  width?: number | null
  height?: number | null
  duration?: number | null
  requested_duration?: number | null
  output_file_url?: string | null
  thumbnail_url?: string | null
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

export type LibraryCollectionScope = 'favorite' | 'like' | 'apply' | 'submissions'
export type ApplyContextSource = 'gallery' | 'favorites' | 'submissions'
