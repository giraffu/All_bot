import type { GalleryPost } from '@/types/gallery'

export interface PublicUserSummary {
  id: number
  author_name: string
  username?: string | null
  user_group: string
  current_identity: string
  checkin_count: number
  total_public_posts: number
  followers_count: number
  following_count: number
  is_following: boolean
  is_self: boolean
}

export interface PublicUserProfileResponse {
  user: PublicUserSummary
  recent_posts: GalleryPost[]
}

export interface FollowingListResponse {
  items: PublicUserSummary[]
  total: number
}

export interface FollowActionResponse {
  success: boolean
  is_following: boolean
}
